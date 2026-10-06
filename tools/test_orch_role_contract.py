import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OrchRoleContract(unittest.TestCase):
    def test_portable_catalog_matches_setup_owned_roles(self):
        source = ROOT / 'skills/setup-pstack/scripts/check-models-config.py'
        spec = importlib.util.spec_from_file_location('models', source)
        models = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(models)
        artifact = json.loads((ROOT / 'skills/poteto-mode/scripts/orch/role-contract.json').read_text())
        self.assertEqual(artifact, {
            'singleRoles': sorted(models.ROLES - models.PANEL_ROLES),
            'panelRoles': sorted(models.PANEL_ROLES),
            'unresolvedAliases': sorted(models.OTHER_ALIASES),
        })
        source = ROOT / 'evals/resume-recovery/oracle.py'
        spec = importlib.util.spec_from_file_location('resume_oracle_contract', source)
        oracle = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = oracle
        spec.loader.exec_module(oracle)
        self.assertEqual(oracle.UNRESOLVED_ALIASES, models.OTHER_ALIASES)
