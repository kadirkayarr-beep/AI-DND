"""The shield a two-handed weapon put down goes back on the arm in one atomic step (Dilim 4A, Task 5; audit #5).

`gear.don_shield` adds the recorded Armor Class share back and clears `shield_down` together, or changes nothing at all
(two hands full, already worn, shield gone from the bag, no Utilize action in a fight). Save, load and Undo bring the
same state back; a front reading `wield` that names the shield does it through `game._front_wield`."""
from __future__ import annotations

import copy
from unittest.mock import patch

import action_economy
import character_progression
import game
import gear
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase
from api.tests.journeys.schema import load_scenario
from api.tests import test_two_handed_shield_ac as two_handed
from api.tests import test_wield_front as wield_front

BAG = ["Zincir Zırh", "Hançer", "Kalkan", "Greatsword", "Zindan Çantası"]


def _setup(seed):
    setup = copy.deepcopy(load_scenario(SCENARIO_DIR / "05c_greatsword_shield_ac.json").setup)
    setup.update(inventory=list(BAG), campaign_seed=seed, front_proposal=True)
    return setup


class ShieldRedon(JourneyCase):
    # WieldFront's play helpers without its own tests (a subclass would run them all again)
    use_setup = wield_front.WieldFront.use_setup
    session = wield_front.WieldFront.session
    world = wield_front.WieldFront.world
    flag = wield_front.WieldFront.flag
    play = wield_front.WieldFront.play
    say = wield_front.WieldFront.say
    undo = wield_front.WieldFront.undo
    reload = wield_front.WieldFront.reload
    notes = wield_front.WieldFront.notes

    item_id = staticmethod(two_handed.TwoHandedShieldAc.item_id)

    async def fighter(self, seed):
        await self.use_setup(_setup(seed))
        return self.session

    def ids(self, session):
        return {name: self.item_id(session, name) for name in ("Greatsword", "Hançer", "Kalkan")}

    def state(self, session):
        return copy.deepcopy((session.world_state, session.character))

    def touched(self, session):
        """What a shield move may touch, for turns played through the front (the turn counter moves with every line)."""
        world = session.world_state
        return copy.deepcopy((world["inventory"], world["equipment"], world.get("shield_down"),
                              world.get("combat"), session.character))

    async def one_hander_in_hand(self, seed):
        s = await self.fighter(seed)
        ids = self.ids(s)
        self.assertEqual(gear.draw(s.world_state, ids["Greatsword"], character=s.character).status, "drawn")
        self.assertEqual(gear.draw(s.world_state, ids["Hançer"], character=s.character).status, "drawn")
        return s

    async def test_donning_after_a_one_hander_restores_ac_and_clears_the_record(self):
        s = await self.fighter(4741)
        before = s.character["armor_class"]
        gear.draw(s.world_state, self.ids(s)["Greatsword"], character=s.character)
        gear.draw(s.world_state, self.ids(s)["Hançer"], character=s.character)
        low = s.character["armor_class"]
        self.assertLess(low, before)
        hands = copy.deepcopy(s.world_state["equipment"])
        inventory = copy.deepcopy(s.world_state["inventory"])
        result = gear.don_shield(s.world_state, s.character)
        self.assertEqual((result.status, result.item["name"]), ("donned", "Kalkan"))
        self.assertEqual(s.character["armor_class"], before)
        self.assertNotIn("shield_down", s.world_state)
        self.assertEqual((s.world_state["equipment"], s.world_state["inventory"]), (hands, inventory))
        self.assertIsNotNone(character_progression._verified_armor_origin(s.character, s.world_state))

    async def test_two_hands_full_refuses_and_changes_nothing(self):
        s = await self.fighter(4742)
        gear.draw(s.world_state, self.ids(s)["Greatsword"], character=s.character)
        before = self.state(s)
        self.assertEqual(gear.don_shield(s.world_state, s.character).status, "hands_full")
        self.assertEqual(self.state(s), before)
        self.assertIn("shield_down", s.world_state)
        # a one-hander in the main hand and something in the off hand: also full
        gear.draw(s.world_state, self.ids(s)["Hançer"], character=s.character)
        s.world_state["equipment"]["off_hand"] = self.item_id(s, "Zindan Çantası")
        before = self.state(s)
        self.assertEqual(gear.don_shield(s.world_state, s.character).status, "hands_full")
        self.assertEqual(self.state(s), before)

    async def test_donning_twice_adds_once(self):
        s = await self.one_hander_in_hand(4743)
        full = s.character["armor_class"] + s.world_state["shield_down"]["ac_bonus"]
        self.assertEqual(gear.don_shield(s.world_state, s.character).status, "donned")
        after = self.state(s)
        self.assertEqual(gear.don_shield(s.world_state, s.character).status, "not_down")
        self.assertEqual((s.world_state, s.character), after)
        self.assertEqual(s.character["armor_class"], full)

    async def test_no_record_no_shield_down_is_not_down(self):
        s = await self.fighter(4744)                      # shield worn, nothing put down
        before = self.state(s)
        self.assertEqual(gear.don_shield(s.world_state, s.character).status, "not_down")
        self.assertEqual(self.state(s), before)
        # a record whose share was never taken off the total (ac_bonus None) is not "down" either
        gear.draw(s.world_state, self.ids(s)["Hançer"])  # no character given: the record is written, the total stays
        self.assertIsNone(s.world_state.get("shield_down"))  # a one-hander puts no shield down
        gear.draw(s.world_state, self.ids(s)["Greatsword"])  # two-handed without a character: record with ac_bonus None
        self.assertIsNone(s.world_state["shield_down"]["ac_bonus"])
        gear.draw(s.world_state, self.ids(s)["Hançer"])
        before = self.state(s)
        self.assertEqual(gear.don_shield(s.world_state, s.character).status, "not_down")
        self.assertEqual(self.state(s), before)

    async def test_a_total_the_origin_cannot_explain_is_refused_and_nothing_changes(self):
        s = await self.one_hander_in_hand(4745)
        s.character["armor_class"] += 1                    # something else moved the total: the save would not load
        before = self.state(s)
        self.assertEqual(gear.don_shield(s.world_state, s.character).status, "not_down")
        self.assertEqual(self.state(s), before)

    async def test_the_shield_gone_from_the_bag_changes_nothing(self):
        s = await self.one_hander_in_hand(4746)
        s.world_state["inventory"] = [i for i in s.world_state["inventory"] if i["name"] != "Kalkan"]
        before = self.state(s)
        self.assertEqual(gear.don_shield(s.world_state, s.character).status, "no_shield")
        self.assertEqual(self.state(s), before)

    async def test_in_a_fight_it_spends_the_utilize_action_once(self):
        s = await self.one_hander_in_hand(4747)
        full = s.character["armor_class"] + s.world_state["shield_down"]["ac_bonus"]
        npc = s.create_npc_from_ai({"name": "Rakip", "role": "Guard", "location": s.world_state["location"]})
        npc.update(current_hp=40, max_hp=40, armor_class=20, hostile=True, distance_ft=5)
        s.world_state.setdefault("monster_perception", {})[npc["id"]] = {"player": {"visible": True}}
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
            s.start_combat(npc)
        self.assertEqual(s.world_state["combat"]["current_actor_id"], "player")
        resources = action_economy.ensure(s)["player"]
        action_economy.consume_action(s, "player", "attack")         # the turn's action is already gone
        self.assertTrue(resources["base_action_spent"])
        before = self.state(s)
        self.assertEqual(gear.don_shield(s.world_state, s.character, session=s).status, "no_action")
        self.assertEqual(self.state(s), before)       # a refusal writes nothing
        resources["base_action_spent"] = False
        s.world_state["combat"]["actions_used"].remove("player")
        self.assertEqual(gear.don_shield(s.world_state, s.character, session=s).status, "donned")
        self.assertEqual(s.character["armor_class"], full)
        self.assertTrue(action_economy.ensure(s)["player"]["base_action_spent"])
        self.assertEqual(s.world_state["combat"]["actions_used"].count("player"), 1)
        self.assertFalse(action_economy.ensure(s)["player"].get("object_interaction"))   # not the free interaction

    async def test_chain_don_save_load_undo(self):
        s = await self.fighter(4748)
        ids = self.ids(s)
        full = s.character["armor_class"]
        await self.say("büyük kılıcımı çekiyorum", front={"kind": "wield", "item_name": "Greatsword"})
        await self.say("hançerimi çekiyorum", front={"kind": "wield", "item_name": "Hançer"})
        low = self.session.character["armor_class"]
        down = copy.deepcopy(self.world["shield_down"])
        self.assertLess(low, full)
        await self.say("kalkanımı takıyorum", front={"kind": "wield", "item_name": "Kalkan"})
        self.assertEqual(self.session.character["armor_class"], full)
        self.assertNotIn("shield_down", self.world)
        # saved and loaded: the full total follows its origin and no record is needed
        fresh = game.create_session(seed=9)
        restore_campaign_session(fresh, serialize_campaign_payload(self.session))
        self.assertEqual((fresh.character["armor_class"], "shield_down" in fresh.world_state), (full, False))
        # Undo: the total is low again and the record is back, loadable; playing it again adds it once
        await self.undo()
        self.assertEqual(self.session.character["armor_class"], low)
        self.assertEqual(self.world["shield_down"], down)
        self.assertIsNotNone(character_progression._verified_armor_origin(self.session.character, self.world))
        fresh = game.create_session(seed=9)
        restore_campaign_session(fresh, serialize_campaign_payload(self.session))
        self.assertEqual((fresh.character["armor_class"], fresh.world_state["shield_down"]), (low, down))
        await self.say("kalkanımı takıyorum", front={"kind": "wield", "item_name": "Kalkan"})
        self.assertEqual(self.session.character["armor_class"], full)
        await self.reload()                                # a played reload keeps the donned state (Undo is gone then)
        self.assertEqual((self.session.character["armor_class"], "shield_down" in self.world), (full, False))
        self.assertEqual(ids["Kalkan"], self.item_id(self.session, "Kalkan"))

    async def test_a_front_wield_naming_the_shield_dons_it(self):
        s = await self.fighter(4749)
        full = s.character["armor_class"]
        await self.say("büyük kılıcımı çekiyorum", front={"kind": "wield", "item_name": "Greatsword"})
        low = self.session.character["armor_class"]
        before = self.touched(self.session)
        await self.say("kalkanımı takıyorum", front={"kind": "wield", "item_name": "Kalkan"})   # two hands full
        self.assertEqual(self.touched(self.session), before)
        self.assertEqual(self.session.character["armor_class"], low)
        self.assertTrue(any(note.startswith("olmadı:") for _, note in self.notes()), self.notes())
        await self.say("hançerimi çekiyorum", front={"kind": "wield", "item_name": "Hançer"})
        await self.say("kalkanımı takıyorum", front={"kind": "wield", "item_name": "Kalkan"})
        self.assertEqual(self.session.character["armor_class"], full)
        self.assertNotIn("shield_down", self.world)
        self.assertIn((None, "bu tur: Kalkan koluna takıldı"), self.notes())
        self.assertEqual(gear.wielded(self.world)["name"], "Hançer")
        # the shield on the arm already: naming it again is said as nothing changed, not as a missing weapon
        before = self.touched(self.session)
        await self.say("kalkanımı takıyorum", front={"kind": "wield", "item_name": "Kalkan"})
        self.assertEqual(self.touched(self.session), before)
        self.assertEqual(self.notes(), [(None, "bu tur: Kalkan için bir şey değişmedi")])
