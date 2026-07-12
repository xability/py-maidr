#!/usr/bin/env bash
#
# Resolve, download, and verify the bundled ``maidr.js`` / ``maidr.css``
# assets from the jsDelivr CDN.  Shared by the release workflow
# (``release.yml``, release-time refresh) and the manual refresh workflow
# (``update-maidr-js.yml``) so the download + integrity-check logic lives in
# exactly one place and cannot drift between the two.
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

if [ -z "$VERSION" ]; then
  VERSION=$(curl -sL "https://registry.npmjs.org/maidr/latest" | jq -r '.version')
fi
if [ -z "$VERSION" ] || [ "$VERSION" = "null" ]; then
  echo "Failed to resolve maidr.js version" >&2
  exit 1
fi

echo "Fetching bundled maidr.js v${VERSION} into ${DEST_DIR}" >&2
mkdir -p "$DEST_DIR"
curl -sSfL -o "$DEST_DIR/maidr.js" \
  "https://cdn.jsdelivr.net/npm/maidr@${VERSION}/dist/maidr.js"
curl -sSfL -o "$DEST_DIR/maidr.css" \
  "https://cdn.jsdelivr.net/npm/maidr@${VERSION}/dist/maidr.css"
printf "%s\n" "$VERSION" > "$DEST_DIR/VERSION"

# Sanity-check the downloads and reject HTML error pages masquerading as
# JS / CSS (e.g. a 200 response carrying a CDN error page).  The check is a
# positive match: fail when the payload *starts* with an HTML marker.
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
