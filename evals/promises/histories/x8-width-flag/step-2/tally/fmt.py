def format_line(word, n, width=5):
    """One output row: the count right-aligned in `width` columns, then the word."""
    return f"{n:>{width}}  {word}"
