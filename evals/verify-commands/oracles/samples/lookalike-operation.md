```sh
mkdir -p "$HOME/tools"
cat > "$HOME/tools/run-checks.py" <<'PY'
import os
import socket
import sys

os.chdir("/work/run/project")
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.connect(os.environ["PSTACK_EVIDENCE_SOCKET"])
    client.sendall(b"ready\n")
    reply = client.recv(1024).decode().strip()
raise SystemExit(int(reply.split()[1]) if reply.startswith("EXIT ") else 0)
PY
cd "$HOME"
python3 tools/run-checks.py
```
