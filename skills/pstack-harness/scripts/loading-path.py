#!/usr/bin/env python3
"""Report the declared harness loading path and its UTF-8 source bytes."""
import argparse
import json
import locale
import re
import subprocess
import sys
from pathlib import Path

skill = Path(__file__).resolve().parents[1]
project = skill.parents[1]
main = skill / 'SKILL.md'
text = main.read_text(encoding='utf-8')
tables = text.split('## Runtime adapters\n', 1)
actions = dict(re.findall(r'^\| `([^`]+)` \| (.+) \|$', tables[0], re.MULTILINE))
runtimes = dict(re.findall(r'^\| `([^`]+)` \| (.+) \|$', tables[1], re.MULTILINE))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--action', required=True, choices=list(actions),
                    help='Action whose loading path to report, as named in the harness skill')
parser.add_argument('--runtime', choices=['claude-code', 'codex', 'hermes', 'grok', 'other'],
                    help='Required for spawn and transcript')
parser.add_argument('--persona', action='store_true', help='Add the persona contract; spawn only')
parser.add_argument('--baseline', help='Git commit containing the unsplit guide; omit for a '
                    'current-only report. Needs git on PATH and a pstack source checkout whose '
                    'history holds the commit. The script resolves its own path first, so a '
                    "symlinked install compares against the symlink target's repository.")
args = parser.parse_args()
if args.action in {'spawn', 'transcript'} and args.runtime is None:
    parser.error('--runtime is required for ' + args.action)
if args.persona and args.action != 'spawn':
    parser.error('--persona requires --action spawn')
selected = [actions[args.action]]
if args.action in {'spawn', 'transcript'}:
    selected.append(runtimes[args.runtime].split(' | ')[0 if args.action == 'spawn' else 1])
if args.action == 'persona':
    selected.append(actions['portable-paths'])
if args.persona:
    selected.append(actions['persona'])
paths = [Path('SKILL.md')]
for row in selected:
    for target in re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)', row):
        path = Path(target)
        if path.is_absolute() or '..' in path.parts:
            parser.error('route leaves the harness skill: ' + target)
        if path not in paths:
            paths.append(path)
after = []
for path in paths:
    data = (skill / path).read_bytes()
    after.append({'path': str((skill / path).relative_to(project)), 'bytes': len(data)})
before_paths = [Path('SKILL.md')]
if args.persona or args.action == 'persona':
    before_paths.append(Path('references/named-roles.md'))
if args.persona or args.action in {'spawn', 'persona', 'portable-paths'}:
    before_paths.append(Path('references/portable-paths.md'))
before = None
if args.baseline is not None:
    def git(*command):
        try:
            result = subprocess.run(['git', '-C', str(project), *command], capture_output=True)
        except FileNotFoundError:
            sys.exit('loading-path.py: error: --baseline needs git, which is not on PATH. '
                     'Omit --baseline for a current-only report.')
        result.stderr = result.stderr.decode(locale.getpreferredencoding(False), 'replace').strip()
        return result
    opened = git('rev-parse', '--git-dir')
    if opened.returncode and 'safe.directory' in opened.stderr:
        sys.exit(f'loading-path.py: error: git refuses to open the repository that holds '
                 f'{project} because another user owns it. Mark the directory safe as git '
                 f'describes below, or omit --baseline for a current-only report.\n{opened.stderr}')
    if opened.returncode:
        sys.exit(f'loading-path.py: error: git cannot open {project} as a repository '
                 f'({opened.stderr}). --baseline reads the old guide from Git '
                 'history, so run the copy inside a pstack source checkout, or omit --baseline '
                 'for a current-only report.')
    if git('rev-parse', '--verify', '--quiet', args.baseline + '^{commit}').returncode:
        sys.exit(f'loading-path.py: error: baseline {args.baseline} is not a commit in {project}. '
                 'Fetch the history that contains it, or pass a commit this checkout has.')
    files = []
    for path in before_paths:
        relative = str((skill / path).relative_to(project))
        shown = git('show', f'{args.baseline}:./{relative}')
        if shown.returncode:
            sys.exit(f'loading-path.py: error: baseline {args.baseline} has no {relative}: '
                     + shown.stderr)
        files.append({'path': relative, 'bytes': len(shown.stdout)})
    before = {'files': files, 'bytes': sum(row['bytes'] for row in files)}
print(json.dumps({
    'measurement': 'declared harness source loading contract, not observed agent reads or provider tokens',
    'action': args.action, 'runtime': args.runtime, 'persona': args.persona,
    'baseline': args.baseline,
    'before': before,
    'after': {'files': after, 'bytes': sum(row['bytes'] for row in after)},
}, indent=2))
