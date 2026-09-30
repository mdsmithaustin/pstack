#!/usr/bin/env bash
# Exit 1 when the diff against $1 touches code and adds nothing under Unreleased.
set -euo pipefail
base="$1"
changed=$(git diff --name-only "$base"...HEAD)
if ! grep -qE '^(internal|cmd)/' <<<"$changed"; then
  echo "no code changes; changelog not required"
  exit 0
fi
added=$(git diff "$base"...HEAD -- CHANGELOG.md | sed -n '/^+## Unreleased/,/^+## /p' | grep -c '^+- ' || true)
if [ "$added" -eq 0 ]; then
  added=$(git diff -U0 "$base"...HEAD -- CHANGELOG.md | grep -c '^+- ' || true)
fi
if [ "$added" -eq 0 ]; then
  echo "code changed but CHANGELOG.md has no new line under Unreleased"
  exit 1
fi
echo "changelog updated ($added line(s))"
