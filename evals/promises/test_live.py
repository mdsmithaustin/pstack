import unittest

import live

CODEX_CHAT = """I'm using `poteto-mode`. I'll identify the command first.

1. In progress. **You own the design. Plan, review, verify.** Delegate implementation. Stay in the lead.
2. Pending. `how` over the affected subsystem.
3. ⏭️ `architect`. skipped: one module
4. [x] Verify on the matching surface."""


class ChatWorklist(unittest.TestCase):
    def test_capitalized_states_skips_and_checkboxes_parse(self):
        items = live.chat_worklist(CODEX_CHAT)
        self.assertEqual([i["state"] for i in items], ["in progress", "pending", "skipped: one module", "completed"])
        self.assertEqual(items[1]["text"], "Pending. `how` over the affected subsystem.")

    def test_a_list_with_no_state_is_not_a_worklist(self):
        self.assertIsNone(live.chat_worklist("1. read the code\n2. write the fix"))

    def test_a_reply_summary_with_one_state_word_is_not_a_worklist(self):
        reply = "Summary\n- the flag now emits rows\n- default text stays byte-identical\n- verification done for both forms"
        self.assertIsNone(live.chat_worklist(reply))

    def test_bare_checkbox_lines_parse(self):
        self.assertEqual([i["state"] for i in live.chat_worklist("[x] one\n[ ] two\n- [~] three")],
                         ["completed", "pending", "in progress"])


if __name__ == "__main__":
    unittest.main()
