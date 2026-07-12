#!/usr/bin/env bash
#
# Resolve, download, and verify the bundled ``maidr.js`` / ``maidr.css``
# assets.  Shared by the release workflow (``release.yml``, release-time
# refresh) and the manual refresh workflow (``update-maidr-js.yml``) so the
# download + integrity-check logic lives in exactly one place and cannot
# drift between the two.
#
# The assets are extracted from the official npm tarball, whose contents are
# verified against the ``dist.integrity`` (SRI) / ``dist.shasum`` hash
# published in the npm registry metadata.  This gives a real supply-chain
# guarantee: a tampered CDN/registry response fails the hash check instead of
# being written into the bundle (and, at release time, shipped to PyPI).
#
# Usage:
#   fetch-maidr-bundle.sh [VERSION] [DEST_DIR]
#
#   VERSION   maidr npm version to fetch.  Resolves the latest published
#             version on npm when empty or omitted.
#   DEST_DIR  directory to write ``maidr.js`` / ``maidr.css`` / ``VERSION``
#             into.  Defaults to ``maidr/static``.
#
# The resolved version is written to ``<DEST_DIR>/VERSION`` and printed as the
# final line of stdout so callers can capture it, e.g.
# ``VERSION=$(fetch-maidr-bundle.sh)``.  All progress output goes to stderr to
# keep stdout limited to the version string.
set -euo pipefail

VERSION="${1:-}"
DEST_DIR="${2:-maidr/static}"

REGISTRY="https://registry.npmjs.org/maidr"

if [ -z "$VERSION" ]; then
  VERSION=$(curl -sSfL "$REGISTRY/latest" | jq -r '.version')
fi
if [ -z "$VERSION" ] || [ "$VERSION" = "null" ]; then
  echo "Failed to resolve maidr.js version" >&2
  exit 1
fi

# Validate the version shape before splicing it into any URL.  This rejects
# malformed or hostile values (e.g. a caller-supplied version) so they cannot
# build an unintended request path.
if ! printf '%s' "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+([-+.][0-9A-Za-z.-]+)*$'; then
  echo "Refusing to fetch: '$VERSION' is not a valid maidr version" >&2
  exit 1
fi

echo "Fetching bundled maidr.js v${VERSION} into ${DEST_DIR}" >&2

# Fetch the registry metadata for this exact version to get the tarball URL
# and its published integrity hash.
META=$(curl -sSfL "$REGISTRY/$VERSION")
TARBALL=$(printf '%s' "$META" | jq -r '.dist.tarball // empty')
INTEGRITY=$(printf '%s' "$META" | jq -r '.dist.integrity // empty')
SHASUM=$(printf '%s' "$META" | jq -r '.dist.shasum // empty')
if [ -z "$TARBALL" ]; then
  echo "Failed to resolve npm tarball URL for maidr@$VERSION" >&2
  exit 1
fi

WORK=$(mktemp -d)
# shellcheck disable=SC2064  # expand WORK now so the trap removes this dir
trap "rm -rf '$WORK'" EXIT
TGZ="$WORK/maidr.tgz"
curl -sSfL -o "$TGZ" "$TARBALL"

# Verify the tarball against the registry-published hash.  Prefer the SRI
# ``integrity`` field (sha512); fall back to the legacy ``shasum`` (sha1).
if [ -n "$INTEGRITY" ]; then
  ALGO=${INTEGRITY%%-*}
  EXPECTED=${INTEGRITY#*-}
  ACTUAL=$(openssl dgst "-${ALGO}" -binary "$TGZ" | openssl base64 -A)
  if [ "$ACTUAL" != "$EXPECTED" ]; then
    echo "Integrity check failed for maidr@$VERSION tarball ($ALGO)" >&2
    exit 1
  fi
  echo "Verified tarball ${ALGO} integrity" >&2
elif [ -n "$SHASUM" ]; then
  ACTUAL=$(sha1sum "$TGZ" | awk '{print $1}')
  if [ "$ACTUAL" != "$SHASUM" ]; then
    echo "Shasum check failed for maidr@$VERSION tarball" >&2
    exit 1
  fi
  echo "Verified tarball shasum" >&2
else
  echo "No integrity/shasum in registry metadata for maidr@$VERSION" >&2
  exit 1
fi

# Extract the bundled assets from the verified tarball.  npm tarballs place
# published files under ``package/``.
tar -xzf "$TGZ" -C "$WORK" package/dist/maidr.js package/dist/maidr.css
mkdir -p "$DEST_DIR"
cp "$WORK/package/dist/maidr.js" "$DEST_DIR/maidr.js"
cp "$WORK/package/dist/maidr.css" "$DEST_DIR/maidr.css"
printf "%s\n" "$VERSION" > "$DEST_DIR/VERSION"

# Defense-in-depth sanity checks: non-empty, and not an HTML error page
# masquerading as JS / CSS.  The check is a positive match: fail when the
# payload *starts* with an HTML marker.
test -s "$DEST_DIR/maidr.js"
test -s "$DEST_DIR/maidr.css"
test -s "$DEST_DIR/VERSION"
for asset in maidr.js maidr.css; do
  if head -c 128 "$DEST_DIR/${asset}" | grep -qiE "^[[:space:]]*<!DOCTYPE|^[[:space:]]*<html"; then
    echo "${asset} looks like an HTML error page" >&2
    exit 1
  fi
done

echo "$VERSION"
