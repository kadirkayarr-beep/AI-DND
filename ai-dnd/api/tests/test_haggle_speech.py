"""Price negotiation must work through the actual HTTP Say path, in its one speech call."""
import copy
import json
from unittest.mock import patch
from uuid import uuid4

import front_proposal
import game
from api.tests.journeys.runner import call_kind
from api.tests.test_economic_action_http import EconomicHttpFixture, ROOM
from api.tests import test_campaign_api

LINE = "Bu oda için bütçeme biraz yaklaşır mısın?"


def say_calls():
    """What one Say line spends: its one speech call, after the front reading when the flag is on."""
    return ["front", "speech"] if front_proposal.enabled() else ["speech"]


class PriceSpeechClient:
    def __init__(self, text, propose=True, corrupt=None, person="barman"):
        self.text, self.propose, self.corrupt, self.person = text, propose, corrupt, person
        self.calls = []

    def kinds(self):
        return [call_kind(call["format"]) for call in self.calls]

    def speech_call(self):
        return next(call for call in self.calls if call_kind(call["format"]) == "speech")

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        props = kwargs["format"]["properties"]
        if "front" in props:
            # Flag on, the line is read first, as local play's model reads it: words said to the person spoken to.
            front = {"kind": "speak_to", "person_id": self.person, "place_id": "none", "offer_id": "none",
                     "thing_id": "none", "answer": "none", "inside": False, "timing": "now"}
            return {"message": {"content": json.dumps({"intent": "dialogue", "action": "dialogue", "target": {
                "type": "none", "reference": ""}, "completion": "unclear", "confidence": 0.9, "front": front})}}
        assert "spoken_text" in props, "Say must not add a classifier or narrator call"
        packet = {"spoken_text": "Teklifini dinliyorum; hesabı beraber gözden geçirebiliriz.",
                  "stage_direction": "", "threat": "none"}
        if self.propose and "price_negotiation" in props:
            shape = props["price_negotiation"]["properties"]
            value = {"offer_id": shape["offer_id"]["enum"][0], "npc_id": "barman", "evidence_quote": self.text}
            if self.corrupt:
                value.update(self.corrupt)
            packet["price_negotiation"] = value
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


class NaturalPriceSpeech(EconomicHttpFixture):
    async def ready(self, modifier=3):
        self.record.game_session._experimental_npc_dialogue_enabled = True
        self.record.game_session.character["modifiers"]["charisma"] = modifier
        self.record.game_session.rng.seed(12)
        await self.card(**ROOM)
        self.save()

    async def say(self, text=LINE, propose=True, corrupt=None, body=None):
        body = body or {"message": text, "interaction_mode": "say", "target_id": "barman", "action_id": str(uuid4())}
        client = PriceSpeechClient(text, propose, corrupt, person=body["target_id"])
        with patch.object(game, "perform_skill_check", wraps=game.perform_skill_check) as checks:
            response = await test_campaign_api.CampaignApiTests.post_scene_turn(self, self.turn_url, client, body)
        return response, client, checks, body

    def open_total(self):
        cards = [o for o in self.offers().values() if o["status"] == "prepared"]
        self.assertEqual(len(cards), 1)
        return sum(line["total_cp"] for line in cards[0]["lines"])

    async def test_natural_say_request_rolls_once_and_discounts_without_payment(self):
        await self.ready()
        response, client, checks, body = await self.say()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.kinds(), say_calls())
        self.assertEqual(checks.call_count, 1)
        self.assertEqual(checks.call_args.args[0], "Persuasion")
        self.assertEqual(self.open_total(), 45)
        self.assertEqual(self.purse(), 100)
        self.assertIn("45 bakır", response.json()["narration"])
        self.assertEqual(response.json()["turn_outcome"]["action"], "skill_check")
        replay, again, replay_checks, _ = await self.say(body=body)
        self.assertEqual(replay.content, response.content)
        self.assertEqual(len(again.calls), 0)
        self.assertEqual(replay_checks.call_count, 0)

    async def test_an_unrelated_say_line_keeps_speech_and_never_rolls_or_discounts(self):
        await self.ready()
        response, client, checks, _ = await self.say("Köprüden geçmek güvenli mi?", propose=False)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.kinds(), say_calls())
        self.assertEqual(checks.call_count, 0)
        self.assertEqual(self.open_total(), 50)
        self.assertEqual(self.purse(), 100)
        self.assertIn("Teklifini", response.json()["narration"])

    async def test_invalid_proposal_does_not_block_the_spoken_reply(self):
        await self.ready()
        response, client, checks, _ = await self.say(corrupt={"evidence_quote": "başka turdan söz"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.kinds(), say_calls())
        self.assertEqual(checks.call_count, 0)
        self.assertEqual(self.open_total(), 50)
        self.assertIn("Teklifini", response.json()["narration"])

    async def test_failed_engine_check_keeps_the_price_and_does_not_spend_daily_discount(self):
        await self.ready(modifier=-20)
        response, client, checks, _ = await self.say()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.kinds(), say_calls())
        self.assertEqual(checks.call_count, 1)
        self.assertEqual(self.open_total(), 50)
        self.assertEqual(self.purse(), 100)
        npc = next(n for n in self.world["npcs"] if n["id"] == "barman")
        self.assertNotIn("price_cut_day_v1", npc)
        self.assertIn("fiyat aynı", response.json()["narration"])
    async def test_default_do_question_with_selected_npc_uses_the_same_speech_call(self):
        await self.ready()
        body = {"message": LINE, "interaction_mode": "do", "target_id": "barman", "action_id": str(uuid4())}
        response, client, checks, _ = await self.say(body=body)
        self.assertEqual(response.status_code, 200, response.text)
        # A Do line to a chosen person is not read first (front skip "skipped:typed"), flag on or off.
        self.assertEqual(client.kinds(), ["speech"])
        self.assertEqual(checks.call_count, 1)
        self.assertEqual(self.open_total(), 45)
        self.assertEqual(self.purse(), 100)

    async def test_other_npc_never_receives_the_barmans_offer(self):
        await self.ready()
        body = {"message": LINE, "interaction_mode": "say", "target_id": "farmer", "action_id": str(uuid4())}
        response, client, checks, _ = await self.say(body=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.kinds(), say_calls())
        self.assertNotIn("price_negotiation", client.speech_call()["format"]["properties"])
        self.assertEqual(checks.call_count, 0)
        self.assertEqual(self.open_total(), 50)

    async def test_model_price_field_is_rejected_without_blocking_speech(self):
        await self.ready()
        response, client, checks, _ = await self.say(corrupt={"amount_cp": 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.kinds(), say_calls())
        self.assertEqual(checks.call_count, 0)
        self.assertEqual(self.open_total(), 50)
        self.assertEqual(self.purse(), 100)
        self.assertIn("Teklifini", response.json()["narration"])

    async def test_speech_discount_save_failure_rolls_back_and_same_action_retries(self):
        from api.persistence.campaign_models import CampaignStorageError
        await self.ready()
        before = copy.deepcopy(self.world)
        with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("synthetic speech discount save")):
            response, _, checks, body = await self.say()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(checks.call_count, 1)
        self.assertEqual(self.world, before)
        response, client, checks, _ = await self.say(body=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.open_total(), 45)
        self.assertEqual(self.purse(), 100)

    async def test_speech_discount_reloads_and_undo_restores_daily_right(self):
        from api.session_manager import SessionManager
        from api.persistence.campaign_store import CampaignStore
        from api.tests.auth_fixture import TEST_PLAYER
        await self.ready()
        response, _, _, body = await self.say()
        self.assertEqual(response.status_code, 200, response.text)
        manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        _, record, *_ = manager.resume_campaign(self.record.campaign_id, principal=TEST_PLAYER)
        npc = next(n for n in record.game_session.world_state["npcs"] if n["id"] == "barman")
        self.assertEqual(npc["price_cut_cp_v1"], {"room": 5})
        undone = await self.http.post(self.undo_url, json={"action_id": str(uuid4()), "target_action_id": body["action_id"]})
        self.assertEqual(undone.status_code, 200, undone.text)
        npc = next(n for n in self.world["npcs"] if n["id"] == "barman")
        self.assertNotIn("price_cut_day_v1", npc)
        self.assertNotIn("price_cut_cp_v1", npc)
        self.assertEqual(self.purse(), 100)
        manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        _, record, *_ = manager.resume_campaign(self.record.campaign_id, principal=TEST_PLAYER)
        self.assertEqual(record.game_session.world_state, self.world)
    async def test_statement_negotiation_uses_one_engine_roll_and_one_rng_draw(self):
        import random
        await self.ready()
        text = "Bu odanın fiyatını düşürmeye ikna etmeye çalışıyorum"
        traces = []
        original = game.perform_skill_check

        def traced(*args, **kwargs):
            rng = self.record.game_session.rng
            before = rng.getstate()
            result = original(*args, **kwargs)
            traces.append((before, rng.getstate(), copy.deepcopy(result)))
            return result

        with patch.object(game, "perform_skill_check", side_effect=traced):
            response, client, checks, _ = await self.say(text)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.kinds(), say_calls())
        self.assertEqual(checks.call_count, 1)
        self.assertEqual(len(traces), 1)
        before, after, resolved = traces[0]
        expected_rng = random.Random()
        expected_rng.setstate(before)
        expected_die = expected_rng.randint(1, 20)
        self.assertEqual(resolved["dice"], expected_die)
        self.assertEqual(after, expected_rng.getstate())
        self.assertEqual(self.record.game_session.rng.getstate(), after)
        self.assertEqual(resolved["result"], "BAŞARILI")
        self.assertEqual(self.open_total(), 45)
        self.assertEqual(self.purse(), 100)
        self.assertIn("45 bakır", response.json()["narration"])