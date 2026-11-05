"""Offline schema export using the parity suite's temporary, fail-closed app."""
import json
import unittest
from api.tests import test_contract_parity as parity

class ExportHeldContract(unittest.TestCase):
    def test_export_held_schemas_from_temporary_runtime(self):
        parity.setUpModule()
        try:
            schemas = parity.app.openapi()['components']['schemas']
            selected = {key: schemas[key] for key in ('ShopCounterHeld', 'ShopCounterResponse')}
            self.assertIn('held', selected['ShopCounterResponse']['properties'])
            self.assertNotIn('held', selected['ShopCounterResponse']['required'])
            print('HELD_SCHEMA_EXPORT=' + json.dumps(selected, ensure_ascii=True, sort_keys=True))
        finally:
            unittest.doModuleCleanups()