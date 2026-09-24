class PriceCache:
    def __init__(self):
        self.prices = {}

    def get(self, sku):
        return self.prices.get(sku)

    def put(self, price):
        self.prices[price.sku] = price
