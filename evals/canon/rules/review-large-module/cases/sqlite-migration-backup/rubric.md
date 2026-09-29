# Grading guide: SQLite backup before migration (positive)

## Flaw location

`omnigent/db/utils.py`, lines 769-863 after the PR: the `_SQLITE_BACKUP_*` constants, `sqlite_database_path`, `backup_sqlite_database`, and `_backup_hint`, called from `_initialize_or_verify_schema`.

## The flaw

A file that is already well over 1,000 lines takes on a new responsibility.

`utils.py` is 1,527 lines on main, and the PR takes it to 1,627. Its docstring reads "Database utilities — engine caching, session management, helpers." It already holds engine caching, Lakebase tokens, migrations, session makers, id generation, full-text search helpers, and time helpers. The PR adds a separate job: managing backup files. `sqlite_database_path` finds the file behind a URL. `backup_sqlite_database` checks free disk space, creates the copy with the source's permission bits, runs SQLite's online backup API, cleans up a partial copy, and prunes old copies. None of it touches an `Engine` or a session. The only link to the rest of the file is one call in `_initialize_or_verify_schema` and the changed error text. The `omnigent/db` package already splits topics into sibling modules, such as `cockroachdb.py` (358 lines), `compression.py` (137 lines), `metrics.py` (78 lines), and `workspace_cache.py` (184 lines).

The fix is to put the backup code in its own module. Move the constants, `sqlite_database_path`, and `backup_sqlite_database` into a new module, for example `omnigent/db/sqlite_backup.py` (Move Function, Extract Class), and call it from `_initialize_or_verify_schema`. `_backup_hint` can move with them or stay. `utils.py` then grows only by the call and the message change. A wider split of `utils.py` counts too, when the backup code lands in a module of its own.

## Grading

- FOUND. The review names `utils.py`, or the backup functions in it. It says what is wrong. Either `utils.py` is already large (over about 1,000 lines, a line count such as "1,500 lines", or plainly "already huge", "a god module", "too big"), or the backup code is a separate job, file management rather than engine and session code. It asks for the backup code to live in its own module. Either reason is enough. A review that asks for the move on cohesion alone and never mentions size is FOUND. The ask may be blocking or a clear request for this PR.
- PARTIAL. Any one of these:
  - The review says `utils.py` is too large or mixes jobs but asks for no extraction of the backup code in this PR. Calling it a follow-up, or asking only for a general split of `utils.py` someday, counts here.
  - The review's fix keeps the backup code in `utils.py`, such as a section banner or a private class inside the file.
- MISSED. The review says nothing about where the backup code lives or about the size of `utils.py`.

## Comments that count neither way

- The copy only runs on the automatic startup path, not in `omnigent debug db-upgrade`, and not for Postgres or CockroachDB.
- Skipping the copy with a warning when disk space is low, whether that should fail instead, or that the free-space check ignores the WAL file.
- `O_EXCL` failing if two starts copy the same revision in the same second, or the one-second timestamp resolution.
- The retention default of 3, the env var name, or `_env_int` raising at startup on a bad value.
- Copies sitting next to the database (for example on a small Docker volume), no restore command, or missing docs.
- Sorting by name, or `iterdir` scanning the whole data directory.
- The copy delaying startup for a large database, or a request for progress logging.
- `_make_db_at_revision` duplicated from `tests/db/test_utils.py` in the new test file.
- The `except BaseException` cleanup, the local `import sqlite3`, or the wording of `_backup_hint`.
