#!/usr/bin/env python3
"""Workspace cases: the agent works inside a checkout of a real upstream repo.

A case opts in with case.json "workspace": {"repo": NAME, "commit": SHA,
"overlay": "overlay/"}. The repo comes from a local bare mirror that holds the
pinned commit at depth 1, so a run never touches the network or the user's own
clone. The harness copies only single files into its workspace (flattened into
inputs/), so the per-run entry wrapper materializes the checkout itself:

  workspace.py fetch REPO COMMIT [--from PATH]     put COMMIT into the mirror
  workspace.py wrap [--token T --discovery D] -- TARGET ARG...

`wrap` runs in the harness workspace. It checks out the commit there, copies
the overlay over it, and refuses to start the agent unless the result has the
tree the build recorded. After the agent exits it writes the diff of
everything the agent changed to a slot outside the workspace.

A review case adds case.json "review": {"patch", "title", "body_file",
"branch"}. Its checkout gets a local `main` at the pinned commit and the PR
branch, which holds pr.patch as one commit by a neutral author at a fixed
date, so every arm gets the same commit ids. The PR branch is checked out and
the PR body sits in the workspace root, untracked, under its own file name.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

REPOS = {
    "omnigent": "https://github.com/omnigent-ai/omnigent.git",
    "hermes": "https://github.com/NousResearch/hermes-agent.git",
}
DEFAULT_CACHE = Path.home() / ".cache" / "canon-screen"
TIMEOUT_S = 1800
SHA = re.compile(r"^[0-9a-f]{40}$")
REPO_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
BRANCH = re.compile(r"^[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*$")
BODY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REVIEW_KEYS = {"patch", "title", "body_file", "branch"}
BASE_BRANCH = "main"
PR_AUTHOR = {"GIT_AUTHOR_NAME": "Sam Rivera", "GIT_AUTHOR_EMAIL": "sam.rivera@example.com",
             "GIT_COMMITTER_NAME": "Sam Rivera", "GIT_COMMITTER_EMAIL": "sam.rivera@example.com"}
# Our own git calls ignore user and system config, whose LFS filters, fsmonitor,
# or diff prefixes would change what a checkout writes or a diff says.
GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}
# The wrapper exits with this code, without starting the agent, when the
# workspace cannot be built or does not match the recorded tree.
REFUSED = 97
CREDENTIAL_FILES = {".credentials.json", "auth.json"}
CREDENTIAL_TOKENS = {
    "API key": re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}"),
    "OAuth token": re.compile(rb'"(?:access|refresh)_?[Tt]oken"\s*:\s*"[^"\s]{20,}"'),
}


class WorkspaceError(Exception):
    pass


@dataclass(frozen=True)
class Spec:
    repo: str
    commit: str
    # {path: bytes} copied over the checkout; a review case's PR body is one of them.
    overlay: dict
    # A review case's {"patch": bytes, "title", "branch", "body_file"}, else None.
    review: dict = None

    @property
    def key(self):
        parts = [self.repo, self.commit, tree_digest(self.overlay)]
        if self.review:
            parts.append([hashlib.sha256(self.review["patch"]).hexdigest(), self.review["title"], self.review["branch"]])
        digest = hashlib.sha256(json.dumps(parts).encode()).hexdigest()
        return f"{self.repo}-{self.commit[:12]}-{digest[:12]}"


def tree_digest(files):
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode() + b"\0" + str(len(files[path])).encode() + b"\0" + files[path])
    return digest.hexdigest()


def read_files(root):
    """{relative path: bytes} for every regular file under root, symlinks not followed."""
    files = {}
    for directory, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            path = Path(directory, name)
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def mounted_paths(root):
    """Every file and symlink already under root, as posix paths."""
    found = []
    for directory, dirs, names in os.walk(root):
        found += [Path(directory, name).relative_to(root).as_posix() for name in names]
        found += [Path(directory, name).relative_to(root).as_posix() for name in dirs if Path(directory, name).is_symlink()]
    return sorted(found)


def parse_review(case_root, raw):
    """(review dict, {body_file: bytes}) from case.json "review"."""
    where = f"{case_root}/case.json review"
    if not isinstance(raw, dict) or set(raw) != REVIEW_KEYS:
        raise WorkspaceError(f"{where} must have exactly {sorted(REVIEW_KEYS)}, not {raw!r}")
    if not all(isinstance(raw[key], str) and raw[key].strip() for key in REVIEW_KEYS):
        raise WorkspaceError(f"{where} values must be non-empty strings")
    if not BRANCH.match(raw["branch"]) or raw["branch"] == BASE_BRANCH or ".." in raw["branch"] or raw["branch"].endswith((".lock", ".")):
        raise WorkspaceError(f"{where} branch {raw['branch']!r} must be a lowercase branch name other than {BASE_BRANCH}")
    if not BODY_NAME.match(raw["body_file"]):
        raise WorkspaceError(f"{where} body_file {raw['body_file']!r} must be a plain file name in the case directory")
    files = {}
    for key in ("patch", "body_file"):
        path = Path(case_root) / raw[key]
        if Path(case_root).resolve() not in path.resolve().parents or not path.is_file():
            raise WorkspaceError(f"{where} {key} {raw[key]!r} is not a file inside the case")
        files[key] = path.read_bytes()
    review = {"patch": files["patch"], "title": raw["title"].strip(), "branch": raw["branch"], "body_file": raw["body_file"]}
    return review, {raw["body_file"]: files["body_file"]}


def parse_spec(case_root, raw, review=None):
    if not isinstance(raw, dict) or set(raw) - {"repo", "commit", "overlay"} or not {"repo", "commit"} <= set(raw):
        raise WorkspaceError(f"{case_root}/case.json workspace must be {{\"repo\", \"commit\", \"overlay\"}}, not {raw!r}")
    if not isinstance(raw["repo"], str) or not REPO_NAME.match(raw["repo"]):
        raise WorkspaceError(f"{case_root}/case.json workspace repo must name a mirror such as {sorted(REPOS)}, not {raw['repo']!r}")
    if not isinstance(raw["commit"], str) or not SHA.match(raw["commit"]):
        raise WorkspaceError(f"{case_root}/case.json workspace commit must be a full 40-character sha")
    overlay = {}
    if raw.get("overlay"):
        root = (Path(case_root) / raw["overlay"]).resolve()
        if Path(case_root).resolve() not in root.parents or not root.is_dir():
            raise WorkspaceError(f"{case_root}/case.json workspace overlay {raw['overlay']!r} is not a directory inside the case")
        overlay = read_files(root)
    if review is None:
        return Spec(raw["repo"], raw["commit"], overlay)
    review, body = parse_review(case_root, review)
    if set(body) & set(overlay):
        raise WorkspaceError(f"{case_root}/case.json review body_file {review['body_file']!r} is also an overlay file")
    return Spec(raw["repo"], raw["commit"], {**overlay, **body}, review)


def git(*args, cwd=None, env=None):
    proc = subprocess.run(["git", *args], cwd=cwd, env={**os.environ, **GIT_ENV, **(env or {})}, capture_output=True)
    if proc.returncode != 0:
        raise WorkspaceError(f"git {' '.join(args[:2])} failed: {proc.stderr.decode(errors='replace').strip()[-400:]}")
    return proc.stdout


def cache_root():
    return Path(os.environ.get("CANON_CACHE", DEFAULT_CACHE)).expanduser().resolve()


def mirror_path(repo):
    return cache_root() / "mirrors" / f"{repo}.git"


def has_commit(mirror, commit):
    probe = subprocess.run(["git", "--git-dir", str(mirror), "cat-file", "-e", f"{commit}^{{commit}}"],
                           env={**os.environ, **GIT_ENV}, capture_output=True)
    return mirror.is_dir() and probe.returncode == 0


def fetch(repo, commit, source=None):
    """Put commit into the repo's bare mirror at depth 1, from source (a clone or
    URL) or the upstream URL. Idempotent."""
    mirror = mirror_path(repo)
    if not mirror.is_dir():
        mirror.parent.mkdir(parents=True, exist_ok=True)
        git("init", "-q", "--bare", str(mirror))
    if not has_commit(mirror, commit):
        git("--git-dir", str(mirror), "-c", "uploadpack.allowAnySHA1InWant=true",
            "fetch", "-q", "--depth", "1", str(source or REPOS[repo]), commit)
    if not has_commit(mirror, commit):
        raise WorkspaceError(f"{repo} mirror still lacks {commit} after the fetch")
    return mirror


def require_mirror(spec):
    mirror = mirror_path(spec.repo)
    if not has_commit(mirror, spec.commit):
        raise WorkspaceError(f"{mirror} lacks {spec.commit}; run `python3 evals/canon/workspace.py fetch {spec.repo} {spec.commit} --from <clone>`")
    return mirror


def tracked_paths(mirror, commit):
    listing = git("--git-dir", str(mirror), "ls-tree", "-r", "-z", "--name-only", commit).decode()
    return {path for path in listing.split("\0") if path}


@contextmanager
def staged(root, base):
    """Env for git calls that see base plus everything under root that git does
    not ignore, staged into a throwaway index so the workspace's own is untouched."""
    with tempfile.TemporaryDirectory() as directory:
        env = {"GIT_INDEX_FILE": str(Path(directory) / "index")}
        git("read-tree", base, cwd=root, env=env)
        git("add", "-A", cwd=root, env=env)
        yield env


def snapshot(root, base):
    with staged(root, base) as env:
        return git("write-tree", cwd=root, env=env).decode().strip()


def ignore_line(path):
    return "/" + re.sub(r"([*?\[\]\\!# ])", r"\\\1", path)


def exclude(root, paths):
    info = root / ".git" / "info"
    info.mkdir(parents=True, exist_ok=True)
    with (info / "exclude").open("a", encoding="utf-8") as handle:
        handle.writelines(ignore_line(path) + "\n" for path in paths)


def mount_roots(present, tracked):
    """The shallowest path of each mounted file that is not a directory the
    repo tracks: skills/ in a repo without one, skills/pstack in a repo whose
    own skills/ it joins."""
    tracked_dirs = {"/".join(path.split("/")[:depth]) for path in tracked for depth in range(1, path.count("/") + 1)}
    roots = set()
    for path in present:
        parts = path.split("/")
        roots.add(next("/".join(parts[:depth]) for depth in range(1, len(parts) + 1) if "/".join(parts[:depth]) not in tracked_dirs))
    return sorted(roots)


def commit_review(root, commit, review):
    """Put branch main at commit and the PR branch one commit above it, with
    the PR branch checked out. Returns {branch: commit id} for both."""
    stamp = int(git("show", "-s", "--format=%ct", commit, cwd=root).decode().strip()) + 3600
    env = {**PR_AUTHOR, "GIT_AUTHOR_DATE": f"@{stamp} +0000", "GIT_COMMITTER_DATE": f"@{stamp} +0000"}
    git("checkout", "-q", "-B", BASE_BRANCH, commit, cwd=root)
    git("checkout", "-q", "-b", review["branch"], cwd=root)
    with tempfile.TemporaryDirectory() as directory:
        patch = Path(directory) / "pr.patch"
        patch.write_bytes(review["patch"])
        git("apply", "--index", "--binary", "--whitespace=nowarn", str(patch), cwd=root)
    git("-c", "commit.gpgsign=false", "commit", "-q", "--no-verify", "-m", review["title"], cwd=root, env=env)
    return refs(root, review["branch"])


def refs(root, branch):
    """{branch: commit id} of main and the PR branch in root."""
    return {name: git("rev-parse", "--verify", "-q", f"refs/heads/{name}", cwd=root).decode().strip()
            for name in (BASE_BRANCH, branch)}


def head_state(root):
    """{"head_after": HEAD commit id or None, "refs_after": {local branch: commit id}}
    as the agent left them."""
    head = subprocess.run(["git", "rev-parse", "-q", "--verify", "HEAD"], cwd=root, env={**os.environ, **GIT_ENV}, capture_output=True)
    listing = git("for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads", cwd=root).decode()
    return {"head_after": head.stdout.decode().strip() or None,
            "refs_after": dict(line.split(" ", 1) for line in listing.splitlines() if line)}


def materialize(root, mirror, commit, overlay, review=None):
    """Check commit out into root beside the files already there, copy the
    overlay over it, and return the tree id of the result. The directories
    holding the files already in root (the mounted skills) are excluded from
    git's view, so nothing the agent writes there reaches the diff. A review
    checks out the PR branch that commit_review builds before the overlay."""
    root = Path(root)
    tracked = tracked_paths(mirror, commit)
    roots = mount_roots(mounted_paths(root), tracked)
    clash = sorted(path for path in tracked | set(overlay) if any(path == top or path.startswith(top + "/") for top in roots))
    if clash:
        raise WorkspaceError(f"the repo or overlay would overwrite mounted files: {clash[:5]}")
    git("init", "-q", "--template=", cwd=root)
    (root / ".git" / "objects" / "info").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "objects" / "info" / "alternates").write_text(str(Path(mirror) / "objects") + "\n")
    if (Path(mirror) / "shallow").is_file():
        shutil.copyfile(Path(mirror) / "shallow", root / ".git" / "shallow")
    git("checkout", "-q", "--detach", commit, cwd=root)
    base = commit_review(root, commit, review)[review["branch"]] if review else commit
    for path, data in overlay.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    exclude(root, roots)
    return snapshot(root, base)


def harvest(root, base):
    """Binary diff from base to the workspace as it is now: edits, deletions,
    and new files git does not ignore. Renames show as a deletion and an add."""
    with staged(root, base) as env:
        return git("-c", "core.quotePath=false", "diff", "--cached", "--binary", "--no-renames", "--no-color",
                   "--no-ext-diff", "--no-textconv", base, cwd=root, env=env)


def reference_checkout(spec):
    """(path, tree) of the pinned checkout with the overlay, built once per spec
    under the cache. Oracles apply a run's diff to it. A review spec's checkout
    is the PR branch."""
    mirror = require_mirror(spec)
    path = cache_root() / "checkouts" / spec.key
    record = path.with_name(path.name + ".tree")
    if path.is_dir() and record.is_file():
        return path, record.read_text().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{spec.key}-", dir=path.parent))
    try:
        tree = materialize(staging, mirror, spec.commit, spec.overlay, spec.review)
        if path.exists():
            shutil.rmtree(path)
        os.replace(staging, path)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    record.write_text(tree + "\n")
    return path, tree


def expose(root, discovery, tree="skills/pstack"):
    """Make the mounted skills discoverable at root/discovery. A repo without
    that directory gets one symlink to the whole tree; a repo that tracks it
    gets a copy of each skill beside its own."""
    target = root / discovery
    if not target.exists() and not target.is_symlink():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(os.path.relpath(root / tree, target.parent))
        exclude(root, [discovery])
        return
    added = []
    for skill in sorted(path for path in (root / tree).iterdir() if path.is_dir()):
        if (target / skill.name).exists():
            raise WorkspaceError(f"{discovery}/{skill.name} already exists in the repo")
        shutil.copytree(skill, target / skill.name, symlinks=True)
        added.append(f"{discovery}/{skill.name}")
    exclude(root, added)


def next_slot(root):
    root.mkdir(parents=True, exist_ok=True)
    for number in range(1, 10000):
        slot = root / f"{number:04d}"
        try:
            slot.mkdir()
            return slot
        except FileExistsError:
            continue
    raise WorkspaceError(f"{root} has no free slot")


def checkout_tokens(checkout):
    """The exact bytes of every credential-shaped match in a checkout's files,
    .git aside: upstream test fakes and doc examples an agent may quote."""
    found = set()
    for directory, names, files in os.walk(checkout):
        names[:] = [name for name in names if name != ".git"]
        for name in files:
            path = Path(directory, name)
            if path.is_file() and not path.is_symlink():
                data = path.read_bytes()
                found.update(match.group() for pattern in CREDENTIAL_TOKENS.values() for match in pattern.finditer(data))
    return found


def credential_findings(root, known=frozenset()):
    """[(path under root, what it holds)] for each file that is an agent
    credential file or holds an API key or OAuth token. A match whose bytes
    are in known does not count."""
    root = Path(root)
    findings = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.name in CREDENTIAL_FILES:
            findings.append((relative, "credential file"))
        elif path.is_file() and not path.is_symlink():
            data = path.read_bytes()
            findings += [(relative, kind) for kind, pattern in CREDENTIAL_TOKENS.items()
                         if any(match.group() not in known for match in pattern.finditer(data))]
    return findings


def disk_bytes(root):
    return sum(os.lstat(Path(directory, name)).st_size for directory, _, names in os.walk(root) for name in names)


def arm_review(arm, spec):
    """The review materialize takes, from an arm's workspace.json "review" and
    its pr.patch, or None for a case that is not a review."""
    if not spec.get("review"):
        return None
    return {**spec["review"], "patch": (Path(arm) / "pr.patch").read_bytes()}


def check_refs(root, spec):
    """Refuse a review checkout whose main or PR branch is not the commit the
    build recorded, and return the refs."""
    found = refs(root, spec["review"]["branch"])
    if found != spec["review"]["refs"]:
        raise WorkspaceError(f"review refs {found} are not the recorded {spec['review']['refs']}")
    return found


def wrap(argv, stdin=sys.stdin.buffer):
    """The entry wrapper for a workspace case. Env CANON_WORKSPACE names the
    arm's workspace dir (workspace.json, overlay/, and pr.patch for a
    review); CANON_HARVEST names the
    directory that gets one numbered slot per run."""
    split = argv.index("--")
    options, command = argv[:split], argv[split + 1:]
    token = options[options.index("--token") + 1] if "--token" in options else None
    discovery = options[options.index("--discovery") + 1] if "--discovery" in options else None
    arm = Path(os.environ["CANON_WORKSPACE"])
    spec = json.loads((arm / "workspace.json").read_text())
    slot = next_slot(Path(os.environ["CANON_HARVEST"]))
    record = {"expected_tree": spec["tree"]}

    def save():
        (slot / "workspace.json").write_text(json.dumps(record, indent=2) + "\n")

    root = Path.cwd()
    started = time.monotonic()
    review = arm_review(arm, spec)
    try:
        record["tree"] = materialize(root, Path(spec["mirror"]), spec["commit"], read_files(arm / "overlay"), review)
        if record["tree"] != spec["tree"]:
            raise WorkspaceError(f"materialized tree {record['tree']} is not the recorded {spec['tree']}")
        if review:
            record["refs"] = check_refs(root, spec)
        if discovery:
            expose(root, discovery)
    except WorkspaceError as exc:
        record["error"] = str(exc)
        save()
        print(f"workspace: {exc}", file=sys.stderr)
        return REFUSED
    record["materialize_s"] = round(time.monotonic() - started, 2)
    save()
    prompt = stdin.read()
    if token:
        prompt = token.encode() + b" " + prompt
    record["agent_rc"] = subprocess.run(command, input=prompt).returncode
    started = time.monotonic()
    try:
        diff = harvest(root, record["tree"])
        (slot / "workspace.diff").write_bytes(diff)
        record["diff_bytes"] = len(diff)
    except WorkspaceError as exc:
        record["error"] = f"harvest: {exc}"
    if review:
        record.update(head_state(root))
    record["harvest_s"] = round(time.monotonic() - started, 2)
    record["workspace_bytes"] = disk_bytes(root)
    save()
    return record["agent_rc"]


def main(argv):
    if argv[:1] == ["wrap"]:
        return wrap(argv[1:])
    if argv[:1] == ["fetch"] and len(argv) in (3, 5) and (len(argv) == 3 or argv[3] == "--from"):
        if not REPO_NAME.match(argv[1]) or not SHA.match(argv[2]) or (len(argv) == 3 and argv[1] not in REPOS):
            print(f"workspace: fetch takes a repo name, a full sha, and --from unless the repo is one of {sorted(REPOS)}", file=sys.stderr)
            return 2
        print(fetch(argv[1], argv[2], argv[4] if len(argv) == 5 else None))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except WorkspaceError as exc:
        print(f"workspace: {exc}", file=sys.stderr)
        sys.exit(1)
