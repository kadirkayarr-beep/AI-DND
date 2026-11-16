"""D-191: a test that leaves a sqlite connection unclosed must not break the shared HTTP teardown on Windows.

A ``sqlite3.Connection`` sits in a reference cycle, so ``with sqlite3.connect(...)`` (which only commits) leaves the
file open until the cyclic collector runs. Windows refuses to delete an open file, so the temporary directory cleanup
raised ``PermissionError [WinError 32]`` whenever the collector had not run yet. Linux deletes open files, so CI never
saw it. Collection is switched off here so the outcome does not depend on when the collector happens to run.
"""
from __future__ import annotations

import gc
import unittest
import unittest.mock
from pathlib import Path


class SharedTeardownTests(unittest.TestCase):
    def test_an_unclosed_connection_does_not_break_teardown(self):
        # Imported here: a module-level name would make the loader run every CampaignApiTests test again.
        from api.tests.test_campaign_api import CampaignApiTests

        seen = {}

        class LeavesConnectionOpen(CampaignApiTests):
            async def test_leak(self):
                with self.store._connect() as connection:
                    connection.execute("SELECT count(*) FROM campaigns").fetchone()
                seen["directory"] = self.temporary_directory.name

        was_enabled = gc.isenabled()
        gc.disable()
        try:
            result = unittest.TestResult()
            LeavesConnectionOpen("test_leak").run(result)
        finally:
            if was_enabled:
                gc.enable()
        self.assertEqual([(str(case), trace) for case, trace in result.errors + result.failures], [])
        self.assertEqual(result.testsRun, 1)
        self.assertFalse(Path(seen["directory"]).exists())

    def test_a_clean_teardown_does_not_force_a_full_collection(self):
        # A full collection costs ~0.06 s on a loaded machine and the teardown is shared by every HTTP test;
        # it runs only when the cleanup actually met an open file.
        from api.tests import test_campaign_api
        from api.tests.test_campaign_api import CampaignApiTests

        seen = {}

        class ClosesEverything(CampaignApiTests):
            async def test_nothing_left_open(self):
                seen["directory"] = self.temporary_directory.name

        result = unittest.TestResult()
        with unittest.mock.patch.object(test_campaign_api.gc, "collect") as collect:
            ClosesEverything("test_nothing_left_open").run(result)
        self.assertEqual([(str(case), trace) for case, trace in result.errors + result.failures], [])
        self.assertEqual(collect.call_count, 0)
        self.assertFalse(Path(seen["directory"]).exists())


if __name__ == "__main__":
    unittest.main()
