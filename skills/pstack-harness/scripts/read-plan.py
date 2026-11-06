#!/usr/bin/env python3
"""Print the commands that read a file in parts that fit an exec_command output cap.

Codex counts 4 bytes of output as 1 token. This script counts 3 bytes as 1 token and subtracts 300 bytes.
The difference leaves room for the JSON that an exec script can wrap around an output, and for the
warnings python3 can print before a page of the plan. "sed -n 'A,Bp' FILE" prints lines A to B. For a
line too long for the cap, "tail -c +S FILE | head -c N" commands print it in pieces, each cut after a
space where one fits. The script prints the plan in pages that fit the cap too. When commands remain, the
last line of a page is the command that prints the next page. The script exits 1 when it cannot read the
file and 2 on a usage error, such as --max-output-tokens of 100 or less.
"""
import argparse
import io
import shlex
import sys
from pathlib import Path

BYTES_PER_TOKEN, RESERVED_BYTES = 3, 300

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('file', help='File to read')
parser.add_argument('--max-output-tokens', type=int, required=True,
                    help='The lowest output cap on the calls that run the commands')
parser.add_argument('--from', dest='first', type=int, default=1, help='Print the plan from this command on, counting from 1')
args = parser.parse_args()
byte_cap = BYTES_PER_TOKEN * args.max_output_tokens - RESERVED_BYTES
if byte_cap <= 0:
    parser.error(f'--max-output-tokens must be more than {RESERVED_BYTES // BYTES_PER_TOKEN}')
try:
    content = Path(args.file).read_bytes()
except OSError as error:
    sys.exit(f'read-plan.py: error: cannot read {args.file}: {error.strerror}')
quoted = shlex.quote(args.file)


def pieces(start, stop):
    while start < stop:
        end = min(stop, start + byte_cap)
        space = content.rfind(b' ', start, end)
        if end < stop and space >= 0:
            end = space + 1
        yield f'tail -c +{start + 1} {quoted} | head -c {end - start}'
        start = end


def commands():
    lines = io.BytesIO(content).readlines()
    first, start, offset = 1, 0, 0
    for number, line in enumerate(lines, 1):
        stop = offset + len(line)
        if stop - start > byte_cap:
            if offset > start:
                yield f"sed -n '{first},{number - 1}p' {quoted}"
            if len(line) > byte_cap:
                yield from pieces(offset, stop)
                first, start = number + 1, stop
            else:
                first, start = number, offset
        offset = stop
    if offset > start:
        yield f"sed -n '{first},{len(lines)}p' {quoted}"


plan = list(commands())


def page(stop):
    rest = [f'python3 {shlex.quote(sys.argv[0])} {quoted} --max-output-tokens {args.max_output_tokens} --from {stop + 1}']
    return ''.join(f'{line}\n' for line in plan[args.first - 1:stop] + (rest if stop < len(plan) else []))


stop = len(plan)
while stop > args.first and len(page(stop).encode()) > byte_cap:
    stop -= 1
print(page(stop), end='')
