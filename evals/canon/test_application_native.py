import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
import unittest
import uuid

if len(sys.argv) > 1 and sys.argv[1] == "config-probe":
    import importlib.util
    spec = importlib.util.spec_from_file_location("application", "/tmp/canon-application.py")
    application = importlib.util.module_from_spec(spec)
    sys.modules["application"] = application
    spec.loader.exec_module(application)
else:
    import application


def config_probe(root, output):
    home = output / "config-home"
    (home / ".codex").mkdir(parents=True)
    (root / ".codex").mkdir()
    (root / ".codex/config.toml").write_text('developer_instructions="APPLICATION_CONFIG_SENTINEL"\n')
    generated = application._native_command({"model": "unused", "effort": "high"}, root)
    settings = [generated[i + 1] for i, arg in enumerate(generated[:-1]) if arg == "-c"]
    results = {}
    for case in ("generated", "old-dotted-control"):
        overrides = settings if case == "generated" else [s for s in settings if not s.startswith("projects=")] + ["projects." + json.dumps(str(root)) + '.trust_level="trusted"']
        command = ["codex", "app-server"]
        for setting in overrides:
            command += ["-c", setting]
        env = {**os.environ, "HOME": str(home), "CODEX_HOME": str(home / ".codex")}
        with (output / (case + ".stderr")).open("w") as stderr:
            proc = subprocess.Popen(command, cwd=root / "project", env=env, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=stderr)
            def request(message):
                proc.stdin.write((json.dumps(message) + "\n").encode())
                proc.stdin.flush()
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if not select.select([proc.stdout], [], [], max(0, deadline - time.monotonic()))[0]:
                        break
                    response = json.loads(proc.stdout.readline())
                    if response.get("id") == message["id"]:
                        if "error" in response:
                            raise AssertionError(response)
                        return response["result"]
                raise AssertionError("config request timed out")
            try:
                request({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "application_config_probe", "version": "1"}, "capabilities": {"experimentalApi": True}}})
                proc.stdin.write(b'{"method":"initialized","params":{}}\n')
                proc.stdin.flush()
                results[case] = request({"id": 2, "method": "config/read", "params": {"cwd": str(root / "project"), "includeLayers": True}})
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                proc.stdin.close()
                proc.stdout.close()
    (output / "config-results.json").write_text(json.dumps(results, indent=2))
    assert results["generated"]["config"]["developer_instructions"] == "APPLICATION_CONFIG_SENTINEL", results
    assert results["old-dotted-control"]["config"].get("developer_instructions") != "APPLICATION_CONFIG_SENTINEL", results


@unittest.skipUnless(os.environ.get("CANON_APPLICATION_TEMPLATE"), "requires explicit prepared sandbox template")
class NativeDeliveryTests(unittest.TestCase):
    def test_actual_clone_setup_harvest_and_config_without_model_turns(self):
        evidence = Path(os.environ["CANON_APPLICATION_EVIDENCE"]).absolute()
        evidence.mkdir(parents=True, exist_ok=True)
        root = evidence / ("clone.with spaces-" + uuid.uuid4().hex[:8])
        staging = root / "staging"
        snapshots = {}
        inventories = {}
        for tree, location in (("project", "project"), ("skills", ".agents/skills")):
            source = root / (tree + "-source")
            source.mkdir(parents=True)
            (source / "nested").mkdir()
            (source / ".gitattributes").write_bytes(b"*.txt text eol=crlf\n*.id ident\n")
            (source / "lf.txt").write_bytes(b"alpha\nbeta\n")
            (source / "crlf.txt").write_bytes(b"one\r\ntwo\r\n")
            (source / "marker.id").write_bytes(b"$Id$\n")
            (source / "nested/.gitattributes").write_bytes(b"* text=auto eol=lf\n")
            (source / "nested/crlf.txt").write_bytes(b"nested line\r\n")
            (source / "empty/nested").mkdir(parents=True)
            (source / "empty/nested").chmod(0o770)
            (source / ".gitignore").write_text("ignored.dat\n")
            (source / "ignored.dat").write_text("snapshot file despite ignore rules\n")
            (source / ".pytest_cache").mkdir()
            (source / ".pytest_cache/.gitignore").write_text("*\n")
            (source / ".pytest_cache/result").write_text("cached result\n")
            for name, mode in (("plain", 0o644), ("execute", 0o755), ("writable", 0o664), ("nested/restricted", 0o600)):
                (source / name).write_text(tree + ":" + name)
                (source / name).chmod(mode)
            (source / "nested").chmod(0o750)
            snapshots[tree] = application.Snapshot.freeze(source, root / (tree + "-snapshot"))
            inventories[tree] = application._inventory(snapshots[tree])
            application.replay(snapshots[tree], staging / location)
        application._stage(staging)
        name = "canon-delivery-check-" + uuid.uuid4().hex[:12]
        payload = {"root": str(staging), "runtime": {"model": "unused", "effort": "high", "timeout_s": 1},
                   "prompt": "NOT RUN", "project": snapshots["project"].sha256,
                   "skills": snapshots["skills"].sha256, "project_entries": inventories["project"], "skill_entries": inventories["skills"]}
        application._write_json(root / "input.json", payload)
        try:
            application._command(["sbx", "create", "--skills", "off", "--clone", "--name", name, "-q", "-t", os.environ["CANON_APPLICATION_TEMPLATE"], "codex", staging], timeout=120)
            for source, target in ((Path(application.__file__), application.REMOTE + ".py"),
                                   (root / "input.json", application.REMOTE + ".json"),
                                   (Path(__file__), application.REMOTE + "-check.py")):
                application._command(["sbx", "cp", source, name + ":" + target])
            setup = json.loads(application._command(["sbx", "exec", name, "python3", application.REMOTE + ".py", "setup", application.REMOTE + ".json"], timeout=120).stdout)
            application._write_json(root / "setup.json", setup)
            application._command(["sbx", "exec", name, "python3", application.REMOTE + ".py", "harvest", application.REMOTE + ".json"])
            application._command(["sbx", "cp", name + ":" + application.REMOTE + ".tar", root / "harvest.tar"])
            application._unpack(root / "harvest.tar", root / "harvest")
            status = json.loads((root / "harvest/status.json").read_text())
            self.assertTrue(status["guidance_valid"])
            self.assertEqual(status["capture_sha256"], snapshots["project"].sha256)
            for tree in inventories:
                self.assertEqual([{k: v for k, v in e.items() if k != "mode"} for e in setup["clone_inventories"][tree]], [{k: v for k, v in e.items() if k != "mode"} for e in inventories[tree]])
            application._command(["sbx", "exec", name, "python3", application.REMOTE + "-check.py", "config-probe", str(staging), application.REMOTE + "-home"], timeout=60)
            application._command(["sbx", "cp", name + ":" + application.REMOTE + "-home/config-results.json", root / "config-results.json"])
        finally:
            application._command(["sbx", "rm", "--force", name])
            listing = json.loads(application._command(["sbx", "ls", "--json"]).stdout)
            application._write_json(root / "cleanup.json", listing)
            self.assertTrue(all(row["name"] != name for row in listing["sandboxes"]))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "config-probe":
        config_probe(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        unittest.main()
