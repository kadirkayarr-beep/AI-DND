"""Owner P6 human test (18 Oct 2026, 033edc5) pinned as regressions.

The fixture is the owner's own saved campaign after turn 41 (turns 35-41 changed
no world fact, so it is also the state those turns ran against). Every test
here starts from that real state and replays the owner's own words, or a plain
consequence of them. The model is mocked: a grounding or narration call gets an
unusable answer, so these tests prove the deterministic path alone.

The rule under test: understand the action once, bind it to a real target, hand
it to the owner that can resolve it, report only what was really done.
"""

from __future__ import annotations

import copy
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import game
import npc_statements
from api.tests import test_campaign_api
from api.tests.test_campaign_api import create_city_with_locked_tavern
from api.tests.test_lr00_p1_intent import ProbeShapedClient

FIXTURE = Path(__file__).parent / "fixtures" / "lr00_p6_human_world.json"
CITY = "fr:city:neverwinter"
GARRICK = "location_001"
GARRICK_DOOR = "venue-door:location_001"


def human_world():
    return copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8"))["world_state"])


class HumanP6Regressions(unittest.IsolatedAsyncioTestCase):
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
        _, self.session_id, self.session, self.turn_url, _, _ = await create_city_with_locked_tavern(self)
        world = self.session.world_state
        campaign_id = world.get("campaign_id")
        world.clear()
        world.update(human_world())
        world["campaign_id"] = campaign_id  # the owner's state, under this test campaign

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    @property
    def world(self):
        return self.manager.get(self.session_id).game_session.world_state

    def door(self, door_id=GARRICK_DOOR):
        return copy.deepcopy(next(d for d in self.world["doors"] if d["id"] == door_id))

    async def turn(self, message, *, mode=None, target=None, action_id=None):
        self.client.message = message
        body = {"message": message, "action_id": action_id or str(uuid.uuid4())}
        if mode:
            body["interaction_mode"] = mode
        if target:
            body["target_id"] = target
        self.receipts.clear()
        response = await self.http.post(self.turn_url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["narration"], (self.receipts[-1] if self.receipts else None)

    # --- records 35 and 37: approaching a building is not a person search ----
    async def test_approaching_the_inn_by_name_reaches_its_door(self):
        for message in ("garick hanına doğru yaklaşıyorum", "Garrick Hanına yaklaşıyorum"):
            with self.subTest(message=message):
                door_before = self.door()
                text, receipt = await self.turn(message)
                self.assertNotIn("Kime yaklaşmak", text)
                self.assertIn("Garrick", text)
                self.assertIn("kilitli", text.casefold())
                self.assertEqual(self.world["location"], CITY)
                self.assertEqual(self.door(), door_before)
                self.assertEqual(receipt.get("status"), "completed", receipt)
                self.assertIn(receipt.get("target_id"), {GARRICK, GARRICK_DOOR}, receipt)

    # --- record 38: a bare place name must not claim the player is there -----
    async def test_bare_place_name_does_not_say_you_are_inside(self):
        text, receipt = await self.turn("Garrick Hanı")
        self.assertNotIn("Bulunduğun yer: Garrick", text)
        self.assertEqual(self.world["location"], CITY)
        self.assertIn("Garrick", text)
        self.assertNotEqual(receipt.get("status"), "resolved", receipt)

    # --- record 39 stays safe ------------------------------------------------
    async def test_declined_force_with_a_look_at_the_lock_changes_nothing(self):
        before = self.door()
        text, _ = await self.turn("Garrick Hanı Kapısı’nı kırmayacağım, sadece kilidine bakıyorum.")
        self.assertEqual(self.door(), before)
        self.assertIn("kilit", text.casefold())

    # --- record 40: a repeated look does not roll again ------------------------
    async def test_repeated_lock_inspection_does_not_reroll(self):
        await self.turn("Garrick Hanına yaklaşıyorum")
        _, first = await self.turn("kilidi inceliyorum")
        _, second = await self.turn("kilidi inceliyorum")
        self.assertEqual(first.get("target_id"), GARRICK_DOOR, first)
        rolls_first = first.get("dice")
        self.assertIsNone(second.get("dice"), second)
        self.assertTrue(second.get("repeated_observation"), second)
        if rolls_first is not None:
            self.assertIn(first.get("skill"), {"Investigation", "Perception"})

    # --- record 41: an attempt is never a silent 'resolved' ------------------
    async def test_lockpicking_without_tools_is_a_concrete_obstacle(self):
        await self.turn("Garrick Hanına yaklaşıyorum")
        before = self.door()
        text, receipt = await self.turn("kilidi açmaya çalışıyorum")
        self.assertNotIn("belirgin bir değişiklik olmuyor", text)
        self.assertEqual(receipt.get("status"), "blocked", receipt)
        self.assertEqual(receipt.get("reason"), "tools_required", receipt)
        self.assertEqual(receipt.get("target_id"), GARRICK_DOOR, receipt)
        self.assertEqual(self.door(), before)

    async def test_lockpicking_with_tools_rolls_exactly_once(self):
        self.world["inventory"].append({"item_id": "item_test_tools", "name": "Thieves' Tools"})
        await self.turn("Garrick Hanına yaklaşıyorum")
        rolls = []
        original = game.roll_d20

        def counting():
            value = original()
            rolls.append(value)
            return value

        with patch.object(game, "roll_d20", counting):
            _, receipt = await self.turn("kilidi açmaya çalışıyorum")
        self.assertEqual(receipt.get("skill"), "Sleight of Hand", receipt)
        self.assertIn(len(rolls), {1, 2})  # 2 only with advantage/disadvantage
        self.assertEqual(receipt.get("target_id"), GARRICK_DOOR)
        door = self.door()
        self.assertEqual(door["locked"], not receipt.get("success"))
        self.assertFalse(door["broken"])

    async def test_same_action_id_replays_without_a_second_roll(self):
        self.world["inventory"].append({"item_id": "item_test_tools", "name": "Thieves' Tools"})
        await self.turn("Garrick Hanına yaklaşıyorum")
        action_id = str(uuid.uuid4())
        first, _ = await self.turn("kilidi açmaya çalışıyorum", action_id=action_id)
        state = copy.deepcopy(self.world)
        again, _ = await self.turn("kilidi açmaya çalışıyorum", action_id=action_id)
        self.assertEqual(first, again)
        self.assertEqual(self.world, state)

    # --- records 16-24: the guard's Kızılhan is a followable reference --------
    async def test_guard_named_inn_is_an_attributed_reference_not_a_fact(self):
        refs = npc_statements.place_references(self.world)
        kizil = [ref for ref in refs if ref.get("name") and "kızılhan" in ref["name"].casefold()]
        self.assertEqual(len(kizil), 1, refs)
        self.assertEqual(kizil[0]["said_by"], "npc_002")
        self.assertEqual(kizil[0]["status"], "rumor")
        self.assertIsNone(kizil[0].get("location_id"))
        self.assertFalse(any(
            "kızılhan" in str(loc.get("name", "")).casefold()
            for loc in self.world["locations"].values() if isinstance(loc, dict)
        ))

    async def test_searching_for_the_named_inn_follows_the_reference(self):
        text, receipt = await self.turn("Şehirde kızılhanı arıyorum")
        self.assertNotIn("birden fazla kişi", text)
        self.assertIn("Kızılhan", text)
        place_id = receipt.get("target_id")
        place = self.world["locations"].get(place_id)
        self.assertIsInstance(place, dict, receipt)
        self.assertNotEqual(place_id, GARRICK)
        self.assertEqual(place.get("provenance", {}).get("said_by"), "npc_002")
        # The guard's 'open' is her claim; the door has its own saved state.
        self.assertIn("claims", place.get("provenance", {}))
        door = next(d for d in self.world["doors"] if d["id"] == f"venue-door:{place_id}")
        self.assertIn(door["open"], {True, False})
        # Following it again reuses the same place (whichever owner answers the move).
        count = len(self.world["locations"])
        again_text, _ = await self.turn("Kızılhan'a gidiyorum")
        self.assertIn("Kızılhan", again_text)
        self.assertEqual(len(self.world["locations"]), count)
        self.assertIn(self.world["location"], {CITY, place_id})
        if door["locked"]:
            self.assertEqual(self.world["location"], CITY)
        ref = next(r for r in npc_statements.place_references(self.world)
                   if r.get("name") and "kızılhan" in r["name"].casefold())
        self.assertEqual(ref.get("location_id"), place_id)
        # Standing at the Kızılhan door, "its door" is that door, not the street's first door.
        knock_text, _ = await self.turn("kapısını çalıyorum")
        self.assertIn("Kızılhan", knock_text)
        self.assertNotIn("Garrick", knock_text)

    def record_npc_place_statement(self, npc_id, name, quote):
        npc = {
            "id": npc_id,
            "name": npc_id.removeprefix("npc_test_").title(),
            "name_known_to_player": True,
            "role": "guide",
            "location": CITY,
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        self.world["npcs"].append(npc)
        statement = npc_statements.record(
            self.world,
            npc,
            "Şehirde başka hangi yere gidebilirim?",
            f'{npc["name"]}, “{quote}” diye yanıtlıyor.',
            turn=42,
        )
        self.assertIsNotNone(statement)
        self.assertEqual(statement["text"], quote)
        return npc, statement

    async def test_marek_said_named_camhouse_can_be_reached_by_natural_go_phrase(self):
        name = "Mavi Fener Camhanesi"
        _, statement = self.record_npc_place_statement(
            "npc_test_marek",
            name,
            "Mavi Fener Camhanesi doğu kapısının yanındadır.",
        )
        self.assertEqual(statement["player"], "Şehirde başka hangi yere gidebilirim?")

        action_id = str(uuid.uuid4())
        message = "Marek'in söylediği Mavi Fener Camhanesi'ne gidiyorum"
        text, receipt = await self.turn(message, action_id=action_id)

        self.assertEqual(receipt.get("action"), "grounded_action", (text, receipt))
        place_id = receipt.get("target_id")
        place = self.world["locations"].get(place_id)
        self.assertEqual(receipt.get("status"), "completed", (text, receipt))
        self.assertIsInstance(place, dict, (text, receipt))
        self.assertEqual(place.get("name"), name, (text, receipt, place))
        self.assertEqual(
            place.get("provenance", {}).get("said_by"),
            "npc_test_marek",
            (text, receipt, place),
        )
        locations_after_first_visit = copy.deepcopy(self.world["locations"])
        replay_text, replay_receipt = await self.turn(message, action_id=action_id)
        self.assertEqual(replay_text, text)
        self.assertEqual(self.world["locations"], locations_after_first_visit)
        _, repeat_receipt = await self.turn(message, action_id=str(uuid.uuid4()))
        # The fixture door is locked, so the second approach can be blocked at
        # the door; it must still reuse the already materialized place.
        self.assertIn(repeat_receipt.get("status"), {"completed", "blocked"}, repeat_receipt)
        self.assertEqual(
            sum(location.get("name") == name for location in self.world["locations"].values()),
            1,
            self.world["locations"],
        )
        self.assertEqual(self.world["locations"], locations_after_first_visit)

    async def test_unspoken_player_claim_does_not_create_a_named_npc_place(self):
        before_locations = copy.deepcopy(self.world["locations"])
        text, receipt = await self.turn(
            "Marek'in söylediği Mavi Fener Camhanesi'ne gidiyorum"
        )
        self.assertEqual(self.world["locations"], before_locations)
        self.assertFalse(any(
            ref.get("name") == "Mavi Fener Camhanesi"
            for ref in npc_statements.place_references(self.world, settlement_id=CITY)
        ))

    async def test_negative_travel_to_a_spoken_place_does_not_materialize_or_move(self):
        self.record_npc_place_statement(
            "npc_test_marek",
            "Mavi Fener Camhanesi",
            "Mavi Fener Camhanesi doğu kapısının yanındadır.",
        )
        before_location = self.world["location"]
        before_locations = copy.deepcopy(self.world["locations"])
        text, receipt = await self.turn("Mavi Fener Camhanesi'ne gitmiyorum")
        self.assertNotEqual(receipt.get("status"), "completed", (text, receipt))
        self.assertEqual(self.world["location"], before_location)
        self.assertEqual(self.world["locations"], before_locations)

    async def test_two_spoken_camhouse_names_materialize_as_distinct_city_places(self):
        names = ("Mavi Fener Camhanesi", "Kızıl Lale Camhanesi")
        speakers = ("npc_test_marek", "npc_test_lale")
        for speaker, name in zip(speakers, names):
            _, statement = self.record_npc_place_statement(
                speaker,
                name,
                f"{name} şehirde bilinen bir yerdir.",
            )
            self.assertTrue(statement["text"].startswith(name))

        refs = npc_statements.place_references(self.world, settlement_id=CITY)
        named_refs = [ref for ref in refs if ref.get("name") in names]
        self.assertEqual(
            {ref.get("name") for ref in named_refs},
            set(names),
            {"npc_statements": refs},
        )
        self.assertEqual(
            {ref.get("said_by") for ref in named_refs},
            set(speakers),
            {"npc_statements": refs},
        )
        self.assertEqual(
            len({ref.get("id") for ref in named_refs}),
            2,
            {"npc_statements": named_refs},
        )

        resolved_ids = []
        for name in names:
            text, receipt = await self.turn(f"{name}'ne gidiyorum")
            place_id = receipt.get("target_id")
            place = self.world["locations"].get(place_id)
            self.assertEqual(receipt.get("status"), "completed", (text, receipt))
            self.assertIsInstance(place, dict, (text, receipt))
            self.assertEqual(place.get("name"), name, (text, receipt, place))
            self.assertEqual(place.get("parent_location_id"), CITY, place)
            resolved_ids.append(place_id)

        self.assertEqual(len(set(resolved_ids)), 2, resolved_ids)
        refs = npc_statements.place_references(self.world, settlement_id=CITY)
        self.assertEqual(
            {ref.get("name") for ref in refs if ref.get("name") in names},
            set(names),
            refs,
        )
        self.assertEqual(
            {ref.get("said_by") for ref in named_refs},
            set(speakers),
            refs,
        )

    async def test_two_word_library_names_keep_distinct_place_identities(self):
        names = ("Mavi Kütüphanesi", "Kızıl Kütüphanesi")
        speakers = ("npc_test_marek", "npc_test_lale")
        for speaker, name in zip(speakers, names):
            self.record_npc_place_statement(
                speaker,
                name,
                f"{name} şehrin eski bir yapısıdır.",
            )

        resolved_ids = []
        for name in names:
            text, receipt = await self.turn(f"{name}'ne gidiyorum")
            place = self.world["locations"].get(receipt.get("target_id"))
            self.assertEqual(receipt.get("status"), "completed", (text, receipt))
            self.assertIsInstance(place, dict, (text, receipt))
            self.assertEqual(place.get("name"), name, (text, receipt, place))
            resolved_ids.append(place["id"])

        self.assertNotEqual(
            resolved_ids[0],
            resolved_ids[1],
            {
                "ids": resolved_ids,
                "refs": npc_statements.place_references(self.world, settlement_id=CITY),
                "locations": self.world["locations"],
            },
        )
        refs = npc_statements.place_references(self.world, settlement_id=CITY)
        for name, speaker, location_id in zip(names, speakers, resolved_ids):
            ref = next((r for r in refs if r.get("name") == name), None)
            self.assertIsNotNone(ref, refs)
            self.assertEqual(ref.get("said_by"), speaker, ref)
            self.assertEqual(ref.get("location_id"), location_id, ref)
        self.assertEqual(
            sum(location.get("name") in names for location in self.world["locations"].values()),
            2,
            self.world["locations"],
        )

    def test_two_word_observatory_name_is_preserved_as_a_place_reference(self):
        _, statement = self.record_npc_place_statement(
            "npc_test_marek",
            "Ayışığı Rasathanesi",
            "Ayışığı Rasathanesi kuzey yamacındadır.",
        )
        self.assertEqual(statement["text"], "Ayışığı Rasathanesi kuzey yamacındadır.")
        refs = npc_statements.place_references(self.world, settlement_id=CITY)
        self.assertEqual(
            [ref.get("name") for ref in refs if ref.get("said_by") == "npc_test_marek"],
            ["Ayışığı Rasathanesi"],
            refs,
        )

    def test_four_word_place_reference_is_complete_without_a_suffix_duplicate(self):
        self.record_npc_place_statement(
            "npc_test_marek",
            "Eski Mavi Fener Camhanesi",
            "Eski Mavi Fener Camhanesi doğu kapısının yanındadır.",
        )
        refs = npc_statements.place_references(self.world, settlement_id=CITY)
        self.assertEqual(
            [ref.get("name") for ref in refs if ref.get("said_by") == "npc_test_marek"],
            ["Eski Mavi Fener Camhanesi"],
            refs,
        )

    def test_denied_place_and_reported_person_are_not_place_references(self):
        for speaker, quote in (
            ("npc_test_marek", "Mavi Fener Camhanesi diye bir yer yok."),
            ("npc_test_lale", "Kral Aras Demirpençe öldü."),
            ("npc_test_tan", "Mavi Kütüphanesi diye bir yer yok."),
        ):
            self.record_npc_place_statement(speaker, "Tanık", quote)
        refs = npc_statements.place_references(self.world, settlement_id=CITY)
        self.assertFalse(
            any(
                ref.get("said_by") in {"npc_test_marek", "npc_test_lale", "npc_test_tan"}
                for ref in refs
            ),
            refs,
        )

    def test_named_place_reference_distinguishes_rumor_from_known_location(self):
        self.record_npc_place_statement(
            "npc_test_marek",
            "Garrick Hanı",
            "Garrick Hanı şehrin merkezindedir.",
        )
        self.record_npc_place_statement(
            "npc_test_lale",
            "Ayışığı Rasathanesi",
            "Ayışığı Rasathanesi kuzey yamacındadır.",
        )
        refs = npc_statements.place_references(self.world, settlement_id=CITY)
        known = next(ref for ref in refs if ref.get("name") == "Garrick Hanı")
        rumor = next(ref for ref in refs if ref.get("name") == "Ayışığı Rasathanesi")
        self.assertEqual((known.get("status"), known.get("location_id")), ("resolved", GARRICK))
        self.assertEqual((rumor.get("status"), rumor.get("location_id")), ("rumor", None))

    async def test_reported_npc_first_person_travel_is_not_the_players_move(self):
        self.record_npc_place_statement(
            "npc_test_marek",
            "Mavi Fener Camhanesi",
            "Mavi Fener Camhanesi şehirde bilinen bir yerdir.",
        )
        before_location = self.world["location"]
        before_locations = copy.deepcopy(self.world["locations"])
        _, receipt = await self.turn("Marek Mavi Fener Camhanesi’ne gidiyorum dedi")
        self.assertEqual(receipt.get("status"), "no_effect", receipt)
        self.assertEqual(self.world["location"], before_location)
        self.assertEqual(self.world["locations"], before_locations)

    async def test_another_inn_is_not_garrick_again(self):
        text, receipt = await self.turn("Açık olan başka han varmı diye şehirde geziyorum")
        self.assertNotEqual(receipt.get("target_id"), GARRICK, (text, receipt))
        self.assertNotEqual(text, "Yakınlarda Garrick Hanı adlı küçük bir han buluyorsun. Sokağa açılan kapısı kapalı ve kilitli.")

    async def test_wandering_and_reading_signs_is_not_a_lore_wall(self):
        before = len(self.world["locations"]) + len(self.world.get("features", []))
        text, receipt = await self.turn(
            "Şehirde geziniyorum farklı sokakları geziyorum. tabelalara dikkat ediyorum."
        )
        self.assertNotIn("hiçbir söz sağlam görünmüyor", text)
        self.assertEqual(receipt.get("action"), "grounded_action", receipt)
        after = len(self.world["locations"]) + len(self.world.get("features", []))
        self.assertGreaterEqual(after, before)
        self.assertGreater(len(text), 40)

    # --- records 9, 30, 31: real promises are kept, invented ones refused ----
    def test_npc_agreement_to_escort_is_recorded_and_a_false_claim_is_not(self):
        world = self.world
        quarion = next(n for n in world["npcs"] if n["id"] == "npc_001")
        npc_statements.record(
            world, quarion,
            "tamam hadi beni en yakındaki hana götür",
            "Quarion, “Hemen gidelim. Ancak unutma, ben sadece yol göstericiyim. Hanın içini bilmiyorum.”",
            turn=9,
        )
        real = npc_statements.claim_support(world, quarion, "beni hana götüreceğini söylemiştin")
        self.assertEqual(real["status"], "supported", real)
        self.assertIn("gidelim", real["quote"])
        fake = npc_statements.claim_support(world, quarion, "bana kılıç vereceğini söylemiştin")
        self.assertEqual(fake["status"], "unsupported", fake)

    async def test_false_sword_claim_changes_nothing(self):
        inventory = copy.deepcopy(self.world["inventory"])
        text, _ = await self.turn("Quarion, bana kılıç vereceğini söylemiştin")
        self.assertNotIn("Evet, bunu söylemiştim", text)
        self.assertEqual(self.world["inventory"], inventory)

    # --- compound, negation, condition ----------------------------------------
    async def test_go_and_knock_runs_both_steps_in_order(self):
        before = self.door()
        text, receipt = await self.turn("Garrick Hanı'na gidip kapısını çalıyorum")
        steps = receipt.get("steps") or []
        self.assertEqual([s.get("verb") for s in steps], ["go", "knock"], receipt)
        self.assertTrue(all(s.get("status") == "completed" for s in steps), steps)
        self.assertEqual(self.door(), before)
        self.assertEqual(self.world["location"], CITY)

    async def test_blocked_first_step_stops_the_dependent_step(self):
        text, receipt = await self.turn("Hana girip içerideki barmene selam veriyorum")
        steps = receipt.get("steps") or []
        self.assertEqual(steps[0].get("status"), "blocked", receipt)
        self.assertTrue(all(s.get("status") == "not_attempted" for s in steps[1:]), steps)
        self.assertEqual(self.world["location"], CITY)
        self.assertNotIn("selamın", text.casefold())

    async def test_conditional_entry_does_not_enter(self):
        await self.turn("Garrick Hanına yaklaşıyorum")
        _, receipt = await self.turn("Kilit açılırsa içeri bakarım")
        self.assertEqual(self.world["location"], CITY)
        self.assertNotEqual(receipt.get("status"), "completed", receipt)

    async def test_knocking_without_forcing_only_knocks(self):
        # A single knock stays with the existing knock owner; what matters is
        # that it knocks and that "zorlamadan" never turns into a forcing roll.
        await self.turn("Garrick Hanına yaklaşıyorum")
        before = self.door()
        text, receipt = await self.turn("Kapıyı zorlamadan tokmağı iki kez vuruyorum")
        self.assertEqual(self.door(), before)
        self.assertIsNone(receipt.get("skill"), receipt)
        self.assertRegex(text.casefold(), r"vur|tıklat|tokma")
        self.assertNotIn("belirgin bir değişiklik olmuyor", text)


    # --- from the first blind live run (scripts now seen; kept as regressions) --
    async def test_the_branch_that_matches_the_door_runs(self):
        await self.turn("Garrick Hanına yaklaşıyorum")
        before = self.door()
        text, receipt = await self.turn("Eğer açıksa içeri giriyorum, kapalıysa birkaç kez tıklatırım.")
        statuses = [(s.get("verb"), s.get("status")) for s in receipt.get("steps", [])]
        self.assertEqual(statuses, [("enter", "condition_unmet"), ("knock", "completed")], receipt)
        self.assertEqual(self.world["location"], CITY)
        self.assertEqual(self.door(), before)

    async def test_a_shop_the_player_points_at_is_made_here_with_a_door(self):
        count = len(self.world["locations"])
        text, receipt = await self.turn("Şu kapalı dükkânın kapısına yaklaşıp kulak veriyorum, ses yoksa kilide bakıyorum.")
        self.assertEqual(len(self.world["locations"]), count + 1)
        shop_id = receipt["steps"][0]["target_id"]
        self.assertNotIn("Garrick", text)
        self.assertTrue(any(d["id"] == f"venue-door:{shop_id}" for d in self.world["doors"]))
        self.assertNotIn("Adsız", text)
        self.assertEqual(self.world["location"], CITY)

    async def test_a_chain_that_goes_somewhere_stops_in_front(self):
        text, receipt = await self.turn("tapınağa varınca kapısı açık mı diye bakıyorum")
        self.assertEqual(self.world["location"], CITY, (text, receipt))

    async def test_opening_a_crate_never_opens_the_door_and_creates_no_item(self):
        await self.turn("Garrick Hanına yaklaşıyorum")
        inventory = copy.deepcopy(self.world["inventory"])
        before = self.door()
        text, receipt = await self.turn("Sandığın kapağını kaldırmayı deniyorum; kilitliyse hiç uğraşmıyorum.")
        self.assertEqual(self.door(), before)
        self.assertEqual(self.world["inventory"], inventory)
        self.assertNotIn("Kapıyı itiyorsun", text)

    async def test_take_me_there_is_not_sitting_down(self):
        text, _ = await self.turn("beni oraya goturur musun yolu hic bilmiyorum")
        self.assertNotIn("Oturabileceğin", text)

    # --- execute_intent: no owner means not resolved -------------------------
    def test_interact_without_an_owner_is_not_reported_as_resolved(self):
        result = self.session.execute_intent({"intent": "interact"}, "taşın üstündeki yosunu okşuyorum")
        self.assertNotEqual(result.get("status"), "resolved", result)
        self.assertFalse(result.get("success"), result)


if __name__ == "__main__":
    unittest.main()
