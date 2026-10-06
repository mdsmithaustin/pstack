from pathlib import Path


def load_tests(loader, tests, pattern):
    suite = str(Path(__file__).resolve().parents[1] / 'evals/resume-recovery')
    discovered = loader.discover(suite, pattern='test_*.py', top_level_dir=suite)
    if discovered.countTestCases() == 0:
        raise RuntimeError('resume-recovery discovery found zero tests')
    return discovered
