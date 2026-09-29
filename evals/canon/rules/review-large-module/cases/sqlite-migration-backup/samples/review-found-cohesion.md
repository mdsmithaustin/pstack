## Review: `sqlite-backup-before-migrate`

Nice, practical feature. Taking the copy before `_run_migrations` rather than telling people to take one after a failure is the right fix, and the online backup API is the correct tool with WAL enabled.

### Findings

1. **`warning`: the backup code belongs in its own module.** `sqlite_database_path` and `backup_sqlite_database` are file management: free space, permissions, the backup API, pruning. Nothing in them touches an engine or a session, which is what everything around them in `omnigent/db/utils.py` is about. The `db` package already gives topics their own files (`cockroachdb.py`, `compression.py`, `metrics.py`), so I'd move these into `omnigent/db/sqlite_backup.py` and call it from `_initialize_or_verify_schema`.
2. **`nit`: low-disk policy.** Skipping the copy with a warning when free space is short is reasonable, but the warning is easy to miss at startup. Consider mentioning it again in the failure message if the upgrade then fails.
3. **`nit`: timestamp resolution.** Two starts in the same second from the same revision would hit `O_EXCL`. Adding microseconds to the stamp removes the edge.
4. **Tests.** Good coverage. The retention test pins exact names, which is what a person listing the directory would see. `_make_db_at_revision` is copied from `tests/db/test_utils.py`; fine for a test.
5. **Docs.** `OMNIGENT_SQLITE_BACKUP_KEEP` should go in the configuration docs.
6. **`nit`: exception scope.** `except BaseException` around the copy is broader than it needs to be. `except (OSError, sqlite3.Error)` says what you expect, though the re-raise keeps it safe either way.
7. **`nit`: restore path.** The log line could say how to restore: stop the server and move the copy over the database.

Approve once the module move is done.
