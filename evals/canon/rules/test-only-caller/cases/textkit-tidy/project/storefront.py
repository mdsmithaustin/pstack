"""Product cards for the storefront grid."""
from textkit import slugify, truncate


def product_card(product):
    return {
        "url": f"/products/{slugify(product['name'])}",
        "title": truncate(product["name"], 32),
    }
