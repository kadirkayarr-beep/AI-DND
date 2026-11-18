"""engine_hash covers game.py and every game_parts/*.py file."""
from __future__ import annotations

import contextlib
import io
import httpx
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from api.persistence import campaign_store
from api.tests.engine_sources import ENGINE_ROOT, engine_source_files


class EngineHashPartsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "game_parts").mkdir()
        self.game = self.root / "game.py"
        self.game.write_bytes(b"game")
        (self.root / "game_parts" / "a.py").write_bytes(b"a")
        (self.root / "game_parts" / "b.py").write_bytes(b"b")

    def _digest(self) -> str:
        return campaign_store._engine_digest(self.game)

    def test_changing_a_part_changes_the_hash(self):
        before = self._digest()
        (self.root / "game_parts" / "a.py").write_bytes(b"a2")
        self.assertNotEqual(before, self._digest())

    def test_adding_a_part_changes_the_hash(self):
        before = self._digest()
        (self.root / "game_parts" / "c.py").write_bytes(b"c")
        self.assertNotEqual(before, self._digest())

    def test_renaming_a_part_changes_the_hash(self):
        before = self._digest()
        (self.root / "game_parts" / "b.py").rename(self.root / "game_parts" / "z.py")
        self.assertNotEqual(before, self._digest())

    def test_changing_game_py_changes_the_hash(self):
        before = self._digest()
        self.game.write_bytes(b"game2")
        self.assertNotEqual(before, self._digest())

    def test_the_hash_is_stable_for_the_same_files(self):
        self.assertEqual(self._digest(), self._digest())

    def test_product_and_test_helper_list_the_same_files(self):
        files = campaign_store._engine_files(ENGINE_ROOT / "game.py")
        self.assertEqual(files, engine_source_files())
        self.assertGreater(len(files), 1)   # game_parts must be present

    def test_a_missing_engine_file_is_a_storage_error(self):
        with patch.object(campaign_store, "_engine_digest", side_effect=OSError):
            with self.assertRaises(campaign_store.CampaignStorageError):
                campaign_store.CampaignStore._engine_hash()

    def test_live_smoke_reports_the_engine_digest(self):
        from api import live_smoke
        out = io.StringIO()
        with patch.object(live_smoke.httpx, "Client", side_effect=httpx.ConnectError("no server")) as client:
            with contextlib.redirect_stdout(out):
                live_smoke.main()   # the FAIL report still carries the hash; no real HTTP client opens
        client.assert_called_once()
        report = json.loads(out.getvalue())
        self.assertEqual(
            report["game_sha256"], campaign_store._engine_digest(ENGINE_ROOT / "game.py")
        )


if __name__ == "__main__":
    unittest.main()
