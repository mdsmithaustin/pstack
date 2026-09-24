#!/usr/bin/env python3
"""Paired screen of one-rule amendments to existing pstack skills.

Each rule in rules/<id>/ is a one-hunk unified diff against skills/ that adds
or replaces one passage in one file. For each case of each rule this script
builds two arms from the working tree:

  current  the git-tracked skill files as they are in skills/
  amended  the same files with rule.patch applied

and refuses the build unless the only difference is that one contiguous change.
Both arms are ordinary with_skill manifests with the same case, so the harness
gives both the same instruction and mounts the skill under the same name.

A rule's cases are positive (the rule should change the answer) or near-miss
(the rule must not change it). A rule separates only when every positive case
separates and no near-miss case reverses or goes ungraded.

--entry skill (default) mounts only the skill that owns the patched file.
--entry poteto-mode mounts every tracked skill under skills/pstack, links it
where the agent discovers project skills, and starts the prompt with the
agent's explicit invocation, as a user of /poteto-mode would.

A rule whose rule.json names companions gets those skill directories copied
unchanged from $CANON_COMPANIONS_ROOT (default ~/.agents/skills) into both
arms beside pstack. The one-change check never sees them.

A case whose case.json names a workspace runs inside a checkout of a real repo
at a pinned commit (see workspace.py) instead of receiving project files in the
prompt. Its oracle grades the diff the agent left on that checkout.

  screen.py plan [--runs-root DIR ...]                 list rules, cases, and past runs
  screen.py build --out DIR [--entry E] [RULE ...]     write both arms of every case
  screen.py audit [--entry E] [RULE ...]               model-free: build, validate, audit, prepare
  screen.py run --agent claude|codex --out DIR [--entry E] [RULE ...]   paid: answer, grade, compare
  screen.py compare --out DIR                          print paired verdicts with exposure
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

CANON = Path(__file__).resolve().parent
sys.path.insert(0, str(CANON))
import workspace  # noqa: E402

REPO = CANON.parents[1]
RULES = Path(os.environ.get("CANON_RULES", CANON / "rules")).resolve()
ARMS = ("current", "amended")
DEFAULT_MODELS = {"claude": "sonnet", "codex": "gpt-6-sol"}
MANIFEST = "shared-benchmark.json"
ENTRIES = ("skill", "poteto-mode")
ENTRY_SKILL = "poteto-mode"
ENTRY_TREE = "pstack"
ENTRY_TIMEOUT_S = 900
DEFAULT_RUNS_ROOT = Path("/private/tmp/canon-entry")
# Skills a user installs beside pstack. A rule that routes to one names it in
# rule.json "companions", and both arms mount the same copy next to pstack.
DEFAULT_COMPANIONS_ROOT = Path.home() / ".agents" / "skills"
COMPANION_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# How each agent is invoked explicitly, and where it discovers project skills.
# Codex docs: "$skill" works even when agents/openai.yaml disables implicit use.
ENTRY_INVOCATION = {"claude": ("/poteto-mode", ".claude/skills"), "codex": ("$poteto-mode", ".agents/skills")}
READ_EVENTS = {"file_read", "skill_load", "command", "tool_call"}
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,(\d+))? @@")
# The harness names a near-miss case "adversarial"; a regression guard, not a capability.
CASE_KINDS = {"positive": ("positive", "capability"), "near-miss": ("adversarial", "regression")}
# audit-manifest blocks any manifest without a near-miss case. Each manifest holds
# one case, so a positive case's manifest accepts that one blocker and no other.
ACCEPTED_BLOCKER = "no adversarial cases"
LEAK = re.compile(r"\b(evals?|evaluation|judge|experiment|rubric|score|compare|benchmark|candidate|arena)\b", re.IGNORECASE)
# Runs made before rules had cases name no case. These are the cases they ran.
LEGACY_CASES = {
    "notation-not-runtime": "checkout-rules",
    "observe-through-interface": "register-email",
    "translate-foreign-model": "paylane-webhooks",
    "preparatory-refactor": "csv-export",
    "fork-shared-helper": "payroll-overtime",
}


class ScreenError(Exception):
    pass


@dataclass(frozen=True)
class Case:
    rule: str
    id: str
    kind: str
    root: Path
    spec: dict

    @property
    def workspace(self):
        return self.spec.get("workspace")


@dataclass(frozen=True)
class Rule:
    id: str
    source: str
    patch: str
    target: str
    cases: tuple
    companions: tuple = ()

    @property
    def skill(self):
        return self.target.split("/", 1)[0]


@dataclass(frozen=True)
class Change:
    target: str
    removed: str
    inserted: str

    @property
    def kind(self):
        return "replace" if self.removed else "insert"


def skill_ci():
    return Path(os.environ.get("SKILL_CI", REPO.parent / "skill-ci")).resolve()


def harness(*arguments, env=None):
    command = ["uv", "run", "--no-project", "python", str(skill_ci() / "tools" / "run_runner.py"), "skill-benchmark", *map(str, arguments)]
    print("+", " ".join(command[4:]), flush=True)
    subprocess.run(command, check=True, env=env)


def oracle_checks(rule_id):
    spec = importlib.util.spec_from_file_location("canon_check", CANON / "oracles" / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RULES = RULES
    return module.load_oracle(rule_id)


def load_case(rule_id, root):
    spec_path = root / "case.json"
    spec = json.loads(spec_path.read_text()) if spec_path.is_file() else {}
    # A workspace case works in a real checkout, so it has no project/ and its
    # timeout defaults to workspace.TIMEOUT_S.
    in_workspace = "workspace" in spec
    for required in (spec_path, root / "prompt.md", *(() if in_workspace else (root / "project",))):
        if not required.exists():
            raise ScreenError(f"case {rule_id}/{root.name} has no {required.name}")
    if in_workspace and (root / "project").exists():
        raise ScreenError(f"case {rule_id}/{root.name} names a workspace, so it must not have project/")
    missing = {"kind", "domain", "expected_behavior", *(() if in_workspace else ("timeout_s",))} - set(spec)
    if missing:
        raise ScreenError(f"{spec_path} lacks {sorted(missing)}")
    if in_workspace:
        workspace.parse_spec(root, spec["workspace"])
    if spec["kind"] not in CASE_KINDS:
        raise ScreenError(f"{spec_path} kind must be one of {sorted(CASE_KINDS)}, not {spec['kind']!r}")
    if LEAK.search(root.name):
        raise ScreenError(f"case id {root.name!r} carries meta vocabulary; pick a project-shaped name")
    return Case(rule_id, root.name, spec["kind"], root, spec)


def load_rule(rule_id):
    root = RULES / rule_id
    for required in ("rule.json", "oracle.py", "cases"):
        if not (root / required).exists():
            raise ScreenError(f"rule {rule_id} has no {required}")
    patch = (root / "rule.patch").read_text()
    cases = tuple(load_case(rule_id, path) for path in sorted((root / "cases").iterdir()) if path.is_dir())
    if not any(case.kind == "positive" for case in cases):
        raise ScreenError(f"rule {rule_id} has no positive case")
    checks = set(oracle_checks(rule_id))
    if checks != {case.id for case in cases}:
        raise ScreenError(f"rules/{rule_id}/oracle.py CHECKS covers {sorted(checks)}, cases are {[case.id for case in cases]}")
    spec = json.loads((root / "rule.json").read_text())
    companions = spec.get("companions", [])
    if not isinstance(companions, list) or not all(isinstance(name, str) and COMPANION_NAME.match(name) for name in companions):
        raise ScreenError(f"rules/{rule_id}/rule.json companions must be a list of skill directory names, not {companions!r}")
    return Rule(rule_id, spec["source"], patch, parse_patch(patch)[0], cases, tuple(companions))


def load_rules(requested=()):
    known = sorted(path.name for path in RULES.iterdir() if (path / "rule.patch").is_file())
    unknown = sorted(set(requested) - set(known))
    if unknown:
        raise ScreenError(f"unknown rule(s): {', '.join(unknown)}; known: {', '.join(known)}")
    return [load_rule(rule_id) for rule_id in (requested or known)]


def tracked(scope):
    listing = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "--", scope],
        capture_output=True, check=True,
    ).stdout.decode()
    paths = [path for path in listing.split("\0") if path]
    if not paths:
        raise ScreenError(f"{scope} has no tracked files")
    return {path.removeprefix("skills/"): (REPO / path).read_bytes() for path in paths}


def companions_root():
    return Path(os.environ.get("CANON_COMPANIONS_ROOT", DEFAULT_COMPANIONS_ROOT)).expanduser().resolve()


def read_tree(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def tree_hash(files):
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode() + b"\0" + str(len(files[path])).encode() + b"\0" + files[path])
    return digest.hexdigest()


def companion_trees(rule, mounted):
    """{name: {path: bytes}} for each companion skill the rule routes to, read
    as-is from the companion root. A name that is also a skill in the mounted
    tree is refused, because the copy would shadow or merge into it."""
    root = companions_root()
    taken = {path.split("/", 1)[0] for path in mounted}
    trees = {}
    for name in rule.companions:
        if name in taken:
            raise ScreenError(f"companion {name} collides with a skill in the mounted tree")
        if not (root / name / "SKILL.md").is_file():
            raise ScreenError(f"companion {name} has no SKILL.md under {root}; set CANON_COMPANIONS_ROOT")
        trees[name] = read_tree(root / name)
    return trees


def parse_patch(patch):
    """Return (path, start line, hunk lines) for a patch of one hunk in one file
    whose added and removed lines form one unbroken run."""
    lines = patch.splitlines(keepends=True)
    targets = [line[len("+++ b/"):].rstrip("\n") for line in lines if line.startswith("+++ b/")]
    if len(targets) != 1:
        raise ScreenError(f"rule.patch must change exactly one file, it names {len(targets)}")
    heads = [index for index, line in enumerate(lines) if line.startswith("@@")]
    if len(heads) != 1:
        raise ScreenError(f"rule.patch must be exactly one hunk, it has {len(heads)}")
    head = HUNK.match(lines[heads[0]])
    old_left, new_left = (int(count) if count is not None else 1 for count in head.group(2, 3))
    body = []
    for line in lines[heads[0] + 1:]:
        if old_left <= 0 and new_left <= 0:
            break
        if line == "\n":
            line = " \n"
        if line[:1] not in (" ", "-", "+"):
            raise ScreenError(f"rule.patch hunk ends early; its header expects {old_left} more old and {new_left} more new line(s)")
        body.append((line[0], line[1:]))
        old_left -= line[0] in " -"
        new_left -= line[0] in " +"
    if old_left > 0 or new_left > 0:
        raise ScreenError(f"rule.patch hunk ends early; its header expects {old_left} more old and {new_left} more new line(s)")
    changed = [index for index, (tag, _) in enumerate(body) if tag in "+-"]
    if not changed:
        raise ScreenError("rule.patch changes nothing")
    if changed[-1] - changed[0] + 1 != len(changed):
        raise ScreenError("rule.patch hunk has unchanged lines between its edits; make it one contiguous change")
    return targets[0], int(head.group(1)) - 1, body


def apply_patch(tree, patch):
    path, start, body = parse_patch(patch)
    if path not in tree:
        raise ScreenError(f"patch targets {path}, which is not a tracked file in the mounted tree")
    source = tree[path].decode().splitlines(keepends=True)
    result, cursor = source[:start], start
    for tag, text in body:
        if tag in " -":
            if cursor >= len(source) or source[cursor] != text:
                raise ScreenError(f"{path}:{cursor + 1} no longer matches rule.patch; skills/ changed under the rule")
            cursor += 1
        if tag in " +":
            result.append(text)
    return {**tree, path: "".join(result + source[cursor:]).encode()}


def single_change(current, amended):
    """The one contiguous change between two trees, trimmed to the characters
    that differ. Refuses edits in two files or two places in one file."""
    changed = [path for path in current if current[path] != amended[path]]
    if len(changed) != 1:
        raise ScreenError(f"rule.patch must change exactly one file in the tree, changed {changed}")
    before = current[changed[0]].decode().splitlines(keepends=True)
    after = amended[changed[0]].decode().splitlines(keepends=True)
    edits = [op for op in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes() if op[0] != "equal"]
    if len(edits) != 1:
        raise ScreenError(f"rule.patch edits {changed[0]} beyond one contiguous change; a line that is the same in the removed and added text splits the edit, so leave it out of the hunk's -/+ lines")
    _, i1, i2, j1, j2 = edits[0]
    removed, inserted = "".join(before[i1:i2]), "".join(after[j1:j2])
    prefix = len(os.path.commonprefix([removed, inserted]))
    suffix = len(os.path.commonprefix([removed[prefix:][::-1], inserted[prefix:][::-1]]))
    return Change(changed[0], removed[prefix:len(removed) - suffix], inserted[prefix:len(inserted) - suffix])


def rule_change(rule, tree):
    return single_change(tree, apply_patch(tree, rule.patch))


def frontmatter_description(skill_md):
    match = re.search(r"^description:\s*(.+)$", skill_md.split("\n---", 1)[0], re.MULTILINE)
    value = match.group(1).strip()
    return json.loads(value) if value.startswith('"') else value


def harness_version():
    lock = (skill_ci() / "runner.lock").read_text().strip().splitlines()[-1]
    return "git+" + lock.rsplit("@", 1)[1]


def render_prompt(case):
    prompt = (case.root / "prompt.md").read_text()
    if case.workspace:
        if "{project}" in prompt:
            raise ScreenError(f"{case.rule}/{case.id} works in a checkout; its prompt must not ask for {{project}}")
        overlay = workspace.parse_spec(case.root, case.workspace).overlay
        seeded = "\n".join(f"{path}\n{data.decode(errors='replace')}" for path, data in overlay.items())
    else:
        project_root = case.root / "project"
        listing = "\n\n".join(
            f'<file path="{path.relative_to(project_root).as_posix()}">\n{path.read_text()}</file>'
            for path in sorted(project_root.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts
        )
        prompt, seeded = prompt.replace("{project}", listing), ""
    prompt = prompt.strip()
    leaked = sorted({match.group(0).lower() for match in LEAK.finditer(prompt + "\n" + seeded)})
    if leaked:
        raise ScreenError(f"{case.rule}/{case.id} prompt or overlay carries meta vocabulary the answering agent would see: {leaked}")
    return prompt


def manifest(rule, case, prompt, skill, description, skill_paths, entry):
    kind, intent = CASE_KINDS[case.kind]
    return {
        "version": 1,
        "skill_name": skill,
        "skill_description": description,
        "harness": {
            "name": "skill-eval-harness",
            "url": "https://github.com/mdsmithaustin/skill-eval-harness",
            "version": harness_version(),
        },
        "skill_paths": skill_paths,
        "variants": ["with_skill", "without_skill"],
        "split_policy": {
            "tune": "One public case per manifest. Only the with_skill rows run; the paired arm is a second manifest.",
            "holdback": "None. A screen is a directional read, not promotion evidence.",
        },
        "cases": [
            {
                "id": case.id,
                "split": "tune",
                "kind": kind,
                "eval_intent": intent,
                "domain": case.spec["domain"],
                "difficulty": "core",
                "trigger_type": "explicit",
                "success_goals": ["outcome"],
                "prompt": prompt,
                "expected_behavior": case.spec["expected_behavior"],
                "assertions": [
                    {
                        "name": "rule-behavior",
                        "type": "script",
                        "command": ["python3", "oracles/check.py", rule.id, case.id, "{output_dir}"],
                        "severity": "gate",
                        "oracle": "strong",
                        "timeout_s": 240,
                    }
                ],
                "tags": [f"source:{rule.source}", f"skill:{skill}", f"entry:{entry}", f"case-kind:{case.kind}"],
            }
        ],
    }


def copy_grader(rule, case, root, checkout=None):
    """Give the arm the grader files and nothing that holds an answer. A
    workspace case gets the path of its pinned checkout instead of project/."""
    shutil.copytree(CANON / "oracles", root / "oracles", ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))
    rule_root = root / "rules" / rule.id
    rule_root.mkdir(parents=True)
    shutil.copyfile(RULES / rule.id / "oracle.py", rule_root / "oracle.py")
    if checkout is None:
        shutil.copytree(case.root / "project", rule_root / "cases" / case.id / "project", ignore=shutil.ignore_patterns("__pycache__"))
        return
    (rule_root / "cases" / case.id).mkdir(parents=True)
    (rule_root / "cases" / case.id / "workspace.json").write_text(json.dumps({"checkout": str(checkout[0]), "tree": checkout[1]}) + "\n")


def mount_clashes(tracked, rule, entry, skills):
    """Paths the repo tracks where the mounted skills will go: the skill root,
    and, under the poteto-mode entry, each skill's copy in a discovery
    directory the repo already has (workspace.expose)."""
    def taken(prefix):
        return prefix in tracked or any(path.startswith(prefix + "/") for path in tracked)

    if entry == "skill":
        return [prefix for prefix in (f"skills/{name}" for name in (rule.skill, *rule.companions)) if taken(prefix)]
    clashes = [f"skills/{ENTRY_TREE}"] if taken(f"skills/{ENTRY_TREE}") else []
    names = sorted({path.split("/", 1)[0] for path in skills} | set(rule.companions))
    for _, discovery in ENTRY_INVOCATION.values():
        if taken(discovery):
            clashes += [discovery] if discovery in tracked else [f"{discovery}/{name}" for name in names if taken(f"{discovery}/{name}")]
    return clashes


def prepare_workspace(rule, case, entry, skills):
    """(spec, (checkout, tree)) for a workspace case, refusing a repo that
    tracks a path the mounted skills take."""
    spec = workspace.parse_spec(case.root, case.workspace)
    clashes = mount_clashes(workspace.tracked_paths(workspace.require_mirror(spec), spec.commit), rule, entry, skills)
    if clashes:
        raise ScreenError(f"{rule.id}/{case.id}: {spec.repo}@{spec.commit[:12]} tracks paths the mounted skills take: {clashes}")
    return spec, workspace.reference_checkout(spec)


def write_arm_workspace(root, spec, tree):
    """The arm's copy of what the entry wrapper materializes, hashed as read back."""
    arm = root / "workspace"
    (arm / "overlay").mkdir(parents=True)
    for path, data in spec.overlay.items():
        (arm / "overlay" / path).parent.mkdir(parents=True, exist_ok=True)
        (arm / "overlay" / path).write_bytes(data)
    record = {"repo": spec.repo, "commit": spec.commit, "mirror": str(workspace.mirror_path(spec.repo)), "tree": tree}
    (arm / "workspace.json").write_text(json.dumps(record, indent=2) + "\n")
    return tree_hash(read_tree(arm))


def workspace_record(spec, checkout, arm_hashes):
    """Refuse the build unless every arm holds the same workspace input."""
    if len(set(arm_hashes.values())) != 1:
        raise ScreenError(f"arms hold different workspace inputs: {arm_hashes}")
    return {"repo": spec.repo, "commit": spec.commit, "tree": checkout[1], "checkout": str(checkout[0]), "arms": arm_hashes}


def build(out, rules, entry="skill"):
    built = {}
    for rule in rules:
        if entry == "skill":
            skill, tree_dir, current = rule.skill, "skills", tracked(f"skills/{rule.skill}")
            skill_paths = [f"skills/{skill}/SKILL.md"]
        else:
            skill, tree_dir, current = ENTRY_SKILL, ENTRY_TREE, tracked("skills")
            skill_paths = [ENTRY_TREE]
        amended = apply_patch(current, rule.patch)
        change = single_change(current, amended)
        description = frontmatter_description(current[f"{skill}/SKILL.md"].decode())
        companions = companion_trees(rule, current)
        if entry == "skill":
            skill_paths += [f"skills/{name}/SKILL.md" for name in companions]
        cases, arm_hashes = {}, {}
        for case in rule.cases:
            prompt = render_prompt(case)
            spec, checkout, workspace_hashes = None, None, {}
            if case.workspace:
                spec, checkout = prepare_workspace(rule, case, entry, current)
            for arm, tree in zip(ARMS, (current, amended)):
                root = out / "arms" / rule.id / case.id / arm
                if root.exists():
                    shutil.rmtree(root)
                for path, data in tree.items():
                    destination = root / tree_dir / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(data)
                for name, files in companions.items():
                    for path, data in files.items():
                        destination = root / tree_dir / name / path
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(data)
                    arm_hashes.setdefault(name, {})[f"{case.id}/{arm}"] = tree_hash(read_tree(root / tree_dir / name))
                copy_grader(rule, case, root, checkout)
                if spec is not None:
                    workspace_hashes[f"{case.id}/{arm}"] = write_arm_workspace(root, spec, checkout[1])
                (root / MANIFEST).write_text(json.dumps(manifest(rule, case, prompt, skill, description, skill_paths, entry), indent=2) + "\n")
            if spec is None:
                cases[case.id] = {"kind": case.kind, "timeout_s": ENTRY_TIMEOUT_S if entry == ENTRY_SKILL else case.spec["timeout_s"]}
            else:
                cases[case.id] = {"kind": case.kind, "timeout_s": case.spec.get("timeout_s", workspace.TIMEOUT_S),
                                  "workspace": workspace_record(spec, checkout, workspace_hashes)}
        built[rule.id] = {"entry": entry, "tree_dir": tree_dir, "target": change.target, "patch_kind": change.kind,
                          "removed": change.removed, "inserted": change.inserted, "cases": cases}
        if companions:
            built[rule.id]["companions"] = companion_record(companions, arm_hashes)
        (out / "arms" / rule.id / "build.json").write_text(json.dumps(built[rule.id], indent=2) + "\n")
        print(f"{rule.id}: {entry} entry, {len(current)} tracked files, skills/{change.target} {change.kind}, cases {', '.join(cases)}")
        for name, record in built[rule.id].get("companions", {}).get("trees", {}).items():
            print(f"  companion {name}: {record['files']} file(s), sha256 {record['sha256'][:12]} in every arm")
        if change.removed:
            print("  - " + change.removed.strip().replace("\n", "\n    "))
        print("  + " + change.inserted.strip().replace("\n", "\n    "))
    return built


def companion_record(companions, arm_hashes):
    """Hash each companion as read back from every arm, and refuse the build
    unless every arm holds the same bytes as the companion root."""
    trees = {}
    for name, files in companions.items():
        expected = tree_hash(files)
        differing = sorted(arm for arm, digest in arm_hashes[name].items() if digest != expected)
        if differing:
            raise ScreenError(f"companion {name} differs from its source in {differing}")
        trees[name] = {"files": len(files), "sha256": expected, "arms": arm_hashes[name]}
    return {"root": str(companions_root()), "trees": trees}


def check_manifest(root, kind):
    manifest_path = root / MANIFEST
    harness("validate", "--strict-leakage", manifest_path)
    harness("audit-manifest", "--strict-judge", "--out", root / "audit.json", manifest_path)
    blockers = json.loads((root / "audit.json").read_text())["readiness"]["blockers"]
    accepted = ACCEPTED_BLOCKER if kind == "positive" else None
    remaining = [blocker for blocker in blockers if not (accepted and blocker.startswith(accepted))]
    if remaining:
        raise ScreenError(f"{manifest_path} readiness blockers: {remaining}")
    if len(remaining) < len(blockers):
        print(f"accepted readiness blocker for a one-case manifest: {ACCEPTED_BLOCKER}")


def with_skill_rows(tasks, destination):
    rows = [line for line in tasks.read_text().splitlines() if json.loads(line).get("variant") == "with_skill"]
    if not rows:
        raise ScreenError(f"{tasks} has no with_skill rows")
    destination.write_text("\n".join(rows) + "\n")
    return len(rows)


def audit(rules, entry="skill"):
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory)
        build(out, rules, entry)
        for rule in rules:
            for case in rule.cases:
                for arm in ARMS:
                    root = out / "arms" / rule.id / case.id / arm
                    check_manifest(root, case.kind)
                    harness("prepare", root / MANIFEST, "--split", "tune", "--runs-per-variant", "1", "--out", root / "tasks-all.jsonl")
                    count = with_skill_rows(root / "tasks-all.jsonl", root / "tasks.jsonl")
                    print(f"OK {rule.id}/{case.id}/{arm}: {count} with_skill row(s)")


def agent_env(agent, out):
    env = dict(os.environ)
    if agent == "codex" and os.environ.get("CODEX_BIN"):
        shim = out / "bin"
        shim.mkdir(parents=True, exist_ok=True)
        binary = Path(os.environ["CODEX_BIN"]).resolve()
        # Codex spawns helpers such as codex-code-mode-host from the directory
        # it was started from, so a lone symlink disables its shell tool.
        helpers = [path for path in binary.parent.iterdir() if path.name.startswith("codex-") and path.is_file() and os.access(path, os.X_OK)]
        for source in (binary, *helpers):
            link = shim / ("codex" if source == binary else source.name)
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(source)
        env["PATH"] = f"{shim}{os.pathsep}{env['PATH']}"
    version = subprocess.run([agent, "--version"], capture_output=True, text=True, env=env, check=False)
    if version.returncode != 0:
        raise ScreenError(f"`{agent} --version` failed under the run's PATH; set CODEX_BIN for a working codex binary")
    print(f"{agent}: {version.stdout.strip()}")
    return env


def entry_wrapper(agent, out, target):
    token, discovery = ENTRY_INVOCATION[agent]
    wrapper = out / "entry" / agent
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        "#!/bin/sh\n"
        f"mkdir -p {shlex.quote(str(Path(discovery).parent))}\n"
        f"ln -sfn ../skills/{ENTRY_TREE} {shlex.quote(discovery)}\n"
        f"{{ printf '%s ' {shlex.quote(token)}; cat; }} | {shlex.quote(str(target))} \"$@\"\n"
    )
    wrapper.chmod(0o755)
    return wrapper


def workspace_wrapper(agent, out, target, entry):
    """The entry wrapper for a workspace case. workspace.py wrap materializes
    the checkout in the agent's cwd, adds the invocation under the poteto-mode
    entry, runs the agent, and harvests its diff."""
    wrapper = out / "entry" / f"{agent}-workspace"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(CANON / "workspace.py"), "wrap"]
    if entry == ENTRY_SKILL:
        token, discovery = ENTRY_INVOCATION[agent]
        command += ["--token", token, "--discovery", discovery]
    command += ["--", str(target)]
    wrapper.write_text(f"#!/bin/sh\nexec {' '.join(map(shlex.quote, command))} \"$@\"\n")
    wrapper.chmod(0o755)
    return wrapper


def backend_args(agent, out, entry, in_workspace=False):
    tools = skill_ci() / "tools"
    target = tools / ("claude-project-only" if agent == "claude" else "codex-project-only")
    if in_workspace:
        target = workspace_wrapper(agent, out, target, entry)
    elif entry == ENTRY_SKILL:
        target = entry_wrapper(agent, out, target)
    if agent == "claude":
        return ["--claude-bin", target]
    sandbox = "workspace-write" if in_workspace else "read-only"
    return ["--codex-cmd", f"{shlex.quote(str(target))} exec --json --skip-git-repo-check --sandbox {sandbox}"]


def file_harvest(work, expected_tree):
    """Move the numbered slots the wrapper filled, in task order, to each run's
    path under work/harvest, and refuse a run whose workspace was not the
    tree the build recorded."""
    harvest = work / "harvest"
    rows = [json.loads(line)["run_dir"] for line in (work / "tasks.jsonl").read_text().splitlines()]
    slots = sorted(harvest.glob("[0-9][0-9][0-9][0-9]")) if harvest.is_dir() else []
    if len(slots) != len(rows):
        raise ScreenError(f"{work}: the wrapper filled {len(slots)} workspace slot(s) for {len(rows)} run(s)")
    for slot, run_dir in zip(slots, rows):
        record = json.loads((slot / "workspace.json").read_text())
        if record.get("tree") != expected_tree or record.get("error"):
            raise ScreenError(f"{work}/{run_dir}: workspace tree {record.get('tree')} is not the built {expected_tree} {record.get('error', '')}".rstrip())
        destination = harvest / run_dir
        destination.parent.mkdir(parents=True, exist_ok=True)
        slot.rename(destination)


def run(agent, out, rules, model, runs, timeout, entry="skill"):
    env = agent_env(agent, out)
    built = build(out, rules, entry)
    for rule in rules:
        for case in rule.cases:
            case_build = built[rule.id]["cases"][case.id]
            backend = backend_args(agent, out, entry, "workspace" in case_build)
            for arm in ARMS:
                check_manifest(out / "arms" / rule.id / case.id / arm, case.kind)
            for arm in ARMS:
                root = out / "arms" / rule.id / case.id / arm
                work = out / agent / rule.id / case.id / arm
                if work.exists():
                    raise ScreenError(f"{work} exists; use a fresh --out so runs never mix")
                work.mkdir(parents=True)
                harness("prepare", root / MANIFEST, "--split", "tune", "--runs-per-variant", runs, "--out", work / "tasks-all.jsonl")
                with_skill_rows(work / "tasks-all.jsonl", work / "tasks.jsonl")
                run_env = env
                if "workspace" in case_build:
                    run_env = {**env, "CANON_WORKSPACE": str(root / "workspace"), "CANON_HARVEST": str(work / "harvest")}
                harness("run-agent", "--agent", agent, "--model", model, *backend,
                        "--tasks", work / "tasks.jsonl", "--runs", work / "runs",
                        "--timeout", timeout or case_build["timeout_s"], env=run_env)
                if "workspace" in case_build:
                    file_harvest(work, case_build["workspace"]["tree"])
                harness("grade", root / MANIFEST, "--runs", work / "runs", "--variant", "with_skill",
                        "--allow-scripts", "--out", work / "grade.json")
    compare(out)


def verdict(result):
    rows = [row for row in result.get("assertions", []) if row.get("name") == "rule-behavior"]
    if not rows or result.get("missing_output") or result.get("execution_valid") is False:
        return "INVALID", "no gradable answer"
    evidence = rows[0].get("evidence") or ""
    reasons = [line.removeprefix("FAIL: ") for line in evidence.splitlines() if line.startswith("FAIL: ")]
    return ("PASS" if rows[0].get("passed") else "FAIL"), "; ".join(reasons)


def skill_files_read(events, tree_files):
    """Tracked skill files named by a completed read, command, or tool input.

    A read counts when the input names the file's path under skills/, or names
    both its skill directory and its path inside that skill (cd then cat)."""
    inputs = [
        str(event.get("input_summary") or "")
        for event in events
        if event.get("status") == "completed" and event.get("type") in READ_EVENTS
    ]
    seen = set()
    for path in tree_files:
        skill, _, inner = path.partition("/")
        segment = re.compile(rf"(^|[/\s]){re.escape(skill)}($|[/\s])")
        if any(path in text or (segment.search(text) and inner in text) for text in inputs):
            seen.add(path)
    return sorted(seen)


def entry_invoked(run_base):
    trace = run_base / "trace.jsonl"
    return trace.is_file() and f"<command-name>/{ENTRY_SKILL}</command-name>" in trace.read_text(errors="replace")


def exposure(result, tree_files):
    base = Path(result.get("run_base", ""))
    events_path = base / "events.json"
    events = json.loads(events_path.read_text()).get("events", []) if events_path.is_file() else []
    return {"read": skill_files_read(events, tree_files), "entry_invoked": entry_invoked(base)}


def classify(current, amended, target):
    """Name what a pair shows. A pair whose amended arm never read the patched
    file says nothing about the rule, so it is unexposed rather than a tie."""
    if current is None or amended is None or "INVALID" in (current["verdict"], amended["verdict"]):
        return "invalid"
    exposed = target in amended["exposure"]["read"] or (target == f"{ENTRY_SKILL}/SKILL.md" and amended["exposure"]["entry_invoked"])
    if not exposed:
        return "unexposed"
    return {
        ("FAIL", "PASS"): "separates",
        ("PASS", "FAIL"): "reverses",
        ("PASS", "PASS"): "tie-pass",
        ("FAIL", "FAIL"): "tie-fail",
    }[(current["verdict"], amended["verdict"])]


def rule_verdict(outcomes):
    """outcomes: [(case id, case kind, pair outcome)] for one rule, agent, and run,
    with outcome "missing" for a built case that has no grade. Returns (verdict,
    reasons). A near-miss that went ungraded or never ran cannot show it held,
    so it blocks the verdict like a reversal does."""
    reasons = [f"{case} {outcome}" for case, kind, outcome in outcomes
               if (kind == "positive" and outcome != "separates") or (kind == "near-miss" and outcome in ("reverses", "invalid", "missing"))]
    if not any(kind == "positive" for _, kind, _ in outcomes):
        reasons.append("no positive case ran")
    return ("separates" if not reasons else "not-separated"), reasons


def compare(out):
    if not any(out.glob("*/*/*/*/grade.json")) and any(out.glob("*/*/*/grade.json")):
        raise ScreenError(f"{out} was made before rules had cases; its compare.json is final and plan reads it")
    table = []
    for grade in sorted(out.glob("*/*/*/*/grade.json")):
        agent, rule, case, arm = grade.parent.relative_to(out).parts
        build_info = json.loads((out / "arms" / rule / "build.json").read_text())
        tree_root = out / "arms" / rule / case / arm / build_info["tree_dir"]
        tree_files = sorted(path.relative_to(tree_root).as_posix() for path in tree_root.rglob("*.md"))
        companions = set(build_info.get("companions", {}).get("trees", {}))
        for result in json.loads(grade.read_text())["results"]:
            status, reasons = verdict(result)
            seen = exposure(result, tree_files)
            if companions:
                seen["companions_read"] = sorted({path.split("/", 1)[0] for path in seen["read"]} & companions)
            table.append({
                "agent": agent, "rule": rule, "case": case, "kind": build_info["cases"][case]["kind"], "arm": arm,
                "run": result.get("run_number"), "entry": build_info["entry"], "target": build_info["target"],
                "verdict": status, "reasons": reasons, "exposure": seen,
            })
    pairs = {}
    for row in table:
        pairs.setdefault((row["agent"], row["rule"], row["run"], row["case"]), {})[row["arm"]] = row
    summary = []
    for (agent, rule, run_number, case), arms in sorted(pairs.items(), key=lambda item: tuple(map(str, item[0]))):
        first = next(iter(arms.values()))
        outcome = classify(arms.get("current"), arms.get("amended"), first["target"])
        summary.append({"agent": agent, "rule": rule, "case": case, "kind": first["kind"], "run": run_number, "target": first["target"], "outcome": outcome})
        cells = [f"{arm}={arms[arm]['verdict'] if arm in arms else 'MISSING'}" for arm in ARMS]
        print(f"{agent:6} {rule:26} {case:18} {first['kind']:9} run-{run_number}  " + "  ".join(cells) + f"  {outcome.upper()}")
        for arm in ARMS:
            row = arms.get(arm)
            if row is None:
                continue
            seen = row["exposure"]["read"]
            target_state = "read" if first["target"] in seen else "NOT READ"
            entry_state = "invoked" if row["exposure"]["entry_invoked"] else "not observed"
            companion_state = ""
            if "companions_read" in row["exposure"]:
                companion_state = f"; companion {', '.join(row['exposure']['companions_read']) or 'none'} read"
            print(f"    {arm}: {first['target']} {target_state}; entry {entry_state}{companion_state}; read {len(seen)} skill file(s): {', '.join(seen) or 'none'}")
            if row["reasons"]:
                print(f"    {arm}: {row['reasons']}")
    grouped = {}
    for pair in summary:
        grouped.setdefault((pair["agent"], pair["rule"], pair["run"]), []).append((pair["case"], pair["kind"], pair["outcome"]))
    for (agent, rule, run_number), outcomes in grouped.items():
        ran = {case for case, _, _ in outcomes}
        built_cases = json.loads((out / "arms" / rule / "build.json").read_text())["cases"]
        outcomes += [(case, spec["kind"], "missing") for case, spec in built_cases.items() if case not in ran]
    rules = []
    for (agent, rule, run_number), outcomes in sorted(grouped.items(), key=lambda item: tuple(map(str, item[0]))):
        result, reasons = rule_verdict(outcomes)
        rules.append({"agent": agent, "rule": rule, "run": run_number, "verdict": result, "reasons": reasons})
        print(f"{agent:6} {rule:26} rule run-{run_number}  {result.upper()}" + (f"  ({'; '.join(reasons)})" if reasons else ""))
    (out / "compare.json").write_text(json.dumps({"pairs": summary, "rules": rules, "runs": table}, indent=2) + "\n")
    print(f"wrote {out / 'compare.json'}")


def out_dirs(roots):
    for root in roots:
        if (root / "compare.json").is_file():
            yield root
        elif root.is_dir():
            yield from sorted(path for path in root.iterdir() if (path / "compare.json").is_file())


def arm_file(out, rule_id, case_id, arm, build_info):
    arm_root = out / "arms" / rule_id / arm if "cases" not in build_info else out / "arms" / rule_id / case_id / arm
    path = arm_root / build_info["tree_dir"] / build_info["target"]
    return path.read_bytes() if path.is_file() else None


def past_runs(roots, rules, trees):
    """{(rule, case): ["agent/entry outcome", ...]} from finished --out dirs. A run
    whose owner file differs from today's current or amended text is marked as
    run against older text."""
    runs = {}
    for out in out_dirs(roots):
        for pair in json.loads((out / "compare.json").read_text())["pairs"]:
            rule = rules.get(pair["rule"])
            case_id = pair.get("case") or LEGACY_CASES.get(pair["rule"])
            build_path = out / "arms" / pair["rule"] / "build.json"
            if rule is None or not build_path.is_file():
                continue
            build_info = json.loads(build_path.read_text())
            current, amended = trees[rule.id]
            fresh = build_info["target"] == rule.target and all(
                arm_file(out, rule.id, case_id, arm, build_info) == tree.get(rule.target)
                for arm, tree in zip(ARMS, (current, amended))
            )
            label = f"{pair['agent']}/{build_info['entry']} {pair['outcome']}" + ("" if fresh else " (older text)")
            runs.setdefault((rule.id, case_id), []).append(label)
    return runs


def plan(roots):
    rules = {rule.id: rule for rule in load_rules()}
    tree = tracked("skills")
    trees, changes = {}, {}
    for rule in rules.values():
        try:
            amended = apply_patch(tree, rule.patch)
            changes[rule.id] = single_change(tree, amended)
            trees[rule.id] = (tree, amended)
        except ScreenError as exc:
            changes[rule.id] = exc
            trees[rule.id] = (tree, {})
    runs = past_runs(roots, rules, trees)
    for rule in rules.values():
        change = changes[rule.id]
        kind = change.kind if isinstance(change, Change) else f"BROKEN: {change}"
        print(f"{rule.id}  [{rule.source}]  skills/{rule.target}  {kind}" + (f"  companions {', '.join(rule.companions)}" if rule.companions else ""))
        for case in rule.cases:
            seen = runs.get((rule.id, case.id))
            print(f"  {case.id:20} {case.kind:9}  {'; '.join(seen) if seen else 'not run'}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--runs-root", type=Path, action="append",
                   help=f"a finished --out dir, or a directory of them; repeatable (default {DEFAULT_RUNS_ROOT})")
    p = sub.add_parser("build")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--entry", choices=ENTRIES, default="skill")
    p.add_argument("rules", nargs="*")
    p = sub.add_parser("audit")
    p.add_argument("--entry", choices=ENTRIES, default="skill")
    p.add_argument("rules", nargs="*")
    p = sub.add_parser("run")
    p.add_argument("--agent", choices=sorted(DEFAULT_MODELS), required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model")
    p.add_argument("--runs", type=int, default=1, help="paired repetitions per case (default 1)")
    p.add_argument("--timeout", type=int, help="seconds per answer; a workspace case defaults to its timeout_s, else 1800; "
                   "other cases to 900 under the poteto-mode entry, else their timeout_s")
    p.add_argument("--entry", choices=ENTRIES, default="skill")
    p.add_argument("rules", nargs="*")
    p = sub.add_parser("compare")
    p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            plan(args.runs_root or [DEFAULT_RUNS_ROOT])
        elif args.command == "build":
            build(args.out.resolve(), load_rules(args.rules), args.entry)
        elif args.command == "audit":
            audit(load_rules(args.rules), args.entry)
        elif args.command == "run":
            run(args.agent, args.out.resolve(), load_rules(args.rules), args.model or DEFAULT_MODELS[args.agent], args.runs, args.timeout, args.entry)
        else:
            compare(args.out.resolve())
    except (ScreenError, workspace.WorkspaceError, subprocess.CalledProcessError) as exc:
        print(f"screen: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
