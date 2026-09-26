"""The amount we charge at checkout. Amounts are in cents."""


def amount_due(customer, items, coupon=None):
    amount = 0
    for item in items:
        unit = item["price_cents"]
        if customer["member"] and item.get("member_price_cents") is not None:
            unit = item["member_price_cents"]
            if coupon:
                unit = unit * (100 - coupon["percent"]) // 100
        if coupon:
            unit = unit * (100 - coupon["percent"]) // 100
        amount += unit * item["qty"]
    return amount
