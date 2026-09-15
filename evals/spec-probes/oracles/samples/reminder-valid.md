<spec-probe-record>
{
  "scope": "spec_review",
  "requirements": [
    {
      "requirement_id": "RR-301",
      "shape": "numeric-range",
      "items": [
        {"check_index": 1, "probe_kind": "edge", "category": "boundary-values", "question": "Which timezone defines the calendar day for the two-reminder limit?", "disposition": "unresolved", "reason": "The two-reminder boundary depends on a calendar day with no timezone.", "resolution_kind": "gap"},
        {"check_index": 2, "probe_kind": "edge", "category": "precision-overflow", "question": "Can the integer reminder count require rounding?", "disposition": "dismissed", "reason": "The reminder count is a discrete integer, so rounding is not applicable.", "resolution_kind": "not_applicable"}
      ],
      "coverage": {"applicable": 2, "resolved": 0, "dismissed": 1, "unresolved": 1, "backstop": 0, "judgment": 0}
    },
    {
      "requirement_id": "RR-302",
      "shape": "text",
      "items": [
        {"check_index": 3, "probe_kind": "edge", "category": "empty-degenerate", "question": "What should an empty SMS or email message do?", "disposition": "unresolved", "reason": "Neither the SMS nor email requirement defines empty message content.", "resolution_kind": "gap"},
        {"check_index": 4, "probe_kind": "edge", "category": "encoding", "question": "Which character encoding and SMS length rule applies to the name?", "disposition": "unresolved", "reason": "SMS content includes a name but gives no character encoding contract.", "resolution_kind": "gap"},
        {"check_index": 5, "probe_kind": "prohibition", "category": "bespoke-prohibition", "question": "Must the reviewer reject reminders that shame a borrower to drive repayment?", "disposition": "resolved", "reason": "The judgment tag assigns a trained reviewer to reject shaming framing against the borrower.", "resolution_kind": "judgment"},
        {"check_index": 6, "probe_kind": "prohibition", "category": "bespoke-prohibition", "question": "Must SMS hide the overdue amount from a third party viewing the device?", "disposition": "unresolved", "reason": "The SMS may expose the overdue amount to a third party, but audience limits are unstated.", "resolution_kind": "gap"}
      ],
      "coverage": {"applicable": 4, "resolved": 1, "dismissed": 0, "unresolved": 3, "backstop": 0, "judgment": 1}
    }
  ],
  "coverage": {"applicable": 6, "resolved": 1, "dismissed": 1, "unresolved": 4, "backstop": 0, "judgment": 1}
}
</spec-probe-record>
