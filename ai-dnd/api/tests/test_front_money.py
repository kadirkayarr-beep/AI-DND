"""Dilim 1, Task 5: the front reading carries the deal fields, lists the vendor's goods and reads a say-mode line
only when it names coin.

The model proposes what the coin is for (`deal`, `deal_goods`, `keep_change`); Python never reads a figure from it.
A say-mode line that names no coin spends no model call; one that does is read for its coin alone, and is still
said to the person the player chose.
"""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

import front_proposal
import game
import interaction_adventure
from api.tests import test_front_proposal as front_tests
from api.tests.journeys.runner import call_kind
from api.tests.test_front_carries_more import ProposalClient

GOODS = [{"id": "bira", "name": "bira"}, {"id": "sarap", "name": "şarap"}, {"id": "yemek", "name": "tabak yemek"}]
LISTED = {"people": [{"id": "npc_a", "name": "A"}], "places": [], "things": [], "offers": [], "bag": [],
          "parcels": [], "jobs": [], "wants": [], "goods": GOODS, "speaking_with": "npc_a"}


class KindsClient(front_tests.FrontClient):
    """The front client, also keeping the kind of every model call the turn made."""

    def __init__(self):
        super().__init__()
        self.kinds = []

    def chat(self, *args, **kwargs):
        self.kinds.append(call_kind(kwargs.get("format")) or "other")
        return super().chat(*args, **kwargs)


class Table(unittest.IsolatedAsyncioTestCase):
    """The front table's helpers (test_front_proposal.FrontTable), without its own tests."""

    asyncSetUp = front_tests.FrontTable.asyncSetUp
    asyncTearDown = front_tests.FrontTable.asyncTearDown
    campaign_with_npc = front_tests.FrontTable.campaign_with_npc
    open_job = front_tests.FrontTable.open_job
    begin = front_tests.FrontTable.begin
    routes = front_tests.FrontTable.routes
    a_place = front_tests.FrontTable.a_place


class TheSchemaAndTheClauses(unittest.TestCase):
    def test_deal_fields_sit_right_after_kind(self):
        self.assertEqual(list(front_proposal.schema(LISTED)["properties"])[:4],
                         ["kind", "deal", "deal_goods", "keep_change"])

    def test_the_deal_fields_offer_only_listed_choices_and_are_always_asked(self):
        schema = front_proposal.schema(LISTED)
        self.assertEqual(schema["properties"]["deal"]["enum"], ["goods", "room", "tip", "gift", "paid_before", "none"])
        self.assertEqual(schema["properties"]["deal_goods"]["enum"], ["bira", "sarap", "yemek", "none"])
        self.assertEqual(schema["properties"]["keep_change"], {"type": "boolean"})
        self.assertTrue({"deal", "deal_goods", "keep_change"} <= set(schema["required"]))

    def test_no_goods_listed_leaves_only_none(self):
        self.assertEqual(front_proposal.schema({**LISTED, "goods": []})["properties"]["deal_goods"]["enum"], ["none"])

    def test_the_guidance_names_each_deal_field(self):
        text = front_proposal.guidance(LISTED)
        for field in ("deal:", "deal_goods:", "keep_change:"):
            self.assertIn(field, text)

    def test_a_reading_without_deal_fields_still_validates(self):
        bare = {"front": {"kind": "speak_to", "person_id": "npc_a"}}
        dealt = {"front": {"kind": "speak_to", "person_id": "npc_a", "deal": "goods", "deal_goods": "bira",
                           "keep_change": True}}
        self.assertEqual(front_proposal.validate(bare, LISTED), {"kind": "speak_to", "id": "npc_a"})
        self.assertEqual(front_proposal.validate(dealt, LISTED), {"kind": "speak_to", "id": "npc_a"})

    def test_names_coin_follows_the_coin_in_clauses(self):
        self.assertTrue(front_proposal.names_coin("Oda için beş gümüş ödüyorum"))
        self.assertFalse(front_proposal.names_coin("bi altın versem, bira verir misin?"))
        self.assertFalse(front_proposal.names_coin("Akşam kalabalık olur mu?"))

    def test_names_coin_agrees_with_coin_in_on_every_line(self):
        reading = {"front": {"coin_cp": 7}}
        for line in ("Oda için beş gümüş ödüyorum", "bi altın versem, bira verir misin?", "Akşam kalabalık olur mu?",
                     "bi altın atıyorum, ne olduğunu anlat bakalım?", "bende bi altın var, nereye harcasam?",
                     "beş gümüş vermiyorum", "biraz para bırakıyorum masaya", "selam"):
            self.assertEqual(front_proposal.names_coin(line), front_proposal.coin_in(reading, line) > 0, line)


class TheGoodsOnTheList(Table):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.begin()
        self.sera = next(npc for npc in self.world["npcs"] if npc["id"] == "npc_private_sera")

    def listed(self):
        """The listing as a turn sees it: the engine reads people through the session it is running."""
        token = game._ACTIVE_SESSION.set(self.session)
        try:
            return front_proposal.listing(self.session)
        finally:
            game._ACTIVE_SESSION.reset(token)

    def test_the_listing_names_the_vendors_goods(self):
        self.npc["role"] = "barmen"
        listed = self.listed()
        self.assertEqual(listed["speaking_with"], self.npc["id"])
        self.assertEqual(listed["goods"], [{"id": "bira", "name": "bira"}, {"id": "sarap", "name": "şarap"},
                                           {"id": "yemek", "name": "tabak yemek"}])

    def test_the_one_vendor_here_lists_when_the_talk_is_with_someone_else(self):
        self.sera["role"] = "garson"
        self.assertEqual(self.listed()["goods"], GOODS)

    def test_two_vendors_and_neither_spoken_to_list_nothing(self):
        self.sera["role"] = "garson"
        self.world["npcs"].append({**self.sera, "id": "npc_second_server", "name": "Lida"})
        listed = self.listed()
        self.assertIn("npc_second_server", [row["id"] for row in listed["people"]])
        self.assertEqual(listed["goods"], [])

    def test_the_vendor_spoken_to_lists_even_beside_another(self):
        self.npc["role"] = "barmen"
        self.sera["role"] = "garson"
        self.world["npcs"].append({**self.sera, "id": "npc_second_server", "name": "Lida"})
        self.assertEqual(self.listed()["goods"], GOODS)

    def test_a_vendor_elsewhere_lists_nothing(self):
        self.sera["role"] = "garson"
        self.sera["location"] = "elsewhere"
        self.assertEqual(self.listed()["goods"], [])

    def test_nobody_selling_lists_nothing(self):
        self.assertEqual(self.listed()["goods"], [])


class SayModeCoin(Table):
    async def begin(self, **kwargs):
        await super().begin(**kwargs)
        self.client = KindsClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.npc["role"] = "barmen"
        self.people = {"barman": self.npc}

    async def say_to(self, who, line):
        """One say-mode turn to that person; the coin the reading saw is kept before the turn clears it."""
        self.client.kinds = []
        self.front_coin = None
        clear = game._clear_turn_transients

        def keep_then_clear(session):  # the turn clears first; the request clears again after it
            if self.front_coin is None:
                self.front_coin = getattr(session, "_front_coin", 0)
            clear(session)

        body = {"message": line, "interaction_mode": "say", "target_id": self.people[who]["id"],
                "action_id": str(uuid.uuid4())}
        with patch.object(game, "_clear_turn_transients", keep_then_clear):
            response = await self.http.post(self.turn_url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_say_mode_reads_only_a_line_that_names_coin(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 50, "deal": "room",
                             "deal_goods": "none", "keep_change": False}
        await self.say_to("barman", "Akşam kalabalık olur mu?")
        self.assertNotIn("front", self.client.kinds)
        self.assertEqual(self.routes()[-1]["route"], "skipped:typed")
        await self.say_to("barman", "Oda için beş gümüş ödüyorum")
        self.assertIn("front", self.client.kinds)
        self.assertEqual(self.front_coin, 50)
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")

    async def test_the_coin_reading_stays_within_the_turns_call_cap(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 50, "deal": "room"}
        await self.say_to("barman", "Oda için beş gümüş ödüyorum")
        self.assertEqual(self.client.kinds.count("front"), 1)
        self.assertNotIn("intent", self.client.kinds)  # the reading is this turn's classifier call
        self.assertLessEqual(len(self.client.kinds), 2)

    async def test_the_coin_line_stays_with_the_chosen_person_whatever_else_was_read(self):
        await self.begin()
        here = self.world["location"]
        self.client.front = {"kind": "go_to", "place_id": self.a_place(), "person_id": "npc_private_sera",
                             "coin_cp": 50, "deal": "room", "deed": "steal", "threat_to": "npc_private_sera"}
        with patch("world_happenings.threatened") as threatened:
            await self.say_to("barman", "Oda için beş gümüş ödüyorum")
        threatened.assert_not_called()
        self.assertEqual(self.world["location"], here)
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")
        self.assertEqual(self.front_coin, 50)
        self.assertFalse(self.session._front_deed)

    async def test_a_coin_line_to_nobody_typed_is_not_a_say_mode_reading(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 50}
        response = await self.http.post(self.turn_url, json={"message": "Oda için beş gümüş ödüyorum",
                                                             "interaction_mode": "ask_dm",
                                                             "action_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("front", self.client.kinds)


class ProposalKindsClient(ProposalClient):
    """The reading also carries the interaction half (as the real schema asks), and every call's kind is kept."""

    def __init__(self):
        super().__init__()
        self.kinds = []

    def chat(self, *args, **kwargs):
        self.kinds.append(call_kind(kwargs.get("format")) or "other")
        return super().chat(*args, **kwargs)


class SayModeCoinKeepsTheTalk(Table):
    """A say-mode coin line's later proposal step reuses the reading (the turn's classifier call): it behaves as a
    free line the reading gave to the same person does (test_front_carries_more, test_front_voice), never worse.

    The person spoken to is Sera, who has no job open: a coin line to the job's owner is taken as talk about the
    job by the thread gate (D57, Task 6), which keeps any proposal out of that turn with or without the reading."""

    say_to = SayModeCoin.say_to

    async def begin(self, **kwargs):
        await super().begin(**kwargs)
        self.client = ProposalKindsClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.npc = next(npc for npc in self.world["npcs"] if npc["id"] == "npc_private_sera")
        self.people = {"kişi": self.npc}
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 50, "deal": "room",
                             "deal_goods": "none", "keep_change": False}

    def promise(self, line, addressee):
        self.client.interaction = {
            "operation": "promise", "quote": line, "privacy": "addressed",
            "conversation": {"addressee_id": addressee, "subject_phrase": "", "subject_role": "unknown",
                             "meaning": "unknown", "topic_relation": "new", "candidate_evidence_ids": []}}

    def assert_one_reading(self):
        self.assertEqual(self.client.kinds.count("front"), 1)
        self.assertNotIn("intent", self.client.kinds)  # the proposal step asked no second classifier call
        self.assertLessEqual(len(self.client.kinds), 2)
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")
        self.assertEqual(self.front_coin, 50)

    async def test_a_promise_with_coin_said_to_the_person_is_recorded_from_the_one_reading(self):
        await self.begin()
        line = "Söz veriyorum oda için beş gümüş ödüyorum"
        self.assertEqual(interaction_adventure.hint(line, self.npc), "promise")
        self.promise(line, self.npc["id"])
        reply = await self.say_to("kişi", line)
        self.assert_one_reading()
        self.assertEqual(reply["turn_outcome"]["status"], "recorded")

    async def test_a_reading_that_left_the_promise_unusable_lets_the_chosen_person_answer(self):
        await self.begin()
        line = "Söz veriyorum oda için beş gümüş ödüyorum"
        self.promise(line, None)
        self.client.narration = "Görürüz bakalım."
        reply = await self.say_to("kişi", line)
        self.assert_one_reading()
        self.assertIn("Görürüz bakalım.", reply["narration"])
        self.assertNotEqual(reply["turn_outcome"]["status"], "recorded")

    async def test_two_clauses_with_coin_said_to_the_person_get_the_person_and_keep_no_plan(self):
        await self.begin()
        line = "Oda için beş gümüş ödüyorum, sonra yukarı çıkıyorum"
        self.assertEqual(interaction_adventure.hint(line, self.npc), "plan")
        self.client.interaction = {"operation": "plan", "quote": line, "privacy": "private",
                                   "steps": [{"quote": "Oda için beş gümüş ödüyorum", "depends_on": None,
                                              "precondition": ""},
                                             {"quote": "sonra yukarı çıkıyorum", "depends_on": 0,
                                              "precondition": ""}]}
        self.client.narration = "Anahtar tezgâhta."
        reply = await self.say_to("kişi", line)
        self.assert_one_reading()
        self.assertIn("Anahtar tezgâhta.", reply["narration"])
        self.assertFalse(((self.world.get(interaction_adventure.KEY) or {}).get("plan")))

    async def test_a_say_line_without_coin_keeps_its_own_proposal_call(self):
        await self.begin()
        line = "Söz veriyorum yarın geri gelirim"
        self.assertFalse(front_proposal.names_coin(line))
        await self.say_to("kişi", line)
        self.assertNotIn("front", self.client.kinds)  # no reading: the old proposal step asks the model itself
        self.assertIn("intent", self.client.kinds)
        self.assertEqual(self.routes()[-1]["route"], "skipped:typed")


class TheTurnStartsClean(unittest.TestCase):
    def test_begin_clears_the_money_fields_of_the_last_turn(self):
        class Session:
            world_state = {}
        session = Session()
        session._coin_decision = object()
        session._coin_answer = "declines"
        session._coin_answer_for = "tip"
        session._coin_claimed = True
        session._turn_notes = [(None, "eski not")]
        front_proposal.begin(session)
        self.assertIsNone(session._coin_decision)
        self.assertIsNone(session._coin_answer)
        self.assertIsNone(session._coin_answer_for)
        self.assertIs(session._coin_claimed, False)
        self.assertEqual(session._turn_notes, [])


if __name__ == "__main__":
    unittest.main()
