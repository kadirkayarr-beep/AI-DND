"""Dilim 4C Task 0 (G1): the surrendered state through the real routes (scenario 44's setup, scripted model, fixed
campaign seed): surrender accepted -> Undo -> the same acceptance again -> save/load -> one effect, one XP each."""
from __future__ import annotations

import copy
from unittest.mock import patch

import monster_combat
from api.tests import test_dilim4b_combat_xp as t1
from api.tests import test_wield_front as wield_front
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase
from api.tests.journeys.schema import load_scenario

ACCEPT = "Teslim olma teklifini kabul ediyorum."


class SurrenderRoutes(JourneyCase):
    use_setup = wield_front.WieldFront.use_setup
    session = wield_front.WieldFront.session
    world = wield_front.WieldFront.world
    flag = wield_front.WieldFront.flag
    play = wield_front.WieldFront.play
    say = wield_front.WieldFront.say
    undo = wield_front.WieldFront.undo
    reload = wield_front.WieldFront.reload

    def record(self, identity):
        return next(r for r in self.world["combat"]["participant_records"] if r["id"] == identity)

    def proposals(self):
        return self.world["monster_combat"]["actors"]["guard"]["proposals"]

    async def two_foes_and_an_offer(self, seed):
        setup = copy.deepcopy(load_scenario(SCENARIO_DIR / "44_savas_xp_bir_kez.json").setup)
        setup["campaign_seed"] = seed
        await self.use_setup(setup)
        await self.say("Muhafıza saldırıyorum", intent=t1.ATTACK)
        self.assertTrue(self.world["combat"]["active"])
        self.assertEqual(self.world["combat"]["current_actor_id"], "player")
        brute = t1.person("brute1", "muhafız", distance_ft=5, location=self.world["location"])
        self.world["npcs"].append(brute)
        with patch("game.roll_initiative", return_value=1):
            self.session.join_combat_participants(["brute1"])
        memory = monster_combat.state(self.session, "guard")
        cid = self.world["combat"]["combat_id"]
        memory.setdefault("proposals", []).append(
            {"proposal_id": f"{cid}:1:guard:0:SURRENDER_PROPOSED", "type": "SURRENDER_PROPOSED",
             "status": "pending", "actor_id": "guard"})

    async def test_accept_save_load_undo_replay_is_one_surrender_and_one_payment(self):
        await self.two_foes_and_an_offer(4820)
        await self.say(ACCEPT)
        self.assertTrue(self.world["combat"]["active"])
        self.assertEqual(self.record("guard")["status"], "surrendered")
        self.assertEqual(self.record("brute1")["status"], "active")
        await self.undo()  # Undo is offered only for the live session's last turn (a reloaded one answers undo_unavailable)
        self.assertTrue(self.world["combat"]["active"])
        self.assertEqual([p["status"] for p in self.proposals()], ["pending"])
        self.assertEqual(self.record("guard")["status"], "active")
        await self.say(ACCEPT)
        self.assertEqual([p["status"] for p in self.proposals()], ["accepted"])
        self.assertEqual(self.record("guard")["status"], "surrendered")
        self.assertEqual(self.session.character["xp"], 0)
        await self.reload()
        self.assertEqual(self.record("guard")["status"], "surrendered")
        brute = next(n for n in self.world["npcs"] if n["id"] == "brute1")
        brute.update(current_hp=0, combat_status="dead")
        self.assertEqual(self.session._combat_end_if_decided()["reason"], "target_defeated")
        self.assertEqual(self.session.character["xp"], 50)
        self.assertEqual(sorted(self.world["xp_awarded_event_ids"]), ["combat:foe:brute1", "combat:foe:guard"])
        await self.say("etrafa bakıyorum")  # the ending is written by a turn's save
        await self.reload()
        self.assertEqual((self.session.character["xp"], sorted(self.world["xp_awarded_event_ids"])),
                         (50, ["combat:foe:brute1", "combat:foe:guard"]))
