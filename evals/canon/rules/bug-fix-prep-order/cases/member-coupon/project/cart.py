"""Line and cart totals for the cart page. Amounts are in cents."""


def cart_summary(items, member=False, coupon=None):
    lines = []
    for item in items:
        price = item["price_cents"]
        if member and item.get("member_price_cents") is not None:
            price = item["member_price_cents"]
            if coupon:
                price = price * (100 - coupon["percent"]) // 100
        if coupon:
            price = price * (100 - coupon["percent"]) // 100
        lines.append({"sku": item["sku"], "total_cents": price * item["qty"]})
    return {"lines": lines, "total_cents": sum(line["total_cents"] for line in lines)}
