"""G2.12 rows.

D-057: a running narrative spell reaches the next turn's scene prompt.
D-280: eight spells are read by their Turkish name.
"""
import json
import unittest
from collections.abc import Callable
from typing import Any

import game
import spell_effects
from api.tests.test_dilim4c_5_narrative_spells import wizard
from api.tests.test_spell_preparation_4c2 import now

# The engine's `bound` wrapper (game.py) adds the session= keyword that the plain function does not show.
world_context: Callable[..., dict[str, Any]] = game.build_world_context


class RunningSpellReachesNextTurnTests(unittest.TestCase):
    """D-057."""

    def test_a_running_narrative_spell_is_in_the_next_scene_context(self) -> None:
        """A spell still running shows its name, effect and seconds left."""
        s = wizard()
        self.assertNotIn("active_spell_effects", world_context(session=s))
        spell_effects.resolve(s, ("narrative", "Mage Hand"))
        s.world_state["campaign_time"]["elapsed_seconds"] += 30  # next turn
        listed = world_context(session=s)["active_spell_effects"]
        self.assertEqual([entry["spell"] for entry in listed], ["Mage Hand"])
        self.assertEqual(listed[0]["seconds_left"], 30)
        self.assertEqual(listed[0]["name_tr"], "Büyücü Eli")
        self.assertIn("hayalet bir el", listed[0]["effect"])
        context = world_context(session=s)
        self.assertIn("Büyücü Eli", json.dumps(context, ensure_ascii=False))

    def test_a_spell_cast_elsewhere_is_not_in_this_scene(self) -> None:
        """After travel the narrator hears nothing of a spell left behind."""
        s = wizard()
        spell_effects.resolve(s, ("narrative", "Mage Hand"))
        self.assertIn("active_spell_effects", world_context(session=s))
        s.world_state["location"] = "somewhere_else"
        self.assertNotIn("active_spell_effects", world_context(session=s))

    def test_a_finished_spell_is_not_in_the_context(self) -> None:
        """A spell past its end leaves no trace in the context."""
        s = wizard()
        spell_effects.resolve(s, ("narrative", "Mage Hand"))
        s.world_state["campaign_time"]["elapsed_seconds"] += 60
        self.assertEqual(spell_effects.active(s.world_state), [])
        self.assertNotIn("active_spell_effects", world_context(session=s))
        self.assertEqual(now(s), s.world_state["campaign_time"]["elapsed_seconds"])


class EightSpellsReadByTurkishNameTests(unittest.TestCase):
    """D-280."""

    def test_each_unresolved_spell_is_named_by_its_turkish_name(self) -> None:
        """A Turkish name reads as that spell, not as a negation or a shorter spell."""
        table = {
            "Yaşam Karşıtı Kabuk büyüsünü yapıyorum": "Antilife Shell",
            "Yaşam Aurası büyüsünü yapıyorum": "Aura of Life",
            "Sahte Yaşam büyüsünü yapıyorum": "False Life",
            "Gecikmeli Ateş Topu büyüsünü yapıyorum": "Delayed Blast Fireball",
            "Lanet Verme büyüsünü yapıyorum": "Bestow Curse",
            "Lanet Kaldırma büyüsünü yapıyorum": "Remove Curse",
            "Canavarı Büyüleme büyüsünü yapıyorum": "Charm Monster",
            "Mordenkainen'in Muhteşem Köşkü büyüsünü yapıyorum": (
                "Mordenkainen's Magnificent Mansion"
            ),
        }
        for line, spell in table.items():
            with self.subTest(line):
                self.assertEqual(spell_effects.named(line), ("not_yet", spell))
