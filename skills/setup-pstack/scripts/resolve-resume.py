#!/usr/bin/env python3
"""Resolve saved exact roles to observed, certified recovery destinations without dispatch."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple, TypedDict

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("models_config", Path(__file__).with_name("check-models-config.py"))
models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models)


class EvalReceipt(TypedDict):
    suite: str
    oracle_sha256: str
    fixture_sha256: str
    binding: dict
    observed: dict
    evidence_sha256: dict[str, str]


class DestinationCandidate(NamedTuple):
    harness: str
    resolution: dict | None
    route: str | None
    version: str | None
    eval_receipt: EvalReceipt | None
    eligible: bool
    reason: str | None


class ResolutionInput(NamedTuple):
    work_model: str | None


def read_resolution_input(path: Path) -> ResolutionInput:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or set(value) != {"workModel"}
            or value["workModel"] is not None and not isinstance(value["workModel"], str)):
        raise ValueError("resolution input must be an object containing only workModel as a string or null")
    if value["workModel"] is not None:
        try:
            models.work_model_argument(value["workModel"])
        except argparse.ArgumentTypeError as error:
            raise ValueError(f"argument --work-model: {error}") from error
    return ResolutionInput(value["workModel"])


def read_config(path: Path) -> tuple[dict, dict]:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    sections, findings = models.parse(text)
    errors = [f"{path}:{line}: {message}" for line, level, message in findings if level == "error"]
    if errors:
        raise ValueError("\n".join(errors))
    priorities, _ = models.parse_resume_priority(text)
    return sections, priorities


def candidate(harness: str, role: str, arm: int, layers: list, context: dict, oracle: Path | None,
              resolution_input: ResolutionInput | None = None) -> DestinationCandidate:
    route, version = context.get("route"), context.get("version")
    receipt = None
    resolution = None
    try:
        if role == "trail reviewer" and resolution_input is None:
            raise ValueError("saved reviewer resolution input is unknown")
        catalog = models.CLIS[harness].catalog
        arms = models.resolve_role(role, harness, layers, models.listed_models(catalog) if catalog else models.NO_CATALOG,
                                   work_model=resolution_input.work_model if resolution_input is not None else None)
        if arm > len(arms):
            raise ValueError(f"saved arm {arm} does not exist")
        resolved = arms[arm - 1]
        resolution = json.loads(resolved.to_json())
        if models.INHERIT in (resolved.model, resolved.effort):
            raise ValueError("destination identity is not concrete")
        if context.get("available") is not True or not route or not version:
            raise ValueError("destination availability, route or version is unobserved")
        if oracle is None:
            raise ValueError("current external oracle is required")
        run = Path(context["eval_run"])
        if not run.is_absolute():
            raise ValueError("eval_run must be an absolute retained evidence path")
        run = run.resolve()
        receipt = json.loads((run / "receipt.json").read_text(encoding="utf-8"))
        current = subprocess.run([sys.executable, str(oracle), "check", "--run", str(run)],
                                 capture_output=True, text=True, timeout=30)
        if current.returncode:
            raise ValueError("current oracle rejected evidence: " + current.stderr.strip())
        observed = json.loads(current.stdout)
        if receipt != observed:
            raise ValueError("stale or forged eval receipt")
        if receipt["oracle_sha256"] != hashlib.sha256(oracle.read_bytes()).hexdigest():
            raise ValueError("eval oracle changed")
        binding = {"harness": harness, "resolution": resolution, "route": route, "version": version,
                   "permission_context": context["permission_context"]}
        if receipt["binding"] != binding:
            raise ValueError("eval binding does not match exact current resolution or route context")
        if receipt["suite"] != "pstack-resume-runner-v2":
            raise ValueError("unsupported eval suite")
        return DestinationCandidate(harness, resolution, route, version, receipt, True, None)
    except models.WorkModelSyntaxError:
        raise
    except (OSError, ValueError, KeyError, TypeError, LookupError, subprocess.TimeoutExpired) as error:
        return DestinationCandidate(harness, resolution, route, version, receipt, False, str(error))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--source", required=True, choices=sorted(models.CLIS))
    parser.add_argument("--role", required=True, choices=sorted(models.ROLES))
    parser.add_argument("--arm", required=True, type=int)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--user-file", type=Path, default=Path.home() / ".agents" / models.CONFIG_NAME)
    parser.add_argument("--contexts", type=Path, required=True, help="operator-observed destination contexts keyed by harness")
    parser.add_argument("--oracle", type=Path, help="trusted current resume-recovery oracle.py from the source checkout")
    parser.add_argument("--resolution-input", type=Path, help="saved successful resolver input containing workModel as a string or null")
    args = parser.parse_args()
    if args.arm < 1 or (args.role not in models.PANEL_ROLES and args.arm != 1):
        parser.error("saved arm must be positive and single-value roles require arm 1")
    try:
        resolution_input = read_resolution_input(args.resolution_input) if args.resolution_input is not None else None
        workspace, workspace_priority = read_config(args.project / ".agents" / models.CONFIG_NAME)
        user, user_priority = read_config(args.user_file)
        defaults, _ = models.parse(models.SKILL_DEFAULT_FILE.read_text(encoding="utf-8"))
        contexts = json.loads(args.contexts.read_text(encoding="utf-8"))
        if not isinstance(contexts, dict) or any(not isinstance(value, dict) for value in contexts.values()):
            raise ValueError("contexts must map harness names to observed context objects")
        priority = models.resolve_priority(args.source, workspace_priority, user_priority)
        candidates = [candidate(destination, args.role, args.arm,
                                models.build_layers(destination, workspace, user, defaults),
                                contexts.get(destination, {}), args.oracle.resolve() if args.oracle else None, resolution_input)
                      for destination in priority.destinations]
        print(json.dumps({"priority": priority._asdict(), "candidates": [item._asdict() for item in candidates]}))
        return 0 if any(item.eligible for item in candidates) else 1
    except (OSError, ValueError, TypeError) as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
