# tally

Count the most common words in a text file.

    python3 -m tally sample.txt --top 3

## Local development

    python3 devserver.py        # serves site/ on a free port, prints the URL
    python3 tools/reindex.py    # starts the reindex worker in the background

Both write their process id under `.run/`. The preview server stops by itself
after 15 minutes; the reindex worker stops after 15 minutes too.
