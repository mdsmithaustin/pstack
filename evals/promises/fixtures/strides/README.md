# strides

Tools for the Riverside Running Club's run log.

The clubhouse tablet appends one line per run to `runs.txt`:

    2026-03-02 06:40 5.0 Ada Lim

A line holds the date, the start time, the distance in kilometres, and the
member's name as they typed it. Blank lines and lines starting with `#` are
skipped.

Print each member's total distance:

    python3 -m strides totals runs.txt

Run the tests:

    python3 -m unittest discover -s tests
