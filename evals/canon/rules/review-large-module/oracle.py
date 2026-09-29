"""Review a file the pull request grows past about 1,000 lines, or grows further with a new
responsibility, and leave a data file alone.

accounts-login-throttle takes omnigent/server/auth.py from 906 to 1,054 lines with a failed-login
throttle. sqlite-migration-backup adds SQLite backup-file management to omnigent/db/utils.py, which
is already 1,527 lines. Each precheck needs the review to name the file or the new code in it.
agent-jsonl-log is the near-miss: hermes's pure-data defaults table and example config grow by a
logging block, and the precheck needs the review to name one of those data files."""
from shared import review_names


def check_accounts_login_throttle(answer, workspace):
    """The file pushed past 1,000 lines, or the throttle code that pushes it."""
    return review_names(answer, (r"\bauth\.py\b", r"\bLoginThrottle\w*"))


def check_sqlite_migration_backup(answer, workspace):
    """The module already past 1,000 lines, or the backup functions added to it."""
    return review_names(answer, (r"\butils\.py\b", r"\bbackup_sqlite_database\b", r"\bsqlite_database_path\b"))


def check_agent_jsonl_log(answer, workspace):
    """The data files the PR grows: the defaults table or the example config."""
    return review_names(answer, (r"config_defaults\.py", r"\bDEFAULT_CONFIG\b", r"cli-config\.yaml\.example"))


CHECKS = {
    "accounts-login-throttle": check_accounts_login_throttle,
    "agent-jsonl-log": check_agent_jsonl_log,
    "sqlite-migration-backup": check_sqlite_migration_backup,
}
