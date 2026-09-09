#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


@dataclass(frozen=True)
class Role:
    id: str
    aliases: tuple[str, ...]
    description: str
    body: str
    background: bool
    skills: tuple[str, ...]


@dataclass(frozen=True)
class Destination:
    harness: str
    root: Path

    @property
    def directory(self) -> Path:
        return self.root / {"claude-code": ".claude", "codex": ".codex"}[self.harness] / "agents"


@dataclass(frozen=True)
class NativeFile:
    path: Path
    expected: bytes
    previous: bytes | None
    status: str


def load_roles(skill_directory: Path) -> tuple[Role, ...]:
    payload = json.loads((skill_directory / "references/subagents/roles.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "roles"}:
        raise ValueError("invalid role bundle fields")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ValueError("unsupported role bundle version")
    if not isinstance(payload["roles"], list) or not payload["roles"]:
        raise ValueError("role bundle must contain roles")
    roles = []
    aliases = set()
    fields = {"id", "aliases", "description", "body", "background", "skills", "source_sha256"}
    for item in payload["roles"]:
        if not isinstance(item, dict) or set(item) != fields:
            raise ValueError("invalid role fields")
        if not isinstance(item["id"], str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", item["id"]):
            raise ValueError("invalid native role identifier")
        for key in ("description", "body"):
            if not isinstance(item[key], str) or not item[key].strip():
                raise ValueError(f"{item['id']}: empty or invalid {key}")
        if type(item["background"]) is not bool:
            raise ValueError(f"{item['id']}: background must be boolean")
        if not isinstance(item["source_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["source_sha256"]):
            raise ValueError(f"{item['id']}: invalid source digest")
        for key in ("aliases", "skills"):
            values = item[key]
            if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{item['id']}: invalid {key}")
            if len(set(values)) != len(values):
                raise ValueError(f"{item['id']}: duplicate {key}")
        if item["id"] not in item["aliases"] or aliases.intersection(item["aliases"]):
            raise ValueError("missing canonical alias or duplicate role alias")
        if any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill) for skill in item["skills"]):
            raise ValueError(f"{item['id']}: invalid sibling skill name")
        aliases.update(item["aliases"])
        roles.append(Role(item["id"], tuple(item["aliases"]), item["description"], item["body"], item["background"], tuple(item["skills"])))
    if not {"poteto-agent", "Comment Sicko", "comment-sicko"}.issubset(aliases):
        raise ValueError("role bundle lacks required pstack aliases")
    return tuple(roles)


def render_brief(role: Role, skills_root: Path) -> str:
    paths = [skills_root / name / "SKILL.md" for name in role.skills]
    for path in paths:
        if not path.is_file():
            raise ValueError(f"{role.id}: missing sibling skill {path}")
    guidance = (
        "Pstack installed skill paths\n\n"
        "Use these local files when the persona below requires a skill read. "
        "Read each required SKILL.md in full; follow its relative references from its directory. "
        "Resolve other named sibling skills under this installed skills root: "
        + json.dumps(str(skills_root), ensure_ascii=False) + ".\n"
    )
    guidance += "".join(f"- {name}: {json.dumps(str(path), ensure_ascii=False)}\n" for name, path in zip(role.skills, paths))
    return guidance + "\n" + role.body


def render_native(role: Role, destination: Destination, brief: str) -> bytes:
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    if destination.harness == "claude-code":
        content = f"---\nname: {role.id}\ndescription: {quote(role.description)}\n"
        if role.background:
            content += "background: true\n"
        content += "---\n\n" + brief
        marker = "<!-- pstack-generated:v1:{role}:{digest} -->\n"
    else:
        content = f"name = {quote(role.id)}\ndescription = {quote(role.description)}\ndeveloper_instructions = {quote(brief)}\n"
        marker = "# pstack-generated:v1:{role}:{digest}\n"
    encoded = (content + "\n").encode("utf-8")
    return encoded + marker.format(role=role.id, digest=hashlib.sha256(encoded).hexdigest()).encode("ascii")


def managed(content: bytes, role_id: str, harness: str) -> bool:
    prefix, separator, last = content[:-1].rpartition(b"\n")
    if not separator or not content.endswith(b"\n"):
        return False
    if harness == "claude-code":
        pattern = rb"<!-- pstack-generated:v1:" + role_id.encode() + rb":([0-9a-f]{64}) -->"
    else:
        pattern = rb"# pstack-generated:v1:" + role_id.encode() + rb":([0-9a-f]{64})"
    match = re.fullmatch(pattern, last)
    return match is not None and hashlib.sha256(prefix + b"\n").hexdigest().encode() == match[1]


def validate_destination(destination: Destination) -> None:
    if destination.root.is_symlink() or not destination.root.is_dir():
        raise ValueError(f"destination root must be an existing nonsymlink directory: {destination.root}")
    if destination.harness == "hermes":
        return
    for path in (destination.directory.parent, destination.directory):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError(f"destination must be a nonsymlink directory: {path}")


def inspect_native(role: Role, destination: Destination, brief: str) -> NativeFile:
    suffix = ".md" if destination.harness == "claude-code" else ".toml"
    path = destination.directory / (role.id + suffix)
    expected = render_native(role, destination, brief)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return NativeFile(path, expected, None, "conflict")
    if not path.exists():
        return NativeFile(path, expected, None, "missing")
    previous = path.read_bytes()
    if previous == expected:
        status = "current"
    elif managed(previous, role.id, destination.harness):
        status = "outdated-generated"
    else:
        status = "conflict"
    return NativeFile(path, expected, previous, status)


def install_files(files: tuple[NativeFile, ...], destination: Destination) -> None:
    validate_destination(destination)
    destination.directory.mkdir(parents=True, exist_ok=True)
    validate_destination(destination)
    for item in files:
        if item.status == "current":
            continue
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.directory, prefix=".pstack-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(item.expected)
                stream.flush()
                os.fsync(stream.fileno())
            validate_destination(destination)
            if item.path.is_symlink():
                raise ValueError(f"destination changed during install: {item.path}")
            if item.previous is None:
                os.link(temporary, item.path)
            else:
                if not item.path.is_file() or item.path.read_bytes() != item.previous:
                    raise ValueError(f"destination changed during install: {item.path}")
                os.replace(temporary, item.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check, brief, or register installed pstack personas.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("brief").add_argument("role")
    for command in ("check", "install"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--harness", choices=("claude-code", "codex", "hermes"))
        scope = subparser.add_mutually_exclusive_group()
        scope.add_argument("--project", type=Path)
        scope.add_argument("--user", type=Path)
    args = parser.parse_args()
    destination = None
    if args.command != "brief":
        root = args.project or args.user
        if bool(args.harness) != bool(root):
            parser.error("--harness requires exactly one of --project ABS_ROOT or --user ABS_ROOT")
        if args.command == "install" and not root:
            parser.error("install requires --harness and an explicit destination")
        if root and not root.is_absolute():
            parser.error("destination root must be absolute")
        if args.command == "install" and args.harness == "hermes":
            parser.error("Hermes has no supported native role-file registration; use brief")
        if root:
            destination = Destination(args.harness, root)
    skill_directory = Path(os.path.abspath(sys.argv[0])).parent.parent
    skills_root = skill_directory.parent
    report = {"payload": "invalid", "native_activation": "unverified", "roles": []}
    try:
        roles = load_roles(skill_directory)
        if args.command == "brief":
            role = next((role for role in roles if args.role in role.aliases), None)
            if role is None:
                parser.error(f"unknown pstack role: {args.role}")
            sys.stdout.write(render_brief(role, skills_root))
            return 0
        briefs = {role.id: render_brief(role, skills_root) for role in roles}
        report["payload"] = "ready"
        if destination:
            validate_destination(destination)
        if destination and destination.harness != "hermes":
            files = tuple(inspect_native(role, destination, briefs[role.id]) for role in roles)
            report["roles"] = [{"id": role.id, "native_file": item.status, "path": str(item.path)} for role, item in zip(roles, files)]
            if args.command == "install" and not any(item.status == "conflict" for item in files):
                install_files(files, destination)
                for row in report["roles"]:
                    row["action"] = "unchanged" if row["native_file"] == "current" else "installed"
                    row["native_file"] = "current"
            success = all(row["native_file"] == "current" for row in report["roles"])
        else:
            report["roles"] = [{"id": role.id, "native_file": "unsupported" if destination else "not-requested"} for role in roles]
            success = True
        print(json.dumps(report, indent=2))
        return 0 if success else 1
    except (OSError, ValueError, UnicodeError) as error:
        if args.command == "brief":
            print(f"error: {error}", file=sys.stderr)
        else:
            report["error"] = str(error)
            print(json.dumps(report, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
