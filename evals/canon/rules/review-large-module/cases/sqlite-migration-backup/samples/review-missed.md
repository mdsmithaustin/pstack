## Review: `sqlite-backup-before-migrate`

Reviewed the change to `_initialize_or_verify_schema` and the new tests. This is a sensible safety net for local installs.

### Correctness

- The copy runs only in the behind-head branch, after `_verify_db_revision_is_supported`, so a database from a newer build is never copied or touched. Correct.
- A fresh database (`current is None`) gets no copy, which is right: there is nothing to lose.
- The online backup API includes committed WAL pages, so the copy is consistent even though the engine already has pooled connections open.
- A partial copy is removed if the backup raises, so a full disk doesn't leave a truncated file that looks like a good backup.

### Suggestions

- `warning`: the copy runs only on the startup path. `omnigent debug db-upgrade` is exactly where someone retries by hand, and it should take a copy too.
- `nit`: the free-space check compares against the main file only. With a large `-wal` file the copy can be bigger than `st_size`. Adding the WAL size would make the check honest.
- `nit`: `iterdir()` scans the whole data directory to prune. Fine for `~/.omnigent`, but a glob on the prefix would be cheaper.
- `nit`: a restore hint in the log line (stop the server, move the copy over the database) would save someone a search.

### Tests

The stale-database test checks that the copy is at the old revision while the live database reaches head. That's the contract. Approve.
