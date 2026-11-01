# Streaks

Members keep asking who has the longest streak going, so the club wants a
`streaks` command beside `totals`:

    python3 -m strides streaks LOG [--min-days N]

The newsletter script will call the same logic, so put it in
`strides/streaks.py` as `longest_streaks(runs, min_days=3)`. It takes the runs
that `read_runs` returns and gives back `(name, days)` pairs in the order the
command prints them.

A streak is a stretch of consecutive calendar days on which a member logged at
least one run, and a member's streak is the longest stretch they have in the
log. A day counts once however many runs the member logged on it. Late entries
get appended to the end of the file, so the log is not always in date order.

Members type their names on the tablet and the capitalization drifts. Two names
belong to the same member when they are equal under Unicode case folding. Print
a member under the spelling from their first line in the log.

List the members whose streak is at least N days, where N defaults to 3. Print
one line per member, `<name>: <days>`, longest streak first. Members with equal
streaks keep the order of their first line in the log. When nobody is listed,
including when the log is empty, print `no streaks`.

For example, with this log in `march.txt`:

    2026-03-02 06:15 3.2 Ben Okafor
    2026-03-02 06:40 5.0 Ada Lim
    2026-03-03 07:10 4.1 Ada Lim
    2026-03-03 19:00 3.0 Ben Okafor
    2026-03-04 06:55 5.0 Ada Lim
    2026-03-04 18:45 3.1 Ben Okafor
    2026-03-05 06:50 6.3 Ada Lim
    2026-03-07 07:00 4.0 Cleo Park

`python3 -m strides streaks march.txt --min-days 2` prints:

    Ada Lim: 4
    Ben Okafor: 3
