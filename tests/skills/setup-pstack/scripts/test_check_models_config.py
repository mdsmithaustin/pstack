import importlib.util
import json
import os
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
feature, refactoring: gpt-6-sol@high
bug-fix: gpt-6-sol@xhigh
arena runners: gpt-6-sol@max, gpt-6-sol@xhigh, gpt-6-astra@high, gpt-6-luna@high
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
                ("gpt-6-sol", "max"),
                ("gpt-6-sol", "xhigh"),
                ("gpt-6-astra", "high"),
                ("gpt-6-luna", "high"),
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
        sections, findings = cmc.parse("bug-fix: gpt-6-luna@minimal\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("unknown effort", errs[0][2])
        self.assertNotIn("bug-fix", sections[""])

    def test_invalid_entries_are_omitted_from_sections(self):
        sections, findings = cmc.parse("arena runners: gpt-6-astra@none, sonnet@high\n")
        self.assertEqual(len(errors_of(findings)), 1)
        self.assertEqual(sections[""]["arena runners"], [("sonnet", "high")])

    def test_ultra_is_refused_on_gpt6_luna(self):
        sections, findings = cmc.parse("## codex\nbug-fix: gpt-6-luna@ultra\n")
        self.assertEqual(
            findings,
            [(2, "error", "effort 'ultra' not supported by model 'gpt-6-luna'")],
        )
        self.assertNotIn("bug-fix", sections["codex"])

    def test_ultra_allowed_on_gpt6_sol(self):
        _, findings = cmc.parse("## codex\nbug-fix: gpt-6-sol@ultra\n")
        self.assertEqual(findings, [(2, "notice", "gpt-6-sol@ultra pins an expensive tier")])

    def test_none_is_refused_on_the_releases_that_reject_it(self):
        for model in ("gpt-6.1-sol", "gpt-6-astra", "gpt-6-sol", "gpt-6-luna"):
            with self.subTest(model=model):
                _, findings = cmc.parse(f"bug-fix: {model}@none\n")
                self.assertEqual(
                    errors_of(findings),
                    [(1, "error", f"effort 'none' not supported by model '{model}'")],
                )

    def test_unknown_model_gets_no_effort_check(self):
        sections, findings = cmc.parse("bug-fix: gpt-9-terra@ultra\n")
        self.assertEqual(errors_of(findings), [])
        self.assertEqual(sections[""]["bug-fix"], [("gpt-9-terra", "ultra")])


class ClaudeCodeSectionEfforts(unittest.TestCase):
    def test_claude_code_section_rejects_none_and_ultra(self):
        text = "## claude-code\ndefault: auto@none\ntrail reviewer: inherit-parent@ultra\n"
        sections, findings = cmc.parse(text)
        self.assertEqual(
            errors_of(findings),
            [
                (2, "error", "effort 'none' is not a Claude Code level (low, medium, high, xhigh, max)"),
                (3, "error", "effort 'ultra' is not a Claude Code level (low, medium, high, xhigh, max)"),
            ],
        )
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

    def test_grok_section_rejects_ultra(self):
        text = "## grok\ntrail reviewer: grok-4.6@ultra\n"
        sections, findings = cmc.parse(text)
        self.assertEqual(
            errors_of(findings),
            [(2, "error", "effort 'ultra' is not a Grok Build level (low, medium, high, xhigh)")],
        )
        self.assertNotIn("trail reviewer", sections["grok"])

    def test_grok_section_rejects_max_and_none(self):
        for model, effort in (("grok-4.6", "max"), ("grok-4.6", "none")):
            with self.subTest(effort=effort):
                sections, findings = cmc.parse(f"## grok\ntrail reviewer: {model}@{effort}\n")
                self.assertEqual(
                    errors_of(findings),
                    [(2, "error", f"effort '{effort}' is not a Grok Build level (low, medium, high, xhigh)")],
                )
                self.assertNotIn("trail reviewer", sections["grok"])

    def test_grok_section_takes_its_levels(self):
        sections, findings = cmc.parse("## grok\ntrail reviewer: grok-4.7-build-fast@xhigh\n")
        self.assertEqual(findings, [])
        self.assertEqual(sections["grok"]["trail reviewer"], [("grok-4.7-build-fast", "xhigh")])

    def test_grok_4_7_rejects_an_effort_its_catalog_lacks(self):
        _, findings = cmc.parse("## grok\ntrail reviewer: grok-4.7@max\n")
        self.assertEqual(
            errors_of(findings),
            [(2, "error", "effort 'max' not supported by model 'grok-4.7'")],
        )

    def test_grok_build_fast_rejects_max(self):
        sections, findings = cmc.parse("## grok\ntrail reviewer: grok-4.7-build-fast@max\n")
        self.assertEqual(
            errors_of(findings),
            [(2, "error", "effort 'max' not supported by model 'grok-4.7-build-fast'")],
        )
        self.assertNotIn("trail reviewer", sections["grok"])

    def test_codex_section_is_unaffected(self):
        text = "## codex\ntrail reviewer: gpt-6-sol@ultra\n"
        sections, findings = cmc.parse(text)
        self.assertEqual(errors_of(findings), [])
        self.assertEqual(sections["codex"]["trail reviewer"], [("gpt-6-sol", "ultra")])


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
            "trail reviewer: gpt-6-sol@xhigh\n"
            "default: gpt-6-sol@high\n"
        )
        sections, findings = cmc.parse(text)
        self.assertEqual(errors_of(findings), [])
        self.assertEqual(sections["codex"]["trail reviewer"], [("gpt-6-sol", "xhigh")])
        self.assertEqual(sections["codex"]["default"], [("gpt-6-sol", "high")])

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


FULL_LEVELS = ("low", "medium", "high", "xhigh", "max", "ultra")
LUNA_LEVELS = FULL_LEVELS[:-1]


def catalog_entry(slug, visibility="list", levels=None):
    if levels is None:
        levels = LUNA_LEVELS if slug.endswith("-luna") else FULL_LEVELS
    return {
        "slug": slug,
        "visibility": visibility,
        "supported_reasoning_levels": [{"effort": effort, "description": effort} for effort in levels],
    }


def catalog_json(*models):
    entries = []
    for model in models:
        if isinstance(model, dict):
            entries.append(model)
        else:
            entries.append(catalog_entry(*(model if isinstance(model, tuple) else (model,))))
    return json.dumps({"models": entries})


def read_listed(catalog_text):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "models_cache.json"
        path.write_text(catalog_text, encoding="utf-8")
        return cmc.listed_models(path)


def run_script(args, codex_catalog=None):
    with tempfile.TemporaryDirectory() as codex_home:
        if codex_catalog is not None:
            (Path(codex_home) / "models_cache.json").write_text(codex_catalog, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env={**os.environ, "CODEX_HOME": codex_home},
        )


class ResolveRunner:
    def resolve(self, harness, *roles, user=None, workspace=None, codex_catalog=None, work_model=None):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            if workspace is not None:
                (project / ".agents").mkdir()
                (project / ".agents" / "pstack-models.md").write_text(workspace, encoding="utf-8")
            user_file = Path(tmp) / "user-models.md"
            if user is not None:
                user_file.write_text(user, encoding="utf-8")
            result = run_script(
                [
                    "--resolve", "--harness", harness,
                    "--project", str(project), "--user-file", str(user_file),
                    *(["--work-model", work_model] if work_model else []), *roles,
                ],
                codex_catalog,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines()]


class Resolve(ResolveRunner, unittest.TestCase):
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

    def test_routine_ships_a_medium_effort_scan_model_on_every_harness(self):
        def routine(harness):
            [arm] = self.resolve(harness, "routine")
            return arm

        self.assertEqual(routine("claude-code"), {
            "role": "routine", "arm": 1, "model": "sonnet", "effort": "medium", "source": "skill default",
        })
        self.assertEqual(routine("codex"), {
            "role": "routine", "arm": 1, "model": "gpt-6-luna", "effort": "medium", "source": "skill default ## codex",
        })
        self.assertEqual(routine("grok"), {
            "role": "routine", "arm": 1, "model": "grok-4.7", "effort": "medium", "source": "skill default",
            "notes": ["sonnet translated to grok-4.7"],
        })
        self.assertEqual(routine("hermes"), {
            "role": "routine", "arm": 1, "model": "inherit-parent", "effort": "medium", "source": "skill default",
            "notes": ["sonnet is not usable on hermes"],
        })

    def test_a_routine_line_overrides_the_shipped_default(self):
        [arm] = self.resolve("claude-code", "routine", user="routine: haiku@low\n")
        self.assertEqual((arm["model"], arm["effort"], arm["source"]), ("haiku", "low", "user flat"))

    def test_codex_prefers_its_section_and_translates_aliases(self):
        self.assertEqual(
            self.resolve("codex", "feature", "swarm workers", "bug-fix", "default", user=USER_FILE),
            [
                {"role": "feature", "arm": 1, "model": "gpt-6-sol", "effort": "high", "source": "user ## codex"},
                {"role": "swarm workers", "arm": 1, "model": "gpt-6-luna", "effort": "xhigh", "source": "user ## codex"},
                {
                    "role": "bug-fix", "arm": 1, "model": "gpt-6-sol", "effort": "high",
                    "source": "user flat", "notes": ["opus translated to gpt-6-sol"],
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
                workspace="feature, refactoring: opus\n\n## codex\nfeature, refactoring: gpt-6-luna@low\n",
            ),
            [{"role": "feature", "arm": 1, "model": "gpt-6-luna", "effort": "low", "source": "workspace ## codex"}],
        )

    def test_translation_effort_applies_only_when_none_is_written(self):
        [bare] = self.resolve("codex", "feature", user="feature, refactoring: sonnet\n")
        self.assertEqual(
            bare,
            {
                "role": "feature", "arm": 1, "model": "gpt-6-sol", "effort": "high",
                "source": "user flat", "notes": ["sonnet translated to gpt-6-sol@high"],
            },
        )
        [pinned] = self.resolve("codex", "feature", user="feature, refactoring: opus@medium\n")
        self.assertEqual(pinned["model"], "gpt-6-sol")
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
        [feature] = self.resolve("claude-code", "feature", user="feature, refactoring: gpt-9-terra@none\n")
        self.assertEqual(
            (feature["model"], feature["effort"], feature["notes"]),
            (
                "inherit-parent", "inherit-parent",
                ["gpt-9-terra is not usable on claude-code", "effort none is not usable on claude-code"],
            ),
        )

    def test_ultra_is_kept_on_the_models_that_take_it(self):
        for model in ("gpt-6.1-sol", "gpt-6-sol", "gpt-6-astra"):
            with self.subTest(model=model):
                [arm] = cmc.resolve_role("feature", "codex", [Layer("user flat", {"feature": [(model, "ultra")]})])
                self.assertEqual((arm.model, arm.effort, arm.notes), (model, "ultra", ()))

    def test_ultra_is_dropped_on_luna(self):
        [arm] = cmc.resolve_role("feature", "codex", [Layer("user flat", {"feature": [("gpt-6-luna", "ultra")]})])
        self.assertEqual(
            (arm.model, arm.effort, arm.notes),
            ("gpt-6-luna", "high", ("effort ultra is not usable with gpt-6-luna",)),
        )

    def test_none_is_refused_on_every_gpt6_release(self):
        for model in ("gpt-6.1-sol", "gpt-6-astra", "gpt-6-sol", "gpt-6-luna"):
            with self.subTest(model=model):
                [arm] = cmc.resolve_role("feature", "codex", [Layer("user flat", {"feature": [(model, "none")]})])
                self.assertEqual(
                    (arm.model, arm.effort, arm.notes),
                    (model, "high", (f"effort none is not usable with {model}",)),
                )
                [arm] = cmc.resolve_role("bug-fix", "codex", [Layer("user flat", {"bug-fix": [(model, "none")]})])
                self.assertEqual((arm.model, arm.effort), (model, "xhigh"))

    def test_panel_comes_from_one_line(self):
        user = USER_FILE + "arena runners: fable@high, opus@xhigh, sonnet@high\n"
        arms = self.resolve("claude-code", "arena runners", user=user, workspace="arena runners: opus, sonnet\n")
        self.assertEqual(
            arms,
            [
                {"role": "arena runners", "arm": 1, "model": "opus", "effort": "inherit-parent", "source": "workspace flat"},
                {"role": "arena runners", "arm": 2, "model": "sonnet", "effort": "inherit-parent", "source": "workspace flat"},
            ],
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

    def test_codex_reads_the_shipped_default_section_before_its_flat_lines(self):
        [reviewer] = self.resolve("codex", "trail reviewer")
        self.assertEqual(
            reviewer,
            {"role": "trail reviewer", "arm": 1, "model": "gpt-6-astra", "effort": "high", "source": "skill default ## codex"},
        )

    def test_a_role_the_user_names_still_beats_the_shipped_section(self):
        [feature] = self.resolve("codex", "feature", user="feature, refactoring: sonnet@high\n")
        self.assertEqual(
            (feature["model"], feature["effort"], feature["source"]),
            ("gpt-6-sol", "high", "user flat"),
        )

    def test_a_missing_user_file_is_skipped(self):
        [feature] = self.resolve("claude-code", "feature")
        self.assertEqual(
            feature,
            {"role": "feature", "arm": 1, "model": "sonnet", "effort": "inherit-parent", "source": "skill default"},
        )


class CodexListedRelease(ResolveRunner, unittest.TestCase):
    def only(self, role, user, catalog):
        [arm] = self.resolve("codex", role, user=user, codex_catalog=catalog)
        return arm

    def test_newest_listed_release_wins(self):
        arm = self.only("feature", "feature, refactoring: gpt-6-sol@high\n", catalog_json("gpt-6.1-sol", "gpt-6-sol"))
        self.assertEqual(
            arm,
            {
                "role": "feature", "arm": 1, "model": "gpt-6.1-sol", "effort": "high", "source": "user flat",
                "notes": ["gpt-6-sol runs as gpt-6.1-sol, the newest release this Codex lists with effort high"],
            },
        )

    def test_shipped_default_follows_the_catalog(self):
        arm = self.only("feature", None, catalog_json("gpt-6.1-sol", "gpt-6-sol"))
        self.assertEqual(
            (arm["model"], arm["effort"], arm["source"]),
            ("gpt-6.1-sol", "high", "skill default ## codex"),
        )

    def test_a_release_whose_catalog_levels_lack_the_effort_is_skipped(self):
        newer = catalog_entry("gpt-6.1-luna", levels=("low", "medium", "high"))
        arm = self.only("swarm workers", "## codex\nswarm workers: gpt-6-luna@xhigh\n", catalog_json(newer, "gpt-6-luna"))
        self.assertEqual((arm["model"], arm["effort"], arm.get("notes")), ("gpt-6-luna", "xhigh", None))

    def test_either_spelling_of_the_tier_keeps_a_written_effort_the_older_release_takes(self):
        newer = catalog_entry("gpt-6.1-luna", levels=("low", "medium", "high"))
        catalog = catalog_json(newer, "gpt-6-luna")
        arm = self.only("swarm workers", "## codex\nswarm workers: gpt-6-luna@xhigh\n", catalog)
        self.assertEqual((arm["model"], arm["effort"], arm.get("notes")), ("gpt-6-luna", "xhigh", None))
        arm = self.only("swarm workers", "## codex\nswarm workers: gpt-6.1-luna@xhigh\n", catalog)
        self.assertEqual(
            (arm["model"], arm["effort"], arm["notes"]),
            (
                "gpt-6-luna", "xhigh",
                ["gpt-6.1-luna runs as gpt-6-luna, the newest release this Codex lists with effort xhigh"],
            ),
        )

    def test_a_written_effort_no_listed_release_takes_still_drops(self):
        newer = catalog_entry("gpt-6.1-luna", levels=("low", "medium", "high"))
        older = catalog_entry("gpt-6-luna", levels=("low", "medium", "high"))
        catalog = catalog_json(newer, older)
        for written in ("gpt-6.1-luna", "gpt-6-luna"):
            with self.subTest(written=written):
                arm = self.only("swarm workers", f"## codex\nswarm workers: {written}@xhigh\n", catalog)
                self.assertEqual(
                    (arm["model"], arm["effort"]),
                    ("gpt-6.1-luna", "high"),
                )
                self.assertEqual(
                    arm["notes"][0], f"effort xhigh is not usable with {written}",
                )

    def test_a_release_whose_catalog_levels_include_the_effort_is_taken(self):
        arm = self.only("swarm workers", "## codex\nswarm workers: gpt-6-luna@xhigh\n", catalog_json("gpt-6.1-luna", "gpt-6-luna"))
        self.assertEqual(
            (arm["model"], arm["effort"], arm["notes"]),
            ("gpt-6.1-luna", "xhigh", ["gpt-6-luna runs as gpt-6.1-luna, the newest release this Codex lists with effort xhigh"]),
        )

    def test_an_effort_the_catalog_omits_for_the_model_drops_to_the_role_floor(self):
        sol = catalog_entry("gpt-6-sol", levels=("low", "medium", "high", "xhigh"))
        for role, user, floor in (
            ("feature", "feature, refactoring: gpt-6-sol@max\n", "high"),
            ("bug-fix", "bug-fix: gpt-6-sol@max\n", "xhigh"),
        ):
            with self.subTest(role=role):
                arm = self.only(role, user, catalog_json(sol))
                self.assertEqual(
                    (arm["model"], arm["effort"], arm["notes"]),
                    ("gpt-6-sol", floor, ["effort max is not usable with gpt-6-sol"]),
                )

    def test_a_floor_the_catalog_omits_drops_to_the_models_highest_effort_below_it(self):
        sol = catalog_entry("gpt-6-sol", levels=("low", "medium", "high"))
        arm = self.only("bug-fix", "## codex\nbug-fix: gpt-6-sol\n", catalog_json(sol))
        self.assertEqual(
            (arm["model"], arm["effort"], arm["notes"]),
            ("gpt-6-sol", "high", ["effort xhigh is not usable with gpt-6-sol"]),
        )
        arm = self.only("bug-fix", "## codex\nbug-fix: gpt-6-sol\n", catalog_json(catalog_entry("gpt-6-sol", levels=("low", "medium"))))
        self.assertEqual(
            (arm["model"], arm["effort"], arm["notes"]),
            ("gpt-6-sol", "medium", ["effort xhigh is not usable with gpt-6-sol"]),
        )

    def test_a_floor_the_model_takes_is_unchanged(self):
        sol = catalog_entry("gpt-6-sol", levels=("low", "medium", "high"))
        arm = self.only("feature", "## codex\nfeature, refactoring: gpt-6-sol\n", catalog_json(sol))
        self.assertEqual((arm["model"], arm["effort"], arm.get("notes")), ("gpt-6-sol", "high", None))

    def test_a_floor_with_nothing_below_it_rises_to_the_models_lowest_effort(self):
        sol = catalog_entry("gpt-6-sol", levels=("xhigh", "max"))
        arm = self.only("feature", "## codex\nfeature, refactoring: gpt-6-sol\n", catalog_json(sol))
        self.assertEqual(
            (arm["model"], arm["effort"], arm["notes"]),
            ("gpt-6-sol", "xhigh", ["effort high is not usable with gpt-6-sol"]),
        )

    def test_a_dropped_written_effort_and_a_dropped_floor_both_leave_a_note(self):
        sol = catalog_entry("gpt-6-sol", levels=("low", "medium", "high"))
        arm = self.only("bug-fix", "## codex\nbug-fix: gpt-6-sol@max\n", catalog_json(sol))
        self.assertEqual(
            (arm["effort"], arm["notes"]),
            ("high", ["effort max is not usable with gpt-6-sol", "effort xhigh is not usable with gpt-6-sol"]),
        )

    def test_a_written_effort_that_is_also_the_floor_is_noted_once(self):
        sol = catalog_entry("gpt-6-sol", levels=("low", "medium", "high"))
        arm = self.only("bug-fix", "## codex\nbug-fix: gpt-6-sol@xhigh\n", catalog_json(sol))
        self.assertEqual(
            (arm["model"], arm["effort"], arm["notes"]),
            ("gpt-6-sol", "high", ["effort xhigh is not usable with gpt-6-sol"]),
        )

    def test_a_catalog_of_only_efforts_pstack_does_not_know_keeps_the_floor(self):
        sol = catalog_entry("gpt-6-sol", levels=("minimal",))
        arm = self.only("bug-fix", "## codex\nbug-fix: gpt-6-sol\n", catalog_json(sol))
        self.assertEqual((arm["model"], arm["effort"], arm.get("notes")), ("gpt-6-sol", "xhigh", None))

    def test_an_effort_the_catalog_adds_beyond_the_table_is_kept(self):
        listed = read_listed(catalog_json(catalog_entry("gpt-6-luna", levels=LUNA_LEVELS + ("ultra",))))
        layers = [Layer("user flat", {"feature": [("gpt-6-luna", "ultra")]})]
        [arm] = cmc.resolve_role("feature", "codex", layers, listed)
        self.assertEqual((arm.model, arm.effort, arm.notes), ("gpt-6-luna", "ultra", ()))

    def test_an_entry_with_empty_or_missing_levels_falls_back_to_the_table_row(self):
        empty = catalog_entry("gpt-6-sol", levels=())
        missing = {"slug": "gpt-6-sol", "visibility": "list"}
        for entry in (empty, missing):
            with self.subTest(entry=entry):
                listed = read_listed(catalog_json(entry))
                layers = [Layer("user flat", {"feature": [("gpt-6-sol", "none")]})]
                [arm] = cmc.resolve_role("feature", "codex", layers, listed)
                self.assertEqual(
                    (arm.model, arm.effort, arm.notes),
                    ("gpt-6-sol", "high", ("effort none is not usable with gpt-6-sol",)),
                )
                arm = self.only("feature", "feature, refactoring: gpt-6-sol@ultra\n", catalog_json(entry))
                self.assertEqual((arm["model"], arm["effort"], arm.get("notes")), ("gpt-6-sol", "ultra", None))

    def test_a_newer_release_with_no_levels_is_judged_by_the_table(self):
        newer = catalog_entry("gpt-6.1-sol", levels=())
        arm = self.only("feature", "feature, refactoring: gpt-6-sol@ultra\n", catalog_json(newer, "gpt-6-sol"))
        self.assertEqual((arm["model"], arm["effort"]), ("gpt-6.1-sol", "ultra"))
        arm = self.only("feature", "feature, refactoring: gpt-6-sol@high\n", catalog_json(newer, "gpt-6-sol"))
        self.assertEqual((arm["model"], arm["effort"]), ("gpt-6.1-sol", "high"))

    def test_an_older_release_stands_in_for_one_the_account_lacks(self):
        arm = self.only("feature", "feature, refactoring: gpt-6.1-luna@high\n", catalog_json("gpt-6-luna", "gpt-6.1-sol"))
        self.assertEqual(
            (arm["model"], arm["effort"], arm["notes"]),
            ("gpt-6-luna", "high", ["gpt-6.1-luna runs as gpt-6-luna, the newest release this Codex lists with effort high"]),
        )

    def test_a_model_the_catalog_lacks_stays_as_written(self):
        arm = self.only("feature", "feature, refactoring: gpt-6.1-luna@high\n", catalog_json("gpt-6.1-sol"))
        self.assertEqual((arm["model"], arm.get("notes")), ("gpt-6.1-luna", None))

    def test_a_hidden_entry_does_not_count(self):
        arm = self.only(
            "feature", "feature, refactoring: gpt-6-sol@high\n",
            catalog_json(("gpt-6.1-sol", "hide"), "gpt-6-sol"),
        )
        self.assertEqual((arm["model"], arm.get("notes")), ("gpt-6-sol", None))

    def test_an_entry_without_visibility_counts_as_listed(self):
        catalog = json.dumps({"models": [{"slug": "gpt-6.1-sol"}, {"slug": "gpt-6-sol"}]})
        arm = self.only("feature", "feature, refactoring: gpt-6-sol@high\n", catalog)
        self.assertEqual(arm["model"], "gpt-6.1-sol")

    def test_no_catalog_changes_nothing(self):
        arm = self.only("feature", "feature, refactoring: gpt-6-sol@high\n", None)
        self.assertEqual((arm["model"], arm.get("notes")), ("gpt-6-sol", None))

    def test_a_malformed_catalog_changes_nothing(self):
        for text in ("{not json", "[]", '{"models": 3}', '{"models": ["gpt-6.1-sol"]}', '{"models": [{"visibility": "list"}]}'):
            with self.subTest(text=text):
                arm = self.only("feature", "feature, refactoring: gpt-6-sol@high\n", text)
                self.assertEqual((arm["model"], arm.get("notes")), ("gpt-6-sol", None))

    def test_translated_alias_gets_both_notes_in_order(self):
        arm = self.only("bug-fix", "bug-fix: opus\n", catalog_json("gpt-6.1-sol", "gpt-6-sol"))
        self.assertEqual(
            arm,
            {
                "role": "bug-fix", "arm": 1, "model": "gpt-6.1-sol", "effort": "xhigh", "source": "user flat",
                "notes": [
                    "opus translated to gpt-6-sol@xhigh",
                    "gpt-6-sol runs as gpt-6.1-sol, the newest release this Codex lists with effort xhigh",
                ],
            },
        )

    def test_inherit_parent_is_left_alone(self):
        arm = self.only("default", "default: inherit-parent\n", catalog_json("gpt-6.1-sol"))
        self.assertEqual((arm["model"], arm["effort"], arm.get("notes")), ("inherit-parent", "inherit-parent", None))

    def test_a_panel_is_picked_arm_by_arm(self):
        user = "arena runners: gpt-6-sol@max, gpt-6-luna@xhigh, gpt-6-astra@high\n"
        arms = self.resolve("codex", "arena runners", user=user, codex_catalog=catalog_json("gpt-6.1-sol", "gpt-6-sol", "gpt-6-luna", "gpt-6-astra"))
        self.assertEqual([a["model"] for a in arms], ["gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra"])

    def test_hermes_never_consults_the_catalog(self):
        [arm] = self.resolve(
            "hermes", "feature", user="feature, refactoring: gpt-6-sol@high\n",
            codex_catalog=catalog_json("gpt-6.1-sol", "gpt-6-sol"),
        )
        self.assertEqual((arm["model"], arm.get("notes")), ("gpt-6-sol", None))

    def test_claude_code_never_consults_the_list(self):
        listed = {"gpt-6.1-sol": cmc.MODEL_EFFORTS["gpt-6.1-sol"], "gpt-6-sol": cmc.MODEL_EFFORTS["gpt-6-sol"]}
        layers = [Layer("user flat", {"feature": [("gpt-6-sol", "high")]})]
        [arm] = cmc.resolve_role("feature", "claude-code", layers, listed)
        self.assertEqual(
            (arm.model, arm.effort, arm.notes),
            ("inherit-parent", "high", ("gpt-6-sol is not usable on claude-code",)),
        )

    def test_resolve_role_takes_the_listed_set_directly(self):
        layers = [Layer("user flat", {"feature": [("gpt-6-sol", "high")]})]
        [arm] = cmc.resolve_role("feature", "codex", layers, {"gpt-6.1-sol": frozenset({"low", "high"})})
        self.assertEqual((arm.model, arm.effort), ("gpt-6.1-sol", "high"))
        [arm] = cmc.resolve_role("feature", "codex", layers)
        self.assertEqual((arm.model, arm.notes), ("gpt-6-sol", ()))


OPERATOR_FILE = """feature, refactoring: sonnet@high
bug-fix, perf-issue, hillclimb: opus@high
judgment and prose, hardest tasks, reflect judgment, reflect divergent, reflect synthesizer: opus@xhigh
how explorer, why investigators: sonnet@medium
how explainer, why synthesizer, reflect tooling: opus@high
arena runners, architect runners: opus@xhigh, opus@xhigh, sonnet@high
arena cross-judge pool, interrogate reviewers: opus@xhigh, opus@high, sonnet@high
swarm workers: sonnet@high
trail reviewer: opus@xhigh
default: inherit-parent

## codex
feature, refactoring, hillclimb, judgment and prose, how explainer, why synthesizer, reflect tooling, swarm workers: gpt-6.1-sol@high
bug-fix, perf-issue, hardest tasks, reflect judgment, reflect synthesizer, reflect divergent: gpt-6.1-sol@xhigh
how explorer, why investigators: gpt-6.1-sol@medium
arena runners, architect runners, interrogate reviewers: gpt-6.1-sol@xhigh, gpt-6.1-sol@xhigh, gpt-6.1-sol@high
arena cross-judge pool: gpt-6-astra@high, gpt-6.1-sol@xhigh
trail reviewer: gpt-6.1-sol@xhigh
default: inherit-parent

## grok
feature, refactoring, bug-fix, perf-issue, hillclimb, judgment and prose, how explainer, why synthesizer, reflect tooling: grok-4.7@high
reflect judgment, reflect divergent, reflect synthesizer, swarm workers, trail reviewer: grok-4.7@high
hardest tasks: grok-4.7@xhigh
how explorer, why investigators: grok-4.7@medium
arena runners, architect runners, arena cross-judge pool, interrogate reviewers: grok-4.7@high, grok-4.7@xhigh, grok-4.7@high
default: inherit-parent
"""

STEP_CATALOG = catalog_json("gpt-6.1-sol", "gpt-6-astra", "gpt-6-sol", "gpt-6-luna")


class ReviewerRunner(ResolveRunner):
    def reviewer(self, harness, work_model, user=OPERATOR_FILE, codex_catalog=None):
        [arm] = self.resolve(harness, "trail reviewer", user=user, codex_catalog=codex_catalog, work_model=work_model)
        return arm


class TrailReviewerStep(ReviewerRunner, unittest.TestCase):

    def test_a_step_target_with_no_recognized_levels_keeps_the_target_effort(self):
        catalog = catalog_json("gpt-6-sol", catalog_entry("gpt-6-astra", levels=["minimal"]))
        user = "## codex\ntrail reviewer: gpt-6-sol@xhigh\nfeature: gpt-6-astra\n"
        self.assertEqual(
            self.reviewer("codex", "gpt-6-sol@xhigh", user=user, codex_catalog=catalog),
            {
                "role": "trail reviewer", "arm": 1, "model": "gpt-6-astra", "effort": "high", "source": "user ## codex",
                "notes": ["trail reviewer matched work model gpt-6-sol; stepped up to gpt-6-astra (allowed by feature)"], "step": "up",
            },
        )

    def test_claude_steps_down_when_the_config_never_names_a_higher_tier(self):
        self.assertEqual(
            self.reviewer("claude-code", "opus@xhigh"),
            {
                "role": "trail reviewer", "arm": 1, "model": "sonnet", "effort": "xhigh", "source": "user flat",
                "notes": ["trail reviewer matched work model opus; stepped down to sonnet"], "step": "down",
            },
        )

    def test_codex_steps_up_across_releases_of_one_tier(self):
        self.assertEqual(
            self.reviewer("codex", "gpt-6.1-sol@xhigh", codex_catalog=STEP_CATALOG),
            {
                "role": "trail reviewer", "arm": 1, "model": "gpt-6-astra", "effort": "high", "source": "user ## codex",
                "notes": ["trail reviewer matched work model gpt-6.1-sol; stepped up to gpt-6-astra (allowed by arena cross-judge pool)"], "step": "up",
            },
        )

    def test_either_release_of_the_work_tier_counts_as_the_same_model(self):
        arm = self.reviewer("codex", "gpt-6-sol@xhigh", codex_catalog=STEP_CATALOG)
        self.assertEqual((arm["model"], arm["effort"], arm["step"]), ("gpt-6-astra", "high", "up"))
        self.assertEqual(arm["notes"], ["trail reviewer matched work model gpt-6-sol; stepped up to gpt-6-astra (allowed by arena cross-judge pool)"])

    def test_grok_with_one_model_in_the_config_is_a_same_model_review(self):
        self.assertEqual(
            self.reviewer("grok", "grok-4.7@high"),
            {
                "role": "trail reviewer", "arm": 1, "model": "grok-4.7", "effort": "xhigh", "source": "user ## grok",
                "notes": [
                    "trail reviewer matched work model grok-4.7; "
                    "the config allows no other model in its family, so this is a same-model review"
                ],
                "step": "same-model",
            },
        )

    def test_grok_steps_down_to_the_build_variant_when_the_config_names_it(self):
        user = "## grok\ntrail reviewer: grok-4.7@high\nswarm workers: grok-4.7-build-fast@medium\n"
        self.assertEqual(
            self.reviewer("grok", "grok-4.7@high", user=user),
            {
                "role": "trail reviewer", "arm": 1, "model": "grok-4.7-build-fast", "effort": "xhigh",
                "source": "user ## grok",
                "notes": ["trail reviewer matched work model grok-4.7; stepped down to grok-4.7-build-fast (allowed by swarm workers)"],
                "step": "down",
            },
        )

    def test_grok_build_variant_work_steps_up_to_grok_4_7(self):
        user = "## grok\ntrail reviewer: grok-4.7-build-fast@high\nswarm workers: grok-4.7@medium\n"
        arm = self.reviewer("grok", "grok-4.7-build-fast@xhigh", user=user)
        self.assertEqual((arm["model"], arm["effort"], arm["step"]), ("grok-4.7", "high", "up"))

    def test_shipped_defaults_allow_fable_so_claude_steps_up(self):
        self.assertEqual(
            self.reviewer("claude-code", "opus@xhigh", user=None),
            {
                "role": "trail reviewer", "arm": 1, "model": "fable", "effort": "high", "source": "skill default",
                "notes": ["trail reviewer matched work model opus; stepped up to fable"], "step": "up",
            },
        )

    def test_shipped_grok_defaults_hold_one_model_so_the_review_is_same_model(self):
        self.assertEqual(
            self.reviewer("grok", "grok-4.7@high", user=None),
            {
                "role": "trail reviewer", "arm": 1, "model": "grok-4.7", "effort": "xhigh", "source": "skill default",
                "notes": [
                    "opus translated to grok-4.7",
                    "trail reviewer matched work model grok-4.7; "
                    "the config allows no other model in its family, so this is a same-model review",
                ],
                "step": "same-model",
            },
        )

    def test_no_collision_prints_the_arm_unchanged(self):
        self.assertEqual(
            self.reviewer("claude-code", "sonnet@high"),
            {"role": "trail reviewer", "arm": 1, "model": "opus", "effort": "xhigh", "source": "user flat"},
        )

    def test_an_explicit_reviewer_that_differs_stands_as_written(self):
        user = OPERATOR_FILE.replace("trail reviewer: opus@xhigh", "trail reviewer: haiku@low")
        self.assertEqual(
            self.reviewer("claude-code", "opus@xhigh", user=user),
            {"role": "trail reviewer", "arm": 1, "model": "haiku", "effort": "low", "source": "user flat"},
        )

    def test_an_inherited_reviewer_is_left_alone(self):
        user = OPERATOR_FILE.replace("trail reviewer: opus@xhigh", "trail reviewer: inherit-parent")
        arm = self.reviewer("claude-code", "opus@xhigh", user=user)
        self.assertEqual((arm["model"], arm["effort"], "step" in arm), (cmc.INHERIT, cmc.INHERIT, False))

    def test_a_step_down_from_xhigh_stays_at_xhigh(self):
        arm = self.reviewer("claude-code", "opus@xhigh")
        self.assertEqual((arm["model"], arm["effort"]), ("sonnet", "xhigh"))

    def test_a_step_down_from_max_never_yields_max(self):
        arm = self.reviewer("claude-code", "opus@max")
        self.assertEqual((arm["model"], arm["effort"]), ("sonnet", "xhigh"))

    def test_a_step_up_from_max_lands_on_xhigh(self):
        arm = self.reviewer("claude-code", "opus@max", user=None)
        self.assertEqual((arm["model"], arm["effort"]), ("fable", "xhigh"))

    def test_a_step_up_never_lowers_effort_below_high(self):
        arm = self.reviewer("claude-code", "opus@low", user=None)
        self.assertEqual((arm["model"], arm["effort"]), ("fable", "high"))

    def test_a_missing_work_effort_offsets_the_reviewers_own_effort(self):
        user = OPERATOR_FILE.replace("trail reviewer: opus@xhigh", "trail reviewer: opus@medium")
        arm = self.reviewer("claude-code", "opus", user=user)
        self.assertEqual((arm["model"], arm["effort"]), ("sonnet", "high"))

    def test_an_inherited_work_effort_offsets_the_reviewers_own_effort(self):
        user = OPERATOR_FILE.replace("trail reviewer: opus@xhigh", "trail reviewer: opus@medium")
        arm = self.reviewer("claude-code", "opus@inherit-parent", user=user)
        self.assertEqual((arm["model"], arm["effort"]), ("sonnet", "high"))

    def test_no_effort_anywhere_keeps_the_session_effort(self):
        arm = self.reviewer("claude-code", "opus", user=None)
        self.assertEqual((arm["model"], arm["effort"], arm["step"]), ("fable", cmc.INHERIT, "up"))

    def test_a_claude_alias_work_model_translates_on_codex(self):
        user = "## codex\ntrail reviewer: gpt-6-sol@high\nswarm workers: gpt-6-astra@high\n"
        arm = self.reviewer("codex", "opus", user=user, codex_catalog=STEP_CATALOG)
        self.assertEqual(
            (arm["model"], arm["effort"], arm["step"], arm["notes"][-1]),
            (
                "gpt-6-astra", "high", "up",
                "trail reviewer matched work model gpt-6-sol; stepped up to gpt-6-astra (allowed by swarm workers)",
            ),
        )

    def test_a_tier_the_config_leaves_out_is_not_a_candidate(self):
        user = "## codex\ntrail reviewer: gpt-6-sol@high\n"
        arm = self.reviewer("codex", "opus", user=user, codex_catalog=STEP_CATALOG)
        self.assertEqual((arm["model"], arm["effort"], arm["step"]), ("gpt-6-luna", "xhigh", "down"))

    def test_the_target_effort_drops_to_the_highest_level_the_catalog_offers(self):
        catalog = catalog_json("gpt-6.1-sol", ("gpt-6-astra", "list", ("low", "medium")), "gpt-6-sol", "gpt-6-luna")
        arm = self.reviewer("codex", "gpt-6.1-sol@xhigh", codex_catalog=catalog)
        self.assertEqual((arm["model"], arm["effort"]), ("gpt-6-astra", "medium"))

    def test_other_roles_print_unchanged(self):
        [feature, _] = self.resolve(
            "claude-code", "feature", "trail reviewer", user=OPERATOR_FILE, work_model="sonnet@high",
        )
        self.assertEqual(
            feature, {"role": "feature", "arm": 1, "model": "sonnet", "effort": "high", "source": "user flat"},
        )

    def test_no_roles_still_steps_the_trail_reviewer_line(self):
        arms = self.resolve("claude-code", user=OPERATOR_FILE, work_model="opus@xhigh")
        [reviewer] = [a for a in arms if a["role"] == "trail reviewer"]
        self.assertEqual(
            reviewer,
            {
                "role": "trail reviewer", "arm": 1, "model": "sonnet", "effort": "xhigh", "source": "user flat",
                "notes": ["trail reviewer matched work model opus; stepped down to sonnet"], "step": "down",
            },
        )
        self.assertEqual({a['role'] for a in arms}, set(cmc.ROLES))

    def test_a_full_claude_model_id_maps_to_its_alias_on_claude_code(self):
        self.assertEqual(
            self.reviewer("claude-code", "claude-opus-5-5@xhigh"),
            {
                "role": "trail reviewer", "arm": 1, "model": "sonnet", "effort": "xhigh", "source": "user flat",
                "notes": ["trail reviewer matched work model opus; stepped down to sonnet"], "step": "down",
            },
        )

    def test_every_full_claude_id_shape_maps_to_its_alias(self):
        for work_model, alias, expected in (
            ("claude-haiku-4-5-20251001@high", "haiku", ("sonnet", "high", "up")),
            ("claude-sonnet-5-5@high", "sonnet", ("opus", "high", "up")),
            ("claude-fable-5-1@high", "fable", ("opus", "xhigh", "down")),
        ):
            with self.subTest(work_model=work_model):
                arm = self.reviewer("claude-code", work_model, user=f"trail reviewer: {alias}@high\n")
                self.assertEqual((arm["model"], arm["effort"], arm["step"]), expected)
                self.assertEqual(
                    arm["notes"][0],
                    f"trail reviewer matched work model {alias}; stepped {expected[2]} to {expected[0]}",
                )

    def test_a_full_claude_model_id_maps_to_its_alias_on_codex(self):
        user = "## codex\ntrail reviewer: gpt-6-sol@high\nswarm workers: gpt-6-astra@high\n"
        arm = self.reviewer("codex", "claude-opus-5-5", user=user, codex_catalog=STEP_CATALOG)
        self.assertEqual(
            arm,
            {
                "role": "trail reviewer", "arm": 1, "model": "gpt-6-astra", "effort": "high", "source": "user ## codex",
                "notes": ["trail reviewer matched work model gpt-6-sol; stepped up to gpt-6-astra (allowed by swarm workers)"], "step": "up",
            },
        )

    def test_a_full_claude_id_stays_a_real_slug_on_hermes(self):
        user = "## hermes\ntrail reviewer: claude-opus-5-5@xhigh\nswarm workers: claude-sonnet-5@high\n"
        self.assertEqual(
            self.reviewer("hermes", "claude-opus-5-5@xhigh", user=user),
            {
                "role": "trail reviewer", "arm": 1, "model": "claude-opus-5-5", "effort": "xhigh",
                "source": "user ## hermes",
                "notes": [
                    "trail reviewer matched work model claude-opus-5-5; "
                    "the config allows no other model in its family, so this is a same-model review"
                ],
                "step": "same-model",
            },
        )

    def test_a_work_model_outside_the_families_is_same_model_even_when_the_config_allows_others(self):
        user = "## codex\ntrail reviewer: gpt-5.6-sol@high\nfeature: gpt-6-astra@high\n"
        arm = self.reviewer("codex", "gpt-5.6-sol@high", user=user, codex_catalog=STEP_CATALOG)
        self.assertEqual(
            arm,
            {
                "role": "trail reviewer", "arm": 1, "model": "gpt-5.6-sol", "effort": "xhigh",
                "source": "user ## codex",
                "notes": [
                    "trail reviewer matched work model gpt-5.6-sol; "
                    "the config allows no other model in its family, so this is a same-model review"
                ],
                "step": "same-model",
            },
        )

    def rejected(self, harness, work_model, user=OPERATOR_FILE):
        with tempfile.TemporaryDirectory() as tmp:
            user_file = Path(tmp) / "user-models.md"
            user_file.write_text(user, encoding="utf-8")
            return run_script(
                ["--resolve", "--harness", harness, "--project", tmp, "--user-file", str(user_file),
                 "--work-model", work_model, "trail reviewer"],
            )

    def test_a_claude_code_work_model_that_is_not_an_alias_or_a_claude_id_is_a_usage_error(self):
        for work_model, named in (
            ("claude-foo@high", "claude-foo"),
            ("claude-3-opus-20240229@xhigh", "claude-3-opus-20240229"),
            ("claude-nova-6@xhigh", "claude-nova-6"),
            ("opus[1m]@xhigh", "opus[1m]"),
        ):
            with self.subTest(work_model=work_model):
                result = self.rejected("claude-code", work_model)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn(repr(named), result.stderr)

    def test_a_claude_code_usage_error_says_which_models_claude_code_takes(self):
        result = self.rejected("claude-code", "claude-nova-6@xhigh")
        self.assertIn(
            "argument --work-model: 'claude-nova-6' is not a Claude Code model; "
            "use an alias (fable, opus, sonnet, haiku) or a claude-<alias>-... ID",
            result.stderr,
        )

    def test_full_claude_ids_with_a_date_or_context_suffix_step_down_on_claude_code(self):
        for work_model in ("claude-opus-5-5", "claude-opus-4-1-20250805", "claude-opus-5-5[1m]"):
            with self.subTest(work_model=work_model):
                self.assertEqual(
                    self.reviewer("claude-code", f"{work_model}@xhigh"),
                    {
                        "role": "trail reviewer", "arm": 1, "model": "sonnet", "effort": "xhigh", "source": "user flat",
                        "notes": ["trail reviewer matched work model opus; stepped down to sonnet"], "step": "down",
                    },
                )

    def test_inherit_parent_and_auto_work_models_print_the_reviewer_unchanged_with_a_session_model_note(self):
        hermes_user = "## hermes\ntrail reviewer: model-a@high\n"
        for harness, work_model, user, expected in (
            ("claude-code", "inherit-parent@high", OPERATOR_FILE, {"model": "opus", "effort": "xhigh", "source": "user flat"}),
            ("claude-code", "auto", OPERATOR_FILE, {"model": "opus", "effort": "xhigh", "source": "user flat"}),
            ("hermes", "inherit-parent", hermes_user, {"model": "model-a", "effort": "high", "source": "user ## hermes"}),
        ):
            alias = work_model.partition("@")[0]
            with self.subTest(harness=harness, work_model=work_model):
                self.assertEqual(
                    self.reviewer(harness, work_model, user=user),
                    {
                        "role": "trail reviewer", "arm": 1, **expected,
                        "notes": [f"work model {alias} names no model, so pass the session model; no step applied"],
                    },
                )

    def test_a_work_model_hermes_cannot_use_adds_a_note_and_applies_no_step(self):
        user = "## hermes\ntrail reviewer: model-a@high\n"
        self.assertEqual(
            self.reviewer("hermes", "opus@xhigh", user=user),
            {
                "role": "trail reviewer", "arm": 1, "model": "model-a", "effort": "high", "source": "user ## hermes",
                "notes": ["work model opus is not usable on hermes; no step applied"],
            },
        )

    def test_an_arbitrary_work_model_slug_on_codex_prints_with_no_error_and_no_note(self):
        self.assertEqual(
            self.reviewer("codex", "gpt-9-zeta@high"),
            {
                "role": "trail reviewer", "arm": 1, "model": "gpt-6.1-sol", "effort": "xhigh",
                "source": "user ## codex",
            },
        )

    def test_a_moved_arm_drops_the_notes_that_described_the_old_model(self):
        arm = self.reviewer("codex", "gpt-6-sol@xhigh", codex_catalog=catalog_json("gpt-6-sol", "gpt-6-astra", "gpt-6-luna"))
        self.assertEqual(
            arm["notes"], ["trail reviewer matched work model gpt-6-sol; stepped up to gpt-6-astra (allowed by arena cross-judge pool)"],
        )

    def test_hermes_with_a_distinct_work_model_prints_unchanged(self):
        user = "## hermes\ntrail reviewer: model-a@high\nfeature: model-b@high\n"
        self.assertEqual(
            self.reviewer("hermes", "model-b@high", user=user),
            {"role": "trail reviewer", "arm": 1, "model": "model-a", "effort": "high", "source": "user ## hermes"},
        )

    def test_hermes_with_an_inherited_reviewer_prints_unchanged_with_no_step(self):
        user = "## hermes\ntrail reviewer: inherit-parent\nfeature: model-b@high\n"
        self.assertEqual(
            self.reviewer("hermes", "model-b@high", user=user),
            {
                "role": "trail reviewer", "arm": 1, "model": "inherit-parent", "effort": "inherit-parent",
                "source": "user ## hermes",
            },
        )

    def test_a_work_model_with_an_unknown_effort_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script(
                ["--resolve", "--harness", "claude-code", "--project", tmp, "--user-file", f"{tmp}/none.md",
                 "--work-model", "opus@turbo", "trail reviewer"],
            )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("unknown effort 'turbo'", result.stderr)


class TrailReviewerStepNote(ReviewerRunner, unittest.TestCase):
    def test_the_issue_config_steps_to_astra_and_names_the_role_that_allows_it(self):
        self.assertEqual(
            self.reviewer("codex", "gpt-6.1-sol@high", codex_catalog=STEP_CATALOG),
            {
                "role": "trail reviewer", "arm": 1, "model": "gpt-6-astra", "effort": "high", "source": "user ## codex",
                "notes": [
                    "trail reviewer matched work model gpt-6.1-sol; "
                    "stepped up to gpt-6-astra (allowed by arena cross-judge pool)"
                ],
                "step": "up",
            },
        )

    def test_the_note_lists_up_to_three_allowing_roles_and_omits_more(self):
        three = "## codex\ntrail reviewer: gpt-6.1-sol@xhigh\nroutine, swarm workers, hillclimb: gpt-6-astra@high\n"
        [arm] = self.resolve("codex", "trail reviewer", user=three, work_model="gpt-6.1-sol@high")
        self.assertEqual(
            arm["notes"],
            ["trail reviewer matched work model gpt-6.1-sol; stepped up to gpt-6-astra (allowed by hillclimb, routine, swarm workers)"],
        )
        four = three.replace("hillclimb", "hillclimb, bug-fix")
        [arm] = self.resolve("codex", "trail reviewer", user=four, work_model="gpt-6.1-sol@high")
        self.assertEqual(
            arm["notes"],
            ["trail reviewer matched work model gpt-6.1-sol; stepped up to gpt-6-astra"],
        )

class TrailReviewerPin(ReviewerRunner, unittest.TestCase):
    PIN = "trail reviewer step: off"

    def pinned_file(self, reviewer="gpt-6.1-sol@high", pin=PIN):
        return OPERATOR_FILE.replace("trail reviewer: gpt-6.1-sol@xhigh", f"trail reviewer: {reviewer}\n{pin}")

    def test_a_pinned_reviewer_stands_on_a_match_at_its_written_effort(self):
        self.assertEqual(
            self.reviewer("codex", "gpt-6.1-sol@high", user=self.pinned_file(), codex_catalog=STEP_CATALOG),
            {
                "role": "trail reviewer", "arm": 1, "model": "gpt-6.1-sol", "effort": "high", "source": "user ## codex",
                "notes": [
                    "trail reviewer matched work model gpt-6.1-sol; "
                    "trail reviewer step is off, so this is a same-model review"
                ],
                "step": "same-model",
            },
        )

    def test_the_pin_keeps_the_written_effort_whatever_the_work_effort(self):
        for written in ("medium", "high", "xhigh"):
            with self.subTest(written=written):
                arm = self.reviewer(
                    "codex", "gpt-6.1-sol@xhigh", user=self.pinned_file(f"gpt-6.1-sol@{written}"),
                    codex_catalog=STEP_CATALOG,
                )
                self.assertEqual((arm["model"], arm["effort"], arm["step"]), ("gpt-6.1-sol", written, "same-model"))

    def test_a_pinned_reviewer_on_claude_code_stands_as_written(self):
        user = "trail reviewer: opus@high\ntrail reviewer step: off\n"
        arm = self.reviewer("claude-code", "opus@xhigh", user=user)
        self.assertEqual((arm["model"], arm["effort"], arm["step"]), ("opus", "high", "same-model"))

    def test_a_pin_changes_nothing_when_the_reviewer_already_differs(self):
        user = "trail reviewer: haiku@low\ntrail reviewer step: off\n"
        self.assertEqual(
            self.reviewer("claude-code", "opus@xhigh", user=user),
            {"role": "trail reviewer", "arm": 1, "model": "haiku", "effort": "low", "source": "user flat"},
        )

    def test_a_pinned_inherit_parent_reviewer_stays_unlabeled(self):
        for harness, work_model, user in (
            ("claude-code", "opus@xhigh", "trail reviewer: inherit-parent\ntrail reviewer step: off\n"),
            ("hermes", "model-b@high", "## hermes\ntrail reviewer: inherit-parent\ntrail reviewer step: off\n"),
        ):
            with self.subTest(harness=harness):
                arm = self.reviewer(harness, work_model, user=user)
                self.assertEqual((arm["model"], arm["effort"]), ("inherit-parent", "inherit-parent"))
                self.assertNotIn("step", arm)
                self.assertNotIn("notes", arm)

    def test_the_pin_keeps_the_notes_the_arm_already_carried(self):
        user = "## grok\ntrail reviewer: opus@high\ntrail reviewer step: off\n"
        self.assertEqual(
            self.reviewer("grok", "grok-4.7@high", user=user),
            {
                "role": "trail reviewer", "arm": 1, "model": "grok-4.7", "effort": "high", "source": "user ## grok",
                "notes": [
                    "opus translated to grok-4.7",
                    "trail reviewer matched work model grok-4.7; "
                    "trail reviewer step is off, so this is a same-model review",
                ],
                "step": "same-model",
            },
        )

    def test_the_pin_follows_layer_order_so_a_workspace_section_on_overrides_a_user_off(self):
        [arm] = self.resolve(
            "codex", "trail reviewer", user=self.pinned_file(), workspace="## codex\ntrail reviewer step: on\n",
            codex_catalog=STEP_CATALOG, work_model="gpt-6.1-sol@high",
        )
        self.assertEqual((arm["model"], arm["step"]), ("gpt-6-astra", "up"))

    def test_each_section_binds_its_own_harness(self):
        for value, claude_step, codex_step in (("off", "same-model", "same-model"), ("on", "down", "up")):
            with self.subTest(value=value):
                user = OPERATOR_FILE.replace(
                    "trail reviewer: opus@xhigh", f"trail reviewer: opus@xhigh\ntrail reviewer step: {value}"
                ).replace(
                    "trail reviewer: gpt-6.1-sol@xhigh", f"trail reviewer: gpt-6.1-sol@xhigh\ntrail reviewer step: {value}"
                )
                self.assertEqual(self.reviewer("claude-code", "opus@xhigh", user=user)["step"], claude_step)
                self.assertEqual(
                    self.reviewer("codex", "gpt-6.1-sol@xhigh", user=user, codex_catalog=STEP_CATALOG)["step"],
                    codex_step,
                )

    def test_a_codex_section_pin_does_not_bind_claude_code(self):
        user = "trail reviewer: opus@xhigh\n\n## codex\ntrail reviewer step: off\n"
        self.assertEqual(self.reviewer("claude-code", "opus@xhigh", user=user)["step"], "up")

    def test_the_setting_is_not_a_role(self):
        self.assertNotIn("trail reviewer step", cmc.ROLES)
        arms = self.resolve("codex", user=self.pinned_file(), codex_catalog=STEP_CATALOG)
        self.assertEqual({a["role"] for a in arms}, set(cmc.ROLES))


class TrailReviewerPinLint(unittest.TestCase):
    def test_off_and_on_lint_clean_in_every_section(self):
        for value in ("off", "on"):
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "pstack-models.md"
                    path.write_text(f"trail reviewer step: {value}\n\n## codex\ntrail reviewer step: {value}\n", encoding="utf-8")
                    result = run_script([str(path)])
                self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_any_other_value_is_an_error(self):
        for value in ("maybe", "off@high", "off, on", "opus"):
            with self.subTest(value=value):
                _, findings = cmc.parse(f"trail reviewer step: {value}\n")
                self.assertEqual(len(errors_of(findings)), 1, findings)

    def test_the_setting_cannot_share_a_line_with_a_role(self):
        sections, findings = cmc.parse("trail reviewer, trail reviewer step: off\n")
        self.assertEqual(len(errors_of(findings)), 1)
        self.assertNotIn("trail reviewer", sections[""])

    def test_binding_the_setting_twice_in_a_section_is_an_error(self):
        _, findings = cmc.parse("trail reviewer step: off\ntrail reviewer step: on\n")
        self.assertEqual(len(errors_of(findings)), 1)

    def test_the_cli_lint_exits_zero_for_a_pinned_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pstack-models.md"
            path.write_text("trail reviewer: gpt-6.1-sol@high\ntrail reviewer step: off\n", encoding="utf-8")
            result = run_script([str(path)])
        self.assertEqual((result.returncode, result.stdout), (0, ""))


class ListedModels(unittest.TestCase):
    def test_maps_each_listed_slug_to_its_catalog_levels(self):
        listed = read_listed(catalog_json("gpt-6-sol", "gpt-6-luna", ("gpt-6.1-sol", "hide")))
        self.assertEqual(
            listed,
            {"gpt-6-sol": frozenset(FULL_LEVELS), "gpt-6-luna": frozenset(LUNA_LEVELS)},
        )

    def test_empty_or_missing_levels_map_to_an_empty_set(self):
        text = catalog_json(catalog_entry("gpt-6-sol", levels=()), {"slug": "gpt-6-luna"})
        self.assertEqual(read_listed(text), {"gpt-6-sol": frozenset(), "gpt-6-luna": frozenset()})

    def test_a_read_or_shape_failure_is_an_empty_mapping(self):
        bad = (
            "{not json", "[]", '{"models": 3}', '{"models": ["gpt-6-sol"]}', '{"models": [{"visibility": "list"}]}',
            '{"models": [{"slug": "gpt-6-sol", "supported_reasoning_levels": "low"}]}',
            '{"models": [{"slug": "gpt-6-sol", "supported_reasoning_levels": [{"description": "low"}]}]}',
        )
        for text in bad:
            with self.subTest(text=text):
                self.assertEqual(read_listed(text), {})
        self.assertEqual(cmc.listed_models(Path("/nonexistent/models_cache.json")), {})


class GrokResolve(ResolveRunner, unittest.TestCase):
    def test_flat_alias_translates_and_keeps_the_written_effort(self):
        [arm] = self.resolve("grok", "feature", user="feature, refactoring: sonnet@high\n")
        self.assertEqual(
            arm,
            {
                "role": "feature", "arm": 1, "model": "grok-4.7", "effort": "high",
                "source": "user flat", "notes": ["sonnet translated to grok-4.7"],
            },
        )

    def test_flat_alias_without_effort_runs_at_the_session_effort(self):
        [arm] = self.resolve("grok", "bug-fix", user="bug-fix: opus\n")
        self.assertEqual(
            arm,
            {
                "role": "bug-fix", "arm": 1, "model": "grok-4.7", "effort": "inherit-parent",
                "source": "user flat", "notes": ["opus translated to grok-4.7"],
            },
        )

    def test_grok_section_beats_a_flat_line(self):
        user = "feature, refactoring: sonnet@high\n\n## grok\nfeature, refactoring: grok-4.7@low\n"
        [arm] = self.resolve("grok", "feature", user=user)
        self.assertEqual(
            arm,
            {"role": "feature", "arm": 1, "model": "grok-4.7", "effort": "low", "source": "user ## grok"},
        )

    def test_a_named_grok_model_passes_through(self):
        user = "## grok\nfeature, refactoring: grok-4.7-build-fast@xhigh\n"
        [arm] = self.resolve("grok", "feature", user=user)
        self.assertEqual(
            arm,
            {"role": "feature", "arm": 1, "model": "grok-4.7-build-fast", "effort": "xhigh", "source": "user ## grok"},
        )

    def test_a_flat_effort_the_grok_cli_rejects_falls_back_to_the_session_effort(self):
        [arm] = self.resolve("grok", "default", user="default: inherit-parent@max\n")
        self.assertEqual(
            arm,
            {
                "role": "default", "arm": 1, "model": "inherit-parent", "effort": "inherit-parent",
                "source": "user flat", "notes": ["effort max is not usable on grok"],
            },
        )

    def test_an_effort_the_grok_cli_rejects_keeps_the_model_and_falls_back_to_the_session_effort(self):
        layers = [Layer("user ## grok", {"feature": [("grok-4.7", "max")]})]
        [arm] = cmc.resolve_role("feature", "grok", layers)
        self.assertEqual(
            (arm.model, arm.effort, arm.notes),
            ("grok-4.7", "inherit-parent", ("effort max is not usable on grok",)),
        )

    def test_the_shipped_default_resolves_for_grok(self):
        [arm] = self.resolve("grok", "trail reviewer")
        self.assertEqual(
            arm,
            {
                "role": "trail reviewer", "arm": 1, "model": "grok-4.7", "effort": "inherit-parent",
                "source": "skill default", "notes": ["opus translated to grok-4.7"],
            },
        )

    def test_a_panel_translates_arm_by_arm(self):
        arms = self.resolve("grok", "arena runners")
        self.assertEqual([(a["model"], a["effort"]) for a in arms], [("grok-4.7", "inherit-parent")] * 3)
        self.assertEqual(
            [a["notes"] for a in arms],
            [
                [
                    "fable translated to grok-4.7",
                    "arena runners resolves to one distinct model (grok-4.7), so agreement between its arms "
                    "is not independent confirmation",
                ],
                ["opus translated to grok-4.7"],
                ["sonnet translated to grok-4.7"],
            ],
        )

    def test_grok_never_consults_the_codex_catalog(self):
        [arm] = self.resolve(
            "grok", "feature", user="feature, refactoring: gpt-6-sol@high\n",
            codex_catalog=catalog_json("gpt-6.1-sol", "gpt-6-sol"),
        )
        self.assertEqual((arm["model"], arm["effort"], arm.get("notes")), ("gpt-6-sol", "high", None))


class ShippedDefaultLeak(ResolveRunner, unittest.TestCase):
    def notes(self, harness, role, **kwargs):
        return [arm.get("notes", []) for arm in self.resolve(harness, role, **kwargs)]

    def test_a_role_the_partial_config_omits_names_itself_and_the_fix(self):
        [arm] = self.resolve("claude-code", "hardest tasks", user="feature, refactoring: sonnet\n")
        self.assertEqual(arm["source"], "skill default")
        self.assertEqual(
            arm["notes"],
            [
                "hardest tasks is not bound in your config, and the shipped default opus appears in none of "
                "your lines; add a `hardest tasks:` line to pstack-models.md to choose its model"
            ],
        )

    def test_a_panel_flags_only_the_arms_whose_model_the_config_never_uses(self):
        arms = self.resolve("claude-code", "arena runners", user="feature, refactoring: sonnet\n")
        self.assertEqual(
            [("notes" in arm, arm["model"]) for arm in arms],
            [(True, "fable"), (True, "opus"), (False, "sonnet")],
        )

    def test_a_default_whose_model_the_config_uses_elsewhere_gets_no_note(self):
        self.assertEqual(self.notes("claude-code", "swarm workers", user="feature, refactoring: sonnet\n"), [[]])

    def test_a_workspace_file_alone_makes_the_config_partial(self):
        [arm] = self.resolve("claude-code", "hardest tasks", workspace="feature, refactoring: sonnet\n")
        self.assertIn("hardest tasks is not bound", arm["notes"][0])

    def test_no_config_means_the_shipped_defaults_are_intended(self):
        self.assertEqual(self.notes("claude-code", "hardest tasks"), [[]])

    def test_a_step_setting_without_role_bindings_preserves_default_output(self):
        for harness in ("claude-code", "codex", "hermes", "grok"):
            expected = self.resolve(harness, user="", workspace="")
            self.assertTrue(expected)
            for location in ("user", "workspace"):
                for section in ("", f"## {harness}\n"):
                    for value in ("on", "off"):
                        with self.subTest(harness=harness, location=location, section=section, value=value):
                            config = f"{section}trail reviewer step: {value}\n"
                            self.assertEqual(self.resolve(harness, **{location: config}), expected)

    def test_a_role_the_config_binds_gets_no_note(self):
        self.assertEqual(self.notes("claude-code", "feature", user="feature, refactoring: sonnet\n"), [[]])

    def test_an_inheriting_default_never_leaks_a_model(self):
        self.assertEqual(self.notes("claude-code", "default", user="feature, refactoring: sonnet\n"), [[]])

    def test_codex_compares_translated_models(self):
        arms = self.resolve("codex", "arena runners", user="feature, refactoring: sonnet\n")
        self.assertEqual(
            [(arm["model"], "notes" in arm) for arm in arms],
            [("gpt-6-sol", False), ("gpt-6-sol", False), ("gpt-6-luna", True)],
        )
        self.assertIn("gpt-6-luna", arms[2]["notes"][0])

    def test_a_step_up_onto_a_model_only_a_shipped_default_allows_says_so(self):
        [arm] = self.resolve(
            "claude-code", "trail reviewer", user="feature, refactoring: sonnet\ntrail reviewer: opus\n",
            work_model="opus@xhigh",
        )
        self.assertEqual((arm["model"], arm["step"]), ("fable", "up"))
        self.assertEqual(
            arm["notes"],
            [
                "trail reviewer matched work model opus; stepped up to fable",
                "fable is in no line of your config; it is allowed only through the shipped default of a role "
                "your config leaves unbound",
            ],
        )

    def test_a_step_that_lands_on_a_model_the_config_names_gets_no_note(self):
        [arm] = self.resolve(
            "claude-code", "trail reviewer", user="trail reviewer: opus\nhow explorer: fable\n",
            work_model="opus@xhigh",
        )
        self.assertEqual(arm["model"], "fable")
        self.assertEqual(arm["notes"], ["trail reviewer matched work model opus; stepped up to fable"])


class PanelDiversityNote(ResolveRunner, unittest.TestCase):
    def test_a_panel_on_one_model_notes_it_on_the_first_arm_only(self):
        arms = self.resolve("claude-code", "interrogate reviewers", user="interrogate reviewers: opus, opus@high, opus@max\n")
        self.assertEqual(
            [arm.get("notes") for arm in arms],
            [
                [
                    "interrogate reviewers resolves to one distinct model (opus), so agreement between its arms "
                    "is not independent confirmation"
                ],
                None,
                None,
            ],
        )

    def test_a_panel_with_two_models_gets_no_note(self):
        arms = self.resolve("claude-code", "interrogate reviewers", user="interrogate reviewers: opus, sonnet, sonnet\n")
        self.assertEqual([arm.get("notes") for arm in arms], [None, None, None])

    def test_a_panel_mixing_a_model_and_inherit_parent_gets_no_note(self):
        for role in ("arena runners", "architect runners", "interrogate reviewers"):
            for models in (("opus", "inherit-parent"), ("inherit-parent", "opus")):
                with self.subTest(role=role, models=models):
                    arms = self.resolve("claude-code", role, user=f"{role}: {', '.join(models)}\n")
                    self.assertEqual([arm["model"] for arm in arms], list(models))
                    self.assertEqual([arm.get("notes") for arm in arms], [None, None])

    def test_two_releases_of_one_gpt6_tier_count_as_one_model(self):
        arms = self.resolve(
            "codex", "interrogate reviewers",
            user="## codex\ninterrogate reviewers: gpt-6.1-sol@xhigh, gpt-6-sol@high\n",
            codex_catalog=catalog_json("gpt-6.1-sol", "gpt-6-sol"),
        )
        self.assertIn("one distinct model", arms[0]["notes"][-1])

    def test_grok_defaults_resolve_every_panel_to_one_model(self):
        for role in ("arena runners", "architect runners", "interrogate reviewers"):
            with self.subTest(role=role):
                arms = self.resolve("grok", role)
                self.assertIn("(grok-4.7)", arms[0]["notes"][-1])

    def test_the_cross_judge_pool_picks_one_arm_so_it_gets_no_note(self):
        arms = self.resolve("grok", "arena cross-judge pool")
        self.assertNotIn("one distinct model", " ".join(arms[0].get("notes", [])))

    def test_an_inheriting_panel_names_the_parent_model(self):
        arms = self.resolve("hermes", "arena runners")
        self.assertIn("one distinct model (the parent model)", arms[0]["notes"][-1])

    def test_a_single_arm_panel_is_one_model(self):
        [arm] = self.resolve("claude-code", "architect runners", user="architect runners: opus\n")
        self.assertIn("one distinct model (opus)", arm["notes"][-1])

    def test_a_role_outside_the_panel_set_gets_no_note(self):
        [arm] = self.resolve("grok", "swarm workers")
        self.assertNotIn("one distinct model", " ".join(arm.get("notes", [])))

    def test_the_claude_code_defaults_are_a_diverse_panel(self):
        arms = self.resolve("claude-code", "interrogate reviewers")
        self.assertEqual([arm.get("notes") for arm in arms], [None, None, None])


class ResolveExitCodes(unittest.TestCase):
    def run_resolve(self, *args, user=None):
        with tempfile.TemporaryDirectory() as tmp:
            user_file = Path(tmp) / "user-models.md"
            if user is not None:
                user_file.write_text(user, encoding="utf-8")
            result = run_script(["--resolve", "--project", tmp, "--user-file", str(user_file), *args])
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
        result, _ = self.run_resolve("--harness", "cursor", "feature")
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
