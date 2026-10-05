"""Readied-reaction responses retain real scheduler outcomes through HTTP."""
import copy
import unittest
from unittest.mock import patch

import game
import httpx
import action_economy as ae
from api.main import create_app
from api.tests import test_action_economy as economy_tests
from api.tests.test_campaign_time import scene
from api.tests.test_action_economy_end_turn import opponents
from api.persistence.campaign_store import CampaignStore
from api.persistence.campaign_models import CampaignStorageError
from api.session_manager import SessionManager


def interrupted(session, response_kind="attack"):
    """The first enemy has already attacked; two supported attacks remain."""
    npcs = opponents(session)
    response = ({"kind": "attack", "target_id": npcs[0]["id"]}
                if response_kind == "attack" else {"kind": "move", "distance_ft": 5})
    if response_kind == "attack" and not session.find_weapon_in_inventory("Kılıç")[0]:
        session.world_state["inventory"].append({"name": "Kılıç"})
    session.run_player_turn("Hamle.", combat_action={"steps": [{
        "kind": "ready",
        "trigger": {"event": "actor_attacks", "actor_id": npcs[0]["id"]},
        "response": response,
    }]})
    with patch("game.roll_d20", return_value=1):
        prior = session.run_player_turn(
            "Hamle.", combat_action={"steps": [{"kind": "end_turn"}]}
        )
    assert session.world_state["combat"]["current_actor_id"] == npcs[0]["id"]
    assert len(prior["action_result"]["economy_steps"][0]["enemy_actions"]) == 1
    return npcs, ae.ensure(session)["player"]["opportunity"]["id"]


def assert_continuation(test, result, session, npcs, kind, outcomes, damage):
    step = result["action_result"]["economy_steps"][0]
    test.assertEqual(step["kind"], kind)
    actions = step["enemy_actions"]
    test.assertEqual([a["actor_id"] for a in actions], [n["id"] for n in npcs[1:]])
    test.assertEqual([a["outcome"] for a in actions], outcomes)
    test.assertEqual([a["damage"] for a in actions], damage)
    narration = result["narration"]
    sentences = []
    for npc, outcome, amount in zip(npcs[1:], outcomes, damage):
        subject = f"{npc['name']} adlı rakibinin"
        sentences.append(
            f"{subject} karşı saldırısı seni ıskalar." if outcome == "miss" else
            f"{subject} {'kritik ' if outcome == 'critical_hit' else ''}karşı saldırısı sana isabet eder; {amount} hasar alırsın."
        )
    sentences.append(f"Bilincin açık; {100 - sum(damage)}/100 canın kaldı.")
    positions = [narration.index(sentence) for sentence in sentences]
    test.assertEqual(positions, sorted(positions))
    for sentence in sentences:
        test.assertEqual(narration.count(sentence), 1)
    test.assertNotIn(npcs[0]["name"] + " adlı rakibinin karşı saldırısı", narration)
    test.assertNotIn("Turunu bitirirsin.", narration)
    test.assertEqual(session.character["current_hp"], 100 - sum(damage))
    test.assertEqual(session.world_state["combat"]["current_actor_id"], "player")
    test.assertEqual(session.world_state["combat"]["round"], 2)
    test.assertIsNone(ae.ensure(session)["player"]["opportunity"])
    test.assertFalse(ae.ensure(session)["player"]["reaction_spent"])


class ReactionNarrationTests(unittest.TestCase):
    def test_accept_and_decline_retain_ordered_attacks_without_rerunning_trigger(self):
        for kind in ("react", "decline_reaction"):
            for response_kind in ("attack", "move"):
                for rolls, outcomes, damage in (
                    ([15, 20], ["hit", "critical_hit"], [4, 4]),
                    ([1, 15], ["miss", "hit"], [0, 4]),
                ):
                    with self.subTest(kind=kind, response=response_kind, outcomes=outcomes):
                        session = scene()
                        npcs, identity = interrupted(session, response_kind)
                        with patch("game.roll_attack", return_value=1) as reaction_roll, \
                             patch("game.roll_d20", side_effect=rolls) as enemy_roll, \
                             patch("game.roll_damage", return_value=4):
                            result = session.run_player_turn(
                                "Hamle.", combat_action={"steps": [{
                                    "kind": kind, "opportunity_id": identity,
                                }]}
                            )
                        self.assertEqual(enemy_roll.call_count, 2)
                        self.assertEqual(reaction_roll.call_count,
                                         int(kind == "react" and response_kind == "attack"))
                        assert_continuation(self, result, session, npcs, kind, outcomes, damage)
                        self.assertEqual(result["action_economy_result"]["steps"],
                                         result["action_result"]["economy_steps"])
                        self.assertEqual(result["model_calls"], 0)

    def test_final_status_includes_scheduler_death_save_results(self):
        for kind in ("react", "decline_reaction"):
            for status, maximum, damage, rolls, expected in (
                ("dead", 4, 8, [15], "Ölürsün."),
                ("active", 100, 4, [15, 20], "Bilincin açık; 1/100 canın kaldı."),
                ("unconscious", 100, 4, [15, 10, 1, 1, 10, 1, 1, 10, 1, 1], "Bilincini kaybedersin."),
            ):
                with self.subTest(kind=kind, status=status):
                    session = scene()
                    npcs, identity = interrupted(session, "move")
                    # Leave one attacker active so death-save rolls have a
                    # simple, explicit schedule; other actors still keep slots.
                    npcs[0]["conditions"] = ["incapacitated"]
                    npcs[2]["conditions"] = ["incapacitated"]
                    session.character.update(current_hp=1, max_hp=maximum)
                    session.world_state["death_state"]["mode"] = "PERMADEATH"
                    with patch("game.roll_d20", side_effect=rolls), \
                         patch("game.roll_damage", return_value=damage):
                        result = session.run_player_turn(
                            "Hamle.", combat_action={"steps": [{
                                "kind": kind, "opportunity_id": identity,
                            }]}
                        )
                    actions = result["action_result"]["economy_steps"][0]["enemy_actions"]
                    self.assertEqual(actions[0]["actor_id"], npcs[1]["id"])
                    self.assertEqual(actions[0]["damage"], damage)
                    self.assertIn(f"{damage} hasar alırsın.", result["narration"])
                    self.assertTrue(result["narration"].endswith(expected), result["narration"])
                    self.assertEqual(session.world_state["player_combat_status"], status)
                    self.assertEqual(session.character["current_hp"], 1 if status == "active" else 0)
                    if status != "dead":
                        saves = [a for a in actions if a["action"] == "death_save"]
                        self.assertEqual(saves[-1]["outcome"],
                                         "revived" if status == "active" else "stable")
                    self.assertEqual(result["model_calls"], 0)

    def test_reaction_that_ends_combat_has_no_invented_enemy_attack(self):
        session = scene()
        npcs, identity = interrupted(session)
        for npc in npcs:
            npc.update(current_hp=0, combat_status="dead", alive=False)
        npcs[0].update(current_hp=1, combat_status="active", alive=True)
        with patch("game.roll_attack", return_value=20), \
             patch("game.roll_damage", return_value=8), \
             patch.object(session, "_resolve_enemy_turns_until_player",
                          side_effect=AssertionError("closed combat must not schedule")):
            result = session.run_player_turn(
                "Hamle.", combat_action={"steps": [{"kind": "react", "opportunity_id": identity}]}
            )
        self.assertEqual(result["action_result"]["economy_steps"][0]["enemy_actions"], [])
        self.assertFalse(session.world_state["combat"]["active"])
        self.assertNotIn("karşı saldırısı", result["narration"])


class ReactionNarrationApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = economy_tests.ActionEconomyApiTests.asyncSetUp
    asyncTearDown = economy_tests.ActionEconomyApiTests.asyncTearDown
    request = economy_tests.ActionEconomyApiTests.request
    post = economy_tests.ActionEconomyApiTests.post
    command = economy_tests.ActionEconomyApiTests.command

    async def test_failed_react_save_rolls_back_and_retries_once_after_reopening(self):
        await self.assert_failed_resolution_retry("react")

    async def test_failed_decline_save_rolls_back_and_retries_once_after_reopening(self):
        await self.assert_failed_resolution_retry("decline_reaction")

    async def assert_failed_resolution_retry(self, kind):
        record = self.manager.get(self.sid)
        session = record.game_session
        npcs, identity = interrupted(session)
        # These real d20 rolls both hit. Fix only damage and the readied strike's
        # miss so this remains a nonfatal scheduler/persistence regression.
        session.rng.seed(0)
        campaign_id = self.created["campaign_id"]
        self.manager.save_campaign(campaign_id)
        command = self.command(session, npcs[0], {
            "kind": kind, "opportunity_id": identity,
        })

        def runtime(current):
            engine = current.game_session
            return copy.deepcopy((
                engine.serialize_game_state(), engine.rng.getstate(), engine.messages,
                current.journal, current.combat_history, current.narrative_memory,
                current.turn_action_receipts,
            ))

        before = runtime(record)
        combat_before = copy.deepcopy(session.world_state["combat"])
        resources_before = copy.deepcopy(ae.ensure(session)["player"])
        saved_before = self.store.get_campaign(campaign_id)
        self.assertEqual(session.character["current_hp"], 100)
        self.assertEqual(combat_before["current_actor_id"], npcs[0]["id"])
        self.assertEqual(resources_before["opportunity"]["id"], identity)
        self.assertFalse(resources_before["reaction_spent"])
        self.assertIsNotNone(resources_before["ready"])
        self.assertIsNone(self.manager.get_turn_action(record, command["action_id"]))
        attempted_receipts = []

        def fail_save(*args, **kwargs):
            # Prove we reached autosave AFTER resolving the actual pending attacks,
            # rather than rejecting the request or failing before combat changed.
            receipt = copy.deepcopy(kwargs["turn_action_receipt"])
            attempted_receipts.append(receipt)
            body = receipt["response"]
            assert_continuation(
                self, {"action_result": body["combat_result"],
                       "narration": body["narration"]},
                session, npcs, kind, ["hit", "hit"], [4, 4],
            )
            self.assertEqual(session.world_state["player_combat_status"], "active")
            self.assertNotEqual(session.rng.getstate(), before[1])
            self.assertIsNotNone(kwargs["turn_entry"])
            self.assertIsNotNone(kwargs["combat_history_entry"])
            raise CampaignStorageError("controlled reaction autosave failure")

        with patch("game.roll_attack", return_value=1) as reaction_roll, \
             patch("game.roll_d20", wraps=game.roll_d20) as enemy_roll, \
             patch("game.roll_damage", return_value=4), \
             patch.object(self.store, "save_campaign", side_effect=fail_save) as save:
            failed = await self.post(command)
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(save.call_count, 1)
        self.assertEqual(enemy_roll.call_count, 2)
        self.assertEqual(reaction_roll.call_count, int(kind == "react"))
        self.assertEqual(runtime(record), before)
        self.assertEqual(session.character["current_hp"], 100)
        self.assertEqual(session.world_state["combat"], combat_before)
        self.assertEqual(ae.ensure(session)["player"], resources_before)
        self.assertEqual(self.store.get_campaign(campaign_id), saved_before)
        self.assertIsNone(self.manager.get_turn_action(record, command["action_id"]))
        self.assertIsNone(self.store.get_turn_action(campaign_id, command["action_id"]))

        with patch("game.roll_attack", return_value=1) as reaction_roll, \
             patch("game.roll_d20", wraps=game.roll_d20) as enemy_roll, \
             patch("game.roll_damage", return_value=4), \
             patch.object(self.store, "save_campaign", wraps=self.store.save_campaign) as save:
            successful = await self.post(command)
        self.assertEqual(successful.status_code, 200, successful.text)
        self.assertEqual(save.call_count, 1)
        self.assertEqual(enemy_roll.call_count, 2)
        self.assertEqual(reaction_roll.call_count, int(kind == "react"))
        body = successful.json()
        # A failed attempt's uncommitted history event gets a fresh UUID on retry;
        # the mechanical outcome and narration must still be identical.
        self.assertEqual(body["combat_result"], attempted_receipts[0]["response"]["combat_result"])
        self.assertEqual(body["narration"], attempted_receipts[0]["response"]["narration"])
        assert_continuation(
            self, {"action_result": body["combat_result"], "narration": body["narration"]},
            session, npcs, kind, ["hit", "hit"], [4, 4],
        )
        self.assertNotEqual(session.rng.getstate(), before[1])
        committed = self.store.get_campaign(campaign_id)
        self.assertEqual(len(committed.history), len(saved_before.history) + 1)
        self.assertEqual(len(committed.combat_history), len(saved_before.combat_history) + 1)
        receipt = self.store.get_turn_action(campaign_id, command["action_id"])
        self.assertEqual(receipt["request_hash"], attempted_receipts[0]["request_hash"])
        self.assertEqual(receipt["response"], body)
        self.assertEqual(record.combat_history, committed.combat_history)

        accepted = runtime(record)
        with patch.object(session, "run_player_turn", side_effect=AssertionError("replay ran turn")), \
             patch.object(self.store, "save_campaign", side_effect=AssertionError("replay saved")):
            replay = await self.post(command)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), body)
        self.assertEqual(runtime(record), accepted)
        self.assertEqual(self.store.get_campaign(campaign_id), committed)

        reopened_store = CampaignStore(self.store.path)
        manager = SessionManager(session_factory=scene, campaign_store=reopened_store)
        sid, restored, _, history, _ = manager.resume_campaign(campaign_id)
        self.assertEqual(runtime(restored), accepted)
        self.assertEqual(history, committed.history)
        self.assertEqual(manager.get_turn_action(restored, command["action_id"]), receipt)
        # Resume can update metadata; compare replay with the post-resume store.
        reopened_before = reopened_store.get_campaign(campaign_id)
        app = create_app(session_manager=manager, ollama_adapter=self.app.state.ollama_adapter)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            with patch.object(restored.game_session, "run_player_turn",
                              side_effect=AssertionError("reopened replay ran turn")), \
                 patch.object(reopened_store, "save_campaign",
                              side_effect=AssertionError("reopened replay saved")):
                for _ in range(2):
                    replay = await client.post(f"/api/game/sessions/{sid}/turn", json=command)
                    self.assertEqual(replay.status_code, 200, replay.text)
                    self.assertEqual(replay.json(), dict(body, session_id=sid))
                    self.assertEqual(runtime(restored), accepted)
                    self.assertEqual(reopened_store.get_campaign(campaign_id), reopened_before)
                    self.assertEqual(manager.get_turn_action(restored, command["action_id"]), receipt)

    async def test_both_reaction_responses_and_saved_receipts_retain_enemy_attacks(self):
        for kind in ("react", "decline_reaction"):
            with self.subTest(kind=kind):
                session = self.manager.get(self.sid).game_session
                session.end_combat()
                session.world_state["npcs"] = []
                npcs, identity = interrupted(session)
                command = self.command(session, npcs[0], {
                    "kind": kind, "opportunity_id": identity,
                })
                with patch("game.roll_attack", return_value=1), \
                     patch("game.roll_d20", side_effect=[15, 20]), \
                     patch("game.roll_damage", return_value=4):
                    response = await self.post(command)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                assert_continuation(self, {"action_result": body["combat_result"],
                                           "narration": body["narration"]},
                                    session, npcs, kind, ["hit", "critical_hit"], [4, 4])
                before = copy.deepcopy((session.world_state, session.character, session.rng.getstate()))
                with patch("game.roll_d20", side_effect=AssertionError("receipt rerolled")), \
                     patch("game.roll_attack", side_effect=AssertionError("reaction repeated")):
                    replay = await self.post(command)
                self.assertEqual(replay.json(), body)
                self.assertEqual((session.world_state, session.character, session.rng.getstate()), before)
                manager = SessionManager(session_factory=scene,
                                         campaign_store=CampaignStore(self.store.path))
                _, restored, _, _, _ = manager.resume_campaign(self.created["campaign_id"])
                saved = manager.get_turn_action(restored, command["action_id"])["response"]
                self.assertEqual(saved["narration"], body["narration"])
                self.assertEqual(saved["combat_result"], body["combat_result"])
                self.assertEqual(restored.game_session.character["current_hp"], 92)
