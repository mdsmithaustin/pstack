#!/bin/sh
set -eu
case $0 in */*) cd "${0%/*}" ;; esac
python3 -m unittest -q
