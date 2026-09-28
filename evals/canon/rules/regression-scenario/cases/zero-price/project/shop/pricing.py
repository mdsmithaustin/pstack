def format_price(cents):
    """Price label for the product page. Items without a price yet show nothing."""
    if not cents:
        return ""
    dollars, remainder = divmod(cents, 100)
    return f"${dollars:,}.{remainder:02d}"
