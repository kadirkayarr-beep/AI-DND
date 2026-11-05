"""An open price offer and a social check are not, by themselves, a negotiation."""
import copy
from unittest.mock import patch

import game
import money_owner
from api.tests.test_spoken_decline import Spoken

LINE = "Bu oda için bütçeme biraz yaklaşır mısın?"


def proposal(world, npc_id="barman", kind="room", line=LINE):
    offer = next(o for o in money_owner.price_negotiation_offers(world)
                 if o["npc_id"] == npc_id and o["kind"] == kind)
    return {"offer_id": offer["offer_id"], "npc_id": npc_id, "evidence_quote": line}


class NegotiationAdmission(Spoken):
    def attempt(self, value=None, line=LINE):
        return money_owner.haggle(self.s, self.npc("barman"),
            {"skill": "Persuasion", "result": "BAŞARILI"}, negotiation=value, player_input=line)

    def test_absent_unclear_and_malformed_intent_change_nothing(self):
        self.prepare("room", "barman")
        before = copy.deepcopy(self.w)
        for value in (None, {}, "room", {"offer_id": "invented", "npc_id": "barman", "evidence_quote": LINE}):
            with self.subTest(value=value):
                self.assertIsNone(self.attempt(value))
                self.assertEqual(self.w, before)

    def test_current_offer_and_exact_evidence_allow_the_engine_discount(self):
        self.prepare("room", "barman")
        before = self.money()
        self.assertIn("45 bakır", self.attempt(proposal(self.w)))
        self.assertEqual(self.money(), before)

    def test_wrong_npc_quote_amount_and_stale_offer_are_rejected(self):
        self.prepare("room", "barman")
        valid = proposal(self.w)
        invalid = [{**valid, "npc_id": "osman"}, {**valid, "evidence_quote": "not in this turn"},
                   {**valid, "evidence_quote": ""}, {**valid, "amount_cp": 1}]
        for value in invalid:
            with self.subTest(value=value):
                before = copy.deepcopy(self.w)
                self.assertIsNone(self.attempt(value))
                self.assertEqual(self.w, before)
        self.w.setdefault("campaign_time", {})["elapsed_seconds"] = 86400
        before = copy.deepcopy(self.w)
        self.assertIsNone(self.attempt(valid))
        self.assertEqual(self.w, before)

    def test_classifier_exposes_only_current_offer_ids_without_price_authority(self):
        self.prepare("room", "barman")
        with patch.object(game.ollama, "chat", return_value={"message": {"content": '{"intent":"persuasion"}'}}) as chat:
            game.parse_player_intent(LINE)
        field = chat.call_args.kwargs["format"]["properties"]["price_negotiation"]
        self.assertEqual(set(field["properties"]), {"offer_id", "npc_id", "evidence_quote"})
        self.assertEqual(field["properties"]["offer_id"]["enum"],
                         [o["offer_id"] for o in money_owner.price_negotiation_offers(self.w)])
        self.assertFalse(field["additionalProperties"])
        self.assertEqual(chat.call_count, 1)
        self.assertEqual(chat.call_args.kwargs["options"]["num_predict"], 400)

    def test_normalization_keeps_only_a_current_grounded_offer_proposal(self):
        self.prepare("room", "barman")
        valid = proposal(self.w)
        self.assertEqual(game.normalize_intent({"intent": "persuasion", "price_negotiation": valid}, LINE)
                         ["price_negotiation"], valid)
        self.assertNotIn("price_negotiation", game.normalize_intent(
            {"intent": "persuasion", "price_negotiation": valid}, "Başka bir söz."))
    def test_a_cancelled_offer_and_a_replaced_counter_cannot_authorize_discount(self):
        self.prepare("room", "barman")
        old = proposal(self.w)
        self.prepare("room", "barman", tender_cp=60)
        before = copy.deepcopy(self.w)
        self.assertIsNone(self.attempt(old))
        self.assertEqual(self.w, before)
        self.open_counter(amount=0, keep_change=False)
        old_counter = proposal(self.w, kind="goods")
        self.w["flags"]["counter_offer_v1"]["seq"] += 1
        before = copy.deepcopy(self.w)
        self.assertIsNone(self.attempt(old_counter))
        self.assertEqual(self.w, before)


from dataclasses import replace
from api.tests.journeys.runner import JourneyCase, SCENARIO_DIR
from api.tests.journeys.schema import load_scenario


class NegotiationRoutes(JourneyCase):
    async def test_front_reading_keeps_the_same_explicit_price_intent(self):
        scenario = load_scenario(SCENARIO_DIR / "03_room_sleep.json")
        step = scenario.steps[1]
        # No price keyword is required: the same parser interprets the current utterance.
        text = "Kesem hafif, ortada buluşmaya ikna etmeye çalışıyorum."
        value = {"offer_id": "$room:barman", "npc_id": "barman", "evidence_quote": text}
        step = replace(step, say=text, script={"intent": {"intent": "persuasion", "price_negotiation": value},
                                              "front": {"kind": "attempt"}})
        scenario = replace(scenario, setup={**scenario.setup, "front_proposal": True},
                           steps=(scenario.steps[0], step))
        with patch.object(game, "parse_player_intent", wraps=game.parse_player_intent) as parser:
            results = await self.run_scenario(scenario)
        self.assertEqual([r.status for r in results], ["pass", "pass"], results)
        self.assertTrue(any(call.kwargs.get("front_list") is not None for call in parser.call_args_list))

    async def test_front_unclear_intent_keeps_the_social_check_without_discount(self):
        scenario = load_scenario(SCENARIO_DIR / "03_room_sleep.json")
        step = replace(scenario.steps[1], say="Köprüden geçmeye ikna etmeye çalışıyorum.",
                       script={"intent": "persuasion", "front": {"kind": "attempt"}},
                       expect={"kart": {"max_total_cp": 50}, "kese": 100})
        scenario = replace(scenario, setup={**scenario.setup, "front_proposal": True},
                           steps=(scenario.steps[0], step))
        with patch.object(game, "apply_check_outcome_to_world_state",
                          wraps=game.apply_check_outcome_to_world_state) as checks:
            results = await self.run_scenario(scenario)
        self.assertEqual([r.status for r in results], ["pass", "pass"], results)
        self.assertEqual(checks.call_args_list[-1].args[1]["skill"], "Persuasion")
        npc = next(n for n in self.manager.get(self.last_session_id).game_session.world_state["npcs"]
                   if n["id"] == "barman")
        self.assertNotIn("price_cut_day_v1", npc)