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
        text = "## grok\ntrail reviewer: grok-4.7-build-fast@ultra\n"
        sections, findings = cmc.parse(text)
        self.assertEqual(
            errors_of(findings),
            [(2, "error", "effort 'ultra' is not a Grok Build level (low, medium, high, xhigh)")],
        )
        self.assertNotIn("trail reviewer", sections["grok"])

    def test_grok_section_rejects_max_and_none(self):
        for model, effort in (("grok-4.7-build-fast", "max"), ("grok-4.6", "none")):
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
    def resolve(self, harness, *roles, user=None, workspace=None, codex_catalog=None):
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
                    "--project", str(project), "--user-file", str(user_file), *roles,
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

    def test_codex_reads_the_shipped_default_section_before_its_flat_lines(self):
        [reviewer] = self.resolve("codex", "trail reviewer")
        self.assertEqual(
            reviewer,
            {"role": "trail reviewer", "arm": 1, "model": "gpt-6-luna", "effort": "xhigh", "source": "skill default ## codex"},
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
            [["fable translated to grok-4.7"], ["opus translated to grok-4.7"], ["sonnet translated to grok-4.7"]],
        )

    def test_grok_never_consults_the_codex_catalog(self):
        [arm] = self.resolve(
            "grok", "feature", user="feature, refactoring: gpt-6-sol@high\n",
            codex_catalog=catalog_json("gpt-6.1-sol", "gpt-6-sol"),
        )
        self.assertEqual((arm["model"], arm["effort"], arm.get("notes")), ("gpt-6-sol", "high", None))


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
