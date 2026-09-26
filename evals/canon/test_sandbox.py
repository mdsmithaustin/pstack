import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "oracles"))

import sandbox  # noqa: E402
import sbx_inside  # noqa: E402
import test_workspace  # noqa: E402
import workspace  # noqa: E402
from shared import apply_diff, workspace_diff  # noqa: E402

screen = test_workspace.screen

CLAUDE_HARNESS_ARGV = ["-p", "--output-format", "stream-json", "--verbose", "--no-session-persistence", "--model", "sonnet"]
CODEX_HARNESS_ARGV = ["exec", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write", "--model", "gpt-6-sol",
                      "--ephemeral", "--ignore-user-config", "--ignore-rules", "--output-last-message", "/host/tmp/last.json", "-"]


class AgentCommandTests(unittest.TestCase):
    def test_claude_keeps_its_session_and_gets_every_tool_inside_the_sandbox(self):
        command, last_message = sandbox.agent_command("claude", CLAUDE_HARNESS_ARGV)

        self.assertEqual(command, [
            "claude", "-p", "--output-format", "stream-json", "--verbose", "--model", "sonnet",
            "--setting-sources", "project", "--permission-mode", "bypassPermissions",
            "--strict-mcp-config", "--allowedTools", "TodoWrite",
        ])
        self.assertIsNone(last_message)

    def test_codex_keeps_its_rollouts_and_sandbox_config_and_writes_its_last_message_inside(self):
        command, last_message = sandbox.agent_command("codex", CODEX_HARNESS_ARGV)

        self.assertEqual(command, [
            "codex", "exec", "--json", "--skip-git-repo-check", "--sandbox", "danger-full-access", "--model", "gpt-6-sol",
            "--ignore-rules", "--output-last-message", "/tmp/canon-last-message.txt",
            "-c", "mcp_servers.mcp-gateway.enabled=false", "-",
        ])
        self.assertEqual(last_message, "/host/tmp/last.json")


class ClaudeStreamTests(unittest.TestCase):
    def test_every_result_but_the_last_is_dropped_and_the_rest_keep_their_order(self):
        stream = [
            b'{"type":"system","subtype":"init"}\n',
            b'{"type":"assistant","message":"spawn"}\n',
            b'{"type":"result","result":"Waiting on the delegate."}\n',
            b'{"type":"assistant","message":"delegate done"}\n',
            b'not json\n',
            b'{"type":"result","result":"Final answer."}\n',
            b'{"type":"system","subtype":"after"}\n',
        ]

        self.assertEqual(list(sandbox.last_result_only(stream)), [
            b'{"type":"system","subtype":"init"}\n',
            b'{"type":"assistant","message":"spawn"}\n',
            b'{"type":"assistant","message":"delegate done"}\n',
            b'not json\n',
            b'{"type":"result","result":"Final answer."}\n',
            b'{"type":"system","subtype":"after"}\n',
        ])

    def test_a_stream_with_one_result_passes_unchanged(self):
        stream = [b'{"type":"assistant"}\n', b'{"type":"result","result":"ok"}\n', b'["result"]\n']

        self.assertEqual(list(sandbox.last_result_only(stream)), stream)


    def test_claude_run_keeps_the_raw_stream_and_forwards_one_result(self):
        agent = ("import json, sys\n"
                 "prompt = sys.stdin.read()\n"
                 "print(json.dumps({'type': 'result', 'result': 'wait'}))\n"
                 "print(json.dumps({'type': 'result', 'result': prompt}))\n"
                 "sys.exit(7)\n")

        class LocalBox:
            def exec_stdout(self, *argv, stdin=None):
                return subprocess.Popen([*argv], stdin=stdin, stdout=subprocess.PIPE)

        with tempfile.TemporaryDirectory() as directory:
            prompt, raw, out = Path(directory) / "prompt.txt", Path(directory) / "raw-stream.jsonl", io.BytesIO()
            prompt.write_bytes(b"done")

            code = sandbox.stream_claude(LocalBox(), [sys.executable, "-c", agent], prompt, raw, out)

            self.assertEqual((code, out.getvalue()), (7, b'{"type": "result", "result": "done"}\n'))
            self.assertEqual(raw.read_bytes(), b'{"type": "result", "result": "wait"}\n{"type": "result", "result": "done"}\n')


class TemplateNameTests(unittest.TestCase):
    def test_deps_tag_names_agent_repo_and_commit_and_changes_with_the_uv_pin(self):
        config = {"uv": "0.12.17", "repos": {"omnigent": {"python": "3.12", "sync": ["--frozen"], "package": "omnigent"}},
                  "agents": {"codex": {"kit": "codex", "cli": "@openai/codex@0.157.0"}, "claude": {"kit": "claude"}}}
        commit = "02969a131c72d74c00c5800d8e82ae831f8ec5e5"

        with mock.patch.object(sandbox, "CONFIG", config):
            tags = [sandbox.deps_tag("codex", "omnigent", commit), sandbox.deps_tag("claude", "omnigent", commit)]
            config["uv"] = "0.12.18"
            tags.append(sandbox.deps_tag("codex", "omnigent", commit))

        self.assertEqual(tags, ["canon-deps-codex-omnigent-02969a131c72:47f72d544d42",
                                "canon-deps-claude-omnigent-02969a131c72:331004b2e409",
                                "canon-deps-codex-omnigent-02969a131c72:ccddbecf90ae"])

    def test_deps_env_keeps_uv_offline_and_outside_the_workspace(self):
        self.assertEqual(sandbox.deps_env("hermes"), {
            "UV_PROJECT_ENVIRONMENT": "/opt/canon-deps/hermes/venv",
            "UV_CACHE_DIR": "/opt/canon-deps/uv-cache",
            "UV_PYTHON_INSTALL_DIR": "/opt/canon-deps/python",
            "UV_PYTHON": "3.11",
            "UV_PYTHON_DOWNLOADS": "never",
            "UV_OFFLINE": "1",
        })


class ScreenRunnerTests(unittest.TestCase):
    def test_sbx_runner_refuses_a_pasted_project_case(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(screen.ScreenError, "workspace cases only"):
            screen.backend_args("claude", Path(directory), "poteto-mode", False, "sbx")

    def test_sbx_runner_wraps_both_agents_in_sandbox_py(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            claude = screen.backend_args("claude", out, "poteto-mode", True, "sbx")
            codex = screen.backend_args("codex", out, "poteto-mode", True, "sbx")
            wrapper = (out / "entry" / "claude-sbx").read_text()

        self.assertEqual(claude, ["--claude-bin", out / "entry" / "claude-sbx"])
        self.assertEqual(codex, ["--codex-cmd", f"{out / 'entry' / 'codex-sbx'} exec --json --skip-git-repo-check --sandbox workspace-write"])
        self.assertIn(f"{ROOT / 'sandbox.py'} wrap --agent claude --token /poteto-mode --discovery .claude/skills -- \"$@\"", wrapper)


class StagingTests(test_workspace.ShopRepo):
    def test_staged_checkout_clones_without_the_host_mirror(self):
        root = self.harness_workspace("staged", "# Poteto mode\n")
        workspace.materialize(root, self.mirror, self.commit, self.spec.overlay)

        sandbox.self_contained(root)
        clone = self.base / "clone"
        subprocess.run(["git", "clone", "-q", str(root), str(clone)], env={**os.environ, **workspace.GIT_ENV}, check=True, capture_output=True)

        self.assertFalse((root / ".git" / "objects" / "info" / "alternates").exists())
        self.assertEqual(test_workspace.git(clone, "rev-parse", "HEAD").strip(), self.commit)
        self.assertEqual((clone / "app" / "orders.py").read_text(), test_workspace.UPSTREAM["app/orders.py"])
        self.assertFalse((clone / "CONTEXT.md").exists())


class InsideTests(test_workspace.ShopRepo):
    """sbx_inside.py runs on a plain clone here, as it does inside the sandbox."""

    def clone(self):
        stage = self.base / "stage"
        stage.mkdir()
        workspace.materialize(stage, self.mirror, self.commit, {})
        sandbox.self_contained(stage)
        clone = self.base / "clone"
        subprocess.run(["git", "clone", "-q", str(stage), str(clone)], env={**os.environ, **workspace.GIT_ENV}, check=True, capture_output=True)
        return clone

    def payload(self, clone, agent):
        payload = self.base / "payload"
        tracked = screen.tracked("skills")
        for path, data in tracked.items():
            (payload / "skills" / "pstack" / path).parent.mkdir(parents=True, exist_ok=True)
            (payload / "skills" / "pstack" / path).write_bytes(data)
        (payload / "overlay").mkdir(parents=True)
        (payload / "overlay" / "CONTEXT.md").write_bytes(test_workspace.CONTEXT)
        tree = workspace.reference_checkout(self.spec)[1]
        spec = {"repo": "shop", "commit": self.commit, "tree": tree}
        manifest = sandbox.manifest(agent, clone, spec, sandbox.CONFIG["agents"][agent]["discovery"])
        (payload / "manifest.json").write_text(json.dumps(manifest))
        return payload / "manifest.json", tree

    def test_setup_mounts_the_skills_registers_the_persona_and_keeps_the_recorded_tree(self):
        clone = self.clone()
        manifest, tree = self.payload(clone, "claude")

        record = sbx_inside.setup(manifest)

        self.assertEqual(record, {"persona": [".claude/agents/comment-sicko.md", ".claude/agents/poteto-agent.md"], "deps": None, "tree": tree})
        self.assertTrue((clone / ".claude" / "skills" / "poteto-mode" / "SKILL.md").is_file())
        self.assertIn(f"{clone}/.claude/skills/poteto-mode/SKILL.md", (clone / ".claude" / "agents" / "poteto-agent.md").read_text())
        self.assertEqual(test_workspace.git(clone, "status", "--porcelain"), "?? CONTEXT.md\n")

    def test_codex_setup_trusts_the_project_so_its_roles_load(self):
        clone = self.clone()
        manifest, tree = self.payload(clone, "codex")
        home = self.base / "home"
        (home / ".codex").mkdir(parents=True)
        (home / ".codex" / "config.toml").write_text('approval_policy = "never"\n')

        with mock.patch.object(sbx_inside, "HOME", home):
            record = sbx_inside.setup(manifest)

        self.assertEqual(record["persona"], [".codex/agents/comment-sicko.toml", ".codex/agents/poteto-agent.toml"])
        self.assertEqual((home / ".codex" / "config.toml").read_text(),
                         f'approval_policy = "never"\n\n[projects."{clone}"]\ntrust_level = "trusted"\n')

    def test_setup_refuses_a_clone_at_another_commit(self):
        clone = self.clone()
        manifest, _ = self.payload(clone, "claude")
        record = json.loads(manifest.read_text())
        record["commit"] = "0" * 40
        manifest.write_text(json.dumps(record))

        with self.assertRaisesRegex(workspace.WorkspaceError, "the clone is at"):
            sbx_inside.setup(manifest)

    def test_harvest_packs_the_diff_and_every_session_transcript(self):
        clone = self.clone()
        manifest, _ = self.payload(clone, "claude")
        sbx_inside.setup(manifest)
        (clone / "app" / "orders.py").write_text("changed\n")
        home = self.base / "home"
        subagents = home / ".claude" / "projects" / "-work" / "s1" / "subagents"
        subagents.mkdir(parents=True)
        (subagents / "agent-a1.jsonl").write_text("{}\n")

        with mock.patch.object(sbx_inside, "HOME", home):
            record = sbx_inside.harvest(manifest, self.base / "out")

        self.assertGreater(record["diff_bytes"], 0)
        self.assertEqual(sorted(apply_diff(workspace.reference_checkout(self.spec)[0], (self.base / "out" / "workspace.diff").read_text())),
                         ["app/orders.py"])
        self.assertTrue((self.base / "out" / "transcripts" / "claude" / "-work" / "s1" / "subagents" / "agent-a1.jsonl").is_file())
        self.assertTrue((self.base / "out.tar").is_file())


RUN_DENY = ["api.github.com", "archive.ubuntu.com", "codeload.github.com", "download.docker.com", "files.pythonhosted.org",
            "github.com", "objects.githubusercontent.com", "ports.ubuntu.com", "pypi.org", "raw.githubusercontent.com",
            "registry.npmjs.org", "release-assets.githubusercontent.com", "releases.astral.sh", "security.ubuntu.com"]


class FakeSbx:
    """Stands in for the sbx CLI: records every argv and answers the calls
    wrap makes. The policy allows the model API and the hosts in allowed."""

    def __init__(self, tree, allowed=()):
        self.tree, self.allowed, self.calls = tree, {"api.openai.com", "chatgpt.com", *allowed}, []

    def __call__(self, *args, input=None, capture=True, check=True):
        args = [str(arg) for arg in args]
        self.calls.append(args)
        stdout = b""
        if args[:2] == ["policy", "check"]:
            stdout = json.dumps({"allowed": args[5] in self.allowed}).encode()
        elif args[:2] == ["policy", "ls"]:
            stdout = b'{"rules": []}'
        elif args[:2] == ["policy", "log"]:
            stdout = b"[]"
        elif args[0] == "exec" and "setup" in args:
            stdout = json.dumps({"tree": self.tree}).encode()
        elif args[0] == "cp" and args[2].startswith("/") and args[1].endswith(":/tmp/canon-out.tar"):
            with tarfile.open(args[2], "w") as archive:
                for name, data in {"inside.json": b"{}", "workspace.diff": b""}.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
        return subprocess.CompletedProcess(args, 0, stdout, b"")

    def agent_runs(self):
        return [call for call in self.calls if call[0] == "exec" and "timeout" in call]


class WrapPolicyTests(test_workspace.ShopRepo):
    """sandbox.py wrap for a Codex run, with sbx faked."""

    def wrap(self, fake):
        root = self.harness_workspace("wrapped", "# Poteto mode\n")
        arm = self.base / "arm"
        (arm / "overlay").mkdir(parents=True)
        (arm / "overlay" / "CONTEXT.md").write_bytes(test_workspace.CONTEXT)
        (arm / "workspace.json").write_text(json.dumps({"repo": "shop", "commit": self.commit, "mirror": str(self.mirror), "tree": fake.tree}))
        environment = {"CANON_WORKSPACE": str(arm), "CANON_HARVEST": str(self.base / "harvest")}
        previous = Path.cwd()
        os.chdir(root)
        try:
            with mock.patch.object(sandbox, "sbx", fake), mock.patch.dict(os.environ, environment), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = sandbox.wrap(["--agent", "codex", "--", *CODEX_HARNESS_ARGV], stdin=io.BytesIO(b"Add amendments."))
        finally:
            os.chdir(previous)
        return code, root, json.loads((self.base / "harvest" / "0001" / "workspace.json").read_text())

    def test_create_clones_the_checkout_denies_the_run_list_and_mounts_nothing_else(self):
        fake = FakeSbx(workspace.reference_checkout(self.spec)[1])

        code, root, record = self.wrap(fake)

        self.assertEqual(code, 0)
        self.assertEqual(fake.calls[0], ["create", "--skills", "off", "--name", record["sandbox"], "-q", "--clone",
                                         *[arg for host in RUN_DENY for arg in ("--deny-network", host)], "codex", str(root.resolve())])
        self.assertEqual(record["egress"], {**{host: False for host in RUN_DENY}, "example.org": False})
        self.assertEqual(len(fake.agent_runs()), 1)

    def test_a_policy_that_allows_a_probe_host_refuses_the_run_before_the_agent_starts(self):
        fake = FakeSbx(workspace.reference_checkout(self.spec)[1], allowed={"example.org", "pypi.org"})

        code, _, record = self.wrap(fake)

        self.assertEqual(code, workspace.REFUSED)
        self.assertEqual(record["error"], "the sandbox's network policy does not deny example.org, pypi.org; "
                                          "check the global policy with `sbx policy ls`")
        self.assertEqual((record["egress"]["example.org"], record["egress"]["pypi.org"], record["egress"]["github.com"]), (True, True, False))
        self.assertEqual(fake.agent_runs(), [])
        self.assertEqual(fake.calls[-1], ["rm", "--force", record["sandbox"]])


def sandboxes_available():
    return (os.environ.get("CANON_SBX_E2E") == "1" and shutil.which("sbx") is not None
            and test_workspace.harness_available())


@unittest.skipUnless(sandboxes_available(), "needs CANON_SBX_E2E=1, Docker Sandboxes (sbx), and the skill-ci harness")
class SandboxedStandInRunTests(test_workspace.ShopRule):
    """Both arms of the shop rule answered by offline/sbx-agent inside real sandboxes."""

    def run_agent(self, agent):
        environment = {"CANON_SBX_STANDIN": str(ROOT / "offline" / "sbx-agent")}
        with mock.patch.dict(os.environ, environment), contextlib.redirect_stdout(io.StringIO()) as printed:
            screen.run(agent, self.out, [self.rule], "sonnet" if agent == "claude" else "gpt-6-sol", 1, None, "poteto-mode", "sbx")
        return printed.getvalue()

    def check(self, agent, transcript):
        printed = self.run_agent(agent)
        compared = json.loads((self.out / "compare.json").read_text())
        self.assertEqual([pair["outcome"] for pair in compared["pairs"]], ["separates"], printed[-3000:])
        checkout = workspace.reference_checkout(workspace.parse_spec(self.rule.cases[0].root, self.rule.cases[0].workspace))[0]
        work = self.out / agent / "orders-workspace" / "orders-amend"
        self.assertEqual(sorted(apply_diff(checkout, workspace_diff(work / "amended" / "runs" / "orders-amend" / "with_skill"))),
                         ["app/amend_log.md", "app/legacy.py", "app/orders.py"])
        for arm in ("current", "amended"):
            harvest = work / arm / "harvest" / "orders-amend" / "with_skill"
            record = json.loads((harvest / "workspace.json").read_text())
            self.assertEqual(record["agent_rc"], 0, record)
            self.assertEqual(record["tree"], record["expected_tree"])
            self.assertIs(record["reachable"][sandbox.CONFIG["agents"][agent]["api"][0]], True)
            self.assertEqual((record["egress"]["pypi.org"], record["egress"]["example.org"]), (False, False))
            self.assertTrue(set(record["timings"]) >= {"create_s", "setup_s", "agent_s", "harvest_s", "destroy_s"})
            self.assertTrue(list(harvest.glob(transcript)), sorted(str(p) for p in harvest.rglob("*")))
            self.assertTrue((harvest / "network-log.json").is_file())
            if agent == "claude":
                raw = (harvest / "raw-stream.jsonl").read_bytes().splitlines()
                self.assertEqual([json.loads(line)["result"] for line in raw if sandbox.is_result(line)][:1], ["Waiting on the delegate."])
                self.assertEqual(sum(map(sandbox.is_result, raw)), 2)
            else:
                self.assertFalse((harvest / "raw-stream.jsonl").exists())
        self.assertNotIn(record["sandbox"], sandbox.sandboxes())

    def test_claude_stand_in_runs_in_a_sandbox_and_the_rule_separates(self):
        self.check("claude", "transcripts/claude/*/*/subagents/agent-*.jsonl")

    def test_codex_stand_in_runs_in_a_sandbox_and_the_rule_separates(self):
        self.check("codex", "transcripts/codex/sessions/*/*/*/rollout-*.jsonl")


if __name__ == "__main__":
    unittest.main()
