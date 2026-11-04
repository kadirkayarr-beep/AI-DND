"""The journey scenario file: a strict loader (typos fail loudly) and the expectation checker."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from api.tests.journeys.schema import (
    EXPECT_KEYS,
    Scenario,
    ScenarioError,
    Step,
    check_expect,
    load_scenario,
)

_TEMP: tempfile.TemporaryDirectory | None = None


def setUpModule():
    global _TEMP
    _TEMP = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(_TEMP.cleanup)


def write_scenario(data, *, raw: str | None = None) -> Path:
    folder = Path(tempfile.mkdtemp(dir=_TEMP.name))
    path = folder / "scenario.json"
    path.write_text(raw if raw is not None else json.dumps(data), encoding="utf-8")
    return path


def small_scenario(**changes) -> dict:
    data = {
        "id": "01_bira",
        "title": "Bira alinir",
        "source_items": [35],
        "setup": {"seed": 7},
        "steps": [{"say": "bir bira alayim", "expect": {"kese": 96}}],
    }
    data.update(changes)
    return data


class TheLoaderIsStrict(unittest.TestCase):
    def test_a_small_scenario_loads_with_defaults(self):
        scenario = load_scenario(write_scenario(small_scenario()))
        self.assertIsInstance(scenario, Scenario)
        self.assertEqual(scenario.id, "01_bira")
        self.assertEqual(scenario.source_items, (35,))
        self.assertFalse(scenario.zero_tolerance)
        self.assertFalse(scenario.real_chain_core)
        self.assertEqual(scenario.setup, {"seed": 7})
        (step,) = scenario.steps
        self.assertIsInstance(step, Step)
        self.assertEqual(step.say, "bir bira alayim")
        self.assertIsNone(step.command)
        self.assertEqual(step.expect, {"kese": 96})
        self.assertEqual(step.known_broken, ())
        self.assertFalse(step.real_chain)
        self.assertFalse(step.independent)

    def test_every_documented_step_field_loads(self):
        data = small_scenario(
            zero_tolerance=False,
            real_chain_core=True,
            steps=[
                {
                    "economic_action": {"action": "confirm"},
                    "script": {"front": {"coin_cp": 500}},
                    "expect": {"kart": None},
                    "known_broken": [3, 35],
                    "real_chain": True,
                    "independent": True,
                }
            ],
        )
        scenario = load_scenario(write_scenario(data))
        (step,) = scenario.steps
        self.assertEqual(step.economic_action, {"action": "confirm"})
        self.assertEqual(step.script, {"front": {"coin_cp": 500}})
        self.assertEqual(step.known_broken, (3, 35))
        self.assertTrue(step.real_chain)
        self.assertTrue(step.independent)
        self.assertTrue(scenario.real_chain_core)

    def test_unknown_key_is_rejected(self):
        for label, data, needle in (
            ("scenario", small_scenario(titel="typo"), "titel"),
            (
                "step",
                small_scenario(steps=[{"say": "x", "expcet": {}}]),
                "expcet",
            ),
        ):
            with self.subTest(label), self.assertRaises(ScenarioError) as raised:
                load_scenario(write_scenario(data))
            self.assertIn(needle, str(raised.exception))

    def test_a_duplicate_json_key_is_rejected(self):
        raw = '{"id": "a", "title": "t", "steps": [{"say": "x"}], "title": "u"}'
        with self.assertRaises(ScenarioError) as raised:
            load_scenario(write_scenario(None, raw=raw))
        self.assertIn("title", str(raised.exception))

    def test_unknown_expect_key_is_rejected(self):
        data = small_scenario(steps=[{"say": "x", "expect": {"kese": 1, "kesee": 2}}])
        with self.assertRaises(ScenarioError) as raised:
            load_scenario(write_scenario(data))
        self.assertIn("kesee", str(raised.exception))

    def test_the_expect_key_set_is_exactly_the_documented_one(self):
        self.assertEqual(
            set(EXPECT_KEYS),
            {
                "kese", "envanter", "oda", "kip", "savas", "konum", "hp",
                "kart", "tezgah", "kisi_kese", "olu", "yasak_metin", "gerekli_metin",
            },
        )

    def test_step_needs_exactly_one_action(self):
        for label, step in (
            ("none", {"expect": {"kese": 1}}),
            ("two", {"say": "x", "command": "/item shop_buy 1"}),
            ("three", {"say": "x", "economic_action": {}, "combat_action": {}}),
        ):
            with self.subTest(label), self.assertRaises(ScenarioError):
                load_scenario(write_scenario(small_scenario(steps=[step])))

    def test_zero_tolerance_scenario_cannot_carry_known_broken(self):
        data = small_scenario(
            zero_tolerance=True,
            steps=[{"say": "x", "known_broken": [29]}],
        )
        with self.assertRaises(ScenarioError) as raised:
            load_scenario(write_scenario(data))
        self.assertIn("known_broken", str(raised.exception))

    def test_zero_tolerance_with_an_empty_known_broken_is_fine(self):
        data = small_scenario(zero_tolerance=True, steps=[{"say": "x", "known_broken": []}])
        self.assertTrue(load_scenario(write_scenario(data)).zero_tolerance)

    def test_wrong_value_types_are_rejected(self):
        for label, data in (
            ("id", small_scenario(id=7)),
            ("empty id", small_scenario(id="")),
            ("source_items", small_scenario(source_items=["35"])),
            ("bool item", small_scenario(source_items=[True])),
            ("setup", small_scenario(setup=[1])),
            ("zero_tolerance", small_scenario(zero_tolerance="yes")),
            ("no steps", small_scenario(steps=[])),
            ("steps", small_scenario(steps={"say": "x"})),
            ("step", small_scenario(steps=["say x"])),
            ("say", small_scenario(steps=[{"say": 3}])),
            ("empty say", small_scenario(steps=[{"say": ""}])),
            ("action dict", small_scenario(steps=[{"economic_action": "confirm"}])),
            ("expect", small_scenario(steps=[{"say": "x", "expect": [1]}])),
            ("known_broken", small_scenario(steps=[{"say": "x", "known_broken": "3"}])),
            ("real_chain", small_scenario(steps=[{"say": "x", "real_chain": 1}])),
        ):
            with self.subTest(label), self.assertRaises(ScenarioError):
                load_scenario(write_scenario(data))

    def test_missing_required_keys_are_rejected(self):
        for key in ("id", "title", "steps"):
            data = small_scenario()
            del data[key]
            with self.subTest(key), self.assertRaises(ScenarioError) as raised:
                load_scenario(write_scenario(data))
            self.assertIn(key, str(raised.exception))

    def test_unreadable_or_malformed_files_raise_scenario_error(self):
        missing = Path(_TEMP.name) / "nowhere" / "scenario.json"
        with self.assertRaises(ScenarioError):
            load_scenario(missing)
        with self.assertRaises(ScenarioError):
            load_scenario(write_scenario(None, raw="{not json"))
        with self.assertRaises(ScenarioError):
            load_scenario(write_scenario(["a list"]))

    def test_errors_name_the_file_and_the_step(self):
        path = write_scenario(small_scenario(steps=[{"say": "ok"}, {"say": "x", "oops": 1}]))
        with self.assertRaises(ScenarioError) as raised:
            load_scenario(path)
        message = str(raised.exception)
        self.assertIn("scenario.json", message)
        self.assertIn("2", message)


class TheCheckerReportsInTurkish(unittest.TestCase):
    def test_check_expect_passes_when_everything_matches(self):
        expected = {
            "kese": 96,
            "envanter": {"Bira": 1},
            "oda": False,
            "kip": {"active": False},
            "savas": False,
            "konum": "tavern",
            "hp": 12,
            "kart": None,
            "olu": "alive",
            "yasak_metin": ["/__direct_shop_buy__"],
            "gerekli_metin": "bira",
        }
        observed = {
            "kese": 96,
            "envanter": {"Bira": 1},
            "oda": False,
            "kip": {"active": False, "with": None},
            "savas": False,
            "konum": "tavern",
            "hp": 12,
            "kart": None,
            "olu": "alive",
            "narration": "Barmen Bira getirir.",
        }
        self.assertEqual(check_expect(expected, observed), [])

    def test_check_expect_reports_each_mismatch_in_turkish(self):
        problems = check_expect(
            {"kese": 100, "hp": 12, "konum": "street"},
            {"kese": 96, "hp": 12, "konum": "tavern"},
        )
        self.assertEqual(
            problems,
            ["kese: beklenen 100, gözlenen 96", "konum: beklenen street, gözlenen tavern"],
        )

    def test_check_expect_ignores_observed_keys_the_step_does_not_expect(self):
        self.assertEqual(check_expect({"kese": 5}, {"kese": 5, "hp": 1, "oda": True}), [])

    def test_check_expect_says_so_when_a_key_was_not_observed(self):
        self.assertEqual(
            check_expect({"kese": 5}, {}),
            ["kese: beklenen 5, gözlenen yok"],
        )

    def test_check_expect_compares_the_inventory_exactly(self):
        problems = check_expect(
            {"envanter": {"Bira": 1}},
            {"envanter": {"Bira": 1, "Ekmek": 1}},
        )
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("envanter: beklenen"))

    def test_check_expect_matches_card_and_mode_by_the_keys_asked_for(self):
        observed = {"kart": {"max_total_cp": 5, "counterparty_label": "Barmen"}}
        self.assertEqual(check_expect({"kart": {"max_total_cp": 5}}, observed), [])
        self.assertEqual(
            check_expect({"kart": {"max_total_cp": 4}}, observed),
            ["kart.max_total_cp: beklenen 4, gözlenen 5"],
        )
        self.assertEqual(
            check_expect({"kart": None}, observed),
            ["kart: beklenen yok, gözlenen {'max_total_cp': 5, 'counterparty_label': 'Barmen'}"],
        )
        self.assertEqual(
            check_expect({"kart": {"max_total_cp": 5}}, {"kart": None}),
            ["kart: beklenen {'max_total_cp': 5}, gözlenen yok"],
        )

    def test_check_expect_matches_the_counter_offer_and_other_purses_by_the_keys_asked_for(self):
        observed = {"tezgah": {"npc_id": "barman", "key": "bira", "unit_cp": 4},
                    "kisi_kese": {"barman": 4, "guard": 0}}
        self.assertEqual(check_expect({"tezgah": {"key": "bira"}, "kisi_kese": {"barman": 4}}, observed), [])
        self.assertEqual(
            check_expect({"tezgah": {"unit_cp": 5}, "kisi_kese": {"barman": 5}}, observed),
            ["tezgah.unit_cp: beklenen 5, gözlenen 4", "kisi_kese.barman: beklenen 5, gözlenen 4"],
        )
        self.assertEqual(
            check_expect({"tezgah": None}, observed),
            ["tezgah: beklenen yok, gözlenen {'npc_id': 'barman', 'key': 'bira', 'unit_cp': 4}"],
        )
        self.assertEqual(
            check_expect({"tezgah": {"key": "bira"}}, {"tezgah": None}),
            ["tezgah: beklenen {'key': 'bira'}, gözlenen yok"],
        )

    def test_check_expect_forbidden_text_is_case_insensitive(self):
        problems = check_expect(
            {"yasak_metin": "/__DIRECT_shop_buy__"},
            {"narration": "Sohbette /__direct_SHOP_buy__ 1 gorundu."},
        )
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("yasak_metin:"))
        self.assertIn("/__DIRECT_shop_buy__", problems[0])

    def test_check_expect_forbidden_text_list_reports_each_hit(self):
        problems = check_expect(
            {"yasak_metin": ["kilic", "kalkan", "ok"]},
            {"narration": "Kilic ve Kalkan."},
        )
        self.assertEqual(len(problems), 2)

    def test_check_expect_forbidden_text_passes_when_absent_or_unnarrated(self):
        self.assertEqual(check_expect({"yasak_metin": "x"}, {"narration": "temiz"}), [])
        self.assertEqual(check_expect({"yasak_metin": "x"}, {}), [])

    def test_check_expect_required_text_is_case_insensitive_and_reported_when_missing(self):
        self.assertEqual(
            check_expect({"gerekli_metin": "ODA TUTULDU"}, {"narration": "Oda tutuldu."}),
            [],
        )
        problems = check_expect({"gerekli_metin": "oda tutuldu"}, {"narration": "Selam."})
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("gerekli_metin:"))
        self.assertEqual(len(check_expect({"gerekli_metin": "x"}, {})), 1)

    def test_check_expect_rejects_a_key_the_schema_does_not_know(self):
        with self.assertRaises(ScenarioError):
            check_expect({"kesee": 1}, {"kese": 1})


if __name__ == "__main__":
    unittest.main()
