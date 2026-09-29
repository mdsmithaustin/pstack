## Review: `sqlite-backup-before-migrate`

Good change. Taking the copy before `_run_migrations`, instead of telling people to take one after the upgrade has already failed, is the right order, and SQLite's online backup API is the correct tool with WAL on. The stale-database test checks the copy's `alembic_version`, which is the property that matters.

### Findings

1. **`nit`: `omnigent/db/utils.py` keeps growing.** It is 1,527 lines on main and 1,627 after this, and it already mixes engine caching, Lakebase tokens, migrations, session makers, and FTS helpers. The backup helpers add one more job. Not something to hold this PR for; a split of `utils.py` into topic modules would be a good follow-up for whoever touches it next.
2. **`nit`: low-disk policy.** Skipping the copy with a warning when free space is short is reasonable, but the warning is easy to miss at startup. Repeat it in the failure message if the upgrade then fails.
3. **`nit`: timestamp resolution.** Two starts in the same second from the same revision would hit `O_EXCL`. Microseconds in the stamp remove the edge.
4. **Docs.** `OMNIGENT_SQLITE_BACKUP_KEEP` should go in the configuration docs.
5. **Scope.** The copy only runs on the automatic startup path. `omnigent debug db-upgrade` still upgrades without one; worth a line in the PR body so nobody assumes otherwise.
6. **Tests.** Good coverage, and the retention test pins the names a person listing the directory would see. `_make_db_at_revision` is copied from `tests/db/test_utils.py`; fine for a test.

Approve.
