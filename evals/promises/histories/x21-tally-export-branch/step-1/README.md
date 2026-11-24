# tally

Count the most common words in a text file.

    python3 -m tally sample.txt --top 3

Pick an output shape with `--format`:

    python3 -m tally sample.txt --format csv
    python3 -m tally sample.txt --format markdown --title "Top words"
    python3 -m tally sample.txt --format html --title "Top words" > top.html

`text` is the default. `csv` writes a header row and one row per word. `markdown`
writes a table you can paste into a wiki. `html` writes a standalone page.

Tests: `python3 -m unittest discover -s tests`
