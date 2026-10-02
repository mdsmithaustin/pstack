#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
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

    def effort_path(self, level="max"):
        return self.project / ".claude" / "agents" / f"pstack-effort-{level}.md"

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

    def test_brief_asks_for_a_persona_line_in_the_first_reply(self):
        brief = self.run_cli("brief", "poteto-agent").stdout
        self.assertIn("Put the exact line `persona: poteto-agent` on its own line in your first reply.\n", brief)
        self.assertTrue(brief.startswith("Pstack installed skill paths\n"))

    def test_persona_with_its_own_first_line_gets_no_marker(self):
        brief = self.run_cli("brief", "Comment Sicko").stdout
        self.assertNotIn("persona: comment-sicko", brief)
        self.assertNotIn("on its own line in your first reply", brief)
        self.assertTrue(brief.startswith("Pstack installed skill paths\n"))
        self.assertIn("Yes... Ha ha ha... Yes!", brief)

    def test_signature_missing_from_the_body_invalidates_the_bundle(self):
        payload = json.loads(self.bundle.read_text())
        payload["roles"][0]["signature"] = "a line the body never says"
        self.bundle.write_text(json.dumps(payload))
        self.assertIn("signature", self.run_cli("brief", "poteto-agent", expected=1).stderr)

    def test_unknown_role_has_no_partial_brief(self):
        result = self.run_cli("brief", "unregistered", expected=2)
        self.assertEqual(result.stdout, "")
        self.assertIn("unknown pstack persona", result.stderr)

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

    def test_aliases_of_one_installation_share_native_files(self):
        per_skill = self.root / "per-skill links"
        per_skill.mkdir()
        for skill in self.installed.iterdir():
            (per_skill / skill.name).symlink_to(skill, target_is_directory=True)
        whole = self.root / "whole link"
        whole.symlink_to(self.installed, target_is_directory=True)
        copied = self.root / "copied skills"
        shutil.copytree(self.installed, copied)
        for harness in ("claude-code", "codex"):
            self.native(harness)
            paths = [self.role_path(role, harness) for role in ("comment-sicko", "poteto-agent")]
            before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
            for alias in (per_skill, whole):
                with self.subTest(harness=harness, alias=alias.name):
                    script = alias / "pstack-harness/scripts/subagents.py"
                    report = json.loads(self.run_cli("check", "--harness", harness, "--project", self.project, script=script).stdout)
                    self.assertEqual({row["native_file"] for row in report["roles"]}, {"current"})
                    report = json.loads(self.run_cli("install", "--harness", harness, "--project", self.project, script=script).stdout)
                    self.assertEqual({row["action"] for row in report["roles"]}, {"unchanged"})
                    self.assertEqual([(path.read_bytes(), path.stat().st_mtime_ns) for path in paths], before)
            with self.subTest(harness=harness, alias="copied"):
                script = copied / "pstack-harness/scripts/subagents.py"
                report = json.loads(self.run_cli("check", "--harness", harness, "--project", self.project, script=script, expected=1).stdout)
                self.assertEqual({row["native_file"] for row in report["roles"]}, {"outdated-generated"})

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

    def test_bytes_appended_after_marker_are_user_edits(self):
        for harness in ("claude-code", "codex"):
            self.native(harness)
            path = self.role_path("poteto-agent", harness)
            changed = path.read_bytes() + b"\n"
            path.write_bytes(changed)
            self.native(harness, expected=1)
            self.assertEqual(path.read_bytes(), changed)

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

    def test_destination_swap_after_preflight_does_not_create_outside_directories(self):
        driver = self.root / "swap before install.py"
        driver.write_text("""import importlib.util
import sys

script, outside, *arguments = sys.argv[1:]
spec = importlib.util.spec_from_file_location("subagents_race", script)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
install = module.install_files

def swap_before_install(files, destination):
    destination.directory.parent.symlink_to(outside, target_is_directory=True)
    return install(files, destination)

module.install_files = swap_before_install
sys.argv = [script, *arguments]
sys.exit(module.main())
""")
        for harness in ("claude-code", "codex"):
            outside = self.root / (harness + " unintended directory")
            outside.mkdir()
            (outside / "personal.txt").write_text("keep this file")
            with self.subTest(harness=harness):
                result = self.run_cli(
                    self.script, outside, "install", "--harness", harness,
                    "--project", self.project, script=driver, expected=1,
                )
                self.assertIn("nonsymlink directory", json.loads(result.stdout)["error"])
                self.assertEqual(sorted(path.name for path in outside.iterdir()), ["personal.txt"])
            self.role_path(harness=harness).parent.parent.unlink()
            self.native(harness)
            self.assertIn("# Comment Sicko", self.role_path(harness=harness).read_text())

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

    def test_every_harness_rejects_invalid_destination_roots(self):
        missing = self.root / "missing"
        regular_file = self.root / "regular file"
        regular_file.write_text("keep this file")
        symlink = self.root / "symlink root"
        symlink.symlink_to(self.project, target_is_directory=True)
        for harness in ("claude-code", "codex", "hermes"):
            for scope in ("--project", "--user"):
                for root in (missing, regular_file, symlink):
                    with self.subTest(harness=harness, scope=scope, root=root.name):
                        result = self.run_cli("check", "--harness", harness, scope, root, expected=1)
                        self.assertIn("existing nonsymlink directory", json.loads(result.stdout)["error"])
        self.assertFalse(missing.exists())
        self.assertEqual(regular_file.read_text(), "keep this file")
        self.assertEqual(list(self.project.iterdir()), [])

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

    def test_claude_install_writes_five_effort_agents_with_only_effort_policy(self):
        levels = ("low", "medium", "high", "xhigh", "max")
        report = json.loads(self.native("claude-code").stdout)
        self.assertEqual([row["id"] for row in report["efforts"]], [f"pstack-effort-{level}" for level in levels])
        self.assertEqual({row["action"] for row in report["efforts"]}, {"installed"})
        delegate = (self.installed / "pstack-harness/references/subagents/effort-delegate.md").read_text()
        for level in levels:
            with self.subTest(level=level):
                text = self.effort_path(level).read_text()
                frontmatter, body = text[4:].split("---\n", 1)
                fields = dict(line.split(": ", 1) for line in frontmatter.splitlines())
                self.assertEqual(set(fields), {"name", "description", "effort"})
                self.assertEqual(fields["name"], f"pstack-effort-{level}")
                self.assertEqual(fields["effort"], level)
                self.assertIsInstance(json.loads(fields["description"]), str)
                self.assertIn(delegate, body)
                self.assertRegex(text.splitlines()[-1], rf"<!-- pstack-generated:v1:pstack-effort-{level}:[0-9a-f]{{64}} -->")

    def test_effort_agents_are_root_independent(self):
        self.native("claude-code")
        second_root = self.root / "second installed skills"
        shutil.copytree(ROOT / "skills", second_root)
        second_project = self.root / "second project"
        second_project.mkdir()
        second_script = second_root / "pstack-harness/scripts/subagents.py"
        self.run_cli("install", "--harness", "claude-code", "--project", second_project, script=second_script)
        for level in ("low", "medium", "high", "xhigh", "max"):
            first_bytes = self.effort_path(level).read_bytes()
            second_bytes = (second_project / ".claude/agents" / f"pstack-effort-{level}.md").read_bytes()
            self.assertEqual(first_bytes, second_bytes)
        report = json.loads(self.run_cli("check", "--harness", "claude-code", "--project", second_project, expected=1).stdout)
        self.assertEqual({row["native_file"] for row in report["roles"]}, {"outdated-generated"})
        self.assertEqual({row["native_file"] for row in report["efforts"]}, {"current"})

    def test_codex_and_hermes_get_no_effort_agents(self):
        self.native("codex")
        self.assertEqual(json.loads(self.native("codex", command="check").stdout)["efforts"], [])
        self.assertEqual(json.loads(self.native("hermes", command="check").stdout)["efforts"], [])
        self.assertEqual(list((self.project / ".codex/agents").glob("pstack-effort-*")), [])

    def test_repeated_effort_installs_are_noops(self):
        self.native("claude-code")
        paths = [self.effort_path(level) for level in ("low", "medium", "high", "xhigh", "max")]
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
        report = json.loads(self.native("claude-code").stdout)
        self.assertEqual({row["action"] for row in report["efforts"]}, {"unchanged"})
        self.assertEqual([(path.read_bytes(), path.stat().st_mtime_ns) for path in paths], before)

    def test_template_change_upgrades_every_level(self):
        self.native("claude-code")
        template = self.installed / "pstack-harness/references/subagents/effort-delegate.md"
        template.write_text(template.read_text() + "\nAn upstream revision.\n")
        report = json.loads(self.native("claude-code", command="check", expected=1).stdout)
        self.assertEqual({row["native_file"] for row in report["efforts"]}, {"outdated-generated"})
        report = json.loads(self.native("claude-code").stdout)
        self.assertEqual({row["native_file"] for row in report["efforts"]}, {"current"})
        self.assertIn("An upstream revision.", self.effort_path("max").read_text())

    def test_squatted_effort_file_does_not_block_persona_upgrade(self):
        self.native("claude-code")
        self.effort_path("max").write_text("squatted content")
        self.mutate_body("\nA persona revision.\n")
        report = json.loads(self.native("claude-code", expected=1).stdout)
        self.assertIn("conflict", {row["native_file"] for row in report["efforts"]})
        self.assertEqual({row["native_file"] for row in report["roles"]}, {"current"})

    def test_squatted_persona_file_does_not_block_effort_upgrade(self):
        self.native("claude-code")
        template = self.installed / "pstack-harness/references/subagents/effort-delegate.md"

        self.role_path("poteto-agent", "claude-code").write_text("squatted content")
        template.write_text(template.read_text() + "\nAnother revision.\n")
        report = json.loads(self.native("claude-code", expected=1).stdout)
        self.assertIn("conflict", {row["native_file"] for row in report["roles"]})
        self.assertEqual({row["native_file"] for row in report["efforts"]}, {"current"})

    def test_missing_or_templated_delegate_fails_without_partial_output(self):
        template = self.installed / "pstack-harness/references/subagents/effort-delegate.md"
        original = template.read_text()
        for mutation in ("missing", "templated"):
            with self.subTest(mutation=mutation):
                if mutation == "missing":
                    template.unlink()
                else:
                    template.write_text(original + "{brace}")
                self.assertIn("# Comment Sicko", self.run_cli("brief", "Comment Sicko").stdout)
                self.assertEqual(json.loads(self.run_cli("check", expected=1).stdout)["payload"], "invalid")
                self.native("claude-code", expected=1)
                self.assertFalse((self.project / ".claude").exists())
            template.write_text(original)

    def test_claude_code_persona_bytes_match_a_hand_written_reconstruction(self):
        self.native("claude-code")
        for role in json.loads(self.bundle.read_text())["roles"]:
            role_id = role["id"]
            content = f"---\nname: {role_id}\ndescription: {json.dumps(role['description'], ensure_ascii=False)}\n"
            if role["background"]:
                content += "background: true\n"
            brief = self.run_cli("brief", role_id).stdout
            content += "---\n\n" + brief
            encoded = (content + "\n").encode("utf-8")
            digest = hashlib.sha256(encoded).hexdigest()
            expected = encoded + f"<!-- pstack-generated:v1:{role_id}:{digest} -->\n".encode("ascii")
            with self.subTest(role=role_id):
                self.assertEqual(self.role_path(role_id, "claude-code").read_bytes(), expected)


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


class LevelParity(unittest.TestCase):
    def test_effort_levels_match_lint(self):
        subagents_spec = importlib.util.spec_from_file_location(
            "subagents_under_test", ROOT / "skills/pstack-harness/scripts/subagents.py")
        subagents = importlib.util.module_from_spec(subagents_spec)
        # module-level dataclasses need their module resolvable via sys.modules during exec_module
        sys.modules[subagents_spec.name] = subagents
        subagents_spec.loader.exec_module(subagents)
        lint_spec = importlib.util.spec_from_file_location(
            "check_models_config_under_test", ROOT / "skills/setup-pstack/scripts/check-models-config.py")
        lint = importlib.util.module_from_spec(lint_spec)
        sys.modules[lint_spec.name] = lint
        lint_spec.loader.exec_module(lint)
        self.assertEqual(set(subagents.EFFORT_LEVELS), lint.CLAUDE_EFFORTS)


if __name__ == "__main__":
    unittest.main()
