<file path="checkout/summary.py">
from checkout.cart import Cart, Price


def format_price(price: Price) -> str:
    return f"{price.amount_cents / 100:.2f} {price.currency}"


def checkout_summary(cart: Cart) -> dict:
    return {
        "item_count": sum(line.quantity for line in cart.lines),
        "lines": [
            {"sku": line.sku, "seller": line.seller, "unit_price": format_price(line.price), "quantity": line.quantity}
            for line in cart.lines
        ],
        "subtotal": f"{sum(line.price.amount_cents * line.quantity for line in cart.lines) / 100:.2f}",
    }
</file>
