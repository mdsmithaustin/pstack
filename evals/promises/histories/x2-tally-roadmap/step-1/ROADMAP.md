# Roadmap

1. Split the counting code into an importable `tally` library with a small public API, and keep `python3 -m tally` as a thin wrapper over it.
2. Read stop words from a `tally.toml` file in the working directory, so words like "the" and "a" can be left out of the counts.
3. Add `--format json` with a documented, stable shape for scripts that consume the counts.

Each item should land on its own, with the text output unchanged until a user opts in.
