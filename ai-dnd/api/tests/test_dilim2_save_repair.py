"""Dilim 2, Task 19: loading repairs a bad happening row, a hand that points at nothing and a talk with someone gone,
names each repair in the log and never refuses the save over them; a sound save comes back unchanged. Undo and a
reload return a draw, a delivery and a closed talk whole. No real model is called."""
from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import game
import world_happenings
import world_threads
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.journeys.runner import (SCENARIO_DIR, _NOT_STATE, JourneyCase, ScriptedModel, _front_setting, _Reader,
                                       apply_setup, read_observed)
from api.tests.journeys.schema import Step, load_scenario
from api.tests.test_wield_front import PACKAGE_C


def _setup(name, **extra):
    return {**copy.deepcopy(load_scenario(SCENARIO_DIR / name).setup), **extra}


def _step(line=None, front=None, undo=False):
    return Step(say=line, command=None, economic_action=None, combat_action=None,
                script={"front": front} if front else None, expect={}, known_broken=(), real_chain=False,
                independent=True, undo=undo)


class SaveRepair(JourneyCase):
    """Scenario 19's setup saved to the campaign store, broken in the stored JSON, then resumed by a new manager (the
    store's read, the campaign restore and ``game.load_game``: every load path a campaign takes)."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.setup = _setup("19_quest_item_no_duplicate.json")
        campaign = await self._journey_campaign(self.setup)
        apply_setup(self, campaign, self.setup)
        self.campaign_id = campaign["campaign_id"]
        self.session_id = self.last_session_id = campaign["session_id"]
        self._loaded = None

    # --- the stored save ------------------------------------------------------------------------------------------
    def _payload(self):
        with sqlite3.connect(self.store.path) as connection:
            row = connection.execute("SELECT payload_json FROM campaigns WHERE campaign_id = ?",
                                     (self.campaign_id,)).fetchone()
        return json.loads(row[0])

    def saved_world(self):
        """The world as the store holds it (written to JSON and read back); the test breaks it and hands it to load."""
        self.manager.save_campaign(self.campaign_id)
        return self._payload()["engine_save"]["world_state"]

    def load(self, world):
        """Write ``world`` into the stored campaign, resume it with a new manager; return what the repair named."""
        payload = self._payload()
        payload["engine_save"]["world_state"] = world
        connection = sqlite3.connect(self.store.path)
        try:
            connection.execute("UPDATE campaigns SET payload_json = ? WHERE campaign_id = ?",
                               (json.dumps(payload, ensure_ascii=False), self.campaign_id))
            connection.commit()
        finally:
            connection.close()
        named = []
        real = game._repair_dilim2_fields

        def spy(target):
            fixed = real(target)
            named.append(list(fixed))
            return fixed
        self.fresh = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        with patch.object(game, "_repair_dilim2_fields", new=spy):
            self.fresh_id, *_ = self.fresh.resume_campaign(self.campaign_id)
        self.assertEqual(len(named), 1, named)
        self._loaded = self.fresh.get(self.fresh_id).game_session.world_state
        return named[0]

    def loaded_world(self):
        return self._loaded

    def save_again(self):
        self.fresh.save_campaign(self.campaign_id)
        return self._payload()["engine_save"]["world_state"]

    @staticmethod
    def happenings_state(world):
        return world[world_threads.KEY]

    def a_row(self, kind):
        state = self.happenings_state(self.loaded_world() or self._payload()["engine_save"]["world_state"])
        thread = state["threads"][0]
        return {"thread_id": thread["thread_id"], "kind": kind, "at": 0, "place_id": thread["place_id"],
                "line": "Bir şey oldu.", "known_to_player": False, "next_thread_id": None}

    @staticmethod
    def talk_open_with(world, npc_id, change):
        """Open the talk with ``npc_id`` in the stored flags, then break the person: dead, elsewhere or not in the save."""
        here = world["location"]
        if change != "unknown_id":
            world["npcs"].append({"id": npc_id, "name": "Marek", "role": "Barmen", "current_hp": 10, "location": here})
        flags = world["flags"]
        turn = flags.get("turn_index", 0)
        flags.update(active_npc_id=npc_id, active_npc_until_turn=turn + 6, last_npc_id=npc_id)
        person = next((n for n in world["npcs"] if n.get("id") == npc_id), None)
        if change == "dead":
            person["combat_status"] = "dead"
        elif change == "elsewhere":
            person["location"] = next(place for place in world["locations"] if place != here)

    # --- repairs --------------------------------------------------------------------------------------------------
    async def test_old_save_without_dilim2_rows_loads_and_saves_again(self):
        world = self.saved_world()                                        # a save from before Dilim 2: no "delivered" rows
        self.assertNotIn("delivered", [r["kind"] for r in world_happenings.ledger(self.happenings_state(world))])
        stored = copy.deepcopy(world)
        self.assertEqual(self.load(world), [])
        self.assertEqual(json.loads(json.dumps(self.save_again())), stored)

    async def test_a_sound_talk_and_hand_are_kept_as_they_are(self):
        world = self.saved_world()
        self.talk_open_with(world, "barman", "here")
        world["inventory"].append({"item_id": "item:sword", "name": "Longsword", "weapon_id": "longsword"})
        world["inventory"].append({"item_id": "item:dagger", "name": "Dagger", "weapon_id": "dagger"})
        world["equipment"] = {"main_hand": "item:sword", "off_hand": "Dagger"}   # an id, and an old name alias
        rows = world_happenings.ledger(self.happenings_state(world))
        rows.append(self.a_row(kind="visit"))
        stored = copy.deepcopy(world)
        self.assertEqual(self.load(world), [])
        self.assertEqual(json.loads(json.dumps(self.save_again())), stored)

    async def test_the_new_worlds_default_hand_is_kept(self):
        # a new world holds "longsword" in the main hand whatever the bag holds (a Sorcerer's too): a sound save
        world = self.saved_world()
        world["inventory"] = []
        world["equipment"] = {"main_hand": "longsword", "off_hand": None}
        stored = copy.deepcopy(world)
        self.assertEqual(self.load(world), [])
        self.assertEqual(json.loads(json.dumps(self.save_again())), stored)

    async def test_a_bad_happening_row_is_dropped_and_named(self):
        world = self.saved_world()
        rows = world_happenings.ledger(self.happenings_state(world))
        rows.append(self.a_row(kind="visit"))
        rows.append(self.a_row(kind="gossip"))
        with self.assertLogs(level="WARNING") as logged:
            fixed = self.load(world)
        self.assertEqual([f for f in fixed if f.startswith("happening:")], ["happening:gossip"])
        kinds = [r["kind"] for r in world_happenings.ledger(self.happenings_state(self.loaded_world()))]
        self.assertNotIn("gossip", kinds)
        self.assertIn("visit", kinds)
        self.assertIn("happening:gossip", "\n".join(logged.output))
        saved = [r["kind"] for r in world_happenings.ledger(self.happenings_state(self.save_again()))]
        self.assertEqual(saved, kinds)

    async def test_a_hand_pointing_at_nothing_is_emptied(self):
        world = self.saved_world()
        world["equipment"] = {"main_hand": "item:gone", "off_hand": "item:also-gone"}
        with self.assertLogs(level="WARNING") as logged:
            self.assertEqual(sorted(self.load(world)), ["equipment:main_hand", "equipment:off_hand"])
        self.assertEqual(self.loaded_world()["equipment"], {"main_hand": None, "off_hand": None})
        self.assertIn("equipment:main_hand", "\n".join(logged.output))

    async def test_a_talk_with_a_dead_or_absent_person_is_closed(self):
        for change in ("dead", "elsewhere", "unknown_id"):
            with self.subTest(change=change):
                world = self.saved_world()
                self.talk_open_with(world, "barman", change)               # dead: npc["combat_status"]="dead"; elsewhere: other location
                self.assertIn("talk:barman" if change != "unknown_id" else "talk:nobody", self.load(world))
                flags = self.loaded_world()["flags"]
                self.assertEqual((flags["active_npc_id"], flags["active_npc_until_turn"]), (None, -1))

    async def test_nothing_is_refused(self):
        world = self.saved_world()
        world["equipment"] = {"main_hand": "item:gone", "off_hand": None}
        self.talk_open_with(world, "barman", "dead")
        world_happenings.ledger(self.happenings_state(world)).append(self.a_row(kind="gossip"))
        self.assertEqual(sorted(self.load(world)), ["equipment:main_hand", "happening:gossip", "talk:barman"])
        self.assertIsNotNone(self.loaded_world())                    # the campaign opened

    async def test_the_engine_file_load_repairs_too(self):
        # game.load_game from a save file (the engine's own load path, without the campaign store)
        world = self.saved_world()
        world["equipment"] = {"main_hand": "item:gone", "off_hand": None}
        self.talk_open_with(world, "barman", "elsewhere")
        world_happenings.ledger(self.happenings_state(world)).append(self.a_row(kind="gossip"))
        engine_save = self._payload()["engine_save"]
        engine_save["world_state"] = world
        session = self.manager.get(self.session_id).game_session
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "save.json"
            path.write_text(json.dumps(engine_save, ensure_ascii=False), encoding="utf-8")
            with patch.object(game, "_repair_dilim2_fields", wraps=game._repair_dilim2_fields) as repair:
                session.load_game(path)
        self.assertEqual(repair.call_count, 1)
        loaded = session.world_state
        self.assertEqual(loaded["equipment"]["main_hand"], None)
        self.assertEqual(loaded["flags"]["active_npc_id"], None)
        self.assertNotIn("gossip", [r["kind"] for r in world_happenings.ledger(self.happenings_state(loaded))])


class UndoAndReload(JourneyCase):
    """Undo through the product's route and a reload through a new manager return a draw, a delivery and a talk."""

    async def use(self, setup):
        self.setup = setup
        campaign = await self._journey_campaign(setup)
        apply_setup(self, campaign, setup)
        self.campaign_id = campaign["campaign_id"]
        self.session_id = self.last_session_id = campaign["session_id"]
        self.last_turn_action_id = None

    @property
    def world(self):
        return self.manager.get(self.session_id).game_session.world_state

    async def run_step(self, step):
        with _front_setting(self.setup):
            failures = await (self._undo(self.session_id, step, ScriptedModel()) if step.undo
                              else self._play(self.session_id, step, ScriptedModel()))
        self.assertEqual(failures, [])

    async def say(self, line, front=None):
        await self.run_step(_step(line, front))

    async def undo(self):
        await self.run_step(_step(undo=True))

    def observed(self):
        found = read_observed(self, self.session_id)
        return {key: value for key, value in found.items() if key not in _NOT_STATE}

    def reloaded_observed(self):
        fresh = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        reloaded_id, *_ = fresh.resume_campaign(self.campaign_id)
        found = read_observed(_Reader(fresh), reloaded_id)
        return {key: value for key, value in found.items() if key not in _NOT_STATE}

    # --- the three plays ------------------------------------------------------------------------------------------
    async def use_package_c(self):
        """Scenario 05's setup (package C: Greatsword and a heavy crossbow in the bag, hands empty), no fight."""
        await self.use(_setup("05_greatsword.json", front_proposal=True, inventory=list(PACKAGE_C)))

    async def play_draw(self):
        await self.use_package_c()
        await self.say("büyük kılıcımı çekiyorum", front={"kind": "wield", "item_name": "Greatsword"})
        self.assertEqual(self.observed()["elinde"], "Greatsword")

    async def accept(self):
        await self.use(_setup("19_quest_item_no_duplicate.json"))
        await self.say("olur, götürürüm")
        [thread] = [t for t in world_threads.view(self.world)["threads"] if t.get("status") == "accepted"]
        self.thread_id = thread["thread_id"]
        self.tuna = thread["recipient_npc_id"]

    async def at_recipient(self):
        self.world["location"] = world_threads.by_id(self.world, self.thread_id)["target_place_id"]
        self.manager.save_campaign(self.campaign_id)

    async def play_delivery(self):
        await self.accept(); await self.at_recipient()
        await self.say("Tuna, iade takımını getirdim", front={"kind": "hand_over", "person_id": self.tuna, "item_id": "none"})
        self.assertEqual(self.observed()["kese"], 112)

    async def talk_to_marek(self):
        """Scenario 08's first steps: greet Marek, take the room through the card, greet him again."""
        self.scenario = load_scenario(SCENARIO_DIR / "08_talk_mode.json")
        await self.use(self.scenario.setup)
        for index in (0, 1, 3, 4):
            await self.run_step(self.scenario.steps[index])
        self.assertIs(self.observed()["kip"]["active"], True)
        self.assertIs(self.observed()["oda"], True)

    async def play_sleep(self):
        await self.talk_to_marek()
        await self.say("odama gidip uyuyorum")                              # sleep closes the talk (Görev 10)
        self.assertIs(self.observed()["kip"]["active"], False)

    # --- undo -----------------------------------------------------------------------------------------------------
    async def test_undo_restores_the_draw(self):
        await self.use_package_c()
        before = self.observed()
        await self.say("büyük kılıcımı çekiyorum", front={"kind": "wield", "item_name": "Greatsword"})
        self.assertEqual(self.observed()["elinde"], "Greatsword")
        await self.undo()
        self.assertIsNone(self.observed()["elinde"])
        self.assertEqual(self.observed(), before)

    async def test_undo_restores_the_delivery(self):
        await self.accept(); await self.at_recipient()
        before = self.observed()
        await self.say("Tuna, iade takımını getirdim", front={"kind": "hand_over", "person_id": self.tuna, "item_id": "none"})
        self.assertEqual(self.observed()["kese"], 112)
        await self.undo()
        seen = self.observed()
        self.assertEqual((seen["kese"], seen["envanter"], seen["gunluk"]["sayac"], seen["gunluk"]["iz"]),
                         (100, {"İade takımı": 1}, 1, []))
        self.assertEqual(seen, before)

    async def test_undo_restores_the_talk(self):
        await self.talk_to_marek()
        before = self.observed()
        await self.say("odama gidip uyuyorum")                              # sleep closes the talk (Görev 10)
        self.assertIs(self.observed()["kip"]["active"], False)
        await self.undo()
        self.assertIs(self.observed()["kip"]["active"], True)
        self.assertEqual(self.observed(), before)

    async def test_a_new_manager_reload_matches_live_after_each(self):
        for play in (self.play_draw, self.play_delivery, self.play_sleep):
            with self.subTest(play=play.__name__):
                await play()
                self.assertEqual(self.reloaded_observed(), self.observed())
