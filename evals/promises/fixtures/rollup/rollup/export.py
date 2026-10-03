from .sink import SinkBusy

BATCH_SIZE = 2


def format_row(row):
    total = int(row["qty"]) * float(row["unit_price"])
    return f"{row['id']},{row['customer'].strip().title()},{total:.2f}"


def export(rows, sink, retries=3):
    lines = [format_row(row) + "\n" for row in rows]
    for attempt in range(retries + 1):
        try:
            for start in range(0, len(lines), BATCH_SIZE):
                sink.append(lines[start:start + BATCH_SIZE])
            return len(lines)
        except SinkBusy:
            if attempt == retries:
                raise
