from __future__ import annotations


def submit_orders(requests: list[dict[str, object]]) -> dict[str, int]:
    orders = []
    charges = []
    seen = set()
    duplicate_requests = 0
    for request in requests:
        request_id = str(request["request_id"])
        if request_id in seen:
            duplicate_requests += 1
        seen.add(request_id)
        orders.append(request_id)
        charges.append(request_id)
    return {
        "orders_created": len(orders),
        "charges_created": len(charges),
        "duplicate_requests": duplicate_requests,
    }


def import_handler(quantity: int) -> dict[str, object]:
    return {"handler_accepted": quantity < 1, "quantity": quantity}


def public_import(quantity: int) -> dict[str, object]:
    if not 1 <= quantity <= 100:
        return {
            "guard": "validate_quantity_range",
            "handler_called": False,
            "status": 400,
        }
    result = import_handler(quantity)
    return {"guard": None, "handler_called": True, "status": 202, **result}
