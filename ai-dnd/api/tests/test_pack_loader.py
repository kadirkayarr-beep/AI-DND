"""Direct unit tests for api.lore_authority.pack_loader: the pack index and review gate fail closed."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from api.lore_authority import pack_loader


class ReadJsonTests(unittest.TestCase):
    def test_missing_or_broken_file_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(RuntimeError):
                pack_loader._read_json(Path(folder) / "none.json")
            broken = Path(folder) / "bad.json"
            broken.write_text("{not json", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                pack_loader._read_json(broken)

    def test_valid_file_loads(self):
        with tempfile.TemporaryDirectory() as folder:
            good = Path(folder) / "ok.json"
            good.write_text('{"a": 1}', encoding="utf-8")
            self.assertEqual(pack_loader._read_json(good), {"a": 1})


class PackIndexTests(unittest.TestCase):
    def test_shipped_index_loads_with_one_verified_pack(self):
        packs = pack_loader.load_pack_index()
        verified = [p for p in packs if p["coverage_status"] in {"VERIFIED", "VERIFIED_PARTIAL"}]
        self.assertEqual(len(verified), 1)

    def test_invalid_indexes_are_refused(self):
        incomplete = {"pack_id": "a", "coverage_status": "INCOMPLETE"}
        bad = [
            [],
            {"packs": []},
            {"packs": ["x"]},
            {"packs": [incomplete, incomplete]},
            {"packs": [{"pack_id": 1, "coverage_status": "INCOMPLETE"}]},
            {"packs": [{"pack_id": "a", "coverage_status": "VERIFIED"}]},
            {"packs": [{"pack_id": "a", "coverage_status": "GUESSED"}]},
        ]
        for payload in bad:
            with self.subTest(payload=json.dumps(payload)):
                with mock.patch.object(pack_loader, "_read_json", return_value=payload):
                    with self.assertRaises(ValueError):
                        pack_loader.load_pack_index()

    def test_unindexed_pack_is_refused(self):
        with self.assertRaises(ValueError):
            pack_loader.registry_for_pack("fr:pack:not-there:v1")

    def test_incomplete_pack_answers_with_default_registry(self):
        from api.lore_authority.registry import default_lore_registry

        registry = pack_loader.registry_for_pack("fr:pack:incomplete:v1")
        self.assertEqual(type(registry), type(default_lore_registry()))


class ReviewGateTests(unittest.TestCase):
    def test_extraction_that_is_not_review_gated_is_refused(self):
        wrong_status = {"extraction_status": "OK", "engine_review_status": "UNREVIEWED_EXTRACTED", "pack": {}}
        for extraction in ("x", {}, wrong_status):
            with self.subTest(extraction=str(extraction)):
                with mock.patch.object(pack_loader, "_read_json", return_value=extraction):
                    with self.assertRaises(ValueError):
                        pack_loader._load_reviewed_files(Path("e.json"), Path("r.json"))

    def test_production_pack_is_fully_reviewed(self):
        extracted, reviewed, registry, catalog = pack_loader.load_production_pack()
        self.assertEqual(len(extracted.entities), len(reviewed.entities))
        self.assertTrue(catalog.packs)
        self.assertIsNotNone(registry.entity(catalog.packs[0].world_id))


if __name__ == "__main__":
    unittest.main()
