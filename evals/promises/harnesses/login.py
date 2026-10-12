"""What a live wave needs from each CLI's login, shared by the adapters and live.py."""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from grade_boundary import read_file

ERROR = "ERROR"
DECIDED = ("PASS", "FAIL")
STATUS_TIMEOUT_S = 60
DEATH_WINDOW = 4000


@dataclass(frozen=True)
class Login:
    cli: str
    relogin: str
    death: re.Pattern


class LoginRequired(RuntimeError):
    def __init__(self, login, detail):
        super().__init__(f"{login.cli} login is not usable: {detail}. Run `{login.relogin}`, then start the wave again")
        self.login = login
        self.detail = detail


def check_status(login, argv, env=None):
    """Run the CLI's own login status command. It spends no model tokens."""
    try:
        done = subprocess.run([str(a) for a in argv], env=env, capture_output=True, text=True, timeout=STATUS_TIMEOUT_S,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LoginRequired(login, f"`{' '.join(map(str, argv))}` did not finish: {error!r}") from error
    if done.returncode:
        raise LoginRequired(login, f"`{' '.join(map(str, argv))}` exited {done.returncode}: {(done.stdout + done.stderr).strip()[-300:]}")
    return done.stdout


def auth_death(login, record):
    """The auth-failure text that ended a turn, or None. Only a turn that exited nonzero counts, and only its stderr tail
    and last stream line, so a reply that quotes a login message in a run that finished is not read as a dead login."""
    if not record.get("exit_code") or record.get("timed_out"):
        return None
    tail = []
    if record.get("stderr"):
        tail.append(_read(record["stderr"])[-DEATH_WINDOW:])
    if record.get("stream"):
        lines = [line for line in _read(record["stream"]).splitlines() if line.strip()]
        tail.append(lines[-1][-DEATH_WINDOW:] if lines else "")
    found = login.death.search("\n".join(tail))
    return found.group(0) if found else None


def _read(path):
    try:
        return read_file(Path(path)).decode(errors="replace")
    except FileNotFoundError:
        return ""


def death_record(login, detail):
    return {"cli": login.cli, "relogin": login.relogin, "detail": detail}


def error_verdict(case, harness, skills_at, error, graded=None):
    reason = f"{error['cli']} login died: {error['detail']}"
    promises = {}
    for pid in case["promises"]:
        result = graded[pid] if graded else {}
        gate = applicability(pid, harness)
        if gate.get("not_applicable"):
            promises[pid] = gate
        elif result.get("verdict") in DECIDED:
            promises[pid] = result
        else:
            judge = {k: result[k] for k in ("needs_judge", "excerpt") if k in result}
            promises[pid] = {"verdict": ERROR, "failures": [reason], "evidence": [], **judge}
    return {"case": case["id"], "harness": harness, "skills_at": skills_at, "error": error, "promises": promises}


def applicability(pid, harness):
    import oracles
    return oracles.check(pid, {"harness": harness}, None, None)
