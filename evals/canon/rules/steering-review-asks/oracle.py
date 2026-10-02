"""Each case replays a merged pull request from the commit its branch started
at, or for omnigent-close-code from the main commit the branch merged before
its review fix. A run passes when the PR's own tests pass on its diff (functional) and
when it meets what the maintainer asked for in review (constraint:<id>).
Scope against the merged diff is reported, never failed: the check writes
scope.json beside the harvested workspace.diff."""
import json
import re
from pathlib import PurePosixPath

from shared import apply_diff, project_test_results


def appended(checkout, sources):
    """{path: bytes} of each grader-owned test source, appended to the
    checkout's copy of that file, never the agent's, or alone when the
    checkout has none. pytest keeps the last definition of a name, so an
    appended test also replaces an older one of the same name."""
    files = {}
    for path, source in sources.items():
        original = checkout / path
        files[path] = (original.read_bytes() if original.is_file() else b"") + source.encode()
    return files


def result_status(results, node):
    """passed, failed, skipped, or missing for one pytest node id or vitest
    file::name, folding the parameters of a parametrized test into one outcome.
    Any failed parameter fails it and any skipped one beats passed, since an
    agent-side conftest or marker can skip a grader-owned test."""
    path, _, name = node.partition("::")
    if path.endswith(".py"):
        parts = name.split("::")
        key = ".".join([path.removesuffix(".py").replace("/", "."), *parts[:-1]]) + "::" + parts[-1]
    else:
        key = node
    found = [status for label, status in results.items() if label == key or label.startswith(key + "[")]
    if not found:
        return "missing"
    if "failed" in found:
        return "failed"
    return "skipped" if "skipped" in found else "passed"


def added_lines(diff):
    """{path: [each line the diff adds]} for every path a unified diff touches."""
    added, path = {}, None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[1]
            added[path] = []
        elif line.startswith("+") and not line.startswith("+++") and path is not None:
            added[path].append(line[1:])
    return added


def is_test_file(path):
    return path.startswith("tests/") or re.search(r"\.(test|spec)\.[cm]?[jt]sx?$", path) is not None


def report_scope(workspace, footprint):
    added = added_lines(workspace.diff)
    record = {"outside_footprint": sorted(set(added) - set(footprint)),
              "added": sum(map(len, added.values())), "merged_added": sum(footprint.values())}
    if workspace.harvest is not None:
        (workspace.harvest / "scope.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def graded(workspace, image, sources, tests, footprint, statics=()):
    """Failures from running tests, {node: dimension}, in the case's image
    over the agent's diff with the grader-owned sources laid on top, plus the
    static constraint checks over the lines the diff adds."""
    report_scope(workspace, footprint)
    changed = apply_diff(workspace.checkout, workspace.diff)
    files = {**changed, **appended(workspace.checkout, sources)}
    targets = sorted({node if node.split("::")[0].endswith(".py") else node.split("::")[0] for node in tests})
    results = project_test_results(image, workspace.checkout, files, targets)
    failures = [f"{dimension}: {node} {status}" + (" (a skipped grader-owned test never ran)" if status == "skipped" else "")
                for node, dimension in tests.items() if (status := result_status(results, node)) != "passed"]
    added = added_lines(workspace.diff)
    return failures + [failure for static in statics for failure in static(added)]


# omnigent #6005. The PR's streak test pins the private _RECYCLE_PROMPT_MAX_STREAK,
# so the functional set runs a port that accepts any cap up to 20.
CLOSE_CODE_PR_TESTS = r'''

async def test_dns_errno_failure_is_not_a_recycle(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("omnigent.host.connect._RECONNECT_BASE_S", 0.0)
    monkeypatch.setattr("omnigent.host.connect._RECONNECT_CAP_S", 0.0)
    dns_failure = OSError(11001, "getaddrinfo failed")
    spy = _ConnectSpy([dns_failure, dns_failure, dns_failure, asyncio.CancelledError()])
    _patch_connect(monkeypatch, spy)
    host = _host()

    with caplog.at_level(logging.WARNING, logger="omnigent.host.connect"):
        await host.run()

    assert spy.call_count == 4
    reconnects = [
        record.message for record in caplog.records if "Reconnecting in" in record.message
    ]
    assert len(reconnects) == 3
    assert not any("(recycle" in r for r in reconnects), (
        "a DNS resolution failure must take the backoff ladder, not the prompt recycle cadence"
    )


@pytest.mark.parametrize("port", [502, 1001, 1012])
async def test_endpoint_port_is_not_a_recycle(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    port: int,
) -> None:
    """Standalone numbers in transport errors are not protocol status codes."""
    monkeypatch.setattr("omnigent.host.connect._RECONNECT_BASE_S", 0.0)
    failure = OSError(f"Connect call failed ('203.0.113.1', {port})")
    spy = _ConnectSpy([failure, asyncio.CancelledError()])
    _patch_connect(monkeypatch, spy)

    with caplog.at_level(logging.WARNING, logger="omnigent.host.connect"):
        await _host().run()

    reconnects = [
        record.message for record in caplog.records if "Reconnecting in" in record.message
    ]
    assert len(reconnects) == 1
    assert "(recycle" not in reconnects[0]
'''

CLOSE_CODE_CHECKS = r'''import asyncio
import logging

import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from tests.host.test_connect import _ConnectSpy, _host, _invalid_status, _patch_connect


async def reconnects(monkeypatch, caplog, script, url="https://app.example.databricks.com"):
    monkeypatch.setattr("omnigent.host.connect._RECONNECT_BASE_S", 0.0)
    monkeypatch.setattr("omnigent.host.connect._RECONNECT_CAP_S", 0.0)
    monkeypatch.setattr("omnigent.host.connect.configured_harness_map", dict)
    monkeypatch.setattr("omnigent.host.connect.gateway_inference_map", dict)
    _patch_connect(monkeypatch, _ConnectSpy([*script, asyncio.CancelledError()]))
    with caplog.at_level(logging.WARNING, logger="omnigent.host.connect"):
        await _host(url).run()
    return ["(recycle" in record.message for record in caplog.records if "Reconnecting in" in record.message]


async def test_sustained_recycle_failures_fall_back_to_backoff(monkeypatch, caplog):
    prompt = await reconnects(monkeypatch, caplog, [_invalid_status(502)] * 40)
    assert len(prompt) == 40 and prompt[0], prompt
    assert prompt == sorted(prompt, reverse=True) and not any(prompt[20:]), prompt


@pytest.mark.parametrize("failure", [
    RuntimeError("server rejected WebSocket connection: HTTP 502"),
    RuntimeError("received 1012 (service restart)"),
    OSError("peer going away"),
], ids=["http-502-text", "1012-text", "going-away-text"])
async def test_text_that_spells_a_close_code_is_not_a_recycle(monkeypatch, caplog, failure):
    assert await reconnects(monkeypatch, caplog, [failure]) == [False]


@pytest.mark.parametrize("failure", [_invalid_status(502), ConnectionClosedError(Close(1012, "service restart"), None)],
                         ids=["invalid-status-502", "close-frame-1012"])
async def test_structured_recycle_signals_reconnect_promptly(monkeypatch, caplog, failure):
    assert await reconnects(monkeypatch, caplog, [failure]) == [True]


async def test_codeless_drop_after_an_accepted_upgrade_reconnects_promptly(monkeypatch, caplog):
    assert await reconnects(monkeypatch, caplog, [None]) == [True]


async def test_loopback_502_takes_the_backoff(monkeypatch, caplog):
    assert await reconnects(monkeypatch, caplog, [_invalid_status(502)], url="http://127.0.0.1:8080") == [False]
'''


def check_close_code(answer, workspace):
    checks = "tests/host/test_reconnect_classification.py"
    return graded(workspace, "omnigent-336207801509",
                  {"tests/host/test_connect.py": CLOSE_CODE_PR_TESTS, checks: CLOSE_CODE_CHECKS}, {
                      "tests/host/test_connect.py::test_dns_errno_failure_is_not_a_recycle": "functional",
                      f"{checks}::test_sustained_recycle_failures_fall_back_to_backoff": "functional",
                      "tests/host/test_connect.py::test_endpoint_port_is_not_a_recycle": "constraint:C1",
                      f"{checks}::test_text_that_spells_a_close_code_is_not_a_recycle": "constraint:C2",
                      f"{checks}::test_structured_recycle_signals_reconnect_promptly": "constraint:C3",
                      f"{checks}::test_codeless_drop_after_an_accepted_upgrade_reconnects_promptly": "constraint:C3",
                      f"{checks}::test_loopback_502_takes_the_backoff": "constraint:C3",
                  }, {"omnigent/host/connect.py": 30, "tests/host/test_connect.py": 87,
                      "tests/e2e/test_host_dns_failure_reconnect_backoff.py": 175})




# omnigent #2104. The PR's bridge test and its Monitor web test encode the
# review ask, so they are graded as K1 and K2 below, by checks that pin no
# data-dict shape or response id. The functional set is the PR's other two,
# its endpoint test posting a task notification rather than a <skill> block,
# since the request covers only notifications. K1 follows a notification from
# the bridge through the forwarder's POST to the stored item, so it accepts
# is_meta set in the bridge or in the events route.
TASK_NOTIFY_PR_TESTS = r'''

NOTIFICATION = "\n".join([
    "<task-notification>",
    "<task-id>a815d170defd74675</task-id>",
    "<tool-use-id>toolu_bdrk_01Uz3yFPSUrsqovLfRN4uhyt</tool-use-id>",
    "<status>completed</status>",
    '<summary>Agent "Explore spec" finished</summary>',
    "</task-notification>",
])


async def test_external_meta_user_message_persists_without_live_input_event(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        "omnigent.server.routes.sessions.session_stream.publish",
        lambda sid, ev: published.append((sid, ev)),
    )
    agent = await create_test_agent(client)
    session = await _create_session(client, agent["id"])

    resp = await client.post(
        f"/v1/sessions/{session['id']}/events",
        json={
            "type": "external_conversation_item",
            "data": {
                "item_type": "message",
                "item_data": {
                    "role": "user",
                    "content": [{"type": "input_text", "text": NOTIFICATION}],
                    "is_meta": True,
                },
                "response_id": "codex_turn_123",
                "source_id": "codex-skill-meta",
            },
        },
    )
    assert resp.status_code == 202, resp.text

    items = (await client.get(f"/v1/sessions/{session['id']}/items")).json()["data"]
    meta = next(item for item in items if item["type"] == "message")
    assert meta["is_meta"] is True
    assert meta["content"][0]["text"] == NOTIFICATION
    snap = await client.get(f"/v1/sessions/{session['id']}")
    assert snap.status_code == 200
    assert snap.json()["title"] is None
    assert published == []
'''

TASK_NOTIFY_PR_WEB_TESTS = r'''

describe("itemsToBlocks — flat shape", () => {
  it("hides legacy Claude task notifications that predate is_meta", () => {
    const items: ConversationItem[] = [
      userMessage("resp_before", "visible before", "msg_before"),
      userMessage(
        "resp_task",
        [
          "<task-notification>",
          "<task-id>a815d170defd74675</task-id>",
          "<tool-use-id>toolu_bdrk_01Uz3yFPSUrsqovLfRN4uhyt</tool-use-id>",
          "<output-file>/tmp/tasks/a815d170defd74675.output</output-file>",
          "<status>completed</status>",
          '<summary>Agent "Explore spec" finished</summary>',
          "<result>final report</result>",
          "</task-notification>",
        ].join("\n"),
        "msg_legacy_task_notification",
      ),
      userMessage("resp_after", "visible after", "msg_after"),
    ];

    const blocks = itemsToBlocks(items);

    const userBlocks = blocks.filter((b): b is UserMessageBlock => b.type === "user_message");
    const texts = userBlocks.map((b) => b.content.map((c) => ("text" in c ? c.text : "")).join(""));
    expect(texts).toEqual(["visible before", "visible after"]);
  });
});
'''

MONITOR, KILLED = ("<task-notification>\n<task-id>b1mhekpmy</task-id>\n<summary>Monitor event: CI results</summary>\n"
                   "<event>E2E UI Tests (shard 2/3)\tfail\t1m50s</event>\n</task-notification>",
                   "<task-notification>\n<task-id>k2</task-id>\n<status>killed</status>\n</task-notification>")
ASKS_ABOUT_TAG = "<task-notification> shows up in my logs, what does it mean?"

TRANSCRIPT = r'''
def transcript_items(tmp_path, content):
    path = tmp_path / "session.jsonl"
    path.write_text(json.dumps({"type": "user", "uuid": "u1", "message": {"role": "user", "content": content}}) + "\n")
    return read_transcript_items_since(path, 0, agent_name="claude-native-ui")[2]
'''

TASK_NOTIFY_CHECKS = rf'''import json

from omnigent.claude_native_bridge import read_transcript_items_since

ASKS_ABOUT_TAG = {ASKS_ABOUT_TAG!r}
{TRANSCRIPT}

def messages(tmp_path, content):
    return [(item.data.get("is_meta") is True, "".join(block.get("text", "") for block in item.data.get("content", [])))
            for item in transcript_items(tmp_path, content) if item.item_type == "message"]


def test_user_text_that_only_opens_with_the_tag_stays_visible(tmp_path):
    assert messages(tmp_path, ASKS_ABOUT_TAG) == [(False, ASKS_ABOUT_TAG)]
'''

TASK_NOTIFY_STORED_CHECKS = rf'''import json

import pytest

from omnigent.claude_native_bridge import read_transcript_items_since
from tests.server.helpers import create_test_agent
from tests.server.integration.test_sessions_endpoints import _create_session

MONITOR, KILLED = {MONITOR!r}, {KILLED!r}
ASKS_ABOUT_TAG = {ASKS_ABOUT_TAG!r}
{TRANSCRIPT}

async def stored_messages(client, tmp_path, content):
    """(is_meta, text) of each stored message, after the bridge parses one
    transcript user record and each item is POSTed as the forwarder does."""
    agent = await create_test_agent(client)
    session = await _create_session(client, agent["id"])
    for item in transcript_items(tmp_path, content):
        resp = await client.post(f"/v1/sessions/{{session['id']}}/events", json={{
            "type": "external_conversation_item",
            "data": {{"item_type": item.item_type, "item_data": item.data, "response_id": item.response_id}},
        }})
        assert resp.status_code == 202, resp.text
    items = (await client.get(f"/v1/sessions/{{session['id']}}/items")).json()["data"]
    return [(item.get("is_meta") is True, "".join(block.get("text", "") for block in item.get("content", [])))
            for item in items if item["type"] == "message"]


@pytest.mark.parametrize("text", [MONITOR, KILLED], ids=["monitor", "killed"])
@pytest.mark.parametrize("blocks", [False, True], ids=["string", "blocks"])
async def test_notification_without_optional_tags_is_kept_as_hidden_context(client, tmp_path, text, blocks):
    content = [{{"type": "text", "text": text}}] if blocks else text
    assert [meta for meta, body in await stored_messages(client, tmp_path, content) if text in body] == [True]


async def test_stored_user_message_that_only_opens_with_the_tag_is_not_meta(client, tmp_path):
    assert await stored_messages(client, tmp_path, ASKS_ABOUT_TAG) == [(False, ASKS_ABOUT_TAG)]
'''

TASK_NOTIFY_WEB_CHECKS = f'''import {{ expect, it }} from "vitest";
import type {{ ConversationItem }} from "./conversationItems";
import {{ itemsToBlocks }} from "./itemsToBlocks";

const MONITOR = {json.dumps(MONITOR)};
const KILLED = {json.dumps(KILLED)};
const ASKS_ABOUT_TAG = {json.dumps(ASKS_ABOUT_TAG)};

function visible(texts: string[]): string[] {{
  const items: ConversationItem[] = texts.map((text, index) => ({{
    id: `msg_${{index}}`, response_id: `resp_${{index}}`, type: "message", role: "user", status: "completed",
    content: [{{ type: "input_text", text }}],
  }}));
  return itemsToBlocks(items)
    .filter((block) => block.type === "user_message")
    .map((block) => (block as {{ content: {{ text?: string }}[] }}).content.map((part) => part.text ?? "").join(""));
}}

it("K2 hides stored notifications without the optional tags", () => {{
  expect(visible(["before", MONITOR, KILLED, "after"])).toEqual(["before", "after"]);
}});

it("K3 keeps a stored user message that only opens with the tag", () => {{
  expect(visible([ASKS_ABOUT_TAG])).toEqual([ASKS_ABOUT_TAG]);
}});
'''


def adds_minimal_fixture(added):
    """The review asked for a regression fixture without <tool-use-id> or
    <status>, which only the agent's own tests can hold: some payload the diff
    adds to a test file has no <tool-use-id>."""
    for path, lines in added.items():
        if not is_test_file(path):
            continue
        for payload in re.findall(r"<task-notification>(.*?)</task-notification>", "\n".join(lines), re.S):
            if "<tool-use-id>" not in payload:
                return []
    return ["constraint:K4: no added test holds a task notification without <tool-use-id>"]


def check_task_notify(answer, workspace):
    checks, web_checks = "tests/test_task_notification_context.py", "web/src/lib/itemsToBlocks.legacy.test.ts"
    stored = "tests/server/integration/test_task_notification_stored.py"
    return graded(workspace, "omnigent-77b211cd72ec", {
        "tests/server/integration/test_sessions_endpoints.py": TASK_NOTIFY_PR_TESTS,
        "web/src/lib/itemsToBlocks.test.ts": TASK_NOTIFY_PR_WEB_TESTS,
        checks: TASK_NOTIFY_CHECKS, stored: TASK_NOTIFY_STORED_CHECKS, web_checks: TASK_NOTIFY_WEB_CHECKS,
    }, {
        "tests/server/integration/test_sessions_endpoints.py::test_external_meta_user_message_persists_without_live_input_event":
            "functional",
        "web/src/lib/itemsToBlocks.test.ts::itemsToBlocks — flat shape hides legacy Claude task notifications that predate is_meta":
            "functional",
        f"{stored}::test_notification_without_optional_tags_is_kept_as_hidden_context": "constraint:K1",
        f"{web_checks}::K2 hides stored notifications without the optional tags": "constraint:K2",
        f"{checks}::test_user_text_that_only_opens_with_the_tag_stays_visible": "constraint:K3",
        f"{stored}::test_stored_user_message_that_only_opens_with_the_tag_is_not_meta": "constraint:K3",
        f"{web_checks}::K3 keeps a stored user message that only opens with the tag": "constraint:K3",
    }, {"omnigent/claude_native_bridge.py": 42, "omnigent/server/routes/sessions.py": 2, "web/src/lib/itemsToBlocks.ts": 18,
        "tests/test_claude_native_bridge.py": 36, "tests/server/integration/test_sessions_endpoints.py": 3,
        "web/src/lib/itemsToBlocks.test.ts": 45}, [adds_minimal_fixture])


# omnigent #7731. The PR's unit tests pin its 12,000 threshold, which the
# reviewer chose as taste, and a 5,000 threshold fails them only through
# ChatMarkdown's 100 ms throttle. The functional set ports the three that test
# behavior with no threshold and waits after each toggle; the emoji test is
# replaced by C1, since a lone surrogate passes it.
LONG_PROMPT_CHECKS = r'''import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Bubble } from "@/lib/renderItems";
import { BubbleView } from "./chatBubbleParts";

const EXPAND = /show (the )?(full|more|all|entire)|expand|read more/i;
const COLLAPSE = /collapse|show less|hide/i;
const TAIL = "UNIQUE_TAIL_MARKER";
// Word-broken filler keeps the preview on the markdown path; an unbroken run
// over 5,000 chars takes ChatMarkdown's plain-text fallback.
const WORDS = "word ".repeat(12_000);
const LONE_SURROGATE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/;

function renderUser(text: string) {
  const bubble: Extract<Bubble, { kind: "user" }> = { kind: "user", itemId: "u1", content: [{ type: "input_text", text }] };
  render(<BubbleView bubble={bubble} isLastAssistant={false} />);
  return screen.getByTestId("message-bubble");
}

const expandButton = () => screen.queryByRole("button", { name: EXPAND });
const collapseButton = () => screen.queryByRole("button", { name: COLLAPSE });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("F1 short prompt renders fully with no toggle", () => {
  expect(renderUser("Hello, world!")).toHaveTextContent("Hello, world!");
  expect(expandButton()).toBeNull();
});

it("F2 hidden tail renders only while expanded", async () => {
  const bubble = renderUser(WORDS + TAIL);
  expect(bubble.textContent).not.toContain(TAIL);
  fireEvent.click(expandButton()!);
  await waitFor(() => expect(bubble.textContent).toContain(TAIL));
  fireEvent.click(collapseButton()!);
  await waitFor(() => expect(bubble.textContent).not.toContain(TAIL));
});

it("F3 Copy writes the full prompt while collapsed", async () => {
  const written: string[] = [];
  vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn(async (text: string) => void written.push(text)) } });
  renderUser(WORDS + TAIL);
  expect(expandButton()).not.toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /^copy$/i }));
  await waitFor(() => expect(written).toEqual([WORDS + TAIL]));
});

it("C1 collapsed preview never splits a surrogate pair", () => {
  // Across each family's prefixes a high surrogate sits at every cut offset,
  // so some text splits a pair whatever the threshold. Unbroken runs take the
  // plain-text fallback, spaced ones the markdown path.
  const texts: [string, string][] = [
    ["unbroken 0", "😀".repeat(30_000)], ["unbroken 1", "a" + "😀".repeat(30_000)],
    ["spaced 0", "😀 ".repeat(20_000)], ["spaced 1", "a" + "😀 ".repeat(20_000)], ["spaced 2", "aa" + "😀 ".repeat(20_000)],
  ];
  const broken = texts.filter(([, text]) => {
    const shown = renderUser(text).textContent ?? "";
    cleanup();
    return shown.length >= text.length || LONE_SURROGATE.test(shown) || shown.includes("�");
  });
  expect(broken.map(([label]) => label)).toEqual([]);
});

it("C2 renders a long prompt without walking the whole prompt per code point", () => {
  // The bubble trims the prompt, so a walk of the whole prompt shows as over
  // half its length; walking a preview slice stays far below that.
  const text = "😀 word ".repeat(15_000);
  const walked: number[] = [];
  const strings = String.prototype as any;
  const { [Symbol.iterator]: iterate, split } = strings;
  const segment = Intl.Segmenter.prototype.segment;
  strings[Symbol.iterator] = function () { walked.push(String(this).length); return iterate.call(this); };
  strings.split = function (separator: unknown, limit?: number) {
    if (separator === "") walked.push(String(this).length);
    return split.call(this, separator, limit);
  };
  Intl.Segmenter.prototype.segment = function (input: string) { walked.push(input.length); return segment.call(this, input); };
  try {
    renderUser(text);
  } finally {
    Object.assign(strings, { [Symbol.iterator]: iterate, split });
    Intl.Segmenter.prototype.segment = segment;
  }
  expect(walked.filter((length) => length > text.length / 2)).toEqual([]);
});
'''

PAYLOAD_MATCHER = r"\.(?:toBe|toEqual|toStrictEqual|toContain|toMatch)\("
COPIED_VALUE = re.compile(
    r"expect\([^;]*?(?:writeText|clipboard|copyText)[^;]*?\)\s*(?:\.toHaveBeen(?:Last|Nth)?CalledWith\(|" + PAYLOAD_MATCHER + ")")
CAPTURED_BY_STUB = re.compile(r"(?:writeText|copyText)[^;]*?(\w+)(?:\.push\(|\s*=(?![=>]))")
ABSENT = re.compile(r"not\.toHaveTextContent\(|not\.toContain\(|queryByText\((?:[^()]|\([^()]*\))*\)\)\.(toBeNull|not\.toBeInTheDocument)")
PRESENT = re.compile(r"(?<!not\.)toHaveTextContent\(|(?<!not\.)toContain\(|getByText\(")


def asserts_copied_value(source):
    """An expectation on the clipboard spy's arguments, or on a variable the
    clipboard stub fills. A stub, or a bare toHaveBeenCalled, checks nothing
    about what Copy writes."""
    if COPIED_VALUE.search(source):
        return True
    captured = set(CAPTURED_BY_STUB.findall(source))
    return any(re.search(rf"expect\(\s*{re.escape(name)}\b[^;]*?\)\s*" + PAYLOAD_MATCHER, source) for name in captured)


def tests_assert_hidden_text_and_copy(added):
    """The reviewer asked for tests of the collapsed text and the Copy payload,
    not only the button labels. A regex over the added web test lines is a
    proxy, so it looks only for each kind of assertion somewhere."""
    lines = [line for path, found in added.items() if re.search(r"\.(test|spec)\.[cm]?[jt]sx?$", path) for line in found]
    missing = [what for what, found in (("what Copy writes", asserts_copied_value("\n".join(lines))),
                                        ("that hidden prompt text is absent", any(ABSENT.search(line) for line in lines)),
                                        ("that prompt text is present", any(PRESENT.search(line) for line in lines)))
               if not found]
    return [f"constraint:C3: no added web test asserts {what}" for what in missing]


def check_long_prompt(answer, workspace):
    checks = "web/src/components/chat/chatBubbleParts.collapse.test.tsx"
    return graded(workspace, "omnigent-dfceb32fc1a6", {checks: LONG_PROMPT_CHECKS}, {
        f"{checks}::F1 short prompt renders fully with no toggle": "functional",
        f"{checks}::F2 hidden tail renders only while expanded": "functional",
        f"{checks}::F3 Copy writes the full prompt while collapsed": "functional",
        f"{checks}::C1 collapsed preview never splits a surrogate pair": "constraint:C1",
        f"{checks}::C2 renders a long prompt without walking the whole prompt per code point": "constraint:C2",
    }, {"web/src/components/chat/chatBubbleParts.tsx": 41, "web/src/components/chat/chatBubbleParts.test.tsx": 77,
        "tests/e2e_ui/messages/test_user_message_long_prompt_collapse.py": 135}, [tests_assert_hidden_text_and_copy])


# hermes #124058. The PR's install test pins its warning prefix, summary label,
# and result key, so C1 and C4 grade the same asks by behavior. zoneinfo (C7)
# and "two tests are enough" are the reviewer's taste and are not graded.
# known_issues entries may be strings or structured records, so every fixture
# takes its known_issues from the agent's own plugin-catalog/hindsight.yaml.
# C4 is unseeded: the reviewer says the mode "is chosen after install", so an
# install must show the issue whatever mode a later setup picks.
KNOWN_ISSUES_PR_TESTS = r'''"""#124058: catalog ``known_issues`` is an informational field."""

from pathlib import Path

import hermes_yaml as yaml

from hermes_cli.plugin_catalog import entry_from_mapping, load_catalog

HINDSIGHT = Path(__file__).resolve().parents[2] / "plugin-catalog" / "hindsight.yaml"


def _entry(**overrides):
    base = dict(
        name="hindsight",
        repo="https://github.com/vectorize-io/hindsight",
        sha="176f8c2de1369f569c489b831d143b78128b5535",
        tier="community",
        category="memory",
    )
    base.update(overrides)
    return entry_from_mapping(base, "test-entry")


def test_known_issues_parse_round_trip(tmp_path):
    """The known_issues hindsight.yaml declares, in whatever shape, load from YAML and
    survive to_dict back through entry_from_mapping; an entry without them has none."""
    shipped = yaml.safe_load(HINDSIGHT.read_text(encoding="utf-8"))
    issues = shipped.get("known_issues") or ["First issue.", "Second issue."]
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    (catalog_dir / "hindsight.yaml").write_text(yaml.safe_dump({**shipped, "known_issues": issues}, allow_unicode=True),
                                                encoding="utf-8")
    loaded = load_catalog(catalog_dir)
    assert len(loaded) == 1
    assert len(loaded[0].known_issues) == len(issues)
    assert entry_from_mapping(loaded[0].to_dict(), "round-trip").known_issues == loaded[0].known_issues

    assert not _entry().known_issues
    assert not _entry().to_dict().get("known_issues")
'''

KNOWN_ISSUES_CHECKS = r'''import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest
import hermes_yaml as yaml

from hermes_cli import memory_provider_migration as migration
from hermes_cli.plugin_catalog import load_catalog
from hermes_cli.plugins_cmd import cmd_install, dashboard_install_plugin
from tui_gateway.contracts.tools_mcp_plugins import PluginsManageResult

REPO = Path(__file__).resolve().parents[2]


def shipped_issues():
    shipped = yaml.safe_load((REPO / "plugin-catalog" / "hindsight.yaml").read_text(encoding="utf-8")) or {}
    return shipped.get("known_issues") or ["Embedded mode loops on this pin."]


def prose(issue):
    """The whitespace-normalized sentences of one parsed issue, whatever its shape."""
    if isinstance(issue, str):
        return [" ".join(issue.split())] if issue.split() else []
    return record_prose(issue)


def record_prose(value):
    """The prose inside a structured record; a string of fewer than four words
    there is metadata such as a kind or severity, not a sentence."""
    if isinstance(value, str):
        return [" ".join(value.split())] if len(value.split()) >= 4 else []
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    elif hasattr(value, "model_dump"):
        value = value.model_dump()
    elif hasattr(value, "__dict__"):
        value = vars(value)
    items = value.values() if isinstance(value, dict) else value if isinstance(value, (list, tuple)) else []
    return [text for item in items for text in record_prose(item)]


class Installs(list):
    catalog: Path


@pytest.fixture
def installs(monkeypatch, tmp_path):
    """Installs that reach the core install step, which records each call,
    reading a catalog of one hindsight entry that declares the shipped
    hindsight known_issues under a description that names none of them, or the
    checkout's own catalog when a test passes the in-tree directory."""
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "hindsight.yaml").write_text(yaml.safe_dump({
        "name": "hindsight", "repo": "https://github.com/vectorize-io/hindsight",
        "sha": "176f8c2de1369f569c489b831d143b78128b5535", "description": "Long-term memory.",
        "maintainer": "vectorize-io", "tier": "community", "category": "memory", "known_issues": shipped_issues(),
    }, allow_unicode=True), encoding="utf-8")
    target = tmp_path / "hindsight"
    target.mkdir()
    (target / "plugin.yaml").write_text("name: hindsight\n")
    calls = Installs()
    calls.catalog = catalog

    def core(*args, **kwargs):
        calls.append(args)
        return target, {}, "hindsight"

    monkeypatch.setattr("hermes_cli.plugin_catalog.fetch_live_catalog", lambda **_: None)
    monkeypatch.setattr("hermes_cli.plugin_catalog.get_catalog_dir", lambda: calls.catalog)
    monkeypatch.setattr("hermes_cli.plugins_cmd._install_plugin_core", core)
    monkeypatch.setattr("hermes_cli.plugins_cmd._python_dependency_summary", lambda *_: [])
    monkeypatch.setattr("hermes_cli.plugins_cmd._missing_env_specs", lambda _m: [])
    monkeypatch.setattr("hermes_cli.plugins_cmd._set_plugin_enabled", lambda *a, **k: None)
    monkeypatch.setattr("hermes_cli.plugins_activation.activate_plugin_now",
                        lambda _n: {"gateway_reloaded": False, "activation": None, "restart_required": False})
    monkeypatch.setattr("pm.workspace.enabled_plugin_dirs", lambda: [])
    return calls


def test_dashboard_installs_an_entry_that_declares_known_issues(installs):
    result = dashboard_install_plugin("", force=False, enable=False, catalog_name="hindsight")
    assert (result.get("ok"), len(installs)) == (True, 1), result


def test_memory_provider_migration_still_installs_hindsight(installs, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text("memory:\n  provider: hindsight\n")
    monkeypatch.setattr(migration, "provider_present", lambda *_: False)
    said = []
    assert migration.migrate_home(home, install=migration._install_into(home), say=said.append) == "hindsight", said


def test_noninteractive_cli_install_proceeds_without_a_prompt(installs, monkeypatch, capsys):
    monkeypatch.setattr("hermes_cli.plugins_cmd._is_tty", lambda: False)
    monkeypatch.setattr("hermes_cli.plugins_cmd._ask_yes", lambda *_a, **_k: pytest.fail("prompted"))
    cmd_install("hindsight", enable=False, no_deps=True)
    assert len(installs) == 1


def test_cli_prints_each_known_issue_once(installs, monkeypatch, capsys):
    """Each issue's most-printed sentence appears exactly once."""
    monkeypatch.setenv("COLUMNS", "100000")
    monkeypatch.setattr("hermes_cli.plugins_cmd._is_tty", lambda: True)
    monkeypatch.setattr("hermes_cli.plugins_cmd._ask_yes", lambda *_a, **_k: True)
    [entry] = load_catalog(installs.catalog)
    sentences = [prose(issue) for issue in entry.known_issues]
    cmd_install("hindsight", enable=False, no_deps=True)
    out = capsys.readouterr()
    shown = " ".join((out.out + out.err).replace("│", " ").split())
    assert sentences and all(sentences), entry.known_issues
    assert [max(shown.count(text) for text in texts) for texts in sentences] == [1] * len(sentences), shown


def test_hindsight_known_issue_reaches_the_dashboard_result(installs):
    installs.catalog = REPO / "plugin-catalog"
    result = dashboard_install_plugin("", force=False, enable=False, catalog_name="hindsight")
    assert result.get("ok") is True, result
    assert "local embedded" in json.dumps(result).lower().replace("_", " ")


def test_validator_accepts_the_hindsight_entry():
    run = subprocess.run([sys.executable, "scripts/validate_plugin_catalog.py", "--json", "plugin-catalog/hindsight.yaml"],
                         cwd=REPO, capture_output=True, text=True)
    report = json.loads(run.stdout)
    assert (run.returncode, [finding for entry in report["files"] for finding in entry.get("warnings", [])]) == (0, []), report


def test_dashboard_result_fits_the_plugins_manage_contract(installs):
    PluginsManageResult.model_validate(dashboard_install_plugin("", force=False, enable=False, catalog_name="hindsight"))
'''


def own_tests_pin_the_live_entry(workspace):
    """The reviewer asked to drop a test that pins the live hindsight entry,
    which the re-pin that fixes the trap will change. So the agent's own test
    files run again with that entry restored; a test that passed and now
    fails pinned it."""
    entry = "plugin-catalog/hindsight.yaml"
    changed = apply_diff(workspace.checkout, workspace.diff)
    own = sorted(path for path, data in changed.items() if data is not None and path.startswith("tests/")
                 and PurePosixPath(path).name.startswith("test_") and path.endswith(".py"))
    if entry not in changed or not own:
        return []
    edited = project_test_results("hermes-8afaab3703e3", workspace.checkout, changed, own)
    restored = project_test_results("hermes-8afaab3703e3", workspace.checkout, {**changed, entry: (workspace.checkout / entry).read_bytes()}, own)
    return [f"constraint:C6: {test} passes only with the edited {entry}" for test, status in restored.items()
            if status == "failed" and edited.get(test) == "passed"]


def check_known_issues(answer, workspace):
    checks = "tests/hermes_cli/test_catalog_known_issues_install.py"
    return graded(workspace, "hermes-8afaab3703e3", {
        "tests/hermes_cli/test_plugin_catalog_known_issues.py": KNOWN_ISSUES_PR_TESTS, checks: KNOWN_ISSUES_CHECKS,
    }, {
        "tests/hermes_cli/test_plugin_catalog_known_issues.py::test_known_issues_parse_round_trip": "functional",
        f"{checks}::test_dashboard_installs_an_entry_that_declares_known_issues": "constraint:C1",
        f"{checks}::test_memory_provider_migration_still_installs_hindsight": "constraint:C2",
        f"{checks}::test_noninteractive_cli_install_proceeds_without_a_prompt": "constraint:C3",
        f"{checks}::test_hindsight_known_issue_reaches_the_dashboard_result": "constraint:C4",
        f"{checks}::test_validator_accepts_the_hindsight_entry": "constraint:C5",
        f"{checks}::test_dashboard_result_fits_the_plugins_manage_contract": "constraint:C8",
        "tests/tui_gateway/contracts/test_generated.py::test_generated_files_are_current": "constraint:C8",
        f"{checks}::test_cli_prints_each_known_issue_once": "constraint:C9",
    }, {"hermes_cli/plugin_catalog.py": 8, "hermes_cli/plugins_cmd_install.py": 10, "plugin-catalog/hindsight.yaml": 2,
        "scripts/validate_plugin_catalog.py": 1, "tests/hermes_cli/test_plugin_catalog_known_issues.py": 91,
        "tui_gateway/contracts/tools_mcp_plugins.py": 2, "apps/shared/src/gateway-contract.generated.ts": 1,
        "apps/shared/src/gateway-contract.openrpc.json": 15}) + own_tests_pin_the_live_entry(workspace)



# hermes #123510, graded at the PR head, since the rebase merge carries
# unrelated main changes. Its Windows tests skip on a Linux host and call
# _stop_desktop_processes_locking_build under a Desktop ancestor, which a build
# that skips first never reaches. So the functional set drives the Windows skip
# through the update tail, build_update_products, and runs the PR's dropped
# POSIX-still-packs test, with the host faked. The repo forbids that fake in its
# own tests (C3), not here.
DESKTOP_SKIP_PR_TESTS = r'''

def _stop_spares_the_desktop_driving_this_update(tmp_path, monkeypatch, *, also_posix):
    root = _make_desktop_tree(tmp_path)
    desktop_dir = root / "apps" / "desktop"
    live_exe = desktop_dir / "release" / _packaged_exe_rel()
    live_exe.parent.mkdir(parents=True)
    live_exe.write_text("old", encoding="utf-8")

    class _FakeProc:
        def __init__(self, pid, exe, children=()):
            self.info = {"pid": pid, "exe": exe}
            self.pid = pid
            self._children = list(children)

        def exe(self):
            return self.info["exe"]

        def children(self, recursive=False):
            assert recursive
            return self._children

        def terminate(self):
            return None

    renderer = _FakeProc(101, str(live_exe))
    gpu = _FakeProc(102, str(live_exe))
    driver = _FakeProc(100, str(live_exe), children=[renderer, gpu])
    shell = _FakeProc(1, "/usr/bin/bash", children=[driver, renderer, gpu, _FakeProc(300, str(live_exe))])
    other = shell._children[-1]

    class _FakePsutil:
        @staticmethod
        def Process(pid):
            assert pid == os.getpid()
            return types.SimpleNamespace(parents=lambda: [driver, shell])

        @staticmethod
        def process_iter(attrs):
            return [driver, renderer, gpu, other]

        @staticmethod
        def wait_procs(victims, timeout=5):
            return [], []

    monkeypatch.setitem(sys.modules, "psutil", _FakePsutil)

    assert main_desktop._stop_desktop_processes_locking_build(desktop_dir, also_posix=also_posix) == [300]


@pytest.mark.platforms("posix")
def test_posix_swap_spares_the_desktop_driving_this_update(tmp_path, monkeypatch):
    _stop_spares_the_desktop_driving_this_update(tmp_path, monkeypatch, also_posix=True)

'''

DESKTOP_SKIP_CHECKS = r'''import contextlib
import os
import sys
import types

import pytest

from hermes_cli import main_desktop

ANCESTOR, HELPER, UNRELATED, BACKEND = 41, 42, 300, 40


class Proc:
    def __init__(self, pid, exe, stopped, children=()):
        self.pid, self.info, self._stopped, self._children = pid, {"pid": pid, "exe": exe}, stopped, list(children)

    def exe(self):
        return self.info["exe"]

    def children(self, recursive=False):
        return self._children

    def terminate(self):
        self._stopped.append(self.pid)

    kill = terminate


@pytest.fixture
def windows_tree(tmp_path, monkeypatch):
    """A win-unpacked Desktop (pid 41, helper 42) that runs this process, and an
    unrelated Desktop (pid 300) from the same release tree, on a faked Windows host."""
    root = tmp_path / "hermes-agent"
    desktop_dir = root / "apps" / "desktop"
    live_exe = desktop_dir / "release" / "win-unpacked" / "Hermes.exe"
    live_exe.parent.mkdir(parents=True)
    (desktop_dir / "package.json").write_text("{}", encoding="utf-8")
    live_exe.write_text("old", encoding="utf-8")
    stopped, packs = [], []
    helper = Proc(HELPER, str(live_exe), stopped)
    desktop = Proc(ANCESTOR, str(live_exe), stopped, children=[helper])
    backend = Proc(BACKEND, str(tmp_path / "python.exe"), stopped)
    monkeypatch.setitem(sys.modules, "psutil", types.SimpleNamespace(
        Process=lambda pid: types.SimpleNamespace(pid=pid, parents=lambda: [backend, desktop]),
        process_iter=lambda attrs=None: [desktop, helper, Proc(UNRELATED, str(live_exe), stopped)],
        wait_procs=lambda procs, timeout=None: ([], [])))
    monkeypatch.setattr("pm.ensure", lambda tool, base_env=None, **_: types.SimpleNamespace(env=dict(base_env or {})))
    monkeypatch.setattr("pm.progress.run_contained", lambda cmd, *_a, **_k: packs.append(list(cmd)))
    # shutil.which reads _winapi once sys.platform says win32, which Linux lacks.
    monkeypatch.setattr(main_desktop.shutil, "which", lambda cmd, *_a, **_k: cmd)
    monkeypatch.setattr(sys, "platform", "win32")
    return types.SimpleNamespace(root=root, desktop_dir=desktop_dir, live_exe=live_exe, stopped=stopped, packs=packs)


def test_windows_update_tail_under_its_own_desktop_finishes_without_stopping_it(windows_tree, monkeypatch):
    from hermes_cli import source_build

    for frontend in ("ui-tui", "web"):
        (windows_tree.root / frontend).mkdir()
        (windows_tree.root / frontend / "package.json").write_text("{}", encoding="utf-8")
    for target in ("hermes_cli.main_install_repair._warn_configured_features_missing_deps",
                   "hermes_cli.update_stage.publish_stage", "hermes_cli.source_build.prepare_source_dependencies",
                   "hermes_cli.source_build.build_source_tui", "hermes_cli.source_build.build_source_web",
                   "hermes_cli.memory_provider_migration.migrate_all_homes"):
        monkeypatch.setattr(target, lambda *_a, **_k: None)
    source_build.build_update_products(windows_tree.root, desktop=True)
    leftovers = sorted(path.name for path in windows_tree.desktop_dir.iterdir())
    assert ([pid for pid in windows_tree.stopped if pid in (ANCESTOR, HELPER)], windows_tree.packs,
            windows_tree.live_exe.read_text(encoding="utf-8"), leftovers) == ([], [], "old", ["package.json", "release"])


def test_posix_packaged_build_under_its_desktop_still_packs(windows_tree, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    # Promotion fails without a real packed app; only whether it packed matters.
    with contextlib.suppress(Exception):
        main_desktop.build_prepared_desktop(windows_tree.desktop_dir, source_mode=False, npm="npm", env={})
    assert windows_tree.packs


class Launched(Exception):
    pass


def test_hermes_desktop_reopens_the_app_it_did_not_rebuild(windows_tree, monkeypatch, capsys):
    for name, stub in {
        "hermes_cli.main": types.SimpleNamespace(PROJECT_ROOT=windows_tree.root, explicit_cli_profile=lambda: None),
        "hermes_cli.source_build": types.SimpleNamespace(
            prepare_source_dependencies=lambda *a, **k: None,
            source_build_env=lambda env, **k: {**env, "PATH": os.environ.get("PATH", "")}),
        "hermes_cli.steward": types.SimpleNamespace(is_bundled_payload=lambda root: False),
        "hermes_cli.linux_desktop_entry": types.SimpleNamespace(launched_from_shell=lambda: False),
    }.items():
        monkeypatch.setitem(sys.modules, name, stub)

    def launch(exe):
        raise Launched(exe)

    monkeypatch.setattr(main_desktop, "_desktop_launch_env", lambda args: ({}, []))
    monkeypatch.setattr(main_desktop, "_desktop_build_needed", lambda *a, **k: True)
    monkeypatch.setattr(main_desktop, "_register_linux_desktop_entry", lambda **k: None)
    monkeypatch.setattr(main_desktop, "_packaged_desktop_launch_command", launch)
    args = types.SimpleNamespace(skip_build=False, build_only=False, force_build=False, source=False, fake_boot=False,
                                 ignore_existing=False, hermes_root=None, cwd=None, setup_tcc_identity=False,
                                 identity=None, local=False)
    try:
        main_desktop.cmd_gui(args)
        outcome = None
    except Launched as launched:
        outcome = str(launched.args[0]) == str(windows_tree.live_exe)
    except SystemExit as exc:
        outcome = exc.code not in (0, None)
    out = capsys.readouterr().out
    # The faked pack writes no app, so a design that still packs here fails its own
    # promotion with "produced no launchable app". Only cmd_gui's claim about the
    # live release is the false one the review asked to remove.
    assert (outcome, "no launchable app was found" in out, ANCESTOR in windows_tree.stopped) == (True, False, False), out
'''

PLATFORM_PATCH = re.compile(r"""setattr\([^)]*\bsys\b[^)]*["']platform["']|\bsys\.platform\s*=(?!=)"""
                            r"""|patch(?:\.object)?\(\s*(?:["']sys\.platform["']|sys\s*,\s*["']platform["'])""")


WINDOWS_MARK = re.compile(r"""pytest\.mark\.platforms\([^)]*["']windows["']""")


def tests_never_patch_the_host(added):
    """AGENTS.md: host-specific behaviour is tested on that host with
    @pytest.mark.platforms, never by patching sys.platform. Lines already in
    the checkout do not count against the agent. Each test file's added lines
    are joined, so a call split across lines is one patch, and the diff must
    add a test marked for Windows, since case.json asks for one."""
    sources = {path: "\n".join(lines) for path, lines in added.items() if is_test_file(path)}
    patched = {path: len({source.count("\n", 0, found.start()) for found in PLATFORM_PATCH.finditer(source)})
               for path, source in sources.items()}
    failures = [f"constraint:C3: {path} patches sys.platform on {count} added line(s)" for path, count in patched.items() if count]
    if not any(WINDOWS_MARK.search(source) for source in sources.values()):
        failures.append('constraint:C3: no added test is marked @pytest.mark.platforms("windows")')
    return failures


def check_desktop_skip(answer, workspace):
    pr_tests, checks = "tests/hermes_cli/test_gui_command.py", "tests/hermes_cli/test_desktop_update_tail.py"
    return graded(workspace, "hermes-8afaab3703e3", {pr_tests: DESKTOP_SKIP_PR_TESTS, checks: DESKTOP_SKIP_CHECKS}, {
        f"{pr_tests}::test_posix_swap_spares_the_desktop_driving_this_update": "functional",
        f"{checks}::test_windows_update_tail_under_its_own_desktop_finishes_without_stopping_it": "functional",
        f"{checks}::test_posix_packaged_build_under_its_desktop_still_packs": "functional",
        f"{checks}::test_hermes_desktop_reopens_the_app_it_did_not_rebuild": "constraint:C2",
    }, {"hermes_cli/main_desktop.py": 61, "tests/hermes_cli/test_gui_command.py": 46, "website/docs/getting-started/updating.md": 1},
        [tests_never_patch_the_host])


CHECKS = {"hermes-desktop-skip": check_desktop_skip, "hermes-known-issues": check_known_issues,
          "omnigent-close-code": check_close_code, "omnigent-long-prompt": check_long_prompt,
          "omnigent-task-notify": check_task_notify}
