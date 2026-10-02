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
            b'{"type":"system","subtype":"after"}\n',
            b'{"type":"result","result":"Final answer."}\n',
        ])

    def test_a_stream_that_ends_with_its_one_result_passes_unchanged(self):
        stream = [b'{"type":"assistant"}\n', b'["result"]\n', b'{"type":"result","result":"ok"}\n']

        self.assertEqual(list(sandbox.last_result_only(stream)), stream)

    def test_task_notifications_after_the_last_result_move_before_it(self):
        stream = [
            b'{"type":"assistant","message":"done"}\n',
            b'{"type":"result","result":"Final answer."}\n',
            b'{"type":"system","subtype":"background_tasks_changed","tasks":[]}\n',
            b'{"type":"system","subtype":"task_notification","status":"stopped"}\n',
        ]

        self.assertEqual(list(sandbox.last_result_only(stream)), [
            b'{"type":"assistant","message":"done"}\n',
            b'{"type":"system","subtype":"background_tasks_changed","tasks":[]}\n',
            b'{"type":"system","subtype":"task_notification","status":"stopped"}\n',
            b'{"type":"result","result":"Final answer."}\n',
        ])


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

    def test_judge_tag_covers_the_kit_and_cli_pin_but_not_uv(self):
        config = {"uv": "0.12.17", "repos": {"omnigent": {"python": "3.12", "sync": ["--frozen"], "package": "omnigent"}},
                  "agents": {"codex": {"kit": "codex", "cli": "@openai/codex@0.157.0"}, "claude": {"kit": "claude"}}}

        with mock.patch.object(sandbox, "CONFIG", config):
            tags = [sandbox.deps_tag("codex")]
            config["uv"] = "0.12.18"
            tags.append(sandbox.deps_tag("codex"))
            config["agents"]["codex"]["cli"] = "@openai/codex@0.158.0"
            tags.append(sandbox.deps_tag("codex"))
            with self.assertRaisesRegex(sandbox.SandboxError, "claude"):
                sandbox.deps_tag("claude")

        self.assertEqual(tags, ["canon-judge-codex:9ea5b36366e7", "canon-judge-codex:9ea5b36366e7", "canon-judge-codex:2e954a8479b3"])

    def test_deps_env_keeps_uv_offline_and_outside_the_workspace(self):
        with mock.patch.object(sandbox.workspace, "git", side_effect=sandbox.workspace.WorkspaceError("no .python-version")):
            env = sandbox.deps_env("hermes", "0" * 40)

        self.assertEqual(env, {
            "UV_PROJECT_ENVIRONMENT": "/opt/canon-deps/hermes/venv",
            "UV_CACHE_DIR": "/opt/canon-deps/uv-cache",
            "UV_PYTHON_INSTALL_DIR": "/opt/canon-deps/python",
            "UV_PYTHON": "3.11",
            "UV_PYTHON_DOWNLOADS": "never",
            "UV_OFFLINE": "1",
        })


    def test_a_commit_that_pins_python_uses_its_pin(self):
        with mock.patch.object(sandbox.workspace, "git", return_value=b"3.14\n"):
            self.assertEqual(sandbox.deps_env("hermes", "0" * 40)["UV_PYTHON"], "3.14")


class SyncArgsTests(unittest.TestCase):
    CONFIG = {"repos": {"omnigent": {"sync": ["--frozen"], "tools": {"group": "test", "extra": "dev"}}}}

    def sync_args(self, pyproject):
        with mock.patch.object(sandbox, "CONFIG", self.CONFIG), mock.patch.object(sandbox.workspace, "git", return_value=pyproject.encode()):
            return sandbox.sync_args("omnigent", "0" * 40)

    def test_a_commit_with_the_dependency_group_syncs_the_group(self):
        self.assertEqual(self.sync_args('[project]\nname = "o"\n[dependency-groups]\ntest = ["pytest"]\n'), ["--frozen", "--group", "test"])

    def test_a_commit_from_before_the_group_syncs_the_extra(self):
        self.assertEqual(self.sync_args('[project]\nname = "o"\n[project.optional-dependencies]\ndev = ["pytest"]\n'), ["--frozen", "--extra", "dev"])

    def test_a_commit_with_neither_is_refused(self):
        with self.assertRaisesRegex(sandbox.SandboxError, r"^omnigent at 000000000000 declares neither dependency group 'test' nor extra 'dev'$"):
            self.sync_args('[project]\nname = "o"\n')


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


class HistoryStagingTests(test_workspace.HistoryRepo):
    def staged_clone(self, history):
        mirror = workspace.fetch("shop", self.head, self.upstream, history=True)
        root = self.harness_workspace("staged", "# Poteto mode\n")
        workspace.materialize(root, mirror, self.head, {}, history=history)
        sandbox.self_contained(root)
        clone = self.base / "clone"
        subprocess.run(["git", "clone", "-q", str(root), str(clone)], env={**os.environ, **workspace.GIT_ENV}, check=True, capture_output=True)
        return clone

    def test_staged_history_checkout_clones_with_every_ancestor(self):
        self.assertEqual(self.log(self.staged_clone(True)), "Keep legacy orders readable (#12)\nShop\n")

    def test_staged_checkout_without_history_clones_only_the_pinned_commit(self):
        self.assertEqual(self.log(self.staged_clone(False)), "Keep legacy orders readable (#12)\n")


class RegisterAgentsTests(unittest.TestCase):
    def test_a_skills_tree_from_before_effort_agents_still_registers_its_personas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "skills" / "pstack" / "pstack-harness" / "scripts" / "subagents.py"
            script.parent.mkdir(parents=True)
            persona = root / ".claude" / "agents" / "poteto-agent.md"
            script.write_text(f"import json\nprint(json.dumps({{'roles': [{{'path': {str(persona)!r}}}]}}))\n")

            written = sbx_inside.register_agents(root, {"discovery": "skills/pstack", "harness": "claude"})

        self.assertEqual(written, [".claude/agents/poteto-agent.md"])


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

        self.assertEqual(record, {"agents": [".claude/agents/comment-sicko.md", ".claude/agents/poteto-agent.md", ".claude/agents/pstack-effort-high.md",
                                              ".claude/agents/pstack-effort-low.md", ".claude/agents/pstack-effort-max.md", ".claude/agents/pstack-effort-medium.md",
                                              ".claude/agents/pstack-effort-xhigh.md"],
                                   "deps": None, "tree": tree})
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

        self.assertEqual(record["agents"], [".codex/agents/comment-sicko.toml", ".codex/agents/poteto-agent.toml"])
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

    def test_setup_refuses_a_history_case_whose_clone_is_shallow(self):
        clone = self.clone()
        manifest, _ = self.payload(clone, "claude")
        record = json.loads(manifest.read_text())
        record["history"] = True
        manifest.write_text(json.dumps(record))

        with self.assertRaisesRegex(workspace.WorkspaceError, "the clone lacks the history"):
            sbx_inside.setup(manifest)

    def test_setup_refuses_when_the_offline_uv_sync_fails_and_keeps_its_stderr(self):
        clone = self.clone()
        manifest, _ = self.payload(clone, "claude")
        record = json.loads(manifest.read_text())
        record["deps"] = {"env": {"UV_PROJECT_ENVIRONMENT": str(self.base / "venv"), "UV_OFFLINE": "1"}, "sync": ["--frozen"]}
        manifest.write_text(json.dumps(record))
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        (bin_dir / "uv").write_text("#!/bin/sh\necho 'error: Failed to fetch: `https://pypi.org/simple/pytest/`' >&2\nexit 2\n")
        (bin_dir / "uv").chmod(0o755)

        with mock.patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}):
            with self.assertRaisesRegex(workspace.WorkspaceError,
                                        r"^offline uv sync failed \(2\): error: Failed to fetch: `https://pypi.org/simple/pytest/`$"):
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


RUN_DENY = ["api.github.com", "archive.ubuntu.com", "bridge.claudeusercontent.com", "claude.com", "code.claude.com",
            "codeload.github.com", "download.docker.com", "downloads.claude.ai", "files.pythonhosted.org", "github.com",
            "mcp-proxy.anthropic.com", "objects.githubusercontent.com", "platform.claude.com", "ports.ubuntu.com", "pypi.org",
            "raw.githubusercontent.com", "registry.npmjs.org", "release-assets.githubusercontent.com", "releases.astral.sh",
            "security.ubuntu.com"]


class FakeSbx:
    """Stands in for the sbx CLI: records every argv and answers the calls
    wrap makes. The policy allows the model API and the hosts in allowed, and
    answers a check on a host in unanswered with JSON that carries no decision."""

    def __init__(self, tree, allowed=(), unanswered=(), setup_error=None):
        self.tree, self.allowed, self.unanswered, self.calls = tree, {"api.openai.com", "chatgpt.com", *allowed}, set(unanswered), []
        self.setup_error = setup_error
        self.saved = []

    def __call__(self, *args, input=None, capture=True, check=True):
        args = [str(arg) for arg in args]
        self.calls.append(args)
        stdout = b""
        if args[:2] == ["policy", "check"]:
            answer = {"host": args[5]} if args[5] in self.unanswered else {"allowed": args[5] in self.allowed}
            stdout = json.dumps(answer).encode()
        elif args[:2] == ["policy", "ls"]:
            stdout = b'{"rules": []}'
        elif args[:2] == ["policy", "log"]:
            stdout = b"[]"
        elif args[:3] == ["template", "ls", "--json"]:
            stdout = json.dumps([{"repository": f"docker.io/library/{tag.split(':')[0]}", "tag": tag.split(":")[1], "size": 7}
                                 for tag in self.saved]).encode()
        elif args[:2] == ["template", "save"]:
            self.saved.append(args[3])
        elif args[0] == "exec" and args[-1] == "codex --version":
            stdout = b"codex-cli 0.160.0\n"
        elif args[0] == "exec" and "setup" in args:
            if self.setup_error:
                return subprocess.CompletedProcess(args, 1, b"", self.setup_error.encode())
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

    wrap_spec = {}

    def wrap(self, fake):
        root = self.harness_workspace("wrapped", "# Poteto mode\n")
        arm = self.base / "arm"
        (arm / "overlay").mkdir(parents=True)
        (arm / "overlay" / "CONTEXT.md").write_bytes(test_workspace.CONTEXT)
        (arm / "workspace.json").write_text(json.dumps({"repo": "shop", "commit": self.commit, "mirror": str(self.mirror), "tree": fake.tree, **self.wrap_spec}))
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

    def test_a_history_case_is_materialized_with_history_and_carries_it_into_the_manifest(self):
        fake = FakeSbx(workspace.reference_checkout(self.spec)[1])
        calls = []
        real = workspace.materialize

        def recording(*args):
            calls.append(args[-1])
            return real(*args[:-1], False)

        with mock.patch.object(workspace, "materialize", recording):
            original = self.wrap_spec
            self.wrap_spec = {"history": True}
            try:
                self.wrap(fake)
            finally:
                self.wrap_spec = original

        self.assertEqual(calls, [True])
        self.assertIs(sandbox.manifest("codex", Path("/w"), {"repo": "shop", "commit": "c", "tree": "t", "history": True}, None)["history"], True)

    def test_create_clones_the_checkout_denies_the_run_list_and_mounts_nothing_else(self):
        fake = FakeSbx(workspace.reference_checkout(self.spec)[1])

        code, root, record = self.wrap(fake)

        self.assertEqual(code, 0)
        self.assertEqual(fake.calls[0], ["create", "--skills", "off", "--name", record["sandbox"], "-q", "--clone",
                                         *[arg for host in RUN_DENY for arg in ("--deny-network", host)], "codex", str(root.resolve())])
        self.assertEqual(record["egress"], {**{host: False for host in RUN_DENY}, "example.org": False})
        self.assertEqual(len(fake.agent_runs()), 1)

    def test_a_policy_that_allows_a_probe_host_refuses_the_run_before_the_agent_starts(self):
        fake = FakeSbx(workspace.reference_checkout(self.spec)[1], allowed={"example.org", "platform.claude.com", "pypi.org"})

        code, _, record = self.wrap(fake)

        self.assertEqual(code, workspace.REFUSED)
        self.assertEqual(record["error"], "the sandbox's network policy does not deny example.org, platform.claude.com, pypi.org; "
                                          "check the global policy with `sbx policy ls`")
        self.assertEqual((record["egress"]["example.org"], record["egress"]["platform.claude.com"], record["egress"]["pypi.org"],
                          record["egress"]["github.com"]), (True, True, True, False))
        self.assertEqual(fake.agent_runs(), [])
        self.assertEqual(fake.calls[-1], ["rm", "--force", record["sandbox"]])

    def test_a_policy_answer_without_a_decision_refuses_the_run_before_the_agent_starts(self):
        fake = FakeSbx(workspace.reference_checkout(self.spec)[1], unanswered={"example.org"})

        code, _, record = self.wrap(fake)

        self.assertEqual(code, workspace.REFUSED)
        self.assertEqual(record["error"], "the sandbox's network policy does not deny example.org; "
                                          "check the global policy with `sbx policy ls`")
        self.assertEqual((record["egress"]["example.org"], record["egress"]["github.com"]), (None, False))
        self.assertEqual(fake.agent_runs(), [])


class ProbeSetupTests(unittest.TestCase):
    def test_a_failed_setup_stops_the_probe_before_any_check_or_agent_runs(self):
        fake = FakeSbx("unused", setup_error="WorkspaceError: the clone is at abc, not def")

        with mock.patch.object(sandbox, "sbx", fake), \
                self.assertRaisesRegex(sandbox.SandboxError, r"^sandbox setup failed \(1\): WorkspaceError: the clone is at abc, not def$"):
            sandbox.probe("codex")

        setup = next(index for index, call in enumerate(fake.calls) if call[0] == "exec" and "setup" in call)
        self.assertEqual([call[0] for call in fake.calls[setup + 1:]], ["rm"])


    def test_a_no_repo_probe_runs_the_pinned_cli_not_the_kits(self):
        pin = sandbox.CONFIG["agents"]["codex"]["cli"]
        fake = FakeSbx("unused", setup_error="WorkspaceError: stop here")

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(sandbox, "sbx", fake), \
                mock.patch.object(sandbox, "records_dir", return_value=Path(directory)), self.assertRaises(sandbox.SandboxError):
            sandbox.probe("codex")

        self.assertTrue(any(call[0] == "exec" and call[-4:] == ["npm", "install", "-g", pin] for call in fake.calls))
        creates = [call for call in fake.calls if call[0] == "create" and "--clone" in call]
        self.assertEqual([call[call.index("-t") + 1] for call in creates], [sandbox.deps_tag("codex")])

    def test_a_probe_for_an_agent_with_no_pin_installs_nothing(self):
        fake = FakeSbx("unused", setup_error="WorkspaceError: stop here")

        with mock.patch.object(sandbox, "sbx", fake), self.assertRaises(sandbox.SandboxError):
            sandbox.probe("claude")

        self.assertFalse(any("npm" in call for call in fake.calls))
        self.assertFalse(any(call[0] == "create" and "-t" in call for call in fake.calls))


class PersonasOfferedTests(unittest.TestCase):
    registered = [".codex/agents/comment-sicko.toml", ".codex/agents/poteto-agent.toml"]

    def test_codex_offers_a_persona_whose_role_the_request_names(self):
        body = {"tools": [{"name": "spawn_agent", "description": "Available roles:\npoteto-agent: scoped delegate\n"}]}

        self.assertEqual(sandbox.personas_offered("codex", self.registered, json.dumps(body)),
                         {"comment-sicko": False, "poteto-agent": True})

    def test_claude_offers_a_persona_that_init_lists_as_an_agent(self):
        registered = [".claude/agents/comment-sicko.md", ".claude/agents/pstack-effort-low.md"]

        self.assertEqual(sandbox.personas_offered("claude", registered, ["Explore", "comment-sicko"]),
                         {"comment-sicko": True, "pstack-effort-low": False})

    def test_a_probe_report_names_the_personas_that_are_not_offered(self):
        self.assertEqual(sandbox.personas_missing({"comment-sicko": False, "poteto-agent": True}), ["comment-sicko"])
        self.assertEqual(sandbox.personas_missing({"comment-sicko": True}), [])

    def test_the_probe_command_exits_nonzero_when_a_persona_is_missing(self):
        for missing, code in (["comment-sicko"], 1), ([], 0):
            report = {"personas offered": {"comment-sicko": not missing}, "personas missing": missing}
            with mock.patch.object(sandbox, "probe", return_value=report), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(sandbox.main(["probe", "--agent", "codex"]), code)


class JudgePolicyTests(unittest.TestCase):
    """sandbox.run_judge for a Claude judge, with sbx faked."""

    def judge(self, fake):
        with mock.patch.object(sandbox, "sbx", fake):
            return sandbox.run_judge("claude", "sonnet", "Judge this review.", {"type": "object"})

    def test_the_judge_runs_when_every_probe_host_is_denied(self):
        fake = FakeSbx(tree=None)

        record = self.judge(fake)

        self.assertEqual(record["egress"], {**{host: False for host in RUN_DENY}, "example.org": False})
        self.assertEqual([call[call.index("timeout") + 3] for call in fake.agent_runs()], ["claude"])

    def test_a_policy_that_allows_a_probe_host_refuses_the_judge_before_it_starts(self):
        fake = FakeSbx(tree=None, allowed={"example.org"})

        with self.assertRaisesRegex(sandbox.SandboxError, r"^the sandbox's network policy does not deny example.org; "
                                                          r"check the global policy with `sbx policy ls`$"):
            self.judge(fake)
        self.assertEqual(fake.agent_runs(), [])
        self.assertEqual(fake.calls[-1][:2], ["rm", "--force"])

    def test_a_policy_answer_without_a_decision_refuses_the_judge_before_it_starts(self):
        fake = FakeSbx(tree=None, unanswered={"example.org"})

        with self.assertRaisesRegex(sandbox.SandboxError, r"^the sandbox's network policy does not deny example.org; "):
            self.judge(fake)
        self.assertEqual(fake.agent_runs(), [])


JUDGE_CONFIG = {"uv": "0.12.17", "repos": {"omnigent": {"python": "3.12", "sync": ["--frozen"], "package": "omnigent"}},
                "agents": {"codex": {"kit": "codex", "cli": "@openai/codex@0.157.0", "api": ["chatgpt.com", "api.openai.com"]},
                           "claude": {"kit": "claude", "api": ["api.anthropic.com"]}}}
COMMIT = "02969a131c72d74c00c5800d8e82ae831f8ec5e5"
JUDGE_TAG = "canon-judge-codex:9ea5b36366e7"
REPO_TAG = "canon-deps-codex-omnigent-02969a131c72:47f72d544d42"


class JudgeTemplateTests(unittest.TestCase):
    def pick(self, backend, repo, commit, available):
        with mock.patch.object(sandbox, "CONFIG", JUDGE_CONFIG), mock.patch.object(sandbox, "templates", return_value=dict.fromkeys(available, {})):
            return sandbox.judge_template(backend, repo, commit)

    def test_a_codex_judge_with_no_repo_gets_the_cli_template(self):
        self.assertEqual(self.pick("codex", None, None, [JUDGE_TAG]), JUDGE_TAG)

    def test_a_codex_judge_prefers_its_repo_template(self):
        self.assertEqual(self.pick("codex", "omnigent", COMMIT, [JUDGE_TAG, REPO_TAG]), REPO_TAG)

    def test_a_codex_judge_falls_back_to_the_cli_template_when_the_repo_template_is_missing(self):
        self.assertEqual(self.pick("codex", "omnigent", COMMIT, [JUDGE_TAG]), JUDGE_TAG)

    def test_a_codex_judge_with_no_template_built_gets_none(self):
        self.assertIsNone(self.pick("codex", None, None, []))

    def test_a_claude_judge_needs_no_template(self):
        self.assertIsNone(self.pick("claude", None, None, [JUDGE_TAG]))


class CodexJudgeTests(unittest.TestCase):
    def judge(self, fake, available):
        with (mock.patch.object(sandbox, "sbx", fake), mock.patch.object(sandbox, "templates", return_value=dict.fromkeys(available, {}))):
            return sandbox.run_judge("codex", "gpt-6-sol", "Judge this review.", {"type": "object"})

    def test_a_codex_judge_without_a_template_is_refused_before_a_sandbox_starts(self):
        fake = FakeSbx(tree=None)

        with self.assertRaises(sandbox.SandboxError) as caught:
            self.judge(fake, [])

        self.assertEqual(str(caught.exception), "a Codex judge needs the pinned Codex CLI; build its template with "
                                                "`python3 evals/canon/sandbox.py deps --agent codex`")
        self.assertEqual(fake.calls, [])

    def test_a_codex_judge_with_no_repo_starts_from_the_cli_template(self):
        fake = FakeSbx(tree=None)

        record = self.judge(fake, [sandbox.deps_tag("codex")])

        create = next(call for call in fake.calls if call[0] == "create")
        self.assertEqual(record["template"], sandbox.deps_tag("codex"))
        self.assertEqual(create[create.index("-t") + 1], sandbox.deps_tag("codex"))
        self.assertEqual([call[call.index("timeout") + 3] for call in fake.agent_runs()], ["codex"])


class BuildJudgeTemplateTests(unittest.TestCase):
    def test_the_cli_only_build_installs_the_cli_and_saves_a_template_with_no_repo_steps(self):
        fake = FakeSbx(tree=None)

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(sandbox, "sbx", fake), \
                mock.patch.object(sandbox, "records_dir", return_value=Path(directory)):
            record = sandbox.build_deps("codex")
            written = json.loads(next(Path(directory).iterdir()).read_text())

        tag = sandbox.deps_tag("codex")
        subcommands = [call[0] for call in fake.calls]
        save = next(call for call in fake.calls if call[:2] == ["template", "save"])
        self.assertEqual(save[3], tag)
        delete = [index for index, call in enumerate(fake.calls) if call[0] == "exec" and call[-3:] == ["sh", "-c", f"rm -f {sandbox.CREDENTIAL_FILES}"]]
        self.assertEqual(len(delete), 1)
        self.assertLess(delete[0], fake.calls.index(save))
        self.assertIn("create", subcommands)
        self.assertIn("stop", subcommands)
        self.assertTrue(any(call[0] == "exec" and call[-4:] == ["npm", "install", "-g", "@openai/codex@0.160.0"] for call in fake.calls))
        self.assertNotIn("cp", subcommands)
        self.assertFalse(any("uv" in call or "src.tar" in " ".join(call) for call in fake.calls))
        self.assertEqual({key: written[key] for key in ("agent", "tag", "cli")}, {"agent": "codex", "tag": tag, "cli": "@openai/codex@0.160.0"})
        self.assertFalse({"repo", "uv", "sync"} & written.keys())
        self.assertEqual(record["versions"], ["codex-cli 0.160.0"])
        self.assertEqual(fake.calls[-1][:2], ["rm", "--force"])

    def test_an_agent_with_no_cli_pin_has_nothing_to_build(self):
        fake = FakeSbx(tree=None)

        with mock.patch.object(sandbox, "sbx", fake), self.assertRaisesRegex(sandbox.SandboxError, "claude"):
            sandbox.build_deps("claude")
        self.assertEqual(fake.calls, [])


class DepsCommandTests(unittest.TestCase):
    def test_a_repo_without_a_commit_is_refused(self):
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as caught:
            sandbox.main(["deps", "--agent", "codex", "--repo", "omnigent"])

        self.assertEqual(caught.exception.code, 2)
        self.assertIn("--repo and --commit together", err.getvalue())


def sandboxes_available():
    return (os.environ.get("CANON_SBX_E2E") == "1" and shutil.which("sbx") is not None
            and test_workspace.harness_available())


class StandInEntryEvidenceTests(unittest.TestCase):
    """offline/sbx-agent writes the entry's invocation evidence only under the poteto-mode entry."""

    def run_stand_in(self, agent, entry):
        token = {"claude": "/poteto-mode ", "codex": "$poteto-mode "}[agent]
        with tempfile.TemporaryDirectory() as scratch:
            scratch = Path(scratch)
            cwd, home = scratch / "clone", scratch / "home"
            for path in (cwd / ".git", home):
                path.mkdir(parents=True)
            discovery = {"claude": ".claude", "codex": ".agents"}[agent]
            (cwd / discovery / "skills" / "poteto-mode").mkdir(parents=True)
            (cwd / discovery / "skills" / "poteto-mode" / "SKILL.md").write_text("skill\n")
            persona = {"claude": ".claude/agents/poteto-agent.md", "codex": ".codex/agents/poteto-agent.toml"}[agent]
            (cwd / persona).parent.mkdir(parents=True)
            (cwd / persona).write_text("persona\n")
            if entry:
                (cwd / "skills" / "pstack").mkdir(parents=True)
            plan = scratch / "plan.json"
            plan.write_text(json.dumps({"arm": "current", "answer": "done", "diff": "", "reads": ["skills/poteto-mode/SKILL.md"]}))
            flags = (["--permission-mode", "bypassPermissions", "--allowedTools", "TodoWrite"] if agent == "claude"
                     else ["--sandbox", "danger-full-access", "--output-last-message", str(scratch / "last.txt")])
            prompt = (token if entry else "") + "Fix the amend function in the orders module."
            done = subprocess.run([sys.executable, str(ROOT / "offline" / "sbx-agent"), str(plan), agent, *flags],
                                  input=prompt, text=True, capture_output=True, cwd=cwd, env={**os.environ, "HOME": str(home)})
            self.assertEqual(done.returncode, 0, done.stderr)
            if agent == "claude":
                return screen.claude_expanded([path.read_text() for path in home.glob(".claude/projects/*/*.jsonl")]), [
                    path.read_text() for path in home.glob(".claude/projects/*/*.jsonl")]
            return any(screen.codex_injected(path) for path in home.glob(".codex/sessions/**/rollout-*.jsonl")), []

    def test_claude_transcript_carries_the_invocation_only_under_the_entry(self):
        without, texts = self.run_stand_in("claude", entry=False)
        self.assertFalse(without)
        self.assertFalse(any("Base directory for this skill" in text for text in texts), texts)
        with_entry, texts = self.run_stand_in("claude", entry=True)
        self.assertTrue(with_entry)
        self.assertTrue(any("Base directory for this skill" in text for text in texts))

    def test_codex_rollout_carries_the_skill_message_only_under_the_entry(self):
        self.assertFalse(self.run_stand_in("codex", entry=False)[0])
        self.assertTrue(self.run_stand_in("codex", entry=True)[0])


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
