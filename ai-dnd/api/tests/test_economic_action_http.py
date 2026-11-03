"""A3: the card over HTTP. Prepare and cancel are not turns; a confirm is a turn only when it consumes the card.

The economic gate stays closed in the product (A4 opens it); these tests open it with `patch`. No model call: a
"real turn" here is a scripted narrative reply at the model boundary, and the confirm path calls no model at all.
Every refusal leaves the purse, the pack, the ledger, the undo checkpoint and the turn counter exactly as they were.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import economic_actions as ea
from api.tests import test_campaign_api as fixtures
from api.tests.test_economic_offer import OfferFixture, proposal

ROOM = {"purpose": "room", "recipient_id": "barman"}
TIP = {"purpose": "tip", "recipient_id": "barman", "amount_cp": 4}


class EconomicHttpFixture(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.CampaignApiTests.asyncSetUp(self)
        self.enterContext(patch("api.main.ECONOMIC_ACTIONS_ENABLED", True))
        self.campaign = await fixtures.CampaignApiTests.create_campaign(self)
        self.turn_url = f'/api/game/sessions/{self.campaign["session_id"]}/turn'
        self.undo_url = f'/api/game/sessions/{self.campaign["session_id"]}/undo'
        self.here = self.world["location"]
        self.world["npcs"] = [
            {"id": "barman", "name": "Marek", "role": "Barmen", "location": self.here, "current_hp": 10},
            {"id": "guard", "name": "Çavuş Hale", "role": "Muhafız", "location": self.here, "current_hp": 10},
            {"id": "farmer", "name": "Ilgın", "role": "Çiftçi", "location": self.here, "current_hp": 10},
        ]
        self.world["currency"] = {"player": 100, "barman": 0, "farmer": 0, "guard": 0}
        self.save()

    async def asyncTearDown(self):
        await fixtures.CampaignApiTests.asyncTearDown(self)

    @property
    def record(self):
        return self.manager.get(self.campaign["session_id"])

    @property
    def world(self):
        return self.record.game_session.world_state

    def save(self):
        self.manager.save_campaign(self.campaign["campaign_id"])

    def revision(self):
        return self.store.get_campaign(self.record.campaign_id).metadata["revision"]

    def offers(self):
        return self.world.get("flags", {}).get("economic_offers", {})

    def purse(self):
        return self.world["currency"]["player"]

    def money(self):
        """The live purse, pack and ledger as bytes: a refusal must leave them exactly as they were."""
        flags = self.world.get("flags", {})
        return json.dumps({"currency": self.world["currency"], "inventory": self.world.get("inventory"),
                           "ledger": flags.get("economic_ledger"), "inn_room": flags.get("inn_room"),
                           "turn_index": flags.get("turn_index", 0)}, ensure_ascii=False, sort_keys=True)

    async def post(self, body):
        return await self.http.post(self.turn_url, json=body)

    async def act(self, economic_action, message, action_id=None):
        body = {"message": message, "action_id": action_id or str(uuid4()), "economic_action": economic_action}
        return await self.post(body), body

    async def prepare(self, **fields):
        response, _ = await self.act({"kind": "prepare", "proposal": fields}, "Teklif hazırla")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def card(self, **fields):
        prepared = await self.prepare(**fields)
        card = prepared["state"]["economic_offer"]
        self.assertIsNotNone(card, prepared["narration"])
        return card

    async def confirm(self, card, action_id=None, digest=None):
        response, body = await self.act(
            {"kind": "confirm", "offer_id": card["offer_id"],
             "confirmation_digest": digest or card["confirmation_digest"]}, "Teklifi onayla", action_id)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), body

    async def cancel(self, offer_id):
        response, _ = await self.act({"kind": "cancel", "offer_id": offer_id}, "Teklifi iptal et")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def real_turn(self, message="Tezgâha yaslanıp salonu dinliyorum."):
        """A completed ordinary turn that keeps the place; the narration is scripted at the model boundary."""
        narrator = fixtures.ControlledVenueOllamaClient("narrative")
        action_id = str(uuid4())
        with patch("api.tests.test_campaign_api.FakeOllamaClient.chat", side_effect=narrator.chat):
            response = await self.post({"message": message, "action_id": action_id})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.world["location"], self.here)
        self.assertEqual(self.record.undo_checkpoint["action_id"], action_id)
        return action_id, response.json()

    async def undo(self, target):
        return await self.http.post(self.undo_url, json={"action_id": str(uuid4()), "target_action_id": target})

    def checkpoint(self):
        checkpoint = getattr(self.record, "undo_checkpoint", None)
        return None if checkpoint is None else (checkpoint["action_id"], checkpoint["post_turn_fingerprint"])

    def hold_by_guard(self):
        deed = {"kind": "theft", "at": 120, "location": self.here, "text": "Tezgâhtan kese çalındı",
                "described": ["guard"], "witnesses": [], "told": [], "heard": [], "seen_near": [],
                "hold": {"guard": "guard", "place": self.here, "turn": 0, "arrest": True}}
        self.world.setdefault("flags", {}).setdefault("deeds", []).append(deed)
        return deed


class ConfirmIsBoundToItsAction(EconomicHttpFixture):
    async def test_confirm_replay_and_payload_conflict(self):
        card = await self.card(**TIP)
        accepted, body = await self.confirm(card)
        self.assertEqual(accepted["economic_resolution"]["status"], "applied")
        self.assertEqual(self.purse(), 96)
        committed = (self.money(), copy.deepcopy(self.offers()), self.revision())
        replay = await self.post(body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), accepted)
        self.assertEqual((self.money(), self.offers(), self.revision()), committed)
        conflict = await self.post({**body, "economic_action": {"kind": "cancel", "offer_id": card["offer_id"]}})
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["detail"]["code"], "action_id_conflict")
        self.assertEqual((self.money(), self.offers(), self.revision()), committed)

    async def test_new_action_cannot_consume_offer_twice(self):
        card = await self.card(**TIP)
        first, _ = await self.confirm(card)
        self.assertEqual(first["economic_resolution"]["net_debit_cp"], 4)
        paid = self.money()
        second, _ = await self.confirm(card)
        self.assertEqual(second["economic_resolution"]["status"], "refused")
        self.assertEqual(second["economic_resolution"]["reason_code"], "offer_not_prepared")
        self.assertEqual(second["economic_resolution"]["net_debit_cp"], 0)
        self.assertEqual(self.money(), paid)
        self.assertEqual((self.purse(), self.world["currency"]["barman"]), (96, 4))

    async def test_unprepared_or_stale_offer_confirm_changes_nothing(self):
        self.world["inventory"] = [*self.world.get("inventory", []), "8 Altın"]
        self.save()
        card = await self.card(**ROOM)
        turn_id, _ = await self.real_turn()
        before = (self.money(), self.checkpoint())
        self.assertIn("8 Altın", self.world["inventory"])
        unknown = {**card, "offer_id": "f" * 32}
        cases = (("offer_not_prepared", unknown, None, None), ("digest_mismatch", card, "0" * 64, None),
                 ("stale", card, None, 60))
        for reason, target, digest, price in cases:
            with self.subTest(reason):
                with patch("bold_acts._ROOM_PRICE", price or 50):
                    answered, _ = await self.confirm(target, digest=digest)
                resolution = answered["economic_resolution"]
                self.assertEqual((resolution["status"], resolution["reason_code"]), ("refused", reason))
                self.assertEqual(resolution["net_debit_cp"], 0)
                self.assertEqual((self.money(), self.checkpoint()), before)
                self.assertIn("8 Altın", self.world["inventory"])
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")
        undone = await self.undo(turn_id)
        self.assertEqual(undone.status_code, 200, undone.text)

    async def test_changed_price_or_recipient_needs_new_confirmation(self):
        with self.subTest("price"):
            card = await self.card(**ROOM)
            with patch("bold_acts._ROOM_PRICE", 60):
                answered, _ = await self.confirm(card)
            self.assertEqual(answered["economic_resolution"]["reason_code"], "stale")
            self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")
            self.assertIsNone(answered["state"]["economic_offer"])
            self.assertEqual(self.purse(), 100)
        with self.subTest("recipient"):
            card = await self.card(purpose="gift", recipient_id="farmer", amount_cp=10)
            self.world["npcs"][2]["hidden"] = True
            answered, _ = await self.confirm(card)
            self.assertEqual(answered["economic_resolution"]["reason_code"], "stale")
            self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")
            self.assertEqual((self.purse(), self.world["currency"]["farmer"]), (100, 0))

    async def test_other_npc_change_keeps_offer_valid(self):
        card = await self.card(purpose="gift", recipient_id="farmer", amount_cp=10)
        self.world["npcs"][1]["location"] = "somewhere-else"
        self.world["npcs"][0]["mood"] = "yorgun"
        answered, _ = await self.confirm(card)
        self.assertEqual(answered["economic_resolution"]["status"], "applied", answered["narration"])
        self.assertEqual((self.purse(), self.world["currency"]["farmer"]), (90, 10))


class WhatThePanelMayPrepare(EconomicHttpFixture):
    async def test_panel_prepare_refuses_purchase_and_item_gift(self):
        room = await self.card(**ROOM)
        before = (copy.deepcopy(self.offers()), self.money(),
                  json.dumps([npc.get("wares_v1") for npc in self.world["npcs"]]))
        for fields in ({"purpose": "purchase", "recipient_id": "barman", "item_id": "bira"},
                       {"purpose": "item_gift", "recipient_id": "farmer", "item_id": "kılıç"}):
            with self.subTest(fields["purpose"]):
                answered = await self.prepare(**fields)
                self.assertEqual(answered["turn_outcome"]["status"], "clarification")
                self.assertEqual(answered["turn_outcome"]["reason"], "purpose_not_offered_here")
                self.assertEqual(answered["state"]["economic_offer"]["offer_id"], room["offer_id"])
                self.assertEqual((self.offers(), self.money(),
                                  json.dumps([npc.get("wares_v1") for npc in self.world["npcs"]])), before)

    async def test_panel_bribe_prepare_is_refused(self):
        tip = await self.card(**TIP)
        self.hold_by_guard()
        before = copy.deepcopy(self.offers())
        with patch("bold_acts._check", side_effect=AssertionError("No check is rolled while preparing")):
            answered = await self.prepare(purpose="gift", recipient_id="guard", amount_cp=100)
        self.assertEqual((answered["turn_outcome"]["status"], answered["turn_outcome"]["reason"]),
                         ("clarification", "bribe_in_turn_only"))
        self.assertEqual(self.offers(), before)
        self.assertEqual(answered["state"]["economic_offer"]["offer_id"], tip["offer_id"])
        # Without the arrest the same gift goes by the A1 rules: the guard who can tie the player to the deed
        # refuses it, exactly as `prepare_offer` says; with no deed at all it is an ordinary gift card.
        self.world["flags"]["deeds"][-1].pop("hold")
        expected = ea.prepare_offer(
            ea.EconomicState(world=self.world, character=None),
            proposal(purpose="gift", recipient_id="guard", amount_cp=100), offer_id="a" * 32,
            campaign_id="c", actor_id="player", turn_index=0)
        answered = await self.prepare(purpose="gift", recipient_id="guard", amount_cp=100)
        self.assertEqual((answered["turn_outcome"]["status"], answered["turn_outcome"]["reason"]),
                         (expected.status, expected.reason_code))
        self.assertEqual(expected.status, "refused")
        self.world["flags"]["deeds"].pop()
        gift = await self.card(purpose="gift", recipient_id="guard", amount_cp=100)
        self.assertFalse(gift["may_refuse"])
        self.assertEqual(gift["max_total_cp"], 100)

    async def test_new_prepare_cancels_other_prepared_offers(self):
        first = await self.card(**TIP)
        second = await self.card(purpose="gift", recipient_id="farmer", amount_cp=10)
        self.assertEqual(self.offers()[first["offer_id"]]["status"], "cancelled")
        asked = await self.prepare(purpose="gift", recipient_id="farmer")  # no amount: a question, no card
        self.assertEqual(asked["turn_outcome"]["status"], "clarification")
        self.assertEqual(asked["state"]["economic_offer"]["offer_id"], second["offer_id"])
        self.assertEqual([offer_id for offer_id, data in self.offers().items() if data["status"] == "prepared"],
                         [second["offer_id"]])

    async def test_session_state_projects_single_offer_and_wallet(self):
        from api import serializers
        session = self.record.game_session
        saved_keys = set(session.serialize_game_state())
        version = session.serialize_game_state().get("version")
        card = await self.card(**TIP)
        projected = serializers.serialize_session_state(session)
        self.assertEqual(projected["economic_offer"]["offer_id"], card["offer_id"])
        self.assertEqual(set(session.serialize_game_state()), saved_keys)
        self.assertEqual(session.serialize_game_state().get("version"), version)
        self.assertNotIn("economic_offer", session.serialize_game_state())
        self.assertNotIn("wallet", session.serialize_game_state())
        await self.cancel(card["offer_id"])
        self.assertIsNone(serializers.serialize_session_state(session)["economic_offer"])
        self.world["currency"] = {"player": 40, "barman": 137}
        self.world["inventory"] = [*self.world.get("inventory", []), "1 Altın"]
        inventory = json.dumps(self.world["inventory"], ensure_ascii=False)
        projected = serializers.serialize_session_state(session)
        self.assertEqual(projected["wallet"], {"total_cp": 140})
        self.assertEqual(json.dumps(self.world["inventory"], ensure_ascii=False), inventory)
        self.assertEqual(self.world["currency"], {"player": 40, "barman": 137})
        self.assertNotIn("137", json.dumps({"wallet": projected["wallet"], "offer": projected["economic_offer"]}))

    async def test_client_cannot_send_source_action_id(self):
        before = (self.money(), copy.deepcopy(self.offers()), self.revision())
        response, _ = await self.act({"kind": "prepare", "proposal": {**ROOM, "source_action_id": str(uuid4())}},
                                     "Teklif hazırla")
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual((self.money(), self.offers(), self.revision()), before)


class WhenTheWorldMoved(EconomicHttpFixture):
    async def assert_stale_and_nothing_moved(self, card):
        before = self.money()
        answered, _ = await self.confirm(card)
        resolution = answered["economic_resolution"]
        self.assertEqual((resolution["status"], resolution["reason_code"]), ("refused", "stale"))
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")
        self.assertEqual(self.money(), before)
        self.assertEqual(resolution["net_debit_cp"], 0)
        self.assertIn("yeni kart", answered["narration"])

    async def test_confirm_after_innkeeper_left_changes_nothing(self):
        card = await self.card(**ROOM)
        self.world["npcs"][0]["location"] = "somewhere-else"
        await self.assert_stale_and_nothing_moved(card)
        self.assertNotIn("inn_room", self.world["flags"])

    async def test_confirm_after_the_player_died_out_of_combat_changes_nothing(self):
        card = await self.card(**ROOM)
        import game
        death = game._death_state_defaults()
        death.update(dead=True, terminal=True)
        self.world["death_state"] = death
        self.record.game_session.character["current_hp"] = 0  # a dead player has no hit points left
        self.assertFalse(self.world.get("combat", {}).get("active"))
        before, checkpoint, revision = self.money(), self.checkpoint(), self.revision()
        world_before = copy.deepcopy(self.world)
        response, _ = await self.act({"kind": "confirm", "offer_id": card["offer_id"],
                                      "confirmation_digest": card["confirmation_digest"]}, "Teklifi onayla")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "player_cannot_act")
        self.assertEqual(self.money(), before)
        self.assertEqual(self.world, world_before)
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "prepared")
        self.assertNotIn("inn_room", self.world["flags"])
        self.assertEqual(self.checkpoint(), checkpoint)
        self.assertEqual(self.revision(), revision)

    async def test_prepare_while_unconscious_opens_no_card(self):
        self.record.game_session.character["current_hp"] = 0
        before, checkpoint = self.money(), self.checkpoint()
        offers = copy.deepcopy(self.offers())
        response, _ = await self.act({"kind": "prepare", "proposal": ROOM}, "Teklif hazırla")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "player_cannot_act")
        self.assertEqual(self.offers(), offers)
        self.assertEqual(self.money(), before)
        self.assertEqual(self.checkpoint(), checkpoint)

    async def test_confirm_during_combat_changes_nothing(self):
        card = await self.card(**TIP)
        with patch("economic_actions._combat", return_value=True):
            await self.assert_stale_and_nothing_moved(card)

    async def test_gift_recipient_not_in_scene_is_refused(self):
        card = await self.card(purpose="gift", recipient_id="farmer", amount_cp=10)
        self.world["npcs"][2]["location"] = "somewhere-else"
        await self.assert_stale_and_nothing_moved(card)

    async def test_purse_drop_after_prepare_is_r5_not_stale(self):
        self.world["currency"]["player"] = 60
        card = await self.card(**ROOM, tip_cp=5)
        self.world["currency"]["player"] = 52
        answered, _ = await self.confirm(card)
        resolution = answered["economic_resolution"]
        self.assertEqual(resolution["status"], "applied")
        self.assertNotEqual(resolution["reason_code"], "stale")
        self.assertEqual(resolution["refusals"], [{"line_id": "tip:1", "reason_code": "no_money"}])
        self.assertEqual((self.purse(), self.world["currency"]["barman"]), (2, 0))
        self.assertEqual(self.world["flags"]["inn_room"]["place"], self.here)

    async def test_refused_confirm_consumes_offer(self):
        card = await self.card(**ROOM)
        self.world["currency"]["player"] = 40
        answered, body = await self.confirm(card)
        resolution = answered["economic_resolution"]
        self.assertEqual((resolution["status"], resolution["reason_code"]), ("refused", "no_money"))
        stored = self.offers()[card["offer_id"]]
        self.assertEqual((stored["status"], stored["consumed_action_id"]), ("consumed", body["action_id"]))
        self.assertIn(stored["operation_id"], self.world["flags"]["economic_ledger"]["operations"])
        again, _ = await self.confirm(card)
        self.assertEqual(again["economic_resolution"]["reason_code"], "offer_not_prepared")
        self.assertEqual(self.purse(), 40)

    async def test_confirm_persists_coin_label_settlement(self):
        with self.subTest("applied"):
            self.world["currency"]["player"] = 0
            self.world["inventory"] = [*self.world.get("inventory", []), "8 Altın"]
            card = await self.card(**TIP)
            self.assertIn("8 Altın", self.world["inventory"])
            answered, _ = await self.confirm(card)
            self.assertEqual(answered["economic_resolution"]["status"], "applied")
            self.assertNotIn("8 Altın", self.world["inventory"])
            self.assertEqual(self.purse(), 796)
        with self.subTest("consuming refusal"):
            self.world["currency"]["player"] = 0
            self.world["inventory"] = [*self.world.get("inventory", []), "1 Altın"]
            card = await self.card(**ROOM, tender_cp=900)
            answered, _ = await self.confirm(card)
            resolution = answered["economic_resolution"]
            self.assertEqual((resolution["status"], resolution["reason_code"]), ("refused", "tender_invalid"))
            self.assertNotIn("1 Altın", self.world["inventory"])
            self.assertEqual(self.purse(), 100)
            self.assertEqual(self.offers()[card["offer_id"]]["status"], "consumed")

    async def test_room_plus_tip_prepare_confirm_over_http(self):
        sink = f"sink:lodging:{self.here}"
        cases = (("base_required", 100, (45, 5, 50, True)), ("all_or_none", 100, (45, 5, 50, True)),
                 ("base_required", 52, (2, 0, 50, True)), ("all_or_none", 52, (52, 0, 0, False)))
        for dependency, purse, expected in cases:
            with self.subTest(dependency=dependency, purse=purse):
                self.world["flags"].pop("inn_room", None)
                self.world["flags"].pop("economic_ledger", None)
                self.world["currency"] = {"player": 100, "barman": 0}
                card = await self.card(**ROOM, tip_cp=5, dependency=dependency)
                self.assertEqual(card["dependency"], dependency)
                self.assertEqual([(line["line_id"], line["total_cp"], line["optional"]) for line in card["lines"]],
                                 [("room:0", 50, False), ("tip:1", 5, dependency == "base_required")])
                self.world["currency"]["player"] = purse
                answered, _ = await self.confirm(card)
                ledger = self.world["flags"].get("economic_ledger") or {}
                got = (self.purse(), self.world["currency"].get("barman", 0),
                       (ledger.get("sink_totals") or {}).get(sink, 0), "inn_room" in self.world["flags"])
                self.assertEqual(got, expected, answered["economic_resolution"])

    async def test_confirm_runs_no_free_text_pipeline(self):
        card = await self.card(**TIP)
        turn = self.world["flags"].get("turn_index", 0)
        nothing = AssertionError("The confirm must not run the free-text pipeline")
        with patch("world_reactions.answer", side_effect=nothing), patch("world_reactions._press", side_effect=nothing), \
                patch("game.ollama.chat", side_effect=nothing):
            answered, _ = await self.confirm(card)
        self.assertEqual(answered["economic_resolution"]["status"], "applied")
        self.assertEqual(answered["narration"], answered["economic_resolution"]["public_summary"])
        self.assertEqual(self.world["flags"]["turn_index"], turn + 1)

    async def test_confirm_rejects_tampered_resolution_before_commit(self):
        card = await self.card(**TIP)
        before = (self.money(), copy.deepcopy(self.offers()), self.revision())
        real = ea.resolve_offer

        def five(*args, **kwargs):
            honest = real(*args, **kwargs)
            return dataclasses.replace(honest, net_debit_cp=5, asset_deltas=[
                ea.AssetDelta("player", "currency", "cp", 100, 95), ea.AssetDelta("barman", "currency", "cp", 0, 5)])

        with patch("economic_actions.resolve_offer", side_effect=five):
            refused, _ = await self.act({"kind": "confirm", "offer_id": card["offer_id"],
                                         "confirmation_digest": card["confirmation_digest"]}, "Teklifi onayla")
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(refused.json()["detail"]["code"], "economic_receipt_refused")
        self.assertEqual((self.money(), self.offers(), self.revision()), before)
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "prepared")


class CancelIsNotUndo(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown

    async def test_cancel_does_not_undo_prior_travel(self):
        self.enterContext(patch("api.main.ECONOMIC_ACTIONS_ENABLED", True))
        _, session_id, _, turn_url, _, _ = await fixtures.create_city_with_locked_tavern(self)
        travel_id = str(uuid4())
        travelled = await self.http.post(turn_url, json={"message": "Tapınağa gidiyorum.", "action_id": travel_id})
        self.assertEqual(travelled.status_code, 200, travelled.text)
        record = self.manager.get(session_id)
        world = record.game_session.world_state
        place = world["location"]
        world["npcs"].append({"id": "farmer", "name": "Ilgın", "role": "Çiftçi", "location": place, "current_hp": 10})
        world["currency"] = {"player": 100}
        prepared = await self.http.post(turn_url, json={
            "message": "Teklif hazırla", "action_id": str(uuid4()),
            "economic_action": {"kind": "prepare",
                                "proposal": {"purpose": "gift", "recipient_id": "farmer", "amount_cp": 10}}})
        self.assertEqual(prepared.status_code, 200, prepared.text)
        card = prepared.json()["state"]["economic_offer"]
        cancelled = await self.http.post(turn_url, json={
            "message": "Teklifi iptal et", "action_id": str(uuid4()),
            "economic_action": {"kind": "cancel", "offer_id": card["offer_id"]}})
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertIsNone(cancelled.json()["state"]["economic_offer"])
        self.assertEqual(world["location"], place)
        self.assertEqual(world["currency"], {"player": 100})
        self.assertEqual(record.undo_checkpoint["action_id"], travel_id)


class OfferLifetime(OfferFixture):
    def stored(self, value, *, source="action-1"):
        result = ea.prepare_from_panel(self.state(), dataclasses.replace(value, source_action_id=source),
                                       campaign_id="campaign-1", actor_id="player",
                                       turn_index=self.w["flags"]["turn_index"])
        self.assertEqual(result.status, "prepared", result.public_message)
        return result.offer.offer_id

    def test_location_change_cancels_prepared_offers(self):
        first = self.stored(proposal(purpose="tip", recipient_id="barman", amount_cp=3), source="action-1")
        records = ea.offer_records(self.w)
        records["second"] = {**copy.deepcopy(records[first]), "offer_id": "second",
                             "proposal": {**records[first]["proposal"], "source_action_id": "action-2"},
                             "status": "prepared"}
        self.assertEqual(ea.cancel_prepared(self.w, actor_id="player", except_source_action_id="action-2"), [first])
        self.assertEqual((records[first]["status"], records["second"]["status"]), ("cancelled", "prepared"))
        self.assertEqual(ea.cancel_prepared(self.w, actor_id="player"), ["second"])
        self.assertEqual(ea.cancel_prepared(self.w, actor_id="player"), [])

    def test_offer_records_are_bounded(self):
        ids = [self.stored(proposal(purpose="tip", recipient_id="barman", amount_cp=index + 1))
               for index in range(25)]
        records = ea.offer_records(self.w)
        self.assertEqual(len(records), ea.OFFER_RECORDS_KEEP + 1)
        self.assertEqual(records[ids[-1]]["status"], "prepared")
        self.assertEqual(list(records), ids[-21:])
        records[ids[-21]].update(status="consumed", consumed_action_id="checkpoint-action")
        ea.cancel_prepared(self.w, actor_id="player")
        ea.prune_offer_records(self.w, keep=3, protect_action_id="checkpoint-action")
        self.assertIn(ids[-21], records)
        self.assertEqual(len(records), 4)
        self.assertTrue(all(len(offer_id) == 32 for offer_id in records))


if __name__ == "__main__":
    unittest.main()
