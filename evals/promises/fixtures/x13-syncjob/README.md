# sync jobs

Each file in `jobs/` configures one sync job. `run_jobs.py` loads every config and prints the sync it would run.
A config the loader rejects is skipped with its error.

    python3 run_jobs.py

The config format is in `docs/sync-job-spec.md`.

Tests: `python3 -m unittest discover -s tests`
