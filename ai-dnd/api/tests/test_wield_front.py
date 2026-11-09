"""Drawing a weapon from the front reading (Dilim 2, Task 15; rc3): the model proposes `wield` with a bag id, Python draws
it through `gear` or changes nothing and tells the narrator it did not happen; the narrator's card says what is in hand
and, right under it, one fixed rule line says a refused move is never narrated as done. No real model is called."""
from __future__ import annotations

import copy
import json
import os
from dataclasses import replace
from unittest.mock import patch

import front_proposal
import game
import gear
import refusals
import world_threads
from api import serializers
from api.tests.journeys.runner import (SCENARIO_DIR, JourneyCase, ScriptedModel, _inventory_counts, apply_setup)
from api.tests.journeys.schema import Step, load_scenario
from api.tests.test_truth_card import crowd

_RULE = "MOTOR GERÇEĞİ 'olmadı' diyen bir hamleyi olmuş gibi anlatma; denemeyi ve neden olmadığını anlat."
_TALK_TO_BARMAN = {"intent": "talk", "action": "talk",
                   "target": {"type": "npc", "reference": "Han Sahibi", "npc_id": "barman", "evidence_quote": ""},
                   "completion": "complete"}


# Package C's starting bag, written out so the setup gives each thing an item id (as scenario 04b does): a fresh
# campaign keeps plain names until an owner materializes them, and the front reading lists only items with ids.
PACKAGE_C = ("Greatsword", "Ağır Tatar Yayı & 20 Ok", "Macera Çantası", "Birlik Sancağı Parçası", "Zar Seti",
             "Askeri Pelerin")


def _setup(name, **extra):
    return {**copy.deepcopy(load_scenario(SCENARIO_DIR / name).setup), **extra}


class WieldFront(JourneyCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.use_rc3_setup()

    # --- the played session ---------------------------------------------------------------------------------------
    async def use_setup(self, setup):
        self.setup = setup
        campaign = await self._journey_campaign(setup)
        apply_setup(self, campaign, setup)
        self.campaign_id = campaign["campaign_id"]
        self.session_id = self.last_session_id = campaign["session_id"]
        self.last_turn_action_id = None
        self.last_narrator_input = None

    async def use_rc3_setup(self):
        """rc3: a Fighter with no sword (the bag holds only an adventurer's pack), a hostile bandit near."""
        await self.use_setup(_setup("rc3_refusal_narration.json", front_proposal=True))

    async def use_package_c(self):
        """Scenario 05's setup (package C: Greatsword and a heavy crossbow in the bag, hands empty), no fight."""
        await self.use_setup(_setup("05_greatsword.json", front_proposal=True, inventory=list(PACKAGE_C)))

    @property
    def session(self):
        return self.manager.get(self.session_id).game_session

    @property
    def world(self):
        return self.session.world_state

    def flag(self):
        return patch.dict(os.environ, {front_proposal.FLAG: "1" if self.setup.get("front_proposal") else "0"})

    async def play(self, step):
        with self.flag():
            failures = await self._play(self.session_id, step, ScriptedModel())
        self.assertEqual(failures, [])

    async def say(self, line, front=None, intent=None, konus=None, speech=None):
        script = {key: value for key, value in (("front", front), ("intent", intent), ("speech", speech)) if value}
        await self.play(Step(say=line, command=None, economic_action=None, combat_action=None, script=script or None,
                             expect={}, known_broken=(), real_chain=False, independent=True, konus=konus))

    async def undo(self):
        step = Step(say=None, command=None, economic_action=None, combat_action=None, script=None, expect={},
                    known_broken=(), real_chain=False, independent=True, undo=True)
        self.assertEqual(await self._undo(self.session_id, step, ScriptedModel()), [])

    async def reload(self):
        step = Step(say=None, command=None, economic_action=None, combat_action=None, script=None, expect={},
                    known_broken=(), real_chain=False, independent=True, reload=True)
        failures, _ = await self._reload(self.session_id, step, ScriptedModel())
        self.assertEqual(failures, [])
        self.session_id = self.last_session_id

    def held(self):
        return gear.wielded(self.world)

    def notes(self):
        return list(getattr(self.session, "_turn_notes", None) or [])

    def narrator_input(self):
        self.assertIsNotNone(self.last_narrator_input, "no narrator call this turn")
        return self.last_narrator_input.split("\n")

    def bag(self):
        return _inventory_counts(self.world["inventory"])

    def crowd(self, **load):
        crowd(self.world, self.session.character, **load)
        self.manager.save_campaign(self.campaign_id)

    async def open_long_room_card(self):
        """Task 11's `asks_for: room` turn, said to a barman with a long name: the room card opens through the play."""
        self.world["npcs"].append({"id": "barman", "name": "Han Sahibi " + "Uzun Adlı Bilge Marek Efendi " * 6,
                                   "role": "Barmen", "location": self.world["location"], "current_hp": 10})
        self.manager.save_campaign(self.campaign_id)
        await self.say("bir oda tutmak istiyorum", konus="barman", intent=_TALK_TO_BARMAN, speech={"asks_for": "room"},
                       front={"kind": "speak_to", "person_id": "barman"})
        card = serializers.serialize_session_state(self.session).get("economic_offer")
        self.assertIsNotNone(card)
        self.assertEqual([line.get("label") for line in card["lines"]], ["Oda (bir gece)"])

    @staticmethod
    def truth_card_block(lines):
        """The narrator input's card: from its heading to the fixed rule line under it, the heading included."""
        start = lines.index("MOTOR GERÇEĞİ (salt okunur):")
        end = next(i for i in range(start, len(lines)) if lines[i] == _RULE)
        return "\n".join(lines[start:end]).strip("\n")

    # --- Step 1 of the plan ---------------------------------------------------------------------------------------
    async def test_wield_with_nothing_to_draw_tells_the_narrator(self):
        await self.say("kılıcımı çekiyorum", front={"kind": "wield", "item_id": "none", "thing_word": "kılıcımı"})
        self.assertEqual(self.bag(), {"Macera Çantası": 1}); self.assertIsNone(self.held())
        text = "\n".join(self.narrator_input())
        for needle in ("olmadı: istediğin silah çantanda yok; hiçbir şey çekilmedi (çantadaki silahlar: yok).",
                       "elin boş", "olmuş gibi anlatma"):
            self.assertIn(needle, text)
        self.assertNotIn("kılıcımı yok", text)                            # the model's word never enters the refusal

    async def test_wield_of_a_thing_that_is_no_weapon_changes_nothing(self):
        before = copy.deepcopy((self.world["inventory"], self.world.get("equipment")))
        await self.say("çantamı çekiyorum", front={"kind": "wield", "item_name": "Macera Çantası"})
        self.assertEqual((self.world["inventory"], self.world.get("equipment")), before)
        self.assertIn((None, "olmadı: istediğin silah çantanda yok; hiçbir şey çekilmedi (çantadaki silahlar: yok)."),
                      self.notes())

    async def test_wield_draws_the_greatsword(self):
        await self.use_package_c()                                        # scenario 05 setup, no fight
        await self.say("büyük kılıcımı çekiyorum", front={"kind": "wield", "item_name": "Greatsword"})
        self.assertEqual(self.held()["name"], "Greatsword")
        self.assertIn((None, "bu tur: Greatsword eline alındı"), self.notes())
        self.assertIn("elinde: Greatsword", "\n".join(self.narrator_input()))
        self.assertFalse(self.world.get("combat", {}).get("active"))
        await self.say("büyük kılıcımı çekiyorum", front={"kind": "wield", "item_name": "Greatsword"})
        self.assertIn((None, "bu tur: Greatsword zaten elinde"), self.notes())
        self.assertEqual(self.held()["name"], "Greatsword")

    async def test_the_weapons_named_in_a_refusal_are_the_bags_own(self):
        await self.use_package_c()
        await self.say("kılıcımı çekiyorum", front={"kind": "wield", "item_id": "none", "thing_word": "kılıcımı"})
        self.assertIsNone(self.held())
        self.assertIn((None, "olmadı: istediğin silah çantanda yok; hiçbir şey çekilmedi "
                             "(çantadaki silahlar: Greatsword, Ağır Tatar Yayı & 20 Ok)."), self.notes())

    async def test_undo_puts_the_drawn_weapon_back_and_a_save_keeps_it(self):
        await self.use_package_c()
        bag_before = copy.deepcopy(self.world["inventory"])
        await self.say("büyük kılıcımı çekiyorum", front={"kind": "wield", "item_name": "Greatsword"})
        self.assertEqual(self.held()["name"], "Greatsword")
        await self.undo()
        self.assertIsNone(self.held())
        self.assertEqual((self.world["inventory"], self.world["equipment"]),
                         (bag_before, {"main_hand": None, "off_hand": None}))
        await self.say("büyük kılıcımı çekiyorum", front={"kind": "wield", "item_name": "Greatsword"})
        await self.reload()                                               # read back from the save, as after a restart
        self.assertEqual(self.held()["name"], "Greatsword")
        self.assertEqual(self.bag(), _inventory_counts(bag_before))      # drawing moves nothing in or out of the bag

    async def test_refusals_reach_the_real_narrator_input_next_to_a_long_offer(self):
        # the real narrator input of a played turn, not narrator_view called alone: several refusals in one turn next to a
        # long active offer, over the 600-byte budget (J-014 #6 asked for this combined case in the real input)
        self.crowd(trails=6, jobs=4, items=30, long_names=True)          # the same load as crowded_world, on the played session
        await self.open_long_room_card()                                 # a room card with a long label is open
        real_begin = front_proposal.begin

        def begin_then_two_more_refusals(session, *args, **kwargs):
            out = real_begin(session, *args, **kwargs)                   # the turn's notes are reset here
            refusals.note(session, "which_enemy", names="Haydut mu, Okçu mu")   # two more refusals in the same turn,
            refusals.note(session, "parcel_not_here", item="İade takımı")      # through the one real note path
            return out
        with patch.object(front_proposal, "begin", side_effect=begin_then_two_more_refusals), \
                self.assertLogs(level="WARNING") as logged:
            await self.say("kılıcımı çekiyorum", front={"kind": "wield", "item_id": "none", "thing_word": "kılıcımı"})
        refusal_notes = [text for _, text in self.notes() if text.startswith("olmadı: ")]
        self.assertEqual(len(refusal_notes), 3)                          # which_enemy, parcel_not_here, nothing_to_draw
        card = self.truth_card_block(self.narrator_input())              # the "MOTOR GERÇEĞİ (salt okunur):" section
        lines = card.splitlines()
        self.assertLessEqual(len(card.encode("utf-8")), 600)
        self.assertTrue(lines[-1].startswith("(kısaltıldı: "), lines[-1])  # the budget was really exceeded
        self.assertTrue(any("para henüz el değiştirmedi" in line for line in lines))    # the active deal stays
        self.assertIn(refusal_notes[0], card)                            # the first refusal is the last to go: whole
        self.assertEqual([l for l in lines if l.startswith("izler:")], [])              # optional lines went first
        for text in refusal_notes[1:]:                                   # a later refusal is whole or named, never silent
            with self.subTest(note=text):
                self.assertTrue(text in card or "olmadı notu" in lines[-1])
        if any(text not in card for text in refusal_notes):
            self.assertTrue(any("olmadı notu" in entry for entry in logged.output))
        self.assertIn("olmuş gibi anlatma", "\n".join(self.narrator_input()))

    async def test_old_front_paths_are_unchanged_without_wield(self):
        before = copy.deepcopy(self.world)                               # rc3: Fighter with no sword
        await self.say("kılıcımı çekiyorum", front={"kind": "attempt"})
        self.assertEqual((self.world["inventory"], self.world.get("equipment")), (before["inventory"], before.get("equipment")))
        self.assertIn("elin boş", "\n".join(self.narrator_input()))

    def test_the_front_reading_lists_wield_after_consume(self):
        self.assertEqual(front_proposal.KINDS[front_proposal.KINDS.index("consume") + 1], "wield")
        self.assertIn("wield: oyuncu bir silahı eline alıyor/çekiyor; item_id çantadaki silah ya da none",
                      front_proposal.guidance(front_proposal.listing(self.session)))

    # --- the wired refusal paths (tasarım §3e) --------------------------------------------------------------------
    async def accept_19(self):
        await self.use_setup(_setup("19_quest_item_no_duplicate.json"))
        await self.say("olur, götürürüm")
        [thread] = [t for t in world_threads.view(self.world)["threads"] if t.get("status") == "accepted"]
        return thread

    def second_errand(self, first, item_noun, name, recipient=None):
        second = copy.deepcopy(first)
        second.update(thread_id=first["thread_id"] + ":second", quest_id=first["quest_id"] + "2", item_noun=item_noun,
                      recipient_npc_id=recipient or first.get("recipient_npc_id"))
        world_threads.view(self.world)["threads"].append(second)
        quest = copy.deepcopy(next(q for q in self.world["quests"] if q.get("quest_id") == first["quest_id"]))
        quest["quest_id"] = second["quest_id"]
        self.world["quests"].append(quest)
        self.world["inventory"].append({"item_id": "parcel:" + second["quest_id"], "name": name, "quantity": 1})
        self.manager.save_campaign(self.campaign_id)

    def refusal_paths(self):
        async def combat_refusal():
            scenario = load_scenario(SCENARIO_DIR / "06_combat_actions.json")
            results = await self.run_scenario(replace(scenario, steps=scenario.steps[:9]))   # step 9: Ready, no trigger
            self.assertEqual([r.status for r in results], ["pass"] * 9, results)
            self.session_id = self.last_session_id

        async def nothing_to_draw():
            await self.use_rc3_setup()
            await self.say("kılıcımı çekiyorum", front={"kind": "wield", "item_id": "none", "thing_word": "kılıcımı"})

        async def weapon_not_owned():
            scenario = json.loads((SCENARIO_DIR / "30_refusal_told.json").read_text(encoding="utf-8"))
            await self.use_setup(scenario["setup"])
            step = scenario["steps"][1]
            await self.say(step["say"], intent=step["script"]["intent"])

        async def parcel_not_here():
            thread = await self.accept_19()
            parcel = next(i for i in self.world["inventory"] if i["item_id"] == "parcel:" + thread["quest_id"])
            self.world["inventory"].remove(parcel)
            giver = next(n for n in self.world["npcs"] if n.get("id") == thread["owner_npc_id"])
            giver.setdefault("inventory", []).append(parcel)
            giver["location"] = thread["target_place_id"]
            self.manager.save_campaign(self.campaign_id)
            await self.say("İade takımını alıyorum", front={"kind": "take", "thing_word": "İade takımını"})

        async def which_parcel():
            thread = await self.accept_19()
            self.second_errand(thread, "iade takımı", "İade takımı")
            await self.say("takımını alıyorum", front={"kind": "take", "item_id": "none", "thing_word": "takımını"})

        async def which_item_to_give():
            thread = await self.accept_19()
            self.world["location"] = thread["target_place_id"]
            self.second_errand(thread, "mühürlü mektup", "Mühürlü mektup", recipient=thread["recipient_npc_id"])
            await self.say("Tuna, getirdim, buyur",
                           front={"kind": "hand_over", "person_id": thread["recipient_npc_id"], "item_id": "none"})

        # The last field is who tells the turn: the narrator model, the person's speech model, or the engine alone
        # (a fight's refusal and a punch for a weapon not owned are told in the engine's own words, with no model call).
        return [
            ("combat_refusal", combat_refusal, "olmadı: " + refusals.REFUSAL_TEXT["invalid_ready_trigger"], "engine"),
            ("nothing_to_draw", nothing_to_draw,
             "olmadı: istediğin silah çantanda yok; hiçbir şey çekilmedi (çantadaki silahlar: yok).", "narrator"),
            ("weapon_not_owned", weapon_not_owned, "olmadı: Kılıç yok; yumrukla vuruyorsun.", "engine"),
            ("parcel_not_here", parcel_not_here, "olmadı: İade takımı burada değil", "narrator"),
            ("which_parcel", which_parcel, "olmadı: hangi işin eşyasını kastettiğin belli değil", "narrator"),
            ("which_item_to_give", which_item_to_give, "olmadı: hangi eşyayı verdiğin belli değil", "speech"),
        ]

    async def test_every_refusal_path_reaches_the_narrator(self):
        # J-014 #6: the wired paths (tasarım §3e). Whoever tells the played turn hears its "olmadı:" note: the narrator's
        # input, or the person's speech input; a turn the engine tells alone calls no model at all, its own text says the
        # move did not happen and the note is on the turn. which_enemy and approach_short join this list in Task 16.
        for name, play, expected, teller in self.refusal_paths():
            with self.subTest(path=name):
                await play()
                if teller == "narrator":
                    self.assertIn(expected, "\n".join(self.narrator_input()))
                elif teller == "speech":
                    self.assertIsNotNone(self.last_speech_input, "no speech call this turn")
                    self.assertIn(expected, self.last_speech_input)
                else:
                    self.assertEqual((self.last_narrator_input, self.last_speech_input), (None, None))
                    self.assertIn(expected.removeprefix("olmadı: "), self.last_narration)
                    self.assertIn(expected, [note for _, note in self.notes()])


if __name__ == "__main__":
    import unittest
    unittest.main()
