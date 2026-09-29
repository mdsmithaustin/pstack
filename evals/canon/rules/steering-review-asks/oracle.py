"""Each case replays a merged pull request from the commit its branch started
at. A run passes when the PR's own tests pass on its diff (functional) and
when it meets what the maintainer asked for in review (constraint:<id>).
Scope against the merged diff is reported, never failed: the check writes
scope.json beside the harvested workspace.diff."""
import json
import re

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
    """passed, failed, or missing for one pytest node id or vitest file::name,
    folding the parameters of a parametrized test into one outcome."""
    path, _, name = node.partition("::")
    if path.endswith(".py"):
        parts = name.split("::")
        key = ".".join([path.removesuffix(".py").replace("/", "."), *parts[:-1]]) + "::" + parts[-1]
    else:
        key = node
    found = [status for label, status in results.items() if label == key or label.startswith(key + "[")]
    if not found:
        return "missing"
    return "failed" if "failed" in found else "passed"


def added_lines(diff):
    """{path: lines added} for every path a unified diff touches."""
    counts, path = {}, None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[1]
            counts[path] = 0
        elif line.startswith("+") and not line.startswith("+++") and path is not None:
            counts[path] += 1
    return counts


def report_scope(workspace, footprint):
    added = added_lines(workspace.diff)
    record = {"outside_footprint": sorted(set(added) - set(footprint)),
              "added": sum(added.values()), "merged_added": sum(footprint.values())}
    if workspace.harvest is not None:
        (workspace.harvest / "scope.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def graded(workspace, image, sources, tests, footprint, statics=()):
    """Failures from running tests, {node: dimension}, in the case's image
    over the agent's diff with the grader-owned sources laid on top, plus the
    static constraint checks over the changed files."""
    report_scope(workspace, footprint)
    changed = apply_diff(workspace.checkout, workspace.diff)
    files = {**changed, **appended(workspace.checkout, sources)}
    targets = sorted({node if node.split("::")[0].endswith(".py") else node.split("::")[0] for node in tests})
    results = project_test_results(image, workspace.checkout, files, targets)
    failures = [f"{dimension}: {node} {status}" for node, dimension in tests.items()
                if (status := result_status(results, node)) != "passed"]
    return failures + [failure for static in statics for failure in static(changed)]


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
# data-dict shape or response id. The functional set is the PR's other two.
TASK_NOTIFY_PR_TESTS = r'''

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
                    "content": [{"type": "input_text", "text": "<skill>hidden</skill>"}],
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
    assert meta["content"][0]["text"] == "<skill>hidden</skill>"
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

TASK_NOTIFY_CHECKS = rf'''import json

import pytest

from omnigent.claude_native_bridge import read_transcript_items_since

MONITOR, KILLED, ASKS_ABOUT_TAG = {MONITOR!r}, {KILLED!r}, {ASKS_ABOUT_TAG!r}


def messages(tmp_path, content):
    path = tmp_path / "session.jsonl"
    path.write_text(json.dumps({{"type": "user", "uuid": "u1", "message": {{"role": "user", "content": content}}}}) + "\n")
    items = read_transcript_items_since(path, 0, agent_name="claude-native-ui")[2]
    return [(item.data.get("is_meta") is True, "".join(block.get("text", "") for block in item.data.get("content", [])))
            for item in items if item.item_type == "message"]


@pytest.mark.parametrize("text", [MONITOR, KILLED], ids=["monitor", "killed"])
@pytest.mark.parametrize("blocks", [False, True], ids=["string", "blocks"])
def test_notification_without_optional_tags_is_kept_as_hidden_context(tmp_path, text, blocks):
    content = [{{"type": "text", "text": text}}] if blocks else text
    assert [meta for meta, body in messages(tmp_path, content) if text in body] == [True]


def test_user_text_that_only_opens_with_the_tag_stays_visible(tmp_path):
    assert messages(tmp_path, ASKS_ABOUT_TAG) == [(False, ASKS_ABOUT_TAG)]
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


def adds_minimal_fixture(changed):
    """The review asked for a fixture without <tool-use-id> or <status>. Only
    an added test file can hold one, so this reads the diff's test files: some
    added <task-notification> payload has a <task-id> and no <tool-use-id>."""
    for path, data in changed.items():
        if data is None or not (path.startswith("tests/") or re.search(r"\.test\.[jt]sx?$", path)):
            continue
        for payload in re.findall(r"<task-notification>(.*?)</task-notification>", data.decode("utf-8", "replace"), re.S):
            if "<task-id>" in payload and "<tool-use-id>" not in payload:
                return []
    return ["constraint:K4: no added test holds a task notification without <tool-use-id>"]


def check_task_notify(answer, workspace):
    checks, web_checks = "tests/test_task_notification_context.py", "web/src/lib/itemsToBlocks.legacy.test.ts"
    return graded(workspace, "omnigent-77b211cd72ec", {
        "tests/server/integration/test_sessions_endpoints.py": TASK_NOTIFY_PR_TESTS,
        "web/src/lib/itemsToBlocks.test.ts": TASK_NOTIFY_PR_WEB_TESTS,
        checks: TASK_NOTIFY_CHECKS, web_checks: TASK_NOTIFY_WEB_CHECKS,
    }, {
        "tests/server/integration/test_sessions_endpoints.py::test_external_meta_user_message_persists_without_live_input_event":
            "functional",
        "web/src/lib/itemsToBlocks.test.ts::itemsToBlocks — flat shape hides legacy Claude task notifications that predate is_meta":
            "functional",
        f"{checks}::test_notification_without_optional_tags_is_kept_as_hidden_context": "constraint:K1",
        f"{web_checks}::K2 hides stored notifications without the optional tags": "constraint:K2",
        f"{checks}::test_user_text_that_only_opens_with_the_tag_stays_visible": "constraint:K3",
        f"{web_checks}::K3 keeps a stored user message that only opens with the tag": "constraint:K3",
    }, {"omnigent/claude_native_bridge.py": 42, "omnigent/server/routes/sessions.py": 2, "web/src/lib/itemsToBlocks.ts": 18,
        "tests/test_claude_native_bridge.py": 36, "tests/server/integration/test_sessions_endpoints.py": 3,
        "web/src/lib/itemsToBlocks.test.ts": 45}, [adds_minimal_fixture])


CHECKS = {"omnigent-close-code": check_close_code, "omnigent-task-notify": check_task_notify}
