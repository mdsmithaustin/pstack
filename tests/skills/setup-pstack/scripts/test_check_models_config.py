import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[4] / "skills" / "setup-pstack"
SCRIPT = SKILL / "scripts" / "check-models-config.py"
EXAMPLE = SKILL / "examples" / "pstack-models.md"

_spec = importlib.util.spec_from_file_location("check_models_config", SCRIPT)
cmc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cmc)
Layer = cmc.Layer

GRAMMAR_EXAMPLE = """---
description: pstack per-role model choices (overrides skill defaults)
---
# comment lines start with #
feature, refactoring: sonnet
bug-fix: opus@xhigh
arena runners: fable@xhigh, opus, sonnet, haiku
swarm workers: inherit-parent

## codex
feature, refactoring: gpt-5.6-terra@high
bug-fix: gpt-5.6-sol@xhigh
arena runners: gpt-5.6-sol@max, gpt-5.6-sol@xhigh, gpt-5.6-terra@high, gpt-5.6-luna@high
"""


def errors_of(findings):
    return [f for f in findings if f[1] == "error"]


def notices_of(findings):
    return [f for f in findings if f[1] == "notice"]


class ShippedShape(unittest.TestCase):
    def test_lints_clean(self):
        text = EXAMPLE.read_text(encoding="utf-8")
        _, findings = cmc.parse(text)
        self.assertEqual(errors_of(findings), [])


class GrammarExample(unittest.TestCase):
    def test_lints_clean_and_parses(self):
        sections, findings = cmc.parse(GRAMMAR_EXAMPLE)
        self.assertEqual(errors_of(findings), [])
        self.assertEqual(sections[""]["bug-fix"], [("opus", "xhigh")])
        self.assertEqual(
            sections["codex"]["arena runners"],
            [
                ("gpt-5.6-sol", "max"),
                ("gpt-5.6-sol", "xhigh"),
                ("gpt-5.6-terra", "high"),
                ("gpt-5.6-luna", "high"),
            ],
        )

    def test_max_and_ultra_produce_notices_not_errors(self):
        _, findings = cmc.parse(GRAMMAR_EXAMPLE)
        self.assertTrue(any("max" in n[2] for n in notices_of(findings)))


class ErrorRules(unittest.TestCase):
    def test_unknown_role(self):
        _, findings = cmc.parse("frobnicate: sonnet\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("unknown role", errs[0][2])

    def test_duplicate_role_in_section(self):
        _, findings = cmc.parse("bug-fix: sonnet\nbug-fix: opus\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("bound twice", errs[0][2])

    def test_unknown_effort(self):
        _, findings = cmc.parse("bug-fix: opus@ludicrous\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("unknown effort", errs[0][2])

    def test_list_on_single_value_role(self):
        _, findings = cmc.parse("bug-fix: opus, sonnet\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("given a list", errs[0][2])

    def test_unknown_section_header(self):
        _, findings = cmc.parse("## nonesuch\nbug-fix: opus\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("unknown section header", errs[0][2])

    def test_duplicate_section(self):
        text = "## codex\nbug-fix: opus\n## codex\nfeature: sonnet\n"
        _, findings = cmc.parse(text)
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("duplicate section", errs[0][2])

    def test_unclosed_frontmatter(self):
        text = "---\ndescription: x\nbug-fix: opus\n"
        _, findings = cmc.parse(text)
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("unclosed frontmatter", errs[0][2])

    def test_empty_entry(self):
        _, findings = cmc.parse("bug-fix: opus,,\n")
        errs = errors_of(findings)
        self.assertTrue(any("empty entry" in e[2] for e in errs))

    def test_minimal_is_not_an_effort(self):
        sections, findings = cmc.parse("bug-fix: gpt-5.6-terra@minimal\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("unknown effort", errs[0][2])
        self.assertNotIn("bug-fix", sections[""])

    def test_invalid_entries_are_omitted_from_sections(self):
        sections, findings = cmc.parse("arena runners: gpt-5.6-terra@ultra, sonnet@high\n")
        self.assertEqual(len(errors_of(findings)), 1)
        self.assertEqual(sections[""]["arena runners"], [("sonnet", "high")])

    def test_ultra_on_gpt56_terra(self):
        _, findings = cmc.parse("bug-fix: gpt-5.6-terra@ultra\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("not supported", errs[0][2])

    def test_ultra_allowed_on_gpt56_sol(self):
        _, findings = cmc.parse("bug-fix: gpt-5.6-sol@ultra\n")
        self.assertEqual(errors_of(findings), [])
        self.assertTrue(any("ultra" in n[2] for n in notices_of(findings)))


class ClaudeCodeSectionEfforts(unittest.TestCase):
    def test_claude_code_section_rejects_none_and_ultra(self):
        text = "## claude-code\ndefault: auto@none\ntrail reviewer: inherit-parent@ultra\n"
        sections, findings = cmc.parse(text)
        errs = errors_of(findings)
        self.assertEqual(len(errs), 2)
        self.assertTrue(all("not a Claude Code level" in e[2] for e in errs))
        self.assertNotIn("default", sections.get("claude-code", {}))
        self.assertNotIn("trail reviewer", sections.get("claude-code", {}))

    def test_flat_none_is_a_claude_code_notice(self):
        text = "default: auto@none\n"
        sections, findings = cmc.parse(text)
        self.assertEqual(errors_of(findings), [])
        self.assertTrue(any(n[2] == "Claude Code cannot use none or ultra, so it runs `default` at the session effort" for n in notices_of(findings)))
        self.assertEqual(sections[""]["default"], [("auto", "none")])

    def test_flat_none_overridden_by_claude_code_section_is_not_a_notice(self):
        text = "default: auto@none\n\n## claude-code\ndefault: auto@high\n"
        sections, findings = cmc.parse(text)
        self.assertEqual(errors_of(findings), [])
        self.assertFalse(any(n[2] == "Claude Code cannot use none or ultra, so it runs `default` at the session effort" for n in notices_of(findings)))
        self.assertEqual(sections[""]["default"], [("auto", "none")])
        self.assertEqual(sections["claude-code"]["default"], [("auto", "high")])

    def test_flat_none_on_two_roles_gets_one_notice_each(self):
        text = "default, trail reviewer: auto@none\n"
        sections, findings = cmc.parse(text)
        self.assertEqual(errors_of(findings), [])
        notices = [n[2] for n in notices_of(findings)]
        self.assertEqual(len(notices), 2)
        self.assertIn("Claude Code cannot use none or ultra, so it runs `default` at the session effort", notices)
        self.assertIn("Claude Code cannot use none or ultra, so it runs `trail reviewer` at the session effort", notices)

    def test_codex_section_is_unaffected(self):
        text = "## codex\ntrail reviewer: gpt-5.6-sol@ultra\n"
        sections, findings = cmc.parse(text)
        self.assertEqual(errors_of(findings), [])
        self.assertEqual(sections["codex"]["trail reviewer"], [("gpt-5.6-sol", "ultra")])


class ReflectShorthand(unittest.TestCase):
    def test_expands_bare_labels(self):
        sections, findings = cmc.parse("reflect judgment, divergent, synthesizer: fable\n")
        self.assertEqual(errors_of(findings), [])
        self.assertEqual(sections[""]["reflect judgment"], [("fable", None)])
        self.assertEqual(sections[""]["reflect divergent"], [("fable", None)])
        self.assertEqual(sections[""]["reflect synthesizer"], [("fable", None)])


class TrailReviewerAndDefaultRoles(unittest.TestCase):
    def test_lint_clean_in_flat_section(self):
        text = "trail reviewer: opus\ndefault: inherit-parent\n"
        sections, findings = cmc.parse(text)
        self.assertEqual(errors_of(findings), [])
        self.assertEqual(sections[""]["trail reviewer"], [("opus", None)])
        self.assertEqual(sections[""]["default"], [("inherit-parent", None)])

    def test_lint_clean_in_codex_section(self):
        text = (
            "## codex\n"
            "trail reviewer: gpt-5.6-terra@xhigh\n"
            "default: gpt-5.6-terra@high\n"
        )
        sections, findings = cmc.parse(text)
        self.assertEqual(errors_of(findings), [])
        self.assertEqual(sections["codex"]["trail reviewer"], [("gpt-5.6-terra", "xhigh")])
        self.assertEqual(sections["codex"]["default"], [("gpt-5.6-terra", "high")])

    def test_default_rejects_list(self):
        _, findings = cmc.parse("default: opus, sonnet\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("given a list", errs[0][2])


class CliExitCodes(unittest.TestCase):
    def _run(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pstack-models.md"
            path.write_text(text, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                capture_output=True,
                text=True,
            )

    def test_valid_file_exits_zero(self):
        result = self._run(GRAMMAR_EXAMPLE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_invalid_file_exits_one(self):
        result = self._run("frobnicate: sonnet\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("error", result.stdout)

    def test_example_file_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(EXAMPLE)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


USER_FILE = """feature, refactoring: sonnet@high
bug-fix: opus@high
how explorer: sonnet@medium
architect runners: fable@high, opus@xhigh, sonnet@high
default: inherit-parent

## codex
feature, refactoring: gpt-6-sol@high
swarm workers: gpt-6-luna@xhigh
default: inherit-parent
"""


class Resolve(unittest.TestCase):
    def resolve(self, harness, *roles, user=None, workspace=None):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            if workspace is not None:
                (project / ".agents").mkdir()
                (project / ".agents" / "pstack-models.md").write_text(workspace, encoding="utf-8")
            user_file = Path(tmp) / "user-models.md"
            if user is not None:
                user_file.write_text(user, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "--resolve", "--harness", harness,
                    "--project", str(project), "--user-file", str(user_file), *roles,
                ],
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_claude_code_reads_user_flat_lines(self):
        def arm(role, model, effort, source, n=1):
            return {"role": role, "arm": n, "model": model, "effort": effort, "source": source}

        self.assertEqual(
            self.resolve(
                "claude-code", "feature", "how explorer", "architect runners",
                "default", "swarm workers", user=USER_FILE,
            ),
            [
                arm("feature", "sonnet", "high", "user flat"),
                arm("how explorer", "sonnet", "medium", "user flat"),
                arm("architect runners", "fable", "high", "user flat", 1),
                arm("architect runners", "opus", "xhigh", "user flat", 2),
                arm("architect runners", "sonnet", "high", "user flat", 3),
                arm("default", "inherit-parent", "inherit-parent", "user flat"),
                arm("swarm workers", "sonnet", "inherit-parent", "skill default"),
            ],
        )

    def test_codex_prefers_its_section_and_translates_aliases(self):
        self.assertEqual(
            self.resolve("codex", "feature", "swarm workers", "bug-fix", "default", user=USER_FILE),
            [
                {"role": "feature", "arm": 1, "model": "gpt-6-sol", "effort": "high", "source": "user ## codex"},
                {"role": "swarm workers", "arm": 1, "model": "gpt-6-luna", "effort": "xhigh", "source": "user ## codex"},
                {
                    "role": "bug-fix", "arm": 1, "model": "gpt-5.6-sol", "effort": "high",
                    "source": "user flat", "notes": ["opus translated to gpt-5.6-sol"],
                },
                {"role": "default", "arm": 1, "model": "inherit-parent", "effort": "inherit-parent", "source": "user ## codex"},
            ],
        )

    def test_entry_is_atomic_across_layers(self):
        self.assertEqual(
            self.resolve("claude-code", "feature", user=USER_FILE, workspace="feature, refactoring: opus\n"),
            [{"role": "feature", "arm": 1, "model": "opus", "effort": "inherit-parent", "source": "workspace flat"}],
        )

    def test_user_section_beats_workspace_flat(self):
        self.assertEqual(
            self.resolve("codex", "feature", user=USER_FILE, workspace="feature, refactoring: opus\n"),
            [{"role": "feature", "arm": 1, "model": "gpt-6-sol", "effort": "high", "source": "user ## codex"}],
        )

    def test_workspace_section_beats_everything(self):
        self.assertEqual(
            self.resolve(
                "codex", "feature", user=USER_FILE,
                workspace="feature, refactoring: opus\n\n## codex\nfeature, refactoring: gpt-6-terra@low\n",
            ),
            [{"role": "feature", "arm": 1, "model": "gpt-6-terra", "effort": "low", "source": "workspace ## codex"}],
        )

    def test_translation_effort_applies_only_when_none_is_written(self):
        [bare] = self.resolve("codex", "feature", user="feature, refactoring: sonnet\n")
        self.assertEqual(
            bare,
            {
                "role": "feature", "arm": 1, "model": "gpt-5.6-terra", "effort": "high",
                "source": "user flat", "notes": ["sonnet translated to gpt-5.6-terra@high"],
            },
        )
        [pinned] = self.resolve("codex", "feature", user="feature, refactoring: opus@medium\n")
        self.assertEqual(pinned["model"], "gpt-5.6-sol")
        self.assertEqual(pinned["effort"], "medium")

    def test_codex_floor_depends_on_the_role(self):
        [bug] = self.resolve("codex", "bug-fix", user="## codex\nbug-fix: gpt-6-sol\n")
        self.assertEqual((bug["model"], bug["effort"], bug["source"]), ("gpt-6-sol", "xhigh", "user ## codex"))
        [feature] = self.resolve("codex", "feature", user="feature, refactoring: gpt-6-sol\n")
        self.assertEqual((feature["model"], feature["effort"], feature["source"]), ("gpt-6-sol", "high", "user flat"))

    def test_unusable_model_inherits_but_keeps_written_effort(self):
        [feature] = self.resolve("claude-code", "feature", user="feature, refactoring: gpt-6-sol@high\n")
        self.assertEqual(
            feature,
            {
                "role": "feature", "arm": 1, "model": "inherit-parent", "effort": "high",
                "source": "user flat", "notes": ["gpt-6-sol is not usable on claude-code"],
            },
        )

    def test_unusable_effort_inherits_but_keeps_model(self):
        layers = [Layer("user flat", {"feature": [("sonnet", "none")]})]
        self.assertEqual(
            [arm.to_json() for arm in cmc.resolve_role("feature", "claude-code", layers)],
            ['{"role": "feature", "arm": 1, "model": "sonnet", "effort": "inherit-parent",'
             ' "source": "user flat", "notes": ["effort none is not usable on claude-code"]}'],
        )

    def test_none_effort_on_a_foreign_model_drops_both_fields_on_claude_code(self):
        [feature] = self.resolve("claude-code", "feature", user="feature, refactoring: gpt-6-sol@none\n")
        self.assertEqual(
            (feature["model"], feature["effort"], feature["notes"]),
            (
                "inherit-parent", "inherit-parent",
                ["gpt-6-sol is not usable on claude-code", "effort none is not usable on claude-code"],
            ),
        )

    def test_ultra_is_refused_where_the_model_cannot_use_it(self):
        layers = [Layer("user flat", {"feature": [("gpt-5.6-terra", "ultra")]})]
        [arm] = cmc.resolve_role("feature", "codex", layers)
        self.assertEqual(
            (arm.model, arm.effort, arm.notes),
            ("gpt-5.6-terra", "high", ("effort ultra is not usable on codex",)),
        )
        [arm] = cmc.resolve_role("bug-fix", "codex", [Layer("user flat", {"bug-fix": [("gpt-5.6-terra", "ultra")]})])
        self.assertEqual((arm.model, arm.effort), ("gpt-5.6-terra", "xhigh"))
        [arm] = cmc.resolve_role("feature", "codex", [Layer("user flat", {"feature": [("gpt-5.6-sol", "ultra")]})])
        self.assertEqual((arm.model, arm.effort, arm.notes), ("gpt-5.6-sol", "ultra", ()))

    def test_panel_comes_from_one_line(self):
        user = USER_FILE + "arena runners: fable@high, opus@xhigh, sonnet@high\n"
        arms = self.resolve("claude-code", "arena runners", user=user, workspace="arena runners: opus\n")
        self.assertEqual(
            arms,
            [{"role": "arena runners", "arm": 1, "model": "opus", "effort": "inherit-parent", "source": "workspace flat"}],
        )

    def test_hermes_has_no_alias_translation(self):
        [feature] = self.resolve("hermes", "feature", user="feature, refactoring: sonnet@high\n")
        self.assertEqual(
            feature,
            {
                "role": "feature", "arm": 1, "model": "inherit-parent", "effort": "high",
                "source": "user flat", "notes": ["sonnet is not usable on hermes"],
            },
        )

    def test_hermes_inherits_effort_with_the_parent_model(self):
        [default] = self.resolve("hermes", "default", user=USER_FILE)
        self.assertEqual((default["model"], default["effort"]), ("inherit-parent", "inherit-parent"))

    def test_no_role_resolves_every_role_alphabetically_from_the_skill_default(self):
        arms = self.resolve("claude-code")
        roles = []
        for arm in arms:
            if arm["role"] not in roles:
                roles.append(arm["role"])
        self.assertEqual(roles, sorted(cmc.ROLES))
        self.assertEqual({arm["source"] for arm in arms}, {"skill default"})
        self.assertEqual(len([a for a in arms if a["role"] == "arena runners"]), 3)

    def test_a_missing_user_file_is_skipped(self):
        [feature] = self.resolve("claude-code", "feature")
        self.assertEqual(
            feature,
            {"role": "feature", "arm": 1, "model": "sonnet", "effort": "inherit-parent", "source": "skill default"},
        )


class ResolveExitCodes(unittest.TestCase):
    def run_resolve(self, *args, user=None):
        with tempfile.TemporaryDirectory() as tmp:
            user_file = Path(tmp) / "user-models.md"
            if user is not None:
                user_file.write_text(user, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--resolve", "--project", tmp, "--user-file", str(user_file), *args],
                capture_output=True,
                text=True,
            )
        return result, user_file

    def test_unknown_role_exits_two(self):
        result, _ = self.run_resolve("--harness", "codex", "frobnicate")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown role 'frobnicate'", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_missing_harness_exits_two(self):
        result, _ = self.run_resolve("feature")
        self.assertEqual(result.returncode, 2)

    def test_unknown_harness_exits_two(self):
        result, _ = self.run_resolve("--harness", "grok", "feature")
        self.assertEqual(result.returncode, 2)

    def test_lint_error_exits_one_without_resolving(self):
        result, user_file = self.run_resolve("--harness", "codex", "feature", user="feature: sonnet@turbo\n")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr,
            f"{user_file}:1: error: unknown effort 'turbo' for model 'sonnet'\n",
        )


if __name__ == "__main__":
    unittest.main()
