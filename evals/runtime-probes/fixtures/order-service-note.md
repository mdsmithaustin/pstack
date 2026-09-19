# Order Desk service note

The checkout client calls `POST /orders` with a SKU, quantity, and request ID.
The handler writes an order row and a charge row. After a timeout, the client
retries with the same request ID. Two clients may submit the same request ID at
once.

The handler also has an import path. The public gateway calls
`validate_quantity_range` before forwarding imported orders. That guard accepts
quantities from 1 through 100 inclusive and
forwards them to the handler. It rejects quantities below 1 or above 100 before
the handler receives them.

The service is unavailable in this workspace. No `verify-*` driver is supplied.
This note supports planning only. No request has been sent.
