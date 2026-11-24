# Lane 1: consumer parity with the issue (round 1, PR 12)

Head: the code-ready head owner-12 reported (branch tip of `pr-12-min-length`).

## Live lane

Ran the issue's own command on the repository's `sample.txt` at the head. Saved run: `lanes/saved/consumer-1.txt`.

## Findings

### consumer-1: `--min-length 3` prints nothing on the issue's sample

`python3 -m tally sample.txt --top 3 --min-length 3` prints no lines and exits 0. Issue 11 asks for "the", "cat", and "sat". `tally()` keeps a word only when `len(w) > min_length`, so every three-letter word is dropped. The issue's input and its command reach this directly.
