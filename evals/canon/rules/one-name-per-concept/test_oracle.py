import difflib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from check import RULES, grade
from shared import Workspace

sys.path.insert(0, str(RULES.parent))
import workspace  # noqa: E402

RULE, CASE = "one-name-per-concept", "billing-pause"
PROJECT = RULES / RULE / "cases" / CASE / "project"


class BillingPauseTests(unittest.TestCase):
    def test_pause_on_subscription_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_membership_beside_subscription_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "the code names one concept twice: MAX_MEMBERSHIP_PAUSE, MembershipPause, membership, membership_id, pause_membership beside "
                "Subscription, SubscriptionStatus, SubscriptionStore, cancel_subscription, subscription, subscription_id, subscriptions, "
                "test_active_subscription_past_its_date_is_due"
            ],
        )

    def test_full_rename_passes(self):
        answer = []
        for path in sorted(PROJECT.rglob("*.py")):
            relative = path.relative_to(PROJECT).as_posix()
            body = path.read_text().replace("Subscription", "Membership").replace("subscription", "membership")
            renamed = relative.replace("subscription", "membership")
            answer.append(f'<file path="{renamed}">\n{body}</file>')
            if renamed != relative:
                answer.append(f'<file path="{relative}">\n</file>')
        answer.append('<file path="billing/pause.py">\ndef pause_membership(membership):\n    return membership\n</file>')
        self.assertEqual(grade(RULE, CASE, text="\n".join(answer)), [])

    def test_no_pause_fails(self):
        self.assertEqual(grade(RULE, CASE, text="Nothing to change."), ["no new name carries the pause"])


def omnigent_sample(case, sample):
    root = RULES / RULE / "cases" / case
    spec = workspace.parse_spec(root, json.loads((root / "case.json").read_text())["workspace"])
    diff = (root / "samples" / f"{sample}.diff").read_text()
    return grade(RULE, case, f"{sample}.md", workspace=Workspace(workspace.reference_checkout(spec)[0], diff))


def omnigent_mirror():
    return workspace.has_commit(workspace.mirror_path("omnigent"), "02969a131c72d74c00c5800d8e82ae831f8ec5e5")


@unittest.skipUnless(omnigent_mirror(), "needs the omnigent mirror; see README Workspace cases")
class SessionsByTagTests(unittest.TestCase):
    def test_label_filter_in_route_store_and_client_passes(self):
        self.assertEqual(omnigent_sample("sessions-by-tag", "good"), [])

    def test_tag_filter_beside_the_labels_fails(self):
        self.assertEqual(
            omnigent_sample("sessions-by-tag", "bad"),
            [
                "omnigent/server/routes/sessions/routes_core.py adds tag names beside the code's labels: tag, tag_filters",
                "omnigent/stores/conversation_store/__init__.py adds tag names beside the code's labels: tags",
                "omnigent/stores/conversation_store/sqlalchemy_store.py adds tag names beside the code's labels: tag_key, tag_value, tags",
                "sdks/python-client/omnigent_client/_sessions.py adds tag names beside the code's labels: tag, tags",
                "omnigent/server/routes/sessions/routes_core.py adds no name that says label",
                "sdks/python-client/omnigent_client/_sessions.py adds no name that says label",
            ],
        )


@unittest.skipUnless(omnigent_mirror(), "needs the omnigent mirror; see README Workspace cases")
class SessionsByLabelTests(unittest.TestCase):
    def test_label_filter_in_route_store_and_client_passes(self):
        self.assertEqual(omnigent_sample("sessions-by-label", "good"), [])

    def test_filter_left_out_of_the_client_fails(self):
        self.assertEqual(omnigent_sample("sessions-by-label", "bad"), ["sdks/python-client/omnigent_client/_sessions.py adds no name that says label"])


ROUTE = "omnigent/server/routes/sessions/routes_core.py"
CLIENT = "sdks/python-client/omnigent_client/_sessions.py"
BEFORE = {
    ROUTE: "from fastapi import Query\n\n\ndef list_sessions(limit: int = Query(default=20)):\n    return limit\n",
    CLIENT: "def list_sessions(limit=20):\n    return {\"limit\": limit}\n",
}


def graded_edit(after):
    """Grade a diff from BEFORE to after on a two-file checkout."""
    diff = "".join(
        f"diff --git a/{path} b/{path}\n" + "".join(difflib.unified_diff(
            BEFORE[path].splitlines(keepends=True), after[path].splitlines(keepends=True), f"a/{path}", f"b/{path}"))
        for path in sorted(after) if after[path] != BEFORE[path]
    )
    with tempfile.TemporaryDirectory() as directory:
        for path, text in BEFORE.items():
            (Path(directory) / path).parent.mkdir(parents=True, exist_ok=True)
            (Path(directory) / path).write_text(text)
        return grade(RULE, "sessions-by-tag", text="Done.", workspace=Workspace(Path(directory), diff))


class DeprecatedAliasTests(unittest.TestCase):
    """omnigent's AGENTS.md asks for a @deprecated marker on anything slated
    for removal. Such an alias is on its way out, not a second name."""

    LABEL_ROUTE = (
        "from fastapi import Query\n\n\ndef list_sessions(\n    limit: int = Query(default=20),\n"
        "    label: list[str] = Query(default=[]),\n{alias}):\n    return limit\n"
    )
    LABEL_CLIENT = "def list_sessions(limit=20, labels=None):\n    return {{\"limit\": limit, \"label\": labels}}\n{alias}"

    def test_deprecated_query_parameter_and_function_are_not_a_second_name(self):
        after = {
            ROUTE: self.LABEL_ROUTE.format(alias="    tag: list[str] = Query(default=[], deprecated=True),\n"),
            CLIENT: self.LABEL_CLIENT.format(alias='\n\n@deprecated("Use list_sessions(labels=...); removed in 0.20.")\ndef list_by_tags(tags):\n    return list_sessions(labels=tags)\n'),
        }

        self.assertEqual(graded_edit(after), [])

    def test_the_same_alias_without_the_marker_is_a_second_name(self):
        after = {
            ROUTE: self.LABEL_ROUTE.format(alias="    tag: list[str] = Query(default=[]),\n"),
            CLIENT: self.LABEL_CLIENT.format(alias="\n\ndef list_by_tags(tags):\n    return list_sessions(labels=tags)\n"),
        }

        self.assertEqual(
            graded_edit(after),
            [
                "omnigent/server/routes/sessions/routes_core.py adds tag names beside the code's labels: tag",
                "sdks/python-client/omnigent_client/_sessions.py adds tag names beside the code's labels: list_by_tags, tags",
            ],
        )
