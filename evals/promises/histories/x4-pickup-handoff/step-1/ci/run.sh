#!/bin/sh
# The hosted runner calls this same script on every push.
set -e
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests -v
