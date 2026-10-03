# relay

Relay is a small tool that not only imports partner feeds but also keeps a local store of them, one file per record — nothing more, nothing less. Feeds arrive as JSON or CSV, and each one is turned into `key=value` lines before it is parsed.

## Running an import

To import a feed, point relay at the file and tell it where the store lives:

    python3 -m relay import feeds/sample.json --store out/

The importer reads the feed, parses it, and writes the records — every record gets its own file, named after its id. Importing the same feed twice replaces the files that were written earlier, so a second run is safe.

## How feeds are read

Relay looks at the suffix of the feed to decide how to load it, and it handles `.json` and `.csv`. When the importer loads a feed it checks the cache, which lives only as long as the process does and builds its key from the feed name and an offset. A feed that fails to load is retried up to three times, and the retries are not only there for slow mirrors but also for feeds that arrive empty — a half-written file is treated the same way.

## The format

A feed holds one record per line, with `key=value` pairs separated by `;`. Blank lines and lines that start with `#` are skipped. Keys are lowercased, and so are ids — so `ID=A1` and `id=a1` name the same record. Lines without an equals sign or an id are rejected.

Two parsers read this format. The one in `parse.py` returns `Record` objects, and the one in `oldparse.py` returns plain dicts; they not only agree on every case under `tests/cases` but also share the same rules for what counts as a bad line. Both read the lines a feed loader produces and the lines in the test cases.

## Tests and housekeeping

Run the tests with `python3 -m unittest discover -s tests`. The cache key format in `cache.py` is provisional and expensive to change later — please do not build on it yet. `tools/old_callers.sh` counts the modules still on the legacy parser, and the number is expected to fall.
