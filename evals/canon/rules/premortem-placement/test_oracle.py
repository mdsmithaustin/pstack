import json
import unittest

from check import RULES, grade

RULE = "premortem-placement"
CASES = RULES / RULE / "cases"


def labels(case):
    return json.loads((CASES / case / "samples" / "labels.json").read_text())


class PushHookRolloutTests(unittest.TestCase):
    CASE = "tally-push-hook-rollout"

    def test_every_labeled_sample_delivers_the_document(self):
        for sample, label in labels(self.CASE).items():
            with self.subTest(sample=sample, label=label):
                self.assertEqual(grade(RULE, self.CASE, sample), [])

    def test_message_without_the_file_fails(self):
        answer = "I looked at the register and the hook looks fine to me. Adopt Monday.\n"
        self.assertEqual(grade(RULE, self.CASE, text=answer), ["the final message holds no ops/premortem.md"])

    def test_empty_file_block_fails(self):
        answer = 'Here it is.\n\n<file path="ops/premortem.md">\n</file>\n'
        self.assertEqual(grade(RULE, self.CASE, text=answer), ["the final message holds no ops/premortem.md"])

    def test_file_under_another_path_fails(self):
        answer = '<file path="docs/premortem.md">\n# Premortem\n\nThe hook is fine.\n</file>\n'
        self.assertEqual(grade(RULE, self.CASE, text=answer), ["the final message holds no ops/premortem.md"])

    def test_fenced_document_passes(self):
        answer = '<file path="ops/premortem.md">\n```markdown\n# Premortem\n\nOne cause under four rows.\n```\n</file>\n'
        self.assertEqual(grade(RULE, self.CASE, text=answer), [])


class ChangelogGateTests(unittest.TestCase):
    CASE = "ledgerd-changelog-gate"

    def test_every_labeled_sample_delivers_the_document(self):
        for sample, label in labels(self.CASE).items():
            with self.subTest(sample=sample, label=label):
                self.assertEqual(grade(RULE, self.CASE, sample), [])

    def test_message_without_the_file_fails(self):
        answer = "Merge it. It reverts in one commit and blocks nobody for two weeks.\n"
        self.assertEqual(grade(RULE, self.CASE, text=answer), ["the final message holds no ops/premortem.md"])


class RetryBumpTests(unittest.TestCase):
    CASE = "tally-retry-bump"

    def test_every_labeled_sample_is_a_reply(self):
        for sample, label in labels(self.CASE).items():
            with self.subTest(sample=sample, label=label):
                self.assertEqual(grade(RULE, self.CASE, sample), [])

    def test_blank_reply_fails(self):
        self.assertEqual(grade(RULE, self.CASE, text="\n\n  \n"), ["the final message is empty"])

    def test_one_line_reply_passes(self):
        self.assertEqual(grade(RULE, self.CASE, text="POST /postings is retried too, so add an idempotency key first.\n"), [])
