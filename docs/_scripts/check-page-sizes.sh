#!/usr/bin/env bash
# Fail when a rendered page grows past what Googlebot will read.
#
# Googlebot fetches the first 2 MB (2,097,152 bytes, uncompressed) of an HTML
# file and discards the rest, so anything after that point is invisible to
# search and to the AI features built on it. The limit here leaves headroom.
#
# Run by both jobs in .github/workflows/docs.yml: the pull request render and
# the publish build, so the page that ships is the page that was checked.
#
# Usage: check-page-sizes.sh <site-directory>
set -euo pipefail

site="${1:?usage: check-page-sizes.sh <site-directory>}"
limit=1900000

echo "Five largest HTML files under ${site}:"
find "${site}" -type f -name '*.html' -printf '%s %p\n' | sort -nr | head -n 5

too_big="$(find "${site}" -type f -name '*.html' -size +"${limit}"c -printf '%s %p\n' | sort -nr)"
if [ -n "${too_big}" ]; then
  echo "::error::HTML pages larger than ${limit} bytes:"
  echo "${too_big}"
  exit 1
fi
echo "All HTML pages are at most ${limit} bytes."
