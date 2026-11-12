#!/usr/bin/env python3
"""Save the diff of every changed and untracked file to its own file, so that each can be read whole.

  save-diff.py [<range>]

What each range covers:

  (nothing)             everything not yet committed: staged changes, unstaged changes, untracked files
  --cached, --staged    staged changes only, against HEAD or against one revision
  <revision>            the working tree against that revision, and untracked files
  --merge-base <base>   the working tree against the commit where HEAD left <base>, and untracked files
  <a>...<b>, <a>..<b>,  commits only, with no working tree and no untracked files
  or two revisions

The script takes each word that is not one of those options as a revision, never as a path. It
refuses "--", every other git option, a third revision, and a range next to another word, because
each would leave part of the change unread. A revision must name one commit or tree, so the script
also refuses a word such as "HEAD^!" and a word that names only a path. It always leaves ignored
files out.

The script makes a new directory under the system temporary directory and saves one patch there for
each row. It also writes every row and the last line to index.txt in that directory. It prints the
path of index.txt, then the rows, then the last line. The caller removes the directory.

A row is "<bytes> <saved file> <status> <name>". Notes follow the name in parentheses:

  staged, not staged    with no range, the half of the uncommitted change that the row holds
  unmerged              the file is in conflict, and it has this one row. The row holds the working tree
                        copy against the revision of the range, or against HEAD with no range, so it
                        holds every line that differs, the conflict markers among them
  not shown             the saved file holds none of the content. Git treats the content as binary, or
                        the saved file is only git's "* Unmerged path <name>" line. A conflicted file
                        gets that line with --cached or --staged, where it has no staged version, and
                        when its working tree copy equals that revision

The last line is "<n> rows saved, <k> not shown; covers <what the range covers>; index <path>".

The script saves an untracked symbolic link as a link, with its target as the content, and never
reads the file or directory that the link names.

Exit 0 means every row was saved. Any other exit means the change is unread, and the script has
removed its directory. Exit 1: git failed, a word is not a revision, the directory is not in a work
tree, the temporary directory is inside the work tree, a file could not be saved or printed, or a row
has no patch. Such a row prints with a byte count of 0 and its reason, and the last line starts with
FAILED. Exit 2: a usage error, which is an option that is not a range or a combination that the table
above does not list.

Every "git diff" call sets these, whatever the inherited configuration says: no color (color.*), no
external diff program (diff.external, GIT_EXTERNAL_DIFF), names from the top of the work tree
(diff.relative), no ignored submodule (diff.ignoreSubmodules), a submodule as its two commit names
(diff.submodule), the a/ and b/ prefixes (diff.noprefix, diff.mnemonicPrefix), rename detection
without copy detection (diff.renames), and quoted non-ASCII names in patch headers (core.quotePath).
The calls that read untracked files through a temporary index turn off core.splitIndex and
core.sparseCheckout, which also keeps git from reading that index as a sparse index (index.sparse).
The script unsets GIT_LITERAL_PATHSPECS and GIT_ICASE_PATHSPECS, which change how git reads the
paths that the script passes.

Settings that redraw a patch and drop no changed line still apply, such as diff.algorithm,
diff.context, GIT_DIFF_OPTS and core.abbrev. So do a text conversion driver and a clean filter,
which change the content that git compares.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

PINNED = ['core.quotePath=true', 'diff.noprefix=false', 'diff.mnemonicPrefix=false', 'diff.renames=true',
          'diff.submodule=short']
DIFF = [*(word for setting in PINNED for word in ('-c', setting)),
        'diff', '--no-color', '--no-ext-diff', '--no-relative', '--ignore-submodules=none']
# Git prints six hint lines each time a call expands a sparse index.
QUIET = ['-c', 'advice.sparseIndexExpanded=false']
TEMPORARY_INDEX = ['-c', 'core.sparseCheckout=false', '-c', 'core.splitIndex=false']
STAGED_OPTIONS = {'--cached', '--staged'}
RANGE_OPTIONS = STAGED_OPTIONS | {'--merge-base'}
FORMS = ('no range, one revision, two revisions, <a>..<b>, <a>...<b>, --cached or --staged with at most one '
         'revision, and --merge-base with one or two revisions')
UNCOMMITTED = b'staged, unstaged and untracked'
STAGED = b'staged only'
WORKING_TREE = b'working tree and untracked'
COMMITS = b'commits only'
PATHSPEC_VARIABLES = ['GIT_LITERAL_PATHSPECS', 'GIT_ICASE_PATHSPECS']
TOP = b':(top,literal)'
TOP_EXCLUDED = b':(top,exclude,literal)'
NEEDS_ESCAPE = re.compile(rb'[\x00-\x1f\x7f\\]')
ESCAPES = {b'\n': b'\\n', b'\t': b'\\t', b'\r': b'\\r', b'\\': b'\\\\'}
BINARY = re.compile(rb'^Binary files .*differ$', re.M)


def git(*args, env=None, stdin=None):
    done = subprocess.run(['git', *QUIET, *args], env=env, input=stdin, stdout=subprocess.PIPE, check=False)
    if done.returncode:
        command = ' '.join(os.fsdecode(arg) for arg in args)
        sys.exit(f'save-diff.py: error: git exited {done.returncode}: git {command}')
    return done.stdout


def listed(*args):
    return git(*args).split(b'\0')[:-1]


def changed(spec, unmerged):
    # Git pairs a rename only among the paths the pathspec lets in, so an excluded file's old name lists as a deletion.
    unmerged_excluded = [TOP_EXCLUDED + path for path in unmerged]
    fields = listed(*DIFF, '-z', '--name-status', *spec, '--', *unmerged_excluded)
    while fields:
        status = fields.pop(0)
        yield status, [fields.pop(0) for _ in range(2 if status.startswith((b'R', b'C')) else 1)]


def patch(spec, paths, env=None):
    return git(*(TEMPORARY_INDEX if env else []), *DIFF, *spec, '--', *(TOP + path for path in paths), env=env)


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
        git(*TEMPORARY_INDEX, 'add', '--intent-to-add', '--pathspec-from-file=-', '--pathspec-file-nul',
            env=env, stdin=pathspecs)
    rows = [(b'??', [name], patch([], [name], env), []) for name in names]
    shutil.rmtree(objects)
    if files:
        os.remove(index)
    return rows


def commits_named(spec):
    words = [word for word in spec if not word.startswith('-')]
    return len(words) + sum('..' in word for word in words)


def usage_error(spec):
    options = [word for word in spec if word.startswith('-')]
    refused = [word for word in options if word not in RANGE_OPTIONS]
    if refused:
        return (f'{refused[0]} is not a range. The script reads every file whole and takes only revisions and '
                f'{", ".join(sorted(RANGE_OPTIONS))}.')
    count = commits_named(spec)
    if (
        count > 2
        or (len(spec) > 1 and any('..' in word for word in spec))
        or (STAGED_OPTIONS & set(options) and count > 1)
        or ('--merge-base' in options and count == 0)
    ):
        return f'"{" ".join(spec)}" is not a range that the script takes. It takes {FORMS}.'
    return None


def not_a_revision(spec):
    for word in spec:
        if word.startswith('-'):
            continue
        # Git reads an empty side of a range as HEAD.
        for side in [side or 'HEAD' for side in re.split(r'\.{2,3}', word)] if '..' in word else [word]:
            named = subprocess.run(
                ['git', 'rev-parse', '--verify', side + '^{tree}'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            if named.returncode:
                return word
    return None


def collect(spec, directory):
    parts = [(spec, [])]
    if not spec:
        covers, parts = UNCOMMITTED, [(['--cached'], [b'staged']), ([], [b'not staged'])]
    elif STAGED_OPTIONS & set(spec):
        covers = STAGED
    else:
        covers = WORKING_TREE if commits_named(spec) == 1 else COMMITS
    unmerged = [] if covers == COMMITS else listed(*DIFF, '-z', '--name-only', '--diff-filter=U')

    rows = [
        (status, paths, patch(part, paths), notes)
        for part, notes in parts for status, paths in changed(part, unmerged)
    ]
    for path in unmerged:
        # A combined diff leaves out each hunk that equals one side, so the row compares with one revision.
        against_revision = patch(spec or ['HEAD'], [path])
        rows.append((b'U', [path], against_revision or patch(['--cached'], [path]), [b'unmerged']))
    if covers in (UNCOMMITTED, WORKING_TREE):
        rows += untracked(directory)
    return rows, covers


def shown(name):
    return NEEDS_ESCAPE.sub(lambda found: ESCAPES.get(found.group(), b'\\x%02x' % found.group()[0]), name)


def save(spec, directory):
    rows, covers = collect(spec, directory)
    lines, unsaved, hidden = [], [], 0
    for number, (status, paths, content, notes) in enumerate(rows, 1):
        saved = os.path.join(directory, b'%04d.diff' % number)
        if BINARY.search(content):
            hidden += 1
            notes = [*notes, b'not shown: git treats it as binary']
        elif content.startswith(b'* Unmerged path '):
            hidden += 1
            notes = [*notes, b'not shown: git prints only the name of this conflicted file']
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
    refused = usage_error(spec)
    if refused:
        print(f'save-diff.py: error: {refused}', file=sys.stderr)
        return 2
    for name in PATHSPEC_VARIABLES:
        os.environ.pop(name, None)
    if sys.stdout is None:
        sys.exit('save-diff.py: error: standard output is closed, so the script has nowhere to print the rows')
    top = os.path.realpath(git('rev-parse', '--show-toplevel').rstrip(b'\n'))
    temporary = os.path.realpath(os.fsencode(tempfile.gettempdir()))
    if os.path.commonpath([top, temporary]) == top:
        sys.exit(f'save-diff.py: error: the temporary directory {os.fsdecode(temporary)} is inside the work tree, '
                 'so the saved files would show up as untracked. Set TMPDIR to a directory outside it and run again.')
    word = not_a_revision(spec)
    if word is not None:
        sys.exit(f'save-diff.py: error: "{word}" does not name one commit or tree, so the script cannot read a change '
                 'against it. The script takes revisions only, never a path.')

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
