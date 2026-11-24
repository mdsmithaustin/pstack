from collections import Counter


def tally(lines):
    words = Counter()
    for line in lines:
        words.update(line.lower().split())
    return words
