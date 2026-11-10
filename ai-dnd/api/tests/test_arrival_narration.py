"""Dilim 3b Task 3: one arrival function proposes a short model scene, checks it and falls back to Python."""
import copy
import json
import types
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import arrival_narration
import game
import local_places
from api import model_phase
from api.ollama_adapter import _MODEL_CALLS
from api.tests.test_interaction_adventure import session as adventure_session

WALK = "mezarlığa gidiyorum"
WALK_AND_ASK = "mezarlığa gidip bir kürek istiyorum"


class FakeModel:
    """Answers the arrival call: a narration string, a whole packet, an exception, or a callable."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        answer = self.answer(**kwargs) if callable(self.answer) else self.answer
        if isinstance(answer, BaseException):
            raise answer
        packet = answer if isinstance(answer, dict) else {"narration": answer, "world_updates": {}, "lore_claims": []}
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


@contextmanager
def bound(session):
    token = game._ACTIVE_SESSION.set(session)
    try:
        yield
    finally:
        game._ACTIVE_SESSION.reset(token)


@contextmanager
def counted_turn(used):
    token = _MODEL_CALLS.set(None if used is None else ["x"] * used)
    try:
        yield
    finally:
        _MODEL_CALLS.reset(token)


def graveyard(*, local_issue=False, marks=False, hour=12):
    """A session standing in a fresh graveyard with its keeper."""
    s = adventure_session()
    s.character["name"] = "Aren"
    if hour is None:
        s.world_state.pop("campaign_time", None)
    else:
        s.world_state["campaign_time"]["start_second"] = hour * 3600
    with bound(s):
        record = local_places.create_local_place(s.world_state, "here", "graveyard")
        s.world_state["location"] = record["id"]
        npc, feature = local_places.furnish(s.world_state, record, create_npc=game.create_npc_from_ai,
                                            create_feature=game.create_local_feature)
    record.pop("local_issue", None)
    if local_issue:
        record["local_issue"] = "Mezarlardan birinin başındaki fener sönük duruyor."
    if marks:
        s.world_state["flags"].setdefault("deeds", []).append(
            {"kind": "theft_unseen", "victim_id": npc["id"], "at": -10 ** 7, "item": ""})
    return _place(s, record["id"], npc["id"], feature)


def _place(s, place_id, npc_id, feature):
    world = s.world_state
    npc = next(n for n in world["npcs"] if n.get("id") == npc_id)
    feature = next((f for f in world["features"] if f.get("id") == (feature or {}).get("id")), feature)
    return types.SimpleNamespace(session=s, world=world, world_state=world, record=world["locations"][place_id],
                                 npc=npc, feature=feature)


def twin(place):
    s = copy.deepcopy(place.session)
    return _place(s, place.record["id"], place.npc["id"], place.feature)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.current = None

    def parts_of(self, place, *, first=True):
        with bound(place.session):
            return local_places.arrival_parts(place.world, place.record, place.npc, place.feature, first_visit=first)

    def scene(self, **kwargs):
        self.current = graveyard(**kwargs)
        return self.parts_of(self.current)

    def return_after(self, seconds):
        self.current = graveyard()
        self.parts_of(self.current)
        self.current.world["campaign_time"]["elapsed_seconds"] += seconds
        return self.parts_of(self.current, first=False)

    def twin_worlds(self):
        a = graveyard()
        return a, twin(a)

    def twin_sessions(self):
        return self.twin_worlds()

    def narrate(self, *, answer, scene=None, used=0, player_input=WALK, session=None):
        if session is not None:
            place = session
            scene = scene or self.parts_of(place)
        else:
            if scene is None:
                scene = self.scene()
            place = self.current
        self.client = FakeModel(answer)
        with bound(place.session), patch.object(game, "ollama", self.client), counted_turn(used):
            return arrival_narration.narrate(game, scene, player_input=player_input,
                                             messages=place.session.messages)

    def sent_messages(self, hour):
        scene = self.scene(hour=hour)
        self.narrate(scene=scene, answer="Rüzgâr esiyor.")
        return self.client.calls[0]["messages"]



class Parts(Fixture):
    def test_arrival_text_is_the_parts_joined(self):
        for first in (True, False):
            with self.subTest(first=first):
                a, b = self.twin_worlds()
                with bound(a.session):
                    parts = local_places.arrival_parts(a.world, a.record, a.npc, None, first_visit=first)
                with bound(b.session):
                    text = local_places.arrival_text(b.world, b.record, b.npc, None, first_visit=first)
                self.assertEqual(text, " ".join(p for p in (parts["fallback"], parts["facts_line"]) if p))
                self.assertEqual(a.world, b.world)

    def test_short_return_does_not_want_the_model(self):
        parts = self.return_after(600)
        self.assertFalse(parts["wants_model"])
        self.assertTrue(self.return_after(1800)["wants_model"])

    def test_parts_carry_the_scene(self):
        parts = self.scene(local_issue=True)
        self.assertEqual((parts["noun"], parts["form"], parts["visit"], parts["burning"]),
                         ("mezarlık", "open_air", "first", False))
        self.assertEqual(parts["present"][0]["name"], game.living_world.public_npc_name(self.current.npc))
        self.assertTrue(parts["presence_line"].startswith(parts["present"][0]["name"] + " burada. "))
        self.assertIn(parts["presence_line"], parts["fallback"])
        self.assertEqual(parts["facts_line"], "Mezarlardan birinin başındaki fener sönük duruyor.")
        self.assertTrue(parts["wants_model"])


class Narrate(Fixture):
    def test_accepted_text_leads_and_facts_follow(self):
        text, info = self.narrate(answer="Taşların arasında rüzgâr dolaşıyor. Otlar hışırdıyor.")
        self.assertTrue(text.startswith("Taşların arasında rüzgâr dolaşıyor."), text)
        self.assertEqual(info, {"source": "model", "reason_code": None, "calls": 1})
        self.assertEqual(self.current.session.last_arrival_narration, info)

    def test_a_bare_narration_packet_is_read_as_empty_proposals(self):
        text, info = self.narrate(answer={"narration": "Taşların arasında rüzgâr dolaşıyor."})
        self.assertEqual(info["source"], "model")
        self.assertTrue(text.startswith("Taşların arasında rüzgâr dolaşıyor."), text)

    def test_fact_lines_follow_the_model_text_unchanged(self):
        scene = self.scene(local_issue=True, marks=True)
        self.assertIn("kesesini yokluyor", scene["facts_line"])
        text, _ = self.narrate(scene=scene, answer="Rüzgâr esiyor.")
        self.assertTrue(text.endswith(scene["facts_line"]), text)
        self.assertEqual(text.count(scene["facts_line"]), 1)

    def test_presence_line_is_added_only_when_the_name_is_missing(self):
        scene = self.scene()
        name = scene["present"][0]["name"]
        without, _ = self.narrate(scene=scene, answer="Rüzgâr esiyor.")
        self.assertIn(scene["presence_line"], without)
        self.assertEqual(without.count(scene["presence_line"]), 1)
        with_name, info = self.narrate(scene=self.scene(), answer=f"{name} toprağı düzlüyor.")
        self.assertEqual(info["source"], "model", with_name)
        self.assertNotIn(" burada. ", with_name)

    def test_unsafe_model_text_is_repaired_or_replaced(self):
        cases = {
            "world_updates": {"narration": "Rüzgâr.", "world_updates": {"create_npcs": [{"name": "Zed"}]},
                              "lore_claims": []},
            "unregistered_person": "Rüzgâr esiyor. Torvald adında bir adam seni bekliyor.",
            "money": "Rüzgâr esiyor. Yerde 5 altın parlıyor.",
            "quoted_speech": "Rüzgâr esiyor. “Hoş geldin,” diyor biri.",
            "too_long": "Bir. İki. Üç. Dört. Beş. Altı.",
            "empty": "",
        }
        for case, answer in cases.items():
            with self.subTest(case=case):
                text, info = self.narrate(answer=answer)
                for bad in ("Torvald", "5 altın", "“Hoş geldin", "Beş."):
                    self.assertNotIn(bad, text)
                if case in ("world_updates", "empty"):
                    self.assertEqual(info["source"], "python")
                    self.assertTrue(text.startswith(self.scene()["fallback"][:20]))

    def test_proposals_are_refused_with_their_code(self):
        _, info = self.narrate(answer={"narration": "Rüzgâr.", "world_updates": {}, "lore_claims": [{"x": 1}]})
        self.assertEqual((info["source"], info["reason_code"]), ("python", "MODEL_WORLD_PROPOSAL_REJECTED"))
        _, info = self.narrate(answer=["Rüzgâr."])
        self.assertEqual((info["source"], info["reason_code"]), ("python", "invalid_packet"))

    def test_world_is_identical_with_and_without_the_call(self):
        called, uncalled = self.twin_sessions()
        self.narrate(session=called, answer="Rüzgâr esiyor.")
        self.narrate(session=uncalled, answer=RuntimeError("down"))
        self.assertEqual(called.world_state, uncalled.world_state)

    def test_a_model_error_gives_the_fallback(self):
        scene = self.scene()
        text, info = self.narrate(scene=scene, answer=RuntimeError("down"))
        self.assertEqual(text, " ".join(p for p in (scene["fallback"], scene["facts_line"]) if p))
        self.assertEqual((info["source"], info["reason_code"], info["calls"]), ("python", "model_error", 1))

    def test_an_assertion_from_a_fake_is_a_model_error_too(self):
        _, info = self.narrate(answer=AssertionError("must not call a real model"))
        self.assertEqual((info["source"], info["reason_code"]), ("python", "model_error"))

    def test_the_call_is_resolved_narration(self):
        phases = []
        self.narrate(answer=lambda **kw: phases.append(model_phase.ModelFailure("X").phase) or "Rüzgâr.")
        self.assertEqual(phases, ["resolved_narration"])

    def test_no_call_when_the_budget_is_spent(self):
        _, info = self.narrate(used=2, answer="Rüzgâr.")
        self.assertEqual((info["calls"], info["reason_code"]), (0, "no_budget"))
        self.assertEqual(self.client.calls, [])

    def test_a_spoken_request_keeps_the_last_call(self):
        _, info = self.narrate(used=1, player_input=WALK_AND_ASK, answer="Rüzgâr.")
        self.assertEqual((info["calls"], info["reason_code"]), (0, "speech_first"))
        _, info = self.narrate(used=0, player_input=WALK_AND_ASK, answer="Rüzgâr.")
        self.assertEqual(info["calls"], 1)

    def test_no_counted_turn_no_call(self):
        _, info = self.narrate(used=None, answer="Rüzgâr.")
        self.assertEqual((info["calls"], info["reason_code"]), (0, "no_counted_turn"))

    def test_short_return_makes_no_call(self):
        _, info = self.narrate(scene=self.return_after(600), answer="Rüzgâr.")
        self.assertEqual((info["calls"], info["reason_code"]), (0, "short_return"))
        self.assertEqual(self.client.calls, [])

    def test_the_prompt_carries_time_place_people_and_no_exits(self):
        sent = self.sent_messages(hour=18)
        facts = json.loads(sent[1]["content"])
        self.assertEqual(facts["ziyaret"], "ilk")
        self.assertEqual(facts["zaman"]["vakit"], "akşam")
        self.assertIn("oradakiler", facts)
        self.assertEqual(facts["yer"]["tur"], "mezarlık")
        for absent in ("cikislar", "hava", "kese", "gorevler", "yokluk"):
            self.assertNotIn(absent, facts)
        self.assertNotIn("zaman", json.loads(self.sent_messages(hour=None)[1]["content"]))
        self.assertIn(arrival_narration.RULES, sent[0]["content"])
        self.assertIn(game.NARRATOR_VOICE, sent[0]["content"])
        kwargs = self.client.calls[0]
        self.assertEqual(kwargs["format"], arrival_narration.SCHEMA)
        self.assertEqual(arrival_narration.SCHEMA["properties"]["arrival"], {"type": "boolean"})

    def test_a_return_tells_the_absence_in_words(self):
        scene = self.return_after(3 * 3600)
        facts = arrival_narration.facts(scene, [{"role": "assistant", "content": "x" * 600}])
        self.assertEqual((facts["ziyaret"], facts["yokluk"]), ("dönüş", "birkaç saat"))
        self.assertEqual(facts["son_anlatim"], "x" * 400)
        self.assertEqual(arrival_narration.facts(self.return_after(3 * 86400), [])["yokluk"], "birkaç gün")

    def world(self):
        return {"locations": {}, "npcs": [], "flags": {}}

    def inn_record(self):
        return {"id": "inn", "name": "Kırık Fıçı Hanı", "description": "Isıl, kalabalık bir han.", "type": "building"}

    def test_a_venue_scene_keeps_todays_fallback(self):
        scene = arrival_narration.venue_scene(self.world(), self.inn_record(), [])
        self.assertEqual(scene["fallback"], f"Kapıdan içeri giriyorsun. {self.inn_record()['name']} içindesin. "
                                            f"{self.inn_record()['description']} İçerisi sessiz.")
        self.assertEqual((scene["presence_line"], scene["facts_line"], scene["wants_model"]), ("", "", True))

    def test_a_venue_scene_with_people_names_them(self):
        people = [{"id": "n1", "name": "Mira", "name_known_to_player": True, "role": "Hancı"}]
        scene = arrival_narration.venue_scene(self.world(), self.inn_record(), people, seen_before=True)
        who = game.living_world.public_scene_people(people)
        self.assertTrue(scene["fallback"].endswith(f" İçeride {who} var."), scene["fallback"])
        self.assertEqual(scene["presence_line"], f" İçeride {who} var.")
        self.assertEqual(scene["visit"], "return")


if __name__ == "__main__":
    unittest.main()
