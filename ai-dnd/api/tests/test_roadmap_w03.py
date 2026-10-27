"""W03 (D4): an attributed NPC claim keeps its speaker; a known fact may get a SEPARATE narrator note.

Design Rev2 §5.5: an NPC's words stay the NPC's words even when the verified world contradicts them; the system does not silently
rewrite the line. If the player already knows (or perceives) the lock, a separate narrator sentence may recall that known state;
if the lock is an unknown secret the narrator does not reveal it as a "correction". A later correction by the NPC keeps both
statements with their time and owner. No new NPC line or player action is invented.
"""
from __future__ import annotations

import copy
import unittest

import attributed_claims
import game
import npc_statements

CITY, TAVERN = "city_test", "loc_tavern"
TAVERN_NAME = "Kızıl Ejder Hanı"
QUOTE = f"{TAVERN_NAME} şehir merkezindedir; uğramaya değer."
ASK = "Şehirde gidebileceğim sakin bir yer önerir misin?"


def world(*, locked=True, lock_known=False):
    door = {"id": f"venue-door:{TAVERN}", "location": CITY, "locked": locked, "open": False, "name": "Han kapısı"}
    # what the player knows lives in flags, never on the door's mechanical record
    return {
        "location": CITY, "flags": {"turn_index": 3, **({"known_locked_door_ids": [door["id"]]} if lock_known else {})},
        "locations": {
            CITY: {"id": CITY, "name": "Neverwinter", "type": "city"},
            TAVERN: {"id": TAVERN, "name": TAVERN_NAME, "type": "building", "scene_kind": "tavern",
                     "parent_location_id": CITY, "aliases": [], "reality_layer": "PROCEDURAL_LOCAL_FICTION"},
        },
        "doors": [door], "npcs": [],
    }


NPC = {"id": "npc_guard", "name": "Marek", "location": CITY}


class AttributedClaimTests(unittest.TestCase):
    def test_claim_keeps_speaker_and_known_correction(self):
        unknown_world = world(lock_known=False)
        known_world = world(lock_known=True)
        spoken_unknown = game._ground_local_place_recommendation_reply(QUOTE, NPC, unknown_world, ASK)
        spoken_known = game._ground_local_place_recommendation_reply(QUOTE, NPC, known_world, ASK)
        claim = {"speaker_text": QUOTE, "source_event_id": "interaction:ev1", "subject": {"name": TAVERN_NAME, "locked": True}}
        unknown_view = attributed_claims.present_claim(claim, {"lock_known_to_player": False})
        known_view = attributed_claims.present_claim(claim, {"lock_known_to_player": True})
        # --- a later correction by the NPC: both statements survive with their time and owner --------------------------
        state_world = world()
        npc_statements.record(state_world, NPC, ASK, f"Marek: “{QUOTE}”", turn=3)
        correction = f"{TAVERN_NAME} bugün kilitli, oraya gitme."
        npc_statements.record(state_world, NPC, "Emin misin?", f"Marek: “{correction}”", turn=5)
        history = npc_statements.ensure(state_world)["statements"][NPC["id"]]
        obs = {
            "speaker_text": spoken_unknown,
            "original_npc_claim": QUOTE,
            "unknown_lock_disclosed": "kilitli" in spoken_unknown.casefold() or bool(unknown_view["narrator_note"]),
            "known_lock_note_speaker": "narrator" if known_view["narrator_note"] else None,
            "later_correction_preserves_original_source": (
                [(item["turn"], item["text"]) for item in history] == [(3, QUOTE), (5, correction)]),
        }
        assert obs["speaker_text"] == obs["original_npc_claim"]
        assert obs["unknown_lock_disclosed"] is False
        assert obs["known_lock_note_speaker"] == "narrator"
        assert obs["later_correction_preserves_original_source"] is True
        self.assertEqual(spoken_known, QUOTE, "knowing the lock never rewrites the NPC's own words")
        self.assertEqual(known_view["speaker_text"], QUOTE)
        self.assertIn("kilitli", known_view["narrator_note"].casefold())
        self.assertNotIn("kilitli", known_view["speaker_text"].casefold(), "the note is separate from the NPC line")
        self.assertEqual(known_view["source_event_id"], "interaction:ev1")

    def test_the_real_note_path_follows_player_knowledge(self):
        self.assertIsNone(game._attributed_place_note(QUOTE, NPC, world(lock_known=False), ASK))
        self.assertIn("kilitli", game._attributed_place_note(QUOTE, NPC, world(lock_known=True), ASK).casefold())

    def test_a_pure_door_query_does_not_teach_the_lock(self):
        w = world(lock_known=False)
        game._venue_entry_door(w, CITY, TAVERN)
        game._venue_entry_door(w, CITY, TAVERN)
        self.assertFalse(w["flags"].get("known_locked_door_ids"), "route planning must not reveal a hidden lock")
        self.assertIsNone(game._attributed_place_note(QUOTE, NPC, w, ASK))

    def test_a_closed_door_refusal_does_not_teach_the_lock(self):
        # review finding: "kapalı. İçeri geçemezsin." never says locked, so the travel refusals do not mark the lock as seen
        import inspect
        for function in (game._adventure_travel_reply,):
            self.assertNotIn("_mark_lock_seen", inspect.getsource(function))
        w = world(lock_known=False)
        game._venue_entry_door(w, CITY, TAVERN)
        self.assertFalse(game._lock_known_to_player(w, f"venue-door:{TAVERN}"))
        w["flags"]["known_locked_door_ids"] = None  # a damaged save must fail closed, not raise
        self.assertFalse(game._lock_known_to_player(w, f"venue-door:{TAVERN}"))
        game._mark_lock_seen(w, w["doors"][0])
        self.assertTrue(game._lock_known_to_player(w, f"venue-door:{TAVERN}"))

    def test_the_player_learns_a_lock_by_being_turned_back_at_the_door(self):
        w = world(lock_known=False)
        before_door = dict(w["doors"][0])
        self.assertFalse(game._lock_known_to_player(w, before_door["id"]), "control: unknown before the attempt")
        door = game._mark_lock_seen(w, game._venue_entry_door(w, CITY, TAVERN))
        self.assertTrue(game._lock_known_to_player(w, door["id"]))
        self.assertEqual(w["doors"][0], before_door, "knowing the lock leaves the door's mechanical record unchanged")
        reply = game._ground_local_place_recommendation_reply(QUOTE, NPC, w, ASK)
        self.assertEqual(reply, QUOTE)
        view = attributed_claims.present_claim(
            {"speaker_text": QUOTE, "source_event_id": "e", "subject": {"name": TAVERN_NAME, "locked": True}},
            {"lock_known_to_player": game._lock_known_to_player(w, door["id"])})
        self.assertEqual(view["narrator_note_speaker"], "narrator")

    def test_an_unknown_lock_is_not_revealed_as_a_correction(self):
        claim = {"speaker_text": QUOTE, "source_event_id": "interaction:ev2", "subject": {"name": TAVERN_NAME, "locked": True}}
        view = attributed_claims.present_claim(claim, {"lock_known_to_player": False})
        self.assertIsNone(view["narrator_note"])
        self.assertEqual(view["speaker_text"], QUOTE)

    def test_an_open_place_gets_no_note_and_no_invented_speech(self):
        claim = {"speaker_text": QUOTE, "source_event_id": "interaction:ev3", "subject": {"name": TAVERN_NAME, "locked": False}}
        view = attributed_claims.present_claim(claim, {"lock_known_to_player": True})
        self.assertEqual((view["speaker_text"], view["narrator_note"]), (QUOTE, None))
        self.assertEqual(game._ground_local_place_recommendation_reply(QUOTE, NPC, world(locked=False), ASK), QUOTE)

    def test_the_input_claim_is_never_mutated(self):
        claim = {"speaker_text": QUOTE, "source_event_id": "e", "subject": {"name": TAVERN_NAME, "locked": True}}
        frozen = copy.deepcopy(claim)
        attributed_claims.present_claim(claim, {"lock_known_to_player": True})
        self.assertEqual(claim, frozen)


if __name__ == "__main__":
    unittest.main()
