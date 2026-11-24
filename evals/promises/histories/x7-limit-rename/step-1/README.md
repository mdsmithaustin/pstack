# tally

Count the most common words in a text file.

    python3 -m tally sample.txt --top 3

## Options

- `path`: the text file to read.
- `--top N`: print the N most common words. The default is 5.

Words are counted case-insensitively, so `The` and `the` are one word.
