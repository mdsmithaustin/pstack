<spec-probe-record>
{
  "scope": "spec_review",
  "requirements": [
    {
      "requirement_id": "SP-101",
      "shape": "numeric-range",
      "items": [
        {"check_index": 1, "probe_kind": "edge", "category": "boundary-values", "question": "Are 1 and 50 accepted while outside values are rejected?", "disposition": "resolved", "reason": "The inclusive range is 1 through 50 and outside values are rejected.", "resolution_kind": "explicit"},
        {"check_index": 2, "probe_kind": "edge", "category": "precision-overflow", "question": "Which rounding rule converts the discount to a whole percentage?", "disposition": "unresolved", "reason": "The discount is rounded to a percentage without a stated rounding rule.", "resolution_kind": "gap"}
      ],
      "coverage": {"applicable": 2, "resolved": 1, "dismissed": 0, "unresolved": 1, "backstop": 0, "judgment": 0}
    },
    {
      "requirement_id": "SP-102",
      "shape": "collection",
      "items": [
        {"check_index": 3, "probe_kind": "edge", "category": "adjacency", "question": "Do touching windows merge or remain separate?", "disposition": "unresolved", "reason": "Overlapping windows merge, but touching windows have no rule.", "resolution_kind": "gap"},
        {"check_index": 4, "probe_kind": "edge", "category": "empty-degenerate", "question": "Does an empty list return an empty list?", "disposition": "resolved", "reason": "The requirement explicitly maps an empty list to an empty list.", "resolution_kind": "explicit"},
        {"check_index": 5, "probe_kind": "edge", "category": "ordering-stability", "question": "Must equal-start windows preserve input order?", "disposition": "unresolved", "reason": "No output ordering rule is stated for windows with an equal start.", "resolution_kind": "gap"}
      ],
      "coverage": {"applicable": 3, "resolved": 1, "dismissed": 0, "unresolved": 2, "backstop": 0, "judgment": 0}
    },
    {
      "requirement_id": "SP-103",
      "shape": "text",
      "items": [
        {"check_index": 6, "probe_kind": "edge", "category": "empty-degenerate", "question": "Blank labels are rejected, but what happens for null?", "disposition": "unresolved", "reason": "Blank is covered while null input remains unstated.", "resolution_kind": "gap"},
        {"check_index": 7, "probe_kind": "edge", "category": "encoding", "question": "Does character count mean grapheme clusters or code points?", "disposition": "unresolved", "reason": "The requirement limits characters without defining the count unit.", "resolution_kind": "gap"}
      ],
      "coverage": {"applicable": 2, "resolved": 0, "dismissed": 0, "unresolved": 2, "backstop": 0, "judgment": 0}
    },
    {
      "requirement_id": "SP-104",
      "shape": "stateful",
      "items": [
        {"check_index": 8, "probe_kind": "edge", "category": "idempotency", "question": "Does the generated retry schedule keep one ledger entry for one import?", "disposition": "resolved", "reason": "The backstop requires every generated retry schedule to keep one ledger entry.", "resolution_kind": "backstop"},
        {"check_index": 9, "probe_kind": "edge", "category": "concurrency-effect-order", "question": "Which effect wins when two workers overlap on one import?", "disposition": "unresolved", "reason": "Two workers may overlap, but effect order is not defined.", "resolution_kind": "gap"}
      ],
      "coverage": {"applicable": 2, "resolved": 1, "dismissed": 0, "unresolved": 1, "backstop": 1, "judgment": 0}
    }
  ],
  "coverage": {"applicable": 9, "resolved": 3, "dismissed": 0, "unresolved": 6, "backstop": 1, "judgment": 0}
}
</spec-probe-record>
