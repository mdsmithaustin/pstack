#!/usr/bin/env python3
"""Authoring checks for review cases, beyond what the build enforces.

A review case's case.json names the PR in "review": {"patch", "title",
"body_file", "branch"}. The checkout this script builds mirrors the one the
harness builds: main at the pinned commit, and the branch holding pr.patch
applied with `git apply --index` as one commit titled with the PR title.

`check` refuses a case unless:
- the case has the files the build needs, labels.json labels every
  samples/review-*.md with one of its kind's verdicts, a positive case has a
  FOUND and a MISSED sample, and a near-miss case has a CLEAN sample;
- rubric.md does not carry the rule id;
- the prompt names the branch and the body file;
- the prompt, title, branch, body, case id, and the lines pr.patch adds carry
  no meta vocabulary and no word that says the PR was built to hold a flaw;
- every FOUND and FALSE_ALARM sample passes the rule's precheck;
- pr.patch applies to the pinned commit and changes 50 to 300 lines outside
  lockfiles.

A document case names what is judged in "document": {"file": path} or
{"message": true}. `check` refuses one unless it has prompt.md, rubric.md, and
project/ or a workspace, labels.json labels every samples/answer-*.md with one
of its kind's verdicts and the kind's required labels are present, rubric.md
does not carry the rule id, the prompt and case id carry no meta vocabulary,
every sample delivers the document the way a run would, and every FOUND and
FALSE_ALARM sample passes the precheck.

  review_cases.py check [RULE/CASE ...]      validate review and document cases, print a table
  review_cases.py checkout RULE/CASE DEST    build main and the branch in DEST
"""
import json
import re
import sys
import tempfile
from pathlib import Path

CANON = Path(__file__).resolve().parent
sys.path.insert(0, str(CANON))
sys.path.insert(0, str(CANON / "oracles"))
import screen  # noqa: E402
import shared  # noqa: E402
import workspace  # noqa: E402

REVIEW_KEYS = {"patch", "title", "body_file", "branch"}
# The sample file pattern of each judged frame.
SAMPLES = {"review": "review-*.md", "document": "answer-*.md"}
LABELS = {"positive": {"FOUND", "PARTIAL", "MISSED"}, "near-miss": {"CLEAN", "FALSE_ALARM"}}
REQUIRED_LABELS = {"positive": {"FOUND", "MISSED"}, "near-miss": {"CLEAN"}}
# Labels whose sample names the location, so the precheck must pass it.
PRECHECK_PASSES = {"FOUND", "FALSE_ALARM"}
PLANTED = re.compile(r"\b(decoys?|planted|near[- ]miss|flaws?|flawed|seeded)\b", re.IGNORECASE)
BRANCH = re.compile(r"^[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*$")
LOCKFILES = re.compile(r"(^|/)(uv\.lock|poetry\.lock|package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$")
MIN_LINES, MAX_LINES = 50, 300
AUTHOR = {"GIT_AUTHOR_NAME": "Sam Rivera", "GIT_AUTHOR_EMAIL": "sam.rivera@example.com",
          "GIT_COMMITTER_NAME": "Sam Rivera", "GIT_COMMITTER_EMAIL": "sam.rivera@example.com"}


class ReviewError(Exception):
    pass


def review_cases(selected=(), frame="review"):
    """(name, root, case.json) of every case judged in frame, review or document."""
    found = []
    for spec_path in sorted(screen.RULES.glob("*/cases/*/case.json")):
        root = spec_path.parent
        name = f"{root.parent.parent.name}/{root.name}"
        if selected and name not in selected:
            continue
        spec = json.loads(spec_path.read_text())
        if frame in spec:
            found.append((name, root, spec))
    missing = sorted(set(selected) - {name for name, _, _ in found})
    if missing:
        raise ReviewError(f"no {frame} case {missing}")
    return found


def added_lines(patch):
    return "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))


def visible_texts(root, spec):
    """{label: text} for what the reviewing agent sees of the case. The patch
    counts by the lines it adds; its context is upstream code."""
    review = spec["review"]
    return {
        "case id": root.name,
        "prompt.md": (root / "prompt.md").read_text(),
        "title": review["title"],
        "branch": review["branch"],
        review["body_file"]: (root / review["body_file"]).read_text(),
        f"{review['patch']} added lines": added_lines((root / review["patch"]).read_text()),
    }


def labels_of(root):
    path = root / "samples" / "labels.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def shape_problems(rule, root, spec):
    review = spec.get("review")
    if spec.get("kind") not in LABELS:
        return [f"kind must be one of {sorted(LABELS)}"]
    if not isinstance(review, dict) or set(review) != REVIEW_KEYS:
        return [f"review must have exactly {sorted(REVIEW_KEYS)}, not {review!r}"]
    problems = []
    if not BRANCH.match(review["branch"]) or review["branch"] == "main":
        problems.append(f"branch {review['branch']!r} is not a lowercase branch name other than main")
    problems += [f"missing {name}" for name in (review["patch"], review["body_file"], "prompt.md", "rubric.md")
                 if not (root / name).is_file()]
    problems += [f"case.json lacks {key}" for key in ("workspace", "expected_behavior", "domain") if key not in spec]
    behavior = spec.get("expected_behavior")
    if behavior is not None and not (isinstance(behavior, list) and behavior and all(isinstance(item, str) and item.strip() for item in behavior)):
        problems.append("case.json expected_behavior must be a list of non-empty strings")
    if problems:
        return problems
    problems += label_problems(rule, root, spec, "review")
    prompt = (root / "prompt.md").read_text()
    problems += [f"prompt.md does not name {what}" for what in (review["branch"], review["body_file"]) if what not in prompt]
    problems += leak_problems(visible_texts(root, spec))
    return problems


def label_problems(rule, root, spec, frame):
    """labels.json covers exactly the frame's samples with the kind's verdicts,
    the kind's required labels are present, and rubric.md hides the rule id."""
    samples = {path.name for path in (root / "samples").glob(SAMPLES[frame])}
    labels = labels_of(root)
    kind = spec["kind"]
    problems = []
    if set(labels) != samples or not set(labels.values()) <= LABELS[kind]:
        problems.append(f"labels.json must label each of {sorted(samples)} with one of {sorted(LABELS[kind])}, not {labels!r}")
    if not REQUIRED_LABELS[kind] <= set(labels.values()):
        problems.append(f"a {kind} case needs samples labeled {sorted(REQUIRED_LABELS[kind])}")
    if rule in (root / "rubric.md").read_text():
        problems.append("rubric.md carries the rule id")
    return problems


def leak_problems(texts):
    problems = []
    for label, text in texts.items():
        leaked = sorted({match.group(0).lower() for regex in (screen.LEAK, PLANTED) for match in regex.finditer(text)})
        if leaked:
            problems.append(f"{label} carries {leaked}")
    return problems


def document_problems(rule, root, spec):
    """Why a document case cannot be judged, or [] when it can."""
    document = spec.get("document")
    if spec.get("kind") not in LABELS:
        return [f"kind must be one of {sorted(LABELS)}"]
    if document != {"message": True} and not (isinstance(document, dict) and set(document) == {"file"} and isinstance(document["file"], str)):
        return [f"document must be {{\"file\": \"<path>\"}} or {{\"message\": true}}, not {document!r}"]
    problems = [f"missing {name}" for name in ("prompt.md", "rubric.md") if not (root / name).is_file()]
    if "review" in spec:
        problems.append("a case is judged on a review or a document, not both")
    if not ("workspace" in spec or (root / "project").is_dir()):
        problems.append("a document case needs project/ or a workspace")
    problems += [f"case.json lacks {key}" for key in ("expected_behavior", "domain") if key not in spec]
    if problems:
        return problems
    problems += label_problems(rule, root, spec, "document")
    problems += leak_problems({"case id": root.name, "prompt.md": (root / "prompt.md").read_text()})
    for name in sorted(labels_of(root)):
        sample = root / "samples" / name
        if not sample.is_file():
            continue
        if "file" in document and "workspace" in spec:
            diff = sample.with_suffix(".diff")
            if not diff.is_file() or document["file"] not in screen.patch_paths(diff.read_text())[1]:
                problems.append(f"{name} needs a sibling {diff.name} that writes {document['file']}")
            elif screen.patch_deletes(diff.read_text(), document["file"]):
                problems.append(f"{name} has a sibling {diff.name} that deletes {document['file']}")
        elif not shared.document_text(sample.read_text(), document).strip():
            problems.append(f"{name} delivers no document")
    return problems


def precheck_problems(rule, root):
    check = screen.load_check()
    problems = []
    for sample, label in sorted(labels_of(root).items()):
        failures = check.grade(rule, root.name, sample)
        if label in PRECHECK_PASSES and failures:
            problems.append(f"the precheck fails {sample} ({label}): {failures}")
    return problems


def git(*args, cwd, env=None):
    return workspace.git(*args, cwd=cwd, env={**AUTHOR, **(env or {})})


def build(root, spec, dest):
    """main at the pinned commit and the branch with pr.patch as one commit,
    checked out in dest. Returns (main, branch head)."""
    parsed = workspace.parse_spec(root, spec["workspace"])
    mirror = workspace.require_mirror(parsed)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        raise ReviewError(f"{dest} is not empty")
    workspace.materialize(dest, mirror, parsed.commit, {}, history=parsed.history)
    git("checkout", "-q", "-B", "main", cwd=dest)
    git("checkout", "-q", "-b", spec["review"]["branch"], cwd=dest)
    git("apply", "--index", "--binary", "--whitespace=nowarn", str(root / spec["review"]["patch"]), cwd=dest)
    git("-c", "commit.gpgsign=false", "commit", "-q", "--no-verify", "-m", spec["review"]["title"], cwd=dest)
    return git("rev-parse", "main", cwd=dest).decode().strip(), git("rev-parse", "HEAD", cwd=dest).decode().strip()


def size(dest, base, head):
    """(changed lines outside lockfiles, files) of base..head."""
    lines = files = 0
    for record in git("diff", "--numstat", f"{base}..{head}", cwd=dest).decode().splitlines():
        added, deleted, path = record.split("\t", 2)
        files += 1
        if not LOCKFILES.search(path) and added != "-":
            lines += int(added) + int(deleted)
    return lines, files


def review_problems(rule, root, spec):
    """(problems, table cell) for a review case: shape, precheck, and PR size."""
    problems = shape_problems(rule, root, spec)
    lines = files = "-"
    if not problems:
        problems += precheck_problems(rule, root)
        with tempfile.TemporaryDirectory() as directory:
            try:
                lines, files = size(Path(directory) / "repo", *build(root, spec, Path(directory) / "repo"))
                if not MIN_LINES <= lines <= MAX_LINES:
                    problems.append(f"{lines} changed lines, outside {MIN_LINES}-{MAX_LINES}")
            except (workspace.WorkspaceError, ReviewError) as exc:
                problems.append(str(exc))
    return problems, f"{spec['workspace']['repo']:8} lines={lines} files={files}"


def document_case_problems(rule, root, spec):
    """(problems, table cell) for a document case: shape, delivery, and, for a
    pasted case, the precheck on every FOUND and FALSE_ALARM sample."""
    problems = document_problems(rule, root, spec)
    if not problems and "workspace" not in spec:
        problems += precheck_problems(rule, root)
    where = spec["workspace"]["repo"] if "workspace" in spec else "pasted"
    return problems, f"{where:8} document={spec['document'].get('file', 'message')}"


CHECKS = {"review": review_problems, "document": document_case_problems}


def check(selected):
    cases = [(name, root, spec, frame) for frame in CHECKS for name, root, spec in review_cases(frame=frame)]
    if selected:
        missing = sorted(set(selected) - {name for name, *_ in cases})
        if missing:
            raise ReviewError(f"no review or document case {missing}")
        cases = [case for case in cases if case[0] in selected]
    if not cases:
        print("no review or document cases", file=sys.stderr)
        return 1
    failed = False
    for name, root, spec, frame in cases:
        problems, cell = CHECKS[frame](name.split("/")[0], root, spec)
        failed |= bool(problems)
        print(f"{'FAIL' if problems else 'ok  '} {name:55} {spec.get('kind', '?'):9} {cell}")
        for problem in problems:
            print(f"     {problem}")
    return 1 if failed else 0


def main(argv):
    if argv[:1] == ["check"]:
        return check(argv[1:])
    if argv[:1] == ["checkout"] and len(argv) == 3:
        (_, root, spec), = review_cases([argv[1]])
        base, head = build(root, spec, argv[2])
        print(f"main {base}\n{spec['review']['branch']} {head}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (ReviewError, workspace.WorkspaceError, screen.ScreenError) as exc:
        print(f"review_cases: {exc}", file=sys.stderr)
        sys.exit(1)
