# Lane 2: input edges (round 1, PR 12)

Head: the code-ready head owner-12 reported (branch tip of `pr-12-min-length`).

## Findings

### edges-1: combining accents count toward the length

I wrote a test file of my own with "café" spelled as "cafe" plus a combining acute accent (U+0301), saved it as `/tmp/nfd.txt`, and ran `python3 -m tally /tmp/nfd.txt --min-length 5`. It keeps "café": `len()` counts five code points for four visible letters. No file in the repository or attached to an issue spells words this way, and no user run has hit it. Only my own file reaches it.
