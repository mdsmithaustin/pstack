# relay

Imports partner feeds into a local store, one file per record. Feeds are JSON or CSV and are turned into `key=value` lines before parsing.

    python3 -m relay import feeds/sample.json --store out/

Tests: `python3 -m unittest discover -s tests`

The cache key format in `cache.py` is provisional and expensive to change later. `tools/old_callers.sh` counts the modules still on the legacy parser.
