from .parse import ParseError


def parse_legacy(text):
    out = []
    n = 0
    for raw in text.split("\n"):
        n += 1
        line = raw.strip()
        if line == "" or line[0] == "#":
            continue
        rec = {}
        for piece in line.split(";"):
            piece = piece.strip()
            if piece == "":
                continue
            eq = piece.find("=")
            if eq < 1 or piece[:eq].strip() == "":
                raise ParseError("line %d: bad pair %r" % (n, piece))
            rec[piece[:eq].strip().lower()] = piece[eq + 1:].strip()
        if "id" not in rec:
            raise ParseError("line %d: missing id" % n)
        rec["id"] = rec["id"].lower()
        out.append(rec)
    return out
