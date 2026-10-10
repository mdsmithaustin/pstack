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

A rule whose rule.json names cases_from is a placement variant. It has its own
rule.patch and runs the named rule's cases and oracle unchanged, or only the
case ids its "cases" list names. The named rule may be an arms rule that holds
its own cases.

An arms rule is a rule whose rule.json lists "arms", current first. It takes
its cases from cases_from, or holds its own oracle.py and cases/ without it. Each
other arm has arms/<arm>.patch, a unified diff against skills/ that may touch
several files. Every arm of every case is built and graded, and compare shows
each arm against current and each later arm against each earlier one.

The arm named stub takes no patch. It keeps every skill directory and each
SKILL.md's frontmatter, and drops every SKILL.md body and every other file, so
it is a control with the same skill names and triggers but no guidance. Any
comparison with it takes stub as the baseline.

A case whose case.json names a workspace runs inside a checkout of a real repo
at a pinned commit (see workspace.py) instead of receiving project files in the
prompt. Its oracle grades the diff the agent left on that checkout.

A workspace case that also names a review hands the agent a pull request on a
branch. Its oracle is a precheck, and a blinded judge from the other model
family grades each review against the case's rubric.md (see review.py).

A case that names a document is judged the same way, on one document instead
of a review: the whole final message, or one named file, read from the final
message's <file path="..."> block in a pasted-project case and from the
harvested diff in a workspace case. A run that delivers no document is
INVALID, never a verdict.

  screen.py plan [--runs-root DIR ...]                 list rules, cases, and past runs
  screen.py build --out DIR [--entry E] [RULE ...]     write both arms of every case
  screen.py audit [--entry E] [RULE ...]               model-free: build, validate, audit, prepare
  screen.py run --agent claude|codex --out DIR [--entry E] [--runner host|sbx] [RULE ...]   paid: answer, grade, compare
  screen.py compare --out DIR                          print paired verdicts with exposure
  screen.py regrade --out DIR                          grade workspace runs again from their diffs, then compare
  screen.py judge --out DIR [--judge B:M]              paid: judge every review or document run again, then compare
  screen.py calibrate [--judge B:M ...] RULE ...       paid: judge each judged case's labeled samples

Every command with --out appends the traceback of any error to
<out>/screen-error.log and prints where it went on stdout and stderr. run logs
a failed arm and goes on to the next, then exits 1.

regrade runs each workspace case's oracle, from the arm's grader copy, on every
harvested run's diff and output.md (empty when missing). It writes regrade.json
beside each grade.json, which it leaves as is, and compare prefers regrade.json
when present. A run the harness called INVALID and regrade graded carries
graded_from_diff. An arm whose run stopped before grading, with harvest slots
still numbered or no grade.json, is mapped and graded from its diff too.
Pasted-project cases keep the harness grade.
"""
import argparse
import dataclasses
import difflib
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import traceback
from dataclasses import dataclass
from pathlib import Path

CANON = Path(__file__).resolve().parent
sys.path.insert(0, str(CANON))
sys.path.insert(0, str(CANON / "oracles"))
import host  # noqa: E402
import review  # noqa: E402
import shared  # noqa: E402
import workspace  # noqa: E402

REPO = CANON.parents[1]
_listing_spec = importlib.util.spec_from_file_location("skill_listing", REPO / "skills/setup-pstack/scripts/skill-listing.py")
skill_listing = importlib.util.module_from_spec(_listing_spec)
_listing_spec.loader.exec_module(skill_listing)
LAUNCHERS = REPO / "tools"
RULES = Path(os.environ.get("CANON_RULES", CANON / "rules")).resolve()
ARMS = ("current", "amended")
ARM_NAME = re.compile(r"^[a-z0-9][a-z0-9+._-]*$")
STUB = "stub"
FRONTMATTER = re.compile(rb"---\n.*?\n---(?:\n|$)", re.DOTALL)
DEFAULT_MODELS = {"claude": "sonnet", "codex": "gpt-6-sol"}
MANIFEST = "shared-benchmark.json"
ENTRIES = ("skill", "poteto-mode")
ENTRY_SKILL = "poteto-mode"
ENTRY_TREE = "pstack"
ENTRY_TIMEOUT_S = 900
DEFAULT_RUNS_ROOT = Path("/private/tmp/canon-entry")
DEFAULT_COMPANIONS_ROOT = Path.home() / ".agents" / "skills"
COMPANION_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
# Codex docs: "$skill" works even when agents/openai.yaml disables implicit use.
ENTRY_INVOCATION = {"claude": ("/poteto-mode", ".claude/skills"), "codex": ("$poteto-mode", ".agents/skills")}
# claude-project-only runs -p under acceptEdits, which denies Bash, and Claude
# Code 2.1.281 has no Grep or Glob tool there. In a workspace case these rules
# let Claude run read-only commands by prefix, as Codex can. The deny rules
# close the flags that run another program or delete files.
CLAUDE_WORKSPACE_TOOLS = (
    "--allowedTools",
    *(f"Bash({prefix}:*)" for prefix in (
        "git log", "git show", "git grep", "git diff", "git status",
        "rg", "grep", "ls", "find", "wc", "head", "sed -n",
    )),
    "--disallowedTools",
    "Bash(find * -exec*)", "Bash(find * -ok*)", "Bash(find * -delete*)",
    "Bash(rg * --pre*)", "Bash(git grep * -O*)", "Bash(git grep * --open-files-in-pager*)",
)
READ_EVENTS = {"file_read", "skill_load", "command", "tool_call"}
# A Skill tool input: the bare skill name, with an optional plugin prefix or leading slash.
LOADED_SKILL = re.compile(r"^(?:[\w.-]+:)?/?([a-z0-9][a-z0-9_-]*)$")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,(\d+))? @@")
# The harness names a near-miss case "adversarial"; a regression guard, not a capability.
CASE_KINDS = {"positive": ("positive", "capability"), "near-miss": ("adversarial", "regression")}
# audit-manifest blocks any manifest without a near-miss case. Each manifest holds
# one case, so a positive case's manifest accepts that one blocker and no other.
ACCEPTED_BLOCKER = "no adversarial cases"
LEAK = re.compile(r"\b(evals?|evaluation|judge|experiment|rubric|score|compare|benchmark|candidate|arena)\b", re.IGNORECASE)
ERROR_LOG = "screen-error.log"
# Runs made before rules had cases name no case. These are the cases they ran.
LEGACY_CASES = {
    "observe-through-interface": "register-email",
    "translate-foreign-model": "paylane-webhooks",
    "notation-not-runtime": "checkout-rules",
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

    @property
    def review(self):
        return self.spec.get("review")

    @property
    def document(self):
        """{"file": path} or {"message": True} for a judged document case, else None."""
        return self.spec.get("document")

    @property
    def frame(self):
        """The judge frame, "review" or "document", or None for an oracle-only case."""
        return "review" if self.review else "document" if self.document else None

    @property
    def owner(self):
        """The rule whose cases/ holds this case; a variant borrows its source's."""
        return self.root.parent.parent.name


def judged(case_build):
    """Whether a build.json case record names a review or a document."""
    return "review" in case_build or "document" in case_build


def case_spec(case):
    return workspace.parse_spec(case.root, case.workspace, case.review)


def standin_carries(rule, arm):
    """Whether the offline stand-ins answer an arm of a workspace case as one
    that carries the rule: every arm but current, or, beside a stub, every arm
    but the stub."""
    return arm != (STUB if STUB in rule.arm_names else "current")


def standin_review(case, treated):
    """The labeled sample an offline stand-in answers a judged case with: the
    CLEAN one for a near-miss, else FOUND when the rule is mounted and MISSED
    when it is not."""
    wanted = "CLEAN" if case.kind == "near-miss" else ("FOUND" if treated else "MISSED")
    labels = check_labels(case.root, case.kind)
    return case.root / "samples" / next(name for name, label in sorted(labels.items()) if label == wanted)


def check_labels(root, kind, document=None, in_workspace=False):
    """samples/labels.json maps each calibration sample to a verdict the judge
    may give for the case's kind. In a document case every sample must
    deliver the document the way a run does: a pasted case's sample holds the
    file block document_text cuts, and a workspace case's sample for a file has
    a sibling .diff that writes that file without deleting it. A sample that
    would judge as absent is refused here, so calibration only ever sees
    deliverable shapes."""
    path = root / "samples" / "labels.json"
    labels = json.loads(path.read_text())
    if not isinstance(labels, dict) or not labels:
        raise ScreenError(f"{path} must map sample file names to verdicts")
    for name, label in labels.items():
        if label not in review.VERDICTS[kind]:
            raise ScreenError(f"{path} labels {name} {label!r}; a {kind} case's verdicts are {review.VERDICTS[kind]}")
        if not (root / "samples" / name).is_file() or "/" in name:
            raise ScreenError(f"{path} names {name}, which is not a file in samples/")
        if document and "file" in document and in_workspace:
            diff = root / "samples" / Path(name).with_suffix(".diff")
            if not diff.is_file() or document["file"] not in patch_paths(diff.read_text())[1]:
                raise ScreenError(f"sample {name} needs a sibling {diff.name} that writes {document['file']}, as a run's harvested diff would")
            if patch_deletes(diff.read_text(), document["file"]):
                raise ScreenError(f"sample {name} has a sibling {diff.name} that deletes {document['file']}, so a run's harvested diff would deliver no document")
        elif document and not shared.document_text((root / "samples" / name).read_text(), document).strip():
            where = f"a <file path=\"{document['file']}\"> block" if "file" in document else "any text"
            raise ScreenError(f"sample {name} delivers no document; a run's final message would need {where}")
    return labels


@dataclass(frozen=True)
class Rule:
    id: str
    source: str
    # rule.patch of a pair rule; None for an arms rule.
    patch: str
    target: str
    cases: tuple
    companions: tuple = ()
    cases_from: str = None
    # An arms rule's ((arm, patch), ...) for every arm after current, in order;
    # the stub arm's patch is None.
    arm_patches: tuple = ()
    # The commit whose skills/ the rule was screened against; None screens the working tree.
    skills_at: str = None

    @property
    def paired(self):
        return not self.arm_patches

    @property
    def arms(self):
        """((arm, patch or None), ...) in run order. current has no patch."""
        treated = (("amended", self.patch),) if self.paired else self.arm_patches
        return (("current", None), *treated)

    @property
    def arm_names(self):
        return tuple(name for name, _ in self.arms)

    @property
    def skill(self):
        return self.target.split("/", 1)[0]

    @property
    def skills(self):
        """Skill directories the rule changes, which the single-skill entry mounts."""
        if self.paired:
            return (self.skill,)
        return tuple(sorted({path.split("/", 1)[0] for _, patch in self.arm_patches if patch for path in patch_paths(patch)[1]})) or (self.skill,)

    @property
    def case_rule(self):
        return self.cases_from or self.id


@dataclass(frozen=True)
class Change:
    target: str
    removed: str
    inserted: str

    @property
    def kind(self):
        return "replace" if self.removed else "insert"


def harness(*arguments, env=None):
    command = ["skill-ci", "harness", "skill-benchmark", *map(str, arguments)]
    print("+", " ".join(command[2:]), flush=True)
    subprocess.run(command, check=True, env=env, cwd=REPO)


def load_check(rules=None):
    spec = importlib.util.spec_from_file_location("canon_check", CANON / "oracles" / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RULES = rules or RULES
    return module


def oracle_checks(rule_id):
    return load_check().load_oracle(rule_id)


def load_case(rule_id, root):
    spec_path = root / "case.json"
    spec = json.loads(spec_path.read_text()) if spec_path.is_file() else {}
    in_workspace = "workspace" in spec
    for required in (spec_path, root / "prompt.md", *(() if in_workspace else (root / "project",))):
        if not required.exists():
            raise ScreenError(f"case {rule_id}/{root.name} has no {required.name}")
    if in_workspace and (root / "project").exists():
        raise ScreenError(f"case {rule_id}/{root.name} names a workspace, so it must not have project/")
    missing = {"kind", "domain", "expected_behavior", *(() if in_workspace else ("timeout_s",))} - set(spec)
    if missing:
        raise ScreenError(f"{spec_path} lacks {sorted(missing)}")
    if spec.get("kind") not in CASE_KINDS:
        raise ScreenError(f"{spec_path} kind must be one of {sorted(CASE_KINDS)}, not {spec.get('kind')!r}")
    if "review" in spec and "document" in spec:
        raise ScreenError(f"{spec_path} names both a review and a document; a case is judged on one")
    if "review" in spec and not in_workspace:
        raise ScreenError(f"{spec_path} names a review, so it must name a workspace")
    if "document" in spec:
        document = spec["document"]
        if document != {"message": True} and not (isinstance(document, dict) and set(document) == {"file"} and isinstance(document["file"], str)):
            raise ScreenError(f"{spec_path} document must be {{\"file\": \"<path>\"}} or {{\"message\": true}}, not {document!r}")
        if "file" in document:
            try:
                shared.safe_path(document["file"])
            except shared.OracleError as exc:
                raise ScreenError(f"{spec_path} document file: {exc}") from exc
    if in_workspace:
        workspace.parse_spec(root, spec["workspace"], spec.get("review"))
    if "review" in spec or "document" in spec:
        for required in (root / "rubric.md", root / "samples" / "labels.json"):
            if not required.is_file():
                raise ScreenError(f"judged case {rule_id}/{root.name} has no {required.relative_to(root)}")
        check_labels(root, spec["kind"], spec.get("document"), in_workspace)
    if LEAK.search(root.name):
        raise ScreenError(f"case id {root.name!r} carries meta vocabulary; pick a project-shaped name")
    return Case(rule_id, root.name, spec["kind"], root, spec)


def rule_spec(rule_id):
    """rule.json, with a variant's missing source and companions taken from
    the rule it names in cases_from. A variant holds no cases/ or oracle.py."""
    root = RULES / rule_id
    if not (root / "rule.json").is_file():
        raise ScreenError(f"rule {rule_id} has no rule.json")
    spec = json.loads((root / "rule.json").read_text())
    origin = spec.get("cases_from")
    if origin is None:
        return spec
    for own in ("oracle.py", "cases"):
        if (root / own).exists():
            raise ScreenError(f"rule {rule_id} takes its cases from {origin}, so it must not have {own}")
    if not isinstance(origin, str) or origin == rule_id or not (RULES / origin / "rule.json").is_file():
        raise ScreenError(f"rules/{rule_id}/rule.json cases_from must name another rule, not {origin!r}")
    source = json.loads((RULES / origin / "rule.json").read_text())
    if "cases_from" in source:
        raise ScreenError(f"rule {rule_id} takes its cases from {origin}, which takes its own from {source['cases_from']}")
    return {"source": source["source"], "companions": source.get("companions", []), **spec}


def load_arm_patches(rule_id, names):
    """((arm, patch), ...) for an arms rule: one arms/<arm>.patch per listed arm
    after current except stub, and no patch that rule.json does not list."""
    root = RULES / rule_id
    if (root / "rule.patch").exists():
        raise ScreenError(f"rule {rule_id} lists arms, so it must not have rule.patch")
    if not isinstance(names, list) or not names or names[0] != "current":
        raise ScreenError(f"rules/{rule_id}/rule.json arms must be a list that starts with current, not {names!r}")
    if len(names) < 2 or len(set(names)) != len(names) or not all(isinstance(name, str) and ARM_NAME.match(name) for name in names):
        raise ScreenError(f"rules/{rule_id}/rule.json arms must be current and at least one more distinct name matching {ARM_NAME.pattern}, not {names!r}")
    patches = {path.name.removesuffix(".patch"): path for path in (root / "arms").glob("*.patch")}
    missing = [name for name in names[1:] if name != STUB and name not in patches]
    if missing:
        raise ScreenError(f"rule {rule_id} has no arms/<arm>.patch for {missing}")
    if STUB in patches:
        raise ScreenError(f"rule {rule_id} has arms/{STUB}.patch, but the {STUB} arm is built from current and takes no patch")
    unlisted = sorted(set(patches) - set(names[1:]))
    if unlisted:
        raise ScreenError(f"rule {rule_id} has arms/<arm>.patch for arms its rule.json does not list after current: {unlisted}")
    return tuple((name, None if name == STUB else patches[name].read_text()) for name in names[1:])


def load_rule(rule_id):
    spec = rule_spec(rule_id)
    origin = spec.get("cases_from", rule_id)
    arm_patches = ()
    if "arms" in spec or (RULES / rule_id / "arms").exists():
        arm_patches = load_arm_patches(rule_id, spec.get("arms"))
    root = RULES / origin
    for required in ("oracle.py", "cases"):
        if not (root / required).exists():
            raise ScreenError(f"rule {origin} has no {required}")
    patch = None if arm_patches else (RULES / rule_id / "rule.patch").read_text()
    cases = tuple(load_case(rule_id, path) for path in sorted((root / "cases").iterdir()) if path.is_dir())
    checks = set(oracle_checks(origin))
    if checks != {case.id for case in cases}:
        raise ScreenError(f"rules/{origin}/oracle.py CHECKS covers {sorted(checks)}, cases are {[case.id for case in cases]}")
    chosen = spec.get("cases")
    if chosen is not None:
        if not isinstance(chosen, list) or not chosen or not all(isinstance(id, str) and id for id in chosen) or not set(chosen) <= checks:
            raise ScreenError(f"rules/{rule_id}/rule.json cases must be a list of case ids from {origin} {sorted(checks)}, not {chosen!r}")
        cases = tuple(case for case in cases if case.id in chosen)
    if not any(case.kind == "positive" for case in cases):
        raise ScreenError(f"rule {rule_id} runs no positive case")
    companions = spec.get("companions", [])
    if not isinstance(companions, list) or not all(isinstance(name, str) and COMPANION_NAME.match(name) for name in companions):
        raise ScreenError(f"rules/{rule_id}/rule.json companions must be a list of skill directory names, not {companions!r}")
    skills_at = spec.get("skills_at")
    if skills_at is not None and not (isinstance(skills_at, str) and COMMIT.match(skills_at)):
        raise ScreenError(f"rules/{rule_id}/rule.json skills_at must be a full 40-character commit, not {skills_at!r}")
    patched = [arm_patch for _, arm_patch in arm_patches if arm_patch]
    target = parse_patch(patch)[0] if patch else sorted(patch_paths(patched[0])[1])[0] if patched else f"{ENTRY_SKILL}/SKILL.md"
    return Rule(rule_id, spec["source"], patch, target, cases, tuple(companions), spec.get("cases_from"), arm_patches, skills_at)


def load_rules(requested=()):
    known = sorted(path.name for path in RULES.iterdir() if (path / "rule.patch").is_file() or (path / "arms").is_dir() or lists_arms(path))
    unknown = sorted(set(requested) - set(known))
    if unknown:
        raise ScreenError(f"unknown rule(s): {', '.join(unknown)}; known: {', '.join(known)}")
    return [load_rule(rule_id) for rule_id in (requested or known)]


def lists_arms(root):
    """Whether root's rule.json lists arms, which a rule of current and stub
    alone needs to be found, having no patch."""
    return (root / "rule.json").is_file() and "arms" in json.loads((root / "rule.json").read_text())


def tracked(scope, commit=None):
    if commit is not None:
        archive = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", commit, "--", scope], capture_output=True)
        if archive.returncode != 0:
            raise ScreenError(f"cannot read {scope}/ at {commit}: {archive.stderr.decode().strip()}")
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            return {member.name.removeprefix("skills/"): tar.extractfile(member).read() for member in tar if member.isfile()}
    listing = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "--", scope],
        capture_output=True, check=True,
    ).stdout.decode()
    paths = [path for path in listing.split("\0") if path]
    if not paths:
        raise ScreenError(f"{scope} has no tracked files")
    return {path.removeprefix("skills/"): (REPO / path).read_bytes() for path in paths}


def rule_tree(rule):
    return tracked("skills", rule.skills_at)


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


def git_apply(tree, patch, *flags):
    """Run git apply on tree written into a scratch repo, which anchors the
    patch paths at its root. Returns (completed process, tree read back)."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        env = {**os.environ, **workspace.GIT_ENV}
        subprocess.run(["git", "init", "-q", str(root)], env=env, check=True)
        for path, data in tree.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_bytes(data)
        (root / ".git" / "arm.patch").write_text(patch)
        result = subprocess.run(["git", "apply", *flags, ".git/arm.patch"], cwd=root, env=env, capture_output=True, text=True)
        return result, {path: data for path, data in read_tree(root).items() if not path.startswith(".git/")}


def patch_paths(patch):
    """(strip level, paths relative to skills/) of a multi-file patch. Paths
    written as a/skills/... drop the skills/ prefix."""
    result, _ = git_apply({}, patch, "--numstat", "-p1")
    if result.returncode:
        raise ScreenError(f"arm patch does not parse: {result.stderr.strip()}")
    paths = [line.split("\t", 2)[2] for line in result.stdout.splitlines()]
    if paths and all(path.startswith("skills/") for path in paths):
        return 2, [path.removeprefix("skills/") for path in paths]
    return 1, paths


def patch_deletes(patch, path):
    """Whether a patch deletes path."""
    result, _ = git_apply({}, patch, "--summary", "-p1")
    if result.returncode:
        raise ScreenError(f"patch does not parse: {result.stderr.strip()}")
    return any(line.split(" ", 4)[4:] == [path] for line in result.stdout.splitlines() if line.startswith(" delete mode "))


def apply_arm_patch(tree, patch):
    """The tree with an arm's patch applied by git apply. Refuses a patch that
    does not apply or leaves the tree as it was."""
    strip, _ = patch_paths(patch)
    result, applied = git_apply(tree, patch, f"-p{strip}")
    if result.returncode:
        raise ScreenError(f"arm patch does not apply to skills/: {result.stderr.strip()}")
    if applied == tree:
        raise ScreenError("arm patch changes nothing")
    return applied


def stub_tree(tree):
    """Each skill's SKILL.md cut to its frontmatter and its agents/openai.yaml
    as it is, so both arms list the same skills by description and the same
    by name only. No other file."""
    stubs = {}
    for path, data in tree.items():
        inner = path.partition("/")[2]
        if inner == "SKILL.md":
            match = FRONTMATTER.match(data)
            if not match:
                raise ScreenError(f"skills/{path} has no frontmatter to keep in the stub arm")
            stubs[path] = match.group(0)
        elif inner == workspace.INVOCATION_POLICY:
            stubs[path] = data
    return stubs


def arm_trees(rule, current):
    """[(arm, tree)] in the rule's order, current first."""
    apply = apply_patch if rule.paired else apply_arm_patch
    return [(name, stub_tree(current) if name == STUB else current if patch is None else apply(current, patch)) for name, patch in rule.arms]


def arm_summary(arm, paths):
    if arm == STUB:
        cut = sum(path.endswith("/SKILL.md") and path.count("/") == path.startswith("skills/") + 1 for path in paths)
        return f"{cut} SKILL.md cut to frontmatter, {len(paths) - cut} other file(s) dropped"
    return ", ".join(paths)


def changed_paths(before, after):
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def rule_mounted(rule, mounted, tree):
    """Whether the mounted skill text carries the rule: a pair rule's inserted
    text, or every line some arm adds that the current tree lacks. A pair rule
    whose inserted text the current file already holds, such as a cut, is
    mounted where its removed text is gone."""
    if rule.paired:
        change = rule_change(rule, tree)
        inserted, removed = change.inserted.strip(), change.removed.strip()
        if inserted and inserted not in tree[change.target].decode(errors="replace"):
            return inserted in mounted
        return removed not in mounted
    text = b"\n".join(tree.values()).decode(errors="replace")
    for _, patch in rule.arm_patches:
        if patch is None:
            continue
        added = [line[1:].strip() for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")]
        new = [line for line in added if line and line not in text]
        if new and all(line in mounted for line in new):
            return True
    return False


def frontmatter_description(skill_md):
    match = re.search(r"^description:\s*(.+)$", skill_md.split("\n---", 1)[0], re.MULTILINE)
    value = match.group(1).strip()
    return json.loads(value) if value.startswith('"') else value


def harness_version():
    pinned = tomllib.loads((REPO / ".skill-ci.toml").read_text())["version"]
    return f"skill-ci {pinned}"


def render_prompt(case):
    prompt = (case.root / "prompt.md").read_text()
    if case.workspace:
        if "{project}" in prompt:
            raise ScreenError(f"{case.rule}/{case.id} works in a checkout; its prompt must not ask for {{project}}")
        spec = case_spec(case)
        seeded = "\n".join(f"{path}\n{data.decode(errors='replace')}" for path, data in spec.overlay.items())
        if spec.review:
            seeded += f"\n{spec.review['title']}\n{spec.review['branch']}"
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


def answered_case(rules, prompt, mounted, arm_workspace=None):
    """(rule, case) the offline stand-in answers. A workspace case's input
    sits at arms/<rule>/<case>/<arm>/workspace, which names both. Otherwise the
    prompt picks the case, and a case that a variant shares with its source
    goes to the rule whose text is mounted."""
    matches = [(rule, case) for rule in rules for case in rule.cases if render_prompt(case) in prompt]
    if arm_workspace:
        named = tuple(Path(arm_workspace).parts[-4:-2])
        matches = [(rule, case) for rule, case in matches if (rule.id, case.id) == named]
    elif len(matches) > 1:
        matches.sort(key=lambda match: not rule_mounted(match[0], mounted, rule_tree(match[0])))
    if not matches:
        raise ScreenError("no case matches the prompt")
    return matches[0]


def prompt_clashes(cases):
    """Pairs of cases where one prompt equals or contains another. A variant
    and its source load the same case directory, so that pair is not a clash."""
    prompts = [(case, render_prompt(case)) for case in cases]
    return sorted(
        f"{inner.rule}/{inner.id} inside {outer.rule}/{outer.id}"
        for inner, inner_prompt in prompts for outer, outer_prompt in prompts
        if inner is not outer and inner.root != outer.root and inner_prompt in outer_prompt
    )


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
    shutil.copyfile(RULES / rule.case_rule / "oracle.py", rule_root / "oracle.py")
    if checkout is None:
        shutil.copytree(case.root / "project", rule_root / "cases" / case.id / "project", ignore=shutil.ignore_patterns("__pycache__"))
        return
    (rule_root / "cases" / case.id).mkdir(parents=True)
    (rule_root / "cases" / case.id / "workspace.json").write_text(json.dumps({"checkout": str(checkout[0]), "tree": checkout[1]}) + "\n")
    # shared.project_test_results finds this machine's dependency images here.
    if (CANON / "images" / "images.json").is_file():
        (root / "images").mkdir()
        shutil.copyfile(CANON / "images" / "images.json", root / "images" / "images.json")


def mount_clashes(tracked, rule, entry, skills):
    """Paths the repo tracks where the mounted skills will go: the skill root,
    and, under the poteto-mode entry, each skill's copy in a discovery
    directory the repo already has (workspace.expose)."""
    def taken(prefix):
        return prefix in tracked or any(path.startswith(prefix + "/") for path in tracked)

    if entry == "skill":
        return [prefix for prefix in (f"skills/{name}" for name in (*rule.skills, *rule.companions)) if taken(prefix)]
    clashes = [f"skills/{ENTRY_TREE}"] if taken(f"skills/{ENTRY_TREE}") else []
    names = sorted({path.split("/", 1)[0] for path in skills} | set(rule.companions))
    for _, discovery in ENTRY_INVOCATION.values():
        if taken(discovery):
            clashes += [discovery] if discovery in tracked else [f"{discovery}/{name}" for name in names if taken(f"{discovery}/{name}")]
    return clashes


def prepare_workspace(rule, case, entry, skills):
    """(spec, (checkout, tree)) for a workspace case, refusing a repo that
    tracks a path the mounted skills take."""
    spec = case_spec(case)
    clashes = mount_clashes(workspace.tracked_paths(workspace.require_mirror(spec), spec.commit), rule, entry, skills)
    if clashes:
        raise ScreenError(f"{rule.id}/{case.id}: {spec.repo}@{spec.commit[:12]} tracks paths the mounted skills take: {clashes}")
    return spec, workspace.reference_checkout(spec)


def review_record(spec, checkout):
    """What a review case's arms and build.json record: the PR's title,
    branch, body file, and the commit ids of main and the PR branch as the
    reference checkout holds them. None for a case that is not a review."""
    if not spec.review:
        return None
    return {"title": spec.review["title"], "branch": spec.review["branch"], "body_file": spec.review["body_file"],
            "refs": workspace.refs(checkout[0], spec.review["branch"])}


def write_arm_workspace(root, spec, tree, pr=None):
    """The arm's copy of what the entry wrapper materializes, hashed as read
    back. A review arm also holds pr.patch and the recorded refs."""
    arm = root / "workspace"
    (arm / "overlay").mkdir(parents=True)
    for path, data in spec.overlay.items():
        (arm / "overlay" / path).parent.mkdir(parents=True, exist_ok=True)
        (arm / "overlay" / path).write_bytes(data)
    record = {"repo": spec.repo, "commit": spec.commit, "mirror": str(workspace.mirror_path(spec.repo, spec.history)), "tree": tree}
    if spec.history:
        record["history"] = True
    if pr:
        (arm / "pr.patch").write_bytes(spec.review["patch"])
        record["review"] = pr
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
            skill, tree_dir = rule.skill, "skills"
            current = {path: data for path, data in rule_tree(rule).items() if path.split("/", 1)[0] in rule.skills}
            others = [name for name in rule.skills if name != skill and f"{name}/SKILL.md" in current]
            skill_paths = [f"skills/{name}/SKILL.md" for name in (skill, *others)]
        else:
            skill, tree_dir, current = ENTRY_SKILL, ENTRY_TREE, rule_tree(rule)
            skill_paths = [ENTRY_TREE]
        trees = arm_trees(rule, current)
        if rule.paired:
            change = single_change(current, trees[1][1])
            record = {"target": change.target, "patch_kind": change.kind, "removed": change.removed, "inserted": change.inserted}
        else:
            arm_changes = {name: changed_paths(current, tree) for name, tree in trees}
            record = {"target": rule.target, "patch_kind": "arms", "arm_changes": arm_changes, "arm_listed": arm_listed(current, trees)}
        description = frontmatter_description(current[f"{skill}/SKILL.md"].decode())
        companions = companion_trees(rule, current)
        if entry == "skill":
            skill_paths += [f"skills/{name}/SKILL.md" for name in companions]
        cases, arm_hashes = {}, {}
        for case in rule.cases:
            prompt = render_prompt(case)
            spec, checkout, pr, workspace_hashes = None, None, None, {}
            if case.workspace:
                spec, checkout = prepare_workspace(rule, case, entry, current)
                pr = review_record(spec, checkout)
            for arm, tree in trees:
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
                    workspace_hashes[f"{case.id}/{arm}"] = write_arm_workspace(root, spec, checkout[1], pr)
                (root / MANIFEST).write_text(json.dumps(manifest(rule, case, prompt, skill, description, skill_paths, entry), indent=2) + "\n")
            if spec is None:
                cases[case.id] = {"kind": case.kind, "timeout_s": ENTRY_TIMEOUT_S if entry == ENTRY_SKILL else case.spec["timeout_s"]}
            else:
                cases[case.id] = {"kind": case.kind, "timeout_s": case.spec.get("timeout_s", workspace.TIMEOUT_S),
                                  "workspace": workspace_record(spec, checkout, workspace_hashes)}
                if pr:
                    cases[case.id]["review"] = pr
            if case.document:
                cases[case.id]["document"] = case.document
        built[rule.id] = {"entry": entry, "tree_dir": tree_dir, **record, "arms": list(rule.arm_names), "cases": cases}
        if companions:
            built[rule.id]["companions"] = companion_record(companions, arm_hashes)
        (out / "arms" / rule.id / "build.json").write_text(json.dumps(built[rule.id], indent=2) + "\n")
        shape = f"skills/{record['target']} {record['patch_kind']}" if rule.paired else f"arms {', '.join(rule.arm_names)}"
        print(f"{rule.id}: {entry} entry, {len(current)} tracked files, {shape}, cases {', '.join(cases)}")
        for name, tree_record in built[rule.id].get("companions", {}).get("trees", {}).items():
            print(f"  companion {name}: {tree_record['files']} file(s), sha256 {tree_record['sha256'][:12]} in every arm")
        if not rule.paired:
            for arm in rule.arm_names[1:]:
                listed = record["arm_listed"][arm]
                print(f"  {arm}: {arm_summary(arm, [f'skills/{path}' for path in record['arm_changes'][arm]])}"
                      + (f"; listed by description: {', '.join(listed)}" if listed else ""))
            continue
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
                for arm in rule.arm_names:
                    root = out / "arms" / rule.id / case.id / arm
                    check_manifest(root, case.kind)
                    harness("prepare", root / MANIFEST, "--split", "tune", "--runs-per-variant", "1", "--out", root / "tasks-all.jsonl")
                    count = with_skill_rows(root / "tasks-all.jsonl", root / "tasks.jsonl")
                    print(f"OK {rule.id}/{case.id}/{arm}: {count} with_skill row(s)")


def agent_env(agent, out, runner="host"):
    env = dict(os.environ)
    if runner == "sbx":
        version = subprocess.run(["sbx", "version"], capture_output=True, text=True, check=False)
        if version.returncode != 0:
            raise ScreenError("`sbx version` failed; --runner sbx needs Docker Sandboxes")
        print(f"sbx: {version.stdout.strip()}")
        return env
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


def host_wrapper(agent, out, target, entry, in_workspace):
    """The host runner's entry wrapper. host.py wrap links the skill tree and
    adds the invocation under the poteto-mode entry, runs the agent with its
    session kept and moves that session into the run's harvest slot, and for a
    workspace case materializes the checkout in the agent's cwd first and
    harvests its diff after."""
    wrapper = out / "entry" / (f"{agent}-workspace" if in_workspace else agent)
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(CANON / "host.py"), "wrap", "--agent", agent]
    if in_workspace:
        command.append("--workspace")
    if entry == ENTRY_SKILL:
        token, discovery = ENTRY_INVOCATION[agent]
        command += ["--token", token, "--discovery", discovery]
    command += ["--", str(target)]
    tools = CLAUDE_WORKSPACE_TOOLS if agent == "claude" and in_workspace else ()
    wrapper.write_text(f"#!/bin/sh\nexec {' '.join(map(shlex.quote, command))} \"$@\" {' '.join(map(shlex.quote, tools))}".rstrip() + "\n")
    wrapper.chmod(0o755)
    return wrapper


def sandbox_wrapper(agent, out, entry):
    """The entry wrapper for a workspace case under --runner sbx: sandbox.py
    wrap runs the agent inside its own sandbox (see sandbox.py)."""
    wrapper = out / "entry" / f"{agent}-sbx"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(CANON / "sandbox.py"), "wrap", "--agent", agent]
    if entry == ENTRY_SKILL:
        token, discovery = ENTRY_INVOCATION[agent]
        command += ["--token", token, "--discovery", discovery]
    wrapper.write_text(f"#!/bin/sh\nexec {' '.join(map(shlex.quote, command))} -- \"$@\"\n")
    wrapper.chmod(0o755)
    return wrapper


def refuse_effort(agent, effort):
    if effort and agent != "codex":
        raise ScreenError("--effort applies to --agent codex only; the screen passes Claude no effort setting")


def backend_args(agent, out, entry, in_workspace=False, runner="host", effort=None):
    """The harness flags that name the agent's command. effort pins Codex's
    reasoning effort with a -c override in the command itself: the harness runs
    Codex with --ignore-user-config, which skips config files but keeps -c, and
    sandbox.py's argv rewrite passes it through, so both runners get it."""
    refuse_effort(agent, effort)
    target = LAUNCHERS / ("claude-project-only" if agent == "claude" else "codex-project-only")
    if runner == "sbx":
        if not in_workspace:
            raise ScreenError("--runner sbx runs workspace cases only; a pasted-project case has no checkout to clone")
        target = sandbox_wrapper(agent, out, entry)
    elif in_workspace or entry == ENTRY_SKILL:
        target = host_wrapper(agent, out, target, entry, in_workspace)
    if agent == "claude":
        return ["--claude-bin", target]
    sandbox = "workspace-write" if in_workspace else "read-only"
    pin = f" -c {shlex.quote(f'model_reasoning_effort={effort}')}" if effort else ""
    return ["--codex-cmd", f"{shlex.quote(str(target))} exec --json --skip-git-repo-check --sandbox {sandbox}{pin}"]


TIMED_OUT_RC = 124


def last_message_missing(record):
    """True when the only thing the wrapper recorded against a slot is that
    its sandbox held no last message to copy out. Codex writes that file only
    when it finishes, so a run the harness timed out (GNU timeout exits 124)
    leaves none, while the tree and the diff harvested before the copy are
    sound. A crash, a clean exit that wrote no message, and any other copy
    failure are not this."""
    error = str(record.get("error") or "")
    return (record.get("agent_rc") == TIMED_OUT_RC
            and re.fullmatch(r'sbx cp \S+:/tmp/canon-last-message\.txt failed \(\d+\): .*not found in container\s*', error, re.DOTALL) is not None)


def slot_refusal(record, expected_tree):
    """Why a slot's workspace.json cannot be graded, or None. A mismatched tree
    and any other recorded error are told apart, because the trees of an
    errored slot usually match."""
    if record.get("tree") != expected_tree:
        return f"workspace tree {record.get('tree')} is not the built {expected_tree}"
    if record.get("error") and not last_message_missing(record):
        return f"the wrapper recorded an error: {record['error']}"
    return None


def file_harvest(work, expected_tree=None):
    """Move the numbered slots the wrapper filled, in task order, to each run's
    path under work/harvest, and refuse a workspace run whose checkout was not
    the tree the build recorded. A slot whose wrapper the harness killed on
    timeout still names its pinned session, so every slot's transcript is
    collected from here before any check can refuse the harvest (see host.py).
    A run a refusal interrupted left its earlier slots moved, so the slots
    still numbered fill the runs whose harvest dir does not exist yet."""
    harvest = work / "harvest"
    rows = [json.loads(line)["run_dir"] for line in (work / "tasks.jsonl").read_text().splitlines()]
    slots = sorted(harvest.glob("[0-9][0-9][0-9][0-9]")) if harvest.is_dir() else []
    for slot in slots:
        host.recover(slot)
    pending = [run_dir for run_dir in rows if not (harvest / run_dir).exists()]
    if len(slots) != len(pending):
        raise ScreenError(f"{work}: the wrapper filled {len(slots)} harvest slot(s) for {len(pending)} unharvested of {len(rows)} run(s)")
    for slot, run_dir in zip(slots, pending):
        if expected_tree:
            refusal = slot_refusal(json.loads((slot / "workspace.json").read_text()), expected_tree)
            if refusal:
                raise ScreenError(f"{work}/{run_dir}: {refusal}")
        destination = harvest / run_dir
        destination.parent.mkdir(parents=True, exist_ok=True)
        slot.rename(destination)


def select_cases(rules, case_ids):
    if not case_ids:
        return rules
    known = {case.id for rule in rules for case in rule.cases}
    unknown = sorted(set(case_ids) - known)
    if unknown:
        raise SystemExit(f"unknown case id(s): {', '.join(unknown)}")
    chosen = [dataclasses.replace(rule, cases=tuple(c for c in rule.cases if c.id in case_ids)) for rule in rules]
    return [rule for rule in chosen if rule.cases]


def log_error(out, context, exc):
    """Append exc's traceback to <out>/screen-error.log and say where it went
    on stdout and on stderr, so a caller that reads only one stream sees it."""
    out.mkdir(parents=True, exist_ok=True)
    with (out / ERROR_LOG).open("a", encoding="utf-8") as handle:
        handle.write(f"--- {time.strftime('%Y-%m-%dT%H:%M:%S')} {context}\n{''.join(traceback.format_exception(exc))}\n")
    message = f"screen: ERROR in {context}: {type(exc).__name__}: {exc} (traceback in {out / ERROR_LOG})"
    print(message, flush=True)
    print(message, file=sys.stderr, flush=True)


def refuse_leaks(work, case_build):
    """Refuse an arm whose run output holds credential material, apart from
    credential-shaped bytes the pinned checkout already holds."""
    known = workspace.checkout_tokens(case_build["workspace"]["checkout"]) if "workspace" in case_build else set()
    leaks = workspace.credential_findings(work, known)
    if leaks:
        raise ScreenError(f"{work}: credential material in the run output: "
                          + ", ".join(f"{path} ({kind})" for path, kind in leaks))


def run_arm(agent, out, rule, case, arm, case_build, backend, env, model, runs, timeout, entry="skill"):
    """Answer, grade, and judge one arm. A run through a wrapper (every
    workspace case, and every case under the poteto-mode entry) fills one
    harvest slot per run, which moves beside the run dir before the leak scan
    reads the run's output."""
    root = out / "arms" / rule.id / case.id / arm
    work = out / agent / rule.id / case.id / arm
    if work.exists():
        raise ScreenError(f"{work} exists; use a fresh --out so runs never mix")
    work.mkdir(parents=True)
    harness("prepare", root / MANIFEST, "--split", "tune", "--runs-per-variant", runs, "--out", work / "tasks-all.jsonl")
    with_skill_rows(work / "tasks-all.jsonl", work / "tasks.jsonl")
    wrapped = "workspace" in case_build or entry == ENTRY_SKILL
    run_env = {**env, "CANON_HARVEST": str(work / "harvest")} if wrapped else env
    if "workspace" in case_build:
        run_env.update(CANON_WORKSPACE=str(root / "workspace"), CANON_TIMEOUT_S=str(timeout or case_build["timeout_s"]))
    harness("run-agent", "--agent", agent, "--model", model, *backend,
            "--tasks", work / "tasks.jsonl", "--runs", work / "runs",
            "--timeout", timeout or case_build["timeout_s"], env=run_env)
    if wrapped:
        file_harvest(work, case_build["workspace"]["tree"] if "workspace" in case_build else None)
    refuse_leaks(work, case_build)
    harness("grade", root / MANIFEST, "--runs", work / "runs", "--variant", "with_skill",
            "--allow-scripts", "--out", work / "grade.json")
    if judged(case_build):
        judge_arm(out, agent, rule, case, arm)


def run(agent, out, rules, model, runs, timeout, entry="skill", runner="host", only_arms=(), effort=None):
    """Answer, grade, and judge every arm of every case. An arm that fails is
    logged with its traceback and skipped, so the other arms still run; the
    run then exits nonzero naming each failed arm. A run limited to some
    arms writes no comparison, since the pairs it would print are incomplete."""
    unknown = sorted(set(only_arms) - {arm for rule in rules for arm in rule.arm_names})
    if unknown:
        raise SystemExit(f"unknown arm(s): {', '.join(unknown)}")
    refuse_effort(agent, effort)
    env = agent_env(agent, out, runner)
    if effort:
        print(f"{agent}: reasoning effort {effort}")
    built = build(out, rules, entry)
    failed = []
    for rule in rules:
        for case in rule.cases:
            case_build = built[rule.id]["cases"][case.id]
            try:
                backend = backend_args(agent, out, entry, "workspace" in case_build, runner, effort)
                for arm in rule.arm_names:
                    check_manifest(out / "arms" / rule.id / case.id / arm, case.kind)
            except Exception as exc:  # noqa: BLE001
                log_error(out, f"{agent}/{rule.id}/{case.id}", exc)
                failed.append(f"{rule.id}/{case.id}")
                continue
            for arm in rule.arm_names:
                if only_arms and arm not in only_arms:
                    continue
                try:
                    run_arm(agent, out, rule, case, arm, case_build, backend, env, model, runs, timeout, entry)
                except Exception as exc:  # noqa: BLE001
                    log_error(out, f"{agent}/{rule.id}/{case.id}/{arm}", exc)
                    failed.append(f"{rule.id}/{case.id}/{arm}")
    if only_arms and any(set(rule.arm_names) - set(only_arms) for rule in rules):
        print(f"ran only {', '.join(only_arms)}; run the other arms into {out}, then compare --out {out}")
    else:
        compare(out)
    if failed:
        raise ScreenError(f"{len(failed)} arm(s) or case(s) failed: {', '.join(failed)}; see {out / ERROR_LOG}, then `screen.py regrade --out {out}`")


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
    both its skill directory and its path inside that skill (cd then cat). The
    harness records Claude's Skill tool as a skill_load whose input is the bare
    skill name, so that counts as a read of the skill's SKILL.md when the tree
    has one."""
    completed = [event for event in events if event.get("status") == "completed" and event.get("type") in READ_EVENTS]
    inputs = [str(event.get("input_summary") or "") for event in completed]
    seen = set()
    for event in completed:
        loaded = LOADED_SKILL.match(str(event.get("input_summary") or "").strip()) if event.get("type") == "skill_load" else None
        if loaded and f"{loaded.group(1)}/SKILL.md" in tree_files:
            seen.add(f"{loaded.group(1)}/SKILL.md")
    for path in tree_files:
        skill, _, inner = path.partition("/")
        segment = re.compile(rf"(^|[/\s]){re.escape(skill)}($|[/\s])")
        if any(path in text or (segment.search(text) and inner in text) for text in inputs):
            seen.add(path)
    return sorted(seen)


def auto_invocable(tree, path):
    """Whether every run offers the agent the SKILL.md at path by its
    description. Its skill's agents/openai.yaml must not turn off implicit
    invocation, which Codex reads. Claude lists managed pstack skills with
    that policy by name only (workspace.name_only_settings). Its
    frontmatter must not set disable-model-invocation, which Claude Code still
    honors in a tree that carries it, as every pinned skills_at tree does."""
    if skill_listing.disables_implicit_invocation(tree.get(f"{path.rsplit('/', 1)[0]}/{workspace.INVOCATION_POLICY}", b"").decode("utf-8")):
        return False
    frontmatter = FRONTMATTER.match(tree[path])
    return not (frontmatter and re.search(rb"^disable-model-invocation:\s*true\s*$", frontmatter.group(0), re.MULTILINE))


def arm_listed(current, trees):
    """{arm: [path, ...]}: the SKILL.md files each arm adds beside current that
    auto_invocable says the agent is offered in every run of that arm. Whether
    a run loads such a skill is its choice, and exposure reads that from the
    same read field as any file."""
    return {arm: sorted(path for path in tree if path not in current and path.endswith("/SKILL.md") and path.count("/") == 1 and auto_invocable(tree, path))
            for arm, tree in trees}


def harvest_dir(run_base):
    """<work>/runs/<run> maps to <work>/harvest/<run>, where the entry wrapper
    of either runner leaves the agent's session transcripts."""
    run_base = Path(run_base)
    runs = next((parent for parent in run_base.parents if parent.name == "runs"), None)
    return runs.parent / "harvest" / run_base.relative_to(runs) if runs else None


def json_lines(path):
    for line in path.read_text(errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield record


def claude_registered(trace):
    """True when the first init event lists the entry among its skills or
    slash commands, so the /poteto-mode token could expand."""
    init = next((record for record in json_lines(trace) if record.get("type") == "system" and record.get("subtype") == "init"), {}) \
        if trace.is_file() else {}
    return ENTRY_SKILL in (init.get("skills") or ()) or ENTRY_SKILL in (init.get("slash_commands") or ())


def claude_expanded(texts):
    return any(f"<command-name>/{ENTRY_SKILL}</command-name>" in text for text in texts)


def codex_injected(rollout):
    """True when a user message in a Codex rollout carries the injected entry
    skill, which Codex sends as <skill><name>poteto-mode</name>..."""
    for record in json_lines(rollout):
        payload = record.get("payload") or {}
        if payload.get("type") == "message" and payload.get("role") == "user":
            if any(str(item.get("text", "")).startswith(f"<skill>\n<name>{ENTRY_SKILL}</name>")
                   for item in payload.get("content") or () if isinstance(item, dict)):
                return True
    return False


def entry_state(agent, run_base, events, read):
    """How a run's trace shows the entry skill reached the agent. "injected"
    when the invocation expanded it, "read" when the agent loaded its SKILL.md
    itself, "not registered" when Claude's init event does not list it, and
    "not observed" otherwise. Claude's -p stream never shows the expansion, but
    the session transcript the wrapper harvests does. Codex has no init
    listing, and only its rollout, which the wrapper also harvests, records
    the injection, so a Codex run without a rollout counts only a read."""
    run_base = Path(run_base)
    trace = run_base / "trace.jsonl"
    transcripts = (harvest_dir(run_base) or run_base) / "transcripts"
    if agent == "claude":
        if not claude_registered(trace):
            return "not registered"
        texts = [path.read_text(errors="replace") for path in (trace, *transcripts.glob("claude/*/*.jsonl")) if path.is_file()]
        if claude_expanded(texts):
            return "injected"
        if any(event.get("status") == "completed" and event.get("name") == "Skill"
               and str(event.get("input_summary") or "").strip("'\"") == ENTRY_SKILL for event in events):
            return "injected"
    elif any(codex_injected(path) for path in transcripts.glob("codex/sessions/**/rollout-*.jsonl")):
        return "injected"
    return "read" if f"{ENTRY_SKILL}/SKILL.md" in read else "not observed"


ENTRY_SEEN = ("injected", "read")


def exposure(result, tree_files, agent):
    base = Path(result.get("run_base", ""))
    events_path = base / "events.json"
    events = json.loads(events_path.read_text()).get("events", []) if events_path.is_file() else []
    read = skill_files_read(events, tree_files)
    return {"read": read, "entry": entry_state(agent, base, events, read)}


def classify(baseline, treatment, target, entry="skill", listed=()):
    """Name what a pair shows. target is the file, or the set of files, that
    differ between the two arms, and listed is the SKILL.md files the treatment
    arm offers by description in every run. The treatment is exposed when it
    read or loaded one of the targets, or poteto-mode/SKILL.md is a target and
    the treatment's trace shows the entry injected, or a target is a listed
    skill. Under the poteto-mode entry a pair is unexposed unless both arms'
    traces show the entry reached the agent, since a run without it tested no
    pstack. An unexposed pair says nothing about the change, so it is not a
    tie, and a listed skill the run never loaded is a tie or a reversal, the
    outcome a placement screen measures."""
    if baseline is None or treatment is None or "INVALID" in (baseline["verdict"], treatment["verdict"]):
        return "invalid"
    if entry == ENTRY_SKILL and not all(arm["exposure"]["entry"] in ENTRY_SEEN for arm in (baseline, treatment)):
        return "unexposed"
    targets = {target} if isinstance(target, str) else set(target)
    injected = treatment["exposure"]["entry"] == "injected"
    exposed = reached(targets, treatment["exposure"]["read"], injected) or bool(targets & set(listed))
    if not exposed:
        return "unexposed"
    return {
        ("FAIL", "PASS"): "separates",
        ("PASS", "FAIL"): "reverses",
        ("PASS", "PASS"): "tie-pass",
        ("FAIL", "FAIL"): "tie-fail",
    }[(baseline["verdict"], treatment["verdict"])]


def reached(targets, read, injected):
    """Whether a run's changed text reached the agent: it read or loaded one of
    the target files, or the entry injected poteto-mode/SKILL.md among them."""
    return bool(set(targets) & set(read)) or (f"{ENTRY_SKILL}/SKILL.md" in targets and injected)


def comparisons(arms):
    """(baseline, treatment) arm pairs: each arm against the first, then each
    later arm against each earlier one. The stub arm is always the baseline,
    so a pair with it separates when guidance turns a fail into a pass, and is
    exposed when the guided arm read a file the stub lacks."""
    treated = arms[1:]
    pairs = [(arms[0], arm) for arm in treated] + [(baseline, arm) for index, baseline in enumerate(treated) for arm in treated[index + 1:]]
    return [(treatment, baseline) if treatment == STUB else (baseline, treatment) for baseline, treatment in pairs]


def differing_files(case_root, build_info, baseline, treatment):
    """Files whose bytes differ between two built arms of one case."""
    changes = build_info["arm_changes"]

    def read(arm, path):
        file = case_root / arm / build_info["tree_dir"] / path
        return file.read_bytes() if file.is_file() else None

    return sorted(path for path in set(changes[baseline]) | set(changes[treatment]) if read(baseline, path) != read(treatment, path))


def rule_verdict(outcomes):
    """outcomes: [(case id, case kind, pair outcome)] for one rule, agent, and run,
    with outcome "missing" for a built case that has no grade. Returns (verdict,
    reasons). A near-miss that went ungraded, never ran, or never read the
    change cannot show it held, so it blocks the verdict like a reversal does."""
    reasons = [f"{case} {outcome}" for case, kind, outcome in outcomes
               if (kind == "positive" and outcome != "separates") or (kind == "near-miss" and outcome in ("reverses", "invalid", "missing", "unexposed"))]
    if not any(kind == "positive" for _, kind, _ in outcomes):
        reasons.append("no positive case ran")
    return ("separates" if not reasons else "not-separated"), reasons


def regrade_run(check, rule, case, run_base):
    """(verdict, reasons) from the oracle on a run's harvested diff and its
    answer, empty when output.md is missing, or on the pasted project as the
    harness graded it. None when a workspace case harvested no diff."""
    try:
        project = check.load_workspace(rule, case, run_base) or check.load_project(rule, case)
    except check.OracleError:
        return None
    output = Path(run_base) / "output.md"
    answer = output.read_text(encoding="utf-8") if output.is_file() else ""
    try:
        failures = check.load_oracle(rule)[case](answer, project)
    except check.OracleError as exc:
        failures = [str(exc)]
    return ("FAIL" if failures else "PASS"), "; ".join(failures)


def work_dirs(out, *markers):
    """Each <agent>/<rule>/<case>/<arm> work dir under out that holds one of markers."""
    found = {path.parent for marker in markers for path in out.glob(f"*/*/*/*/{marker}")}
    return sorted(path for path in found if path.relative_to(out).parts[0] != "arms")


def run_bases(work):
    """[(run number, run dir)] for every with_skill task the work dir prepared."""
    rows = [json.loads(line) for line in (work / "tasks.jsonl").read_text().splitlines() if line.strip()]
    return [(row["run_number"], work / "runs" / row["run_dir"]) for row in rows]


def harness_results(work):
    """grade.json's results, or, for an arm that stopped before grading, one
    ungraded result per prepared run."""
    grade = work / "grade.json"
    if grade.is_file():
        return json.loads(grade.read_text())["results"]
    return [{"run_number": number, "run_base": str(base), "missing_output": True} for number, base in run_bases(work)]


def map_slots(work, tree):
    if (work / "harvest").is_dir() and any((work / "harvest").glob("[0-9][0-9][0-9][0-9]")):
        file_harvest(work, tree)


def regrade(out):
    """Grade every run of every workspace case again from its diff, into
    regrade.json beside grade.json, then compare. The oracle and checkout are
    the arm's grader copy, as the harness used. A run the harness called
    INVALID, or never graded, is marked graded_from_diff. An arm that stopped
    after the agent ran gets its numbered harvest slots mapped first."""
    for work in work_dirs(out, "tasks.jsonl", "grade.json"):
        agent, rule, case, arm = work.relative_to(out).parts
        build_info = json.loads((out / "arms" / rule / "build.json").read_text())
        if "workspace" not in build_info["cases"][case]:
            continue
        try:
            refuse_leaks(work, build_info["cases"][case])
            map_slots(work, build_info["cases"][case]["workspace"]["tree"])
        except ScreenError as exc:
            log_error(out, f"regrade {agent}/{rule}/{case}/{arm}", exc)
            continue
        check = load_check(out / "arms" / rule / case / arm / "rules")
        rows = []
        for result in harness_results(work):
            regraded = regrade_run(check, rule, case, result["run_base"])
            if regraded is None:
                continue
            rows.append({"run": result.get("run_number"), "verdict": regraded[0], "reasons": regraded[1],
                         "graded_from_diff": verdict(result)[0] == "INVALID", "run_base": result["run_base"]})
        (work / "regrade.json").write_text(json.dumps({"results": rows}, indent=2) + "\n")
    compare(out)


def review_pr(case):
    """{"title", "body", "diff"} of a review case's PR, as the judge sees it."""
    spec = case_spec(case)
    return {"title": spec.review["title"], "body": spec.overlay[spec.review["body_file"]].decode(errors="replace"),
            "diff": spec.review["patch"].decode(errors="replace")}


def case_subject(case):
    """The judge's fixed side. A review's is its PR. A document's is the
    request, exactly the text the agent read, project listing included, so the
    judge and the agent share one source."""
    if case.review:
        return review_pr(case)
    return {"request": render_prompt(case)}


def delivered(case, answer, workspace=None):
    """The text the judge grades for one run or one labeled sample: the review
    itself, or the document cut from the final message or the workspace."""
    if case.document:
        return shared.document_text(answer, case.document, workspace)
    return answer


def absent(case):
    """The error a judged run records when it delivered nothing to judge."""
    if not case.document:
        return "no review: output.md is missing or empty"
    if "message" in case.document:
        return "no document: output.md is missing or empty"
    return f"no document: {case.document['file']} not in the " + ("workspace" if case.workspace else "final message")


def secret_words(rule, case):
    """Words the judge never sees: the rule id, the owning rule, every path the
    rule's arms change, and each path's tail inside its skill, such as
    playbooks/premortem.md. Bare words such as a skill's name stay, since a
    document about the change may need them."""
    if rule.paired:
        paths = {rule.target}
    else:
        paths = {path for _, patch in rule.arm_patches if patch for path in patch_paths(patch)[1]}
    tails = {path.split("/", 1)[1] for path in paths if "/" in path.split("/", 1)[1]}
    return (rule.id, case.owner, *sorted(paths | tails))


def judge_answer(case, subject, rubric, backend, model, answer, written, secrets):
    """One judge record for one delivered text, the only place either frame is judged."""
    spec = case_spec(case) if case.workspace else None
    return review.judge(backend, model, case.kind, rubric, subject, answer, written, secrets,
                        spec.repo if spec else None, spec.commit if spec else None, frame=case.frame)


def labeled_samples(case):
    """{name: (label, text)} of a judged case's calibration samples."""
    return {name: (label, (case.root / "samples" / name).read_text()) for name, label in check_labels(case.root, case.kind).items()}


def case_calibration(case, backend, model, rubric, subject):
    path = review.calibration_path(case.owner, case.id, backend, model)
    record = json.loads(path.read_text()) if path.is_file() else None
    return review.calibration_status(record, review.calibration_key(backend, model, case.kind, rubric, subject, labeled_samples(case), case.frame))


def written_by(check, run_base):
    """The diff the reviewer left in the checkout, or "" when none was harvested."""
    try:
        return check.workspace_diff(run_base)
    except check.OracleError:
        return ""


def judge_arm(out, agent, rule, case, arm, judge=None):
    """Judge every run of one judged arm into <work>/judge.json. The judge is
    the other family unless judge names (backend, model). A run that delivered
    nothing to judge records verdict None with the reason, which compare
    reads as INVALID."""
    work = out / agent / rule.id / case.id / arm
    backend, model = judge or review.JUDGE_FOR[agent]
    rubric, subject = (case.root / "rubric.md").read_text(), case_subject(case)
    calibrated, reason = case_calibration(case, backend, model, rubric, subject)
    check = load_check(out / "arms" / rule.id / case.id / arm / "rules")
    secrets = secret_words(rule, case)
    rows = []
    for number, run_base in run_bases(work):
        output = run_base / "output.md"
        answer = output.read_text(encoding="utf-8", errors="replace") if output.is_file() else ""
        written = written_by(check, run_base) if case.review else ""
        precheck = regrade_run(check, rule.id, case.id, run_base) or ("FAIL", "no harvested workspace")
        try:
            cut_from_workspace = case.document and "file" in case.document
            text = delivered(case, answer, check.load_workspace(rule.id, case.id, run_base) if cut_from_workspace else None)
        except check.OracleError:
            text = ""
        if text.strip() or written.strip():
            record = judge_answer(case, subject, rubric, backend, model, text, written, secrets)
        else:
            record = {"backend": backend, "model": model, "verdict": None, "error": absent(case)}
        combined = review.combine(case.kind, record["verdict"], precheck[0] == "PASS") if record["verdict"] else "UNJUDGED"
        record.update(run=number, precheck=precheck[0], precheck_failures=precheck[1], combined=combined,
                      calibrated=calibrated, calibration=reason)
        rows.append(record)
        print(f"judge {agent}/{rule.id}/{case.id}/{arm} run-{number}: {combined} (judge {record['verdict']}, precheck {precheck[0]}"
              f"{'' if calibrated else ', UNCALIBRATED'}){' ' + record['error'] if record.get('error') else ''}", flush=True)
    (work / "judge.json").write_text(json.dumps({"judge": {"backend": backend, "model": model}, "results": rows}, indent=2) + "\n")
    return rows


def judge_all(out, judge=None):
    rules = {}
    for work in work_dirs(out, "tasks.jsonl"):
        agent, rule_id, case_id, arm = work.relative_to(out).parts
        build_info = json.loads((out / "arms" / rule_id / "build.json").read_text())
        if not judged(build_info["cases"][case_id]):
            continue
        rule = rules.setdefault(rule_id, load_rule(rule_id))
        case = next(case for case in rule.cases if case.id == case_id)
        judge_arm(out, agent, rule, case, arm, judge)
    compare(out)


def sample_workspace(case, checkout, name):
    """The Workspace a labeled sample of a workspace case is graded in: the
    reference checkout with the sample's sibling .diff, when the case judges a
    file, so the document is cut from the diff as a run's would be."""
    diff = case.root / "samples" / Path(name).with_suffix(".diff")
    return shared.Workspace(checkout, diff.read_text() if case.document and "file" in case.document and diff.is_file() else "")


def calibrate(rules, judges):
    """Judge every labeled sample of every judged case of rules with each
    judge, store the agreement under the cache, and print it per label. A
    case whose judge disagrees with any label stays uncalibrated, and its
    run results say so. Each sample is delivered through the same cut a run
    goes through, so the judge sees a sample the way it sees a run."""
    check = load_check()
    reviewed = [(rule, case) for rule in rules for case in rule.cases if case.frame]
    if not reviewed:
        raise ScreenError(f"no review or document cases in {', '.join(rule.id for rule in rules)}")
    summary = []
    for rule, case in reviewed:
        rubric, subject = (case.root / "rubric.md").read_text(), case_subject(case)
        checkout = workspace.reference_checkout(case_spec(case))[0] if case.workspace else None
        labeled, secrets = labeled_samples(case), secret_words(rule, case)
        for backend, model in judges:
            samples = {}
            for name, (label, answer) in sorted(labeled.items()):
                graded_in = sample_workspace(case, checkout, name) if checkout else None
                record = judge_answer(case, subject, rubric, backend, model, delivered(case, answer, graded_in), "", secrets)
                failures = check.grade(case.owner, case.id, text=answer, workspace=graded_in)
                samples[name] = {"label": label, "verdict": record["verdict"], "evidence": record.get("evidence"),
                                 "error": record.get("error"), "precheck": "FAIL" if failures else "PASS",
                                 "combined": review.combine(case.kind, record["verdict"], not failures) if record["verdict"] else "UNJUDGED",
                                 "prompt_sha256": record["prompt_sha256"]}
            table, agreed = review.agreement(samples)
            result = {"rule": case.owner, "case": case.id, "kind": case.kind, "backend": backend, "model": model,
                      "template": review.FRAMES[case.frame].version,
                      "key": review.calibration_key(backend, model, case.kind, rubric, subject, labeled, case.frame),
                      "samples": samples, "agreement": table, "calibrated": agreed}
            path = review.calibration_path(case.owner, case.id, backend, model)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, indent=2) + "\n")
            summary.append(result)
            print(f"{case.owner}/{case.id} {case.kind} judge {backend}:{model}: {'CALIBRATED' if agreed else 'UNCALIBRATED'}")
            for label, (hits, total) in sorted(table.items()):
                print(f"    {label:11} {hits}/{total} agree")
            for name, sample in samples.items():
                if sample["verdict"] != sample["label"] or sample["precheck"] == "FAIL":
                    print(f"    {name}: labeled {sample['label']}, judged {sample['verdict']}, precheck {sample['precheck']}"
                          + (f", error {sample['error']}" if sample["error"] else ""))
            print(f"    wrote {path}")
    return summary


def review_row(record, kind):
    """(verdict for the pair, reasons, review fields) of one judged run. The
    combined verdict passes when it is the case's passing verdict."""
    if record is None:
        return "INVALID", "not judged", {"combined": "UNJUDGED", "verdict": None, "precheck": None, "calibrated": False, "calibration": "not judged"}
    fields = {key: record.get(key) for key in ("combined", "verdict", "evidence", "precheck", "calibrated", "calibration", "label", "error")}
    if record["combined"] == "UNJUDGED":
        return "INVALID", f"not judged: {record.get('error')}", fields
    return ("PASS" if record["combined"] == review.PASSING[kind] else "FAIL"), "", fields


def compare(out):
    if not any(out.glob("*/*/*/*/grade.json")) and any(out.glob("*/*/*/grade.json")):
        raise ScreenError(f"{out} was made before rules had cases; its compare.json is final and plan reads it")
    table = []
    for work in work_dirs(out, "grade.json", "regrade.json"):
        agent, rule, case, arm = work.relative_to(out).parts
        grade = work / "grade.json"
        build_info = json.loads((out / "arms" / rule / "build.json").read_text())
        tree_root = out / "arms" / rule / case / arm / build_info["tree_dir"]
        tree_files = sorted(path.relative_to(tree_root).as_posix() for path in tree_root.rglob("*.md"))
        companions = set(build_info.get("companions", {}).get("trees", {}))
        regraded_path = grade.with_name("regrade.json")
        regraded = {row["run"]: row for row in json.loads(regraded_path.read_text())["results"]} if regraded_path.is_file() else {}
        reviewed = judged(build_info["cases"][case])
        verdicts = {}
        if reviewed and (work / "judge.json").is_file():
            verdicts = {row["run"]: row for row in json.loads((work / "judge.json").read_text())["results"]}
        results = json.loads(grade.read_text())["results"] if grade.is_file() else [
            {"run_number": row["run"], "run_base": row.get("run_base", ""), "missing_output": True} for row in regraded.values()]
        for result in results:
            status, reasons = verdict(result)
            seen = exposure(result, tree_files, agent)
            if companions:
                seen["companions_read"] = sorted({path.split("/", 1)[0] for path in seen["read"]} & companions)
            row = {
                "agent": agent, "rule": rule, "case": case, "kind": build_info["cases"][case]["kind"], "arm": arm,
                "run": result.get("run_number"), "entry": build_info["entry"], "target": build_info["target"],
                "verdict": status, "reasons": reasons, "exposure": seen,
            }
            again = regraded.get(result.get("run_number"))
            if again:
                row.update(verdict=again["verdict"], reasons=again["reasons"])
                if again["graded_from_diff"]:
                    row["graded_from_diff"] = True
            if not grade.is_file():
                row["ungraded"] = True
            if reviewed:
                precheck = row["verdict"]
                row["verdict"], row["reasons"], row["review"] = review_row(verdicts.get(result.get("run_number")), row["kind"])
                row["review"]["precheck"] = row["review"]["precheck"] or precheck
            table.append(row)
    pairs = {}
    for row in table:
        pairs.setdefault((row["agent"], row["rule"], row["run"], row["case"]), {})[row["arm"]] = row
    # grouped: (agent, rule, run, (treatment, baseline) of a pair with current, or None for a pair rule) -> case outcomes
    summary, grouped = [], {}
    for (agent, rule, run_number, case), arms in sorted(pairs.items(), key=lambda item: tuple(map(str, item[0]))):
        first = next(iter(arms.values()))
        build_info = json.loads((out / "arms" / rule / "build.json").read_text())
        names = build_info.get("arms", list(ARMS))
        paired = build_info.get("patch_kind") != "arms"
        outcomes = []
        for baseline, treatment in comparisons(names):
            target = first["target"] if paired else differing_files(out / "arms" / rule / case, build_info, baseline, treatment)
            outcome = classify(arms.get(baseline), arms.get(treatment), target, first["entry"], build_info.get("arm_listed", {}).get(treatment, ()))
            pair = {"agent": agent, "rule": rule, "case": case, "kind": first["kind"], "run": run_number, "target": target, "outcome": outcome}
            if not paired:
                pair.update(baseline=baseline, treatment=treatment)
            summary.append(pair)
            outcomes.append(f"    {treatment} vs {baseline}: {outcome.upper()}")
            if names[0] in (baseline, treatment):
                grouped.setdefault((agent, rule, run_number, None if paired else (treatment, baseline)), []).append((case, first["kind"], outcome))
        cells = [f"{arm}={arms[arm]['verdict'] if arm in arms else 'MISSING'}" for arm in names]
        print(f"{agent:6} {rule:26} {case:18} {first['kind']:9} run-{run_number}  " + "  ".join(cells) + (f"  {summary[-1]['outcome'].upper()}" if paired else ""))
        for arm in names:
            row = arms.get(arm)
            if row is None:
                continue
            seen = row["exposure"]["read"]
            if paired:
                target_state = f"{first['target']} {'read' if first['target'] in seen else 'NOT READ'}; "
            else:
                owned = build_info["arm_changes"][arm]
                target_state = f"changed {arm_summary(arm, owned)} ({len(set(owned) & set(seen))} of {len(owned)} read); " if owned else ""
            companion_state = ""
            if "companions_read" in row["exposure"]:
                companion_state = f"; companion {', '.join(row['exposure']['companions_read']) or 'none'} read"
            print(f"    {arm}: {target_state}entry {row['exposure']['entry']}{companion_state}; read {len(seen)} skill file(s): {', '.join(seen) or 'none'}")
            if row.get("graded_from_diff"):
                print(f"    {arm}: graded from the diff; the harness found no gradable answer")
            if row.get("ungraded"):
                print(f"    {arm}: no grade.json; the run stopped before the harness graded it")
            if "review" in row:
                state = row["review"]
                print(f"    {arm}: review {state['combined']} (judge {state['verdict']}, precheck {state['precheck']}"
                      f"{'' if state['calibrated'] else ', uncalibrated: ' + str(state['calibration'])})")
            if row["reasons"]:
                print(f"    {arm}: {row['reasons']}")
        if not paired:
            print("\n".join(outcomes))
    for (agent, rule, run_number, _), outcomes in grouped.items():
        ran = {case for case, _, _ in outcomes}
        built_cases = json.loads((out / "arms" / rule / "build.json").read_text())["cases"]
        outcomes += [(case, spec["kind"], "missing") for case, spec in built_cases.items() if case not in ran]
    rules = []
    # Sort on agent, rule, and run only, so a rule's arms keep their order.
    for (agent, rule, run_number, pair), outcomes in sorted(grouped.items(), key=lambda item: tuple(map(str, item[0][:3]))):
        result, reasons = rule_verdict(outcomes)
        verdict_row = {"agent": agent, "rule": rule, "run": run_number, "verdict": result, "reasons": reasons}
        label = "rule"
        if pair is not None:
            verdict_row["arm"] = next(arm for arm in pair if arm != "current")
            label = f"rule {pair[0]} vs {pair[1]}"
        uncalibrated = any(not row["review"]["calibrated"] for row in table
                           if "review" in row and (row["agent"], row["rule"], row["run"]) == (agent, rule, run_number))
        if uncalibrated:
            verdict_row["uncalibrated"] = True
        rules.append(verdict_row)
        print(f"{agent:6} {rule:26} {label} run-{run_number}  {result.upper()}" + (f"  ({'; '.join(reasons)})" if reasons else "")
              + ("  [judge uncalibrated]" if uncalibrated else ""))
    arm_reach = []
    for (agent, rule, arm) in sorted({(row["agent"], row["rule"], row["arm"]) for row in table}):
        build_info = json.loads((out / "arms" / rule / "build.json").read_text())
        if build_info.get("patch_kind") == "arms":
            changed = build_info["arm_changes"][arm]
        else:
            changed = [build_info["target"]] if arm == "amended" else []
        if not changed:
            continue
        rows = [row for row in table if (row["agent"], row["rule"], row["arm"]) == (agent, rule, arm)]
        count = sum(reached(changed, row["exposure"]["read"], row["exposure"]["entry"] == "injected") for row in rows)
        listed = build_info.get("arm_listed", {}).get(arm, [])
        arm_reach.append({"agent": agent, "rule": rule, "arm": arm, "changed_text_reached": count, "runs": len(rows), "listed": listed})
        print(f"{agent:6} {rule:26} arm {arm}: changed text reached {count}/{len(rows)} run(s)" + (f"; listed by description: {', '.join(listed)}" if listed else ""))
    review_scores = []
    for (agent, rule, arm) in sorted({(row["agent"], row["rule"], row["arm"]) for row in table if "review" in row}):
        rows = [row for row in table if "review" in row and (row["agent"], row["rule"], row["arm"]) == (agent, rule, arm)]
        score = {"agent": agent, "rule": rule, "arm": arm, **review.scores(rows)}
        review_scores.append(score)
        print(f"{agent:6} {rule:26} review {arm}: " + score_line(score))
    (out / "compare.json").write_text(json.dumps({"pairs": summary, "rules": rules, "runs": table, "arms": arm_reach, "review_scores": review_scores}, indent=2) + "\n")
    print(f"wrote {out / 'compare.json'}")


def score_line(score):
    def share(key):
        cell = score[key]
        return f"{cell['count']}/{cell['of']}" + (f" ({cell['rate']:.2f})" if cell["rate"] is not None else "")

    return (f"recall FOUND {share('recall_found')}, FOUND+PARTIAL {share('recall_found_or_partial')}; "
            f"false alarms {share('false_alarm_rate')}; precheck {share('precheck_pass')}; "
            f"{score['unjudged']} unjudged, {score['uncalibrated']} uncalibrated")


def out_dirs(roots):
    for root in roots:
        if (root / "compare.json").is_file():
            yield root
        elif root.is_dir():
            yield from sorted(path for path in root.iterdir() if (path / "compare.json").is_file())


def arm_file(out, rule_id, case_id, arm, build_info, target):
    arm_root = out / "arms" / rule_id / arm if "cases" not in build_info else out / "arms" / rule_id / case_id / arm
    path = arm_root / build_info["tree_dir"] / target
    return path.read_bytes() if path.is_file() else None


def past_runs(roots, rules, trees):
    """{(rule, case): ["agent/entry outcome", ...]} from finished --out dirs. A run
    whose changed files differ from today's text in any arm is marked as run
    against older text."""
    runs = {}
    for out in out_dirs(roots):
        for pair in json.loads((out / "compare.json").read_text())["pairs"]:
            rule = rules.get(pair["rule"])
            case_id = pair.get("case") or LEGACY_CASES.get(pair["rule"])
            build_path = out / "arms" / pair["rule"] / "build.json"
            if rule is None or not build_path.is_file():
                continue
            build_info = json.loads(build_path.read_text())
            files = sorted({path for changed in build_info.get("arm_changes", {}).values() for path in changed}) or [rule.target]
            fresh = build_info["target"] == rule.target and all(
                arm_file(out, rule.id, case_id, arm, build_info, path) == trees[rule.id].get(arm, {}).get(path)
                for arm in build_info.get("arms", ARMS) for path in files
            )
            compared = f"{pair['treatment']} vs {pair['baseline']} " if "treatment" in pair else ""
            label = f"{pair['agent']}/{build_info['entry']} {compared}{pair['outcome']}" + ("" if fresh else " (older text)")
            runs.setdefault((rule.id, case_id), []).append(label)
    return runs


def plan(roots):
    rules = {rule.id: rule for rule in load_rules()}
    trees, changes = {}, {}
    for rule in rules.values():
        trees[rule.id] = {}
        try:
            trees[rule.id] = {"current": rule_tree(rule)}
            trees[rule.id] = dict(arm_trees(rule, trees[rule.id]["current"]))
            changes[rule.id] = single_change(trees[rule.id]["current"], trees[rule.id]["amended"]) if rule.paired else None
        except ScreenError as exc:
            changes[rule.id] = exc
    runs = past_runs(roots, rules, trees)
    for rule in rules.values():
        change = changes[rule.id]
        if isinstance(change, ScreenError):
            kind = f"BROKEN: {change}"
        else:
            kind = change.kind if rule.paired else f"arms {', '.join(rule.arm_names)}"
        print(f"{rule.id}  [{rule.source}]  skills/{rule.target}  {kind}" + (f"  companions {', '.join(rule.companions)}" if rule.companions else ""))
        if not rule.paired and not isinstance(change, ScreenError):
            for arm in rule.arm_names[1:]:
                print(f"  arm {arm}: {arm_summary(arm, changed_paths(trees[rule.id]['current'], trees[rule.id][arm]))}")
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
    p.add_argument("--effort", help="the lead's reasoning effort, e.g. high or xhigh; --agent codex only, on either runner")
    p.add_argument("--runs", type=int, default=1, help="paired repetitions per case (default 1)")
    p.add_argument("--timeout", type=int, help="seconds per answer; a workspace case defaults to its timeout_s, else 1800; "
                   "other cases to 900 under the poteto-mode entry, else their timeout_s")
    p.add_argument("--entry", choices=ENTRIES, default="skill")
    p.add_argument("--case", action="append", default=[], help="run only these case ids (repeatable)")
    p.add_argument("--arm", action="append", default=[], help="run only these arms (repeatable), e.g. --arm current; compare waits for the rest")
    p.add_argument("--runner", choices=("host", "sbx"), default="host",
                   help="host runs the agent CLI on this machine; sbx runs each workspace answer in its own Docker sandbox")
    p.add_argument("rules", nargs="*")
    p = sub.add_parser("compare")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("regrade")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("judge")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--judge", type=judge_choice, help="BACKEND:MODEL for every review; default the other family's judge per agent")
    p = sub.add_parser("calibrate")
    p.add_argument("--judge", type=judge_choice, action="append",
                   help=f"BACKEND:MODEL, repeatable (default {', '.join(':'.join(pair) for pair in sorted(set(review.JUDGE_FOR.values())))})")
    p.add_argument("rules", nargs="+")
    args = parser.parse_args(argv)
    out = args.out.resolve() if getattr(args, "out", None) else None
    try:
        if args.command == "plan":
            plan(args.runs_root or [DEFAULT_RUNS_ROOT])
        elif args.command == "build":
            build(args.out.resolve(), load_rules(args.rules), args.entry)
        elif args.command == "audit":
            audit(load_rules(args.rules), args.entry)
        elif args.command == "run":
            run(args.agent, args.out.resolve(), select_cases(load_rules(args.rules), args.case), args.model or DEFAULT_MODELS[args.agent], args.runs, args.timeout, args.entry, args.runner, only_arms=tuple(args.arm), effort=args.effort)
        elif args.command == "regrade":
            regrade(out)
        elif args.command == "judge":
            judge_all(out, args.judge)
        elif args.command == "calibrate":
            calibrate(load_rules(args.rules), args.judge or sorted(set(review.JUDGE_FOR.values())))
        else:
            compare(out)
    except Exception as exc:  # noqa: BLE001
        if out is not None:
            log_error(out, args.command, exc)
        else:
            traceback.print_exception(exc)
            print(f"screen: {exc}", flush=True)
        return 1
    return 0


def judge_choice(text):
    backend, _, model = text.partition(":")
    if backend not in review.JUDGE_FOR or not model:
        raise argparse.ArgumentTypeError(f"--judge takes BACKEND:MODEL with BACKEND one of {sorted(review.JUDGE_FOR)}, not {text!r}")
    return backend, model


if __name__ == "__main__":
    sys.exit(main())
