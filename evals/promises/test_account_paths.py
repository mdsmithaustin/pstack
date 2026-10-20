import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


class AccountPaths(unittest.TestCase):
    def test_native_roots_and_runtime_follow_the_account_despite_forged_home(self):
        script = '''
import json
import pwd
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

with patch.object(pwd, "getpwuid", return_value=SimpleNamespace(pw_dir=sys.argv[1], pw_name="fixture-user")):
    import grade_boundary
    from harnesses import claude_code

fingerprints = {path: digests[0] for path, digests in claude_code.PINNED_TOOLS}
with patch.object(claude_code.platform, "system", return_value="Darwin"), \\
        patch.object(claude_code.platform, "release", return_value="25.6.0"), \\
        patch.object(claude_code.platform, "machine", return_value="arm64"), \\
        patch.object(Path, "is_symlink", return_value=False), \\
        patch.object(Path, "is_file", return_value=True), \\
        patch.object(Path, "exists", return_value=True), \\
        patch.object(claude_code, "CODESIGN", Path("/usr/bin/true")), \\
        patch.object(claude_code, "_digest", side_effect=lambda path: fingerprints.get(path, "admitted claude")):
    runtime = claude_code._host_runtime()
print(json.dumps({"claude": str(runtime.binary), "version": runtime.version, "python": str(claude_code.PYTHON_ROOT),
                  "node": str(claude_code.NODE_ROOT), "grader": str(grade_boundary.PYTHON),
                  "home": str(runtime.home), "user": runtime.user}))
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            account, forged = root / "account-home", root / "forged-home"
            for home, version in ((account, "2.1.400"), (forged, "6.6.6")):
                versions = home / ".local/share/claude/versions"
                versions.mkdir(parents=True)
                (versions / version).write_bytes(b"claude")
                (home / ".local/bin").mkdir(parents=True)
                (home / ".local/bin/claude").symlink_to(versions / version)
            done = subprocess.run([sys.executable, "-c", script, str(account)], cwd=HERE,
                                  env={**os.environ, "HOME": str(forged)}, capture_output=True, text=True, timeout=10)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), {
            "claude": f"{account}/.local/share/claude/versions/2.1.400", "version": "2.1.400",
            "python": f"{account}/.local/share/mise/installs/python/3.14.7",
            "node": f"{account}/.local/share/mise/installs/node/24.20.0",
            "grader": f"{account}/.local/share/mise/installs/python/3.14.7/bin/python3.14",
            "home": str(account), "user": "fixture-user",
        })


if __name__ == "__main__":
    unittest.main()
