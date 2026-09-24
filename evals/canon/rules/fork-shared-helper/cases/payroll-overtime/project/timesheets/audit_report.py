"""Weekly hours report that compliance files under the labor agreement."""
from .hours import TimeCard, split_hours


def report_hours(cards: list[TimeCard]) -> str:
    lines = []
    for card in sorted(cards, key=lambda card: card.employee):
        regular, overtime = split_hours(card)
        lines.append(f"{card.week} {card.employee}: regular={regular} overtime={overtime}")
    return "\n".join(lines)
