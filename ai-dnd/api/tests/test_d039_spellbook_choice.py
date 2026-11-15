"""D-039 (Kadir 2026-11-15): an old save's Wizard chooses the spellbook once.

Save formats 1-3 carry no creation spells, so a Wizard from such a save has no book (`spellcasting_v1` stays version 1,
`spellbook_missing`). The player picks six level-1 Wizard spells (PHB 2024, Wizard Spellbook); the engine only offers a
ready suggestion and never writes a book by itself. The choice is validated on the server, saved like the creation
selections (`character["spells"]`, then the existing version-1 -> 2 migration), and is outside Undo: it makes the last
turn's undo stale like any other saved change.
"""
import copy
import hashlib
import json
import tempfile
import uuid
from pathlib import Path

import game
import spell_preparation
import spell_scope
import unittest
from api.dnd_2024_rules import SPELLS_CATALOG
from api.tests.test_economic_action_http import EconomicHttpFixture
from api.tests.test_spell_preparation_4c2 import prepper, v1_of
from api.tests.test_wizard_cleric_4c3 import created, earn, step
from api.tests.town_seed import fixed_town
import character_progression as cp

WIZARD_LIST = [s["id"] for s in SPELLS_CATALOG["Wizard"]["spells_level_1"]]
SUGGESTED = WIZARD_LIST[:6]  # the quick-build rule of character creation: the first six of the class list
CHOSEN = ["Shield", "Sleep", "Identify", "Charm Person", "Feather Fall", "Thunderwave"]


def bookless(session=None):
    """A level-1 Wizard as a save format 1-3 loads it: version-1 spell state and no creation spells."""
    s = prepper("Wizard", session)
    s.world_state["spellcasting_v1"] = v1_of(s.world_state["spellcasting_v1"])
    s.character["spells"] = []
    spell_scope.upgrade(s.world_state, s.character)
    assert s.world_state["spellcasting_v1"]["version"] == 1
    return s


class SpellbookChoice(unittest.TestCase):
    def test_the_view_offers_the_wizard_list_and_a_ready_suggestion(self):
        view = spell_preparation.view(bookless())
        self.assertEqual((view["supported"], view["blocked_reason"]), (False, "spellbook_missing"))
        self.assertEqual(view["spellbook_options"], WIZARD_LIST)
        self.assertEqual(view["suggested_spellbook"], SUGGESTED)
        for ready in (prepper("Wizard"), prepper("Cleric"), prepper("Sorcerer")):
            other = spell_preparation.view(ready)
            self.assertEqual((other["spellbook_options"], other["suggested_spellbook"]), ([], []))

    def test_a_chosen_book_is_saved_and_the_migration_window_opens(self):
        s = bookless()
        result = spell_preparation.choose_spellbook(s, list(CHOSEN))
        state = s.world_state["spellcasting_v1"]
        self.assertEqual(result["status"], "spellbook_saved")
        self.assertEqual((state["version"], state["spellbook"], state["prepared"]), (2, CHOSEN, []))
        self.assertEqual(state["prepare_window"], {"opened_second": spell_scope.clock_second(s.world_state),
                                                   "reason": "migration"})
        self.assertEqual(s.character["spells"], CHOSEN)
        view = spell_preparation.view(s)
        self.assertEqual((view["supported"], view["blocked_reason"], view["open"], view["candidates"]),
                         (True, None, True, CHOSEN))
        self.assertEqual(spell_preparation.prepare(s, ["Shield"])["status"], "prepared")

    def test_the_suggestion_itself_can_be_accepted(self):
        s = bookless()
        spell_preparation.choose_spellbook(s, list(spell_preparation.view(s)["suggested_spellbook"]))
        self.assertEqual(s.world_state["spellcasting_v1"]["spellbook"], SUGGESTED)

    def test_an_invalid_book_is_refused_and_changes_nothing(self):
        cases = {
            "five": CHOSEN[:5],
            "seven": CHOSEN + ["Magic Missile"],
            "duplicate": CHOSEN[:5] + ["Shield"],
            "not a wizard spell": CHOSEN[:5] + ["Cure Wounds"],
            "a cantrip": CHOSEN[:5] + ["Fire Bolt"],
            "unknown": CHOSEN[:5] + ["Wish"],
            "empty": [],
        }
        for name, requested in cases.items():
            with self.subTest(case=name):
                s = bookless()
                before = (copy.deepcopy(s.world_state), copy.deepcopy(s.character))
                with self.assertRaises(spell_preparation.PrepareRefused) as refused:
                    spell_preparation.choose_spellbook(s, requested)
                self.assertEqual(refused.exception.code, "prepare_spellbook_invalid")
                self.assertEqual((s.world_state, s.character), before)

    def test_only_a_bookless_wizard_may_choose_and_only_once(self):
        s = bookless()
        spell_preparation.choose_spellbook(s, list(CHOSEN))
        for session in (s, prepper("Wizard"), prepper("Cleric"), prepper("Sorcerer")):
            with self.subTest(cls=session.character["class"]):
                before = (copy.deepcopy(session.world_state), copy.deepcopy(session.character))
                with self.assertRaises(spell_preparation.PrepareRefused) as refused:
                    spell_preparation.choose_spellbook(session, list(SUGGESTED))
                self.assertEqual(refused.exception.code, "prepare_spellbook_not_missing")
                self.assertEqual((session.world_state, session.character), before)

    def test_the_chosen_book_saves_and_loads_as_itself(self):
        s = bookless()
        spell_preparation.choose_spellbook(s, list(CHOSEN))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "wizard.json"
            s.save_game(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["player"]["spells"], CHOSEN)
            loaded = game.GameSession()
            loaded.load_game(path)
            self.assertEqual(loaded.world_state["spellcasting_v1"], s.world_state["spellcasting_v1"])
            self.assertEqual(loaded.character["spells"], CHOSEN)
            # the load check still refuses a book the Wizard list cannot hold
            payload["world_state"]["spellcasting_v1"]["spellbook"] = CHOSEN[:5] + ["Cure Wounds"]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(Exception):
                game.GameSession().load_game(path)

    def test_after_the_choice_the_wizard_can_advance(self):
        session = created("Wizard")
        state = session.world_state["spellcasting_v1"]
        session.world_state["spellcasting_v1"] = v1_of(state)
        session.character["spells"] = []
        earn(session, 2)
        self.assertEqual(cp.preview_level_up(session, 2)["reason"], "wizard_spellbook_missing")
        spell_preparation.choose_spellbook(session, list(CHOSEN))
        spell_preparation.prepare(session, [], close=True)
        step(self, session, 2, {"spellbook_spells": ["Magic Missile", "Mage Armor"]})
        self.assertEqual(session.character["progression_level"], 2)
        self.assertEqual(len(session.world_state["spellcasting_v1"]["spellbook"]), 8)
        self.assertEqual(session.world_state["spellcasting_v1"]["spellbook"][:6], CHOSEN)


class SpellbookChoiceApi(EconomicHttpFixture):
    """The one-time choice over HTTP: receipt and replay, refusals, the stored save and Undo."""

    async def asyncSetUp(self):
        with fixed_town(self, 4391):
            await EconomicHttpFixture.asyncSetUp(self)
        self.sid = self.campaign["session_id"]
        self.url = f"/api/game/sessions/{self.sid}/spellcasting/prepare"

    def wizard(self):
        session = bookless(self.record.game_session)
        self.save()
        return session

    def stored(self):
        return self.store.get_campaign(self.campaign["campaign_id"]).payload["engine_save"]

    async def send(self, body):
        return await self.http.post(self.url, json=body)

    async def test_choose_replay_then_prepare(self):
        w = self.wizard()
        view = await self.http.get(self.url)
        self.assertEqual(view.status_code, 200, view.text)
        self.assertEqual((view.json()["blocked_reason"], view.json()["spellbook_options"], view.json()["suggested_spellbook"]),
                         ("spellbook_missing", WIZARD_LIST, SUGGESTED))
        body = {"action_id": str(uuid.uuid4()), "spellbook": CHOSEN}
        chosen = await self.send(body)
        self.assertEqual(chosen.status_code, 200, chosen.text)
        self.assertEqual(chosen.json()["result"]["status"], "spellbook_saved")
        self.assertEqual(w.world_state["spellcasting_v1"]["spellbook"], CHOSEN)
        saved = self.stored()
        self.assertEqual(saved["world_state"]["spellcasting_v1"]["spellbook"], CHOSEN)
        self.assertEqual(saved["world_state"]["spellcasting_v1"]["version"], 2)
        self.assertEqual(saved["player"]["spells"], CHOSEN)
        again = await self.send(body)  # the same action id replays the stored reply and writes nothing twice
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json(), chosen.json())
        conflict = await self.send({**body, "spellbook": SUGGESTED})
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["detail"]["code"], "action_id_conflict")
        view = await self.http.get(self.url)
        self.assertEqual((view.json()["supported"], view.json()["open"], view.json()["reason"], view.json()["spellbook"]),
                         (True, True, "migration", CHOSEN))
        prepared = await self.send({"action_id": str(uuid.uuid4()), "prepared": ["Shield", "Sleep"]})
        self.assertEqual(prepared.status_code, 200, prepared.text)
        self.assertEqual(self.stored()["world_state"]["spellcasting_v1"]["prepared"], ["Shield", "Sleep"])
        twice = await self.send({"action_id": str(uuid.uuid4()), "spellbook": SUGGESTED})
        self.assertEqual(twice.status_code, 409, twice.text)
        self.assertEqual(twice.json()["detail"]["code"], "prepare_spellbook_not_missing")

    async def test_refusals_change_nothing(self):
        w = self.wizard()
        before = (copy.deepcopy(w.world_state), copy.deepcopy(w.character), copy.deepcopy(self.stored()))
        for body, code in (
            ({"spellbook": CHOSEN[:5]}, "prepare_spellbook_invalid"),
            ({"spellbook": CHOSEN[:5] + ["Cure Wounds"]}, "prepare_spellbook_invalid"),
            ({"spellbook": CHOSEN, "prepared": ["Shield"]}, "prepare_request_mixed"),
            ({"spellbook": CHOSEN, "close": True}, "prepare_request_mixed"),
            ({"prepared": ["Shield"]}, "prepare_spellbook_missing"),
        ):
            with self.subTest(body=body):
                refused = await self.send({"action_id": str(uuid.uuid4()), **body})
                self.assertEqual(refused.status_code, 409, refused.text)
                self.assertEqual(refused.json()["detail"]["code"], code)
                self.assertEqual((w.world_state, w.character, self.stored()), before)
        oversized = await self.send({"action_id": str(uuid.uuid4()), "spellbook": ["x" * 65] * 6})
        self.assertEqual(oversized.status_code, 422, oversized.text)

    async def test_a_list_request_keeps_the_receipt_hash_it_had_before_the_book_field(self):
        """A receipt saved before `spellbook` existed must still replay: an absent book stays out of the hash."""
        prepper("Wizard", self.record.game_session)
        self.save()
        action_id = str(uuid.uuid4())
        saved = await self.send({"action_id": action_id, "prepared": ["Shield"]})
        self.assertEqual(saved.status_code, 200, saved.text)
        old_formula = hashlib.sha256(json.dumps({"command": "spell_prepare", "prepared": ["Shield"], "close": False},
                                                sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        self.assertEqual(self.manager.get_turn_action(self.record, action_id)["request_hash"], old_formula)

    async def test_the_choice_is_outside_undo(self):
        """Ruling: the one-time choice is never undone; it makes the earlier turn's undo stale (like a level step)."""
        w = self.wizard()
        turn_id, _ = await self.real_turn()
        chosen = await self.send({"action_id": str(uuid.uuid4()), "spellbook": CHOSEN})
        self.assertEqual(chosen.status_code, 200, chosen.text)
        undone = await self.undo(turn_id)
        self.assertEqual(undone.status_code, 409, undone.text)
        self.assertEqual(undone.json()["detail"]["code"], "undo_stale")
        self.assertEqual(w.world_state["spellcasting_v1"]["spellbook"], CHOSEN)
        self.assertEqual(self.stored()["world_state"]["spellcasting_v1"]["spellbook"], CHOSEN)


if __name__ == "__main__":
    unittest.main()
