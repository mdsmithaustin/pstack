## Related issue

Closes #8244

## Summary

- When the server boots against a SQLite database whose schema is behind head, it now copies the file before the automatic upgrade runs. The copy is `<db>.pre-migrate-<UTC time>-<from revision>`, next to the database, written with SQLite's online backup API so committed WAL contents are included. It gets the database file's permission bits.
- The newest 3 copies per database are kept. `OMNIGENT_SQLITE_BACKUP_KEEP` changes the count, and `0` turns the copy off. When the disk has less free space than the database, the copy is skipped with a warning instead of blocking startup.
- If the upgrade fails or stops short of head, the error now says where the copy is instead of "Take a backup of your database". That advice came too late: by the time you read it, the automatic upgrade had already run against your only copy.
- Postgres and CockroachDB are unchanged. Managed databases have their own snapshots, and the copy only applies to a local file.

The helpers are `sqlite_database_path` and `backup_sqlite_database` in `omnigent/db/utils.py`, called from `_initialize_or_verify_schema` right before `_run_migrations`.

## Test Plan

```
OMNIGENT_SKIP_WEB_UI=true uv sync --frozen --group test
.venv/bin/python -m pytest -q tests/db/test_sqlite_migration_backup.py tests/db/test_utils.py -k "backup or initialize_or_verify"
```

New tests: the copy holds the rows and the 0600 mode, only the newest copies are kept, nothing is written for in-memory, missing, Postgres, or disabled databases, a stale database is copied at its old revision before the upgrade, and a failed upgrade's message names the copy.

Manual: stamped a copy of my `~/.omnigent/omnigent.db` back to `8a4f1e9c2b07`, started `omnigent server`, and got `omnigent.db.pre-migrate-20260927T181204Z-8a4f1e9c2b07` beside it with the old schema.

## Demo

- [ ] Visual demo attached below
- [x] Non-visual evidence provided below or in Test Plan
- [ ] Not applicable — no behavioral change

## Type of change

- [ ] Bug fix
- [x] Feature
- [ ] UI / frontend change
- [ ] Refactor / chore
- [ ] Docs
- [ ] Test / CI
- [ ] Breaking change

## Test coverage

- [x] Unit tests added / updated
- [x] Integration tests added / updated
- [ ] E2E tests added / updated
- [x] Manual verification completed
- [ ] Existing tests cover this change
- [ ] Not applicable

## Coverage notes

Manual run above: a real local database stamped one revision back, then a normal server start.

## Changelog

A local SQLite database is copied aside before Omnigent upgrades its schema on startup
