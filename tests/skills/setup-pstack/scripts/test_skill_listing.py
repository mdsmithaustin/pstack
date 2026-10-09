import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SCRIPT = REPO / "skills" / "setup-pstack" / "scripts" / "skill-listing.py"

_spec = importlib.util.spec_from_file_location("skill_listing", SCRIPT)
sl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sl)

REAL_MANAGED = """
architect arena automate-me benchmark-checklist blast-radius bro correct
create-verification-skill figure-it-out interrogate maintain-verification-skill
make-bot-ui no-comments poteto-help poteto-mode poteto-tdd poteto-teach
principle-attack-the-premise principle-boundary-discipline principle-build-the-lever
principle-encode-lessons-in-structure principle-exhaust-the-design-space
principle-experience-first principle-explain-the-number principle-fix-root-causes
principle-foundational-thinking principle-guard-the-context-window
principle-laziness-protocol principle-make-operations-idempotent
principle-migrate-callers-then-delete-legacy-apis principle-minimize-reader-load
principle-model-the-domain principle-never-block-on-the-human
principle-outcome-oriented-execution principle-prove-it-works
principle-redesign-from-first-principles principle-separate-before-serializing-shared-state
principle-sequence-verifiable-units principle-subtract-before-you-add
principle-test-behavior-not-implementation principle-type-system-discipline
recall reflect show-me-your-work swarm technical-writing typescript-best-practices
""".split()


def make_skill(root: Path, name: str, openai_yaml: str | None) -> None:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n", encoding="utf-8")
    if openai_yaml is not None:
        (skill / "agents").mkdir()
        (skill / "agents" / "openai.yaml").write_text(openai_yaml, encoding="utf-8")


FALSE_YAML = "policy:\n  allow_implicit_invocation: false\n"
TRUE_YAML = "policy:\n  allow_implicit_invocation: true\n"


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "skills"
        make_skill(self.root, "arena", FALSE_YAML)
        make_skill(self.root, "bro", FALSE_YAML)
        make_skill(self.root, "how", TRUE_YAML)
        make_skill(self.root, "why", None)
        make_skill(self.root, "unslop", "interface:\n  display_name: E\n")
        (self.root / "not-a-skill").mkdir()
        (self.root / "not-a-skill" / "agents").mkdir()
        (self.root / "not-a-skill" / "agents" / "openai.yaml").write_text(FALSE_YAML, encoding="utf-8")
        self.settings = self.tmp / "config" / "settings.json"

    def run_cli(self, command, *extra, env=None, settings=True):
        args = [sys.executable, str(SCRIPT), command, "--skills-root", str(self.root)]
        if settings:
            args += ["--settings", str(self.settings)]
        full_env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        full_env.update(env or {})
        proc = subprocess.run([*args, *extra], capture_output=True, text=True, env=full_env)
        return proc

    def write_settings(self, data):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def read_settings(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))


class ManagedSet(Base):
    def test_only_false_flag_under_policy_with_a_skill_md_is_managed(self):
        self.assertEqual(sl.managed_skills(self.root), ["arena", "bro"])

    def test_yaml_forms(self):
        cases = {
            "policy:\n  allow_implicit_invocation: false\n": True,
            "policy:\n  allow_implicit_invocation: False  # off\n": True,
            "policy:\n  allow_implicit_invocation: \"false\"\n": True,
            "policy: {allow_implicit_invocation: false}\n": True,
            "policy:\n  allow_implicit_invocation: true\n": False,
            "policy:\n  allow_implicit_invocation: falsey\n": False,
            "allow_implicit_invocation: false\n": False,
            "policy:\n  other: 1\ninterface:\n  allow_implicit_invocation: false\n": False,
            "": False,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertIs(sl.disables_implicit_invocation(text), expected)


class OtherSuites(Base):
    def setUp(self):
        super().setUp()
        make_skill(self.root, "grill-me", FALSE_YAML)
        make_skill(self.root, "handoff", None)

    def test_skills_from_other_suites_are_left_alone(self):
        self.write_settings({"skillOverrides": {"handoff": "name-only", "grill-me": "on"}})
        done = self.run_cli("install")
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual((out["added"], out["removed"], out["state"]), (["arena", "bro"], [], "current"))
        self.assertEqual(self.read_settings()["skillOverrides"],
                         {"handoff": "name-only", "grill-me": "on", "arena": "name-only", "bro": "name-only"})


class FreshInstall(Base):
    def test_creates_missing_file_and_parent(self):
        proc = self.run_cli("install")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read_settings(), {"skillOverrides": {"arena": "name-only", "bro": "name-only"}})
        self.assertTrue(self.settings.read_text(encoding="utf-8").endswith("}\n"))
        self.assertIn('\n  "skillOverrides": {\n    "arena": "name-only"', self.settings.read_text(encoding="utf-8"))
        out = json.loads(proc.stdout)
        self.assertEqual(out["settings"], str(self.settings))
        self.assertEqual(out["skills_root"], str(self.root))
        self.assertEqual(out["name_only"], 2)
        self.assertEqual(out["added"], ["arena", "bro"])
        self.assertEqual(out["removed"], [])
        self.assertEqual(out["missing"], [])
        self.assertEqual(out["extra"], [])
        self.assertEqual(out["kept_off"], [])
        self.assertEqual(out["state"], "current")
        self.assertIs(out["written"], True)

    def test_check_on_missing_file_is_stale_and_writes_nothing(self):
        proc = self.run_cli("check")
        self.assertEqual(proc.returncode, 1)
        out = json.loads(proc.stdout)
        self.assertEqual(out["missing"], ["arena", "bro"])
        self.assertEqual(out["state"], "stale")
        self.assertFalse(self.settings.exists())


class Merge(Base):
    def test_keeps_unrelated_keys_and_user_entries(self):
        original = {
            "model": "opus",
            "env": {"X": "1"},
            "skillOverrides": {"my-own-skill": "off", "other-name-only": "name-only"},
            "hooks": {},
        }
        self.write_settings(original)
        proc = self.run_cli("install")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            self.read_settings(),
            {
                "model": "opus",
                "env": {"X": "1"},
                "skillOverrides": {
                    "my-own-skill": "off",
                    "other-name-only": "name-only",
                    "arena": "name-only",
                    "bro": "name-only",
                },
                "hooks": {},
            },
        )
        self.assertEqual(list(self.read_settings()), ["model", "env", "skillOverrides", "hooks"])

    def test_off_is_kept_and_reported_not_failed(self):
        self.write_settings({"skillOverrides": {"arena": "off", "bro": "name-only"}})
        check = self.run_cli("check")
        self.assertEqual(check.returncode, 0)
        out = json.loads(check.stdout)
        self.assertEqual(out["kept_off"], ["arena"])
        self.assertEqual(out["missing"], [])
        self.assertEqual(out["state"], "current")
        install = self.run_cli("install")
        self.assertEqual(json.loads(install.stdout)["written"], False)
        self.assertEqual(self.read_settings()["skillOverrides"]["arena"], "off")

    def test_other_values_are_replaced(self):
        for value in ("user-invocable-only", "on", "bogus", None, 3):
            with self.subTest(value=value):
                self.write_settings({"skillOverrides": {"arena": value, "bro": "name-only"}})
                check = self.run_cli("check")
                self.assertEqual(check.returncode, 1)
                self.assertEqual(json.loads(check.stdout)["missing"], ["arena"])
                install = self.run_cli("install")
                out = json.loads(install.stdout)
                self.assertEqual(out["added"], ["arena"])
                self.assertEqual(self.read_settings()["skillOverrides"], {"arena": "name-only", "bro": "name-only"})

    def test_extra_name_only_for_unmanaged_skill_is_removed(self):
        self.write_settings(
            {"skillOverrides": {"arena": "name-only", "bro": "name-only", "how": "name-only", "why": "off", "outside": "name-only"}}
        )
        check = self.run_cli("check")
        self.assertEqual(check.returncode, 1)
        self.assertEqual(json.loads(check.stdout)["extra"], ["how"])
        install = self.run_cli("install")
        out = json.loads(install.stdout)
        self.assertEqual(out["removed"], ["how"])
        self.assertEqual(out["added"], [])
        self.assertEqual(out["state"], "current")
        self.assertEqual(
            self.read_settings()["skillOverrides"],
            {"arena": "name-only", "bro": "name-only", "why": "off", "outside": "name-only"},
        )

    def test_names_outside_the_root_are_never_reported(self):
        self.write_settings({"skillOverrides": {"arena": "name-only", "bro": "name-only", "outside": "name-only"}})
        out = json.loads(self.run_cli("check").stdout)
        self.assertEqual(out["extra"], [])
        self.assertEqual(out["state"], "current")


class Idempotence(Base):
    def test_second_install_changes_nothing(self):
        self.write_settings({"model": "opus", "skillOverrides": {"how": "name-only", "arena": "user-invocable-only"}})
        first = json.loads(self.run_cli("install").stdout)
        self.assertIs(first["written"], True)
        after_first = self.settings.read_bytes()
        mtime = self.settings.stat().st_mtime_ns
        second = json.loads(self.run_cli("install").stdout)
        self.assertIs(second["written"], False)
        self.assertEqual(second["added"], [])
        self.assertEqual(second["removed"], [])
        self.assertEqual(second["state"], "current")
        self.assertEqual(self.settings.read_bytes(), after_first)
        self.assertEqual(self.settings.stat().st_mtime_ns, mtime)

    def test_current_file_with_other_formatting_is_not_rewritten(self):
        compact = '{"skillOverrides":{"arena":"name-only","bro":"name-only"}}'
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(compact, encoding="utf-8")
        out = json.loads(self.run_cli("install").stdout)
        self.assertIs(out["written"], False)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), compact)

    def test_no_temp_files_left_behind(self):
        self.run_cli("install")
        self.assertEqual([p.name for p in self.settings.parent.iterdir()], ["settings.json"])

    def test_symlinked_settings_keeps_the_link(self):
        target = self.tmp / "dotfiles" / "settings.json"
        target.parent.mkdir()
        target.write_text('{"model": "opus"}\n', encoding="utf-8")
        self.settings.parent.mkdir(parents=True)
        self.settings.symlink_to(target)
        self.assertEqual(self.run_cli("install").returncode, 0)
        self.assertTrue(self.settings.is_symlink())
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["model"], "opus")
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["skillOverrides"]["arena"], "name-only")


class ErrorExits(Base):
    def assert_refused(self, content):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_bytes(content)
        for command in ("check", "install"):
            with self.subTest(command=command, content=content):
                proc = self.run_cli(command)
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stdout, "")
                self.assertNotEqual(proc.stderr, "")
                self.assertEqual(self.settings.read_bytes(), content)

    def test_malformed_json_is_left_byte_identical(self):
        self.assert_refused(b'{"model": "opus", ')

    def test_empty_file(self):
        self.assert_refused(b"")

    def test_non_utf8(self):
        self.assert_refused(b'{"a": "\xff"}')

    def test_top_level_not_an_object(self):
        self.assert_refused(b'["skillOverrides"]\n')

    def test_skill_overrides_not_an_object(self):
        self.assert_refused(b'{"skillOverrides": ["arena"]}\n')

    def test_settings_path_is_a_directory(self):
        self.settings.mkdir(parents=True)
        for command in ("check", "install"):
            self.assertEqual(self.run_cli(command).returncode, 2)

    def test_empty_managed_set_means_wrong_root(self):
        empty = self.tmp / "wrong-root"
        empty.mkdir()
        make_skill(empty, "plain", TRUE_YAML)
        for command in ("check", "install"):
            with self.subTest(command=command):
                proc = subprocess.run(
                    [sys.executable, str(SCRIPT), command, "--settings", str(self.settings), "--skills-root", str(empty)],
                    capture_output=True, text=True,
                )
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stdout, "")
                self.assertFalse(self.settings.exists())

    def test_current_check_exits_zero(self):
        self.write_settings({"skillOverrides": {"arena": "name-only", "bro": "name-only"}})
        self.assertEqual(self.run_cli("check").returncode, 0)


class DefaultSettingsPath(Base):
    def test_claude_config_dir_sets_the_default(self):
        config = self.tmp / "custom-config"
        proc = self.run_cli("install", env={"CLAUDE_CONFIG_DIR": str(config)}, settings=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["settings"], str(config / "settings.json"))
        self.assertEqual(
            json.loads((config / "settings.json").read_text(encoding="utf-8")),
            {"skillOverrides": {"arena": "name-only", "bro": "name-only"}},
        )

    def test_empty_claude_config_dir_falls_back_to_home(self):
        home = self.tmp / "home"
        home.mkdir()
        proc = self.run_cli("check", env={"CLAUDE_CONFIG_DIR": "", "HOME": str(home)}, settings=False)
        self.assertEqual(json.loads(proc.stdout)["settings"], str(home / ".claude" / "settings.json"))

    def test_default_skills_root_is_two_levels_above_the_script(self):
        installed = self.tmp / "installed"
        scripts = installed / "setup-pstack" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "skill-listing.py").write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        make_skill(installed, "arena", FALSE_YAML)
        (installed / "setup-pstack" / "SKILL.md").write_text("---\nname: setup-pstack\n---\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(scripts / "skill-listing.py"), "check", "--settings", str(self.settings)],
            capture_output=True, text=True,
        )
        out = json.loads(proc.stdout)
        self.assertEqual(out["skills_root"], str(installed))
        self.assertEqual(out["missing"], ["arena"])


class RealSkillsRoot(unittest.TestCase):
    def test_managed_set_is_the_47_openai_yaml_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "check", "--settings", str(settings), "--skills-root", str(REPO / "skills")],
                capture_output=True, text=True,
            )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(len(REAL_MANAGED), 47)
        self.assertEqual(out["name_only"], 47)
        self.assertEqual(out["missing"], sorted(REAL_MANAGED))
        self.assertEqual(out["extra"], [])
        self.assertEqual(out["kept_off"], [])


if __name__ == "__main__":
    unittest.main()
