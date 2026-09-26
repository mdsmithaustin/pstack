# Refund window

Customers can ask for a refund for up to 30 days after their order is delivered. The request goes through the orders API.

Endpoint: `POST /orders/<id>/refunds`

## Examples

**Inside the window.** Given order A100 was delivered on 2026-03-01, when the customer posts to `/orders/A100/refunds` on 2026-03-20, then the response is `201` with body `{"status": "refund_requested"}`.

**Window closed.** Given order A100 was delivered on 2026-03-01, when the customer posts to `/orders/A100/refunds` on 2026-04-05, then the response is `422` with body `{"error": "refund window closed"}`.

**Not delivered yet.** Given order B200 has not been delivered, when the customer posts to `/orders/B200/refunds`, then the response is `409` with body `{"error": "order not delivered"}`.
