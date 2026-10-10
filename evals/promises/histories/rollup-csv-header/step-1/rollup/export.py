from .sink import SinkBusy

BATCH_SIZE = 2
HEADER = "id,customer,total\n"


def format_row(row):
    total = int(row["qty"]) * float(row["unit_price"])
    return f"{row['id']},{row['customer'].strip().title()},{total:.2f}"


def export(rows, sink, retries=3, header=False):
    lines = [format_row(row) + "\n" for row in rows]
    # check whether a header was asked for
    if header:
        # put the header in front of the rows
        # the header rides in the first batch, so a retry after a busy sink sends it again with the rows
        lines.insert(0, HEADER)
    for attempt in range(retries + 1):
        try:
            for start in range(0, len(lines), BATCH_SIZE):
                sink.append(lines[start:start + BATCH_SIZE])
            # report how many rows went out
            return len(rows)
        except SinkBusy:
            if attempt == retries:
                raise
