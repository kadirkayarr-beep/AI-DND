"""Roadmap step 5: the model reads a free line first, Python checks the listed ids and routes it.

Real app, real adapter, real engine; only the Ollama client is scripted. The front reading is the turn's one
classifier call, so a turn never spends a third call on it. Anything wrong with it leaves the old chain in charge.
"""

from __future__ import annotations

import json
import copy
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import front_proposal
import grounded_action
import world_threads
from api import local_play
from api.tests import test_experimental_npc_dialogue as speech
from api.tests import test_thread_gate as gate_tests
from api.tests.town_seed import fixed_town


class FrontClient(speech.ScriptedNpcSpeechClient):
    """Answers the front reading from a script; a failing front raises like a dead provider."""

    def __init__(self, narration="Şimdilik sessiz bir gün."):
        super().__init__(narration)
        self.front = {"kind": "unclear"}
        self.intent = "narrative"
        self.target = {"type": "none", "reference": ""}
        self.fails = None
        self.drop_front = False

    def chat(self, *args, **kwargs):
        schema = kwargs.get("format") or {}
        if "front" not in (schema.get("properties") or {}):
            return super().chat(*args, **kwargs)
        self.chat_calls += 1
        self.schemas.append(schema)
        self.message_batches.append(kwargs.get("messages", []))
        if self.fails is not None:
            raise self.fails
        filled = {"person_id": "none", "place_id": "none", "offer_id": "none", "thing_id": "none", "answer": "none",
                  "inside": False, **self.front}
        packet = {"intent": self.intent, "action": "narrative", "target": self.target,
                  "completion": "unclear", "confidence": 0.9}
        return {"message": {"content": json.dumps(packet if self.drop_front else {**packet, "front": filled},
                                                  ensure_ascii=False)}}


class FrontTable(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc
    open_job = gate_tests.ThreadTable.open_job
    line = gate_tests.ThreadTable.line
    status = gate_tests.ThreadTable.status
    offer = gate_tests.ThreadTable.offer

    async def begin(self, *, kind="hiring"):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.route_file = Path(self.directory.name) / "routes.jsonl"
        await self.open_job(kind=kind)
        self.enterContext(patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1",
                                                  "AI_DND_ROUTE_LOG": str(self.route_file)}))
        self.client = FrontClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))

    def routes(self):
        return [json.loads(line) for line in self.route_file.read_text(encoding="utf-8").splitlines()]

    def front_calls(self):
        return [schema for schema in self.client.schemas if "front" in (schema.get("properties") or {})]

    def a_place(self):
        return next(key for key, value in self.world["locations"].items()
                    if isinstance(value, dict) and value.get("parent_location_id") == self.world["location"])

    def the_inn(self):
        """The town's inn by its live id: the opening now makes other places first (Task 18), so the first one made
        is no longer the inn these lines name."""
        import living_world
        return next(key for key, value in self.world["locations"].items()
                    if isinstance(value, dict) and value.get("parent_location_id") == self.world["location"]
                    and living_world.scene_kind(self.world, key) == "tavern")

    async def test_a_person_the_model_picked_from_the_list_answers(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        reply = await self.line("şu adamın bu kasaba hakkında ne düşündüğünü merak ettim")
        self.assertIn(self.client.narration, reply["narration"])
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")
        self.assertIs(self.routes()[-1]["reached_model"], True)

    async def test_the_list_holds_only_people_here_and_ids_the_turn_knows(self):
        await self.begin()
        next(npc for npc in self.world["npcs"] if npc["id"] == "npc_private_sera")["location"] = "elsewhere"
        await self.line("etrafa şöyle bir göz atayım")
        kinds = self.front_calls()[0]["properties"]["front"]["properties"]
        self.assertIn(self.npc["id"], kinds["person_id"]["enum"])
        self.assertNotIn("npc_private_sera", kinds["person_id"]["enum"])
        self.assertEqual(kinds["kind"]["enum"], list(front_proposal.KINDS))

    async def test_a_person_nobody_listed_falls_back_to_the_old_chain(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": "npc_invented"}
        reply = await self.line("merhaba millet, biraz konuşalım")
        self.assertTrue(reply["narration"].strip())
        self.assertEqual(self.routes()[-1]["route"], "fallback:invalid")

    async def test_a_failed_call_never_fails_the_turn_on_the_local_model_alone(self):
        await self.begin()
        self.client.fails = ConnectionError("gone")
        reply = await self.line("etrafa şöyle bir göz atayım")
        self.assertTrue(reply["narration"].strip())
        self.assertEqual(self.routes()[-1]["route"], "fallback:failed")
        self.assertIs(self.routes()[-1]["reached_model"], False)

    async def test_the_front_reading_is_the_classifier_call_and_the_cap_holds(self):
        await self.begin()
        self.client.front = {"kind": "attempt"}
        await self.line("yerdeki taşı alıp duvara fırlatıyorum")
        intent_calls = [schema for schema in self.client.schemas if "intent" in (schema.get("properties") or {})]
        self.assertEqual(len(intent_calls), 1)
        self.assertLessEqual(self.client.chat_calls, 2)
        self.assertEqual(self.routes()[-1]["route"], "front:attempt")

    async def test_the_model_reads_a_yes_the_word_lists_never_heard(self):
        await self.begin()
        self.offer()
        self.client.front = {"kind": "offer_answer", "offer_id": self.thread["thread_id"], "answer": "accept"}
        await self.line("hmm güzel, sayılır ben varım bu işte")
        self.assertEqual(self.status(), "accepted")
        self.assertEqual(self.routes()[-1]["route"], "front:offer_answer")

    async def test_a_question_about_the_terms_is_never_taken_as_a_yes(self):
        await self.begin()
        self.offer()
        self.client.front = {"kind": "offer_answer", "offer_id": self.thread["thread_id"], "answer": "accept"}
        reply = await self.line("ne kadar veriyorsun peki?")
        self.assertEqual(self.status(), "offered")
        self.assertIn(self.client.narration, reply["narration"])

    async def test_an_offer_nobody_made_cannot_be_taken(self):
        await self.begin()
        self.client.front = {"kind": "offer_answer", "offer_id": self.thread["thread_id"], "answer": "accept"}
        await self.line("hmm güzel, sayılır ben varım bu işte")
        self.assertEqual(self.status(), "open")
        self.assertEqual(self.routes()[-1]["route"], "fallback:invalid")

    async def test_a_listed_place_is_walked_to_by_the_owner_of_walking(self):
        await self.begin()
        place = self.a_place()
        self.client.front = {"kind": "go_to", "place_id": place}
        # Dilim 3D Task 5 [GEVŞETME OLABİLİR değil, sıkılaştı]: the line must name the place it walks to
        reply = await self.line(f"{self.world['locations'][place]['name']} yerine bi uğrayayım")
        self.assertEqual(self.routes()[-1]["route"], "front:go_to")
        self.assertIn(self.world["locations"][place]["name"], reply["narration"])

    async def test_a_place_nobody_listed_moves_nobody(self):
        await self.begin()
        here = self.world["location"]
        self.client.front = {"kind": "go_to", "place_id": "fr:invented"}
        await self.line("şuraya bi uğrayayım dedim")
        self.assertEqual(self.world["location"], here)
        self.assertEqual(self.routes()[-1]["route"], "fallback:invalid")

    async def test_a_line_that_says_no_to_the_walk_does_not_walk(self):
        with fixed_town(self, 2701):
            await self.begin()
        here = self.world["location"]
        near_before = self.world.get("grounded_action")
        self.client.front = {"kind": "go_to", "place_id": self.the_inn()}
        await self.line("hana gitmiyorum")
        self.assertEqual(self.world["location"], here)
        self.assertEqual(self.world.get("grounded_action"), near_before)

    async def test_a_line_that_says_no_to_the_walk_does_not_walk_through_an_open_door(self):
        """The same 'no' with nothing in the way: no locked door may be what keeps the player where they are."""
        with fixed_town(self, 2701):
            await self.begin()
        here, inn = self.world["location"], self.the_inn()
        for door in self.world.get("doors", []):
            door.update(locked=False, open=True)
        near_before = self.world.get("grounded_action")
        clock_before = copy.deepcopy(self.world.get("campaign_time"))
        self.client.front = {"kind": "go_to", "place_id": inn}
        for line in ("hana gitmiyorum", "Hana gitmiyorum."):
            reply = await self.line(line)
            self.assertEqual(self.world["location"], here, (line, reply["narration"], self.routes()[-1]))
            self.assertEqual(self.world.get("grounded_action"), near_before)
            self.assertEqual(self.world.get("campaign_time"), clock_before)
        self.client.front = {"kind": "unclear"}
        reply = await self.line("hana gitmiyorum")
        self.assertEqual(self.world["location"], here, (reply["narration"], self.routes()[-1]))

    async def test_a_look_goes_to_the_owner_of_looking(self):
        await self.begin()
        self.client.front = {"kind": "look"}
        reply = await self.line("bakalım burada neler dönüyor")
        self.assertTrue(reply["narration"].strip())
        self.assertEqual(self.routes()[-1]["route"], "front:look")

    async def test_a_job_answer_outranks_the_walk_in_the_same_line(self):
        await self.begin()
        self.offer()
        place = self.a_place()
        self.client.front = {"kind": "go_to", "place_id": place}
        await self.line("tamam kabul, hemen gidiyorum oraya")
        self.assertEqual(self.status(), "accepted")

    async def test_leaving_a_job_on_the_way_out_still_leaves_it(self):
        await self.begin()
        self.offer()
        world_threads.accept_hired(self.world, self.thread)
        self.client.front = {"kind": "go_to", "place_id": self.a_place()}
        await self.line("işi bırakıyorum, hana gidiyorum")
        self.assertEqual(self.status(), "abandoned")

    async def no_walk(self, line):
        await self.begin()
        here = self.world["location"]
        self.client.front = {"kind": "go_to", "place_id": self.a_place()}
        await self.line(line)
        self.assertEqual(self.world["location"], here, line)

    async def test_a_question_about_going_is_no_walk_whatever_the_model_read(self):
        await self.no_walk("oraya nasıl giderim?")

    async def test_a_quote_about_going_is_no_walk_whatever_the_model_read(self):
        await self.no_walk("adama 'oraya gidiyorum' diyorum")

    async def test_a_walk_with_more_said_after_it_goes_to_the_chain_that_keeps_the_rest(self):
        await self.begin()
        self.client.front = {"kind": "go_to", "place_id": self.a_place()}
        decision, _ = grounded_action._decide_listed_walk(self.session, "tapınağa gidip kapısını çalıyorum",
                                                          self.a_place(), False)
        self.assertEqual(decision, "defer")

    async def test_the_hideout_keeps_its_own_owner(self):
        await self.begin()
        with patch("adventure.play.inside_hideout", return_value=True):
            await self.line("etrafa şöyle bir göz atayım")
        self.assertEqual(self.front_calls(), [])
        self.assertEqual(self.routes()[-1]["route"], "skipped:hideout")

    async def test_a_no_the_model_misread_as_a_yes_is_still_a_no(self):
        await self.begin()
        self.offer()
        self.client.front = {"kind": "offer_answer", "offer_id": self.thread["thread_id"], "answer": "accept"}
        await self.line("yok, istemiyorum")
        self.assertEqual(self.status(), "declined")

    async def test_terms_asked_after_a_misread_yes_are_shown(self):
        await self.begin()
        self.offer()
        self.client.front = {"kind": "offer_answer", "offer_id": self.thread["thread_id"], "answer": "accept"}
        await self.line("ne kadar veriyorsun peki?", "Hmm.")
        self.assertEqual(self.status(), "offered")
        self.assertIn("Parayı soruyor", str(self.client.message_batches))

    async def test_a_loose_answer_shape_is_a_bad_reading_not_a_crash(self):
        await self.begin()
        self.offer()
        self.client.front = {"kind": "offer_answer", "offer_id": self.thread["thread_id"], "answer": ["accept"]}
        reply = await self.line("hmm belki")
        self.assertTrue(reply["narration"].strip())
        self.assertEqual(self.routes()[-1]["route"], "fallback:invalid")

    async def test_a_reply_with_no_reading_in_it_is_not_logged_as_a_dead_model(self):
        await self.begin()
        self.client.drop_front = True
        await self.line("etrafa şöyle bir göz atayım")
        self.assertEqual(self.routes()[-1]["route"], "fallback:no_front")
        self.assertIs(self.routes()[-1]["reached_model"], True)

    async def test_a_thing_the_model_picked_from_the_list_is_what_the_hand_goes_to(self):
        await self.begin()
        door = {"id": "door_front_test", "name": "Mavi Kapak", "description": "Mavi bir kapak",
                "location": self.world["location"], "open": False, "locked": False, "broken": False}
        self.world.setdefault("doors", []).append(door)
        self.client.front = {"kind": "attempt", "thing_id": door["id"]}
        reply = await self.line("şu yandakine yaklaşıyorum")
        self.assertIn("thing_id", self.front_calls()[0]["properties"]["front"]["properties"])
        self.assertIn("Mavi Kapak", reply["narration"])

    async def test_a_line_nothing_binds_asks_what_is_meant_after_the_reading(self):
        await self.begin()
        self.client.front = {"kind": "unclear"}
        reply = await self.line("şu yandakine yaklaşıyorum")
        self.assertEqual(reply["turn_outcome"]["status"], "clarification")

    async def test_typed_speech_reads_purpose_once_without_general_front_side_effects(self):
        await self.begin()
        self.npc["role"] = "barmen"  # a line said to whoever serves is read without coin (a line to anyone else is not)
        here = self.world["location"]
        money = copy.deepcopy(self.world.get("currency"))
        wants = copy.deepcopy(world_threads.wants_of(self.world))
        self.client.front = {"kind": "attempt", "strike_to": self.npc["id"],
                             "threat_to": self.npc["id"], "want": "coin", "economic_intent": "none"}
        await self.line("selam", mode="say", target=True)
        self.assertEqual(len(self.front_calls()), 1)
        self.assertEqual(sum("intent" in (schema.get("properties") or {}) for schema in self.client.schemas), 1)
        self.assertEqual(self.routes()[-1]["route"], "typed:no_economic")
        self.assertEqual(self.world["location"], here)
        self.assertEqual(self.world.get("currency"), money)
        self.assertEqual(world_threads.wants_of(self.world), wants)
        self.assertFalse(self.world.get("combat", {}).get("active"))
        self.assertEqual(self.world["flags"].get("active_npc_id"), self.npc["id"])

    async def test_the_route_log_never_holds_the_players_words(self):
        await self.begin()
        await self.line("gizlicümlem burada kalsın")
        self.assertNotIn("gizlicümlem", self.route_file.read_text(encoding="utf-8"))


class FlagIsLocalPlayOnly(unittest.TestCase):
    def test_off_unless_asked(self):
        self.assertFalse(front_proposal.enabled({}))
        self.assertTrue(front_proposal.enabled({"AI_DND_FRONT_PROPOSAL": "1"}))

    def test_local_play_turns_it_on_and_the_owner_can_turn_it_off(self):
        environ = {}
        front_proposal.default_on_for_local_play(environ)
        self.assertEqual(environ["AI_DND_FRONT_PROPOSAL"], "1")
        environ = {"AI_DND_FRONT_PROPOSAL": "0"}
        front_proposal.default_on_for_local_play(environ)
        self.assertFalse(front_proposal.enabled(environ))

    def test_only_the_local_play_entry_point_sets_it(self):
        source = Path(local_play.__file__).read_text(encoding="utf-8")
        self.assertIn("default_on_for_local_play(os.environ)", source)

    def test_the_share_counts_free_lines_that_reached_the_model(self):
        rows = [{"route": "front:look", "reached_model": True}, {"route": "owner_first", "reached_model": False},
                {"route": "skipped:typed", "reached_model": False}, {"route": "skipped:combat", "reached_model": False},
                {"route": "fallback:invalid", "reached_model": True}]
        self.assertEqual(front_proposal.share(rows), {"free_lines": 3, "reached_model": 2, "share": 2 / 3})

    def test_a_typed_turn_an_early_owner_answers_is_no_free_line(self):
        class Session:
            world_state = {}
        session = Session()
        front_proposal.begin(session, typed=True)
        self.assertEqual(session._front_route, "skipped:typed")
        front_proposal.begin(session, typed=False)
        self.assertEqual(session._front_route, "owner_first")


if __name__ == "__main__":
    unittest.main()
