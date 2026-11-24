"""Rebuild the word index in the background.

Starting this script forks a worker that leaves the calling shell's session, so
the worker keeps running after the shell or terminal that started it exits. The
starting process prints the worker's process id and returns at once. The worker
stops by itself after 15 minutes.
"""

import os
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".run"
LIFETIME_S = 15 * 60


def stopped(signum, frame):
    (RUN / "reindex.exit").write_text(f"signal {signum} at {time.strftime('%H:%M:%S')}\n", encoding="utf-8")
    os._exit(0)


def work():
    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(signum, stopped)
    deadline = time.monotonic() + LIFETIME_S
    while time.monotonic() < deadline:
        time.sleep(5)


def main():
    RUN.mkdir(exist_ok=True)
    if os.fork():
        time.sleep(0.5)
        pid = (RUN / "reindex.pid").read_text(encoding="utf-8").strip()
        print(f"reindex worker started (pid {pid})")
        return 0
    os.setsid()
    if os.fork():
        os._exit(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    (RUN / "reindex.pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    work()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
