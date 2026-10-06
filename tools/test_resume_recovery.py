"""Include the model-free recovery oracle in the existing tools CI suite."""
from pathlib import Path


def load_tests(loader, tests, pattern):
    suite = str(Path(__file__).resolve().parents[1] / 'evals/resume-recovery')
    return loader.discover(suite, pattern='test_*.py', top_level_dir=suite)
