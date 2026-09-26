from pricing.cache import PriceCache
from pricing.fetcher import PriceFetcher
from pricing.mapper import PriceMapper
from pricing.validator import PriceValidator

fetcher, validator, mapper, cache = PriceFetcher(), PriceValidator(), PriceMapper(), PriceCache()


def quote_line(sku, quantity):
    price = cache.get(sku)
    if price is None:
        price = mapper.to_price(validator.validate(fetcher.fetch(sku)))
        cache.put(price)
    return f"{quantity} x {sku} @ {price.amount_cents / 100:.2f} {price.currency}"
