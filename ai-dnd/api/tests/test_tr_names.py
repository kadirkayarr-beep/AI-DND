"""One Turkish name table for spells and items: two-way consistent, read by the parsers and the narrator prompt."""
import json
import unittest

import spell_scope
import spells
import tr_names
from api.dnd_2024_rules import SPELLS_CATALOG

RULES = json.loads((tr_names.TABLE_PATH.parents[1] / "rules" / "phb2024" / "spells.json").read_text(encoding="utf-8"))
WEAPONS_ARMOR = json.loads((tr_names.TABLE_PATH.parents[1] / "rules" / "phb2024" / "weapons_armor.json").read_text(encoding="utf-8"))


class TrNamesTests(unittest.TestCase):
    def test_every_rules_spell_and_weapon_and_armor_has_a_name(self):
        self.assertEqual([s for s in RULES["spells"] if s not in tr_names.table()["spells"]], [])
        ids = [*WEAPONS_ARMOR["weapons"], *WEAPONS_ARMOR["armor"], "Shield"]
        self.assertEqual([i for i in ids if i not in tr_names.table()["items"]], [])

    def test_table_is_two_way_consistent(self):
        for kind in tr_names.KINDS:
            for item_id, name in tr_names.table()[kind].items():
                with self.subTest(kind=kind, id=item_id):
                    self.assertEqual(tr_names.to_id(name, kind), item_id)
                    self.assertEqual(tr_names.to_tr(item_id, kind), name)
            for item_id, names in tr_names.table()["aliases"].items():
                for name in names:
                    if item_id in tr_names.table()[kind]:
                        self.assertEqual(tr_names.to_id(name, kind), item_id, name)

    def test_typed_turkish_name_is_recognised_without_diacritics_or_case(self):
        for text in ("Sihirli Füze", "sihirli fuze", "SİHİRLİ  FÜZE", "Sihirli Ok", "magic missile"):
            self.assertEqual(tr_names.to_id(text, "spells"), "Magic Missile", text)
        self.assertEqual(tr_names.to_id("Büyük Kılıç", "items"), "Greatsword")

    def test_unknown_name_falls_back_to_english(self):
        self.assertIsNone(tr_names.to_id("Bilinmeyen Büyü", "spells"))
        self.assertEqual(tr_names.to_tr("Totally Unknown Spell"), "Totally Unknown Spell")
        self.assertEqual(tr_names.narrator_line(["Totally Unknown Spell"]), "")

    def test_export_matches_the_table(self):
        exported = json.loads(tr_names.export_json())
        self.assertEqual(exported["spells"], tr_names.table()["spells"])
        self.assertEqual(exported["items"], tr_names.table()["items"])

    def test_narrator_line_names_turkish_and_keeps_the_id(self):
        line = tr_names.narrator_line(["Magic Missile", "Dagger"])
        self.assertIn("Magic Missile = Sihirli Füze", line)
        self.assertIn("Dagger = Hançer", line)

    def test_player_text_with_turkish_name_reaches_the_engine_parsers(self):
        self.assertEqual(spells.classify_cast_phrase("Sihirli Ok büyüsü yapıyorum"), {"kind": "v1", "spell_id": "Magic Missile"})
        self.assertTrue(spell_scope.explicit_request("Sihirli Ok kullanıyorum"))
        self.assertEqual(spell_scope.ALIASES["sihirli ok"], "Magic Missile")
        for old in ("ateş oku", "sihirli füze", "yara iyilestirme", "kutsama"):
            self.assertIn(old, spell_scope.ALIASES)  # old hand-written aliases keep working

    def test_catalog_spells_all_resolve_from_their_turkish_name(self):
        for spell_id in spell_scope.CATALOG:
            with self.subTest(spell=spell_id):
                self.assertEqual(tr_names.to_id(tr_names.to_tr(spell_id, "spells"), "spells"), spell_id)
                self.assertIn(tr_names.fold(tr_names.to_tr(spell_id, "spells")), {tr_names.fold(a) for a in spell_scope.ALIASES})

    def test_narrator_note_covers_known_spells_and_carried_items_only(self):
        note = tr_names.narrator_note(["Magic Missile", "Unlisted Spell"], ["Dagger", "Zırh Parçası"])
        self.assertIn("Magic Missile = Sihirli Füze", note)
        self.assertIn("Dagger = Hançer", note)
        self.assertNotIn("Unlisted Spell", note)
        self.assertEqual(tr_names.narrator_note([], []), "")

    def test_game_prompt_carries_the_narrator_note(self):
        import inspect
        import game
        self.assertIn("tr_names.narrator_note(", inspect.getsource(game._dm_prompt_note))
        self.assertGreaterEqual(inspect.getsource(game).count("_dm_prompt_note("), 2)  # defined and called in the narrator prompt
