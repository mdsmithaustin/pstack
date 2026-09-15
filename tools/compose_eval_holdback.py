from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any


SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CompositionError(ValueError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CompositionError(f"{path} repeats key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompositionError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CompositionError(f"{path} must contain one JSON object")
    return value


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in checked_files(root):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def public_digests(repo: Path, skill_name: str) -> dict[str, str]:
    if not SKILL_NAME.fullmatch(skill_name):
        raise CompositionError(f"invalid skill name: {skill_name}")
    public_manifest = repo / "evals" / skill_name / "shared-benchmark.json"
    public_skill = repo / "skills" / skill_name / "SKILL.md"
    if not public_manifest.is_file():
        raise CompositionError(f"missing public manifest: {public_manifest}")
    if not public_skill.is_file():
        raise CompositionError(f"missing public skill: {public_skill}")
    return {
        "public_manifest_sha256": file_sha256(public_manifest),
        "public_skill_sha256": file_sha256(public_skill),
        "public_suite_sha256": tree_sha256(public_manifest.parent),
        "public_skill_tree_sha256": tree_sha256(public_skill.parent),
    }


def require_digest(overlay: dict[str, Any], field: str, actual: str) -> None:
    expected = overlay.get(field)
    if not isinstance(expected, str) or not SHA256.fullmatch(expected):
        raise CompositionError(f"{field} must be a lowercase SHA-256 digest")
    if expected != actual:
        raise CompositionError(f"{field} does not match the frozen public input")


def checked_files(root: Path) -> list[Path]:
    if not root.is_dir():
        raise CompositionError(f"missing directory: {root}")
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise CompositionError(f"symlinks are not allowed: {path}")
        if path.is_file() and "__pycache__" not in path.parts and "runs" not in path.parts:
            files.append(path)
    return files


def copy_tree(source: Path, destination: Path, *, reject_collisions: bool) -> None:
    for path in checked_files(source):
        relative = path.relative_to(source)
        target = destination / relative
        if reject_collisions and target.exists():
            raise CompositionError(f"private payload collides with public file: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def validate_cases(public: dict[str, Any], overlay: dict[str, Any]) -> list[dict[str, Any]]:
    cases = overlay.get("cases")
    if not isinstance(cases, list) or not cases:
        raise CompositionError("cases must be a non-empty list")
    public_ids = {case.get("id") for case in public.get("cases", []) if isinstance(case, dict)}
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise CompositionError(f"case #{index + 1} must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise CompositionError(f"case #{index + 1} needs a non-empty id")
        kind = case.get("kind")
        if kind not in {"positive", "negative", "adversarial", "behavior", "trigger"}:
            raise CompositionError(f"{case_id} has unsupported kind: {kind!r}")
        if case_id in public_ids or case_id in seen:
            raise CompositionError(f"case id is not unique: {case_id}")
        if case.get("split") != "holdback":
            raise CompositionError(f"{case_id} must use split=holdback")
        if kind == "trigger" and not isinstance(case.get("should_trigger"), bool):
            raise CompositionError(f"{case_id} trigger case needs boolean should_trigger")
        if kind != "trigger" and "should_trigger" in case:
            raise CompositionError(f"{case_id} behavior case must not set should_trigger")
        seen.add(case_id)
        validated.append(case)
    behavior = [case for case in validated if case.get("kind") != "trigger"]
    positive_triggers = [case for case in validated if case.get("kind") == "trigger" and case["should_trigger"]]
    negative_triggers = [case for case in validated if case.get("kind") == "trigger" and not case["should_trigger"]]
    counts = (len(behavior), len(positive_triggers), len(negative_triggers))
    if counts != (4, 4, 4):
        raise CompositionError(
            "private population must contain exactly 4 behavior, 4 positive trigger, "
            f"and 4 negative trigger cases; found {counts[0]}/{counts[1]}/{counts[2]}"
        )
    return validated


def validate_case_references(
    cases: list[dict[str, Any]],
    public_files: set[str],
    private_files: set[str],
) -> None:
    available = public_files | private_files
    for case in cases:
        case_id = case["id"]
        files = case.get("files", [])
        if not isinstance(files, list) or not all(isinstance(value, str) for value in files):
            raise CompositionError(f"{case_id} files must be a string list")
        references = list(files)
        if "prompt_ref" in case:
            prompt_ref = case["prompt_ref"]
            if not isinstance(prompt_ref, str):
                raise CompositionError(f"{case_id} prompt_ref must be a string")
            references.append(prompt_ref)
        for reference in references:
            path = PurePosixPath(reference)
            if (
                not reference
                or "\\" in reference
                or path.is_absolute()
                or path.as_posix() != reference
                or any(part in {".", ".."} for part in path.parts)
            ):
                raise CompositionError(f"{case_id} has an unsafe file reference: {reference!r}")
            if reference not in available:
                raise CompositionError(f"{case_id} references a missing file: {reference}")


def compose(repo: Path, skill_name: str, overlay_path: Path, output_root: Path) -> Path:
    repo = repo.resolve()
    overlay_path = overlay_path.resolve()
    output_root = output_root.resolve()
    if output_root == repo or repo in output_root.parents:
        raise CompositionError("the composed holdback must be outside the repository")
    if output_root.exists():
        if not output_root.is_dir():
            raise CompositionError(f"output path is not a directory: {output_root}")
        if any(output_root.iterdir()):
            raise CompositionError(f"output directory is not empty: {output_root}")

    public_manifest = repo / "evals" / skill_name / "shared-benchmark.json"
    public_skill = repo / "skills" / skill_name / "SKILL.md"
    public_suite = public_manifest.parent
    public_skill_tree = public_skill.parent
    digests = public_digests(repo, skill_name)
    overlay = read_json(overlay_path)
    public = read_json(public_manifest)

    if overlay.get("version") != 1:
        raise CompositionError("overlay version must be 1")
    if overlay.get("skill_name") != skill_name:
        raise CompositionError("overlay skill_name does not match --skill")
    for field, actual in digests.items():
        require_digest(overlay, field, actual)
    private_cases = validate_cases(public, overlay)

    payload_name = overlay.get("payload_dir", "payload")
    if (
        not isinstance(payload_name, str)
        or payload_name in {".", ".."}
        or Path(payload_name).is_absolute()
        or Path(payload_name).parts != (payload_name,)
    ):
        raise CompositionError("payload_dir must be one directory name")
    unresolved_payload = overlay_path.parent / payload_name
    if unresolved_payload.is_symlink():
        raise CompositionError("payload_dir must not be a symlink")
    payload = unresolved_payload.resolve()
    if payload.parent != overlay_path.parent:
        raise CompositionError("payload_dir escapes the overlay directory")

    public_files = {path.relative_to(public_suite).as_posix() for path in checked_files(public_suite)}
    private_files = {path.relative_to(payload).as_posix() for path in checked_files(payload)}
    validate_case_references(private_cases, public_files, private_files)

    output_root.mkdir(parents=True, exist_ok=True)
    output_suite = output_root / "evals" / skill_name
    output_skill = output_root / "skills" / skill_name
    copy_tree(public_suite, output_suite, reject_collisions=False)
    copy_tree(public_skill_tree, output_skill, reject_collisions=False)
    copy_tree(payload, output_suite, reject_collisions=True)

    merged = dict(public)
    merged["cases"] = [*public.get("cases", []), *private_cases]
    split_policy = dict(public.get("split_policy", {}))
    split_policy["holdback"] = "Private cases composed from an external frozen overlay."
    merged["split_policy"] = split_policy
    output_manifest = output_suite / "shared-benchmark.json"
    output_manifest.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return output_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Compose a frozen private holdback outside the repository.")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-public-digests", action="store_true")
    args = parser.parse_args()
    try:
        if args.print_public_digests:
            print(json.dumps(public_digests(args.repo.resolve(), args.skill), indent=2, sort_keys=True))
            return 0
        if args.overlay is None or args.out is None:
            parser.error("--overlay and --out are required unless --print-public-digests is used")
        manifest = compose(args.repo, args.skill, args.overlay, args.out)
    except CompositionError as exc:
        parser.error(str(exc))
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
