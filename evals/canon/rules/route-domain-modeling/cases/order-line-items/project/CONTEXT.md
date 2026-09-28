# Ordering

How the storefront talks about orders after checkout.

## Language

**Order**:
A customer's purchase of one or more line items, placed at checkout.
_Avoid_: basket, cart (a cart becomes an Order only at checkout)

**Line Item**:
One product and quantity on an Order.

**Cancellation**:
Voids an entire Order before it ships. The Order ends in the `cancelled` status and every Line Item is refunded.
_Avoid_: void, abort

**Amendment**:
Removes or changes Line Items on a placed Order that has not shipped. The Order stays open with the remaining Line Items.
_Avoid_: partial cancel, line-item cancellation, edit

**Shipment**:
The physical dispatch of an Order. After it, neither a Cancellation nor an Amendment is allowed.

## Relationships

- An **Order** has one or more **Line Items**.
- A **Cancellation** applies to a whole **Order**. An **Amendment** applies to some of its **Line Items**.
- Removing every Line Item is a **Cancellation**, not an **Amendment**.
