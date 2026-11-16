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

    def _body(self, session_id, step):
        body = super()._body(session_id, step)
        if self.typed and step.say and step.say != "Marek, selam":
            body.update(interaction_mode="say", target_id="barman")  # the talk panel: the person is chosen
        return body

    async def talk_then(self, line, front, expect, *, speech=None, undo=False):
        source = load_scenario(SCENARIO_DIR / "18_room_phrase_not_job.json")
        setup = copy.deepcopy(source.setup)
        # a second person stands here: 'ona' cannot be read as "the only one here"
        setup["npcs"] = [*setup["npcs"], {"id": "traveller", "name": "Selin", "role": "Yolcu", "current_hp": 10}]
        base = replace(source.steps[0], known_broken=(), broken_because=())
        greet = replace(base, say="Marek, selam", script={"front": GREET}, expect={"kese": 100, "kart": None})
        said = replace(base, say=line, script={"front": front, **({"speech": speech} if speech else {})},
                       expect={"kese": 100, "yasak_metin": NEVER, **expect})
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
