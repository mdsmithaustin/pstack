"""Check the guide's install and discovery promises without paid model output."""

import argparse
import fcntl
import json
import os
import re
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
import traceback
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE_REPO = "mdsmithaustin/pstack"
HARNESSES = ("claude-code", "codex", "grok", "hermes")
INSTALLER_AGENT = {"claude-code": "claude-code", "codex": "codex", "grok": "grok", "hermes": "hermes-agent"}
CODEX_APP = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
HERMES_GATEWAY = "hermes-default-gateway"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
PERSONAS = ("poteto-agent", "comment-sicko")
EFFORT_AGENTS = tuple(f"pstack-effort-{level}" for level in ("low", "medium", "high", "xhigh", "max"))
HERMES_SCAN = """
import json, sys
sys.path.insert(0, "/opt/hermes")
from agent.skill_commands import scan_skill_commands
from agent.skill_utils import get_untrusted_project_skills_root
commands = scan_skill_commands()
untrusted = get_untrusted_project_skills_root()
print(json.dumps({
    "commands": sorted(key.lstrip("/") for key in commands),
    "dirs": sorted({value["skill_dir"].rsplit("/", 1)[0] for value in commands.values()}),
    "untrusted_root": str(untrusted[0]) if untrusted else None,
    "untrusted_skills": untrusted[1] if untrusted else 0,
}))
"""


class Inconclusive(Exception):
    pass


@dataclass(frozen=True)
class Listing:
    discovered: frozenset
    invocable: frozenset
    agents: frozenset
    via: str
    detail: dict = field(default_factory=dict)


@dataclass
class Outcome:
    evidence: dict = field(default_factory=dict)
    failures: list = field(default_factory=list)

    def expect(self, ok, message):
        if not ok:
            self.failures.append(message)


@dataclass(frozen=True)
class Run:
    code: int
    out: str
    err: str
    timed_out: bool = False

    @property
    def text(self):
        return ANSI.sub("", self.out + self.err)


def text_of(stream):
    return stream.decode("utf-8", "replace") if isinstance(stream, bytes) else (stream or "")


def run(argv, env, cwd, timeout=240):
    try:
        done = subprocess.run([str(a) for a in argv], env=env, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL)
        return Run(done.returncode, done.stdout, done.stderr)
    except subprocess.TimeoutExpired as err:
        return Run(-1, text_of(err.stdout), text_of(err.stderr), True)


def frontmatter_name(skill_md):
    match = re.search(r"^name:\s*(\S+)", skill_md.read_text(encoding="utf-8"), re.M)
    return match.group(1).strip("\"'") if match else skill_md.parent.name


def frontmatter_flag(skill_md, key):
    head = skill_md.read_text(encoding="utf-8").split("\n---", 2)[0]
    return re.search(rf"^{key}:\s*true\s*$", head, re.M) is not None


class Box:
    def __init__(self, ctx, label):
        self.ctx = ctx
        self.root = (ctx.work / label).resolve()
        self.home = self.root / "home"
        self.project = self.root / "project"
        for d in (self.home, self.project, self.root / "tmp"):
            d.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(self.project), "init", "-q"], check=True)
        self.env = {
            "PATH": os.environ["PATH"], "HOME": str(self.home), "TMPDIR": str(self.root / "tmp"),
            "LANG": "en_US.UTF-8", "TERM": "xterm", "npm_config_cache": str(ctx.npm_cache),
            "DO_NOT_TRACK": "1", "DISABLE_TELEMETRY": "1",
        }

    def skills(self, *args, timeout=300):
        return run(["npx", "-y", "skills", *args], self.env, self.project, timeout)

    def add(self, *args, source=None):
        return self.skills("add", source or str(self.ctx.snapshot), "-s", "*", "-y", *args)

    def project_skill_dirs(self):
        return {d.name: sorted(p.name for p in (self.project / d.name / "skills").iterdir())
                for d in self.project.iterdir() if d.name.startswith(".") and (d / "skills").is_dir()}


class Context:
    def __init__(self, out):
        self.out = out.resolve()
        self.work = self.out / "work"
        self.npm_cache = self.out / "npm-cache"
        self.snapshot = self.work / "source"
        self.boxes = {}
        self.listings = {}
        self.tools = {}
        shutil.rmtree(self.work, ignore_errors=True)
        self.work.mkdir(parents=True)
        self.npm_cache.mkdir(parents=True, exist_ok=True)
        self.snapshot_source()
        self.skills_version = self.skills_cli_version()
        self.skill_names = sorted(frontmatter_name(p) for p in (self.snapshot / "skills").glob("*/SKILL.md"))
        self.hidden = sorted(frontmatter_name(p) for p in (self.snapshot / "skills").glob("*/SKILL.md")
                             if frontmatter_flag(p, "disable-model-invocation"))
        self.path_scoped = sorted(frontmatter_name(p) for p in (self.snapshot / "skills").glob("*/SKILL.md")
                                  if re.search(r"^paths:", p.read_text(encoding="utf-8").split("\n---", 2)[0], re.M))
        self.guide_names = self.read_guide_names()

    def snapshot_source(self):
        files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "-co", "--exclude-standard", "--", "skills"],
                               check=True, capture_output=True).stdout.split(b"\0")
        shutil.rmtree(self.snapshot, ignore_errors=True)
        for rel in filter(None, (f.decode() for f in files)):
            src = ROOT / rel
            if src.is_file():
                dest = self.snapshot / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        self.head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                                   capture_output=True, text=True).stdout.strip()
        self.dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "skills"],
                                         capture_output=True, text=True).stdout.strip())

    def read_guide_names(self):
        named = {}
        for page in sorted((ROOT / "docs/guide").glob("*.md")):
            for name in re.findall(r"(?<![\w/.\-\]\(])/([a-z][a-z0-9\-]+)\b", page.read_text(encoding="utf-8")):
                named.setdefault(name, set()).add(page.name)
        return {n: sorted(p) for n, p in named.items()}

    def box(self, label):
        if label not in self.boxes:
            self.boxes[label] = Box(self, label)
        return self.boxes[label]

    def tool(self, name, finder):
        if name not in self.tools:
            self.tools[name] = finder()
        return self.tools[name]

    def skills_cli_version(self):
        done = run(["npx", "-y", "skills", "--version"], {**os.environ, "npm_config_cache": str(self.npm_cache)}, self.work)
        return done.out.strip() or f"unknown ({done.err.strip()[:80]})"

    def base(self, harness):
        key = f"base-{harness}"
        if key not in self.boxes:
            box = self.box(key)
            if harness == "hermes":
                (box.home / ".hermes").mkdir(exist_ok=True)
            result = box.add("-a", INSTALLER_AGENT[harness])
            if result.code != 0:
                raise Inconclusive(f"npx skills add exited {result.code}: {result.text.strip()[-300:]}")
            box.install = result
            if harness == "hermes":
                trust = hermes(self, box, ["skills", "trust"])
                box.trust = trust.text.strip()
        return self.boxes[key]

    def listing(self, harness):
        if harness not in self.listings:
            self.listings[harness] = LISTERS[harness](self, self.base(harness))
        return self.listings[harness]


def claude_list(ctx, box, model="not-a-real-model-xyz"):
    claude = shutil.which("claude")
    if not claude:
        raise Inconclusive("claude is not on PATH")
    done = run([claude, "-p", "--model", model, "--output-format", "stream-json", "--verbose",
                "--no-session-persistence", "hi"], box.env, box.project, timeout=120)
    for line in done.out.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            commands = frozenset(event.get("slash_commands", []))
            return Listing(frozenset(event.get("skills", [])), commands, frozenset(event.get("agents", [])),
                           "claude -p init event, unknown model, no billing",
                           {"version": event.get("claude_code_version"), "apiKeySource": event.get("apiKeySource")})
    raise Inconclusive(f"claude -p emitted no init event (exit {done.code}): {done.text.strip()[-200:]}")


def find_codex():
    for candidate in (os.environ.get("CODEX_BIN"), CODEX_APP, shutil.which("codex")):
        if candidate and Path(candidate).exists() and run([candidate, "--version"], os.environ, None, 30).code == 0:
            return candidate
    raise Inconclusive("no working codex binary: set CODEX_BIN, install the ChatGPT app, or fix the mise shim")


class StubProvider:
    def __init__(self):
        self.bodies = []
        bodies = self.bodies

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                bodies.append(self.rfile.read(int(self.headers.get("content-length", 0))))
                self.send_response(400)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":{"message":"stub","type":"invalid_request_error"}}')

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def codex_request(ctx, box, prompt, trust):
    codex = ctx.tool("codex", find_codex)
    home = box.root / "codex-home"
    home.mkdir(exist_ok=True)
    stub = StubProvider()
    try:
        argv = [codex, "exec", "-m", "stub-model", "--json", "-c", 'model_provider="stub"',
                "-c", f'model_providers.stub={{name="stub",base_url="{stub.url}",env_key="STUB_KEY",wire_api="responses"}}']
        if trust:
            argv += ["-c", f'projects={{"{box.project.resolve()}"={{trust_level="{trust}"}}}}']
        done = run([*argv, prompt], {**box.env, "CODEX_HOME": str(home), "STUB_KEY": "x"}, box.project, timeout=90)
    finally:
        stub.close()
    if not stub.bodies:
        raise Inconclusive(f"codex exec never reached the stub provider (exit {done.code}): {done.text.strip()[-200:]}")
    return json.loads(stub.bodies[0])


def codex_digest(request):
    injected, implicit, roles = [], [], []
    for item in request.get("input", []):
        for part in item.get("content", []) if isinstance(item.get("content"), list) else []:
            text = part.get("text", "")
            found = re.match(r"<skill>\n<name>([^<]+)</name>", text)
            if found:
                injected.append(found.group(1))
            elif "<skills_instructions>" in text:
                implicit += re.findall(r"^- ([\w.\-]+): .*\(file: ", text, re.M)
    for tool in request.get("tools", []):
        if tool.get("name") == "multi_agent_v1":
            roles += re.findall(r"\n([\w.\-]+): \{\n", json.dumps(tool).replace("\\n", "\n"))
    return frozenset(injected), frozenset(implicit), frozenset(roles)


def codex_list(ctx, box, trust="trusted"):
    names = " ".join(f"${n}" for n in ctx.skill_names)
    injected, implicit, roles = codex_digest(codex_request(ctx, box, f"{names} do nothing", trust))
    return Listing(injected | implicit, injected, roles,
                   "codex exec against a stub provider; every $name mentioned, request captured, no model call",
                   {"implicit_in_model_list": len(implicit), "injected_on_mention": len(injected)})


def grok_list(ctx, box):
    grok = shutil.which("grok")
    if not grok:
        raise Inconclusive("grok is not on PATH")
    home = box.root / "grok-home"
    home.mkdir(exist_ok=True)
    done = run([grok, "inspect", "--json"], {**box.env, "GROK_HOME": str(home), "GROK_FOLDER_TRUST": "0"}, box.project, 90)
    try:
        report = json.loads(done.out)
    except ValueError:
        raise Inconclusive(f"grok inspect --json gave no JSON (exit {done.code}): {done.text.strip()[-200:]}")
    skills = report.get("skills", [])
    return Listing(frozenset(s["name"] for s in skills),
                   frozenset(s["name"] for s in skills if s.get("userInvocable")),
                   frozenset(a["name"] for a in report.get("agents", [])), "grok inspect --json",
                   {"version": report.get("grokVersion"), "projectTrusted": report.get("projectTrusted")})


def hermes_image(ctx):
    pinned = os.environ.get("HERMES_IMAGE")
    if pinned:
        return pinned
    done = run(["docker", "inspect", HERMES_GATEWAY, "--format", "{{.Config.Image}}"], os.environ, None, 30)
    if done.code != 0 or not done.out.strip():
        raise Inconclusive(f"no Hermes image: set HERMES_IMAGE or run the {HERMES_GATEWAY} container ({done.err.strip()[:120]})")
    return done.out.strip()


def hermes(ctx, box, args, entry="/opt/hermes/.venv/bin/hermes", hermes_home=None):
    image = ctx.tool("hermes_image", lambda: hermes_image(ctx))
    state = Path(hermes_home) if hermes_home else box.home / ".hermes"
    state.mkdir(parents=True, exist_ok=True)
    (state / ".no-bundled-skills").touch()
    root = str(box.root)
    argv = ["docker", "run", "--rm", "-i", "--init", "--user", f"{os.getuid()}:{os.getgid()}", "--entrypoint", entry,
            "-v", f"{root}:{root}", "-e", f"HOME={box.home}", "-e", f"HERMES_HOME={state}",
            "-e", f"TERMINAL_CWD={box.project}", "-w", str(box.project), image, *args]
    done = run(argv, os.environ, None, 180)
    if done.code == 125:
        raise Inconclusive(f"docker run failed: {done.err.strip()[-200:]}")
    return done


def hermes_scan(ctx, box, hermes_home=None):
    script = box.root / "scan.py"
    script.write_text(HERMES_SCAN)
    done = hermes(ctx, box, [str(script)], entry="/opt/hermes/.venv/bin/python", hermes_home=hermes_home)
    for line in reversed(done.out.splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    raise Inconclusive(f"hermes scan printed no JSON (exit {done.code}): {done.text.strip()[-200:]}")


def hermes_list(ctx, box):
    scan = hermes_scan(ctx, box)
    names = frozenset(scan["commands"])
    return Listing(names, names, frozenset(), "Hermes scan_skill_commands() in the pinned image, project trusted with `hermes skills trust`",
                   {"dirs": [Path(d).relative_to(box.root).as_posix() for d in scan["dirs"]], "untrusted_skills": scan["untrusted_skills"]})


LISTERS = {"claude-code": claude_list, "codex": codex_list, "grok": grok_list, "hermes": hermes_list}
ENTRY_SYNTAX = {"claude-code": "/<name>", "codex": "$<name>", "grok": "/<name>", "hermes": "/<name>"}


def check_installer_delivers_skills(ctx, harness):
    box, listing = ctx.base(harness), ctx.listing(harness)
    expected = set(ctx.skill_names)
    deferred = sorted(set(ctx.path_scoped) - listing.discovered)
    missing = sorted(expected - listing.discovered - set(deferred))
    outcome = Outcome({"source": f"snapshot of {ctx.head} skills/ ({'with uncommitted edits' if ctx.dirty else 'clean'})",
                       "installer_exit": box.install.code, "expected": len(expected),
                       "discovered": len(expected & listing.discovered), "via": listing.via,
                       "path_scoped_unlisted_until_a_matching_file_is_used": deferred,
                       "project_dirs": {k: len(v) for k, v in box.project_skill_dirs().items()}, **listing.detail})
    outcome.expect(not missing, f"{harness} did not discover {len(missing)} installed skills: {', '.join(missing[:12])}")
    return outcome


def check_slash_skills_invocable(ctx, harness):
    listing = ctx.listing(harness)
    named = sorted(n for n in ctx.guide_names if n in ctx.skill_names)
    missing = sorted(n for n in named if n not in listing.invocable)
    outcome = Outcome({"entry_syntax": ENTRY_SYNTAX[harness], "guide_named_pstack_skills": len(named), "invocable": len(named) - len(missing),
                       "gated_with_disable_model_invocation": len(ctx.hidden), "via": listing.via,
                       "not_pstack_skills_named_in_guide": sorted(n for n in ctx.guide_names if n not in ctx.skill_names)})
    outcome.expect(not missing, f"{harness} offers no user-invocable entry for: {', '.join(missing)}")
    return outcome


def check_setup_pstack_invocable(ctx, harness):
    listing = ctx.listing(harness)
    outcome = Outcome({"entry": ENTRY_SYNTAX[harness].replace("<name>", "setup-pstack"), "via": listing.via,
                       "scope": "entry resolves to the skill; what the skill does once running needs a model run"})
    outcome.expect("setup-pstack" in listing.invocable, f"{harness} lists no invocable entry named setup-pstack")
    return outcome


def check_deslop_available_for_code(ctx, harness):
    listing = ctx.listing(harness)
    named_in = ctx.guide_names.get("deslop", [])
    mentions = subprocess.run(["grep", "-rIl", "deslop", str(ctx.snapshot / "skills")], capture_output=True, text=True).stdout.split()
    outcome = Outcome({"guide_pages_naming_deslop": named_in, "skills_files_mentioning_deslop": [Path(m).relative_to(ctx.snapshot).as_posix() for m in mentions],
                       "closest_listed": sorted(n for n in listing.invocable if n in ("unslop", "no-comments")), "via": listing.via})
    outcome.expect("deslop" in listing.discovered or "deslop" in listing.invocable,
                   f"{harness} lists no deslop skill after install, so /deslop in the guide resolves to nothing")
    return outcome


def pty_session(argv, env, cwd, steps, size=(60, 120)):
    import pty
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.execvpe(argv[0], argv, {**env, "COLUMNS": str(size[1]), "LINES": str(size[0])})
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", size[0], size[1], 0, 0))
    seen = []
    try:
        for keys, wait, until in steps:
            if keys:
                os.write(fd, keys)
            chunk, end = b"", time.monotonic() + wait
            while time.monotonic() < end and not (until and until in ANSI.sub("", chunk.decode("utf-8", "replace"))):
                ready, _, _ = select.select([fd], [], [], 0.3)
                if ready:
                    try:
                        data = os.read(fd, 65536)
                    except OSError:
                        break
                    if not data:
                        break
                    chunk += data
            seen.append(ANSI.sub("", chunk.decode("utf-8", "replace")))
    finally:
        os.killpg(pid, 9)
        os.close(fd)
        os.waitpid(pid, 0)
    return seen


def check_installer_offers_hermes_target(ctx, harness):
    box = ctx.box("prompt")
    bogus = box.add("-a", "not-an-agent")
    valid = re.search(r"Valid agents: (.*)", bogus.text)
    targets = [t.strip() for t in valid.group(1).split(",")] if valid else []
    shown = pty_session(["npx", "-y", "skills", "add", str(ctx.snapshot)], box.env, box.project,
                        [(None, 60, "Select All"), (b" ", 1, None), (b"\r", 15, "Which agents do you want to install to?"),
                         (b"hermes", 4, "Search: hermes")])
    typed = shown[-1]
    outcome = Outcome({"valid_agent_ids": len(targets), "hermes_agent_in_valid_ids": "hermes-agent" in targets,
                       "prompt_after_typing_hermes": [ln.strip(" │") for ln in typed.splitlines() if "Hermes" in ln][-1:],
                       "prompt_title": "Which agents do you want to install to?" if "Which agents do you want to install to?" in typed else None})
    if "Which agents do you want to install to?" not in typed:
        raise Inconclusive(f"the agent prompt never rendered in the pty; last screen: {typed.strip()[-200:]!r}")
    outcome.expect("hermes-agent" in targets, "`npx skills add -a <bad>` lists no hermes-agent among valid agents")
    outcome.expect("Hermes Agent" in typed, "the interactive agent prompt shows no 'Hermes Agent' row when searching 'hermes'")
    return outcome


def check_hermes_install_trust_and_link(ctx, harness):
    outcome = Outcome()
    skip = ctx.box("hermes-link-absent")
    (skip.home / ".hermes").mkdir(exist_ok=True)
    first = skip.add()
    project_dirs = skip.project_skill_dirs()
    outcome.evidence.update({"detected_hermes_home_no_project_dot_hermes": {
        "installer_exit": first.code, "project_dot_hermes_exists": (skip.project / ".hermes").exists(),
        "canonical_skills": len(project_dirs.get(".agents", [])),
        "installer_says": [m.strip(" │") for m in re.findall(r"skipped: .*", first.text)[:1]]}})
    outcome.expect(first.code == 0, f"installer exited {first.code} with Hermes detected")
    outcome.expect(not (skip.project / ".hermes").exists(), "installer created .hermes/ in a project that had none (it should skip the link)")
    outcome.expect(any("Hermes Agent" in line and "project directory not found" in line for line in first.text.splitlines()),
                   "installer did not report skipping Hermes for a missing project directory")

    link = ctx.box("hermes-link-present")
    (link.home / ".hermes").mkdir(exist_ok=True)
    (link.project / ".hermes").mkdir()
    link.add()
    linked = link.project_skill_dirs().get(".hermes", [])
    outcome.evidence["detected_hermes_home_with_project_dot_hermes"] = {"linked_skills": len(linked)}
    outcome.expect(len(linked) == len(ctx.skill_names), f"with .hermes present the installer linked {len(linked)} of {len(ctx.skill_names)} skills")

    chosen = ctx.box("hermes-link-chosen")
    chosen.add("-a", "hermes-agent")
    outcome.evidence["hermes_agent_chosen_explicitly_no_project_dot_hermes"] = {
        "project_dot_hermes_created": (chosen.project / ".hermes").exists(),
        "linked_skills": len(chosen.project_skill_dirs().get(".hermes", [])),
        "caveat": "the skip applies only to an auto-detected Hermes; choosing hermes-agent (flag or prompt) creates the link"}

    before = hermes_scan(ctx, skip)
    trust = hermes(ctx, skip, ["skills", "trust"])
    after = hermes_scan(ctx, skip)
    outcome.evidence["hermes_project_skills"] = {
        "untrusted_discovered": len(set(before["commands"]) & set(ctx.skill_names)), "untrusted_reported_hidden": before["untrusted_skills"],
        "after_hermes_skills_trust_discovered": len(set(after["commands"]) & set(ctx.skill_names)), "trust_says": "Trusted" if "Trusted:" in trust.text else trust.text.strip()[:140]}
    outcome.expect(not set(before["commands"]) & set(ctx.skill_names), "Hermes loaded project skills before the project was trusted")
    outcome.expect(set(ctx.skill_names) <= set(after["commands"]), "Hermes did not load every project skill after `hermes skills trust`")
    return outcome


def check_hermes_global_discovery(ctx, harness):
    outcome = Outcome()
    expected = set(ctx.skill_names)
    native = ctx.box("hermes-global-native")
    (native.home / ".hermes").mkdir(exist_ok=True)
    added = native.add("-g", "-a", "hermes-agent")
    found = set(hermes_scan(ctx, native)["commands"]) & expected
    outcome.evidence["native_dir"] = {"installer_exit": added.code, "installed_to": "~/.hermes/skills",
                                      "files": len(list((native.home / ".hermes/skills").glob("*/SKILL.md"))), "discovered": len(found)}
    outcome.expect(added.code == 0 and found == expected, f"native global install: Hermes discovered {len(found)} of {len(expected)}")

    shared = ctx.box("hermes-global-shared")
    added = shared.add("-g", "-a", "codex")
    state = shared.home / ".hermes"
    bare = set(hermes_scan(ctx, shared, state)["commands"]) & expected
    (state / "config.yaml").write_text("skills:\n  external_dirs:\n    - ~/.agents/skills\n")
    configured = set(hermes_scan(ctx, shared, state)["commands"]) & expected
    outcome.evidence["shared_dir"] = {"installer_exit": added.code, "installed_to": "~/.agents/skills",
                                      "files": len(list((shared.home / ".agents/skills").glob("*/SKILL.md"))),
                                      "discovered_without_external_dirs": len(bare), "discovered_with_external_dirs": len(configured)}
    outcome.expect(added.code == 0 and configured == expected, f"~/.agents/skills with skills.external_dirs: Hermes discovered {len(configured)} of {len(expected)}")
    return outcome


def register_agents(box, harness):
    script = box.project / ".agents/skills/pstack-harness/scripts/subagents.py"
    if not script.exists():
        script = box.project / ".claude/skills/pstack-harness/scripts/subagents.py"
    done = run([sys.executable, script, "install", "--harness", harness, "--project", box.project], box.env, box.project, 60)
    if done.code != 0:
        raise Inconclusive(f"subagents.py install --harness {harness} exited {done.code}: {done.text.strip()[-200:]}")
    return json.loads(done.out)


def registered_box(ctx, harness):
    key = f"registered-{harness}"
    if key not in ctx.boxes:
        box = ctx.box(key)
        added = box.add("-a", INSTALLER_AGENT[harness])
        if added.code != 0:
            raise Inconclusive(f"npx skills add exited {added.code}: {added.text.strip()[-300:]}")
        box.registration = register_agents(box, harness)
    return ctx.boxes[key]


def check_native_agents_appear_in_catalog_after_restart(ctx, harness):
    before = ctx.listing(harness)
    box = registered_box(ctx, harness)
    after = LISTERS[harness](ctx, box)
    wanted = set(PERSONAS) | (set(EFFORT_AGENTS) if harness == "claude-code" else set())
    outcome = Outcome({"before_registration": sorted(wanted & before.agents), "install_report_agents_directory": box.registration.get("agents_directory"),
                       "after_registration_fresh_process": sorted(wanted & after.agents), "via": after.via,
                       "not_exercised": "a restart of a long-lived interactive session; each listing here is a fresh process"})
    outcome.expect(not wanted & before.agents, f"{harness} already listed pstack agents before registration: {sorted(wanted & before.agents)}")
    outcome.expect(wanted <= after.agents, f"a fresh {harness} process did not list: {', '.join(sorted(wanted - after.agents))}")
    return outcome


def check_codex_project_agents_need_trust(ctx, harness):
    box = registered_box(ctx, harness)
    states = {}
    for label, trust in (("trusted", "trusted"), ("untrusted", "untrusted"), ("no_entry", None)):
        states[label] = sorted(set(PERSONAS) & codex_digest(codex_request(ctx, box, "hi", trust))[2])
    outcome = Outcome({"personas_in_catalog": states, "via": "codex exec against a stub provider; spawn tool's role list read from the captured request",
                       "codex_version": run([ctx.tool("codex", find_codex), "--version"], os.environ, None, 30).out.strip()})
    outcome.expect(set(states["trusted"]) == set(PERSONAS), f"trusted project catalog lists {states['trusted']}, not both personas")
    outcome.expect(not states["untrusted"], f"an explicitly untrusted project still lists {states['untrusted']}")
    return outcome


def digest_dir(path):
    return {p.name: [p.stat().st_mtime_ns, p.stat().st_size] for p in sorted(path.glob("*")) if p.is_file()}


def check_skills_update_does_not_refresh_agents(ctx, harness):
    key = "update-published"
    first = key not in ctx.boxes
    box = ctx.box(key)
    if first:
        added = box.add("-a", "claude-code", "-a", "codex", source=SOURCE_REPO)
        box.published = added
        if added.code != 0:
            raise Inconclusive(f"installing the published {SOURCE_REPO} failed (network?): {added.text.strip()[-200:]}")
        for each in ("claude-code", "codex"):
            try:
                box.registered = {**getattr(box, "registered", {}), each: register_agents(box, each)}
            except Inconclusive as err:
                box.registered = {**getattr(box, "registered", {}), each: str(err)}
        marker = box.project / ".agents/skills/why/SKILL.md"
        marker.write_text(marker.read_text(encoding="utf-8") + "\n<!-- tampered -->\n", encoding="utf-8")
        box.before = {h: digest_dir(box.project / d / "agents") for h, d in (("claude-code", ".claude"), ("codex", ".codex"))}
        time.sleep(1.1)
        box.update = box.skills("update", "why", "-p", "-y")
        box.refreshed = "<!-- tampered -->" not in marker.read_text(encoding="utf-8")
        box.after = {h: digest_dir(box.project / d / "agents") for h, d in (("claude-code", ".claude"), ("codex", ".codex"))}
    if isinstance(box.registered[harness], str):
        raise Inconclusive(f"the published install cannot register {harness} agents: {box.registered[harness]}")
    outcome = Outcome({"source": f"{SOURCE_REPO} (published; the CLI cannot update a local-path source)", "skills_cli": ctx.skills_version,
                       "update_exit": box.update.code, "skill_refreshed_by_update": box.refreshed,
                       "agent_files": sorted(box.before[harness]), "agent_files_unchanged": box.before[harness] == box.after[harness]})
    if box.update.code != 0 or not box.refreshed:
        raise Inconclusive(f"`skills update` did not refresh the tampered skill (exit {box.update.code}): {box.update.text.strip()[-200:]}")
    outcome.expect(bool(box.before[harness]), f"no registered {harness} agent files existed to compare")
    outcome.expect(box.before[harness] == box.after[harness], f"`skills update` changed registered {harness} agent files")
    return outcome


@dataclass(frozen=True)
class Check:
    promise: str
    harnesses: tuple
    fn: object


CHECKS = (
    Check("installer-delivers-skills", HARNESSES, check_installer_delivers_skills),
    Check("installer-offers-hermes-target", ("hermes",), check_installer_offers_hermes_target),
    Check("hermes-install-trust-and-link", ("hermes",), check_hermes_install_trust_and_link),
    Check("hermes-global-discovery", ("hermes",), check_hermes_global_discovery),
    Check("codex-project-agents-need-trust", ("codex",), check_codex_project_agents_need_trust),
    Check("native-agents-appear-in-catalog-after-restart", ("claude-code", "codex"), check_native_agents_appear_in_catalog_after_restart),
    Check("skills-update-does-not-refresh-agents", ("claude-code", "codex"), check_skills_update_does_not_refresh_agents),
    Check("setup-pstack-invocable", HARNESSES, check_setup_pstack_invocable),
    Check("slash-skills-invocable", HARNESSES, check_slash_skills_invocable),
    Check("deslop-available-for-code", HARNESSES, check_deslop_available_for_code),
)


def evaluate(ctx, check, harness):
    try:
        outcome = check.fn(ctx, harness)
        verdict = "FAIL" if outcome.failures else "PASS"
        evidence, failures = outcome.evidence, outcome.failures
    except Inconclusive as reason:
        verdict, evidence, failures = "INCONCLUSIVE", {"reason": str(reason)}, []
    except Exception as err:
        verdict, failures = "INCONCLUSIVE", []
        evidence = {"reason": f"check error: {type(err).__name__}: {err}", "trace": traceback.format_exc().splitlines()[-4:]}
    evidence = {"skills_cli": ctx.skills_version, **evidence}
    return {"promise": check.promise, "harness": harness, "verdict": verdict, "evidence": evidence, "failures": failures}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--harness", action="append", choices=HARNESSES, help="repeatable; default all four")
    parser.add_argument("--out", default=None, help="directory for install.json (default: a new temp directory)")
    parser.add_argument("--keep", action="store_true", help="keep the temp HOME/project sandboxes under DIR/work")
    args = parser.parse_args(argv)
    selected = tuple(args.harness or HARNESSES)
    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="pstack-install-"))
    out.mkdir(parents=True, exist_ok=True)
    ctx = Context(out)
    results = []
    try:
        for check in CHECKS:
            for harness in (h for h in check.harnesses if h in selected):
                result = evaluate(ctx, check, harness)
                results.append(result)
                print(json.dumps(result, sort_keys=True), flush=True)
    finally:
        (out / "install.json").write_text(json.dumps(results, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        if not args.keep:
            shutil.rmtree(ctx.work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
