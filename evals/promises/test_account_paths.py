import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


class AccountPaths(unittest.TestCase):
    def test_native_roots_and_runtime_follow_the_account_despite_forged_home(self):
        script = '''
import json
import pwd
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

with patch.object(pwd, "getpwuid", return_value=SimpleNamespace(pw_dir="/fixture/account-home", pw_name="fixture-user")):
    import grade_boundary
    from harnesses import claude_code

fingerprints = {path: digests[0] for path, digests in claude_code.PINNED_TOOLS}
fingerprints[claude_code.CLAUDE_BINARY] = claude_code.CLAUDE_SHA256
with patch.object(claude_code.platform, "system", return_value="Darwin"), \\
        patch.object(claude_code.platform, "release", return_value="25.6.0"), \\
        patch.object(claude_code.platform, "machine", return_value="arm64"), \\
        patch.object(Path, "is_symlink", return_value=False), \\
        patch.object(Path, "is_file", return_value=True), \\
        patch.object(Path, "exists", return_value=True), \\
        patch.object(claude_code, "_digest", side_effect=fingerprints.__getitem__):
    runtime = claude_code._host_runtime()
print(json.dumps({"claude": str(runtime.binary), "python": str(claude_code.PYTHON_ROOT),
                  "node": str(claude_code.NODE_ROOT), "grader": str(grade_boundary.PYTHON),
                  "home": str(runtime.home), "user": runtime.user}))
'''
        done = subprocess.run([sys.executable, "-c", script], cwd=HERE,
                              env={**os.environ, "HOME": "/fixture/forged-home"},
                              capture_output=True, text=True, timeout=10)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), {
            "claude": "/fixture/account-home/.local/share/claude/versions/2.1.295",
            "python": "/fixture/account-home/.local/share/mise/installs/python/3.14.7",
            "node": "/fixture/account-home/.local/share/mise/installs/node/24.20.0",
            "grader": "/fixture/account-home/.local/share/mise/installs/python/3.14.7/bin/python3.14",
            "home": "/fixture/account-home", "user": "fixture-user",
        })


if __name__ == "__main__":
    unittest.main()
