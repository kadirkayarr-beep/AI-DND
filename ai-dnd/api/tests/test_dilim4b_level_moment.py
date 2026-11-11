"""Dilim 4B Task 5: the level-up moment. Python writes the XP/level line from the award's own facts and puts it at the
end of the turn's narration (after the narration checks, no model call, no number from the model); the turn response,
the stored history and the save say the same. Carius (Fighter 3, 2690 XP) beats a guard (+25), reaches level 4, opens
the level screen through the real routes, applies the ASI, and keeps it across save/load; Undo takes the level back.

The front end shows the level button when ``level > progression_level`` (``levelUpEarned``); its options load when the
button is pressed. This task keeps that (no automatic opening): the line tells the player the choices are waiting."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

import xp
from api.tests.journeys.runner import SCENARIO_DIR
from api.tests.journeys.schema import load_scenario
from api.tests import test_dilim4b_job_xp as job_xp
from api.tests import test_wield_front as wield_front
from api.tests.journeys.runner import JourneyCase
from api.tests.test_dilim4b_combat_xp import ATTACK
from api.tests.test_roadmap_c14_fighter import STRENGTH_ASI

LEVEL_CHOICES = {"2": {}, "3": {"subclass_id": "champion"}}


class AwardLine(unittest.TestCase):
    def test_award_line_exact_copy(self):
        self.assertEqual(xp.award_line({"previous_level": 1, "new_level": 1, "xp_gained": 10, "hit_points_gained": 0}),
                         "+10 deneyim puanı.")
        self.assertEqual(xp.award_line({"previous_level": 3, "new_level": 4, "xp_gained": 25, "hit_points_gained": 8}),
                         "+25 deneyim puanı. Seviye 4 oldun; en yüksek canın 8 arttı. "
                         "Yeni seviyenin seçimleri hikâyenin üstündeki \"Kazanılmış seviye seçimlerini kontrol et\" düğmesinde seni bekliyor.")

    def test_a_jump_over_two_levels_names_the_last_one_and_the_whole_gain(self):
        self.assertEqual(xp.award_line({"previous_level": 3, "new_level": 5, "xp_gained": 3610, "hit_points_gained": 16}),
                         "+3610 deneyim puanı. Seviye 5 oldun; en yüksek canın 16 arttı. "
                         "Yeni seviyenin seçimleri hikâyenin üstündeki \"Kazanılmış seviye seçimlerini kontrol et\" düğmesinde seni bekliyor.")

    def test_thresholds_are_the_srd_ones_and_equality_reaches_the_level(self):
        self.assertEqual(xp.LEVEL_THRESHOLDS, ((1, 0), (2, 300), (3, 900), (4, 2700), (5, 6500)))
        self.assertEqual([xp.level_for_xp(n) for n in (299, 300, 899, 900, 2699, 2700, 6499, 6500)],
                         [1, 2, 2, 3, 3, 4, 4, 5])
        self.assertEqual([xp.proficiency_bonus_for(level) for level in range(1, 6)], [2, 2, 2, 2, 3])
        player = {"class": "Fighter", "level": 3, "xp": 2690, "max_hp": 28, "current_hp": 28,
                  "proficiency_bonus": 2, "constitution": 15}
        summary = xp.apply_xp(player, {"xp_awarded_event_ids": []}, 10, "quest:exactly-four")
        self.assertEqual((summary["new_level"], summary["hit_points_gained"], player["level"]), (4, 8, 4))


class LevelMoment(JourneyCase):
    """The real routes with the scripted model: scenario 46's setup (Carius Fighter 3 at 2690 XP, one guard)."""
    use_setup = wield_front.WieldFront.use_setup
    session = wield_front.WieldFront.session
    world = wield_front.WieldFront.world
    flag = wield_front.WieldFront.flag
    play = wield_front.WieldFront.play
    say = wield_front.WieldFront.say
    undo = wield_front.WieldFront.undo
    reload = wield_front.WieldFront.reload

    async def start(self, seed):
        setup = copy.deepcopy(load_scenario(SCENARIO_DIR / "46_seviye_atlama.json").setup)
        setup["campaign_seed"] = seed
        await self.use_setup(setup)
        self.assertEqual((self.session.character["level"], self.session.character["progression_level"],
                          self.session.character["xp"]), (3, 3, 2690))

    async def turn(self, line, intent=ATTACK):
        """One turn through ``say``, keeping the HTTP answer the player got."""
        original, kept = self.http.post, []

        async def post(url, *args, **kwargs):
            response = await original(url, *args, **kwargs)
            if url.endswith("/turn"):
                kept.append(response)
            return response
        with patch.object(self.http, "post", post):
            await self.say(line, intent=intent)
        self.assertEqual(kept[-1].status_code, 200, kept[-1].text)
        return kept[-1].json()

    async def win_kept(self):
        answer = await self.turn("Muhafıza saldırıyorum")
        for _ in range(12):
            if not self.world["combat"]["active"]:
                break
            answer = await self.turn("vuruyorum")
        self.assertFalse(self.world["combat"]["active"])
        self.assertEqual(self.world["npcs"][0]["combat_status"], "dead")
        return answer

    def stored_history(self):
        return self.store.get_campaign(self.campaign_id).history

    async def test_the_xp_line_reaches_the_player_unchanged(self):
        await self.start(4841)
        max_hp = self.session.character["max_hp"]
        answer = await self.win_kept()
        self.assertEqual(answer["level_up"], {"previous_level": 3, "new_level": 4, "xp_gained": 25,
                                              "hit_points_gained": 8})
        line = xp.award_line(answer["level_up"])
        self.assertIn("Seviye 4 oldun", line)
        self.assertTrue(answer["narration"].endswith(" " + line), answer["narration"])
        self.assertEqual(answer["narration"].count("deneyim puanı"), 1)
        character = answer["state"]["character"]
        self.assertEqual((character["level"], character["progression_level"], character["max_hp"]), (4, 3, max_hp + 8))
        self.assertEqual((self.session.character["xp"], self.session.character["level"]), (2715, 4))
        # a fight turn writes no assistant message, so no older message may be given the line
        told = [row["content"] for row in self.session.messages if row.get("role") == "assistant"]
        self.assertFalse(any(line in text for text in told), told)

    async def test_line_survives_reload(self):
        await self.start(4842)
        answer = await self.win_kept()
        self.assertEqual(self.stored_history()[-1]["narration"], answer["narration"])
        await self.reload()
        self.assertEqual(self.stored_history()[-1]["narration"], answer["narration"])
        self.assertTrue(self.stored_history()[-1]["narration"].endswith(xp.award_line(answer["level_up"])))
        self.assertEqual((self.session.character["xp"], self.session.character["level"]), (2715, 4))

    async def test_carius_three_to_four_real_path(self):
        await self.start(4844)
        await self.win_kept()
        self.assertEqual((self.session.character["level"], self.session.character["progression_level"]), (4, 3))
        url = f"/api/game/sessions/{self.session_id}/level-up"
        preview = (await self.http.get(url)).json()
        self.assertEqual((preview["status"], preview["target_level"], preview["class_name"]), ("ready", 4, "Fighter"),
                         preview)
        strength = self.session.character["strength"]
        body = {"action_id": str(uuid4()), "campaign_id": self.campaign_id, "expected_revision": preview["revision"],
                "target_level": 4, "choices": {"asi": copy.deepcopy(STRENGTH_ASI)}}
        applied = await self.http.post(url, json=body)
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual((self.session.character["level"], self.session.character["progression_level"],
                          self.session.character["strength"]), (4, 4, strength + 2))
        after = (await self.http.get(url)).json()
        self.assertNotEqual(after["status"], "ready")               # nothing more to choose at 2715 XP
        before = copy.deepcopy((self.session.character["level"], self.session.character["progression_level"],
                                self.session.character["strength"], self.session.character["xp"],
                                self.session.character["max_hp"]))
        await self.reload()
        self.assertEqual((self.session.character["level"], self.session.character["progression_level"],
                          self.session.character["strength"], self.session.character["xp"],
                          self.session.character["max_hp"]), before)

    async def test_undo_takes_the_level_back(self):
        await self.start(4845)
        max_hp = self.session.character["max_hp"]
        await self.win_kept()
        self.assertEqual(self.session.character["level"], 4)
        await self.undo()
        self.assertEqual((self.session.character["level"], self.session.character["xp"],
                          self.session.character["max_hp"]), (3, 2690, max_hp))
        self.assertEqual(self.world.get("xp_awarded_event_ids", []), [])
        answer = await self.turn("vuruyorum")
        self.assertEqual(answer["level_up"]["new_level"], 4)
        self.assertEqual((self.session.character["level"], self.session.character["xp"],
                          self.session.character["max_hp"]), (4, 2715, max_hp + 8))
        self.assertEqual(self.world["xp_awarded_event_ids"], ["combat:foe:guard"])

    async def test_no_xp_no_line(self):
        await self.start(4846)
        self.world["npcs"][0].update(current_hp=200, max_hp=200)
        self.manager.save_campaign(self.campaign_id)
        answer = await self.turn("Muhafıza saldırıyorum")
        self.assertTrue(self.world["combat"]["active"])
        self.assertIsNone(answer["level_up"])
        self.assertNotIn("deneyim puanı", answer["narration"])
        self.assertNotIn("Seviye", answer["narration"])
        self.assertEqual(self.session.character["xp"], 2690)



class JobLine(job_xp._JobCase):
    """A talking turn writes an assistant message: the delivery's job XP line ends the reply and that message."""
    deliver_turn = job_xp.JobXp.deliver_turn
    ready_to_deliver = job_xp.JobXp.ready_to_deliver

    async def fresh_campaign(self):
        setup = {**self.setup, "campaign_seed": 4847}
        campaign = await self._journey_campaign(setup)
        job_xp.apply_setup(self, campaign, self.setup)
        self.campaign_id = campaign["campaign_id"]
        self.session_id = campaign["session_id"]
        self.last_session_id = self.session_id

    async def test_a_delivery_turn_carries_the_line_in_the_reply_and_its_message(self):
        await self.ready_to_deliver()
        count = len(self.session.messages)
        out = (await self.deliver_turn()).json()
        self.assertEqual(out["level_up"], {"previous_level": 1, "new_level": 1, "xp_gained": 25,
                                           "hit_points_gained": 0})
        line = xp.award_line(out["level_up"])
        self.assertEqual(line, "+25 deneyim puanı.")
        self.assertTrue(out["narration"].endswith(" " + line), out["narration"])
        written = [row["content"] for row in self.session.messages[count:] if row.get("role") == "assistant"]
        self.assertTrue(written, "the delivery turn wrote no assistant message")
        self.assertTrue(written[-1].endswith(" " + line), written[-1])
        self.assertEqual(sum(text.count(line) for text in written), 1)
        self.assertNotIn(line, json_text(self.world.get("npc_speech_log")))


def json_text(value):
    import json
    return json.dumps(value, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
