"""Talk mode has one writer (Dilim 2, Task 9): open, close, snapshot and restore write the three talk fields as today,
and the engine and the API read the conversation through one rule, one list and one filter (tasarım karar 18, 48,
49, 62)."""
from __future__ import annotations

import copy
import unittest

import game
import scheduled_events
import talk_mode
from api import serializers
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, ScriptedModel, _front_setting, apply_setup
from api.tests.journeys.schema import load_scenario


def _world(turn=3, location="inn", combat=False, **flags):
    return {"location": location, "combat": {"active": combat}, "flags": {"turn_index": turn, **talk_mode.fresh(), **flags}}


MAREK = {"id": "barman", "name": "Marek", "location": "inn"}


class TalkModeRules(unittest.TestCase):
    def test_open_then_current_inside_the_window_and_place(self):
        w = _world()
        talk_mode.open(w, "barman", turn=3)
        self.assertEqual({k: w["flags"][k] for k in talk_mode.FIELDS},
                         {"active_npc_id": "barman", "active_npc_until_turn": 9, "last_npc_id": "barman"})
        self.assertEqual(talk_mode.current(w, [MAREK])["id"], "barman")
        w["flags"]["turn_index"] = 9
        self.assertEqual(talk_mode.current(w, [MAREK])["id"], "barman")      # the window's last turn still counts

    def test_current_is_none_in_combat_after_the_window_or_elsewhere(self):
        for change in ({"combat": {"active": True}}, {"location": "street"}):
            w = _world(); talk_mode.open(w, "barman", turn=3); w.update(change)
            with self.subTest(change=change):
                self.assertIsNone(talk_mode.current(w, [MAREK]))
        w = _world(); talk_mode.open(w, "barman", turn=3); w["flags"]["turn_index"] = 10
        self.assertIsNone(talk_mode.current(w, [MAREK]))
        w = _world(); talk_mode.open(w, "barman", turn=3)
        self.assertIsNone(talk_mode.current(w, []))                         # not among the people the caller passes

    def test_close_reasons_and_last_npc(self):
        for reason, last in (("ended", "barman"), ("combat", "barman"), ("walking", "barman"), ("repair", "barman"),
                             ("target_gone", "barman"),
                             ("rest", None), ("moved", None), ("death", None), ("addressed_absent", None)):
            w = _world(); talk_mode.open(w, "barman", turn=3)
            with self.subTest(reason=reason):
                self.assertTrue(talk_mode.close(w, reason))
                self.assertEqual({k: w["flags"][k] for k in talk_mode.FIELDS},
                                 {"active_npc_id": None, "active_npc_until_turn": -1, "last_npc_id": last})
                self.assertFalse(talk_mode.close(w, reason))                # already closed: writes again, returns False
        with self.assertRaises(ValueError):
            talk_mode.close(_world(), "bored")

    def test_snapshot_and_restore_match_todays_two_restores(self):
        w = _world(last_npc_id=None); talk_mode.open(w, "barman", turn=3); w["flags"]["last_npc_id"] = None
        del w["flags"]["active_npc_until_turn"]
        before = copy.deepcopy(w["flags"])
        saved = talk_mode.snapshot(w)
        self.assertEqual(saved, {"active_npc_id": "barman", "last_npc_id": None})
        talk_mode.open(w, "other", turn=5)
        talk_mode.restore(w, saved)                                          # _addressed_in: exactly what was there
        self.assertEqual(w["flags"], before)
        talk_mode.open(w, "other", turn=5)
        talk_mode.restore(w, {k: v for k, v in saved.items() if v is not None})   # rejected proposal: None means gone
        self.assertEqual(w["flags"], {k: v for k, v in before.items() if k != "last_npc_id"})

    def test_fresh_is_a_new_dict_each_time(self):
        a, b = talk_mode.fresh(), talk_mode.fresh()
        a["active_npc_id"] = "x"
        self.assertEqual(b, {"last_npc_id": None, "active_npc_id": None, "active_npc_until_turn": -1})


class TalkModeThroughTheGame(JourneyCase):
    """Scenario 08's inn (Marek the barman) through the real app."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.scenario = load_scenario(SCENARIO_DIR / "08_talk_mode.json")
        self._token = None

    async def asyncTearDown(self):
        if self._token is not None:
            game._ACTIVE_SESSION.reset(self._token)
        await super().asyncTearDown()

    async def session_talking_to_marek(self):
        """Scenario 08 setup, then "Marek'e selam veriyorum"; the engine is bound to the session afterwards."""
        if self._token is not None:
            game._ACTIVE_SESSION.reset(self._token)
            self._token = None
        campaign = await self._journey_campaign(self.scenario.setup)
        apply_setup(self, campaign, self.scenario.setup)
        with _front_setting(self.scenario.setup):
            failures = await self._play(campaign["session_id"], self.scenario.steps[0], ScriptedModel())
        self.assertEqual(failures, [])
        session = self.manager.get(campaign["session_id"]).game_session
        self.assertEqual(session.world_state["flags"]["active_npc_id"], "barman")
        self._token = game._ACTIVE_SESSION.set(session)
        return session

    @staticmethod
    def npc(session, npc_id):
        return next(n for n in session.world_state["npcs"] if n.get("id") == npc_id)

    @staticmethod
    def other_place(session):
        world = session.world_state
        place = world["locations"][world["location"]]
        return place["parent_location_id"]

    @staticmethod
    def enemy_here(session):
        world = session.world_state
        enemy = {"id": "thug", "name": "Haydut", "role": "Haydut", "location": world["location"],
                 "current_hp": 9, "hostile": True}
        world["npcs"].append(enemy)
        return enemy

    @staticmethod
    def hide_by_unseen_event(session, npc_id):
        # an OCCURRED, unobserved, hidden npc_location event (the fields scheduled_events.visible_npcs reads); the
        # rest of the record is the product's own (register_event)
        world = session.world_state
        here = world["location"]
        now = world["campaign_time"]["elapsed_seconds"]
        event = scheduled_events.register_event(
            world, event_id="d2t9-hidden", window_start=now, window_end=now + 60, location_id=here,
            effects=[{"kind": "npc_location", "npc_id": npc_id, "location_id": here}], visibility="hidden")
        event["status"] = "OCCURRED"

    async def test_combat_start_and_moving_close_as_today(self):
        # through the game: start a fight with Marek's room open; then talk again and walk to another place
        session = await self.session_talking_to_marek()
        game.start_combat(self.enemy_here(session))
        flags = session.world_state["flags"]
        self.assertEqual((flags["active_npc_id"], flags["active_npc_until_turn"], flags["last_npc_id"]),
                         (None, -1, "barman"))
        session = await self.session_talking_to_marek()
        self.assertIsNot(game.commit_location_change(self.other_place(session)), False)
        flags = session.world_state["flags"]
        self.assertEqual((flags["active_npc_id"], flags["active_npc_until_turn"], flags["last_npc_id"]),
                         (None, -1, None))

    async def test_serializer_and_game_agree(self):
        session = await self.session_talking_to_marek()
        projected = serializers._conversation_projection(session.world_state)
        self.assertEqual((projected["active"], projected["interlocutor"]["id"]),
                         (True, game._active_interlocutor()["id"]))

    async def test_engine_and_api_agree_for_every_gone_person(self):
        # J-014 #9: one list, one filter, owned by talk_mode (tasarım karar 62); today the serializer reads
        # world["npcs"] unfiltered
        def unconscious(s): self.npc(s, "barman")["combat_status"] = "unconscious"
        def dead(s): self.npc(s, "barman")["combat_status"] = "dead"
        def walked_off(s): self.npc(s, "barman")["location"] = self.other_place(s)
        def deleted(s): s.world_state["npcs"] = [n for n in s.world_state["npcs"] if n.get("id") != "barman"]
        def window_over(s): s.world_state["flags"]["turn_index"] = s.world_state["flags"]["active_npc_until_turn"] + 1
        def hidden(s): self.hide_by_unseen_event(s, "barman")
        for change in (unconscious, dead, walked_off, deleted, window_over, hidden):
            with self.subTest(change=change.__name__):
                session = await self.session_talking_to_marek()
                change(session)
                self.assertIsNone(game._active_interlocutor())
                self.assertEqual(serializers._conversation_projection(session.world_state),
                                 {"active": False, "interlocutor": None})
                self.assertIs(serializers.serialize_session_state(session)["conversation"]["active"], False)
        session = await self.session_talking_to_marek()                      # control: nothing changed, both say Marek
        self.assertEqual((game._active_interlocutor()["id"],
                          serializers._conversation_projection(session.world_state)["active"]),
                         ("barman", True))


if __name__ == "__main__":
    unittest.main()
