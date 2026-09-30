#!/usr/bin/env python3
"""Build the dependency image a workspace case's tests run in.

  images/build.py REPO COMMIT

The image holds REPO's dependencies as its lockfiles at COMMIT pin them, and
none of its source: the build context is only the manifests and lockfiles,
read from the canon mirror. The image id lands in images.json under
REPO-<commit[:12]>, the name shared.project_test_results takes.
"""
import json
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

IMAGES = Path(__file__).resolve().parent
sys.path.insert(0, str(IMAGES.parent))
import workspace  # noqa: E402

MANIFESTS = {"pyproject.toml", "uv.lock", "uv.toml", ".python-version",
             "package.json", "package-lock.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", ".npmrc"}


def build(repo, commit):
    mirror = workspace.mirror_path(repo)
    if not workspace.has_commit(mirror, commit):
        raise workspace.WorkspaceError(f"{mirror} lacks {commit}; run `workspace.py fetch {repo} {commit}` first")
    paths = sorted(path for path in workspace.tracked_paths(mirror, commit)
                   if path.rsplit("/", 1)[-1] in MANIFESTS and "node_modules/" not in path)
    name = f"{repo}-{commit[:12]}"
    with tempfile.TemporaryDirectory() as directory:
        context = Path(directory)
        archive = context / "manifests.tar"
        archive.write_bytes(workspace.git("--git-dir", str(mirror), "archive", "--format=tar", commit, "--", *paths))
        with tarfile.open(archive) as tar:
            tar.extractall(context / "manifests", filter="data")
        archive.unlink()
        started = time.monotonic()
        subprocess.run(["docker", "build", "--progress=plain", "-t", f"canon-{repo}:{commit[:12]}",
                        "-f", str(IMAGES / repo / "Dockerfile"), str(context)], check=True, stdout=sys.stderr)
        seconds = round(time.monotonic() - started)
    image = json.loads(subprocess.run(["docker", "image", "inspect", f"canon-{repo}:{commit[:12]}"],
                                      capture_output=True, text=True, check=True).stdout)[0]
    record = IMAGES / "images.json"
    images = json.loads(record.read_text()) if record.is_file() else {}
    images[name] = {"repo": repo, "commit": commit, "id": image["Id"], "platform": f"{image['Os']}/{image['Architecture']}"}
    record.write_text(json.dumps(dict(sorted(images.items())), indent=2) + "\n")
    print(f"{name} {image['Id']} {image['Size'] // 1_000_000} MB {seconds} s")


if __name__ == "__main__":
    if len(sys.argv) != 3 or not workspace.SHA.match(sys.argv[2]) or not (IMAGES / sys.argv[1] / "Dockerfile").is_file():
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    build(sys.argv[1], sys.argv[2])
