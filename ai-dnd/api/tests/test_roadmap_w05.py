"""W05: a common object is not an invented person, and the person-invention guard stays closed for unknown names.

Evidence decides (referent_span.classify_referent_span): a canonical registered name wins and carries its entity id; a word
that is an everyday scene object or that the scene itself uses as a lowercase noun is an object; any other capitalised word
stays an unknown name and is still rejected. No forbidden-word list grows and the guard is not switched off.
"""
from __future__ import annotations

import unittest

import game
import referent_span

OBSERVED = {"action": "explore", "status": "observed"}


def verdict(session, text):
    return not session._narration_is_unsafe(text, "etrafa bak", None, OBSERVED)  # True = accepted


class CommonObjectNotPersonTests(unittest.TestCase):
    def test_common_object_not_invented_person(self):
        session = game.create_session(seed=12)
        person_session = game.create_session(seed=12)
        person_session.world_state["npcs"].append({
            "id": "npc_bardak", "name": "Bardak", "role": "Çırak", "location": person_session.world_state["location"],
            "memory": [],
        })
        canonical = referent_span.classify_referent_span("Bardak", {"bardak": "npc_bardak"}, {})
        obs = {
            "Bardak durur.": {"accepted": verdict(session, "Bardak durur.")},
            "invented_person_claim": {"accepted": verdict(session, "Elara durur.")},
            "canonical_person_named_Bardak": canonical,
            "expected_person_id": "npc_bardak",
            "canonical_person_scene_accepts": verdict(person_session, "Bardak durur."),
            "dotted_turkish_object": referent_span.classify_referent_span("MASA", {}, {})["kind"],
            "scene_noun_evidence": referent_span.classify_referent_span(
                "Fenerler", {}, {"scene_texts": ["Duvarda eski fenerler asılı."]})["kind"],
            "unknown_stays_unknown": referent_span.classify_referent_span("Elara", {}, {})["kind"],
        }
        assert obs["Bardak durur."]["accepted"] is True
        assert obs["invented_person_claim"]["accepted"] is False
        assert obs["canonical_person_named_Bardak"]["entity_id"] == obs["expected_person_id"]
        self.assertEqual(canonical["kind"], "canonical_person")
        self.assertTrue(obs["canonical_person_scene_accepts"], "a registered person named Bardak stays acceptable")
        self.assertEqual(obs["dotted_turkish_object"], "common_object")
        self.assertEqual(obs["scene_noun_evidence"], "common_object")
        self.assertEqual(obs["unknown_stays_unknown"], "unknown_name")

    def test_name_shaped_words_are_not_cleared_as_objects(self):
        # review finding: given names and short object stems plus a vowel must not pass as objects
        for word in ("Meşale", "Ocak", "Mugi", "Mumi", "Masai", "Cupa"):
            self.assertEqual(referent_span.classify_referent_span(word, {}, {})["kind"], "unknown_name", word)
        self.assertEqual(referent_span.classify_referent_span("Masa", {}, {})["kind"], "common_object")
        self.assertEqual(referent_span.classify_referent_span("Tabak", {}, {})["kind"], "common_object")
        # only the scene's own lowercase use clears an otherwise unknown word
        self.assertEqual(referent_span.classify_referent_span(
            "Meşale", {}, {"scene_texts": ["Duvarda bir meşale yanıyor."]})["kind"], "common_object")

    def test_a_person_name_inside_scene_text_is_not_object_evidence(self):
        # only lowercase uses count; "Elara" capitalised in a description must not turn the name into an object
        result = referent_span.classify_referent_span("Elara", {}, {"scene_texts": ["Elara pencerenin önünde bekler."]})
        self.assertEqual(result["kind"], "unknown_name")


if __name__ == "__main__":
    unittest.main()
