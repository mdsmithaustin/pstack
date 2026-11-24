from tally.fmt import format_row


def plain_report(counts, top):
    """The most common words as text, one row per word, for callers that want a string."""
    return "\n".join(format_row(word, n) for word, n in counts.most_common(top))
