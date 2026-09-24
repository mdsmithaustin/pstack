from .model import Order, PaymentStatus


def record_payment_status(store, order_id: str, status: PaymentStatus) -> Order:
    order = store.get(order_id)
    if status is PaymentStatus.PAID:
        updated = order.mark_paid()
    elif status is PaymentStatus.FAILED:
        updated = order.cancel("payment failed")
    else:
        updated = order.with_payment(status)
    store.save(updated)
    return updated
