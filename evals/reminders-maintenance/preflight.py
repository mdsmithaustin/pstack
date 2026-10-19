#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sources():
    lock = json.loads((ROOT / 'source-lock.json').read_text())
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()}
    if actual != set(lock['files']) | {'source-lock.json'}:
        raise ValueError('source file inventory differs from source-lock.json')
    for name, record in lock['files'].items():
        path = ROOT / name
        if path.is_symlink() or sha256(path) != record['sha256']:
            raise ValueError(f'frozen source changed: {name}')
    ignored = subprocess.run(['git', 'check-ignore', '--stdin'], cwd=ROOT,
                             input='\n'.join(actual) + '\n', text=True, capture_output=True)
    if ignored.returncode != 1:
        raise ValueError(f'public sources must not be ignored: {ignored.stdout}{ignored.stderr}')
    start = ROOT / 'starting-project'
    with zipfile.ZipFile(ROOT / 'starting-project.zip') as archive:
        expected = {p.relative_to(start).as_posix() for p in start.rglob('*') if p.is_file()}
        if len(expected) != 7 or len(archive.namelist()) != 7 or set(archive.namelist()) != expected:
            raise ValueError('model archive must contain exactly the seven starting project files')
        for member in archive.infolist():
            source = start / member.filename
            executable = bool((member.external_attr >> 16) & 0o111)
            if archive.read(member) != source.read_bytes() or executable != bool(source.stat().st_mode & 0o111):
                raise ValueError(f'model archive differs from starting project: {member.filename}')
    package = importlib.metadata.distribution('skill-eval-harness-ext')
    provenance = json.loads(package.read_text('direct_url.json') or '{}')
    if provenance.get('vcs_info', {}).get('commit_id') != lock['harness_revision']:
        raise ValueError('installed native runtime revision differs from source lock')
    for name, expected in lock['runtime_modules'].items():
        if sha256(Path(importlib.import_module(name).__file__)) != expected:
            raise ValueError(f'installed runtime module changed: {name}')
    return sha256(ROOT / 'source-lock.json')


def capture(project, directory):
    from skill_benchmark import write_artifact_commit
    from workspace_contracts import capture_workspace_changes, snapshot_workspace

    directory.mkdir()
    workspace = directory / 'workspace'
    workspace.mkdir()
    baseline = snapshot_workspace(workspace, directory / 'shadow')
    shutil.copytree(project, workspace / 'project')
    run = directory / 'capture'
    run.mkdir()
    capture_workspace_changes(baseline, workspace, run)
    (run / 'output.md').write_text('Synthetic control capture. No model invoked.\n')
    for name, value in [('events.json', []), ('metrics.json', {'synthetic': True}),
                        ('metadata.json', {'kind': 'synthetic_control', 'model': None})]:
        (run / name).write_text(json.dumps(value) + '\n')
    write_artifact_commit(run)
    return run


def check(control, output, image):
    directory = output / control['name']
    run = capture(ROOT / control['project'], directory)
    if control['name'] == 'missing-capture':
        (run / 'artifact-commit.json').unlink()
    elif control['name'] == 'tampered-capture':
        (run / 'output.md').write_text('Tampered after commit.\n')
    launcher = ('import runpy,sys;sys.path.insert(0,sys.argv[1]);'
                'sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name="__main__")')
    command = [sys.executable, '-I', '-B', '-c', launcher, str(ROOT / 'instrument'),
               str(ROOT / 'instrument/experiment.py'), 'check', '--run', str(run),
               '--oracle', str(ROOT / 'oracle/acceptance.py'), '--stage', control['stage'],
               '--oracle-image', image]
    if control['prior'] is not None:
        command += ['--prior-project', str(ROOT / control['prior'])]
    process = subprocess.run(command, capture_output=True, text=True, timeout=150)
    (directory / 'check.stdout').write_text(process.stdout)
    (directory / 'check.stderr').write_text(process.stderr)
    (directory / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    expected = control['expected_result']
    receipt = {'name': control['name'], 'expected_result': expected,
               'checker_exit': process.returncode, 'synthetic_capture': True}
    if expected == 'capture_rejected':
        if process.returncode != 1 or process.stdout != '' or control['failure_marker'] not in process.stderr:
            raise ValueError(f'{control["name"]}: capture rejection did not match')
        receipt.update(acceptance_requests=0, failure_marker=control['failure_marker'])
        return receipt
    if process.stderr or process.returncode not in (0, 1):
        raise ValueError(f'{control["name"]}: checker infrastructure failure')
    result = json.loads(process.stdout)
    if set(result) != {'returncode', 'stdout', 'stderr', 'passed'}:
        raise ValueError(f'{control["name"]}: unexpected checker response')
    if expected == 'pass':
        summary = f'{"requested" if control["stage"] == "design" else "maintenance"}: {control["expected_count"]} requests passed\n'
        if process.returncode != 0 or result != dict(returncode=0, stdout=summary, stderr='', passed=True):
            raise ValueError(f'{control["name"]}: expected full nonzero request count, see check.stdout')
        receipt.update(acceptance_requests=control['expected_count'], failure_marker=None)
    else:
        marker = control['failure_marker']
        expected_response = repr(control['expected_response'])
        expected_code = 2 if 'error' in control['expected_response'] else 0
        if (process.returncode != 1 or result['returncode'] != 1 or result['passed'] is not False
                or result['stdout'] != '' or f'AssertionError: {marker}: expected exit {expected_code} and {expected_response};' not in result['stderr']
                or 'Traceback (most recent call last):' not in result['stderr']):
            raise ValueError(f'{control["name"]}: expected candidate failure, see check.stdout')
        actual_response = control['actual_failure_response']
        if f'got exit {control["actual_failure_exit"]} and {actual_response}; stderr=\'\'' not in result['stderr']:
            raise ValueError(f'{control["name"]}: candidate response differs from control table')
        receipt.update(completed_before_failure_inferred=control['completed_before_failure'],
                       failure_marker=marker, expected_response=control['expected_response'],
                       actual_response=actual_response)
    return receipt


def main():
    parser = argparse.ArgumentParser(description='Run model-free native-capture controls in Docker.')
    parser.add_argument('--output', type=Path, required=True, help='New private receipt directory outside this repository.')
    args = parser.parse_args()
    output = args.output.resolve()
    repository = ROOT.parents[1]
    if output == repository or repository in output.parents or output.exists():
        parser.error('--output must be a new directory outside this repository')
    if not sys.flags.isolated:
        parser.error('run with the harness Python and -I')
    lock_sha = verify_sources()
    case = json.loads((ROOT / 'case.json').read_text())
    image = case['runtime']['oracle_image']
    subprocess.run(['docker', 'image', 'inspect', image], check=True, capture_output=True, timeout=30)
    output.mkdir(parents=True)
    receipts = [check(control, output, image) for control in case['controls']]
    if verify_sources() != lock_sha:
        raise ValueError('source lock changed during preflight')
    receipt = {'case': case['id'], 'kind': 'model_free_preflight', 'paid_calls': 0,
               'source_lock_sha256': lock_sha, 'harness_revision': case['runtime']['harness_revision'],
               'python_version': sys.version, 'oracle_image': image, 'controls': receipts}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'preflight failed: {error}', file=sys.stderr)
        raise SystemExit(1)
