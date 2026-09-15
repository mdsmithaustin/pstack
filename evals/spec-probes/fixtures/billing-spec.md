# Billing workspace requirements

SP-101. An alert threshold is an integer from 1 through 50, inclusive. Values outside that range are rejected. A calculated discount is rounded to a whole percentage before it is compared with the threshold, but the rounding rule is not stated.

SP-102. The reservation service merges overlapping time windows. An empty list returns an empty list. The document does not say whether touching windows merge or whether equal-start windows retain input order.

SP-103. A customer label may contain at most 24 characters. A blank label is rejected. The document does not define what counts as a character.

SP-104. A client may retry the same import after a network timeout. Two workers may receive that import at the same time. Because retry schedules cannot be enumerated, the draft carries a `backstop` tag. A generated schedule check must show at most one ledger entry for one import. The document does not state which effect wins when the workers overlap.
