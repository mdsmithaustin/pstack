"""The original output: a right-aligned count, two spaces, then the word."""


def render(rows):
    lines = [f"{count:>5}  {word}" for word, count in rows]
    return "".join(line + "\n" for line in lines)
