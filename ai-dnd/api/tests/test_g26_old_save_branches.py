"""G2.6 (D-525, D-524, D-576, D-538, D-505): the old-save branches are gone; a new campaign keeps its whole round trip.

Owner rule: old saves do not matter. A save older than format 4 is refused with a clear error, a combat that is not the
schema-3 shape is refused, a Wizard whose state has no spellbook is refused (nothing migrates or chooses a book for
it), and the dialogue mode accepts only unset or ``free_v1``. A new campaign still plays a turn, saves, loads and undoes
back to the same state.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path

import dialogue_runtime
import game
import spell_preparation
from api.tests import test_roadmap_r04_commit_boundary as r04
from api.tests.test_economic_action_http import EconomicHttpFixture
from api.tests.test_spell_preparation_4c2 import prepper, v1_of
from api.tests.town_seed import fixed_town

SIX = ["Shield", "Sleep", "Identify", "Charm Person", "Feather Fall", "Thunderwave"]


def written(session, directory, name):
    path = Path(directory) / name
    session.save_game(path)
    return path


class TestOldSaveVersionsAreRefused(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = directory.name

    def test_a_save_older_than_format_four_is_refused_with_a_clear_error(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                session = game.create_session(seed=2601)
                payload = session.serialize_game_state()
                before = copy.deepcopy(payload)
                payload["version"] = version
                payload["player"].pop("weapon_proficiencies", None)
                path = Path(self.directory) / f"v{version}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "desteklenmiyor"):
                    session.load_game(path)
                with self.assertRaisesRegex(ValueError, "desteklenmiyor"):
                    game._validate_save_payload(payload)
                self.assertEqual(session.serialize_game_state(), before)

    def test_a_current_save_comes_back_byte_for_byte(self):
        session = game.create_session(seed=2602)
        first = written(session, self.directory, "first.json")
        fresh = game.create_session(seed=2699)
        fresh.load_game(first)
        second = written(fresh, self.directory, "second.json")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(json.loads(first.read_text(encoding="utf-8"))["version"], 4)


class TestCombatShape(unittest.TestCase):
    def test_a_new_campaign_combat_is_schema_three(self):
        session = game.create_session(seed=2603)
        self.assertEqual(session.world_state["combat"]["schema_version"], 3)
        self.assertEqual(session.ensure_combat_state()["schema_version"], 3)

    def test_an_older_combat_shape_is_refused_not_migrated(self):
        for schema in (None, 1, 2):
            with self.subTest(schema=schema):
                session = game.create_session(seed=2604)
                combat = {"active": False, "round": 0}
                if schema is not None:
                    combat["schema_version"] = schema
                session.world_state["combat"] = combat
                with self.assertRaisesRegex(ValueError, "Unsupported combat save version"):
                    session.ensure_combat_state()
                self.assertEqual(session.world_state["combat"], combat)


class TestSpellbookWithoutMigration(unittest.TestCase):
    def v1_wizard(self):
        wizard = prepper("Wizard")
        wizard.world_state["spellcasting_v1"] = v1_of(wizard.world_state["spellcasting_v1"])
        return wizard

    def test_a_version_one_wizard_state_stays_as_loaded_and_is_blocked(self):
        wizard = self.v1_wizard()
        with tempfile.TemporaryDirectory() as directory:
            path = written(wizard, directory, "wizard.json")
            fresh = game.create_session(seed=2605)
            fresh.load_game(path)
        self.assertEqual(fresh.world_state["spellcasting_v1"]["version"], 1)
        view = spell_preparation.view(fresh)
        self.assertEqual((view["supported"], view["blocked_reason"]), (False, "spellbook_missing"))
        self.assertEqual((view["spellbook_options"], view["suggested_spellbook"]), ([], []))
        self.assertEqual(fresh.world_state["spellcasting_v1"]["version"], 1, "a read never migrates")

    def test_a_new_wizard_prepares_and_a_migration_window_is_not_a_reason(self):
        wizard = prepper("Wizard")
        result = spell_preparation.prepare(wizard, ["Shield", "Sleep"])
        self.assertEqual(result["status"], "prepared")
        state = wizard.world_state["spellcasting_v1"]
        state["prepare_window"] = {"opened_second": 0, "reason": "migration"}
        from spell_scope import validate
        with self.assertRaises(ValueError):
            validate(state, wizard.character)


class TestSpellbookRoute(EconomicHttpFixture):
    async def asyncSetUp(self):
        with fixed_town(self, 26501):
            await super().asyncSetUp()
        self.url = f"/api/game/sessions/{self.campaign['session_id']}/spellcasting/prepare"

    async def test_a_book_cannot_be_chosen_for_a_wizard_without_one(self):
        wizard = prepper("Wizard", self.record.game_session)
        wizard.world_state["spellcasting_v1"] = v1_of(wizard.world_state["spellcasting_v1"])
        self.save()
        before = copy.deepcopy(wizard.world_state)
        refused = await self.http.post(self.url, json={"action_id": str(uuid.uuid4()), "spellbook": SIX})
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(refused.json()["detail"]["code"], "prepare_spellbook_missing")
        self.assertEqual(wizard.world_state, before)

    async def test_a_new_wizard_still_prepares_over_http(self):
        prepper("Wizard", self.record.game_session)
        self.save()
        done = await self.http.post(self.url, json={"action_id": str(uuid.uuid4()), "prepared": ["Shield", "Sleep"]})
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(done.json()["result"]["status"], "prepared")


class TestDialogueModeIsFreeOrUnset(unittest.TestCase):
    def test_legacy_and_empty_modes_are_refused(self):
        for mode in ("legacy", ""):
            with self.subTest(mode=mode):
                world = {}
                with self.assertRaises(ValueError):
                    dialogue_runtime.initialize_new_campaign(world, mode)
                self.assertEqual(world, {})

    def test_unset_and_free_mode_are_accepted(self):
        world = {}
        dialogue_runtime.initialize_new_campaign(world, None)
        self.assertEqual(world, {})
        dialogue_runtime.initialize_new_campaign(world, dialogue_runtime.MODE)
        self.assertTrue(dialogue_runtime.is_enabled(world))


class TestNewCampaignFullRoundTrip(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with fixed_town(self, 26601):
            await r04.CommitBoundaryTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await r04.CommitBoundaryTests.asyncTearDown(self)

    post = r04.CommitBoundaryTests.post
    live_facts = r04.CommitBoundaryTests.live_facts

    def undo(self, target):
        return self.http.post(f"/api/game/sessions/{self.created['session_id']}/undo",
                              json={"action_id": str(uuid.uuid4()), "target_action_id": target})

    async def test_new_campaign_full_round_trip(self):
        """A new campaign plays a turn, saves, loads into a fresh session, then undoes back to the same state."""
        before_state = copy.deepcopy(self.session.serialize_game_state())
        before_facts = self.live_facts()
        action_id = str(uuid.uuid4())
        self.assertEqual((await self.post(action_id)).status_code, 200)
        played = copy.deepcopy(self.session.serialize_game_state())
        self.assertNotEqual(played, before_state)
        self.assertEqual(played["world_state"]["combat"]["schema_version"], 3)
        stored = self.store.get_campaign(self.cid).payload["engine_save"]
        self.assertEqual(stored["version"], 4)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "round.json"
            path.write_text(json.dumps(stored), encoding="utf-8")
            fresh = game.create_session(seed=2606)
            fresh.load_game(path)
            self.assertEqual(fresh.serialize_game_state(), played)
            again = written(fresh, directory, "again.json")
            self.assertEqual(json.loads(again.read_text(encoding="utf-8")), json.loads(path.read_text(encoding="utf-8")))
        undone = await self.undo(action_id)
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.session.serialize_game_state(), before_state)
        self.assertEqual(self.live_facts(), before_facts)


if __name__ == "__main__":
    unittest.main()
