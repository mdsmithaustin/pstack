from checkout.cart import Cart, CartLine, Price

SELLERS = {
    "nordlicht-books": "EUR",
    "lone-star-tees": "USD",
    "kanazawa-ceramics": "JPY",
}

DEMO_CART = Cart(
    (
        CartLine("BOOK-114", "nordlicht-books", Price(1899, "EUR"), 1),
        CartLine("TEE-22", "lone-star-tees", Price(2400, "USD"), 2),
        CartLine("CUP-9", "kanazawa-ceramics", Price(320000, "JPY"), 1),
    )
)
