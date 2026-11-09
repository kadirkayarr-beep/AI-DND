"""Asking for a room or goods while talking (Dilim 2, Task 11, item 4): the speech answer's optional `asks_for` names
one of the records the engine lists for that person (`money_owner.askable`); only when this turn decided no money, no
fight is on, that part was not declined today and no card or offer of that part is open to that person does the money
owner open the room card or the counter's offer. Nothing is paid without the card's or the counter's confirmation.
The answer's decline fields (`coin_answer`, `coin_answer_for`) are worked first (tasarım karar 58, 64). No real model
is called: the speech answer is scripted."""
from __future__ import annotations

import copy
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import economic_actions
import front_proposal
import game
import money_owner
from api import serializers
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, ScriptedModel, apply_setup, read_observed
from api.tests.journeys.schema import Step, load_scenario


class TalkAsksFor(JourneyCase):
    """Scenario 08's inn: Marek the barman serves rooms and drinks; the purse holds 100 copper."""

    TALK_TO_MAREK = {"intent": "talk", "action": "talk",
                     "target": {"type": "npc", "reference": "Marek", "npc_id": "barman", "evidence_quote": ""},
                     "completion": "complete"}

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.scenario = load_scenario(SCENARIO_DIR / "08_talk_mode.json")
        self._token = None
        self._decisions = 0
        await self.reset_to_setup()

    async def asyncTearDown(self):
        if self._token is not None:
            game._ACTIVE_SESSION.reset(self._token)
        await super().asyncTearDown()

    async def reset_to_setup(self):
        """A fresh campaign with scenario 08's setup; the engine is bound to its session."""
        if self._token is not None:
            game._ACTIVE_SESSION.reset(self._token)
            self._token = None
        campaign = await self._journey_campaign(self.scenario.setup)
        apply_setup(self, campaign, self.scenario.setup)
        self.session_id = self.last_session_id = campaign["session_id"]
        self.last_turn_action_id = None
        self._front_on = False
        self._token = game._ACTIVE_SESSION.set(self.session)

    @property
    def session(self):
        return self.manager.get(self.session_id).game_session

    @property
    def world(self):
        return self.session.world_state

    def marek(self):
        return next(npc for npc in self.world["npcs"] if npc.get("id") == "barman")

    def stranger(self):
        stranger = {"id": "stranger", "name": "Yolcu", "role": "Yolcu", "location": self.world["location"],
                    "current_hp": 10}
        self.world["npcs"].append(stranger)
        return stranger

    async def talk(self, line, speech, front=None, refused=None):
        """One `konus: barman` line; the person's answer carries `speech`; `front` switches the front reading on.

        `refused` is the one HTTP refusal code the turn must end with (nothing applied); otherwise no failure.
        The classifier reads a talk to Marek, as scenario 08's step 3 scripts it. Once a campaign has had a front
        reading, its later lines keep the reading on (with the scripted default reading), as real play does: the flag
        never turns off mid-game, and a turn without the flag would not start (`front_proposal.begin`) a fresh turn
        of Dilim 1's money fields."""
        script = {"speech": copy.deepcopy(speech), "intent": copy.deepcopy(self.TALK_TO_MAREK)}
        if front is not None:
            script["front"] = copy.deepcopy(front)
            self._front_on = True
        step = Step(say=line, command=None, economic_action=None, combat_action=None, script=script,
                    expect={}, known_broken=(), real_chain=False, independent=True, konus="barman")
        flag = {front_proposal.FLAG: "1"} if self._front_on else {}
        real_decide = money_owner.decide
        self._decisions = 0

        def counted(*args, **kwargs):
            decision = real_decide(*args, **kwargs)
            self._decisions += decision is not None
            return decision

        with patch.dict(os.environ, flag), patch.object(money_owner, "decide", counted):
            failures = await self._play(self.session_id, step, ScriptedModel())
        if refused is None:
            self.assertEqual(failures, [])
        else:
            self.assertEqual(len(failures), 1, failures)
            self.assertTrue(failures[0].startswith("HTTP 400: ") and f'"code":"{refused}"' in failures[0]
                            and '"not_applied":true' in failures[0], failures)

    def observed(self):
        return read_observed(self, self.session_id)

    def ledger_rows(self):
        ledger = (self.world.get("flags") or {}).get("economic_ledger")
        operations = ledger.get("operations") if isinstance(ledger, dict) else None
        return sorted(operations) if isinstance(operations, dict) else []

    def money_decisions_this_turn(self):
        return self._decisions

    def open_cards_to(self, npc_id):
        return sum(1 for record in economic_actions.offer_records(self.world).values()
                   if (offer := economic_actions.offer_from_record(record)) is not None
                   and offer.status == "prepared" and offer.proposal.recipient_id == npc_id)

    def start_fight_here(self):
        enemy = {"id": "thug", "name": "Haydut", "role": "Haydut", "location": self.world["location"],
                 "current_hp": 9, "hostile": True}
        self.world["npcs"].append(enemy)
        game.start_combat(enemy)
        self.assertTrue(self.world["combat"]["active"])

    async def confirm_card(self, expect_refused=False):
        """The economic card's confirm route, with the card the state shows now (none: no id, no digest)."""
        card = serializers.serialize_session_state(self.session).get("economic_offer") or {}
        action_id = str(uuid4())
        body = {"action_id": action_id, "message": "Teklifi onayla",
                "economic_action": {"kind": "confirm", "offer_id": card.get("offer_id"),
                                    "confirmation_digest": card.get("confirmation_digest")}}
        response = await self.http.post(f"/api/game/sessions/{self.session_id}/turn", json=body)
        if expect_refused:
            ok = response.status_code == 200 and (response.json().get("action_result") or {}).get("success") is True
            self.assertFalse(ok, response.text[:300])
            return
        self.assertEqual(response.status_code, 200, response.text[:300])
        self.last_turn_action_id = action_id

    async def undo(self):
        failures = await self._undo(self.session_id, Step(
            say=None, command=None, economic_action=None, combat_action=None, script=None, expect={},
            known_broken=(), real_chain=False, independent=True, undo=True), ScriptedModel())
        self.assertEqual(failures, [])

    # --- tests (plan Task 11 Step 1) ---

    async def test_the_askable_list_comes_from_the_records(self):
        # order: room, goods by key, none; Marek's counter lists every good of the inn list (shop_trade.MENUS["inn"])
        self.assertEqual(money_owner.askable(self.world, self.marek()),
                         ["room", "goods:bira", "goods:sarap", "goods:yemek", "none"])
        self.assertEqual(money_owner.askable(self.world, self.stranger()), ["none"])

    async def test_asking_for_a_room_while_talking_opens_the_room_card(self):
        # one clause: "…, geceyi burada geçireyim" falls to the plan path today and never reaches the speech call
        await self.talk("bir oda tutmak istiyorum", {"asks_for": "room"})
        seen = self.observed()
        self.assertEqual(seen["kese"], 100)
        self.assertEqual((seen["kart"]["max_total_cp"], seen["kart"]["counterparty_label"]), (50, "Marek"))
        self.assertEqual(self.ledger_rows(), [])                          # no payment row

    async def test_asking_for_beer_while_talking_opens_the_counter_offer(self):
        await self.talk("bir bira alabilir miyim", {"asks_for": "goods:bira"})
        seen = self.observed()
        self.assertEqual((seen["kese"], seen["kart"]), (100, None))
        self.assertEqual(seen["tezgah"], {"npc_id": "barman", "key": "bira", "unit_cp": 4, "tip_cp": 0, "total_cp": 4})

    async def test_asks_for_is_ignored_when_money_was_decided(self):
        # the money decision comes from the front reading (deal tip + the coin in the line), Dilim 1 D11; the reply takes it
        await self.talk("al şu 2 bakırı, bir de oda istiyorum",
                        {"asks_for": "room", "coin_answer": "takes", "coin_answer_for": "tip"},
                        front={"kind": "speak_to", "person_id": "barman", "deal": "tip", "coin_cp": 2})
        seen = self.observed()
        self.assertEqual((seen["kese"], seen["kart"]["kalemler"]), (100, ["Bahşiş"]))   # the tip card only, no room line
        self.assertEqual(self.money_decisions_this_turn(), 1)             # one consumer (Dilim 1 D5)

    async def test_a_room_declined_in_the_same_reply_opens_no_room_card(self):
        # J-014 #5, same part: an open room card from the last turn, then one reply that declines the room and asks for it
        await self.talk("bir oda tutmak istiyorum", {"asks_for": "room"})
        self.assertEqual(self.observed()["kart"]["kalemler"], ["Oda (bir gece)"])
        await self.talk("aslında odayı boş ver, yine de bir oda verir misin", {"asks_for": "room", "coin_answer": "declines",
                                                                              "coin_answer_for": "room"})
        seen = self.observed()
        self.assertEqual((seen["kese"], seen["kart"]), (100, None))      # the decline cancels the card, asks_for opens none
        self.assertTrue(economic_actions.declined(self.world, "barman", "room", day=economic_actions.game_day(self.world)))
        self.assertEqual(self.ledger_rows(), [])

    async def test_a_room_decline_with_nothing_listed_is_a_general_decline(self):
        # no card open, no coin: "room" is not among this turn's listed parts → Dilim 1 §3b.2 general decline → no card
        await self.talk("oda istemiyorum ama bir oda lazım", {"asks_for": "room", "coin_answer": "declines", "coin_answer_for": "room"})
        self.assertEqual((self.observed()["kese"], self.observed()["kart"]), (100, None))
        self.assertTrue(economic_actions.declined(self.world, "barman", "*", day=economic_actions.game_day(self.world)))

    async def test_a_tip_declined_in_the_same_reply_still_opens_the_room_card(self):
        # cross part: an open tip card is declined; asks_for room still opens the room card
        await self.talk("al şu 2 bakırı", {"coin_answer": "takes", "coin_answer_for": "tip"},
                        front={"kind": "speak_to", "person_id": "barman", "deal": "tip", "coin_cp": 2})
        self.assertEqual(self.observed()["kart"]["kalemler"], ["Bahşiş"])
        await self.talk("bahşiş istemem, ama oda isterim", {"asks_for": "room", "coin_answer": "declines", "coin_answer_for": "tip"})
        seen = self.observed()
        self.assertEqual((seen["kese"], seen["kart"]["kalemler"], seen["kart"]["max_total_cp"]), (100, ["Oda (bir gece)"], 50))
        self.assertTrue(economic_actions.declined(self.world, "barman", "tip", day=economic_actions.game_day(self.world)))
        self.assertFalse(economic_actions.declined(self.world, "barman", "room", day=economic_actions.game_day(self.world)))

    async def test_takes_without_a_listed_room_keeps_the_earlier_decline(self):
        # karar 64: Dilim 1 §3b — the coin_answer_for list comes only from this turn's money decision and the cards/offers
        # open to that NPC; an answer naming a part that is not listed keeps the decline (rule 4). askable is not that list.
        day = economic_actions.game_day(self.world)
        await self.talk("bir oda tutmak istiyorum", {"asks_for": "room"})
        await self.talk("odayı boş ver", {"coin_answer": "declines", "coin_answer_for": "room"})   # the open room card listed room
        self.assertTrue(economic_actions.declined(self.world, "barman", "room", day=day))
        await self.talk("bir oda tutmak istiyorum", {"asks_for": "room"})                    # declined today: no card
        self.assertEqual(self.observed()["kart"], None)
        self.assertNotIn("room", money_owner.parts_for(self.world, self.session, "barman"))   # no money decision, no open card
        await self.talk("tamam, odayı alıyorum", {"asks_for": "room", "coin_answer": "takes", "coin_answer_for": "room"})
        seen = self.observed()
        self.assertEqual((seen["kese"], seen["kart"], seen["tezgah"]), (100, None, None))   # "room" not listed: decline kept, asks_for blocked
        self.assertTrue(economic_actions.declined(self.world, "barman", "room", day=day))
        self.assertEqual(self.ledger_rows(), [])

    async def test_a_money_offer_for_a_room_declined_today_is_refused_until_the_day_ends(self):
        # Dilim 1 as it is (the money path is not touched): coin held out for a room declined today makes one room
        # decision, whose card is refused before any reply (npc_declined); no coin moves, no ledger row, no card, and
        # no speech call reads a "takes". The decline ends with the game day; then asks_for opens the card again.
        day = economic_actions.game_day(self.world)
        await self.talk("bir oda tutmak istiyorum", {"asks_for": "room"})
        await self.talk("odayı boş ver", {"coin_answer": "declines", "coin_answer_for": "room"})
        prepared = []
        real_prepare = economic_actions.prepare_from_turn

        def seen_prepare(*args, **kwargs):
            result = real_prepare(*args, **kwargs)
            prepared.append((result.status, result.reason_code))
            return result

        with patch.object(economic_actions, "prepare_from_turn", seen_prepare):
            await self.talk("al şu 50 bakırı, odayı tutuyorum",
                            {"asks_for": "room", "coin_answer": "takes", "coin_answer_for": "room"},
                            front={"kind": "speak_to", "person_id": "barman", "coin_cp": 50, "deal": "room"})
        self.assertEqual(prepared, [("refused", "npc_declined")])       # the one room card, refused
        self.assertIsNone(self.last_speech_input)                        # no reply was asked for: no takes is read
        self.assertTrue(economic_actions.declined(self.world, "barman", "room", day=day))
        seen = self.observed()
        self.assertEqual((seen["kese"], seen["kart"], seen["tezgah"]), (100, None, None))
        self.assertEqual(self.ledger_rows(), [])
        self.assertEqual((self.open_cards_to("barman"), self.money_decisions_this_turn()), (0, 1))   # asks_for added nothing
        self.world["campaign_time"]["elapsed_seconds"] = (day + 1) * economic_actions._DAY_SECONDS   # the next game day
        self.assertFalse(economic_actions.declined(self.world, "barman", "room",
                                                   day=economic_actions.game_day(self.world)))
        await self.talk("bir oda tutmak istiyorum", {"asks_for": "room"})
        seen = self.observed()
        self.assertEqual((seen["kese"], seen["kart"]["kalemler"], seen["kart"]["max_total_cp"]),
                         (100, ["Oda (bir gece)"], 50))
        self.assertEqual(self.ledger_rows(), [])

    async def test_asks_for_never_opens_a_second_card_of_the_same_part(self):
        await self.talk("bir oda tutmak istiyorum", {"asks_for": "room"})
        first = self.observed()["kart"]
        await self.talk("bir oda istiyorum dedim", {"asks_for": "room"})
        self.assertEqual(self.observed()["kart"], first)
        self.assertEqual(self.open_cards_to("barman"), 1)

    async def test_asks_for_does_nothing_in_combat_or_when_broken(self):
        for bad in ("room!", 7, None, "goods:yok", "none"):
            with self.subTest(asks_for=bad):
                await self.reset_to_setup()
                await self.talk("bir oda tutmak istiyorum", {"asks_for": bad} if bad is not None else {})
                seen = self.observed()
                self.assertEqual((seen["kese"], seen["kart"], seen["tezgah"]), (100, None, None))
        await self.reset_to_setup(); self.start_fight_here()
        # in a fight the say line itself is refused, nothing applied (the product's own combat rule)
        await self.talk("bir oda tutmak istiyorum", {"asks_for": "room"}, refused="unsupported_interaction_mode")
        self.assertEqual((self.observed()["kese"], self.observed()["kart"]), (100, None))
        # and the opener itself opens nothing in a fight, even for an answer that asked for the room
        result = {"narration": "", "action_result": {"action": "dialogue", "npc_id": "barman"}}
        money_owner.ask_after_reply(self.session, result, ("barman", "room"))
        self.assertEqual((self.observed()["kese"], self.observed()["kart"], self.observed()["tezgah"]), (100, None, None))

    async def test_the_card_still_needs_a_confirmation(self):
        await self.talk("bir oda tutmak istiyorum", {"asks_for": "room"})
        await self.confirm_card()                                         # the economic card's confirm route
        self.assertEqual((self.observed()["kese"], self.observed()["oda"]), (50, True))
        await self.confirm_card(expect_refused=True)                      # a second confirm pays nothing
        self.assertEqual(self.observed()["kese"], 50)
        await self.undo()
        self.assertEqual((self.observed()["kese"], self.observed()["oda"]), (100, False))


if __name__ == "__main__":
    unittest.main()
