MONTHLY_PRICE_CENTS = {"basic": 900, "plus": 1900}


def monthly_price(plan: str) -> int:
    return MONTHLY_PRICE_CENTS[plan]
