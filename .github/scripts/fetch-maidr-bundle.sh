#!/usr/bin/env bash
#
# Resolve, download, and verify the bundled ``maidr.js``, ``maidr.css`` and
# ``maidr-math.css`` assets.  Shared by the release workflow
# (``release.yml``, release-time refresh) and the manual refresh workflow
# (``update-maidr-js.yml``) so the
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
#   DEST_DIR  directory to write the assets and ``VERSION``
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
#
# Spelled out as semver's real grammar -- numeric identifiers with no leading
# zeros, then an optional "-prerelease" of non-empty dot-separated
# identifiers, then an optional "+build" -- to stay in step with _VERSION_RE
# in maidr/util/dependencies.py, so this script cannot bundle a version the
# library would refuse to pin.
#
# That parity is enforced, not just asserted here:
# tests/core/test_cdn_version.py::test_shell_guard_matches_the_python_validator
# runs this exact pattern and length cap against the Python validator over a
# shared corpus, so the two cannot silently diverge. The patterns are spelled
# differently on purpose -- bash's [[ =~ ]] takes POSIX ERE, which has no
# (?:...) -- so only a behavioural comparison can check them.
#
# Uses bash's [[ =~ ]] rather than grep because `grep -qE '^...$'` matches if
# *any* line matches, so a VERSION with an embedded newline passed here while
# Python's \Z anchor rejected it. [[ =~ ]] tests the whole string.
#
# This is not a ReDoS fix -- GNU grep -E is DFA-based and does not backtrack,
# whereas glibc regexec does. The catastrophic-backtracking problem was in the
# Python pattern, and was fixed there.
#
# Length is checked first, mirroring _is_valid_version's size-before-shape
# order, so an oversized value never reaches the regex engine.
NUM_ID='0|[1-9][0-9]*'
PRE_ID="0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*"
VERSION_RE="^($NUM_ID)\.($NUM_ID)\.($NUM_ID)(-($PRE_ID)(\.($PRE_ID))*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$"
if [ "${#VERSION}" -gt 128 ] || ! [[ "$VERSION" =~ $VERSION_RE ]]; then
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
#
# ``maidr-math.css`` is KaTeX, which maidr 3.75.1 split out of ``maidr.css``
# so that pages stop paying ~360 kB for maths they will probably never
# render.  ``maidr.js`` fetches it at runtime, resolved *relative to the URL
# it was itself loaded from* -- so an offline render that ships ``maidr.js``
# without it renders LaTeX in AI chat responses unstyled, quietly, and only
# for readers who opened the chat.  It has to travel with the bundle.
#
# Checked before extracting so a maidr older than 3.75.1 fails with a
# sentence rather than with tar's "Not found in archive".  py-maidr stopped
# linking ``maidr.css`` when that release turned it into a placeholder, so a
# bundle without ``maidr-math.css`` has no stylesheet at all.
#
# Listed into a variable first, then matched from a here-string: under
# ``set -o pipefail`` a ``tar | grep -q`` pipeline reports failure on
# *success*, because grep exits at the first match and tar dies of SIGPIPE.
TARBALL_FILES=$(tar -tzf "$TGZ")
if ! grep -qx 'package/dist/maidr-math.css' <<<"$TARBALL_FILES"; then
  echo "maidr@$VERSION does not ship dist/maidr-math.css." >&2
  echo "py-maidr requires maidr >= 3.75.1; refusing to bundle $VERSION." >&2
  exit 1
fi

tar -xzf "$TGZ" -C "$WORK" \
  package/dist/maidr.js package/dist/maidr.css package/dist/maidr-math.css
mkdir -p "$DEST_DIR"
cp "$WORK/package/dist/maidr.js" "$DEST_DIR/maidr.js"
cp "$WORK/package/dist/maidr.css" "$DEST_DIR/maidr.css"
cp "$WORK/package/dist/maidr-math.css" "$DEST_DIR/maidr-math.css"
printf "%s\n" "$VERSION" > "$DEST_DIR/VERSION"

# Defense-in-depth sanity checks: non-empty, and not an HTML error page
# masquerading as JS / CSS.  The check is a positive match: fail when the
# payload *starts* with an HTML marker.
test -s "$DEST_DIR/maidr.js"
test -s "$DEST_DIR/maidr.css"
test -s "$DEST_DIR/maidr-math.css"
test -s "$DEST_DIR/VERSION"
for asset in maidr.js maidr.css maidr-math.css; do
  if head -c 128 "$DEST_DIR/${asset}" | grep -qiE "^[[:space:]]*<!DOCTYPE|^[[:space:]]*<html"; then
    echo "${asset} looks like an HTML error page" >&2
    exit 1
  fi
done

echo "$VERSION"
