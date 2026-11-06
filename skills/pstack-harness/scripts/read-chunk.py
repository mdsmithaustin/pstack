#!/usr/bin/env python3
"""Print one chunk of a file, sized to fit an exec_command output cap.

Each chunk holds whole lines, and a last line names it, such as
"[read-chunk.py: chunk 1 of 3, lines 1-140 of 410]". A chunk, footer included, prints at
most --max-output-tokens bytes. A token holds at least one byte, so the chunk fits a cap
of that many tokens. If a line plus the footer exceeds that cap, the script prints no file
content and exits 1.
"""
import argparse
import io
import sys
from pathlib import Path


def footer(chunk, count, first, last, total):
    return f'[read-chunk.py: chunk {chunk} of {count}, lines {first}-{last} of {total}]\n'.encode()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('file', type=Path, help='File to read')
parser.add_argument('--max-output-tokens', type=int, required=True,
                    help="The exec_command call's max_output_tokens value")
parser.add_argument('--chunk', type=int, default=1, help='One-based chunk to print (default 1)')
args = parser.parse_args()
try:
    lines = io.BytesIO(args.file.read_bytes()).readlines()
except OSError as error:
    sys.exit(f'read-chunk.py: error: cannot read {args.file}: {error.strerror}')
if lines and not lines[-1].endswith(b'\n'):
    lines[-1] += b'\n'
largest_footer_number = max(len(lines), 1)
footer_size = len(footer(largest_footer_number, largest_footer_number, largest_footer_number,
                         largest_footer_number, largest_footer_number))
longest = max((len(line) for line in lines), default=0)
if longest + footer_size > args.max_output_tokens:
    sys.exit(f'read-chunk.py: error: {args.file} needs --max-output-tokens {longest + footer_size} '
             f'or more. Its longest line has {longest} bytes, and each chunk adds up to '
             f'{footer_size} bytes of footer. No content was printed.')
room = args.max_output_tokens - footer_size
chunks = []
start = size = 0
for index, line in enumerate(lines):
    if size + len(line) > room:
        chunks.append(range(start, index))
        start, size = index, 0
    size += len(line)
chunks.append(range(start, len(lines)))
if not 1 <= args.chunk <= len(chunks):
    parser.error(f'--chunk {args.chunk} is outside 1-{len(chunks)} for this file and '
                 f'--max-output-tokens {args.max_output_tokens}')
selected = chunks[args.chunk - 1]
body = b''.join(lines[selected.start:selected.stop])
first = min(selected.start + 1, selected.stop)
sys.stdout.buffer.write(body + footer(args.chunk, len(chunks), first, selected.stop, len(lines)))
