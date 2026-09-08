#!/usr/bin/env python3
"""Execute the portable resource commands exactly as the skills document them."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "skills/pstack-harness/SKILL.md"
AUTOPILOT = ROOT / "skills/poteto-mode/playbooks/autopilot-full.md"
PLAN_PLAYBOOK = ROOT / "skills/poteto-mode/playbooks/multi-phase-plan.md"


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)


def git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = run(["git", *args], cwd, env)
    if result.returncode:
        raise AssertionError(f"git {' '.join(args)} failed:\n{result.stdout}{result.stderr}")
    return result.stdout.strip()


def shell_block(path: Path, heading: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(heading)}\n.*?^```sh\n(.*?)^```$", text, re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"{path} lacks the shell block under {heading!r}")
    return match.group(1)


def inline_command(path: Path, needle: str) -> str:
    for command in re.findall(r"`([^`\n]+)`", path.read_text(encoding="utf-8")):
        if needle in command:
            return command
    raise AssertionError(f"{path} lacks an inline command containing {needle!r}")


def valid_plan() -> str:
    rule = "Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked."
    lines = [
        "# Portable plan",
        "",
        "One concrete change.",
        "",
        "## How to read this",
        "",
        "One box is one unit of work.",
        "Each box names the evidence.",
        "Check a box only when its evidence exists.",
        "Read playbooks/ before work.",
        rule,
        "",
        "## Program checklist",
        "",
        "### Arm the program",
        "",
        "- [ ] Arm `/goal`.",
        "- [ ] Read trunk with `git -C \"${PSTACK_SOURCE_ROOT:?}\" fetch origin '+refs/heads/main:refs/remotes/origin/main' && git -C \"$PSTACK_SOURCE_ROOT\" show 'origin/main:skills/poteto-mode/playbooks/autopilot-full.md'`.",
        "- [ ] Audit every 30-minute interval.",
        "- [ ] Send a status message.",
        "",
        "### Spawn owners",
        "",
        "### PR mechanics",
        "",
        "### Verdict and merge",
        "",
        "### Boot recipe",
        "",
        "## Repair portable reads (PR 1)",
        "",
        "**Depends on.** None.",
        "",
        "**Files.**",
        "",
        "- [ ] Edit one file.",
        "",
        "**Build.**",
        "",
        "- [ ] Run the build.",
        "",
        "**You see.**",
        "",
        "- [ ] The command succeeds.",
        "",
        f"**Verify, unit.** {rule}",
        "",
        "- [ ] Run unit tests.",
        "",
        f"**Verify, live.** {rule} Ten lanes on `sonnet` at the PR head.",
        "",
    ]
    lines.extend(
        f"- [ ] Lane {number}. Save `lane-{number}.png`. Pass when the command succeeds."
        for number in range(1, 11)
    )
    lines.extend(
        [
            "",
            f"**Verify, perf.** {rule}",
            "",
            "- [ ] Metric. Runtime.",
            "- [ ] Probe. Run it.",
            "- [ ] Baseline. Record it.",
            "- [ ] Rule. No regression.",
            "",
            "**Review gate.** None.",
            "",
            "**Merge.**",
            "",
            "- [ ] Merge after verification.",
            "",
            "## Close the program",
            "",
            "Close it.",
            "",
            "## Appendix A. Prototype evidence",
            "",
            "No prototype.",
            "",
        ]
    )
    return "\n".join(lines)


class PortableSkillPaths(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "portable fixture with spaces"
        self.base.mkdir()
        self.remote = self.base / "canonical remote.git"
        git(self.base, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.seed = self.base / "seed"
        git(self.base, "init", "--initial-branch=main", str(self.seed))
        git(self.seed, "config", "user.name", "Test User")
        git(self.seed, "config", "user.email", "test.invalid")
        self._write_source("pstack-v1")
        git(self.seed, "add", "skills")
        git(self.seed, "commit", "-m", "fixture v1")
        git(self.seed, "remote", "add", "origin", "https://github.com/mdsmithaustin/pstack.git")

        self.git_config = self.base / "gitconfig"
        self.git_config.write_text(
            f'[url "{self.remote.as_uri()}"]\n\tinsteadOf = https://github.com/mdsmithaustin/pstack.git\n',
            encoding="utf-8",
        )
        self.env = os.environ.copy()
        self.env["GIT_CONFIG_GLOBAL"] = str(self.git_config)
        self.env["GIT_CONFIG_NOSYSTEM"] = "1"
        git(self.seed, "push", "-u", "origin", "main", env=self.env)

        self.source = self.base / "source checkout"
        git(self.base, "clone", "https://github.com/mdsmithaustin/pstack.git", str(self.source), env=self.env)
        self.consumer = self.base / "unrelated consumer"
        git(self.base, "init", "--initial-branch=main", str(self.consumer))
        git(self.consumer, "config", "user.name", "Test User")
        git(self.consumer, "config", "user.email", "test.invalid")
        (self.consumer / "control.md").write_text("consumer-only\n", encoding="utf-8")
        git(self.consumer, "add", "control.md")
        git(self.consumer, "commit", "-m", "consumer")
        self.consumer_remote = self.base / "consumer remote.git"
        git(self.base, "init", "--bare", "--initial-branch=main", str(self.consumer_remote))
        git(self.consumer, "remote", "add", "origin", str(self.consumer_remote))
        git(self.consumer, "push", "-u", "origin", "main")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_source(self, sentinel: str) -> None:
        harness = self.seed / "skills/pstack-harness/SKILL.md"
        harness.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HARNESS, harness)
        checker = self.seed / "skills/poteto-mode/scripts/check-plan.mjs"
        checker.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "skills/poteto-mode/scripts/check-plan.mjs", checker)
        playbook = self.seed / "skills/poteto-mode/playbooks/autopilot-full.md"
        playbook.parent.mkdir(parents=True, exist_ok=True)
        playbook.write_text(f"{sentinel}\n", encoding="utf-8")
        unslop = self.seed / "skills/unslop/SKILL.md"
        unslop.parent.mkdir(parents=True, exist_ok=True)
        unslop.write_text("unslop fixture\n", encoding="utf-8")

    def _root_script(self) -> str:
        return shell_block(HARNESS, "## Resolve the portable roots")

    def _run_contract(
        self,
        invoked: Path,
        extra: str,
        source: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        values = (env or self.env).copy()
        values["PSTACK_HARNESS_SKILL"] = str(invoked)
        if source is not None:
            values["PSTACK_SOURCE_ROOT"] = str(source)
        else:
            values.pop("PSTACK_SOURCE_ROOT", None)
        script = f"set -eu\n{self._root_script()}\n{extra}\n"
        return run(["sh", "-c", script], self.consumer, values)

    def _linked_install(self) -> Path:
        root = self.base / "linked install skills"
        root.mkdir()
        for name in ("pstack-harness", "poteto-mode", "unslop"):
            (root / name).symlink_to(self.source / "skills" / name, target_is_directory=True)
        return root

    def _copied_install(self) -> Path:
        root = self.base / "copied install skills"
        shutil.copytree(self.source / "skills", root)
        return root

    def test_documented_validator_command_runs_in_source_linked_and_copied_layouts(self) -> None:
        command = inline_command(HARNESS, "check-plan.mjs")
        plan = self.consumer / "valid plan.md"
        plan.write_text(valid_plan(), encoding="utf-8")
        for skills_root in (self.source / "skills", self._linked_install(), self._copied_install()):
            with self.subTest(skills_root=skills_root):
                invoked = skills_root / "pstack-harness/SKILL.md"
                result = self._run_contract(invoked, f'PLAN_PATH={shlex_quote(plan)}\n{command}')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("1 PR sections, 0 problems", result.stdout)

    def test_documented_tick_fetches_fresh_pstack_trunk_not_consumer_trunk(self) -> None:
        command = inline_command(AUTOPILOT, "autopilot-full.md")
        first = self._run_contract(
            self.source / "skills/pstack-harness/SKILL.md",
            command,
        )
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("pstack-v1", first.stdout)
        self.assertNotIn("consumer-only", first.stdout)

        self._write_source("pstack-v2")
        git(self.seed, "add", "skills/poteto-mode/playbooks/autopilot-full.md")
        git(self.seed, "commit", "-m", "fixture v2")
        git(self.seed, "push", "origin", "main", env=self.env)
        second = self._run_contract(
            self.source / "skills/pstack-harness/SKILL.md",
            command,
        )
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("pstack-v2", second.stdout)
        self.assertNotIn("pstack-v1", second.stdout)

    def test_control_skill_read_uses_the_consumer_root(self) -> None:
        command = inline_command(PLAN_PLAYBOOK, "CONTROL_SKILL_PATH")
        result = self._run_contract(
            self.source / "skills/pstack-harness/SKILL.md",
            f"CONTROL_SKILL_PATH=control.md\n{command}",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "consumer-only")

    def test_copied_install_clones_canonical_source_and_cleans_only_its_clone(self) -> None:
        copied = self._copied_install()
        command = inline_command(AUTOPILOT, "autopilot-full.md")
        result = self._run_contract(
            copied / "pstack-harness/SKILL.md",
            f'{command}\nprintf "temp=%s\\n" "$PSTACK_TEMP_ROOT"\n{shell_block(HARNESS, "## Clean up a program-owned source clone")}',
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pstack-v1", result.stdout)
        temp_line = next(line for line in result.stdout.splitlines() if line.startswith("temp="))
        self.assertFalse(Path(temp_line.removeprefix("temp=")).exists())
        self.assertTrue(copied.exists())

    def test_wrong_explicit_source_and_clone_failure_stop_without_installed_fallback(self) -> None:
        copied = self._copied_install()
        wrong = self.base / "wrong source"
        shutil.copytree(self.source, wrong)
        git(wrong, "remote", "set-url", "origin", str(self.consumer_remote))
        rejected = self._run_contract(
            copied / "pstack-harness/SKILL.md",
            "printf 'installed-fallback\\n'",
            source=wrong,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("canonical mdsmithaustin/pstack origin", rejected.stderr)
        self.assertNotIn("installed-fallback", rejected.stdout)

        broken_env = self.env.copy()
        broken_config = self.base / "broken-gitconfig"
        broken_config.write_text(
            '[url "file:///definitely/missing/pstack.git"]\n\tinsteadOf = https://github.com/mdsmithaustin/pstack.git\n',
            encoding="utf-8",
        )
        broken_env["GIT_CONFIG_GLOBAL"] = str(broken_config)
        failed = self._run_contract(
            copied / "pstack-harness/SKILL.md",
            "printf 'installed-fallback\\n'",
            env=broken_env,
        )
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("could not clone canonical pstack source", failed.stderr)
        self.assertNotIn("installed-fallback", failed.stdout)

    def test_documented_validator_command_rejects_a_structurally_invalid_plan(self) -> None:
        command = inline_command(HARNESS, "check-plan.mjs")
        plan = self.consumer / "invalid plan.md"
        plan.write_text(valid_plan().replace("### Spawn owners", "### Missing owners"), encoding="utf-8")
        result = self._run_contract(
            self.source / "skills/pstack-harness/SKILL.md",
            f'PLAN_PATH={shlex_quote(plan)}\n{command}',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Program checklist lacks "### Spawn owners" in order', result.stderr)
        self.assertIn("1 PR sections, 1 problems", result.stdout)


def shlex_quote(path: Path) -> str:
    import shlex

    return shlex.quote(str(path))


if __name__ == "__main__":
    unittest.main()
