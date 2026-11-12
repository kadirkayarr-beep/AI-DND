"""4C.3: Wizard and Cleric are wired classes (table in `classes/`, handler, earned and starting levels 1-5).

Values only, from the page renders (no book text): Wizard Features table PDF ordinal 165 (levels 1-5: PB 2/2/2/2/3, Cantrips
3/3/3/4/4, Prepared 4/5/6/7/9, slots {1:2}/{1:3}/{1:4,2:2}/{1:4,2:3}/{1:4,2:3,3:2}), Spellbook PDF 164 (six level-1 spells, two
Wizard spells of a slotted level at each Wizard level after 1); Cleric Features table PDF ordinal 69 (same spell columns, Channel
Divinity -/2/2/2/2), Prepared Spells PDF 68 (choose additional spells when the number grows, of a level with slots). The engine
never chooses a spell: a level step opens the preparation window (standing until the first list) and the player fills it there.
"""
import copy
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import character_progression as cp
import class_progression
import class_tables
import game
import spell_preparation
import spell_scope
import xp
from api.dnd_2024_rules import SPELLS_CATALOG
from api.main import _capture_session, _restore_session
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload
from api.tests import test_campaign_api as campaign_fixtures
from api.tests.test_economic_action_http import EconomicHttpFixture
from api.tests.test_roadmap_c06 import SPEC
from api.tests.town_seed import fixed_town

ROOT = Path(__file__).resolve().parents[3]
BOOK = ["Magic Missile", "Shield", "Mage Armor", "Detect Magic", "Sleep", "Burning Hands"]
INT_ASI = {"feat": "Ability Score Improvement", "increase": {"intelligence": 2}}
WIS_ASI = {"feat": "Ability Score Improvement", "increase": {"wisdom": 2}}
SPECS = {
    "Wizard": dict(SPEC, character_class="Wizard", cantrips=["Fire Bolt", "Mage Hand", "Light"], spells=list(BOOK),
                   proficient_skills=["Arcana", "History", "Insight", "Sleight of Hand", "Stealth"]),
    "Cleric": dict(SPEC, character_class="Cleric", cantrips=["Sacred Flame", "Guidance", "Light"], spells=["Cure Wounds", "Bless"],
                   proficient_skills=["History", "Medicine", "Insight", "Sleight of Hand", "Stealth"]),
}
CHOICES = {
    "Wizard": {"2": {"spellbook_spells": ["Thunderwave", "Feather Fall"]},
               "3": {"spellbook_spells": ["Identify", "Misty Step"], "subclass_id": "evoker"},
               "4": {"spellbook_spells": ["Charm Person", "Web"], "cantrips": ["Prestidigitation"], "asi": INT_ASI},
               "5": {"spellbook_spells": ["Fireball", "Counterspell"]}},
    "Cleric": {"2": {}, "3": {"subclass_id": "life_domain"}, "4": {"cantrips": ["Thaumaturgy"], "asi": WIS_ASI}, "5": {}},
}
THRESHOLDS = dict(xp.LEVEL_THRESHOLDS)
SLOTS = [{"1": 2}, {"1": 3}, {"1": 4, "2": 2}, {"1": 4, "2": 3}, {"1": 4, "2": 3, "3": 2}]


def source_ids(cls, level):
    data = json.loads((ROOT / "content" / "rules" / "phb2024" / "spells.json").read_text(encoding="utf-8"))["spells"]
    return sorted(name for name, spell in data.items() if spell["level"] == level and cls in spell["classes"])


def bundle(cls, level):
    return {str(n): copy.deepcopy(CHOICES[cls][str(n)]) for n in range(2, level + 1)} if level > 1 else None


def created(cls, level=1):
    session = game.create_session(seed=52)
    cp.create_at_level(session, copy.deepcopy(SPECS[cls]), level, bundle(cls, level))
    session.commit_location_change("tavern")
    session.ensure_campaign_clock()
    return session


def earn(session, level):
    gained = THRESHOLDS[level] - session.character["xp"]
    session._receive_xp_award(xp.apply_xp, session.character, session.world_state, gained, f"quest:4c3-{level}")


def step(test, session, level, choices=None):
    preview = cp.preview_level_up(session, level)
    test.assertEqual(preview["status"], "ready", preview)
    result = cp.apply_level_choices(session, preview, copy.deepcopy(CHOICES[session.character["class"]][str(level)])
                                    if choices is None else choices)
    test.assertEqual(result["status"], "applied", result)
    return result


def earned(test, cls, level):
    session = created(cls)
    spell_preparation.prepare(session, [], close=True)  # the creation window is spent: a level step opens its own
    for target in range(2, level + 1):
        earn(session, target)
        step(test, session, target)
    return session


def spells(session):
    return session.world_state["spellcasting_v1"]


def roundtrip(session, seed=19):
    payload = serialize_campaign_payload(session)
    fresh = game.create_session(seed=seed)
    restore_campaign_session(fresh, payload)
    return fresh


class SourceTables(unittest.TestCase):
    def test_tables_moved_to_classes_and_the_oracle_reads_the_one_file(self):
        for cls in ("Wizard", "Cleric"):
            with self.subTest(cls):
                path = class_tables.table_path(cls)
                self.assertEqual(path.parent.name, "classes")
                self.assertFalse((class_tables.TABLE_DIR / f"{cls.lower()}.json").exists())
                table = cp.table(cls)
                rows = [table["levels"][str(n)] for n in range(1, 6)]
                self.assertEqual([r["proficiency_bonus"] for r in rows], [2, 2, 2, 2, 3])
                self.assertEqual([r["cantrips"] for r in rows], [3, 3, 3, 4, 4])
                self.assertEqual([r["prepared_spells"] for r in rows], [4, 5, 6, 7, 9])
                self.assertEqual([r["slots"] for r in rows], SLOTS)
                self.assertEqual(class_tables.table(cls), table)
                self.assertEqual(table["source"]["unverified_cells"], [])
        self.assertEqual([cp.table("Cleric")["levels"][str(n)]["channel_divinity"] for n in range(1, 6)], [None, 2, 2, 2, 2])
        self.assertEqual(cp.table("Wizard")["source"]["class_rules"]["spellcasting_spellbook"]["pdf_page"], 164)
        self.assertEqual(cp.table("Cleric")["source"]["class_rules"]["spellcasting"]["pdf_page"], 68)

    def test_registered_handlers_and_class_constants(self):
        for cls, die, fixed in (("Wizard", 6, 4), ("Cleric", 8, 5)):
            with self.subTest(cls):
                handler = class_progression.for_class(cls)
                self.assertEqual((handler.name, cp._supported_level(cls), handler.selected_asi), (cls, 5, True))
                self.assertEqual((game.CLASS_HIT_DICE[cls], xp.FIXED_HP_BY_CLASS[cls]), (die, fixed))

    def test_level_two_and_three_lists_come_from_the_spell_source(self):
        wizard = created("Wizard")
        self.assertEqual(cp.extra_spell_ids(wizard.character, "prepared"), set())
        wizard.character.update(level=3, progression_level=3)
        self.assertEqual(cp.extra_spell_ids(wizard.character, "prepared"), set(source_ids("Wizard", 2)))
        wizard.character.update(level=5, progression_level=5)
        self.assertEqual(cp.extra_spell_ids(wizard.character, "prepared"), set(source_ids("Wizard", 2) + source_ids("Wizard", 3)))
        self.assertEqual(cp.extra_spell_ids(wizard.character, "cantrips"), set())


class LevelOneUnchanged(unittest.TestCase):
    def test_created_level_one_state_is_what_it_was_before_wiring(self):
        for cls in ("Wizard", "Cleric"):
            with self.subTest(cls):
                session = created(cls)
                self.assertEqual(cp.capacity(session.character), {"cantrips": 3, "prepared_spells": 4, "slots": {"1": 2}})
                self.assertEqual(spells(session), {
                    "version": 2, "class": cls, "cantrips": SPECS[cls]["cantrips"], "prepared": [], "slots": {"1": 2},
                    "slot_turn": None, "spellbook": BOOK if cls == "Wizard" else None,
                    "prepare_window": {"opened_second": 0, "reason": "creation"}})
                self.assertEqual(spell_scope.prepare_limit(session.character), 4)

    def test_a_version_one_wizard_still_prepares_nothing(self):
        session = created("Wizard")
        state = {k: copy.deepcopy(spells(session)[k]) for k in ("class", "cantrips", "prepared", "slots", "slot_turn")} | {"version": 1}
        spell_scope.validate(state, session.character)
        with self.assertRaises(ValueError):
            spell_scope.validate({**state, "prepared": ["Magic Missile"]}, session.character)

    def test_a_pending_xp_level_keeps_the_applied_level_one_capacity(self):
        session = created("Wizard")
        spell_preparation.prepare(session, ["Magic Missile"])
        earn(session, 3)
        self.assertEqual((session.character["level"], cp.applied_level(session.character)), (3, 1))
        self.assertEqual(cp.capacity(session.character)["slots"], {"1": 2})
        self.assertEqual(cp.preview_level_up(session, 2)["status"], "ready")

    def test_the_public_character_names_what_is_pending_only_for_a_wired_save(self):
        from api.serializers import serialize_session_state
        for cls, name in (("Wizard", "Arcane Recovery"), ("Cleric", "Divine Order")):
            with self.subTest(cls):
                session = created(cls)
                lines = serialize_session_state(session)["character"]["progression_effects_pending"]
                self.assertTrue(any(name in line for line in lines), lines)
                session.character.pop("progression_level")  # an old save that never stored the applied level
                self.assertNotIn("progression_effects_pending", serialize_session_state(session)["character"])


class EarnedProgression(unittest.TestCase):
    def test_wizard_one_to_five(self):
        session = earned(self, "Wizard", 1)
        for target in range(2, 6):
            earn(session, target)
            preview = cp.preview_level_up(session, target)
            required = {"spellbook_spells": 2, **({"subclass_id": 1} if target == 3 else {}),
                        **({"asi": 1, "cantrips": 1} if target == 4 else {})}
            self.assertEqual(preview["choices_required"], required, target)
            self.assertEqual(preview["capacity"]["slots"], SLOTS[target - 1])
            book_before = list(spells(session)["spellbook"])
            step(self, session, target)
            state = spells(session)
            self.assertEqual(state["spellbook"], book_before + CHOICES["Wizard"][str(target)]["spellbook_spells"])
            self.assertEqual(state["slots"], SLOTS[target - 1])
            self.assertEqual(state["prepare_window"], {"opened_second": spell_scope.clock_second(session.world_state), "reason": "level_up"})
            self.assertEqual(spell_scope.prepare_limit(session.character), [4, 5, 6, 7, 9][target - 1])
        self.assertEqual((session.character["progression_level"], session.character["subclass_id"]), (5, "evoker"))
        self.assertEqual(spells(session)["cantrips"], ["Fire Bolt", "Mage Hand", "Light", "Prestidigitation"])
        self.assertEqual(session.character["cantrips"], spells(session)["cantrips"])
        self.assertEqual(session.character["spells"], BOOK, "the character's creation spells are not rewritten")
        self.assertEqual(session.character["intelligence"], 12)
        result = spell_preparation.prepare(session, ["Magic Missile", "Misty Step", "Fireball"])
        self.assertEqual((result["status"], result["dropped"]), ("prepared", []))

    def test_cleric_one_to_five(self):
        session = earned(self, "Cleric", 1)
        for target in range(2, 6):
            earn(session, target)
            preview = cp.preview_level_up(session, target)
            required = {**({"subclass_id": 1} if target == 3 else {}), **({"asi": 1, "cantrips": 1} if target == 4 else {})}
            self.assertEqual(preview["choices_required"], required, target)
            step(self, session, target)
            self.assertEqual(spells(session)["slots"], SLOTS[target - 1])
            self.assertEqual(spells(session)["prepare_window"]["reason"], "level_up")
        self.assertEqual((session.character["subclass_id"], session.character["wisdom"]), ("life_domain", 14))
        self.assertEqual(spells(session)["cantrips"], ["Sacred Flame", "Guidance", "Light", "Thaumaturgy"])
        result = spell_preparation.prepare(session, ["Bless", "Aid", "Revivify"])
        self.assertEqual((result["status"], result["prepared"]), ("prepared", ["Bless", "Aid", "Revivify"]))

    def test_a_level_two_spell_needs_level_two_slots(self):
        session = earned(self, "Cleric", 2)
        self.assertEqual(spell_preparation.prepare(session, ["Aid"])["dropped"], [{"spell_id": "Aid", "reason": "not_on_class_list"}])
        wizard = earned(self, "Wizard", 1)
        earn(wizard, 2)
        preview = cp.preview_level_up(wizard, 2)
        self.assertEqual(sorted(preview["spellbook_spell_ids"]), sorted(set(s["id"] for s in SPELLS_CATALOG["Wizard"]["spells_level_1"]) - set(BOOK)))
        self.assertEqual(cp.apply_level_choices(wizard, preview, {"spellbook_spells": ["Misty Step", "Identify"]})["reason"], "spellbook_spells_invalid")
        earn(wizard, 3)
        step(self, wizard, 2)
        self.assertIn("Misty Step", cp.preview_level_up(wizard, 3)["spellbook_spell_ids"])
        self.assertNotIn("Fireball", cp.preview_level_up(wizard, 3)["spellbook_spell_ids"])

    def test_the_level_window_stands_until_the_first_list(self):
        session = earned(self, "Wizard", 2)
        session.advance_campaign_time(3600, "wait")
        self.assertTrue(spell_preparation.window_open(session))
        spell_preparation.prepare(session, ["Thunderwave"])
        self.assertIsNone(spells(session)["prepare_window"])
        created_session = created("Wizard")
        earn(created_session, 2)
        step(self, created_session, 2)
        self.assertEqual(spells(created_session)["prepare_window"]["reason"], "creation", "an unspent creation window is kept")

    def test_choice_refusals_change_nothing(self):
        session = earned(self, "Wizard", 3)
        earn(session, 4)
        preview = cp.preview_level_up(session, 4)
        good = CHOICES["Wizard"]["4"]
        bad = [({**good, "spellbook_spells": ["Web"]}, "spellbook_spells_invalid"),
               ({**good, "spellbook_spells": ["Web", "Web"]}, "spellbook_spells_invalid"),
               ({**good, "spellbook_spells": ["Web", "Magic Missile"]}, "spellbook_spells_invalid"),
               ({**good, "spellbook_spells": ["Web", "Fireball"]}, "spellbook_spells_invalid"),
               ({**good, "cantrips": ["Fire Bolt"]}, "cantrips_invalid"),
               ({**good, "cantrips": ["Sacred Flame"]}, "cantrips_invalid"),
               ({**good, "cantrips": []}, "cantrips_invalid"),
               ({**good, "asi": {"feat": "Ability Score Improvement", "increase": {"intelligence": 3}}}, "selected_asi_not_supported"),
               ({"spellbook_spells": ["Web", "Blur"], "cantrips": ["Prestidigitation"]}, "selected_asi_not_supported"),
               ({**good, "subclass_id": "evoker"}, "unsupported_choice")]
        before = session._capture_runtime_snapshot()
        for choices, reason in bad:
            with self.subTest(choices):
                self.assertEqual(cp.apply_level_choices(session, preview, choices)["reason"], reason)
                self.assertEqual(session._capture_runtime_snapshot(), before)
        cleric = earned(self, "Cleric", 2)
        earn(cleric, 3)
        preview = cp.preview_level_up(cleric, 3)
        self.assertEqual(preview["subclass_options"], [{"id": "life_domain", "name": "Life Domain"}])
        self.assertEqual(cp.apply_level_choices(cleric, preview, {"subclass_id": "war_domain"})["reason"], "subclass_invalid")

    def test_a_failed_step_leaves_nothing(self):
        for cls in ("Wizard", "Cleric"):
            for level in (2, 3, 4, 5):
                with self.subTest(cls=cls, level=level):
                    session = earned(self, cls, level - 1)
                    earn(session, level)
                    preview = cp.preview_level_up(session, level)
                    before = session._capture_runtime_snapshot()
                    with patch.object(cp, "validate_saved", side_effect=ValueError("forced")):
                        result = cp.for_class(cls).apply_level(session, preview, copy.deepcopy(CHOICES[cls][str(level)]))
                    self.assertEqual(result["reason"], "resulting_state_invalid")
                    self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_a_step_applies_once_and_level_six_stays_closed(self):
        session = earned(self, "Cleric", 1)
        earn(session, 2)
        preview = cp.preview_level_up(session, 2)
        self.assertEqual(cp.apply_level_choices(session, preview, {})["status"], "applied")
        self.assertEqual(cp.apply_level_choices(session, preview, {})["reason"], "already_applied")
        self.assertEqual(cp.preview_level_up(earned(self, "Wizard", 5), 6)["reason"], "progression_level_not_supported")

    def test_a_wizard_without_a_spellbook_cannot_advance(self):
        session = created("Wizard")
        state = spells(session)
        session.world_state["spellcasting_v1"] = {k: copy.deepcopy(state[k]) for k in ("class", "cantrips", "prepared", "slots", "slot_turn")} | {"version": 1}
        session.character["spells"] = []
        earn(session, 2)
        self.assertEqual(cp.preview_level_up(session, 2)["reason"], "wizard_spellbook_missing")

    def test_pending_features_are_named_not_invented(self):
        wizard = cp.progression_disclosure("Wizard", 5)
        cleric = cp.progression_disclosure("Cleric", 5)
        for name in ("Arcane Recovery", "Ritual Adept", "Scholar", "Memorize Spell", "Evoker"):
            self.assertTrue(any(name in line for line in wizard["pending"]), name)
        for name in ("Divine Order", "Channel Divinity", "Life Domain", "Sear Undead"):
            self.assertTrue(any(name in line for line in cleric["pending"]), name)
        for disclosure in (wizard, cleric):
            self.assertFalse(any(name in line for line in disclosure["supported"]
                                 for name in ("Arcane Recovery", "Channel Divinity", "Disciple of Life", "Sear Undead")))


class StartingLevels(unittest.TestCase):
    def test_every_start_reaches_the_applied_level_through_the_same_steps(self):
        for cls in ("Wizard", "Cleric"):
            for level in (2, 3, 4, 5):
                with self.subTest(cls=cls, level=level):
                    session = created(cls, level)
                    self.assertEqual((session.character["progression_level"], session.character["level"]), (level, level))
                    self.assertEqual(spells(session)["slots"], SLOTS[level - 1])
                    self.assertEqual(spells(session)["prepare_window"]["reason"], "creation")
                    self.assertEqual(session.character["current_hp"], session.character["max_hp"])

    def test_start_bundles_are_exact(self):
        for cls in ("Wizard", "Cleric"):
            with self.subTest(cls):
                session = game.create_session(seed=52)
                before = session._capture_runtime_snapshot()
                with self.assertRaises(ValueError):
                    cp.create_at_level(session, copy.deepcopy(SPECS[cls]), 3, {"2": CHOICES[cls]["2"]})
                with self.assertRaises(ValueError):
                    cp.create_at_level(session, copy.deepcopy(SPECS[cls]), 2, {"2": {**CHOICES[cls]["2"], "subclass_id": "x"}})
                with self.assertRaises(ValueError):
                    cp.create_at_level(session, copy.deepcopy(SPECS[cls]), 6, bundle(cls, 5))
                self.assertEqual(session._capture_runtime_snapshot(), before)


class SavedState(unittest.TestCase):
    def test_round_trip_keeps_choices_and_spells(self):
        for cls in ("Wizard", "Cleric"):
            with self.subTest(cls):
                session = earned(self, cls, 5)
                fresh = roundtrip(session)
                for field in ("progression_level", "subclass_id", "asi_choices", "spells", "cantrips", "level", "max_hp"):
                    self.assertEqual(fresh.character[field], session.character[field], field)
                self.assertEqual(fresh.world_state["spellcasting_v1"], spells(session))
                self.assertTrue(spell_preparation.window_open(fresh))

    def test_a_legacy_wizard_without_progression_level_loads_and_advances(self):
        session = created("Wizard")
        session.character.pop("progression_level")
        fresh = roundtrip(session)
        self.assertEqual(cp.applied_level(fresh.character), 1)
        earn(fresh, 2)
        step(self, fresh, 2)
        self.assertEqual(fresh.character["progression_level"], 2)

    def forged(self, cls, level, mutate):
        session = earned(self, cls, level)
        mutate(session)
        with self.assertRaises(ValueError):
            cp.validate_saved(session.character, session.world_state)
            spell_scope.validate(spells(session), session.character)

    def test_forged_saves_fail_closed(self):
        cases = [
            ("Wizard", 2, lambda s: s.character.update(subclass_id="evoker")),
            ("Wizard", 3, lambda s: s.character.update(subclass_id="abjurer")),
            ("Wizard", 3, lambda s: s.character.pop("subclass_id")),
            ("Cleric", 3, lambda s: s.character.update(subclass_id="evoker")),
            ("Wizard", 1, lambda s: s.character.update(metamagic=["Quickened Spell"])),
            ("Wizard", 4, lambda s: spells(s)["cantrips"].pop()),
            ("Cleric", 4, lambda s: spells(s)["cantrips"].pop()),
            ("Wizard", 2, lambda s: spells(s)["spellbook"].pop()),
            ("Wizard", 2, lambda s: spells(s)["spellbook"].append("Misty Step")),
            ("Wizard", 2, lambda s: spells(s).update(prepare_window={"opened_second": 0, "reason": "level-up"})),
            ("Cleric", 2, lambda s: spells(s).update(prepared=["Aid"])),
            ("Cleric", 5, lambda s: spells(s).update(slots={"1": 4, "2": 3, "3": 3})),
        ]
        for cls, level, mutate in cases:
            with self.subTest(cls=cls, level=level):
                self.forged(cls, level, mutate)

    def test_the_whole_save_payload_admits_a_level_five_caster(self):
        for cls in ("Wizard", "Cleric"):
            with self.subTest(cls):
                session = earned(self, cls, 5)
                session._validate_save_payload(session.serialize_game_state())

    def test_undo_snapshot_restores_the_level_step(self):
        for cls in ("Wizard", "Cleric"):
            with self.subTest(cls):
                session = earned(self, cls, 3)
                earn(session, 4)
                before = copy.deepcopy(session.serialize_game_state())
                snapshot = _capture_session(session)
                step(self, session, 4)
                self.assertNotEqual(session.serialize_game_state(), before)
                _restore_session(session, snapshot)
                self.assertEqual(session.serialize_game_state(), before)
                step(self, session, 4)  # the same step again after the restore applies exactly once
                self.assertEqual(session.character["progression_level"], 4)


class LevelUpApi(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaign_fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_fixtures.CampaignApiTests.asyncTearDown

    async def start(self, cls, seed):
        data = copy.deepcopy(SPECS[cls])
        data["class"] = data.pop("character_class")
        data.update(mode="custom", starting_level=1)
        with fixed_town(self, seed):
            response = await self.http.post("/api/game/campaigns", json={"character": data})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        session = self.manager.get(body["session_id"]).game_session
        session._receive_xp_award(xp.apply_xp, session.character, session.world_state, 300, "quest:4c3-http")
        self.manager.save_campaign(body["campaign_id"])
        return body, session

    async def level_up(self, body, choices):
        url = f"/api/game/sessions/{body['session_id']}/level-up"
        preview = await self.http.get(url)
        self.assertEqual(preview.status_code, 200, preview.text)
        p = preview.json()
        self.assertEqual((p["status"], p["target_level"]), ("ready", 2), p)
        request = dict(action_id=str(uuid.uuid4()), campaign_id=body["campaign_id"], expected_revision=p["revision"],
                       target_level=2, choices=choices)
        response = await self.http.post(url, json=request)
        self.assertEqual(response.status_code, 200, response.text)
        return p, request, response.json()

    async def test_wizard_and_cleric_preview_apply_replay_reload(self):
        from api.session_manager import SessionManager
        from api.persistence.campaign_store import CampaignStore
        from api.tests.auth_fixture import TEST_PLAYER
        for cls, seed, choices in (("Wizard", 4401, {"spellbook_spells": ["Thunderwave", "Feather Fall"]}), ("Cleric", 4411, {})):
            with self.subTest(cls):
                body, session = await self.start(cls, seed)
                p, request, applied = await self.level_up(body, choices)
                self.assertEqual(p["choices_required"], {"spellbook_spells": 2} if cls == "Wizard" else {})
                if cls == "Wizard":
                    self.assertEqual(sorted(p["spellbook_spell_ids"]), ["Charm Person", "Feather Fall", "Identify", "Thunderwave"])
                self.assertEqual(session.character["progression_level"], 2)
                saved = copy.deepcopy(session.serialize_game_state())
                url = f"/api/game/sessions/{body['session_id']}/level-up"
                again = await self.http.post(url, json=request)
                self.assertEqual((again.status_code, again.json()), (200, applied))
                self.assertEqual(session.serialize_game_state(), saved)
                manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
                _, record, *_ = manager.resume_campaign(body["campaign_id"])
                self.assertEqual(record.game_session.world_state["spellcasting_v1"], saved["world_state"]["spellcasting_v1"])
                self.assertEqual(record.game_session.character["progression_level"], 2)

    async def test_a_wrong_class_shape_is_refused_without_change(self):
        body, session = await self.start("Cleric", 4421)
        url = f"/api/game/sessions/{body['session_id']}/level-up"
        p = (await self.http.get(url)).json()
        before = copy.deepcopy(session.serialize_game_state())
        response = await self.http.post(url, json=dict(action_id=str(uuid.uuid4()), campaign_id=body["campaign_id"],
                                                       expected_revision=p["revision"], target_level=2,
                                                       choices={"spellbook_spells": ["Thunderwave", "Feather Fall"]}))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(session.serialize_game_state(), before)


def fight_and_cast_magic_missile(test, session):
    """A real fight with one enemy at 30 ft; Magic Missile from the prepared list spends a level-1 slot; the fight ends."""
    import bounded_encounter
    import spell_registry
    from api.tests import test_death_system as fixtures
    session.world_state["npcs"] = [n for n in session.world_state["npcs"] if n["id"] != "death-save-enemy"]
    fixtures.start_test_combat(session)
    enemy = session.world_state["npcs"][-1]
    enemy.update(current_hp=100, max_hp=100, distance_ft=30, monster_stat_block=copy.deepcopy(bounded_encounter.COMMONER))
    session.world_state["equipment"] = {"main_hand": None, "off_hand": None}
    session.world_state["attack_environment"] = {"pairs": {"player|" + enemy["id"]: {
        "distance_ft": 30, "attacker_sees_target": True, "target_sees_attacker": True, "cover": "none"}}}
    session.ensure_combat_state()
    with patch.object(session.rng, "randint", return_value=3):
        cast = spell_registry.cast_spell("Magic Missile", {"session": session}, 1, {"target_id": enemy["id"]})
    test.assertEqual(cast["status"], "applied", cast)
    session.end_combat("test")


class LevelUpWindowIsAdditive(unittest.TestCase):
    """Review finding 1: a level step opens a window that only ADDS to today's list; swapping the list needs a Long Rest."""

    def leveled_with_list_a(self):
        session = earned(self, "Wizard", 1)
        session.resolve_species_trait_action("long_rest")
        self.assertEqual(spell_preparation.prepare(session, ["Magic Missile", "Shield"])["status"], "prepared")
        earn(session, 2)
        step(self, session, 2)
        self.assertEqual(spells(session)["prepare_window"]["reason"], "level_up")
        return session

    def test_the_probe_level_up_fight_cast_then_a_new_list_is_refused(self):
        session = self.leveled_with_list_a()
        fight_and_cast_magic_missile(self, session)
        self.assertTrue(spell_preparation.window_open(session))
        before = copy.deepcopy(session.serialize_game_state())
        for requested in (["Thunderwave", "Feather Fall"], ["Magic Missile", "Thunderwave"], []):
            with self.subTest(requested):
                with self.assertRaises(spell_preparation.PrepareRefused) as caught:
                    spell_preparation.prepare(session, requested)
                self.assertEqual(caught.exception.code, "prepare_level_up_additive_only")
                self.assertIn("Shield", str(caught.exception))
                self.assertEqual(session.serialize_game_state(), before)

    def test_an_additive_list_is_saved_and_closes_the_window(self):
        session = self.leveled_with_list_a()
        fight_and_cast_magic_missile(self, session)
        wanted = ["Shield", "Magic Missile", "Thunderwave", "Feather Fall", "Sleep"]
        result = spell_preparation.prepare(session, wanted)
        self.assertEqual((result["status"], result["prepared"]), ("prepared", wanted))
        self.assertIsNone(spells(session)["prepare_window"])

    def test_a_plain_done_keeps_the_list_and_a_long_rest_window_still_swaps(self):
        session = self.leveled_with_list_a()
        self.assertEqual(spell_preparation.prepare(session, None, close=True)["prepared"], ["Magic Missile", "Shield"])
        session.advance_campaign_time(16 * 3600, "wait")  # a new Long Rest needs 16 hours after the last one
        session.resolve_species_trait_action("long_rest")
        self.assertEqual(spell_preparation.prepare(session, ["Thunderwave"])["prepared"], ["Thunderwave"])

    def test_too_many_is_still_asked_after_the_additive_check(self):
        session = self.leveled_with_list_a()
        result = spell_preparation.prepare(session, ["Magic Missile", "Shield", "Thunderwave", "Feather Fall", "Sleep", "Mage Armor"])
        self.assertEqual((result["status"], result["excess"]), ("too_many", 1))


class LevelUpApiHigherLevels(LevelUpApi):
    async def step(self, body, session, target, amount, choices, expected_required):
        session._receive_xp_award(xp.apply_xp, session.character, session.world_state, amount, f"quest:4c3-http-{target}")
        self.manager.save_campaign(body["campaign_id"])
        url = f"/api/game/sessions/{body['session_id']}/level-up"
        p = (await self.http.get(url)).json()
        self.assertEqual((p["status"], p["target_level"], p["choices_required"]), ("ready", target, expected_required), p)
        request = dict(action_id=str(uuid.uuid4()), campaign_id=body["campaign_id"], expected_revision=p["revision"],
                       target_level=target, choices=copy.deepcopy(choices))
        response = await self.http.post(url, json=request)
        self.assertEqual(response.status_code, 200, response.text)
        again = await self.http.post(url, json=request)
        self.assertEqual((again.status_code, again.json()), (200, response.json()))
        return p

    async def test_levels_three_to_five_over_http(self):
        from api.session_manager import SessionManager
        from api.persistence.campaign_store import CampaignStore
        from api.tests.auth_fixture import TEST_PLAYER
        for cls, seed in (("Wizard", 4431), ("Cleric", 4441)):
            with self.subTest(cls):
                body, session = await self.start(cls, seed)
                await self.level_up(body, CHOICES[cls]["2"])
                wizard = cls == "Wizard"
                p3 = await self.step(body, session, 3, 600, CHOICES[cls]["3"],
                                     {**({"spellbook_spells": 2} if wizard else {}), "subclass_id": 1})
                self.assertEqual(p3["subclass_options"], [{"id": CHOICES[cls]["3"]["subclass_id"],
                                                           "name": "Evoker" if wizard else "Life Domain"}])
                if wizard:
                    self.assertIn("Misty Step", p3["spellbook_spell_ids"])
                p4 = await self.step(body, session, 4, 1800, CHOICES[cls]["4"],
                                     {**({"spellbook_spells": 2} if wizard else {}), "asi": 1, "cantrips": 1})
                self.assertIn(CHOICES[cls]["4"]["cantrips"][0], p4["cantrip_ids"])
                self.assertIn(CHOICES[cls]["4"]["asi"], p4["supported_asi_choices"])
                p5 = await self.step(body, session, 5, 3800, CHOICES[cls]["5"], {"spellbook_spells": 2} if wizard else {})
                self.assertEqual(p5["capacity"]["slots"], SLOTS[4])
                view = await self.http.get(f"/api/game/sessions/{body['session_id']}/spellcasting/prepare")
                self.assertEqual(view.status_code, 200, view.text)
                self.assertEqual((view.json()["open"], view.json()["limit"]), (True, 9))
                self.assertIn(view.json()["reason"], ("creation", "level_up"))
                saved = copy.deepcopy(session.serialize_game_state())
                manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
                _, record, *_ = manager.resume_campaign(body["campaign_id"])
                self.assertEqual(record.game_session.world_state["spellcasting_v1"], saved["world_state"]["spellcasting_v1"])
                self.assertEqual((record.game_session.character["progression_level"], record.game_session.character["subclass_id"]),
                                 (5, CHOICES[cls]["3"]["subclass_id"]))

    async def test_the_additive_rule_over_http(self):
        body, session = await self.start("Cleric", 4451)
        url = f"/api/game/sessions/{body['session_id']}/spellcasting/prepare"
        first = await self.http.post(url, json={"action_id": str(uuid.uuid4()), "prepared": ["Bless", "Cure Wounds"]})
        self.assertEqual(first.status_code, 200, first.text)
        await self.level_up(body, {})
        view = await self.http.get(url)
        self.assertEqual(view.status_code, 200, view.text)
        self.assertEqual((view.json()["open"], view.json()["reason"]), (True, "level_up"))
        before = copy.deepcopy(session.serialize_game_state())
        swap = await self.http.post(url, json={"action_id": str(uuid.uuid4()), "prepared": ["Command", "Bane"]})
        self.assertEqual(swap.status_code, 409, swap.text)
        self.assertEqual(swap.json()["detail"]["code"], "prepare_level_up_additive_only")
        self.assertEqual(session.serialize_game_state(), before)
        request = {"action_id": str(uuid.uuid4()), "prepared": ["Bless", "Cure Wounds", "Command"]}
        added = await self.http.post(url, json=request)
        self.assertEqual(added.status_code, 200, added.text)
        self.assertEqual(session.world_state["spellcasting_v1"]["prepared"], ["Bless", "Cure Wounds", "Command"])
        saved = copy.deepcopy(session.serialize_game_state())
        again = await self.http.post(url, json=request)
        self.assertEqual((again.status_code, again.json()), (200, added.json()))
        self.assertEqual(session.serialize_game_state(), saved)


class UndoWithALevelUpWindow(EconomicHttpFixture):
    """A real turn taken while a level_up window is open: Undo gives back exactly the window and the list."""

    async def asyncSetUp(self):
        with fixed_town(self, 4461):
            await EconomicHttpFixture.asyncSetUp(self)
        self.sid = self.campaign["session_id"]

    async def test_undo_of_a_turn_restores_the_open_level_up_window(self):
        from api.tests.test_spell_preparation_4c2 import prepper
        session = prepper("Wizard", self.record.game_session)
        state = session.world_state["spellcasting_v1"]
        state["prepared"] = ["Magic Missile"]
        state["prepare_window"] = {"opened_second": spell_scope.clock_second(session.world_state), "reason": "level_up"}
        self.save()
        spells_before = copy.deepcopy(state)
        turn_id, _ = await self.real_turn()
        undone = await self.undo(turn_id)
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.record.game_session.world_state["spellcasting_v1"], spells_before)
        self.assertEqual(self.store.get_campaign(self.campaign["campaign_id"]).payload["engine_save"]["world_state"]
                         ["spellcasting_v1"], spells_before)
        self.assertTrue(spell_preparation.window_open(self.record.game_session))
        url = f"/api/game/sessions/{self.sid}/spellcasting/prepare"
        refused = await self.http.post(url, json={"action_id": str(uuid.uuid4()), "prepared": ["Shield"]})
        self.assertEqual(refused.json()["detail"]["code"], "prepare_level_up_additive_only")
        added = await self.http.post(url, json={"action_id": str(uuid.uuid4()), "prepared": ["Magic Missile", "Shield"]})
        self.assertEqual(added.status_code, 200, added.text)

if __name__ == "__main__":
    unittest.main()
