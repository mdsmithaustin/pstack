#!/usr/bin/env python3
"""Report the declared harness loading path and its UTF-8 source bytes."""
import argparse
import json
import re
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--action', required=True)
parser.add_argument('--runtime', choices=['claude-code', 'codex', 'hermes', 'grok', 'other'])
parser.add_argument('--persona', action='store_true')
parser.add_argument('--baseline', required=True, help='Git commit containing the unsplit guide')
args = parser.parse_args()
skill = Path(__file__).resolve().parents[1]
project = skill.parents[1]
main = skill / 'SKILL.md'
text = main.read_text(encoding='utf-8')
tables = text.split('## Runtime adapters\n', 1)
actions = dict(re.findall(r'^\| `([^`]+)` \| (.+) \|$', tables[0], re.MULTILINE))
runtimes = dict(re.findall(r'^\| `([^`]+)` \| (.+) \|$', tables[1], re.MULTILINE))
if args.action not in actions:
    parser.error('unknown action: ' + args.action)
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
    selected.extend([actions['persona'], actions['portable-paths']])
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
if args.persona or args.action in {'persona', 'portable-paths'}:
    before_paths.append(Path('references/portable-paths.md'))
before = []
for path in before_paths:
    relative = str((skill / path).relative_to(project))
    data = subprocess.run(['git', '-C', str(project), 'show', args.baseline + ':' + relative],
                          check=True, capture_output=True).stdout
    before.append({'path': relative, 'bytes': len(data)})
print(json.dumps({
    'measurement': 'declared harness source loading contract, not observed agent reads or provider tokens',
    'action': args.action, 'runtime': args.runtime, 'persona': args.persona,
    'baseline': args.baseline,
    'before': {'files': before, 'bytes': sum(row['bytes'] for row in before)},
    'after': {'files': after, 'bytes': sum(row['bytes'] for row in after)},
}, indent=2))
