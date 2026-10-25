#!/bin/sh
set -eu
case $0 in */*) cd "${0%/*}" ;; esac
cd ..
grep -rlE 'parse_legacy\(' relay --include='*.py' | grep -v 'oldparse\.py' | wc -l | tr -d ' '
