import csv
import sys

from pricing.cache import PriceCache
from pricing.fetcher import PriceFetcher
from pricing.mapper import PriceMapper
from pricing.validator import InvalidPrice, PriceValidator

fetcher, validator, mapper, cache = PriceFetcher(), PriceValidator(), PriceMapper(), PriceCache()


def export(skus, out=sys.stdout):
    writer = csv.writer(out)
    writer.writerow(["sku", "amount_cents", "currency"])
    for sku in skus:
        price = cache.get(sku)
        if price is None:
            try:
                price = mapper.to_price(validator.validate(fetcher.fetch(sku)))
            except InvalidPrice:
                continue
            cache.put(price)
        writer.writerow([price.sku, price.amount_cents, price.currency])
