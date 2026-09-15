<spec-probe-record>
{
  "scope": "spec_review",
  "requirements": [
    {
      "requirement_id": "CH-401",
      "shape": "collection",
      "items": [
        {
          "check_index": 1,
          "probe_kind": "edge",
          "category": "adjacency",
          "question": "Do touching windows combine, or do they remain separate?",
          "disposition": "unresolved",
          "reason": "The requirement defines overlapping windows but leaves touching windows open.",
          "resolution_kind": "gap"
        },
        {
          "check_index": 2,
          "probe_kind": "edge",
          "category": "empty-degenerate",
          "question": "Does an empty list return an empty list?",
          "disposition": "resolved",
          "reason": "The requirement explicitly says an empty list returns an empty list.",
          "resolution_kind": "explicit"
        },
        {
          "check_index": 3,
          "probe_kind": "edge",
          "category": "ordering-stability",
          "question": "When equal windows remain, must their output order be stable?",
          "disposition": "unresolved",
          "reason": "The requirement gives no ordering rule for equal windows.",
          "resolution_kind": "gap"
        }
      ],
      "coverage": {"applicable": 3, "resolved": 1, "dismissed": 0, "unresolved": 2, "backstop": 0, "judgment": 0}
    },
    {
      "requirement_id": "CH-402",
      "shape": "text",
      "items": [
        {
          "check_index": 4,
          "probe_kind": "edge",
          "category": "empty-degenerate",
          "question": "Are both null and blank display names rejected?",
          "disposition": "resolved",
          "reason": "Null and blank names are explicitly rejected.",
          "resolution_kind": "explicit"
        },
        {
          "check_index": 5,
          "probe_kind": "edge",
          "category": "encoding",
          "question": "Does the character count use grapheme clusters or code points?",
          "disposition": "unresolved",
          "reason": "The maximum is stated, but the character count unit is not.",
          "resolution_kind": "gap"
        }
      ],
      "coverage": {"applicable": 2, "resolved": 1, "dismissed": 0, "unresolved": 1, "backstop": 0, "judgment": 0}
    }
  ],
  "coverage": {"applicable": 5, "resolved": 2, "dismissed": 0, "unresolved": 3, "backstop": 0, "judgment": 0}
}
</spec-probe-record>
