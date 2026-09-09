#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstalledPersonaRegression(unittest.TestCase):
    def test_copied_skills_deliver_both_complete_personas(self):
        with tempfile.TemporaryDirectory(prefix="pstack-copied-personas-") as temporary:
            installed = Path(temporary) / "installed skills"
            shutil.copytree(ROOT / "skills", installed)
            command = installed / "pstack-harness/scripts/subagents.py"
            for alias, source in (
                ("poteto-agent", "poteto-agent.md"),
                ("Comment Sicko", "comment-sicko.md"),
            ):
                with self.subTest(alias=alias):
                    result = subprocess.run(
                        [sys.executable, str(command), "brief", alias],
                        cwd=temporary, capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    body = (ROOT / "agents" / source).read_text().split("---\n", 2)[2]
                    self.assertIn(body, result.stdout)
                    self.assertIn(str(installed), result.stdout)
                    self.assertNotIn(str(ROOT), result.stdout)


class SubagentCommands(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pstack-subagents-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.installed = self.root / "installed skills"
        shutil.copytree(ROOT / "skills", self.installed)
        self.script = self.installed / "pstack-harness/scripts/subagents.py"
        self.bundle = self.installed / "pstack-harness/references/subagents/roles.json"
        self.project = self.root / "project with spaces"
        self.project.mkdir()

    def run_cli(self, *arguments, expected=0, script=None):
        result = subprocess.run(
            [sys.executable, str(script or self.script), *map(str, arguments)],
            cwd=self.project, capture_output=True, text=True,
            env={**os.environ, "PATH": str(self.root / "no-tools")},
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def native(self, harness="codex", command="install", scope="--project", expected=0):
        return self.run_cli(command, "--harness", harness, scope, self.project, expected=expected)

    def role_path(self, role="comment-sicko", harness="codex"):
        return self.project / (".codex" if harness == "codex" else ".claude") / "agents" / (role + (".toml" if harness == "codex" else ".md"))

    def mutate_body(self, addition):
        payload = json.loads(self.bundle.read_text())
        payload["roles"][0]["body"] += addition
        self.bundle.write_text(json.dumps(payload))

    def test_check_and_aliases_need_no_git_or_network_tools(self):
        report = json.loads(self.run_cli("check").stdout)
        self.assertEqual(report["payload"], "ready")
        self.assertEqual(report["native_activation"], "unverified")
        self.assertEqual({row["id"] for row in report["roles"]}, {"poteto-agent", "comment-sicko"})
        self.assertEqual({row["native_file"] for row in report["roles"]}, {"not-requested"})
        self.assertEqual(self.run_cli("brief", "Comment Sicko").stdout, self.run_cli("brief", "comment-sicko").stdout)

    def test_unknown_role_has_no_partial_brief(self):
        result = self.run_cli("brief", "unregistered", expected=2)
        self.assertEqual(result.stdout, "")
        self.assertIn("unknown pstack role", result.stderr)

    def test_missing_sibling_stops_brief_and_check(self):
        (self.installed / "poteto-mode/SKILL.md").unlink()
        result = self.run_cli("brief", "poteto-agent", expected=1)
        self.assertEqual(result.stdout, "")
        self.assertIn("missing sibling skill", result.stderr)
        self.assertEqual(json.loads(self.run_cli("check", expected=1).stdout)["payload"], "invalid")
        self.assertIn("# Comment Sicko", self.run_cli("brief", "Comment Sicko").stdout)

    def test_logical_symlink_root_owns_sibling_paths(self):
        logical = self.root / "logical skills"
        logical.mkdir()
        (logical / "pstack-harness").symlink_to(self.installed / "pstack-harness", target_is_directory=True)
        shutil.copytree(self.installed / "poteto-mode", logical / "poteto-mode")
        shutil.rmtree(self.installed / "poteto-mode")
        script = logical / "pstack-harness/scripts/subagents.py"
        result = self.run_cli("brief", "poteto-agent", script=script)
        self.assertIn(str(logical / "poteto-mode/SKILL.md"), result.stdout)
        self.assertNotIn(str(self.installed), result.stdout)

    def test_both_native_formats_preserve_full_brief_without_policy_overrides(self):
        for harness in ("claude-code", "codex"):
            self.native(harness, command="check", expected=1)
            report = json.loads(self.native(harness).stdout)
            self.assertEqual(report["native_activation"], "unverified")
            for role in ("comment-sicko", "poteto-agent"):
                brief = self.run_cli("brief", role).stdout
                text = self.role_path(role, harness).read_text()
                if harness == "codex":
                    parsed = tomllib.loads(text)
                    self.assertEqual(set(parsed), {"name", "description", "developer_instructions"})
                    self.assertEqual(parsed["name"], role)
                    self.assertEqual(parsed["developer_instructions"], brief)
                else:
                    frontmatter, body = text[4:].split("---\n", 1)
                    fields = dict(line.split(": ", 1) for line in frontmatter.splitlines())
                    self.assertEqual(fields["name"], role)
                    self.assertEqual(set(fields), {"name", "description", "background"} if role == "poteto-agent" else {"name", "description"})
                    if role == "poteto-agent":
                        self.assertEqual(fields["background"], "true")
                    self.assertIsInstance(json.loads(fields["description"]), str)
                    self.assertIn(brief, body)
            self.native(harness, command="check")

    def test_native_strings_round_trip_quotes_unicode_and_control_characters(self):
        addition = '\nQuoted """ and \\ backslash, café, tab\t, form feed\f.\n'
        self.mutate_body(addition)
        self.native()
        parsed = tomllib.loads(self.role_path().read_text())
        self.assertEqual(parsed["developer_instructions"], self.run_cli("brief", "Comment Sicko").stdout)
        self.assertIn(addition, parsed["developer_instructions"])

    def test_repeated_installs_are_noops_and_preserve_models(self):
        model = self.project / ".agents/pstack-models.md"
        model.parent.mkdir()
        model.write_text("default: user-choice@high\n")
        for scope in ("--project", "--user"):
            for harness in ("claude-code", "codex"):
                self.native(harness, scope=scope)
                paths = [self.role_path(role, harness) for role in ("comment-sicko", "poteto-agent")]
                before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
                report = json.loads(self.native(harness, scope=scope).stdout)
                self.assertEqual({row["action"] for row in report["roles"]}, {"unchanged"})
                self.assertEqual([(path.read_bytes(), path.stat().st_mtime_ns) for path in paths], before)
        self.assertEqual(model.read_text(), "default: user-choice@high\n")

    def test_unedited_generated_files_upgrade_and_partial_runs_recover(self):
        self.native()
        before = self.role_path().read_bytes()
        self.mutate_body("\nAn upstream revision.\n")
        report = json.loads(self.native(command="check", expected=1).stdout)
        self.assertIn("outdated-generated", {row["native_file"] for row in report["roles"]})
        self.role_path("poteto-agent").unlink()
        self.native()
        self.assertNotEqual(self.role_path().read_bytes(), before)
        self.assertIn("An upstream revision.", tomllib.loads(self.role_path().read_text())["developer_instructions"])
        self.native(command="check")

    def test_local_edit_preserving_marker_stops_all_writes(self):
        for harness in ("claude-code", "codex"):
            self.native(harness)
            path = self.role_path("poteto-agent", harness)
            changed = path.read_text().replace("# Poteto subagent", "# My local persona")
            path.write_text(changed)
            other = self.role_path(harness=harness)
            before = other.read_bytes()
            self.mutate_body("\nNew revision.\n")
            report = json.loads(self.native(harness, expected=1).stdout)
            self.assertIn("conflict", {row["native_file"] for row in report["roles"]})
            self.assertEqual(path.read_text(), changed)
            self.assertEqual(other.read_bytes(), before)

    def test_unmarked_collision_preflights_both_roles(self):
        path = self.role_path("poteto-agent")
        path.parent.mkdir(parents=True)
        path.write_text('name = "my-role"\n')
        self.native(expected=1)
        self.assertEqual(path.read_text(), 'name = "my-role"\n')
        self.assertFalse(self.role_path().exists())
        path.unlink()
        self.native()
        self.assertTrue(self.role_path().is_file())

    def test_symlink_file_and_directories_are_conflicts(self):
        outside = self.root / "outside"
        outside.mkdir()
        target = outside / "personal.toml"
        target.write_text("personal content")
        path = self.role_path("poteto-agent")
        path.parent.mkdir(parents=True)
        path.symlink_to(target)
        self.native(expected=1)
        self.assertEqual(target.read_text(), "personal content")
        self.assertFalse(self.role_path().exists())
        path.unlink()
        path.parent.rmdir()
        path.parent.symlink_to(outside, target_is_directory=True)
        self.native(expected=1)
        self.assertEqual(sorted(item.name for item in outside.iterdir()), ["personal.toml"])
        path.parent.unlink()
        path.parent.parent.rmdir()
        path.parent.parent.symlink_to(outside, target_is_directory=True)
        self.native(expected=1)
        self.assertEqual(sorted(item.name for item in outside.iterdir()), ["personal.toml"])

    def test_invalid_cli_arguments_do_not_write(self):
        for arguments in (
            ("install",),
            ("check", "--harness", "codex"),
            ("install", "--project", str(self.project)),
            ("install", "--harness", "codex", "--project", "relative"),
            ("install", "--harness", "codex", "--project", str(self.project), "--user", str(self.root)),
        ):
            with self.subTest(arguments=arguments):
                self.run_cli(*arguments, expected=2)
        self.assertEqual(list(self.project.iterdir()), [])
        self.native()
        self.assertTrue(self.role_path().exists())

    def test_hermes_reports_payload_without_inventing_native_registration(self):
        report = json.loads(self.native("hermes", command="check").stdout)
        self.assertEqual(report["payload"], "ready")
        self.assertEqual({row["native_file"] for row in report["roles"]}, {"unsupported"})
        self.native("hermes", expected=2)
        self.assertFalse((self.project / ".hermes").exists())
        self.assertIn("# Comment Sicko", self.run_cli("brief", "Comment Sicko").stdout)

    def test_invalid_bundles_fail_without_partial_output(self):
        original = self.bundle.read_text()
        for change in ("version", "duplicate", "traversal", "empty", "wrong-type"):
            payload = json.loads(original)
            if change == "version":
                payload["schema_version"] = 2
            elif change == "duplicate":
                payload["roles"].append(payload["roles"][0])
            elif change == "traversal":
                payload["roles"][0]["skills"] = ["../outside"]
            elif change == "empty":
                payload["roles"][0]["body"] = ""
            else:
                payload["roles"][0]["aliases"] = [None]
            self.bundle.write_text(json.dumps(payload))
            with self.subTest(change=change):
                result = self.run_cli("brief", "Comment Sicko", expected=1)
                self.assertEqual(result.stdout, "")
        self.bundle.write_text(original)
        self.run_cli("check")


class SourceParity(unittest.TestCase):
    def test_generation_checks_source_drift_and_rejects_unknown_frontmatter(self):
        with tempfile.TemporaryDirectory(prefix="pstack-generate-") as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "agents", root / "agents")
            shutil.copytree(ROOT / "skills/pstack-harness", root / "skills/pstack-harness")
            (root / "tools").mkdir()
            script = root / "tools/generate-subagents.py"
            shutil.copyfile(ROOT / "tools/generate-subagents.py", script)

            def run(*arguments, expected=0):
                result = subprocess.run([sys.executable, str(script), *arguments], capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                return result

            run("--check")
            source = root / "agents/poteto-agent.md"
            source.write_text(source.read_text() + "\nChanged upstream body.\n")
            run("--check", expected=1)
            run()
            run("--check")
            bundle = json.loads((root / "skills/pstack-harness/references/subagents/roles.json").read_text())
            for role in bundle["roles"]:
                source_bytes = (root / "agents" / (role["id"] + ".md")).read_bytes()
                self.assertEqual(role["body"], source_bytes.decode().split("---\n", 2)[2])
                self.assertEqual(role["source_sha256"], hashlib.sha256(source_bytes).hexdigest())
            source.write_text(source.read_text().replace("is_background: true", "unknown_field: true"))
            self.assertIn("unsupported frontmatter", run(expected=1).stderr)


if __name__ == "__main__":
    unittest.main()
