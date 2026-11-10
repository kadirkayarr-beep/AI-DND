"""Talk mode has one writer (Dilim 2, Task 9): open, close, snapshot and restore write the three talk fields as today,
and the engine and the API read the conversation through one rule, one list and one filter (tasarım karar 18, 48,
49, 62)."""
from __future__ import annotations

import contextlib
import copy
import os
import unittest
from unittest.mock import call, patch

import front_proposal
import game
import scheduled_events
import talk_mode
import timed_gameplay
from api import serializers
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, ScriptedModel, _front_setting, apply_setup
from api.tests.journeys.schema import Step, load_scenario


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

    def test_a_named_person_who_is_not_here_gets_nobody(self):
        w = _world()
        a = talk_mode.addressee(w, [MAREK], named_word="satıcı", active=None, last_id="barman")
        self.assertEqual((a.status, a.npc, a.word), ("nobody_here", None, "satıcı"))
        a = talk_mode.addressee(w, [MAREK], target_id="barman", named_word="satıcı")
        self.assertEqual((a.status, a.npc["id"]), ("person", "barman"))      # a target on the screen wins
        a = talk_mode.addressee(w, [MAREK], named_id="barman", named_word="satıcı")
        self.assertEqual((a.status, a.npc["id"]), ("person", "barman"))

    def test_a_missing_reference_keeps_todays_order(self):
        w = _world()
        for word in (None, "", "   ", 7):
            with self.subTest(word=word):
                self.assertEqual(talk_mode.addressee(w, [MAREK], named_word=word, last_id="barman").npc["id"], "barman")
        self.assertEqual(talk_mode.addressee(w, [MAREK], named_word=None).npc["id"], "barman")   # the one person here
        self.assertEqual(talk_mode.addressee(w, [], named_word=None).status, "none_named")

    def test_the_active_person_comes_before_the_last_one_and_the_only_one(self):
        w = _world()
        other = {"id": "guest", "name": "Yolcu", "location": "inn"}
        self.assertEqual(talk_mode.addressee(w, [MAREK, other], active="guest", last_id="barman").npc["id"], "guest")
        self.assertEqual(talk_mode.addressee(w, [MAREK, other], last_id="barman").npc["id"], "barman")
        self.assertEqual(talk_mode.addressee(w, [MAREK, other]).status, "none_named")


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

    async def session_talking_to_marek(self, extra_people=None):
        """Scenario 08 setup, then "Marek'e selam veriyorum"; the engine is bound to the session afterwards."""
        if self._token is not None:
            game._ACTIVE_SESSION.reset(self._token)
            self._token = None
        campaign = await self._journey_campaign(self.scenario.setup)
        apply_setup(self, campaign, self.scenario.setup)
        self.session_id = self.last_session_id = campaign["session_id"]
        world = self.manager.get(self.session_id).game_session.world_state
        for person in extra_people or []:
            world["npcs"].append({"location": world["location"], **person})
        with _front_setting(self.scenario.setup):
            failures = await self._play(campaign["session_id"], self.scenario.steps[0], ScriptedModel())
        self.assertEqual(failures, [])
        session = self.manager.get(campaign["session_id"]).game_session
        self.assertEqual(session.world_state["flags"]["active_npc_id"], "barman")
        self._token = game._ACTIVE_SESSION.set(session)
        return session

    async def play(self, session, line, front=None, intent=None):
        """One scripted turn of the session; a reading (`front`) switches the front reading on for it."""
        script = {key: value for key, value in (("front", front), ("intent", intent)) if value is not None}
        step = Step(say=line, command=None, economic_action=None, combat_action=None, script=script or None,
                    expect={}, known_broken=(), real_chain=False, independent=True)
        flag = {front_proposal.FLAG: "1"} if front is not None else {}
        with patch.dict(os.environ, flag):
            failures = await self._play(self.session_id, step, ScriptedModel())
        self.assertEqual(failures, [])

    @staticmethod
    def notes(session):
        return list(getattr(session, "_turn_notes", None) or [])

    def narrator_input(self, session):
        return self.last_narrator_input or ""

    @staticmethod
    def sleep_after_walk_args(session):
        # the path "odama gidip uyuyorum" takes once the walk to the room is done: the room is already rented
        walked = {"narration": "", "action_result": {"action": "lodging", "status": "rented"}}
        return walked, "odama gidip uyuyorum", session.world_state["location"]

    @staticmethod
    def kill_player(session):
        # the way scenario 10 ends: the death state says dead, and ensure_death_state's dead branch settles it
        session.character["current_hp"] = 0
        session.world_state["player_combat_status"] = "dead"
        session.world_state.setdefault("death_state", game._death_state_defaults())["dead"] = True
        game.ensure_death_state()

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

    async def test_sleeping_closes_the_talk(self):
        session = await self.session_talking_to_marek()
        timed_gameplay._take_rest(session, "long_rest", 8 * 3600)          # the real rest entry, same room
        self.assertIsNone(game._active_interlocutor())
        self.assertIs(serializers.serialize_session_state(session)["conversation"]["active"], False)
        self.assertIsNone(session.world_state["flags"]["last_npc_id"])

    async def test_sleep_after_a_walk_closes_the_talk(self):
        session = await self.session_talking_to_marek()
        game._sleep_after_walk(*self.sleep_after_walk_args(session))       # the path "odama gidip uyuyorum" takes
        self.assertIsNone(game._active_interlocutor())

    async def test_a_short_wait_keeps_the_talk(self):
        session = await self.session_talking_to_marek()
        await self.play(session, "biraz bekliyorum", front={"kind": "unclear"})
        self.assertEqual(game._active_interlocutor()["id"], "barman")

    async def test_the_main_talk_path_gives_nobody_for_an_absent_named_person(self):
        line = "satıcıya yaklaşıp ne sattığını soruyorum"
        # (i) talk open: Marek active inside the window; today the active/last branch answers Marek
        session = await self.session_talking_to_marek()
        flags = session.world_state["flags"]
        self.assertGreaterEqual(flags["active_npc_until_turn"], flags["turn_index"])
        found = game.resolve_npc_reference(line, force_dialogue=True, allow_active_fallback=True, named_word="satıcı")
        self.assertEqual(found, {"status": "none", "npc": None, "nobody_here": "satıcı"})
        self.assertEqual(flags["active_npc_id"], "barman")                 # the resolver writes nothing; the turn's _nobody_here closes
        # (ii) after "konuşmayı bitiriyorum": close("ended") writes active_npc_until_turn = -1, so last_npc_id no
        # longer counts on this path; Marek is scenario 08's only person, so today's one-person fallback answers him
        await self.play(session, "konuşmayı bitiriyorum")
        self.assertEqual((flags["active_npc_id"], flags["active_npc_until_turn"], flags["last_npc_id"]),
                         (None, -1, "barman"))
        self.assertEqual([npc["id"] for npc in game._conversation_npcs()], ["barman"])
        found = game.resolve_npc_reference(line, force_dialogue=True, allow_active_fallback=True, named_word="satıcı")
        self.assertEqual(found, {"status": "none", "npc": None, "nobody_here": "satıcı"})
        self.assertIsNone(flags["active_npc_id"])
        found = game.resolve_npc_reference(line, force_dialogue=True, allow_active_fallback=True)
        self.assertEqual(found["npc"]["id"], "barman")                     # no word from the model: today's one-person fallback

    async def test_a_word_for_the_one_person_here_is_not_nobody(self):
        # the model names the innkeeper who is here, but its evidence is not in the line: today's one-person greeting
        session = await self.session_talking_to_marek()
        self.npc(session, "barman")["role"] = "innkeeper"                  # shown to the player as "hancı"
        await self.play(session, "konuşmayı bitiriyorum")
        found = game.resolve_npc_reference("selam veriyorum", force_dialogue=True, allow_active_fallback=True,
                                           named_word="hancı")
        self.assertEqual(found["npc"]["id"], "barman")
        session._named_word = "hancı"
        self.assertEqual(game._thread_person("selam veriyorum", None)["id"], "barman")
        session._named_word = None
        await self.play(session, "merhaba, selam veriyorum",
                        intent={"intent": "talk", "action": "greet",
                                "target": {"type": "npc", "reference": "hancı", "npc_id": "barman",
                                           "evidence_quote": "hancıya selam veriyorum"}})
        self.assertEqual([n for n in self.notes(session) if "görünmüyor" in n[1]], [])
        self.assertEqual(game._active_interlocutor()["id"], "barman")
        # a word nobody here answers to is still nobody
        found = game.resolve_npc_reference("selam veriyorum", force_dialogue=True, allow_active_fallback=True,
                                           named_word="satıcı")
        self.assertEqual(found, {"status": "none", "npc": None, "nobody_here": "satıcı"})

    async def test_the_job_path_gives_nobody_too(self):
        session = await self.session_talking_to_marek()
        session._named_word = "satıcı"
        self.assertIsNone(game._thread_person("satıcıya soruyorum", None))

    async def test_nobody_here_tells_the_narrator_who_is(self):
        session = await self.session_talking_to_marek()
        await self.play(session, "konuşmayı bitiriyorum")
        await self.play(session, "satıcıya yaklaşıp ne sattığını soruyorum",
                        intent={"intent": "talk", "action": "ask",
                                "target": {"type": "npc", "reference": "satıcı", "npc_id": "", "evidence_quote": "satıcı"}})
        self.assertIn((None, "burada 'satıcı' diye biri görünmüyor; görünenler: Marek (Barmen)"), self.notes(session))
        self.assertIn("görünmüyor", self.narrator_input(session))
        self.assertIsNone(game._active_interlocutor())

    async def test_addressing_an_absent_person_closes_the_old_talk_for_the_next_turn(self):
        # J-014 #4 (tasarım karar 57): the talk is open with Marek, the line names a vendor who is not here
        absent = {"intent": "talk", "action": "ask",
                  "target": {"type": "npc", "reference": "satıcı", "npc_id": "", "evidence_quote": "satıcı"}}
        plain = {"intent": "talk", "action": "ask", "target": {"type": "none", "reference": ""}}
        # (a) two people here (Marek and a guest): the next unnamed line is not Marek's by default
        session = await self.session_talking_to_marek(extra_people=[{"id": "guest", "name": "Yolcu", "distance_ft": 3}])
        with patch.object(talk_mode, "close", wraps=talk_mode.close) as closing:
            await self.play(session, "satıcıya yaklaşıp ne sattığını soruyorum", intent=absent)
        self.assertEqual(closing.call_args_list, [call(session.world_state, "addressed_absent")])
        flags = session.world_state["flags"]
        self.assertEqual({k: flags[k] for k in talk_mode.FIELDS},
                         {"active_npc_id": None, "active_npc_until_turn": -1, "last_npc_id": None})
        self.assertIs(serializers.serialize_session_state(session)["conversation"]["active"], False)
        self.assertEqual(game.resolve_npc_reference("peki ne kadar?", force_dialogue=True,
                                                    allow_active_fallback=True)["status"], "ambiguous")
        self.assertIsNone(game._thread_person("peki ne kadar?", None))     # the job path no longer falls to last_npc_id
        await self.play(session, "peki ne kadar?", intent=plain)
        # the unnamed line goes to whoever stands nearest (the guest), not to Marek by the old talk
        self.assertEqual(game._active_interlocutor()["id"], "guest")
        # (b) Marek alone: today's one-person fallback answers the unnamed line, as a fresh open
        session = await self.session_talking_to_marek()
        await self.play(session, "satıcıya yaklaşıp ne sattığını soruyorum", intent=absent)
        self.assertIs(serializers.serialize_session_state(session)["conversation"]["active"], False)
        self.assertEqual(len([n for n in self.notes(session) if "görünmüyor" in n[1]]), 1)   # both callers, one note
        await self.play(session, "peki sen ne satıyorsun?", intent=plain)
        flags = session.world_state["flags"]
        self.assertEqual(flags["active_npc_id"], "barman")
        self.assertGreaterEqual(flags["active_npc_until_turn"], flags["turn_index"])
        self.assertIs(serializers.serialize_session_state(session)["conversation"]["active"], True)

    async def test_death_and_walking_out_close_through_talk_mode(self):
        session = await self.session_talking_to_marek()
        with patch.object(talk_mode, "close", wraps=talk_mode.close) as closing:
            self.kill_player(session)          # the way scenario 10_death kills: ends in ensure_death_state's dead branch
            self.assertIn(call(session.world_state, "death"), closing.call_args_list)
        self.assertEqual(game.ensure_death_state()["dead"], True)
        self.assertEqual({k: session.world_state["flags"][k] for k in talk_mode.FIELDS},
                         {"active_npc_id": None, "active_npc_until_turn": -1, "last_npc_id": None})
        session = await self.session_talking_to_marek()
        with patch.object(talk_mode, "close", wraps=talk_mode.close) as closing:
            game.commit_location_change(self.other_place(session))
            self.assertIn(call(session.world_state, "moved"), closing.call_args_list)

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


class _CountingModel(ScriptedModel):
    """The scripted model, keeping the client of the step so a test can count its calls."""

    @contextlib.contextmanager
    def bind(self, case, step):
        with super().bind(case, step) as client:
            self.client = client
            yield client


class SayModeNamesAnother(JourneyCase):
    """Dilim 3D Task 9 (#17: #057, #179, #181): in say mode a line that names another person standing here is said to
    them, and the talk turns to them. Town fixed by seed 4581; Selin (a traveller) is spoken to, Orhan (a guard)
    stands beside her, Zeynep is somewhere else."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        scenario = load_scenario(SCENARIO_DIR / "08_talk_mode.json")
        self.setup = {**scenario.setup, "campaign_seed": 4581, "currency": {"player": 100, "traveller": 0, "guard": 0},
                      "npcs": [{"id": "traveller", "name": "Selin", "role": "Yolcu", "current_hp": 10},
                               {"id": "guard", "name": "Orhan", "role": "Muhafız", "current_hp": 10}]}
        campaign = await self._journey_campaign(self.setup)
        apply_setup(self, campaign, self.setup)
        self.session_id = self.last_session_id = campaign["session_id"]
        self.session = self.manager.get(self.session_id).game_session
        world = self.session.world_state
        elsewhere = next(p for p in world["locations"] if p != world["location"])
        world["npcs"].append({"id": "far", "name": "Zeynep", "role": "Çiftçi", "current_hp": 10,
                              "location": elsewhere, "name_known_to_player": True})
        for npc in world["npcs"]:
            npc["name_known_to_player"] = True

    async def say(self, line, spoken="Şu yoldan.", target="traveller"):
        step = Step(say=line, command=None, economic_action=None, combat_action=None, script={"spoken": spoken},
                    expect={}, known_broken=(), real_chain=False, independent=True, konus=target)
        model = _CountingModel()
        with _front_setting(self.setup):
            failures = await self._play(self.session_id, step, model)
        self.assertEqual(failures, [])
        self.chat_calls = len(model.client.kinds)

    def talk_target(self):
        return self.session.world_state["flags"]["active_npc_id"]

    def turn_index(self):
        return self.session.world_state["flags"]["turn_index"]

    async def test_naming_the_guard_speaks_to_the_guard(self):
        await self.say("Muhafız, kuzey kapısı ne tarafta?")
        self.assertIn('"npc_id":"guard"', self.last_speech_input)
        self.assertEqual(self.talk_target(), "guard")

    async def test_naming_the_guard_by_name_speaks_to_the_guard(self):
        await self.say("Orhan, kuzey kapısı ne tarafta?")
        self.assertEqual(self.talk_target(), "guard")

    async def test_no_name_stays_with_the_open_talk(self):
        await self.say("Kuzey kapısı ne tarafta?", spoken="Bilmem.")
        self.assertIn("Selin", self.last_speech_input)
        self.assertEqual(self.talk_target(), "traveller")

    async def test_naming_someone_absent_stays(self):
        await self.say("Zeynep, nerede?", spoken="Bilmem.")
        self.assertEqual(self.talk_target(), "traveller")

    async def test_a_line_to_the_one_spoken_to_that_also_names_another_stays(self):
        await self.say("Selin, Orhan nerede?", spoken="Bilmem.")
        self.assertEqual(self.talk_target(), "traveller")

    async def test_naming_the_one_already_spoken_to_stays(self):
        await self.say("Selin, kuzey kapısı ne tarafta?")
        self.assertEqual(self.talk_target(), "traveller")

    async def test_a_question_about_the_guard_stays_with_the_one_spoken_to(self):
        # Review 11 finding 2: a mention is not an address.
        for line in ("Orhan'ı tanıyor musun?", "Orhan nerede?", "Orhan'a güvenebilir miyim?",
                     "Muhafız sana ne dedi?", "Sen Orhan’ı tanıyor musun?", "Orhan hakkında ne düşünüyorsun?"):
            with self.subTest(line=line):
                await self.say(line, spoken="Bilmem.")
                self.assertEqual(self.talk_target(), "traveller")

    async def test_a_dative_and_a_say_verb_is_still_an_address(self):
        await self.say("Orhan'a kuzey kapısını soruyorum.")
        self.assertEqual(self.talk_target(), "guard")

    async def test_still_one_turn_and_two_calls_at_most(self):
        turn = self.turn_index()
        await self.say("Muhafız, kuzey kapısı ne tarafta?")
        self.assertEqual(self.turn_index(), turn + 1)
        self.assertLessEqual(self.chat_calls, 2)


if __name__ == "__main__":
    unittest.main()
