"""Serve site/ on a free local port until stopped, for at most 15 minutes."""

import functools
import http.server
import os
import signal
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUN = ROOT / ".run"
LIFETIME_S = 15 * 60


def stopped(signum, frame):
    (RUN / "devserver.exit").write_text(f"signal {signum} at {time.strftime('%H:%M:%S')}\n", encoding="utf-8")
    sys.exit(0)


def main():
    RUN.mkdir(exist_ok=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "site"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    (RUN / "devserver.pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    (RUN / "devserver.port").write_text(f"{port}\n", encoding="utf-8")
    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(signum, stopped)
    threading.Timer(LIFETIME_S, server.shutdown).start()
    print(f"serving site/ at http://127.0.0.1:{port}/ (pid {os.getpid()})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
