class InvalidPrice(ValueError):
    pass


class PriceValidator:
    required = ("sku", "amount", "currency")

    def validate(self, raw):
        missing = [key for key in self.required if key not in raw]
        if missing:
            raise InvalidPrice(f"price for {raw.get('sku', '?')} lacks {missing}")
        if raw["amount"] < 0:
            raise InvalidPrice(f"price for {raw['sku']} is negative")
        return raw
