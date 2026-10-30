"""B04 content-manifest contract; reads repository manifests only (optional live PDF bookmark check)."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest


REPO = Path(__file__).resolve().parents[3]
MANIFEST_DIR = REPO / "content" / "manifest"
DECISION_FILE = REPO / "docs" / "acceptance" / "decisions" / "2026-10-26-source-use-scope.json"
DECISION_ID = "DEC-2026-10-26-SOURCE-USE-SCOPE"
import os
import shutil
import tempfile
PDF = Path(os.environ.get("AI_DND_PHB_2024_PDF", r"C:\Users\Kadir\Desktop\AI-DND ARŞİV\01_Arastirma\Referans_Kitaplar\2026-10-08\DND ALL BOOKS\D&D 5e - Players Handbook 2024.pdf"))
sys.path.insert(0, str(REPO / "tools" / "content"))
import check_manifest as owner

PINNED_COUNTS = {"class": 12, "subclass": 48, "species": 10, "background": 16, "feat": 75, "spell": 391,
                 "equipment.weapon": 38, "equipment.armor": 13, "equipment.tool": 25,
                 "equipment.adventuring_gear": 82, "equipment.vehicle": 12, "equipment.section": 6}


def load(name):
    return json.loads((MANIFEST_DIR / name).read_text(encoding="utf-8"))


def group_key(entry):
    return entry["category"] + ("." + entry["subcategory"] if entry["category"] == "equipment" else "")


class RoadmapB04Tests(unittest.TestCase):
    def setUp(self):
        self.manifest = load("phb2024.json")
        self.index = load("phb2024-source-index.json")
        self.legacy = load("legacy-compatibility.json")
        self.rows = self.manifest["rows"]
        self.entries = self.index["entries"]

    def observe(self):
        """Test-local observations measured from the real manifests and the real owner, never from a copy."""
        ids = [row["id"] for row in self.rows] + [row["id"] for row in self.legacy["rows"]]
        source_ids = [row["source_id"] for row in self.rows]
        return {
            "manifest_source_ids": source_ids,
            "authorized_source_index_ids": [entry["source_id"] for entry in self.entries],
            "duplicate_ids": sorted({i for i in ids if ids.count(i) > 1} | {i for i in source_ids if source_ids.count(i) > 1}),
            "legacy_choices": [row["name"] for row in self.legacy["rows"]],
            "srd_only_declared_complete": owner.srd_only_declared_complete(self.manifest),
        }

    def test_catalog_requires_every_source_entry(self):
        obs = self.observe()
        assert set(obs["manifest_source_ids"]) == set(obs["authorized_source_index_ids"])
        assert obs["duplicate_ids"] == []
        assert {"Half-Elf", "Half-Orc"} <= set(obs["legacy_choices"])
        assert obs["srd_only_declared_complete"] is False
        self.assertEqual(owner.validate_catalog(self.rows, self.entries), [])
        self.assertEqual(len(obs["manifest_source_ids"]), len(obs["authorized_source_index_ids"]))

    def test_one_missing_or_duplicated_row_fails(self):
        for drop in (0, len(self.rows) // 2, len(self.rows) - 1):
            rows = [row for i, row in enumerate(self.rows) if i != drop]
            codes = {error["code"] for error in owner.validate_catalog(rows, self.entries)}
            self.assertIn("MISSING_ROW", codes)
        duplicated = self.rows + [copy.deepcopy(self.rows[3])]
        self.assertTrue({"DUPLICATE_ID", "DUPLICATE_SOURCE_ID"} <= {e["code"] for e in owner.validate_catalog(duplicated, self.entries)})
        orphan = copy.deepcopy(self.rows[0])
        orphan["source_id"] = "phb2024:class:not-in-the-book"
        orphan["id"] = f"{orphan['category']}|{orphan['source_id']}|{orphan['source_version']}"
        self.assertIn("ORPHAN_ROW", {e["code"] for e in owner.validate_catalog(self.rows + [orphan], self.entries)})

    def test_negative_manifest_cases(self):
        def broken(change):
            row = copy.deepcopy(self.rows[5])
            row.update(change)
            rows = list(self.rows)
            rows[5] = row
            return {error["code"] for error in owner.validate_catalog(rows, self.entries)}

        self.assertIn("EMPTY_RESOLVER", broken({"resolver": {}}))
        self.assertIn("EMPTY_RESOLVER", broken({"resolver": {"existing_owner": None, "basis": ""}}))
        self.assertIn("OWNER_MISSING", broken({"resolver": {"existing_owner": None, "basis": "none_found"}, "proposed_owner": ""}))
        self.assertIn("EMPTY_SOURCE_VERSION", broken({"source_version": ""}))
        self.assertIn("EMPTY_SOURCE_VERSION", broken({"source_version": None}))
        self.assertIn("RIGHTS_UNCLEAR", broken({"rights_ref": None}))
        self.assertIn("RIGHTS_UNCLEAR", broken({"rights_ref": "UNKNOWN"}))
        self.assertIn("BAD_ID_FORMAT", broken({"id": "wrong"}))
        lifecycle = dict(self.rows[5]["lifecycle"])
        self.assertIn("HIDDEN_UNSUPPORTED", broken({"lifecycle": {**lifecycle, "use": "UNSUPPORTED"}}))
        self.assertIn("HIDDEN_UNSUPPORTED", broken({"status": "UNSUPPORTED", "unsupported_reason": ""}))
        self.assertIn("LIFECYCLE_CLAIM_WITHOUT_EVIDENCE", broken({"lifecycle": {**lifecycle, "use": "PASS"}, "evidence_ids": []}))
        self.assertIn("MISSING_FIELD", broken({"lifecycle": {k: v for k, v in lifecycle.items() if k != "save_load"}}))
        self.assertNotIn("LIFECYCLE_CLAIM_WITHOUT_EVIDENCE",
                         broken({"lifecycle": {**lifecycle, "use": "PASS"}, "evidence_ids": ["EV-1"]}))

    def test_unconfirmed_source_text_must_stay_visibly_open(self):
        entries = copy.deepcopy(self.entries)
        entries[7]["text_confirmation"] = "none"
        codes = {error["code"] for error in owner.validate_catalog(self.rows, entries)}
        self.assertIn("UNCONFIRMED_TEXT_NOT_OPEN", codes)
        rows = copy.deepcopy(self.rows)
        match = next(i for i, row in enumerate(rows) if row["source_id"] == entries[7]["source_id"])
        rows[match]["status"] = "OPEN_TEXT_UNCONFIRMED"
        self.assertNotIn("UNCONFIRMED_TEXT_NOT_OPEN", {e["code"] for e in owner.validate_catalog(rows, entries)})

    def test_text_gates_found_entries_the_bookmark_tree_lacks(self):
        gates = next(g for g in self.index["groups"] if g["group"] == "text_gates")
        added = {(a["category"], a["name"], a["pdf_page"]) for a in gates["added_from_text"]}
        self.assertEqual(added, {("spell", "Bane", 244), ("feat", "Heavy Armor Master", 203)})
        corrections = {(c["bookmark_title"], c["corrected_name"]) for c in gates["bookmark_title_corrections"]}
        self.assertEqual(corrections, {("Darvision", "Darkvision"), ("Pantasmal Killer", "Phantasmal Killer")})
        self.assertEqual(gates["spell"]["unpaired_after_additions"], [])
        self.assertEqual(gates["feat"]["unpaired_after_additions"], [])
        self.assertNotIn("unresolved_headers", gates)
        self.assertIn("residual_risk", gates)
        names = {e["name"] for e in self.entries}
        self.assertTrue({"Bane", "Darkvision", "Phantasmal Killer", "Heavy Armor Master"} <= names)
        self.assertFalse({"Darvision", "Pantasmal Killer"} & names)
        ids = {e["source_id"] for e in self.entries}
        self.assertNotIn("phb2024:spell:darvision", ids)
        for entry in self.entries:
            if entry["category"] in ("class", "subclass", "species", "background", "feat", "spell"):
                self.assertIn("bookmark_present", entry)
        corrected = [e for e in self.entries if e.get("bookmark_title")]
        self.assertEqual({e["bookmark_title"] for e in corrected}, {"Darvision", "Pantasmal Killer"})

    def test_rows_must_agree_with_their_source_index_entry(self):
        def broken(index, change):
            rows = copy.deepcopy(self.rows)
            target = copy.deepcopy(rows[index])
            target.update(change)
            rows[index] = target
            return {error["code"] for error in owner.validate_catalog(rows, self.entries)}

        spell = next(i for i, row in enumerate(self.rows) if row["category"] == "spell")
        self.assertIn("ROW_MISMATCH", broken(spell, {"name": "Something Else"}))
        self.assertIn("ROW_MISMATCH", broken(spell, {"category": "feat", "id": f"feat|{self.rows[spell]['source_id']}|2024"}))
        self.assertIn("ROW_MISMATCH", broken(spell, {"source": {**self.rows[spell]["source"], "pdf_page": 1}}))
        self.assertIn("ROW_MISMATCH", broken(spell, {"source_version": "2014", "id": f"spell|{self.rows[spell]['source_id']}|2014"}))
        self.assertIn("STATUS_MISMATCH", broken(spell, {"status": "OPEN_ENUMERATION"}))
        def orphan(source_id, version, legacy):
            row = copy.deepcopy(self.rows[0])
            row.update({"source_id": source_id, "source_version": version, "legacy": legacy,
                        "id": f"{row['category']}|{source_id}|{version}"})
            return {e["code"] for e in owner.validate_catalog(self.rows + [row], self.entries)}

        self.assertIn("ORPHAN_ROW", orphan("fake:orphan", "2024", True))
        self.assertIn("ORPHAN_ROW", orphan("fake:orphan", "legacy-2014", True))      # legacy flag and version, wrong id prefix
        self.assertIn("ORPHAN_ROW", orphan("legacy:species:fake", "2024", True))     # legacy flag and prefix, wrong version
        self.assertIn("ORPHAN_ROW", orphan("legacy:species:fake", "legacy-2014", False))  # prefix and version, no legacy flag
        self.assertNotIn("ORPHAN_ROW", orphan("legacy:species:fake", "legacy-2014", True))

    def test_manifest_level_checks_bind_index_hash_decision_and_basis(self):
        root = REPO
        self.assertEqual(owner.validate_manifest(self.manifest, self.index, root), [])

        def codes(manifest=None, index=None):
            return {e["code"] for e in owner.validate_manifest(manifest or self.manifest, index or self.index, root)}

        self.assertIn("INDEX_HASH_MISMATCH", codes(manifest={**self.manifest, "source_index_sha256": "0" * 64}))
        self.assertIn("RIGHTS_UNCLEAR", codes(manifest={**self.manifest, "rights": {**self.manifest["rights"], "user_scope_decision": "PENDING"}}))
        self.assertIn("RIGHTS_UNCLEAR", codes(manifest={**self.manifest, "rights": {**self.manifest["rights"], "decision_file": "docs/acceptance/decisions/missing.json"}}))
        self.assertIn("NOT_PHB_INDEX_BASIS", codes(manifest={**self.manifest, "completeness_basis": "srd_5_1"}))
        self.assertIn("MISSING_FIELD", codes(manifest={k: v for k, v in self.manifest.items() if k != "field_semantics"}))
        self.assertIn("MISSING_FIELD", codes(manifest={**self.manifest, "field_semantics": {**self.manifest["field_semantics"], "resolver": ""}}))
        self.assertIn("MISSING_FIELD", codes(manifest={**self.manifest, "field_semantics": {k: v for k, v in self.manifest["field_semantics"].items() if k != "lifecycle"}}))
        with tempfile.TemporaryDirectory() as directory:
            fake_root = Path(directory)
            (fake_root / "content" / "manifest").mkdir(parents=True)
            (fake_root / "docs" / "acceptance" / "decisions").mkdir(parents=True)
            shutil.copyfile(MANIFEST_DIR / "phb2024-source-index.json", fake_root / "content" / "manifest" / "phb2024-source-index.json")
            decision = json.loads(DECISION_FILE.read_text(encoding="utf-8"))
            target = fake_root / self.manifest["rights"]["decision_file"]
            target.write_text(json.dumps(decision), encoding="utf-8")
            self.assertEqual(owner.validate_manifest(self.manifest, self.index, fake_root), [])
            target.write_text(json.dumps({**decision, "user_scope_decision": "PENDING"}), encoding="utf-8")
            self.assertIn("RIGHTS_UNCLEAR", {e["code"] for e in owner.validate_manifest(self.manifest, self.index, fake_root)})
            target.write_text(json.dumps({**decision, "decision_id": "DEC-OTHER"}), encoding="utf-8")
            self.assertIn("RIGHTS_UNCLEAR", {e["code"] for e in owner.validate_manifest(self.manifest, self.index, fake_root)})
        self.assertIn("OPEN_SCOPE_ITEM_INVALID", codes(manifest={**self.manifest, "open_scope_items": [{"area": "x"}]}))
        self.assertIn("EDITION_MISMATCH", codes(index={**self.index, "source": {**self.index["source"], "edition": "2014"}}))

    def test_areas_not_enumerated_in_b04_are_listed_as_open_scope_items(self):
        items = self.manifest["open_scope_items"]
        areas = {item["area"] for item in items}
        for expected in ("Weapon properties and mastery properties", "Metamagic options", "Eldritch invocation options",
                         "Battle Master maneuvers", "Appendix B creature stat blocks", "Appendix C rules glossary"):
            self.assertIn(expected, areas)
        for item in items:
            self.assertTrue(item["status"].startswith("OPEN"), item["area"])
            self.assertTrue(item["reason"].strip() and item["proposed_owner"].strip() and item["pdf_pages"], item["area"])
        semantics = self.manifest["field_semantics"]
        for key in ("status.INVENTORIED", "resolver", "lifecycle", "open_scope_items"):
            self.assertIn(key, semantics)
        self.assertIn("not proof", semantics["resolver"])

    def test_unenumerated_source_sections_cannot_be_marked_done(self):
        rows = copy.deepcopy(self.rows)
        section = next(i for i, row in enumerate(rows) if row["subcategory"] == "section")
        rows[section]["status"] = "INVENTORIED"
        self.assertIn("OPEN_ENTRY_NOT_OPEN", {e["code"] for e in owner.validate_catalog(rows, self.entries)})

    def test_srd_list_never_stands_in_for_the_full_book(self):
        self.assertEqual(self.manifest["completeness_basis"], "phb2024_source_index")
        self.assertFalse(owner.srd_only_declared_complete(self.manifest))
        self.assertTrue(owner.srd_only_declared_complete({**self.manifest, "completeness_basis": "srd_5_1"}))
        self.assertTrue(owner.srd_only_declared_complete({**self.manifest, "completeness_basis": "srd_5_1_list_declared_complete"}))
        self.assertTrue(owner.srd_only_declared_complete({**self.manifest, "source_index": "content/manifest/srd.json"}))
        self.assertTrue(owner.srd_only_declared_complete({**self.manifest, "completeness_basis": "System Reference Document 5.1"}))
        self.assertTrue(owner.srd_only_declared_complete({k: v for k, v in self.manifest.items() if k != "completeness_basis"}))
        self.assertTrue(owner.srd_only_declared_complete({}))

    def test_measured_inventory_counts_and_structure_checks(self):
        counts = {}
        for entry in self.entries:
            counts[group_key(entry)] = counts.get(group_key(entry), 0) + 1
        self.assertEqual(counts, PINNED_COUNTS)
        groups = {g["group"]: g for g in self.index["groups"]}
        for name in ("equipment.weapon", "equipment.armor", "equipment.tool", "equipment.vehicle"):
            expected = groups[name]["expected_structure"]
            measured = {k: v for k, v in groups[name]["structure_check"].items() if k in expected}
            self.assertEqual(measured, expected, name)
        feats = {}
        for entry in self.entries:
            if entry["category"] == "feat":
                feats[entry["subcategory"]] = feats.get(entry["subcategory"], 0) + 1
        self.assertEqual(feats, {"origin": 10, "general": 43, "fighting_style": 10, "epic_boon": 12})
        classes = [e for e in self.entries if e["category"] == "class"]
        subclasses = [e for e in self.entries if e["category"] == "subclass"]
        self.assertEqual(len(subclasses), 4 * len(classes))
        for entry in classes:
            self.assertEqual(sum(1 for s in subclasses if s["parent_source_id"] == entry["source_id"]), 4, entry["name"])

    def test_every_entry_has_source_evidence_and_page_references(self):
        allowed = {"page_text_exact", "page_text_fuzzy", "page_text_partial_name", "index_text", "outline_bookmark"}
        for entry in self.entries:
            self.assertIn(entry["text_confirmation"], allowed, entry["source_id"])
            self.assertTrue(1 <= entry["pdf_page"] <= self.index["source"]["pages"], entry["source_id"])
            self.assertEqual(entry["printed_page"], entry["pdf_page"] + 1, entry["source_id"])
            self.assertTrue(entry["source_id"].startswith("phb2024:"))
            self.assertLessEqual(len(entry["name"]), 60, "names only, never book text")
            if entry["category"] == "equipment" and entry.get("granularity") != "section":
                self.assertNotIn(entry.get("name_status"), ("NEEDS_REVIEW", None), entry["source_id"])
        self.assertEqual(self.index["source"]["edition"], "2024")
        self.assertEqual(self.index["source"]["sha256"], "f2ea73369a6c4afbf6a7047249f06e5c51af503d9e42f87fe7a9c2c50aefafea")
        self.assertIn("2024 version", self.index["source"]["edition_evidence"])

    def test_open_equipment_sections_are_explicit_and_not_counted_as_done(self):
        sections = [row for row in self.rows if row["subcategory"] == "section"]
        self.assertEqual(len(sections), 6)
        for row in sections:
            self.assertEqual(row["status"], "OPEN_ENUMERATION", row["name"])
        done = [row for row in self.rows if row["subcategory"] != "section"]
        self.assertTrue(all(row["status"] == "INVENTORIED" for row in done))
        self.assertTrue(all(row["lifecycle"][k] == "NOT_ASSESSED" for row in self.rows for k in owner.LIFECYCLE_KEYS))

    def test_resolver_links_are_recomputed_from_the_existing_code(self):
        texts = {path: (REPO / path).read_text(encoding="utf-8") for path in owner.RESOLVER_FILES}
        matched = 0
        for row in self.rows:
            expected = owner.static_resolver_match(row["name"], texts)
            self.assertEqual(row["resolver"]["existing_owner"], expected, row["id"])
            if expected:
                matched += 1
            else:
                self.assertTrue(row["proposed_owner"], row["id"])
        self.assertGreater(matched, 0)
        barbarian = next(row for row in self.rows if row["source_id"] == "phb2024:class:barbarian")
        self.assertEqual(barbarian["resolver"]["existing_owner"], "ai-dnd/api/dnd_2024_rules.py")

    def test_proposed_owners_follow_the_plan_task_map(self):
        owners = {}
        for row in self.rows:
            owners.setdefault(row["category"], set()).add(row["proposed_owner"])
        self.assertEqual(owners["species"], {"C02"})
        self.assertEqual(owners["background"], {"C02"})
        self.assertEqual(owners["feat"], {"C03"})
        self.assertEqual(owners["spell"], {"C05"})
        self.assertEqual(owners["equipment"], {"C04"})
        self.assertEqual(owners["class"] | owners["subclass"], {f"C{n}" for n in range(10, 22)})
        classes = {row["name"]: row["proposed_owner"] for row in self.rows if row["category"] == "class"}
        self.assertEqual(classes["Barbarian"], "C10")
        self.assertEqual(classes["Wizard"], "C21")
        for row in self.rows:
            if row["category"] == "subclass":
                parent = row["source_id"].split(":")[2]
                self.assertEqual(row["proposed_owner"], classes[parent.title()], row["id"])

    def test_legacy_species_stay_separate_from_the_2024_book(self):
        names = {row["name"]: row for row in self.legacy["rows"]}
        self.assertEqual(set(names), {"Half-Elf", "Half-Orc"})
        index_names = {entry["name"] for entry in self.entries}
        index_ids = {entry["source_id"] for entry in self.entries}
        for name, row in names.items():
            self.assertNotIn(name, index_names)
            self.assertNotIn(row["source_id"], index_ids)
            self.assertTrue(row["source_id"].startswith("legacy:"))
            self.assertNotEqual(row["source_version"], "2024")
            self.assertTrue(row["legacy"])
            self.assertEqual(row["source"]["page_reference_status"], "NOT_READ_IN_B04")
            self.assertEqual(row["resolver"]["existing_owner"], "ai-dnd/api/dnd_2024_rules.py")
            self.assertEqual(row["proposed_owner"], "C02")
            self.assertEqual(row["rights_ref"], DECISION_ID)
        self.assertEqual(owner.validate_catalog(self.rows + self.legacy["rows"], self.entries), [])

    def test_user_scope_decision_is_recorded_and_referenced(self):
        decision = json.loads(DECISION_FILE.read_text(encoding="utf-8"))
        self.assertEqual(decision["decision_id"], DECISION_ID)
        self.assertEqual(decision["user_scope_decision"], "ACCEPTED")
        self.assertEqual(decision["publication_distribution_rights_review"], "NOT_APPLICABLE_TO_CURRENT_SCOPE")
        self.assertIn("not a claim that any third-party license has been verified", decision["not_claimed"])
        self.assertFalse(decision["original_documents_modified"])
        self.assertEqual(self.manifest["rights"]["decision_id"], DECISION_ID)
        self.assertEqual(self.manifest["rights"]["user_scope_decision"], "ACCEPTED")
        self.assertEqual({row["rights_ref"] for row in self.rows}, {DECISION_ID})
        self.assertEqual(self.index["source"]["decision_id"], DECISION_ID)
        self.assertEqual(self.manifest["source_index_sha256"],
                         hashlib.sha256((MANIFEST_DIR / "phb2024-source-index.json").read_bytes()).hexdigest())

    def test_repository_holds_identifiers_only_never_book_text(self):
        for name in ("phb2024.json", "phb2024-source-index.json", "legacy-compatibility.json"):
            self.assertLess((MANIFEST_DIR / name).stat().st_size, 2_500_000, name)
        text = "".join((MANIFEST_DIR / name).read_text(encoding="utf-8") for name in ("phb2024-source-index.json", "phb2024.json"))
        self.assertNotIn("\u00a9", text)
        self.assertFalse(list(REPO.glob("content/**/*.pdf")) or list(REPO.glob("docs/acceptance/**/*.pdf")))

    @unittest.skipUnless(PDF.is_file(), "the user's local PDF is not available on this machine")
    def test_bookmark_derived_entries_match_the_pdf_outline(self):
        from pypdf import PdfReader
        reader = PdfReader(str(PDF))
        self.assertEqual(len(reader.pages), self.index["source"]["pages"])
        titles = {}

        def walk(items):
            for item in items:
                if isinstance(item, list):
                    walk(item)
                else:
                    titles.setdefault(item.title.replace(" (R)", "").strip(), set()).add(reader.get_destination_page_number(item) + 1)

        walk(reader.outline)
        outline_based = [e for e in self.entries if e["category"] in ("class", "subclass", "species", "background", "feat", "spell")]
        with_bookmark = [e for e in outline_based if e["bookmark_present"]]
        self.assertEqual(len(with_bookmark), 12 + 48 + 10 + 16 + 74 + 390)
        for entry in with_bookmark:
            self.assertIn(entry["pdf_page"], titles.get(entry.get("bookmark_title", entry["name"]), set()), entry["source_id"])
        self.assertEqual(sorted(e["name"] for e in outline_based if not e["bookmark_present"]), ["Bane", "Heavy Armor Master"])

if __name__ == "__main__":
    unittest.main()
