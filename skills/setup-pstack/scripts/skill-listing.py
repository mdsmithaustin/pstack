#!/usr/bin/env python3
"""Check or install Claude Code name-only skill listing for the skills Codex keeps from implicit invocation."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

NAME_ONLY = "name-only"
OFF = "off"
OVERRIDES_KEY = "skillOverrides"

# Other suites install into the same skills root, so only pstack's own skills are managed.
# tools/test_skill_invocation_policy.py keeps this equal to the repository's skills/.
PSTACK_SKILLS = frozenset({
    "architect", "arena", "automate-me", "benchmark-checklist", "blast-radius", "bro", "correct",
    "create-verification-skill", "deslop", "documentation-impact", "figure-it-out", "how", "interrogate",
    "maintain-verification-skill", "make-bot-ui", "no-comments", "poteto-help", "poteto-mode", "poteto-tdd",
    "poteto-teach", "principle-attack-the-premise", "principle-boundary-discipline", "principle-build-the-lever",
    "principle-encode-lessons-in-structure", "principle-exhaust-the-design-space", "principle-experience-first",
    "principle-explain-the-number", "principle-fix-root-causes", "principle-foundational-thinking",
    "principle-guard-the-context-window", "principle-laziness-protocol", "principle-make-operations-idempotent",
    "principle-migrate-callers-then-delete-legacy-apis", "principle-minimize-reader-load",
    "principle-model-the-domain", "principle-never-block-on-the-human", "principle-outcome-oriented-execution",
    "principle-prove-it-works", "principle-redesign-from-first-principles",
    "principle-separate-before-serializing-shared-state", "principle-sequence-verifiable-units",
    "principle-subtract-before-you-add", "principle-test-behavior-not-implementation",
    "principle-type-system-discipline", "pstack-harness", "recall", "reflect", "runtime-probes", "setup-pstack",
    "show-me-your-work", "spec-probes", "swarm", "technical-writing", "typescript-best-practices", "unslop",
    "verify-commands", "why",
})

POLICY_HEADER = re.compile(r"^policy\s*:\s*(?P<inline>.*?)\s*(?:#.*)?$")
IMPLICIT_FALSE = re.compile(r"""\ballow_implicit_invocation\s*:\s*["']?false["']?\s*(?:[,}#]|$)""", re.IGNORECASE)


class ListingError(Exception):
    pass


def default_settings() -> Path:
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(config_dir).expanduser() if config_dir else Path.home() / ".claude"
    return base / "settings.json"


def default_skills_root() -> Path:
    return Path(os.path.abspath(__file__)).parents[2]


def disables_implicit_invocation(yaml_text: str) -> bool:
    in_policy = False
    for raw in yaml_text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            header = POLICY_HEADER.match(raw)
            in_policy = header is not None
            if header and header["inline"] and IMPLICIT_FALSE.search(header["inline"]):
                return True
        elif in_policy and IMPLICIT_FALSE.match(raw.strip()):
            return True
    return False


def skill_dirs(root: Path) -> list[str]:
    return sorted(entry.name for entry in root.iterdir() if entry.name in PSTACK_SKILLS and (entry / "SKILL.md").is_file())


def managed_skills(root: Path) -> list[str]:
    managed = []
    for name in skill_dirs(root):
        try:
            text = (root / name / "agents" / "openai.yaml").read_text(encoding="utf-8")
        except OSError:
            continue
        if disables_implicit_invocation(text):
            managed.append(name)
    return managed


def load_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ListingError(f"cannot read {path}: {error}") from error
    if not isinstance(data, dict):
        raise ListingError(f"{path}: top level is not a JSON object")
    if not isinstance(data.get(OVERRIDES_KEY, {}), dict):
        raise ListingError(f"{path}: {OVERRIDES_KEY} is not a JSON object")
    return data


def classify(settings: dict, root: Path) -> dict:
    managed = managed_skills(root)
    if not managed:
        raise ListingError(f"{root}: no skill sets allow_implicit_invocation: false under policy in agents/openai.yaml")
    overrides = settings.get(OVERRIDES_KEY, {})
    managed_set = set(managed)
    return {
        "name_only": len(managed),
        "missing": sorted(n for n in managed if overrides.get(n) not in (NAME_ONLY, OFF)),
        "extra": sorted(n for n in skill_dirs(root) if n not in managed_set and overrides.get(n) == NAME_ONLY),
        "kept_off": sorted(n for n in managed if overrides.get(n) == OFF),
    }


def report(settings_path: Path, root: Path, found: dict) -> dict:
    return {
        "settings": str(settings_path),
        "skills_root": str(root),
        **found,
        "state": "stale" if found["missing"] or found["extra"] else "current",
    }


def check(settings_path: Path, root: Path) -> dict:
    return report(settings_path, root, classify(load_settings(settings_path), root))


def write_atomically(path: Path, data: dict) -> None:
    target = Path(os.path.realpath(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, target)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def install(settings_path: Path, root: Path) -> dict:
    settings = load_settings(settings_path)
    found = classify(settings, root)
    added, removed = found["missing"], found["extra"]
    written = bool(added or removed)
    if written:
        overrides = dict(settings.get(OVERRIDES_KEY, {}))
        for name in removed:
            del overrides[name]
        for name in added:
            overrides[name] = NAME_ONLY
        try:
            write_atomically(settings_path, {**settings, OVERRIDES_KEY: overrides})
        except OSError as error:
            raise ListingError(f"cannot write {settings_path}: {error}") from error
        found = classify(load_settings(settings_path), root)
    return {**report(settings_path, root, found), "added": added, "removed": removed, "written": written}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="skill-listing.py", allow_abbrev=False)
    parser.add_argument("command", choices=("check", "install"))
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--skills-root", type=Path)
    args = parser.parse_args(argv)
    settings_path = args.settings or default_settings()
    root = args.skills_root or default_skills_root()
    try:
        result = (check if args.command == "check" else install)(settings_path, root)
    except (ListingError, OSError) as error:
        print(f"skill-listing.py: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 1 if args.command == "check" and result["state"] == "stale" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
