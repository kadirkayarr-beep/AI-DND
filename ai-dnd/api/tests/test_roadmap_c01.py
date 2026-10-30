"""C01: a capability is COMPLETE only when all six lifecycle axes are proven; every source entry has leaves and a test owner.

`capabilities.capability_status(entry_id, character)` reports visible/create/select/use/advance/save_load separately and never
says COMPLETE while an axis is missing or unassessed. `expand_manifest_tasks(rows)` turns the B04 manifest into atomic leaf
tasks (one behaviour, source oracle, command, dependency, rollback, test owner); spells get separate cantrip-scaling and
slot-upcast leaves, so one is never generalized to the other. `release_blockers(rows)` lists what still blocks a full release;
with the current manifest (nothing assessed yet) it must NOT be empty.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import capabilities

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = json.loads((ROOT / "content" / "manifest" / "phb2024.json").read_text(encoding="utf-8"))
INDEX = json.loads((ROOT / "content" / "manifest" / "phb2024-source-index.json").read_text(encoding="utf-8"))
ROWS = MANIFEST["rows"]


_STATE = {}
EVIDENCE_TEST = "ai-dnd/api/tests/test_roadmap_c01.py"


def record_payload(which, **override):
    """A complete acceptance record: PASS, integer exit code 0, not a mock, bound to one entry, one axis and one test file."""
    return {"testID": f"EV-C01-{which}", "status": "PASS", "exitCode": 0, "mock": False, "entry": "phb2024:spell:x",
            "axis": which, "test": "ai-dnd/api/tests/test_roadmap_c01.py", **override}


def setUpModule():
    """Evidence records live in a temporary evidence root; the module never writes into the repo's evidence folder."""
    _STATE["tmp"] = tempfile.TemporaryDirectory()
    _STATE["previous"] = capabilities.EVIDENCE_ROOT
    root = Path(_STATE["tmp"].name)
    for axis in capabilities.AXES:
        (root / f"{axis}.json").write_text(json.dumps(record_payload(axis)), encoding="utf-8")
    first = capabilities.manifest_open_scope()[0]
    (root / "open.json").write_text(json.dumps(record_payload(
        "enumerate", testID="EV-C01-open", entry="openscope:" + capabilities._slug(first["area"]))), encoding="utf-8")
    capabilities.EVIDENCE_ROOT = root


def tearDownModule():
    capabilities.EVIDENCE_ROOT = _STATE["previous"]
    _STATE["tmp"].cleanup()


def evidence_for(axis, **override):
    return {"evidence_id": f"EV-C01-{axis}", "record": f"{axis}.json",
            "test_owner": "ai-dnd/api/tests/test_roadmap_c01.py", **override}


def row(evidence=True, **axes):
    base = {"id": "spell|x|2024", "source_id": "phb2024:spell:x", "category": "spell", "name": "X", "status": "INVENTORIED",
            "dependencies": [], "proposed_owner": "C05", "source": {"pdf_page": 1, "printed_page": 2},
            "lifecycle": {axis: "NOT_ASSESSED" for axis in capabilities.AXES}}
    base["lifecycle"].update(axes)
    if evidence:
        base["axis_evidence"] = {axis: evidence_for(axis) for axis in capabilities.AXES}
    return base


class CapabilityTests(unittest.TestCase):
    def test_capability_status_requires_all_lifecycle_axes(self):
        done = {axis: "SUPPORTED" for axis in capabilities.AXES}
        complete = capabilities.status_of_row(row(**done), {})
        one_missing = capabilities.status_of_row(row(**{**done, "advance": "UNSUPPORTED"}), {})
        unassessed = capabilities.status_of_row(row(**{**done, "save_load": "NOT_ASSESSED"}), {})
        leaves = capabilities.expand_manifest_tasks(ROWS)
        by_source = {}
        for leaf in leaves:
            by_source.setdefault(leaf["source_id"], []).append(leaf)
        blockers = capabilities.release_blockers(ROWS, capabilities.manifest_open_scope())
        obs = {
            "axes_reported_separately": set(complete["axes"]) == set(capabilities.AXES),
            "complete_when_all_axes": complete["status"] == "COMPLETE",
            "complete_with_missing_axis": one_missing["status"] == "COMPLETE" or unassessed["status"] == "COMPLETE",
            "sources_without_leaf_or_test_owner": sorted(
                {r["source_id"] for r in INDEX["entries"]}
                - {sid for sid, items in by_source.items() if items and all(i["test_owner"] for i in items)}),
            "release_has_no_blockers": not blockers,
        }
        assert obs["axes_reported_separately"] is True
        assert obs["complete_when_all_axes"] is True
        assert obs["complete_with_missing_axis"] is False
        assert obs["sources_without_leaf_or_test_owner"] == []
        assert obs["release_has_no_blockers"] is False, "nothing is assessed yet; a release is NOT possible"
        self.assertEqual(one_missing["missing_axes"], ["advance"])
        self.assertEqual(unassessed["missing_axes"], ["save_load"])
        self.assertEqual(len(blockers), len(ROWS) + len(capabilities.manifest_open_scope()),
                         "every unassessed entry AND every declared open scope area blocks the release")

    def test_leaves_are_atomic_with_oracle_command_dependency_and_rollback(self):
        leaves = capabilities.expand_manifest_tasks(ROWS)
        ids = [leaf["leaf_id"] for leaf in leaves]
        self.assertEqual(len(ids), len(set(ids)), "leaf ids are unique")
        for leaf in leaves[:50] + leaves[-50:]:
            for key in ("leaf_id", "source_id", "behavior", "owner", "test_owner", "oracle", "command", "dependencies", "rollback"):
                self.assertIn(key, leaf)
            self.assertTrue(leaf["leaf_id"].startswith(f"{leaf['owner']}."))
            self.assertEqual(leaf["rollback"], "RB-1")
            self.assertIn("pdf_page", leaf["oracle"])

    def test_every_dependency_resolves_to_a_leaf_and_open_scope_is_covered(self):
        leaves = capabilities.expand_manifest_tasks(ROWS) + capabilities.expand_open_scope(capabilities.manifest_open_scope())
        leaf_ids = {leaf["leaf_id"] for leaf in leaves}
        dangling = [(leaf["leaf_id"], dep) for leaf in leaves for dep in leaf["dependencies"] if dep not in leaf_ids]
        self.assertEqual(dangling, [], "every dependency is a real leaf id (a subclass depends on its class's last leaf)")
        areas = {leaf["oracle"]["area"] for leaf in leaves if leaf["category"] == "open_scope"}
        self.assertEqual(areas, {item["area"] for item in capabilities.manifest_open_scope()})
        self.assertTrue(all(leaf["status"] == "OPEN" for leaf in leaves if leaf["category"] == "open_scope"))
        subclass = next(r for r in ROWS if r["category"] == "subclass")
        first = next(l for l in capabilities.expand_manifest_tasks(ROWS) if l["source_id"] == subclass["source_id"])
        self.assertTrue(any(dep.startswith("C") and ".phb2024:class:" in dep for dep in first["dependencies"]))

    def test_test_owner_existence_is_reported_honestly(self):
        leaves = capabilities.expand_manifest_tasks(ROWS)
        for leaf in leaves[:: max(1, len(leaves) // 60)]:
            self.assertEqual(leaf["test_owner_exists"], (ROOT / leaf["test_owner"]).exists(), leaf["test_owner"])
        self.assertTrue(any(not leaf["test_owner_exists"] for leaf in leaves), "the C02..C21 test files do not exist yet (recorded gap)")

    def test_unknown_axis_values_are_invalid_never_progress(self):
        typo = row(**{axis: "supported" for axis in capabilities.AXES})
        self.assertEqual(capabilities.status_of_row(typo, {})["status"], "INVALID_ROW")
        self.assertEqual(capabilities.status_of_row(row(**{axis: "INVALID" for axis in capabilities.AXES}), {})["status"], "INVALID_ROW")

    def test_supported_needs_real_evidence_for_each_axis(self):
        done = {axis: "SUPPORTED" for axis in capabilities.AXES}
        self.assertEqual(capabilities.status_of_row(row(**done), {})["status"], "COMPLETE")
        none = capabilities.status_of_row(row(evidence=False, **done), {})
        self.assertEqual((none["status"], none["missing_axes"]), ("INCOMPLETE", list(capabilities.AXES)))
        self.assertTrue(all(state == "UNPROVEN" for state in none["axes"].values()))

        def with_use(evidence):
            base = row(**done)
            base["axis_evidence"]["use"] = evidence
            return capabilities.status_of_row(base, {})

        bad_owners = {
            "missing file": "ai-dnd/api/tests/test_roadmap_c99_missing.py",
            "traversal": "../../../../Windows/win.ini",
            "absolute": "C:/Windows/win.ini",
            "directory": "ai-dnd/api/tests",
            "not a test module": "ai-dnd/capabilities.py",
            "outside the tests dir": "README.md",
        }
        for label, owner in bad_owners.items():
            self.assertEqual(with_use(evidence_for("use", test_owner=owner))["missing_axes"], ["use"], label)
        # the evidence record itself must be a real PASS row for exactly this id
        for label, record in {
            "no id": None, "escapes the root": "../use.json", "absolute outside the root": "C:/Windows/win.ini",
            "missing record": "nope.json",
        }.items():
            evidence = evidence_for("use", record=record) if record else {"record": "use.json", "test_owner": evidence_for("use")["test_owner"]}
            self.assertEqual(with_use(evidence)["missing_axes"], ["use"], label)
        root = Path(_STATE["tmp"].name)
        for label, payload in {
            "failed": record_payload("use", status="FAIL"),
            "non-zero exit": record_payload("use", exitCode=1),
            "boolean exit code": record_payload("use", exitCode=False),
            "mock": record_payload("use", mock=True),
            "other test id": record_payload("use", testID="EV-OTHER"),
            "another entry's record": record_payload("use", entry="phb2024:spell:other"),
            "another axis's record": record_payload("use", axis="create"),
            "record names another test file": record_payload("use", test="ai-dnd/api/tests/test_roadmap_c02.py"),
        }.items():
            (root / "bad.json").write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(with_use(evidence_for("use", record="bad.json"))["missing_axes"], ["use"], label)
        # an existing but unrelated test file cannot carry a record that names another file
        self.assertEqual(with_use(evidence_for("use", test_owner="ai-dnd/api/tests/test_roadmap_b04.py"))["missing_axes"], ["use"])
        self.assertEqual(with_use(evidence_for("use", evidence_id=["EV-C01-use"]))["missing_axes"], ["use"], "non-string id")
        # one evidence id cannot prove two axes
        shared = row(**done)
        shared["axis_evidence"]["select"] = evidence_for("create")
        self.assertEqual(capabilities.status_of_row(shared, {})["missing_axes"], ["select"])
        # a bare flag is not trusted
        flag = row(**done)
        flag["axis_evidence"]["use"] = {"test_owner_exists": True}
        self.assertEqual(capabilities.status_of_row(flag, {})["missing_axes"], ["use"])

    def test_completion_requires_every_dependency_transitively(self):
        leaves = capabilities.expand_manifest_tasks(ROWS)
        subclass = next(r for r in ROWS if r["category"] == "subclass" and r["dependencies"])
        klass = next(r for r in ROWS if r["source_id"] == subclass["dependencies"][0])
        class_leaves = [l["leaf_id"] for l in leaves if l["source_id"] == klass["source_id"]]
        sub_leaves = [l["leaf_id"] for l in leaves if l["source_id"] == subclass["source_id"]]
        # out of order: only the class's LAST leaf is done; the earlier ones are not
        out_of_order = capabilities.can_complete_leaf(sub_leaves[0], leaves, {class_leaves[-1]})
        self.assertFalse(out_of_order["allowed"])
        self.assertEqual(set(out_of_order["unmet"]), set(class_leaves[:-1]))
        self.assertTrue(capabilities.can_complete_leaf(sub_leaves[0], leaves, set(class_leaves))["allowed"])
        # a later subclass leaf also needs the earlier subclass leaves
        self.assertFalse(capabilities.can_complete_leaf(sub_leaves[1], leaves, set(class_leaves))["allowed"])
        self.assertTrue(capabilities.can_complete_leaf(sub_leaves[1], leaves, set(class_leaves) | {sub_leaves[0]})["allowed"])
        self.assertEqual(capabilities.can_complete_leaf(sub_leaves[0], leaves, {sub_leaves[0]})["reason"], "already_completed")
        cycle = [{"leaf_id": "A.1", "dependencies": ["A.2"]}, {"leaf_id": "A.2", "dependencies": ["A.1"]}]
        self.assertEqual(capabilities.can_complete_leaf("A.1", cycle, set())["reason"], "dependency_cycle")
        # an unresolved dependency is never satisfied, an unknown leaf is refused
        orphan = [{"leaf_id": "X.1", "dependencies": ["unresolved:ghost"]}]
        self.assertFalse(capabilities.can_complete_leaf("X.1", orphan, {"unresolved:ghost"})["allowed"])
        self.assertFalse(capabilities.can_complete_leaf("nope", leaves, set())["allowed"])

    def test_closing_the_counting_leaf_does_not_close_open_scope(self):
        items = capabilities.manifest_open_scope()
        before = capabilities.release_blockers([], items)
        self.assertEqual(len(before), len(items))
        leaves = capabilities.expand_open_scope(items)
        self.assertTrue(all(capabilities.can_complete_leaf(leaf["leaf_id"], leaves, set())["allowed"] for leaf in leaves))
        # every `enumerate` leaf is now closed

        self.assertEqual(len(capabilities.release_blockers([], items)), len(items), "still blocking after the counting leaves close")
        bare = [{**items[0], "status": "ENUMERATED_COMPLETE"}, *items[1:]]
        self.assertEqual(len(capabilities.release_blockers([], bare)), len(items), "a bare status string closes nothing")
        open_evidence = {"evidence_id": "EV-C01-open", "record": "open.json", "test_owner": EVIDENCE_TEST}
        proven = [{**items[0], "status": "ENUMERATED_COMPLETE", "evidence": open_evidence}, *items[1:]]
        self.assertEqual(len(capabilities.release_blockers([], proven)), len(items) - 1)
        # the same record cannot close a second area
        reused = [proven[0], {**items[1], "status": "ENUMERATED_COMPLETE", "evidence": open_evidence}, *items[2:]]
        self.assertEqual(len(capabilities.release_blockers([], reused)), len(items) - 1, "one record closes one area only")
        # forgetting the argument never hides open scope
        self.assertEqual(len(capabilities.release_blockers([])), len(items))

    def test_menu_view_only_offers_complete_entries_and_names_what_is_missing(self):
        view = capabilities.capability_view(ROWS[0]["id"], {})
        self.assertFalse(view["selectable"])
        self.assertEqual(view["label"], "not_yet_supported")
        self.assertEqual(view["missing_axes"], list(capabilities.AXES))
        self.assertEqual(capabilities.capability_view("nope", {})["label"], "unknown")
        self.assertTrue(all(leaf["existing_owner"] is not None or leaf["category"] != "class"
                            for leaf in capabilities.expand_manifest_tasks([r for r in ROWS if r["category"] == "class"])))

    def test_duplicate_ids_are_refused_and_both_ids_are_accepted(self):
        with self.assertRaises(ValueError):
            capabilities.expand_manifest_tasks([ROWS[0], ROWS[0]])
        item = capabilities.manifest_open_scope()[0]
        with self.assertRaises(ValueError):
            capabilities.expand_open_scope([item, item])
        self.assertEqual(capabilities.capability_status(ROWS[0]["id"], {})["source_id"],
                         capabilities.capability_status(ROWS[0]["source_id"], {})["source_id"])

    def test_a_registered_resolver_runs_only_for_a_complete_entry(self):
        calls = []
        capabilities.register_resolver("registered|x", lambda context, choice: calls.append(choice) or {"status": "ok", "changes": ["x"]})
        try:
            self.assertEqual(capabilities.resolve_capability("registered|x", {}, {"a": 1})["status"], "unsupported")
            self.assertEqual(calls, [], "an unknown/incomplete entry never reaches its resolver")
        finally:
            capabilities._RESOLVERS.pop("registered|x", None)

    def test_spell_progression_is_not_generalized_between_cantrip_and_slot(self):
        spell = next(r for r in ROWS if r["category"] == "spell")
        behaviors = {leaf["behavior"] for leaf in capabilities.expand_manifest_tasks([spell])}
        self.assertIn("advance.cantrip_scaling", behaviors)
        self.assertIn("advance.slot_upcast", behaviors)
        self.assertNotIn("advance", behaviors)

    def test_open_enumeration_rows_stay_open_and_never_complete(self):
        open_rows = [r for r in ROWS if r["status"] != "INVENTORIED"]
        self.assertTrue(open_rows)
        for open_row in open_rows:
            self.assertEqual(capabilities.status_of_row(open_row, {})["status"], "OPEN")
        done = {axis: "SUPPORTED" for axis in capabilities.AXES}
        forced = row(**done)
        forced["status"] = "OPEN_ENUMERATION"
        self.assertEqual(capabilities.status_of_row(forced, {})["status"], "OPEN")

    def test_unknown_entry_is_reported_not_invented_and_unsupported_use_is_refused(self):
        self.assertEqual(capabilities.capability_status("nope|x|2024", {})["status"], "UNKNOWN_ENTRY")
        known = ROWS[0]["id"]
        self.assertNotEqual(capabilities.capability_status(known, {})["status"], "COMPLETE")
        delta = capabilities.resolve_capability(known, {}, {})
        self.assertEqual(delta["status"], "unsupported")
        self.assertEqual(delta["changes"], [], "an unsupported capability changes nothing")

    def test_every_manifest_row_is_in_the_source_index_and_the_reverse(self):
        self.assertEqual({r["source_id"] for r in ROWS}, {e["source_id"] for e in INDEX["entries"]})


if __name__ == "__main__":
    unittest.main()
