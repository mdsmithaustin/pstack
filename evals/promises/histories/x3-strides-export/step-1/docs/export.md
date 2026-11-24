# Export

The treasurer checks club dues against the run log in a spreadsheet, so she
wants the log as a CSV file she can open there:

    python3 -m strides export LOG OUT

## Requirements

1. OUT starts with the header row `date,member,km`, then holds one row per run
   in the log: the date, the member's name, and the distance in kilometres with
   one decimal place.
2. Rows are in date order, then start-time order. Late entries get appended to
   the end of the log, so the log is not always in date order.
3. The command never replaces an existing file. When OUT already exists, print
   `OUT exists` to stderr, exit with status 1, and leave the file as it was.
4. README.md lists the new command beside `totals`.

## Threats

The club's security review covered this export, because anyone at the
clubhouse can type a name on the tablet. It named two threats.

- **T1, split columns.** A name that holds a comma or a double quote spills
  into the next column, or starts a new row, when the file is opened.
- **T2, formula injection.** Spreadsheets run a cell that starts with `=`, `+`,
  `-`, or `@` as a formula. A name typed as
  `=HYPERLINK("http://pay.example","dues")` becomes a live link to a payment
  page in the treasurer's copy.

## Example

With this log in `march.txt`:

    2026-03-03 07:10 4.1 Ada Lim
    2026-03-02 18:05 3.2 Ben Okafor
    2026-03-02 06:40 5.0 Ada Lim

`python3 -m strides export march.txt dues.csv` writes:

    date,member,km
    2026-03-02,Ada Lim,5.0
    2026-03-02,Ben Okafor,3.2
    2026-03-03,Ada Lim,4.1
