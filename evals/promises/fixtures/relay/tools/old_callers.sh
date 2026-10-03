#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
grep -rlE 'parse_legacy\(' relay --include='*.py' | grep -v 'oldparse\.py' | wc -l | tr -d ' '
