"""Turkish text folding has one canonical answer, and the catalog mapping is read once (D-515, D-520, D-548)."""
import importlib
import unittest
from pathlib import Path
from unittest.mock import patch

import bound_text
import living_world
import local_dialogue
import name_catalog
import thread_catalog
import town_knowledge
import vouching
import world_threads
from api import opening_narrative

# Letters only, so a copy that also strips punctuation or squeezes spaces still has to agree.
SAMPLES = ("İ", "I", "ı", "i", "ş", "İSTANBUL ışık", "ISPARTA Şişli", "Çiğdem Öğüt")

# Every copy that folds to plain ASCII lower case.
ASCII_COPIES = (
    ("local_dialogue", "normalize_text"),
    ("held_weapon", "_fold"),
    ("local_exploration", "_fold"),
    ("local_places", "_fold"),
    ("npc_statements", "fold"),
    ("spells", "fold_text"),
    ("narration_claims", "fold"),
    ("spell_effects", "_fold"),
    ("everyday_actions", "_fold"),
    ("grounded_action", "fold"),
    ("interaction_adventure", "normalize"),
    ("tr_names", "fold"),
    ("api.lore_authority.claim_authorization", "_fold"),
)
# Copies that keep the Turkish letters on purpose (the caller matches Turkish patterns), so only the i/İ/I part is shared.
LETTER_KEEPING_COPIES = (("referent_span", "fold"), ("adventure.play", "_fold"))


def _copy(module: str, name: str):
    return getattr(importlib.import_module(module), name)


class FoldCopiesTests(unittest.TestCase):
    def test_every_fold_copy_matches_canonical(self):
        for module, name in ASCII_COPIES:
            fold = _copy(module, name)
            for text in SAMPLES:
                with self.subTest(copy=f"{module}.{name}", text=text):
                    self.assertEqual(fold(text), living_world.normalize_text(text))

    def test_letter_keeping_copies_agree_after_canonical_fold(self):
        for module, name in LETTER_KEEPING_COPIES:
            fold = _copy(module, name)
            for text in SAMPLES:
                with self.subTest(copy=f"{module}.{name}", text=text):
                    self.assertEqual(living_world.normalize_text(fold(text)), living_world.normalize_text(text))

    def test_second_normalize_text_is_the_canonical_one(self):
        self.assertIs(local_dialogue.normalize_text, living_world.normalize_text)


class MappingLoadedOnceTests(unittest.TestCase):
    def _clear_caches(self):
        for owner, name in ((name_catalog, "mapping"), (name_catalog, "_pools"), (town_knowledge, "_role_profiles"),
                            (vouching, "_table"), (opening_narrative, "_catalog")):
            getattr(getattr(owner, name, None), "cache_clear", lambda: None)()

    def test_mapping_loaded_once(self):
        self._clear_caches()
        self.addCleanup(self._clear_caches)
        patcher = patch.object(bound_text, "_rules_cache", None)
        patcher.start()
        self.addCleanup(patcher.stop)
        reads: list[Path] = []
        real = Path.read_text

        def spy(path, *args, **kwargs):
            if path.name == "mapping.json":
                reads.append(path)
            return real(path, *args, **kwargs)

        with patch.object(Path, "read_text", spy):
            name_catalog._pools()
            bound_text.rules()
            thread_catalog.load()
            town_knowledge._role_profiles()
            vouching._table()
            world_threads.want_table()
            world_threads.want_table()
            opening_narrative._catalog()
        self.assertEqual(len(reads), 1, reads)
        self.assertTrue(world_threads.want_table())
        self.assertTrue(bound_text.rules())


if __name__ == "__main__":
    unittest.main()
