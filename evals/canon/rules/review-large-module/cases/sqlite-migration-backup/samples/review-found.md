## Review: `sqlite-backup-before-migrate`

Good change, and the motivation is right: "take a backup" in the failure message was advice for after the damage. Using the online backup API rather than `shutil.copy` is the correct call with WAL on, creating the file with the source's mode before writing closes the brief world-readable window, and the stale-database test checks the copy's `alembic_version`, which is the property that matters.

### Warning: this grows a module that is already far past 1,000 lines

`omnigent/db/utils.py` is 1,527 lines on main and 1,627 after this PR, and it already mixes engine caching, Lakebase tokens, migrations, session makers, id generation, and FTS helpers. The new code is a separate job again: `sqlite_database_path` and `backup_sqlite_database` manage files on disk (free space, permissions, the backup API, pruning) and never touch an engine or a session. Adding a new responsibility to a file this size is the Large Class smell.

Please put it in its own module, for example `omnigent/db/sqlite_backup.py` next to `cockroachdb.py` and `compression.py` (Move Function), and have `_initialize_or_verify_schema` call it. `utils.py` then only gains the call and the new message.

### Smaller things

- `nit`: the copy runs only on the automatic startup path. `omnigent debug db-upgrade` would benefit from the same call.
- `nit`: `O_EXCL` fails if two starts copy the same revision in the same second. Unlikely, but the error would surprise someone. Adding microseconds to the stamp avoids it.
- The failed-upgrade test asserts the exact sentence with the path, which is the behavior an operator sees. Good.

Request changes for the module move. The rest can wait.
