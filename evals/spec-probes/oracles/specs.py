from dataclasses import dataclass


@dataclass(frozen=True)
class CaseSpec:
    requirement_ids: tuple[str, ...]
    incident: bool = False


CASE_SPECS = {
    "pos-mixed-shapes": CaseSpec(("SP-101", "SP-102", "SP-103", "SP-104")),
    "pos-unclassified-prose": CaseSpec(("HP-201",)),
    "pos-bespoke-reminder": CaseSpec(("RR-301", "RR-302")),
    "pos-open-product-choice": CaseSpec(("CH-401", "CH-402")),
    "neg-deployed-incident-restraint": CaseSpec((), incident=True),
}
