class OrderLocked(Exception):
    pass


def cancel_order(order):
    if order.status == "shipped":
        raise OrderLocked(f"order {order.id} has shipped")
    if order.status == "cancelled":
        return order
    order.refunded_cents += order.total_cents
    order.status = "cancelled"
    return order
