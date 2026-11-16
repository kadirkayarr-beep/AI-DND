"""D-097: in a talk with Kavşim, "ona 10 bakır bahşiş veriyorum" answered "Kime vermek istediğini anlayamadım", and a
price question ("ne kadar?") was asked "kime vermek istiyorsun?". 'ona' in an ongoing talk is the one talked to; a
question never opens a coin card; an amount said in the line is never asked again. Scripted reading, real HTTP path."""
import copy
from dataclasses import replace

import economic_actions
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, describe_problems
from api.tests.journeys.schema import load_scenario

TAKES = {"coin_answer": "takes", "coin_answer_for": "unclear"}  # D-096: the person says they take the coin
GREET = {"kind": "speak_to", "person_id": "barman"}
NEVER = [economic_actions._CLARIFY["npc_unknown"], economic_actions._CLARIFY["amount_required"]]


class CoinToTheOneTalkedTo(JourneyCase):
    typed = False
    before_line = None  # a change to the world made just before the line is sent (the talk going stale)

    def _body(self, session_id, step):
        body = super()._body(session_id, step)
        if self.before_line is not None and step.say and step.say != "Marek, selam":
            self.before_line(self.manager.get(session_id).game_session.world_state)
        if self.typed and step.say and step.say != "Marek, selam":
            body.update(interaction_mode="say", target_id="barman")  # the talk panel: the person is chosen
        return body

    async def talk_then(self, line, front, expect, *, speech=None, undo=False, forbid=NEVER):
        source = load_scenario(SCENARIO_DIR / "18_room_phrase_not_job.json")
        setup = copy.deepcopy(source.setup)
        # a second person stands here: 'ona' cannot be read as "the only one here"
        setup["npcs"] = [*setup["npcs"], {"id": "traveller", "name": "Selin", "role": "Yolcu", "current_hp": 10}]
        base = replace(source.steps[0], known_broken=(), broken_because=())
        greet = replace(base, say="Marek, selam", script={"front": GREET}, expect={"kese": 100, "kart": None})
        said = replace(base, say=line, script={"front": front, **({"speech": speech} if speech else {})},
                       expect={"kese": 100, **({"yasak_metin": forbid} if forbid else {}), **expect})
        steps = [greet, said]
        if undo:
            steps += [replace(base, say=None, script=None, undo=True, expect={"kese": 100, "kart": None}),
                      replace(base, say=None, script=None, reload=True, expect={"kese": 100, "kart": None})]
        results = await self.run_scenario(replace(source, setup=setup, steps=tuple(steps)))
        self.assertEqual(describe_problems(results), [])
        return self.manager.get(self.last_session_id).game_session

    async def test_ona_in_a_talk_is_the_one_talked_to(self):
        session = await self.talk_then(
            "ona 10 bakır bahşiş veriyorum",
            {"kind": "speak_to", "person_id": "none", "economic_intent": "tip", "deal": "tip", "coin_cp": 10},
            {"kart": {"max_total_cp": 10, "counterparty_label": "Marek", "kalemler": ["Bahşiş"]}}, speech=TAKES)
        [offer] = session.world_state["flags"]["economic_offers"].values()
        self.assertEqual(offer["proposal"]["recipient_id"], "barman")

    async def test_ona_said_in_the_talk_panel_is_the_person_chosen(self):
        self.typed = True
        await self.talk_then(
            "ona 10 bakır bahşiş veriyorum",
            {"kind": "speak_to", "person_id": "none", "economic_intent": "tip", "deal": "tip", "coin_cp": 10},
            {"kart": {"max_total_cp": 10, "counterparty_label": "Marek", "kalemler": ["Bahşiş"]}}, speech=TAKES)

    async def test_a_price_question_in_the_talk_panel_opens_no_coin_route(self):
        self.typed = True
        await self.talk_then("ne kadar?", {"kind": "speak_to", "person_id": "none", "economic_intent": "purchase"},
                             {"kart": None})

    async def test_an_amount_in_the_line_is_not_asked_again(self):
        # the reading left coin_cp at 0; the line's own "10 bakır" stands, as the words always decide the figure
        await self.talk_then(
            "ona 10 bakır bahşiş veriyorum",
            {"kind": "speak_to", "person_id": "none", "economic_intent": "tip", "deal": "tip", "coin_cp": 0},
            {"kart": {"max_total_cp": 10, "kalemler": ["Bahşiş"]}}, speech=TAKES)

    async def test_the_tip_card_is_undone_and_reload_agrees(self):
        await self.talk_then(
            "ona 10 bakır bahşiş veriyorum",
            {"kind": "speak_to", "person_id": "none", "economic_intent": "tip", "deal": "tip", "coin_cp": 10},
            {"kart": {"max_total_cp": 10, "kalemler": ["Bahşiş"]}}, speech=TAKES, undo=True)

    async def test_a_price_question_opens_no_coin_route(self):
        for line, purpose in (("ne kadar?", "purchase"), ("bira ne kadar?", "purchase"), ("ne kadar?", "tip"),
                              ("ona bahşiş versem mi?", "tip")):
            with self.subTest(line=line, purpose=purpose):
                await self.talk_then(line, {"kind": "speak_to", "person_id": "none", "economic_intent": purpose},
                                     {"kart": None})

    async def test_with_nobody_talked_to_ona_is_still_asked(self):
        # no ongoing talk and two people here: nobody is guessed, the old question stands (no card opens on a guess)
        source = load_scenario(SCENARIO_DIR / "18_room_phrase_not_job.json")
        setup = copy.deepcopy(source.setup)
        setup["npcs"] = [*setup["npcs"], {"id": "traveller", "name": "Selin", "role": "Yolcu", "current_hp": 10}]
        step = replace(source.steps[0], say="ona 10 bakır bahşiş veriyorum", known_broken=(), broken_because=(),
                       script={"front": {"kind": "speak_to", "person_id": "none", "economic_intent": "tip",
                                         "deal": "tip", "coin_cp": 10}},
                       expect={"kese": 100, "kart": None,
                               "gerekli_metin": [economic_actions._CLARIFY["npc_unknown"]]})
        results = await self.run_scenario(replace(source, setup=setup, steps=(step,)))
        self.assertEqual(describe_problems(results), [])


class ReviewCases(CoinToTheOneTalkedTo):
    """Independent review of D-097 (Opus): the cases the first fix let through."""
    ASKS_WHO = [economic_actions._CLARIFY["npc_unknown"]]

    async def test_a_line_naming_another_person_is_not_bound_to_the_one_talked_to(self):
        # talking to Marek, "Selin'e 10 bakır" with no person in the reading: never a card for Marek; asked as before
        session = await self.talk_then(
            "Selin'e 10 bakır bahşiş veriyorum",
            {"kind": "speak_to", "person_id": "none", "economic_intent": "tip", "deal": "tip", "coin_cp": 10},
            {"kart": None, "gerekli_metin": self.ASKS_WHO}, speech=TAKES, forbid=None)
        self.assertEqual((session.world_state.get("flags") or {}).get("economic_offers") or {}, {})

    async def test_a_talk_gone_stale_is_not_used(self):
        # the one talked to walked off, or lies dead: 'ona' has nobody to be bound to, and nobody is guessed
        def walked_off(world):
            next(n for n in world["npcs"] if n["id"] == "barman")["location"] = "somewhere-else"

        def died(world):
            next(n for n in world["npcs"] if n["id"] == "barman").update(current_hp=0, combat_status="dead")

        for change in (walked_off, died):
            with self.subTest(change=change.__name__):
                self.before_line = change
                session = await self.talk_then(
                    "ona 10 bakır bahşiş veriyorum",
                    {"kind": "speak_to", "person_id": "none", "economic_intent": "tip", "deal": "tip", "coin_cp": 10},
                    {"kart": None, "gerekli_metin": self.ASKS_WHO}, speech=TAKES, forbid=None)
                self.assertEqual((session.world_state.get("flags") or {}).get("economic_offers") or {}, {})
        self.before_line = None

    async def test_a_tip_asked_about_with_an_amount_and_no_question_mark_opens_no_card(self):
        # the person would take it (TAKES), so only the question itself keeps the card shut
        await self.talk_then(
            "ona 10 bakır bahşiş versem mi",
            {"kind": "speak_to", "person_id": "none", "economic_intent": "tip", "deal": "tip", "coin_cp": 10},
            {"kart": None}, speech=TAKES)

    async def test_a_buy_with_a_price_question_still_buys(self):
        # "bir bira alayım, ne kadar?" names the goods and the buying: the counter takes it (no coin moves)
        session = await self.talk_then(
            "bir bira alayım, ne kadar?", {"kind": "speak_to", "person_id": "barman", "economic_intent": "purchase"},
            {"kart": None})
        self.assertIn("counter_offer_v1", session.world_state["flags"])

    async def test_a_minus_signed_amount_is_no_amount(self):
        # "-10 bakır" is no figure to hold out: no card for 10 opens; the amount is asked
        await self.talk_then(
            "ona -10 bakır bahşiş veriyorum",
            {"kind": "speak_to", "person_id": "none", "economic_intent": "tip", "deal": "tip", "coin_cp": 0},
            {"kart": None, "gerekli_metin": [economic_actions._CLARIFY["amount_required"]]}, speech=TAKES, forbid=None)

    async def test_a_thing_given_as_a_gift_is_not_asked_a_coin_amount(self):
        await self.talk_then(
            "ona hançerimi hediye ediyorum",
            {"kind": "speak_to", "person_id": "none", "economic_intent": "gift", "deal": "gift"}, {"kart": None})


for _name in [name for name in dir(CoinToTheOneTalkedTo) if name.startswith("test_")]:
    setattr(ReviewCases, _name, None)  # the first class runs its own cases once
