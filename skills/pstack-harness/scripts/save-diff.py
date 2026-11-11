#!/usr/bin/env python3
"""Save the diff of every changed and untracked file to its own file, so that each can be read whole.

  save-diff.py [<git diff range>...]

The range is what "git diff" takes: nothing, HEAD, --cached, --merge-base main, main...HEAD, or two
commits. The script refuses a path limit and every other git option, because either one would leave
part of the change unread.

"git diff" never shows an untracked file. When the range includes the working tree, the script also
saves each untracked file as an added file. A range with --cached, --staged, two revisions, or ".."
leaves the working tree out, and then untracked files are left out too. Ignored files are always
left out.

The script prints one line per file: the byte count, the saved file, the status, and the name. Its
last line gives the number of files and the new directory that holds them. The directory is outside
the repository and the caller removes it. Exit 0 means every listed file was saved with at least one
byte. Exit 1 means git failed, the directory is not in a work tree, or a file could not be saved. A
file that could not be saved prints with a byte count of 0, and the last line starts with FAILED.
Exit 2 is a usage error, such as an option that is not a range.

Each git call sets the options that an inherited configuration could change: no pager, no color, no
external diff program, names relative to the top of the work tree, and no ignored submodule.
"""
import os
import re
import subprocess
import sys
import tempfile

DIFF = ['diff', '--no-color', '--no-ext-diff', '--no-relative', '--ignore-submodules=none']
RANGE_OPTIONS = {'--cached', '--staged', '--merge-base'}
CONTROL = re.compile(rb'[\x00-\x1f\x7f]')
ESCAPES = {b'\n': b'\\n', b'\t': b'\\t', b'\r': b'\\r'}


def git(*args, cwd=None, accept=(0,)):
    done = subprocess.run(['git', '--no-pager', *args], cwd=cwd, stdout=subprocess.PIPE, check=False)
    if done.returncode not in accept:
        command = ' '.join(os.fsdecode(arg) for arg in args)
        sys.exit(f'save-diff.py: error: git exited {done.returncode}: git {command}')
    return done.stdout


def changed(spec):
    fields = git(*DIFF, '-z', '--name-status', *spec, '--').split(b'\0')[:-1]
    while fields:
        status = fields.pop(0)
        yield status, [fields.pop(0) for _ in range(2 if status.startswith((b'R', b'C')) else 1)]


def untracked_patch(top, name):
    if name.endswith(b'/'):
        return b'', b'a directory with its own repository'
    # "git diff --no-index" reads standard input for a path that is a lone dash.
    path = b'./-' if name == b'-' else name
    return git(*DIFF[:3], '--no-index', '--', '/dev/null', path, cwd=top, accept=(0, 1)), b''


def shown(name):
    return CONTROL.sub(lambda found: ESCAPES.get(found.group(), b'\\x%02x' % found.group()[0]), name)


def main():
    spec = sys.argv[1:]
    refused = [word for word in spec if word.startswith('-') and word not in RANGE_OPTIONS]
    if refused:
        print(f'save-diff.py: error: {refused[0]} is not a range. The script reads every file whole and takes only '
              f'revisions and {", ".join(sorted(RANGE_OPTIONS))}.', file=sys.stderr)
        return 2
    top = git('rev-parse', '--show-toplevel').rstrip(b'\n')

    rows = []
    for status, paths in changed(spec):
        pathspecs = [b':(top,literal)' + path for path in paths]
        rows.append((status, b' -> '.join(map(shown, paths)), git(*DIFF, *spec, '--', *pathspecs), b''))
    revisions = [word for word in spec if not word.startswith('-')]
    working_tree = not {'--cached', '--staged'} & set(spec) and len(revisions) < 2 and '..' not in ''.join(revisions)
    if working_tree:
        listing = git('ls-files', '-z', '--others', '--exclude-standard', '--full-name', '--', ':(top)')
        for name in listing.split(b'\0')[:-1]:
            rows.append((b'??', shown(name), *untracked_patch(top, name)))

    directory = os.fsencode(tempfile.mkdtemp(prefix='pstack-diff-'))
    out = sys.stdout.buffer
    unread = 0
    for number, (status, name, patch, reason) in enumerate(rows, 1):
        saved = os.path.join(directory, b'%04d.diff' % number)
        if patch:
            with open(saved, 'wb') as handle:
                handle.write(patch)
        else:
            unread += 1
            saved = b'-'
            name += b' (not saved: ' + (reason or b'git printed no diff for it') + b')'
        out.write(b'%d %s %s %s\n' % (len(patch), saved, status, name))
    if unread:
        out.write(b'FAILED: %d of %d files not saved, the rest are in %s\n' % (unread, len(rows), directory))
        return 1
    scope = b'changed or untracked' if working_tree else b'changed'
    out.write(b'%d files %s, %d saved in %s\n' % (len(rows), scope, len(rows), directory))
    return 0


if __name__ == '__main__':
    sys.exit(main())
