"""4A.3 Dodge: a dodging target that sees its attacker imposes Disadvantage in plain town fights too."""
from __future__ import annotations

import unittest

import action_economy
import game
import weapon_attack
from api.tests import test_combat_lifecycle as lifecycle
from api.tests.town_seed import fixed_town


class DodgeNeedsASeenAttacker(unittest.TestCase):
    def fight(self, seed=4721):
        with fixed_town(self, seed):
            session, npc = lifecycle.ready()
        token = game._ACTIVE_SESSION.set(session)
        self.addCleanup(game._ACTIVE_SESSION.reset, token)
        return session, npc

    def blows_after_dodge(self, session):
        action_economy.execute(session, {"steps": [{"kind": "dodge"}]})
        result = action_economy.execute(session, {"steps": [{"kind": "end_turn"}]})
        return [e for s in result["action_result"]["economy_steps"] for e in s.get("enemy_actions") or []
                if e.get("action") == "enemy_attack"]

    def sources(self, session):
        blows = self.blows_after_dodge(session)
        self.assertTrue(blows)
        return blows[0]["disadvantage_sources"]

    def test_a_town_fight_dodge_gives_disadvantage_to_the_seen_attacker(self):
        session, npc = self.fight(4721)
        self.assertIn("target_dodging", self.sources(session))

    def test_blinded_player_gets_no_dodge_disadvantage(self):
        session, npc = self.fight(4722)
        session.character["conditions"] = ["blinded"]
        self.assertNotIn("target_dodging", self.sources(session))

    def test_invisible_attacker_not_seen_no_disadvantage(self):
        session, npc = self.fight(4723)
        npc["conditions"] = ["invisible"]
        self.assertNotIn("target_dodging", self.sources(session))

    def test_hidden_attacker_not_seen_no_disadvantage(self):
        session, npc = self.fight(4724)
        npc["hidden"] = True
        self.assertNotIn("target_dodging", self.sources(session))

    def test_incapacitated_dodger_gets_none(self):
        session, npc = self.fight(4725)
        action_economy.execute(session, {"steps": [{"kind": "dodge"}]})
        self.assertTrue(action_economy.ensure(session)["player"]["dodging"])
        session.character["conditions"] = ["incapacitated"]
        result = action_economy.execute(session, {"steps": [{"kind": "end_turn"}]})
        blows = [e for s in result["action_result"]["economy_steps"] for e in s.get("enemy_actions") or []
                 if e.get("action") == "enemy_attack"]
        self.assertTrue(blows)
        self.assertNotIn("target_dodging", blows[0]["disadvantage_sources"])

    def test_an_explicit_false_from_the_bounded_encounter_wins(self):
        session, npc = self.fight(4726)
        session.world_state.setdefault("attack_environment", {}).setdefault("pairs", {})[f"{npc['id']}|player"] = {
            "distance_ft": 5, "attacker_sees_target": True, "target_sees_attacker": False}
        self.assertFalse(weapon_attack.target_sees_attacker(session, npc["id"], "player"))
        self.assertNotIn("target_dodging", self.sources(session))

    def test_the_derived_fact_is_never_written_to_the_pair(self):
        session, npc = self.fight(4727)
        before = repr(session.world_state.get("attack_environment"))
        self.assertTrue(weapon_attack.target_sees_attacker(session, npc["id"], "player"))
        self.sources(session)
        self.assertNotIn("target_sees_attacker", repr(session.world_state.get("attack_environment")))
        self.assertEqual(before, repr(session.world_state.get("attack_environment")))

    def test_dodge_loss_when_the_turn_comes_again(self):
        session, npc = self.fight(4728)
        self.assertIn("target_dodging", self.sources(session))
        # The player's next turn has begun: 'dodging' is cleared, so the following blow has no Disadvantage.
        self.assertFalse(action_economy.ensure(session)["player"].get("dodging"))
        result = action_economy.execute(session, {"steps": [{"kind": "end_turn"}]})
        blows = [e for s in result["action_result"]["economy_steps"] for e in s.get("enemy_actions") or []
                 if e.get("action") == "enemy_attack"]
        self.assertTrue(blows)
        self.assertNotIn("target_dodging", blows[0]["disadvantage_sources"])

    def test_monster_against_monster_pair_is_derived_the_same_way(self):
        session, npc = self.fight(4729)
        other = session.create_npc_from_ai({"name": "Ikinci", "role": "Guard", "location": "tavern"})
        self.assertTrue(weapon_attack.target_sees_attacker(session, npc["id"], other["id"]))
        other["conditions"] = ["blinded"]
        self.assertFalse(weapon_attack.target_sees_attacker(session, npc["id"], other["id"]))


if __name__ == "__main__":
    unittest.main()


class HiddenPlayerIsNotSeen(DodgeNeedsASeenAttacker):
    test_a_town_fight_dodge_gives_disadvantage_to_the_seen_attacker = None
    test_blinded_player_gets_no_dodge_disadvantage = test_invisible_attacker_not_seen_no_disadvantage = None
    test_hidden_attacker_not_seen_no_disadvantage = test_incapacitated_dodger_gets_none = None
    test_an_explicit_false_from_the_bounded_encounter_wins = test_the_derived_fact_is_never_written_to_the_pair = None

    def test_a_hidden_player_is_not_seen_by_the_dodging_target(self):
        session, npc = self.fight(4728)
        self.assertTrue(weapon_attack.target_sees_attacker(session, "player", npc["id"]))
        session.world_state.setdefault("flags", {})["player_hidden"] = True
        self.assertFalse(weapon_attack.target_sees_attacker(session, "player", npc["id"]))
