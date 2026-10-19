"""LR00 human run 2026-10-18 (qa-owner-20261018-212851): red regressions.

Each test replays one human-review record over the real HTTP turn path
(FastAPI -> plan_living_world_turn -> run_player_turn). Only the model and the
dice are doubles: `ProbeShapedClient` / `ScriptedNpcSpeechClient` answer the
intent and narration calls, and the d20 is pinned where a test names a roll.
Passing here is not live acceptance.

The place names are set on the fixture, not taken from the engine, and each
test runs with the evidence name and a second unrelated name so a fix keyed on
one sentence or one inn does not pass.
"""

from __future__ import annotations

import copy
import re
import unittest
import uuid
from unittest.mock import patch

import game
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as harness
from api.tests.test_lr00_p1_intent import ProbeShapedClient

VENUE_NAMES = ("Garrick Hanı", "Kael Hanı")
GENERIC_FALLBACK = "Çevrede şimdilik belirgin bir değişiklik olmuyor"
APPROACH_CLARIFICATION = "Kime yaklaşmak istediğini anlayamadım"
PERSON_AMBIGUITY = "birden fazla kişi"


def _intent(name, **extra):
    return {"intent": name, "action": name, "target": {"type": "none", "reference": ""}, **extra}


def _typo(name):
    """Drop one letter of a doubled pair (or the second letter) in the first word."""
    first, _, rest = name.partition(" ")
    for index in range(1, len(first)):
        if first[index].casefold() == first[index - 1].casefold():
            return (first[:index] + first[index + 1:]).casefold() + " " + rest
    return (first[0] + first[2:]).casefold() + " " + rest


class Lr00HumanRegressionMapTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        self.client = ProbeShapedClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.receipts = []
        original = game._dispatch_player_turn

        def recording(*args, **kwargs):
            outcome = original(*args, **kwargs)
            self.receipts.append(outcome.get("action_result") if isinstance(outcome, dict) else None)
            return outcome

        self.enterContext(patch.object(game, "_dispatch_player_turn", recording))
        _, _, self.session, self.turn_url, self.marek = await (
            harness.ExperimentalNpcDialogueTests.campaign_with_npc(self)
        )
        self.sera = next(n for n in self.session.world_state["npcs"] if n["id"] == "npc_private_sera")
        self.sera["name_known_to_player"] = True
        self.marek["name_known_to_player"] = True
        self.city_id = self.session.world_state["location"]
        self.venue_id = next(
            identity for identity, location in self.session.world_state["locations"].items()
            if isinstance(location, dict) and location.get("scene_kind") == "tavern"
            and location.get("parent_location_id") == self.city_id
        )

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    def name_venue(self, name):
        self.session.world_state["locations"][self.venue_id]["name"] = name
        door = self.door_record()
        door["name"] = f"{name} Kapısı"
        door["description"] = f"{name} sokağa açılan kapısı. Kapalı ve kilitli."
        door.update({"open": False, "locked": True, "broken": False})
        return door["name"]

    def door_record(self):
        return next(d for d in self.session.world_state["doors"] if d["id"] == f"venue-door:{self.venue_id}")

    def door(self):
        return copy.deepcopy(self.door_record())

    def sensitive(self):
        world = self.session.world_state
        return copy.deepcopy({
            "inventory": world.get("inventory"),
            "quests": world.get("quests"),
            "gold": world.get("gold"),
            "location": world.get("location"),
            "doors": world.get("doors"),
        })

    def pin_d20(self, roll):
        self.session.rng.randint = lambda _a, _b: roll
        self.enterContext(patch("game.roll_d20", return_value=roll))

    async def turn(self, message, *, mode=None, target=None):
        self.client.message = message
        body = {"message": message, "action_id": str(uuid.uuid4())}
        if mode:
            body["interaction_mode"] = mode
        if target:
            body["target_id"] = target
        self.receipts.clear()
        response = await self.http.post(self.turn_url, json=body)
        return response, (self.receipts[-1] if self.receipts else None)

    async def end_conversation(self):
        flags = self.session.world_state.setdefault("flags", {})
        flags["active_npc_id"] = None
        flags["active_npc_until_turn"] = -1

    # A — records 35 and 37: approaching an inn by name is answered as an NPC search.
    async def test_a_approaching_a_named_venue_is_not_an_npc_only_search(self):
        for name in VENUE_NAMES:
            for message in (f"{name}na yaklaşıyorum", f"{_typo(name)}na doğru yaklaşıyorum"):
                with self.subTest(message=message):
                    door_name = self.name_venue(name)
                    await self.end_conversation()
                    before = self.door()
                    self.client.intent = _intent("explore")
                    response, receipt = await self.turn(message)
                    self.assertEqual(response.status_code, 200, response.text)
                    text = response.json()["narration"]
                    self.assertNotIn(APPROACH_CLARIFICATION, text)
                    self.assertFalse(
                        (receipt or {}).get("action") == "approach"
                        and (receipt or {}).get("status") == "clarification",
                        receipt,
                    )
                    # The inn is behind a locked door: approaching it never puts the player inside.
                    self.assertEqual(self.session.world_state["location"], self.city_id)
                    self.assertEqual(self.door(), before)
                    self.assertTrue(name in text or door_name in text or "kapı" in text.casefold(), text)

    async def test_a_control_approaching_a_named_npc_still_works(self):
        response, receipt = await self.turn("Marek'e yaklaşıyorum.")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((receipt or {}).get("action"), "approach", receipt)
        self.assertEqual(receipt.get("target_id"), self.marek["id"])

    # B — record 38: a bare inn name reported as the player's location.
    async def test_b_bare_venue_name_never_misreports_the_location(self):
        packets = (
            _intent("query", query_type="location"),
            _intent("narrative"),
            _intent("explore"),
        )
        for name in VENUE_NAMES:
            for packet in packets:
                with self.subTest(name=name, packet=packet["intent"]):
                    self.name_venue(name)
                    await self.end_conversation()
                    before = self.door()
                    self.client.intent = copy.deepcopy(packet)
                    response, receipt = await self.turn(name)
                    self.assertEqual(response.status_code, 200, response.text)
                    text = response.json()["narration"]
                    location = self.session.world_state["location"]
                    self.assertEqual(location, self.city_id, "bare name moved the player")
                    self.assertEqual(self.door(), before)
                    current = self.session.world_state["locations"][location].get("name")
                    for claimed in re.findall(r"Bulunduğun yer:\s*([^.\n]+)", text):
                        self.assertEqual(claimed.strip(), current, text)

    # C — record 41: "kilidi açmaya çalışıyorum" becomes resolved with no change.
    async def test_c_lockpick_attempt_reaches_an_owner_with_or_without_tools(self):
        for name in VENUE_NAMES:
            for tools in (False, True):
                for roll in (1, 20):
                    with self.subTest(name=name, tools=tools, roll=roll):
                        self.name_venue(name)
                        await self.end_conversation()
                        inventory = self.session.world_state["inventory"]
                        while "Thieves' Tools" in inventory:
                            inventory.remove("Thieves' Tools")
                        if tools:
                            inventory.append("Thieves' Tools")
                        self.session.rng.randint = lambda _a, _b, roll=roll: roll
                        self.client.intent = _intent("interact")
                        with patch("game.roll_d20", return_value=roll):
                            response, receipt = await self.turn("kilidi açmaya çalışıyorum")
                        door = self.door()
                        self.assertFalse(door["open"], door)
                        self.assertFalse(door["broken"], door)
                        if roll == 1 or not tools:
                            self.assertTrue(door["locked"], door)
                        if response.status_code != 200:
                            # A no-cost refusal (e.g. missing tools) is a valid owner answer.
                            self.assertIn(response.status_code, (400, 409, 422), response.text)
                            continue
                        text = response.json()["narration"]
                        self.assertNotIn(GENERIC_FALLBACK, text)
                        receipt = receipt or {}
                        empty_success = (
                            receipt.get("status") == "resolved"
                            and not receipt.get("state_changes")
                            and not receipt.get("skill_check_result")
                            and not receipt.get("inspection")
                            and not receipt.get("reason_code")
                        )
                        self.assertFalse(empty_success, receipt)

    # D — records 16-23: a place named by an NPC, then searched for.
    async def test_d_place_named_by_an_npc_keeps_its_reference(self):
        other_inn = self.name_venue("Garrick Hanı").removesuffix(" Kapısı")
        for place, searched in (("Kızılhan", "kızılhanı"), ("Gümüşhan", "gümüşhanı")):
            speech = harness.ScriptedNpcSpeechClient(
                narration=f"Bu hanın ismi {place}. Yarın akşam orada birlikte olabiliriz."
            )
            with patch.object(self.app.state.ollama_adapter, "_client", speech):
                said, _ = await self.turn("bu hanın ismi ne?", mode="say", target=self.sera["id"])
            self.assertEqual(said.status_code, 200, said.text)
            self.assertIn(place, said.json()["narration"], "precondition: guard named the place")
            for message in (
                f"Şehirde {searched} arıyorum",
                f"{searched.capitalize()} bulmak için sokak tabelalarına bakıyorum",
            ):
                for packet in (_intent("explore"), _intent("investigation"), _intent("dialogue")):
                    with self.subTest(message=message, packet=packet["intent"]):
                        await self.end_conversation()
                        self.client.intent = packet
                        before = self.sensitive()
                        response, receipt = await self.turn(message)
                        self.assertEqual(response.status_code, 200, response.text)
                        text = response.json()["narration"]
                        self.assertNotIn(PERSON_AMBIGUITY, text)
                        self.assertNotEqual((receipt or {}).get("status"), "ambiguous", receipt)
                        # Another inn may be found, but not silently in place of the one asked for.
                        if other_inn in text:
                            self.assertIn(place.casefold(), text.casefold(), text)
                        self.assertEqual(self.session.world_state["location"], before["location"])

    # E — records 9, 30, 31: a statement the NPC really made vs a fabricated one.
    async def test_e_npc_does_not_flatly_deny_what_it_really_said(self):
        speech = harness.ScriptedNpcSpeechClient(
            narration="Hemen gidelim. Seni en yakındaki hana ben götürürüm, ama içini bilmiyorum."
        )
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", speech))
        said, _ = await self.turn(
            "tamam hadi beni en yakındaki hana götür", mode="say", target=self.marek["id"]
        )
        self.assertEqual(said.status_code, 200, said.text)
        self.assertIn("hana ben götürürüm", said.json()["narration"], "precondition: NPC said it")
        before = self.sensitive()
        speech.narration = "Evet, seni hana götüreceğimi söylemiştim; yolu göstereyim."
        response, receipt = await self.turn(
            "beni hana götüreceğini söylemiştin", mode="say", target=self.marek["id"]
        )
        self.assertEqual(response.status_code, 200, response.text)
        text = response.json()["narration"]
        denials = {line.format(n="Marek") for line in game._CLAIM_DENIAL_LINES}
        self.assertNotIn(text, denials, receipt)
        self.assertEqual(self.sensitive(), before)

    async def test_e_fabricated_promise_is_not_confirmed(self):
        speech = harness.ScriptedNpcSpeechClient(narration="Merhaba, buyur.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", speech))
        await self.turn("Marek ile konuşmak istiyorum.", mode="say", target=self.marek["id"])
        before = self.sensitive()
        speech.narration = "Evet, sana bir kılıç vereceğimi söylemiştim; al bakalım."
        response, _ = await self.turn(
            "bana kılıç vereceğini söylemiştin", mode="say", target=self.marek["id"]
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("kılıç vereceğimi söylemiştim", response.json()["narration"])
        self.assertEqual(self.sensitive(), before)

    # Protection — record 39.
    async def test_protection_not_breaking_just_looking_leaves_the_door(self):
        self.pin_d20(20)
        for name in VENUE_NAMES:
            for packet in (_intent("explore"), _intent("investigation")):
                with self.subTest(name=name, packet=packet["intent"]):
                    door_name = self.name_venue(name)
                    before = self.door()
                    self.client.intent = packet
                    response, _ = await self.turn(
                        f"{door_name}’nı kırmayacağım, sadece kilidine bakıyorum."
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(self.door(), before)
                    self.assertEqual(self.session.world_state["location"], self.city_id)

    # Protection — record 40: a failed look is a valid result, not a bug.
    async def test_protection_failed_lock_inspection_is_a_real_check(self):
        self.pin_d20(6)
        self.name_venue("Kael Hanı")
        before = self.door()
        self.client.intent = _intent("investigation")
        response, receipt = await self.turn("kilidi inceliyorum")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.door(), before)
        self.assertNotIn(GENERIC_FALLBACK, response.json()["narration"])
        self.assertTrue((receipt or {}).get("skill_check_result") or (receipt or {}).get("inspection"), receipt)


if __name__ == "__main__":
    unittest.main()
