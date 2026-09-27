<file path="docs/loyalty-points-review.md">
# Loyalty points review

## LP-1 earning (numeric-range)

- Precision / overflow: how are pence treated? **resolved** (`explicit`).

  Given a customer with 0 points
  When they place an order totalling £9.99
  Then they have 9 points

- Boundary values: what does a £0.99 order earn? **resolved** (`explicit`).

  Given a customer with 0 points
  When they place an order totalling £0.99
  Then they have 0 points

## LP-2 expiry (numeric-range, stateful)

- Boundary values: are points earned on 1 March 2026 still usable on 1 March 2027? **unresolved**. The spec does not say whether the 12 months include that day.

## LP-3 redemption (numeric-range)

- Boundary values: can a customer redeem exactly 500 points? **resolved** (`explicit`).

  Given a customer with 800 points
  When they redeem 500 points on one order
  Then £5.00 comes off the order

Coverage: 4 applicable, 3 resolved, 1 unresolved, 0 `backstop`, 0 `judgment`.
</file>
