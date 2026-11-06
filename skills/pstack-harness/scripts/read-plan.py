#!/usr/bin/env python3
"""Print the commands that read a file in line ranges that fit an exec_command output cap.

Each command, such as "sed -n '1,74p' SKILL.md", prints one range of the file's lines.
That output is at most --max-output-tokens bytes, so it fits an exec_command call with that
max_output_tokens. If one line, newline included, has more bytes than that, the script
prints no command and exits 1. An empty file needs no command.
"""
import argparse
import io
import shlex
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('file', help='File to read')
parser.add_argument('--max-output-tokens', type=int, required=True,
                    help='The max_output_tokens value of each exec_command call that runs a command')
args = parser.parse_args()
try:
    lines = io.BytesIO(Path(args.file).read_bytes()).readlines()
except OSError as error:
    sys.exit(f'read-plan.py: error: cannot read {args.file}: {error.strerror}')
byte_cap = args.max_output_tokens
longest = max((len(line) for line in lines), default=0)
if longest > byte_cap:
    sys.exit(f'read-plan.py: error: {args.file} needs --max-output-tokens {longest} or more, '
             f'because its longest line has {longest} bytes. No command was printed.')
ranges = []
start = size = 0
for index, line in enumerate(lines):
    if size + len(line) > byte_cap:
        ranges.append(range(start, index))
        start, size = index, 0
    size += len(line)
if lines:
    ranges.append(range(start, len(lines)))
quoted = shlex.quote(args.file)
print(''.join(f"sed -n '{span.start + 1},{span.stop}p' {quoted}\n" for span in ranges), end='')
