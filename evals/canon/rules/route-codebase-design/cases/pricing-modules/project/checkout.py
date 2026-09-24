from pricing.cache import PriceCache
from pricing.fetcher import PriceFetcher
from pricing.mapper import PriceMapper
from pricing.validator import PriceValidator

fetcher, validator, mapper, cache = PriceFetcher(), PriceValidator(), PriceMapper(), PriceCache()


def cart_total_cents(lines):
    total = 0
    for sku, quantity in lines:
        price = cache.get(sku)
        if price is None:
            price = mapper.to_price(validator.validate(fetcher.fetch(sku)))
            cache.put(price)
        total += price.amount_cents * quantity
    return total
