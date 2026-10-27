"""K02: damage mitigation is applied once, by the shared owner, for every damage producer.

Inner Radiance (a species producer) used to compute its own resistance and ignored immunity and vulnerability.
The independent oracle below is hand-computed from the 2024 order of operations (immunity -> resistance halves, rounded
down -> vulnerability doubles), not read back from the engine.
"""
from __future__ import annotations

import unittest

import weapon_attack
from api.tests import test_death_system as fixtures

PROFICIENCY = 4  # large enough that a second halving would be visible (4 -> 2 -> 1)


def oracle(amount, *, immune=False, resistant=False, vulnerable=False):
    if immune:
        return 0
    if resistant:
        amount //= 2
    if vulnerable:
        amount *= 2
    return amount


def radiance_session(proficiency=PROFICIENCY):
    session = fixtures.make_session()
    session.character.update(species="Aasimar", race="Aasimar", proficiency_bonus=proficiency, level=3)
    session.initialize_species_trait_state()
    session._species_trait_state().update(active_celestial_form="inner_radiance", celestial_revelation_turns_remaining=10)
    return session


def target(session, target_id, **facts):
    npc = {"id": target_id, "current_hp": 10, "max_hp": 10, "combat_status": "active",
           "location": session.world_state["location"], "distance_ft": 5}
    npc.update(facts)
    session.world_state["npcs"].append(npc)
    return npc


class SharedMitigationTests(unittest.TestCase):
    CASES = {
        "normal": {}, "resistant": {"resistances": ["radiant"]}, "immune": {"immunities": ["radiant"]},
        "vulnerable": {"vulnerabilities": ["radiant"]},
        "resistant_and_vulnerable": {"resistances": ["radiant"], "vulnerabilities": ["radiant"]},
    }
    FLAGS = {"normal": {}, "resistant": {"resistant": True}, "immune": {"immune": True}, "vulnerable": {"vulnerable": True},
             "resistant_and_vulnerable": {"resistant": True, "vulnerable": True}}

    def test_all_damage_producers_share_mitigation(self):
        session = radiance_session()
        npcs = {name: target(session, name, **facts) for name, facts in self.CASES.items()}
        effects = session._finish_species_player_turn()
        by_target = {effect["target_id"]: effect for effect in effects if effect["target_id"] != "player"}
        results = {name: 10 - npc["current_hp"] for name, npc in npcs.items()}
        obs = {
            "radiant_immune_hp_before": 10,
            "radiant_immune_hp_after": npcs["immune"]["current_hp"],
            # the resistant-only case would read 1 (4 -> 2 -> 1) if resolved damage were reduced a second time
            "resolved_damage_mitigated_twice": results["resistant"] != oracle(PROFICIENCY, resistant=True),
            "producer_results": results,
            "independent_rule_oracles": {name: oracle(PROFICIENCY, **flags) for name, flags in self.FLAGS.items()},
        }
        self.assertEqual(obs["radiant_immune_hp_before"], 10)
        self.assertEqual(obs["radiant_immune_hp_after"], 10)
        self.assertIs(obs["resolved_damage_mitigated_twice"], False)
        self.assertEqual(obs["producer_results"], obs["independent_rule_oracles"])
        for name in self.CASES:
            self.assertIn("mitigation", by_target[name], "the effect result carries its sourced mitigation breakdown")
            self.assertEqual(by_target[name]["mitigation"]["final_damage"], oracle(PROFICIENCY, **self.FLAGS[name]))

    def test_the_weapon_owner_matches_the_same_oracle(self):
        session = radiance_session()
        for name, facts in self.CASES.items():
            npc = target(session, f"agree-{name}", **facts)
            actual = weapon_attack.mitigate(session, npc["id"], "radiant", PROFICIENCY)["final_damage"]
            self.assertEqual(actual, oracle(PROFICIENCY, **self.FLAGS[name]), name)

    def test_odd_amounts_pin_the_order_of_application(self):
        # PHB 2024 (PDF p.27, "Order of Application"): flat adjustments, then Resistance (halve, round down), then Vulnerability
        # (double). 3 -> 1 -> 2 is the only order that gives 2; doubling first would give 3, halving twice 0.
        for proficiency in (3, 5):  # 10 HP targets: a larger vulnerable hit would just clamp at 0
            with self.subTest(proficiency=proficiency):
                session = radiance_session(proficiency)
                npcs = {name: target(session, name, **facts) for name, facts in self.CASES.items()}
                session._finish_species_player_turn()
                for name, npc in npcs.items():
                    self.assertEqual(10 - npc["current_hp"], oracle(proficiency, **self.FLAGS[name]), name)
        self.assertEqual(oracle(3, resistant=True, vulnerable=True), 2)
        self.assertEqual(oracle(5, resistant=True, vulnerable=True), 4)

    def test_inner_radiance_reaches_only_creatures_within_ten_feet(self):
        # PHB 2024 PDF p.185: "each creature within 10 feet of you takes Radiant damage" (allies are not excluded).
        session = radiance_session()
        near = target(session, "near", distance_ft=10)
        ally = target(session, "ally", combat_side="party")
        far = target(session, "far", distance_ft=11)
        unknown = target(session, "unknown")
        del unknown["distance_ft"]
        session._finish_species_player_turn()
        self.assertEqual([10 - near["current_hp"], 10 - ally["current_hp"]], [PROFICIENCY, PROFICIENCY])
        self.assertEqual((far["current_hp"], unknown["current_hp"]), (10, 10))

    def test_every_npc_damage_caller_mitigates_first(self):
        import pathlib
        import re
        root = pathlib.Path(__file__).resolve().parents[2]
        for name in ("game.py", "weapon_attack.py", "spell_scope.py", "exploration.py"):
            lines = (root / name).read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if re.search(r"\bapply_npc_damage\(", line) and not line.lstrip().startswith("def "):
                    window = "\n".join(lines[max(0, index - 40):index])
                    self.assertRegex(window, r"mitigate\(", f"{name}:{index + 1} applies NPC damage without the shared mitigation")

    def test_a_dead_or_other_scene_creature_is_not_damaged(self):
        session = radiance_session()
        dead = target(session, "dead", combat_status="dead", current_hp=0)
        elsewhere = target(session, "elsewhere", location="harbour")
        session._finish_species_player_turn()
        self.assertEqual((dead["current_hp"], elsewhere["current_hp"]), (0, 10))


if __name__ == "__main__":
    unittest.main()
