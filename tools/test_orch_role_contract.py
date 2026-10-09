import importlib.util
import json
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
            'harnesses': sorted(models.CLIS),
            'singleRoles': sorted(models.ROLES - models.PANEL_ROLES),
            'panelRoles': sorted(models.PANEL_ROLES),
            'unresolvedAliases': sorted(models.OTHER_ALIASES),
        })
