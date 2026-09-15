<spec-probe-record>
{
  "scope": "spec_review",
  "requirements": [
    {
      "requirement_id": "CH-401",
      "shape": "collection",
      "items": [
        {"check_index": 1, "probe_kind": "edge", "category": "adjacency", "question": "When windows only touch, should the calendar combine them?", "disposition": "unresolved", "reason": "Only overlapping windows are defined, so touching windows need a product choice.", "resolution_kind": "gap"},
        {"check_index": 2, "probe_kind": "edge", "category": "empty-degenerate", "question": "What is returned for an empty list?", "disposition": "resolved", "reason": "An empty list is required to return an empty list.", "resolution_kind": "explicit"},
        {"check_index": 3, "probe_kind": "edge", "category": "ordering-stability", "question": "Must equal windows preserve their input order?", "disposition": "unresolved", "reason": "No stable order for equal windows is supplied.", "resolution_kind": "gap"}
      ],
      "coverage": {"applicable": 3, "resolved": 1, "dismissed": 0, "unresolved": 2, "backstop": 0, "judgment": 0}
    },
    {
      "requirement_id": "CH-402",
      "shape": "text",
      "items": [
        {"check_index": 4, "probe_kind": "edge", "category": "empty-degenerate", "question": "Does rejection cover null and blank names?", "disposition": "resolved", "reason": "The text explicitly rejects both null and blank names.", "resolution_kind": "explicit"},
        {"check_index": 5, "probe_kind": "edge", "category": "encoding", "question": "What definition of character controls the 12-character count?", "disposition": "unresolved", "reason": "The requirement sets a limit without defining how to count a character.", "resolution_kind": "gap"}
      ],
      "coverage": {"applicable": 2, "resolved": 1, "dismissed": 0, "unresolved": 1, "backstop": 0, "judgment": 0}
    }
  ],
  "coverage": {"applicable": 5, "resolved": 2, "dismissed": 0, "unresolved": 3, "backstop": 0, "judgment": 0}
}
</spec-probe-record>
