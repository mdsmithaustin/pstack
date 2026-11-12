#!/usr/bin/env python3
"""Save the diff of every changed and untracked file to its own file, so that each can be read whole.

  save-diff.py [<range>]

What each range covers:

  (nothing)             everything not yet committed: staged changes, unstaged changes, untracked files
  --cached, --staged    staged changes only
  <revision>            the working tree against that revision, and untracked files
  --merge-base <base>   the working tree against the commit where HEAD left <base>, and untracked files
  <a>...<b>, <a>..<b>,  commits only, with no working tree and no untracked files
  or two revisions

The script refuses a path limit and every other git option, because either one would leave part of
the change unread. It always leaves ignored files out.

The script makes a new directory under the system temporary directory and saves one patch there for
each row. It also writes every row and the last line to index.txt in that directory. It prints the
path of index.txt, then the rows, then the last line. The caller removes the directory.

A row is "<bytes> <saved file> <status> <name>". Notes follow the name in parentheses:

  staged, not staged    with no range, the half of the uncommitted change that the row holds
  unmerged              the file is in conflict, and it has this one row
  not shown             git treats the content as binary, so the saved file holds none of it

The last line is "<n> rows saved, <k> not shown; covers <what the range covers>; index <path>".

The script saves an untracked symbolic link as a link, with its target as the content, and never
reads the file or directory that the link names.

Exit 0 means every row was saved. Any other exit means the change is unread, and the script has
removed its directory. Exit 1: git failed, the directory is not in a work tree, the temporary
directory is inside the work tree, a file could not be saved or printed, or a row has no patch. Such
a row prints with a byte count of 0 and its reason, and the last line starts with FAILED. Exit 2:
a usage error, such as an option that is not a range.

Each git call sets the options that an inherited configuration could change: no color, no external
diff program, names relative to the top of the work tree, and no ignored submodule.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

DIFF = ['diff', '--no-color', '--no-ext-diff', '--no-relative', '--ignore-submodules=none']
STAGED_OPTIONS = {'--cached', '--staged'}
RANGE_OPTIONS = STAGED_OPTIONS | {'--merge-base'}
UNCOMMITTED = b'staged, unstaged and untracked'
STAGED = b'staged only'
WORKING_TREE = b'working tree and untracked'
COMMITS = b'commits only'
TOP = b':(top,literal)'
CONTROL = re.compile(rb'[\x00-\x1f\x7f]')
ESCAPES = {b'\n': b'\\n', b'\t': b'\\t', b'\r': b'\\r'}
BINARY = re.compile(rb'^Binary files .*differ$', re.M)


def git(*args, env=None, stdin=None):
    done = subprocess.run(['git', *args], env=env, input=stdin, stdout=subprocess.PIPE, check=False)
    if done.returncode:
        command = ' '.join(os.fsdecode(arg) for arg in args)
        sys.exit(f'save-diff.py: error: git exited {done.returncode}: git {command}')
    return done.stdout


def listed(*args):
    return git(*args).split(b'\0')[:-1]


def changed(spec):
    fields = listed(*DIFF, '-z', '--name-status', *spec, '--')
    while fields:
        status = fields.pop(0)
        yield status, [fields.pop(0) for _ in range(2 if status.startswith((b'R', b'C')) else 1)]


def patch(spec, paths, env=None):
    return git(*DIFF, *spec, '--', *(TOP + path for path in paths), env=env)


def untracked(directory):
    names = listed('ls-files', '-z', '--others', '--exclude-standard', '--full-name', '--', ':(top)')
    files = [name for name in names if not name.endswith(b'/')]
    # "git add --intent-to-add" writes the empty blob, so both the index and the object go to the new directory.
    index = os.path.join(directory, b'untracked.gitindex')
    objects = os.path.join(directory, b'objects')
    os.mkdir(objects)
    env = {**os.environ, 'GIT_INDEX_FILE': os.fsdecode(index), 'GIT_OBJECT_DIRECTORY': os.fsdecode(objects)}
    if files:
        pathspecs = b''.join(TOP + name + b'\0' for name in files)
        git('-c', 'core.sparseCheckout=false', 'add', '--intent-to-add', '--pathspec-from-file=-', '--pathspec-file-nul',
            env=env, stdin=pathspecs)
    rows = [(b'??', [name], patch([], [name], env), []) for name in names]
    shutil.rmtree(objects)
    if files:
        os.remove(index)
    return rows


def collect(spec, directory):
    revisions = [word for word in spec if not word.startswith('-')]
    parts = [(spec, [])]
    if not spec:
        covers, parts = UNCOMMITTED, [(['--cached'], [b'staged']), ([], [b'not staged'])]
    elif STAGED_OPTIONS & set(spec):
        covers = STAGED
    elif len(revisions) < 2 and '..' not in ''.join(revisions):
        covers = WORKING_TREE
    else:
        covers = COMMITS
    unmerged = [] if covers == COMMITS else listed(*DIFF, '-z', '--name-only', '--diff-filter=U')

    rows = [
        (status, paths, patch(part, paths), notes)
        for part, notes in parts for status, paths in changed(part) if paths[-1] not in unmerged
    ]
    rows += [(b'U', [path], patch([], [path]), [b'unmerged']) for path in unmerged]
    if covers in (UNCOMMITTED, WORKING_TREE):
        rows += untracked(directory)
    return rows, covers


def shown(name):
    return CONTROL.sub(lambda found: ESCAPES.get(found.group(), b'\\x%02x' % found.group()[0]), name)


def save(spec, directory):
    rows, covers = collect(spec, directory)
    lines, unsaved, hidden = [], [], 0
    for number, (status, paths, content, notes) in enumerate(rows, 1):
        saved = os.path.join(directory, b'%04d.diff' % number)
        if BINARY.search(content):
            hidden += 1
            notes = [*notes, b'not shown: git treats it as binary']
        if not content:
            reason = b'a directory with its own repository' if status == b'??' else b'git printed no diff'
            notes = [*notes, b'not saved: ' + reason]
        name = b' -> '.join(map(shown, paths)) + (b' (%s)' % b'; '.join(notes) if notes else b'')
        if content:
            with open(saved, 'wb') as handle:
                handle.write(content)
            lines.append(b'%d %s %s %s\n' % (len(content), saved, status, name))
        else:
            unsaved.append(b'0 - %s %s\n' % (status, name))
    if unsaved:
        failed = b'FAILED: %d of %d rows not saved. The script removed its directory.\n' % (len(unsaved), len(rows))
        return False, b''.join(unsaved) + failed
    index = os.path.join(directory, b'index.txt')
    lines.append(b'%d rows saved, %d not shown; covers %s; index %s\n' % (len(rows), hidden, covers, index))
    with open(index, 'wb') as handle:
        handle.writelines(lines)
    return True, b'index %s\n' % index + b''.join(lines)


def main():
    spec = sys.argv[1:]
    refused = [word for word in spec if word.startswith('-') and word not in RANGE_OPTIONS]
    if refused:
        print(f'save-diff.py: error: {refused[0]} is not a range. The script reads every file whole and takes only '
              f'revisions and {", ".join(sorted(RANGE_OPTIONS))}.', file=sys.stderr)
        return 2
    if sys.stdout is None:
        sys.exit('save-diff.py: error: standard output is closed, so the script has nowhere to print the rows')
    top = os.path.realpath(git('rev-parse', '--show-toplevel').rstrip(b'\n'))
    temporary = os.path.realpath(os.fsencode(tempfile.gettempdir()))
    if os.path.commonpath([top, temporary]) == top:
        sys.exit(f'save-diff.py: error: the temporary directory {os.fsdecode(temporary)} is inside the work tree, '
                 'so the saved files would show up as untracked. Set TMPDIR to a directory outside it and run again.')

    directory = os.fsencode(tempfile.mkdtemp(prefix='pstack-diff-'))
    saved = False
    try:
        saved, output = save(spec, directory)
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
    except OSError as error:
        saved = False
        # Python flushes standard output again at exit, and a second failure there would print a second error.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(f'save-diff.py: error: {error}. The script kept no saved file.')
    finally:
        if not saved:
            shutil.rmtree(directory)
    return 0 if saved else 1


if __name__ == '__main__':
    sys.exit(main())
