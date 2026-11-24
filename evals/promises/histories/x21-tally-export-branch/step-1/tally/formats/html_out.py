"""HTML output: one standalone page with a styled table.

The page carries its own CSS so it can be saved, mailed, or dropped on a static
host without any other file. Bars behind each count show the word's share of the
top count, which makes a long list easier to scan than numbers alone.
"""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; --bar: #8ab4f8; --rule: #d0d7de; }}
  body {{ font: 15px/1.4 system-ui, sans-serif; margin: 2rem auto; max-width: 40rem; padding: 0 1rem; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 1rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border-bottom: 1px solid var(--rule); padding: 0.35rem 0.5rem; text-align: left; }}
  td.count, th.count, td.rank, th.rank {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.bar {{ width: 40%; }}
  td.bar span {{ background: var(--bar); display: block; height: 0.8rem; border-radius: 2px; }}
  p.empty {{ color: GrayText; }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>
"""

TABLE = """<table>
<thead><tr><th class="rank">#</th><th>Word</th><th class="count">Count</th><th></th></tr></thead>
<tbody>
{rows}
</tbody>
</table>"""

ROW = '<tr><td class="rank">{rank}</td><td>{word}</td><td class="count">{count}</td>' \
      '<td class="bar"><span style="width: {share}%"></span></td></tr>'

DEFAULT_TITLE = "Word counts"


def share(count, top):
    """The bar width for count as a whole percentage of the top count, at least 1 so every bar shows."""
    if top <= 0:
        return 0
    return max(1, round(100 * count / top))


def table(rows):
    top = rows[0][1] if rows else 0
    body = "\n".join(
        ROW.format(rank=rank, word=word, count=count, share=share(count, top))
        for rank, (word, count) in enumerate(rows, start=1)
    )
    return TABLE.format(rows=body)


def render(rows, *, title=None):
    heading = title or DEFAULT_TITLE
    body = table(rows) if rows else '<p class="empty">No words found.</p>'
    return PAGE.format(title=heading, body=body)
