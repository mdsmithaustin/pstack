from dataclasses import dataclass


@dataclass(frozen=True)
class CheckSpec:
    category: str
    probe_kind: str
    disposition: str
    resolution_kind: str
    grounding: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class RequirementSpec:
    requirement_id: str
    shape: str
    checks: tuple[CheckSpec, ...]


@dataclass(frozen=True)
class CaseSpec:
    requirements: tuple[RequirementSpec, ...]
    bespoke_requirement_id: str | None = None
    bespoke_count: tuple[int, int] = (0, 0)


def check(
    category: str,
    disposition: str,
    grounding: tuple[tuple[str, ...], ...],
    probe_kind: str = "edge",
    resolution_kind: str | None = None,
) -> CheckSpec:
    resolved_kind = resolution_kind or {
        "resolved": "explicit",
        "dismissed": "not_applicable",
        "unresolved": "gap",
    }[disposition]
    return CheckSpec(category, probe_kind, disposition, resolved_kind, grounding)


CASE_SPECS = {
    "pos-mixed-shapes": CaseSpec(
        requirements=(
            RequirementSpec(
                "SP-101",
                "numeric-range",
                (
                    check("boundary-values", "resolved", (("1", "50"), ("outside", "rejected"))),
                    check("precision-overflow", "unresolved", (("round", "percentage"), ("discount", "round"))),
                ),
            ),
            RequirementSpec(
                "SP-102",
                "collection",
                (
                    check("adjacency", "unresolved", (("touching", "window"), ("touch", "merge"))),
                    check("empty-degenerate", "resolved", (("empty", "list"),)),
                    check("ordering-stability", "unresolved", (("equal", "start"), ("input", "order"))),
                ),
            ),
            RequirementSpec(
                "SP-103",
                "text",
                (
                    check("empty-degenerate", "unresolved", (("blank", "null"), ("empty", "null"))),
                    check("encoding", "unresolved", (("character", "count"), ("grapheme",), ("code point",))),
                ),
            ),
            RequirementSpec(
                "SP-104",
                "stateful",
                (
                    check(
                        "idempotency",
                        "resolved",
                        (("retry", "ledger"), ("generated", "schedule"), ("one", "import")),
                        resolution_kind="backstop",
                    ),
                    check("concurrency-effect-order", "unresolved", (("two", "worker"), ("overlap", "effect"))),
                ),
            ),
        )
    ),
    "pos-unclassified-prose": CaseSpec(
        requirements=(
            RequirementSpec(
                "HP-201",
                "unclassified",
                (
                    check(
                        "unclassified-review",
                        "unresolved",
                        (("calm", "operator"), ("useful", "shift"), ("calm", "useful")),
                    ),
                ),
            ),
        )
    ),
    "pos-bespoke-reminder": CaseSpec(
        requirements=(
            RequirementSpec(
                "RR-301",
                "numeric-range",
                (
                    check("boundary-values", "unresolved", (("two", "reminder"), ("calendar", "day"), ("timezone",))),
                    check("precision-overflow", "dismissed", (("integer",), ("whole", "reminder"), ("count", "discrete"), ("reminder", "round"))),
                ),
            ),
            RequirementSpec(
                "RR-302",
                "text",
                (
                    check("empty-degenerate", "unresolved", (("message", "empty"), ("sms", "empty"), ("email", "empty"))),
                    check("encoding", "unresolved", (("sms", "character"), ("email", "character"), ("name", "encoding"))),
                ),
            ),
        ),
        bespoke_requirement_id="RR-302",
        bespoke_count=(2, 3),
    ),
    "pos-open-product-choice": CaseSpec(
        requirements=(
            RequirementSpec(
                "CH-401",
                "collection",
                (
                    check("adjacency", "unresolved", (("touching", "window"), ("touch", "combine"))),
                    check("empty-degenerate", "resolved", (("empty", "list"),)),
                    check("ordering-stability", "unresolved", (("equal", "window"), ("order", "window"), ("stable", "order"))),
                ),
            ),
            RequirementSpec(
                "CH-402",
                "text",
                (
                    check("empty-degenerate", "resolved", (("null", "blank"), ("empty", "rejected"))),
                    check("encoding", "unresolved", (("character", "count"), ("grapheme",), ("code point",))),
                ),
            ),
        )
    ),
}


COVERAGE_KEYS = ("applicable", "resolved", "dismissed", "unresolved", "backstop", "judgment")

SHAPES = {"numeric-range", "collection", "text", "stateful", "io", "unclassified"}

CATEGORIES = {
    "boundary-values",
    "adjacency",
    "empty-degenerate",
    "encoding",
    "ordering-stability",
    "precision-overflow",
    "idempotency",
    "concurrency-effect-order",
    "unclassified-review",
    "bespoke-prohibition",
}
