#!/usr/bin/env python3
"""The half of a sandboxed run that executes inside the sandbox.

sandbox.py copies this file, workspace.py, and a payload into the sandbox and
calls one command at a time. The sandbox's clone of the staging repo is the
cwd. Only the standard library is available.

  sbx_inside.py setup MANIFEST     mount skills, register the persona, link deps, check the tree
  sbx_inside.py harvest MANIFEST OUT   write OUT.tar with workspace.diff and the agent transcripts
"""
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workspace  # noqa: E402

HOME = Path.home()


def tracked(root, commit):
    listing = workspace.git("ls-tree", "-r", "-z", "--name-only", commit, cwd=root).decode()
    return {path for path in listing.split("\0") if path}


def register_persona(root, manifest):
    """Install the named-role wrappers the way a user would, from the mounted
    tree, and return the files it wrote. Codex loads project roles only from a
    trusted project, so the sandbox's own config trusts this one."""
    script = root / manifest["discovery"] / "pstack-harness" / "scripts" / "subagents.py"
    if not manifest.get("harness") or not script.is_file():
        return []
    env = {**os.environ, "PSTACK_SKILLS_ROOT": str(root / manifest["discovery"])}
    proc = subprocess.run([sys.executable, str(script), "install", "--harness", manifest["harness"], "--project", str(root)],
                          env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise workspace.WorkspaceError(f"persona install failed: {proc.stdout[-400:]} {proc.stderr[-400:]}")
    written = [Path(role["path"]).relative_to(root).as_posix() for role in json.loads(proc.stdout)["roles"]]
    if manifest["harness"] == "codex":
        config = HOME / ".codex" / "config.toml"
        with config.open("a", encoding="utf-8") as handle:
            handle.write(f'\n[projects."{root}"]\ntrust_level = "trusted"\n')
    return written


def link_deps(root, manifest):
    """Point the project at the venv the template baked, then let uv reinstall
    the project's own editable packages from this checkout, offline."""
    deps = manifest.get("deps")
    if not deps:
        return None
    env = {**os.environ, **deps["env"]}
    started = time.monotonic()
    venv = root / ".venv"
    if not venv.exists() and not venv.is_symlink():
        venv.symlink_to(deps["env"]["UV_PROJECT_ENVIRONMENT"])
        workspace.exclude(root, [".venv"])
    proc = subprocess.run(["uv", "sync", *deps["sync"]], cwd=root, env=env, capture_output=True, text=True)
    return {"sync_rc": proc.returncode, "sync_s": round(time.monotonic() - started, 2), "sync_tail": proc.stderr[-600:]}


def setup(manifest_path):
    manifest = json.loads(Path(manifest_path).read_text())
    payload = Path(manifest_path).parent
    root = Path(manifest["root"])
    record = {}
    head = workspace.git("rev-parse", "HEAD", cwd=root).decode().strip()
    if head != manifest["commit"]:
        raise workspace.WorkspaceError(f"the clone is at {head}, not {manifest['commit']}")
    shutil.copytree(payload / "skills", root / "skills", symlinks=True, dirs_exist_ok=True)
    mounted = sorted(path.relative_to(root).as_posix() for path in (root / "skills").rglob("*") if path.is_file())
    workspace.exclude(root, workspace.mount_roots(mounted, tracked(root, head)))
    overlay = workspace.read_files(payload / "overlay")
    for path, data in overlay.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(data)
    if manifest.get("discovery"):
        workspace.expose(root, manifest["discovery"], manifest["tree"])
        record["persona"] = register_persona(root, manifest)
        workspace.exclude(root, record["persona"])
    record["deps"] = link_deps(root, manifest)
    record["tree"] = workspace.snapshot(root, head)
    if record["tree"] != manifest["expected_tree"]:
        raise workspace.WorkspaceError(f"sandbox tree {record['tree']} is not the recorded {manifest['expected_tree']}")
    return record


def harvest(manifest_path, out):
    manifest = json.loads(Path(manifest_path).read_text())
    root, out = Path(manifest["root"]), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    record = {}
    try:
        diff = workspace.harvest(root, manifest["expected_tree"])
        (out / "workspace.diff").write_bytes(diff)
        record["diff_bytes"] = len(diff)
    except workspace.WorkspaceError as exc:
        record["error"] = f"harvest: {exc}"
    record["workspace_bytes"] = workspace.disk_bytes(root)
    source, destination = HOME / manifest["transcripts"]["from"], out / "transcripts" / manifest["transcripts"]["to"]
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=True, ignore=shutil.ignore_patterns("lost+found"))
    (out / "inside.json").write_text(json.dumps(record, indent=2) + "\n")
    with tarfile.open(f"{out}.tar", "w") as archive:
        archive.add(out, arcname=".")
    return record


def capture(port, out):
    """Answer every request with HTTP 400 after appending its body to out, so
    an agent pointed here shows the tool list it would send, at no model cost."""
    import http.server

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("content-length") or 0))
            with open(out, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"path": self.path, "body": body.decode(errors="replace")}) + "\n")
            reply = json.dumps({"error": {"message": "capture", "type": "invalid_request_error"}}).encode()
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        do_GET = do_POST

        def log_message(self, *args):
            pass

    http.server.ThreadingHTTPServer(("127.0.0.1", int(port)), Handler).serve_forever()


def main(argv):
    if argv[:1] == ["capture"] and len(argv) == 3:
        capture(argv[1], argv[2])
    try:
        if argv[:1] == ["setup"] and len(argv) == 2:
            print(json.dumps(setup(argv[1])))
            return 0
        if argv[:1] == ["harvest"] and len(argv) == 3:
            print(json.dumps(harvest(argv[1], argv[2])))
            return 0
    except workspace.WorkspaceError as exc:
        print(json.dumps({"error": str(exc)}))
        return workspace.REFUSED
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
