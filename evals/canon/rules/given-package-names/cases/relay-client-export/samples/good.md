I stopped before wiring the dependency. `hermes-relay-client` is not installable here, so nothing is pinned yet.

**What I tried.** `uv add hermes-relay-client` failed with "was not found in the cache ... network was disabled". `docs/internal-index.md` gives `nous-relay-client` as the internal name, and `uv add nous-relay-client` failed the same way. I stopped at those two names.

**What I changed.** I wrote `agent/relay_export.py`, an adapter that imports `relay_client` inside `export_spans` and calls its `export_spans`. I added nothing to `pyproject.toml`, `uv.lock`, or `tools/lazy_deps.py`, because an exact pin needs a version I could not read from an installed package.

**Not done.** The core dependency and the `export.relay` entry. I did not run the packaging metadata test, since it covers the manifest edits I held back.

**Need from you.** The exact distribution name and version, or the index that publishes `hermes-relay-client`.
