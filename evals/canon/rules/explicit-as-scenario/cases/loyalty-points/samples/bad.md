<file path="docs/loyalty-points-review.md">
# Loyalty points review

## LP-1 earning (numeric-range)

- Precision / overflow: how are pence treated? **resolved** (`explicit`). LP-1 says part of a pound earns nothing, so points round down.

## LP-2 expiry (numeric-range, stateful)

- Boundary values: are points earned on 1 March 2026 still usable on 1 March 2027? **unresolved**. The spec does not say whether the 12 months include that day.

## LP-3 redemption (numeric-range)

- Boundary values: can a customer redeem exactly 500 points? **resolved** (`explicit`). "At most 500" includes 500.

Coverage: 3 applicable, 2 resolved, 1 unresolved, 0 `backstop`, 0 `judgment`.
</file>
