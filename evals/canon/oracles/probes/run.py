import json
import shutil
import subprocess
import sys
from pathlib import Path

request = json.load(sys.stdin)
results = []
for index, job in enumerate(request["jobs"]):
    workdir = Path("/tmp") / f"job-{index}"
    shutil.copytree(Path("/work") / job["tree"], workdir)
    try:
        proc = subprocess.run(
            job["argv"],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=job.get("timeout", 20),
            check=False,
        )
        results.append({"rc": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr[-2000:]})
    except subprocess.TimeoutExpired:
        results.append({"rc": None, "stdout": "", "stderr": "timed out"})
    shutil.rmtree(workdir, ignore_errors=True)
json.dump(results, sys.stdout)
