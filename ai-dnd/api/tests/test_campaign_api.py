"""HTTP-level tests for persistent campaign lifecycle and autosave behavior."""

from __future__ import annotations

import copy
from contextlib import closing
from functools import wraps
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

import httpx


AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
import living_world
import quest_catalog
import api.main as main_module
from api.campaign_journal import create_initial_campaign_journal
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.dnd_2024_rules import SPECIES_DEFINITIONS
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


class FakeOllamaClient:
    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        raise AssertionError("Campaign API tests must not call a real model.")


class CampaignApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = CampaignStore(
            Path(self.temporary_directory.name) / "campaigns.sqlite3"
        )
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        self.app = create_app(
            session_manager=self.manager,
            ollama_adapter=adapter,
        )
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    async def create_campaign(self):
        response = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_death_mode_selection_persists_and_legacy_requests_default_to_normal(self):
        legacy = await self.create_campaign()
        self.assertEqual(legacy["state"]["death_state"]["mode"], "NORMAL")

        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                response = await self.http.post(
                    "/api/game/campaigns",
                    json={"death_mode": mode},
                )
                self.assertEqual(response.status_code, 200, response.text)
                created = response.json()
                self.assertEqual(created["state"]["death_state"]["mode"], mode)

                resumed_manager = SessionManager(
                    campaign_store=CampaignStore(self.store.path)
                )
                resumed_id, _, _, _, _ = resumed_manager.resume_campaign(
                    created["campaign_id"]
                )
                self.assertEqual(
                    resumed_manager.get(resumed_id)
                    .game_session.world_state["death_state"]["mode"],
                    mode,
                )

    async def test_normal_death_rollback_does_not_rewrite_campaign_metadata(self):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        session = record.game_session

        def rolled_back_turn(_message, **_kwargs):
            return {
                "narration": "Normal modda çatışma öncesi duruma dönüldü.",
                "action_result": {
                    "action": "death_save",
                    "status": "resolved",
                    "success": True,
                    "death_resolution": {
                        "mode": "NORMAL",
                        "outcome": "rolled_back",
                        "cause": "failed_death_saves",
                        "rolled_back": True,
                        "terminal": False,
                    },
                },
            }

        session.run_player_turn = rolled_back_turn
        with (
            patch.object(
                main_module,
                "set_session_world_metadata",
                side_effect=AssertionError("metadata must come from the checkpoint"),
            ),
            patch.object(
                main_module,
                "update_narrative_memory",
                side_effect=AssertionError("rollback turns do not add memories"),
            ),
            patch.object(
                main_module,
                "update_campaign_journal",
                side_effect=AssertionError("rollback turns do not add journal entries"),
            ),
        ):
            response = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/turn",
                json={"message": "Bekle."},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["combat_result"]["death_resolution"]["outcome"],
            "rolled_back",
        )

    async def test_death_checkpoint_is_json_safe_and_external_restore_is_atomic(self):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        session = record.game_session
        game._capture_combat_death_checkpoint(session=session)
        self.assertIsNotNone(
            session.world_state["death_state"]["combat_checkpoint"]
        )

        self.manager.save_campaign(created["campaign_id"])
        stored = self.store.get_campaign(created["campaign_id"])
        encoded = json.dumps(
            stored.payload,
            ensure_ascii=False,
            allow_nan=False,
        )
        self.assertTrue(encoded)

        resumed_manager = SessionManager(
            campaign_store=CampaignStore(self.store.path)
        )
        resumed_id, resumed_record, _, _, _ = resumed_manager.resume_campaign(
            created["campaign_id"]
        )
        resumed_session = resumed_record.game_session
        checkpoint = copy.deepcopy(
            resumed_session.world_state["death_state"]["combat_checkpoint"]
        )
        campaign_state = checkpoint["campaign_state"]

        resumed_record.journal = {"marker": "must remain untouched"}
        before_narrative = copy.deepcopy(resumed_record.narrative_memory)
        before_lore = resumed_record.lore_authority.to_dict()
        invalid_checkpoint = copy.deepcopy(checkpoint)
        invalid_checkpoint["campaign_state"]["narrative_memory"] = []
        resumed_session.world_state["death_state"][
            "combat_checkpoint"
        ] = invalid_checkpoint

        with self.assertRaises(CampaignStorageError):
            game._restore_combat_death_checkpoint(
                "massive_damage",
                session=resumed_session,
            )

        self.assertEqual(
            resumed_record.journal,
            {"marker": "must remain untouched"},
        )
        self.assertEqual(resumed_record.narrative_memory, before_narrative)
        self.assertEqual(resumed_record.lore_authority.to_dict(), before_lore)

        resumed_session.world_state["death_state"][
            "combat_checkpoint"
        ] = checkpoint
        result = game._restore_combat_death_checkpoint(
            "massive_damage",
            session=resumed_session,
        )
        self.assertTrue(result["rolled_back"])
        self.assertEqual(resumed_record.journal, campaign_state["journal"])
        self.assertEqual(
            resumed_record.narrative_memory,
            campaign_state["narrative_memory"],
        )
        self.assertEqual(
            resumed_record.lore_authority.to_dict(),
            campaign_state["lore_authority"],
        )
        self.assertEqual(
            resumed_session.world_metadata,
            campaign_state["world_metadata"],
        )

    async def test_turn_action_replays_after_resume_and_rejects_reused_payload(self):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        session = record.game_session
        calls = []

        def deterministic_turn(_message, **_kwargs):
            calls.append(True)
            return {
                "narration": "Kapıdan hafif bir ses geliyor.",
                "action_result": {
                    "action": "world_interaction",
                    "status": "resolved",
                    "success": True,
                    "state_changes": [],
                },
            }

        session.run_player_turn = deterministic_turn
        action_id = str(uuid.uuid4())
        body = {
            "message": "Kapının arkasından ses dinliyorum.",
            "action_id": action_id,
        }
        first = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json=body,
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["action_id"], action_id)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.store.get_campaign(created["campaign_id"]).history), 1)

        same_session_retry = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json=body,
        )
        self.assertEqual(same_session_retry.status_code, 200, same_session_retry.text)
        self.assertEqual(same_session_retry.json(), first.json())
        self.assertEqual(len(calls), 1)

        reloaded_manager = SessionManager(
            campaign_store=CampaignStore(self.store.path)
        )
        resumed_id, _, _, _, _ = reloaded_manager.resume_campaign(
            created["campaign_id"]
        )
        reloaded_app = create_app(
            session_manager=reloaded_manager,
            ollama_adapter=None,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reloaded_app),
            base_url="http://testserver",
        ) as reloaded_http:
            after_resume = await reloaded_http.post(
                f"/api/game/sessions/{resumed_id}/turn",
                json=body,
            )
            self.assertEqual(after_resume.status_code, 200, after_resume.text)
            self.assertEqual(after_resume.json()["action_id"], action_id)
            self.assertEqual(after_resume.json()["narration"], first.json()["narration"])
            self.assertEqual(
                after_resume.json()["state"],
                first.json()["state"],
            )

            conflicting = await reloaded_http.post(
                f"/api/game/sessions/{resumed_id}/turn",
                json={**body, "message": "Kapıyı açıyorum."},
            )
            self.assertEqual(conflicting.status_code, 409)
            self.assertEqual(
                conflicting.json()["detail"]["code"],
                "action_id_conflict",
            )
        self.assertEqual(len(self.store.get_campaign(created["campaign_id"]).history), 1)
        self.assertEqual(len(calls), 1)

    def install_test_ambient_event(self, session, event_type="BLUE"):
        world = session.world_state
        if world.get("location") == "Henüz belirlenmedi":
            world["location"] = "tavern"
        location_id = world["location"]
        turn_index = world.get("flags", {}).get("turn_index", 0)
        scene = living_world.ensure_scene_record(
            world,
            location_id,
            turn_index,
        )
        scene["materialized"] = False
        scene["referents"] = []
        scene.pop("ambient_event", None)
        event = {
            "event_id": "city_test_traveler",
            "variation_id": "v1",
            "repeat_group": "test-traveler",
            "event_type": event_type,
            "text": "Bir yolcu kısa süreliğine yakındaki bir kişiye sesleniyor.",
            "aliases": ["yolcu", "gezgin"],
        }
        with patch.object(
            living_world,
            "select_ambient_event",
            return_value=event,
        ):
            scene = living_world.materialize_scene(
                world,
                location_id,
                turn_index,
                create_npc=session.create_npc_from_ai,
                create_feature=session.create_local_feature,
            )
        return scene["ambient_event"]["instance_id"]

    async def test_game_session_bound_turn_uses_engine_signature_fallback(self):
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "name": "Session-bound engine signature regression",
                # This is the release-gate start where city-look is deterministic
                # and must not invoke the fake model adapter.
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": "fr:city:neverwinter",
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        session = self.manager.get(created["session_id"]).game_session
        self.assertIsInstance(session, game.GameSession)

        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Etrafıma bakıyorum."},
        )
        self.assertEqual(response.status_code, 200, response.text)
        turn = response.json()
        self.assertTrue(turn["narration"].strip())
        self.assertIsInstance(turn.get("state"), dict)
        self.assertTrue(turn["state"])

    async def test_city_observation_and_discovery_receipts_survive_resume(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "name": "City observation and discovery receipt regression",
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        session = self.manager.get(created["session_id"]).game_session
        messages = [
            "Şehirde dolanırken etrafımda neler var gözlemliyorum.",
            "Yakınlarda oturup bir şeyler içebileceğim bir yer var mı?",
            "Buralarda bir tücaar var mı?",
        ]
        requests = [
            {"message": message, "action_id": str(uuid.uuid4())}
            for message in messages
        ]
        turns = []
        engine_results = []

        async def execute_and_replay(http, session_id, game_session, body, index):
            # Observe the real engine boundary: TurnResponse deliberately exposes
            # narration/state rather than the living-world action_result.
            real_turn = game_session.run_player_turn

            @wraps(real_turn)
            def capture_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                engine_results.append(copy.deepcopy(result["action_result"]))
                return result

            url = f"/api/game/sessions/{session_id}/turn"
            with patch.object(game_session, "run_player_turn", new=capture_turn):
                first = await http.post(url, json=body)
                self.assertEqual(first.status_code, 200, first.text)
                turn = first.json()
                self.assertEqual(turn["action_id"], body["action_id"])
                self.assertTrue(turn["narration"].strip())
                self.assertEqual(turn["state"]["location"], city_id)
                result = engine_results[-1]
                self.assertEqual(result["action"], "explore" if index == 0 else "local_search")
                self.assertEqual(result["status"], "observed" if index == 0 else "found")
                self.assertTrue(result["success"])
                self.assertTrue(result["direct_response"].strip())
                before_replay = copy.deepcopy(game_session.serialize_game_state())
                replay = await http.post(url, json=body)
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(replay.json(), turn)
                self.assertEqual(game_session.serialize_game_state(), before_replay)
                self.assertEqual(len(engine_results), index + 1)
                self.assertEqual(
                    len(self.store.get_campaign(created["campaign_id"]).history),
                    index + 1,
                )
            turns.append(turn)

        await execute_and_replay(
            self.http, created["session_id"], session, requests[0], 0
        )
        scene = copy.deepcopy(session.world_state["scene_state"]["scenes"][city_id])
        self.assertEqual(scene["kind"], "city")
        self.assertTrue(scene["materialized"])
        self.assertIn("Neverwinter", turns[0]["narration"])

        # Reopen before discovery as well as after it: no original in-memory
        # scene or manager may be needed to continue this sequence.
        reloaded_manager = SessionManager(campaign_store=CampaignStore(self.store.path))
        reloaded_app = create_app(
            session_manager=reloaded_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reloaded_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(
                f"/api/game/campaigns/{created['campaign_id']}/resume"
            )
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"], turns[0]["state"])
            session_id = resumed.json()["session_id"]
            loaded = reloaded_manager.get(session_id).game_session
            for index in (1, 2):
                await execute_and_replay(http, session_id, loaded, requests[index], index)

        world = loaded.world_state
        tavern_id = engine_results[1]["target_id"]
        tavern = world["locations"][tavern_id]
        self.assertEqual(tavern["scene_kind"], "tavern")
        self.assertEqual(tavern["parent_location_id"], city_id)
        self.assertEqual(tavern["exit_location_id"], city_id)
        self.assertEqual(len(world["shops"]), 1)
        shop = world["shops"][0]
        self.assertEqual(shop["id"], engine_results[2]["shop_id"])
        self.assertEqual(shop["location"], city_id)
        self.assertEqual(shop["shopkeeper_id"], engine_results[2]["target_id"])
        shopkeeper = next(npc for npc in world["npcs"] if npc["id"] == shop["shopkeeper_id"])
        self.assertEqual(shopkeeper["location"], city_id)
        self.assertEqual(world["location"], city_id)
        self.assertEqual(world["scene_state"]["scenes"][city_id], scene)
        saved_state = copy.deepcopy(loaded.serialize_game_state())

        restarted_manager = SessionManager(campaign_store=CampaignStore(self.store.path))
        restarted_app = create_app(
            session_manager=restarted_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(
                f"/api/game/campaigns/{created['campaign_id']}/resume"
            )
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"], turns[-1]["state"])
            session_id = resumed.json()["session_id"]
            reopened = restarted_manager.get(session_id).game_session
            self.assertEqual(reopened.serialize_game_state(), saved_state)
            with patch.object(
                reopened, "run_player_turn",
                side_effect=AssertionError("Receipt replay must not execute a turn"),
            ):
                for body, original in zip(requests, turns):
                    replay = await http.post(
                        f"/api/game/sessions/{session_id}/turn", json=body
                    )
                    self.assertEqual(replay.status_code, 200, replay.text)
                    # Resume rebinds only session_id; the saved result,
                    # narration, action ID and historical state stay identical.
                    self.assertEqual(
                        replay.json(), {**original, "session_id": session_id}
                    )
                    self.assertEqual(reopened.serialize_game_state(), saved_state)
            self.assertEqual(
                len(self.store.get_campaign(created["campaign_id"]).history), 3
            )

    async def test_failed_tavern_discovery_is_rolled_back_and_retry_commits_once(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        session = record.game_session
        url = f"/api/game/sessions/{created['session_id']}/turn"
        observation_body = {
            "message": "Şehirde dolanırken etrafımda neler var gözlemliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        observation_results = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_observation(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            observation_results.append(copy.deepcopy(result["action_result"]))
            return result

        # Preserve a committed turn, not merely the campaign's empty baseline.
        with patch.object(session, "run_player_turn", new=capture_observation):
            observed = await self.http.post(url, json=observation_body)
        self.assertEqual(observed.status_code, 200, observed.text)
        self.assertEqual(observed.json()["action_id"], observation_body["action_id"])
        self.assertEqual(len(observation_results), 1)
        self.assertEqual(observation_results[0]["action"], "explore")
        self.assertEqual(observation_results[0]["status"], "observed")
        self.assertTrue(observation_results[0]["success"])
        self.assertNotEqual(observed.json()["state"], created["state"])
        self.assertTrue(record.journal["notable_events"])
        self.assertIn(
            city_id,
            [entry["location_id"] for entry in record.journal["discovered_locations"]],
        )
        observation_receipt = copy.deepcopy(
            self.manager.get_turn_action(record, observation_body["action_id"])
        )
        self.assertEqual(observation_receipt["response"], observed.json())
        self.assertEqual(
            self.store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        body = {
            "message": "Yakınlarda bir taverna arıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        before_save = copy.deepcopy(session.serialize_game_state())
        before_journal = copy.deepcopy(record.journal)
        before_memory = copy.deepcopy(record.narrative_memory)
        before_receipts = copy.deepcopy(record.turn_action_receipts)
        before_campaign = self.store.get_campaign(campaign_id)
        self.assertEqual(before_save["world_state"]["location"], city_id)
        self.assertFalse(any(
            location.get("scene_kind") == "tavern"
            for location in session.world_state["locations"].values()
        ))
        self.assertTrue(
            before_save["world_state"]["scene_state"]["scenes"][city_id]["materialized"]
        )
        self.assertEqual(len(before_campaign.history), 1)
        self.assertEqual(
            before_campaign.history[0]["player_message"], observation_body["message"]
        )
        self.assertEqual(before_campaign.payload["engine_save"], before_save)
        self.assertEqual(before_campaign.payload["journal"], before_journal)
        results = []
        attempted_saves = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            results.append(copy.deepcopy(result["action_result"]))
            attempted_saves.append(copy.deepcopy(session.serialize_game_state()))
            return result

        # Observe a genuine offline discovery, failing only its persistence.
        with (
            patch.object(session, "run_player_turn", new=capture_turn),
            patch.object(
                self.store,
                "save_campaign",
                side_effect=CampaignStorageError("database unavailable"),
            ) as failed_save,
        ):
            failed = await self.http.post(url, json=body)
        failed_save.assert_called_once()
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(
            failed.json()["detail"]["code"], "campaign_storage_unavailable"
        )
        self.assertNotIn("database unavailable", failed.text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "local_search")
        self.assertEqual(results[0]["status"], "found")
        self.assertTrue(results[0]["success"])
        uncommitted_id = results[0]["target_id"]
        self.assertNotIn(uncommitted_id, before_save["world_state"]["locations"])
        self.assertEqual(
            attempted_saves[0]["world_state"]["locations"][uncommitted_id][
                "scene_kind"
            ],
            "tavern",
        )
        self.assertEqual(session.serialize_game_state(), before_save)
        self.assertNotIn(uncommitted_id, session.world_state["locations"])
        self.assertEqual(record.journal, before_journal)
        self.assertEqual(record.narrative_memory, before_memory)
        self.assertEqual(record.turn_action_receipts, before_receipts)
        self.assertEqual(
            self.manager.get_turn_action(record, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertNotIn(body["action_id"], record.turn_action_receipts)
        self.assertIsNone(self.manager.get_turn_action(record, body["action_id"]))
        failed_campaign = self.store.get_campaign(campaign_id)
        self.assertEqual(failed_campaign, before_campaign)
        self.assertEqual(
            self.store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertIsNone(self.store.get_turn_action(campaign_id, body["action_id"]))

        # A new manager must retain the observation without any unsaved venue,
        # scene changes, journal entries, history, or failed discovery receipt.
        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["state"], observed.json()["state"])
        self.assertEqual(resumed.json()["history"], before_campaign.history)
        reopened_record = reopened_manager.get(resumed.json()["session_id"])
        self.assertEqual(
            reopened_record.game_session.serialize_game_state(), before_save
        )
        self.assertEqual(reopened_record.journal, before_journal)
        self.assertEqual(reopened_record.narrative_memory, before_memory)
        self.assertEqual(reopened_record.turn_action_receipts, before_receipts)
        self.assertEqual(
            reopened_manager.get_turn_action(
                reopened_record, observation_body["action_id"]
            ),
            observation_receipt,
        )
        self.assertNotIn(
            uncommitted_id, reopened_record.game_session.world_state["locations"]
        )
        self.assertNotIn(body["action_id"], reopened_record.turn_action_receipts)
        self.assertIsNone(
            reopened_manager.get_turn_action(reopened_record, body["action_id"])
        )
        reopened_campaign = reopened_store.get_campaign(campaign_id)
        # Resume may refresh metadata timestamps, but not saved gameplay.
        self.assertEqual(reopened_campaign.payload, before_campaign.payload)
        self.assertEqual(reopened_campaign.history, before_campaign.history)
        self.assertEqual(reopened_campaign.combat_history, before_campaign.combat_history)
        self.assertEqual(
            reopened_store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertIsNone(
            reopened_store.get_turn_action(campaign_id, body["action_id"])
        )

        # Recover storage and retry the identical action on the live session.
        with patch.object(session, "run_player_turn", new=capture_turn):
            retry = await self.http.post(url, json=body)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["action_id"], body["action_id"])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[-1]["action"], "local_search")
        self.assertEqual(results[-1]["status"], "found")
        self.assertTrue(results[-1]["success"])
        tavern_id = results[-1]["target_id"]
        taverns = [
            location
            for location in session.world_state["locations"].values()
            if location.get("scene_kind") == "tavern"
        ]
        self.assertEqual(len(taverns), 1)
        self.assertEqual(taverns[0], session.world_state["locations"][tavern_id])
        self.assertEqual(taverns[0]["parent_location_id"], city_id)
        self.assertEqual(taverns[0]["exit_location_id"], city_id)
        self.assertEqual(retry.json()["state"]["location"], city_id)
        committed_save = copy.deepcopy(session.serialize_game_state())
        committed_journal = copy.deepcopy(record.journal)
        committed_campaign = self.store.get_campaign(campaign_id)
        self.assertEqual(committed_campaign.payload["engine_save"], committed_save)
        self.assertEqual(committed_campaign.payload["journal"], committed_journal)
        self.assertEqual(len(committed_campaign.history), 2)
        self.assertEqual(committed_campaign.history[:-1], before_campaign.history)
        self.assertEqual(
            self.manager.get_turn_action(record, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertEqual(
            self.store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertEqual(
            self.manager.get_turn_action(record, body["action_id"])["response"],
            retry.json(),
        )
        self.assertEqual(
            self.store.get_turn_action(campaign_id, body["action_id"])["response"],
            retry.json(),
        )
        with patch.object(
            session,
            "run_player_turn",
            side_effect=AssertionError("Discovery replay must not execute a turn"),
        ):
            replay = await self.http.post(url, json=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), retry.json())
        self.assertEqual(session.serialize_game_state(), committed_save)
        self.assertEqual(record.journal, committed_journal)
        self.assertEqual(self.store.get_campaign(campaign_id), committed_campaign)

    async def test_failed_tavern_discovery_retries_once_from_a_fresh_resume(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        session = record.game_session
        turn_url = f"/api/game/sessions/{created['session_id']}/turn"
        observation_body = {
            "message": "Şehirde dolanırken etrafımda neler var gözlemliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        results = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            results.append(copy.deepcopy(result["action_result"]))
            return result

        with patch.object(session, "run_player_turn", new=capture_turn):
            observed = await self.http.post(turn_url, json=observation_body)
        self.assertEqual(observed.status_code, 200, observed.text)
        self.assertEqual(results[0]["action"], "explore")
        self.assertEqual(results[0]["status"], "observed")
        self.assertTrue(results[0]["success"])
        observation_receipt = copy.deepcopy(
            self.store.get_turn_action(campaign_id, observation_body["action_id"])
        )
        self.assertEqual(observation_receipt["response"], observed.json())
        before_save = copy.deepcopy(session.serialize_game_state())
        before_campaign = self.store.get_campaign(campaign_id)
        self.assertEqual(len(before_campaign.history), 1)
        self.assertEqual(
            before_campaign.history[0]["player_message"], observation_body["message"]
        )
        self.assertEqual(before_save["world_state"]["location"], city_id)
        self.assertFalse(any(
            location.get("scene_kind") == "tavern"
            for location in before_save["world_state"]["locations"].values()
        ))
        discovery_body = {
            "message": "Yakınlarda bir taverna arıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        with (
            patch.object(session, "run_player_turn", new=capture_turn),
            patch.object(
                self.store, "save_campaign",
                side_effect=CampaignStorageError("database unavailable"),
            ) as failed_save,
        ):
            failed = await self.http.post(turn_url, json=discovery_body)
        failed_save.assert_called_once()
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(
            failed.json()["detail"]["code"], "campaign_storage_unavailable"
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[-1]["action"], "local_search")
        self.assertEqual(results[-1]["status"], "found")
        self.assertTrue(results[-1]["success"])
        uncommitted_id = results[-1]["target_id"]
        self.assertEqual(session.serialize_game_state(), before_save)
        self.assertEqual(self.store.get_campaign(campaign_id), before_campaign)
        self.assertIsNone(
            self.store.get_turn_action(campaign_id, discovery_body["action_id"])
        )

        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"], observed.json()["state"])
            self.assertEqual(resumed.json()["history"], before_campaign.history)
            resumed_record = reopened_manager.get(resumed.json()["session_id"])
            resumed_session = resumed_record.game_session
            self.assertIsNot(resumed_session, session)
            self.assertEqual(resumed_session.serialize_game_state(), before_save)
            self.assertEqual(resumed_record.journal, before_campaign.payload["journal"])
            self.assertNotIn(uncommitted_id, resumed_session.world_state["locations"])
            self.assertIsNone(
                reopened_manager.get_turn_action(
                    resumed_record, discovery_body["action_id"]
                )
            )
            self.assertEqual(
                reopened_manager.get_turn_action(
                    resumed_record, observation_body["action_id"]
                ),
                observation_receipt,
            )
            resumed_url = f"/api/game/sessions/{resumed.json()['session_id']}/turn"
            resumed_real_turn = resumed_session.run_player_turn
            retry_results = []

            @wraps(resumed_real_turn)
            def capture_retry(*args, **kwargs):
                result = resumed_real_turn(*args, **kwargs)
                retry_results.append(copy.deepcopy(result["action_result"]))
                return result

            with (
                patch.object(
                    session, "run_player_turn",
                    side_effect=AssertionError("Retry must use the resumed session"),
                ) as original_turn,
                patch.object(
                    resumed_session, "run_player_turn", new=capture_retry,
                ),
                patch.object(
                    reopened_store, "save_campaign", wraps=reopened_store.save_campaign
                ) as retry_save,
            ):
                retry = await http.post(resumed_url, json=discovery_body)
            self.assertEqual(retry.status_code, 200, retry.text)
            original_turn.assert_not_called()
            self.assertEqual(len(retry_results), 1)
            self.assertEqual(retry_results[0]["action"], "local_search")
            self.assertEqual(retry_results[0]["status"], "found")
            self.assertTrue(retry_results[0]["success"])
            retry_save.assert_called_once()
            self.assertEqual(retry.json()["action_id"], discovery_body["action_id"])
            taverns = [
                location
                for location in resumed_session.world_state["locations"].values()
                if location.get("scene_kind") == "tavern"
            ]
            self.assertEqual(len(taverns), 1)
            self.assertEqual(
                taverns[0],
                resumed_session.world_state["locations"][retry_results[0]["target_id"]],
            )
            self.assertEqual(taverns[0]["parent_location_id"], city_id)
            self.assertEqual(taverns[0]["exit_location_id"], city_id)
            self.assertEqual(retry.json()["state"]["location"], city_id)
            committed_save = copy.deepcopy(resumed_session.serialize_game_state())
            committed_campaign = reopened_store.get_campaign(campaign_id)
            self.assertEqual(committed_campaign.payload["engine_save"], committed_save)
            self.assertEqual(
                committed_campaign.payload["journal"], resumed_record.journal
            )
            self.assertEqual(
                len(committed_campaign.history), len(before_campaign.history) + 1
            )
            self.assertEqual(committed_campaign.history[:-1], before_campaign.history)
            self.assertEqual(
                committed_campaign.history[-1]["player_message"],
                discovery_body["message"],
            )
            for manager, receipt_record in (
                (self.manager, record), (reopened_manager, resumed_record)
            ):
                self.assertEqual(
                    manager.get_turn_action(
                        receipt_record, observation_body["action_id"]
                    ),
                    observation_receipt,
                )
            self.assertEqual(
                reopened_store.get_turn_action(
                    campaign_id, observation_body["action_id"]
                ),
                observation_receipt,
            )
            discovery_receipt = copy.deepcopy(
                reopened_manager.get_turn_action(
                    resumed_record, discovery_body["action_id"]
                )
            )
            self.assertEqual(discovery_receipt["response"], retry.json())
            self.assertEqual(
                reopened_store.get_turn_action(campaign_id, discovery_body["action_id"]),
                discovery_receipt,
            )
            with (
                patch.object(
                    resumed_session, "run_player_turn",
                    side_effect=AssertionError("Replay must not execute another turn"),
                ) as replay_turn,
                patch.object(
                    reopened_store, "save_campaign",
                    side_effect=AssertionError("Replay must not save again"),
                ) as replay_save,
            ):
                replay = await http.post(resumed_url, json=discovery_body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), retry.json())
            replay_turn.assert_not_called()
            replay_save.assert_not_called()
            self.assertEqual(resumed_session.serialize_game_state(), committed_save)
            self.assertEqual(
                resumed_record.journal, committed_campaign.payload["journal"]
            )
            self.assertEqual(reopened_store.get_campaign(campaign_id), committed_campaign)
            self.assertEqual(
                reopened_store.get_turn_action(campaign_id, observation_body["action_id"]),
                observation_receipt,
            )
            self.assertEqual(
                reopened_store.get_turn_action(campaign_id, discovery_body["action_id"]),
                discovery_receipt,
            )

    async def test_reopened_declined_tavern_search_preserves_entities_and_history(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        original_session = self.manager.get(created["session_id"]).game_session
        discovery_body = {
            "message": "Yakınlarda bir taverna arıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        real_discovery = original_session.run_player_turn
        discovery_results = []

        @wraps(real_discovery)
        def capture_discovery(*args, **kwargs):
            result = real_discovery(*args, **kwargs)
            discovery_results.append(copy.deepcopy(result["action_result"]))
            return result

        with patch.object(original_session, "run_player_turn", new=capture_discovery):
            discovered = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/turn",
                json=discovery_body,
            )
        self.assertEqual(discovered.status_code, 200, discovered.text)
        self.assertEqual(len(discovery_results), 1)
        self.assertEqual(discovery_results[0]["action"], "local_search")
        self.assertEqual(discovery_results[0]["status"], "found")
        self.assertTrue(discovery_results[0]["success"])
        tavern_id = discovery_results[0]["target_id"]
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        self.assertEqual(saved_world["locations"][tavern_id]["scene_kind"], "tavern")
        self.assertEqual(
            saved_world["locations"][tavern_id]["parent_location_id"], city_id
        )

        non_search_narration = "Şehrin sokaklarından gelen sesler sürüyor."

        class DeclinedTavernOllamaClient(FakeOllamaClient):
            def chat(self, *args, **kwargs):
                # Script only the model boundary, never the real turn or save.
                if "intent" in kwargs["format"]["properties"]:
                    packet = {
                        "intent": "narrative",
                        "action": "decline_search",
                        "target": {"type": "none", "reference": ""},
                        "completion": "completed",
                        "confidence": 1.0,
                    }
                else:
                    packet = {
                        "narration": non_search_narration,
                        "world_updates": {},
                        "lore_claims": [],
                    }
                return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}

        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(DeclinedTavernOllamaClient()),
        )
        declined_body = {
            # The supported negative suffix used by the living-world regression
            # also bypasses game.py's is_tavern_search gate.
            "message": "Bir taverna aramıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        self.assertNotEqual(declined_body["action_id"], discovery_body["action_id"])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            session = reopened_manager.get(session_id).game_session
            self.assertIsNot(session, original_session)
            self.assertEqual(session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(resumed.json()["history"], committed.history)
            self.assertIsNone(
                reopened_store.get_turn_action(campaign_id, declined_body["action_id"])
            )
            real_turn = session.run_player_turn
            results = []

            @wraps(real_turn)
            def capture_declined_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result))
                return result

            with patch.object(session, "run_player_turn", new=capture_declined_turn):
                declined = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=declined_body
                )
            self.assertEqual(declined.status_code, 200, declined.text)
            self.assertEqual(declined.json()["action_id"], declined_body["action_id"])
            self.assertEqual(len(results), 1)
            action = results[0]["action_result"]
            self.assertEqual(action["action"], "narrative")
            self.assertEqual(action["status"], "resolved")
            self.assertTrue(action["success"])
            self.assertEqual(action["state_changes"], [])
            self.assertNotIn("target_id", action)
            self.assertEqual(results[0]["narration"], non_search_narration)
            self.assertEqual(declined.json()["narration"], non_search_narration)
            self.assertNotEqual(declined.json()["narration"], discovered.json()["narration"])

            persisted = reopened_store.get_campaign(campaign_id)
            self.assertEqual(persisted.payload["engine_save"], session.serialize_game_state())
            world = persisted.payload["engine_save"]["world_state"]
            self.assertEqual(world["location"], city_id)
            self.assertEqual(set(world["locations"]), set(saved_world["locations"]))
            self.assertEqual(
                {npc["id"] for npc in world["npcs"]},
                {npc["id"] for npc in saved_world["npcs"]},
            )
            self.assertEqual(world["locations"][tavern_id], saved_world["locations"][tavern_id])
            self.assertEqual(
                world["flags"]["turn_index"], saved_world["flags"]["turn_index"] + 1
            )
            self.assertEqual(len(persisted.history), len(committed.history) + 1)
            self.assertEqual(persisted.history[:-1], committed.history)
            self.assertEqual(persisted.history[-1]["player_message"], declined_body["message"])
            self.assertEqual(persisted.history[-1]["narration"], non_search_narration)

        # Reload the new non-search turn, without issuing any receipt replay.
        final_store = CampaignStore(self.store.path)
        final_manager = SessionManager(campaign_store=final_store)
        final_app = create_app(
            session_manager=final_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=final_app),
            base_url="http://testserver",
        ) as http:
            reloaded = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(reloaded.status_code, 200, reloaded.text)
        final_session = final_manager.get(reloaded.json()["session_id"]).game_session
        self.assertIsNot(final_session, session)
        self.assertEqual(final_session.serialize_game_state(), persisted.payload["engine_save"])
        self.assertEqual(reloaded.json()["state"], declined.json()["state"])
        self.assertEqual(reloaded.json()["history"], persisted.history)
        self.assertEqual(final_store.get_campaign(campaign_id).history, persisted.history)

    async def test_reopened_tavern_distance_question_preserves_entities_and_history(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        original_session = self.manager.get(created["session_id"]).game_session
        turn_url = f"/api/game/sessions/{created['session_id']}/turn"
        discovery_body = {
            "message": "Yakınlarda bir taverna arıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        real_discovery = original_session.run_player_turn
        discovery_results = []

        @wraps(real_discovery)
        def capture_discovery(*args, **kwargs):
            result = real_discovery(*args, **kwargs)
            discovery_results.append(copy.deepcopy(result["action_result"]))
            return result

        with patch.object(original_session, "run_player_turn", new=capture_discovery):
            discovered = await self.http.post(turn_url, json=discovery_body)
        self.assertEqual(discovered.status_code, 200, discovered.text)
        self.assertEqual(len(discovery_results), 1)
        self.assertEqual(discovery_results[0]["action"], "local_search")
        self.assertEqual(discovery_results[0]["status"], "found")
        self.assertTrue(discovery_results[0]["success"])
        tavern_id = discovery_results[0]["target_id"]
        entered = await self.http.post(
            turn_url,
            json={"message": "Enter the tavern.", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(entered.status_code, 200, entered.text)
        self.assertEqual(entered.json()["state"]["location"], tavern_id)
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        self.assertEqual(saved_world["locations"][tavern_id]["scene_kind"], "tavern")
        self.assertEqual(saved_world["locations"][tavern_id]["parent_location_id"], city_id)

        # Use the supported route-distance wording, not a declined search.
        question_body = {
            "message": "Taverna ile Kale arasındaki yol mesafesi kaç kilometre?",
            "action_id": str(uuid.uuid4()),
        }
        self.assertNotEqual(question_body["action_id"], discovery_body["action_id"])
        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            # This question is deterministic; unexpected model calls fail offline.
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            session = reopened_manager.get(session_id).game_session
            self.assertIsNot(session, original_session)
            self.assertEqual(session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(resumed.json()["history"], committed.history)
            self.assertIsNone(
                reopened_store.get_turn_action(campaign_id, question_body["action_id"])
            )
            before = copy.deepcopy(session.world_state)
            real_turn = session.run_player_turn
            results = []

            @wraps(real_turn)
            def capture_question_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result))
                return result

            with patch.object(session, "run_player_turn", new=capture_question_turn):
                question = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=question_body
                )
            self.assertEqual(question.status_code, 200, question.text)
            self.assertEqual(question.json()["action_id"], question_body["action_id"])
            self.assertEqual(len(results), 1)  # A fresh turn, not a receipt replay.
            action = results[0]["action_result"]
            self.assertFalse(action.get("action") == "local_search" and action.get("success"))
            self.assertEqual(action["status"], "unverified")
            narration = results[0]["narration"]
            self.assertIn("ölçüm kaydı yok", narration)
            self.assertEqual(question.json()["narration"], narration)
            self.assertNotEqual(narration, discovered.json()["narration"])

            persisted = reopened_store.get_campaign(campaign_id)
            self.assertEqual(persisted.payload["engine_save"], session.serialize_game_state())
            world = persisted.payload["engine_save"]["world_state"]
            self.assertEqual(world["location"], tavern_id)
            self.assertEqual(set(world["locations"]), set(saved_world["locations"]))
            self.assertEqual(
                {npc["id"] for npc in world["npcs"]},
                {npc["id"] for npc in saved_world["npcs"]},
            )
            # Keep discovered entities unchanged. HTTP turn metadata can refresh
            # scene environment fields independently of the lore-query owner.
            for key in (
                "location", "locations", "npcs", "shops", "features", "doors",
                "containers", "quests", "quest_offers", "inventory",
            ):
                self.assertEqual(session.world_state.get(key), before.get(key), key)
                self.assertEqual(world.get(key), saved_world.get(key), key)
            self.assertEqual(len(persisted.history), len(committed.history) + 1)
            self.assertEqual(persisted.history[:-1], committed.history)
            self.assertEqual(persisted.history[-1]["player_message"], question_body["message"])
            self.assertEqual(persisted.history[-1]["narration"], narration)
            question_receipt = reopened_store.get_turn_action(
                campaign_id, question_body["action_id"]
            )
            self.assertEqual(question_receipt["response"], question.json())

        # Reload the accepted question without reissuing its action ID.
        final_store = CampaignStore(self.store.path)
        final_manager = SessionManager(campaign_store=final_store)
        final_app = create_app(
            session_manager=final_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=final_app),
            base_url="http://testserver",
        ) as http:
            reloaded = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(reloaded.status_code, 200, reloaded.text)
        final_session = final_manager.get(reloaded.json()["session_id"]).game_session
        self.assertIsNot(final_session, session)
        self.assertEqual(final_session.serialize_game_state(), persisted.payload["engine_save"])
        self.assertEqual(reloaded.json()["state"], question.json()["state"])
        self.assertEqual(reloaded.json()["history"], persisted.history)
        self.assertEqual(final_store.get_campaign(campaign_id).history, persisted.history)
        self.assertEqual(
            final_store.get_turn_action(campaign_id, question_body["action_id"]),
            question_receipt,
        )

    async def test_discovered_tavern_visit_city_return_and_revisit_survive_resume(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        session = self.manager.get(created["session_id"]).game_session
        url = f"/api/game/sessions/{created['session_id']}/turn"
        results = []

        # Keep the real engine and HTTP save path; capture only the internal
        # action result, which the public TurnResponse does not expose.
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            results.append(copy.deepcopy(result["action_result"]))
            return result

        search_body = {
            "message": "Yakınlarda bir taverna arıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        enter_body = {
            "message": "Enter the tavern.",
            "action_id": str(uuid.uuid4()),
        }
        with patch.object(session, "run_player_turn", new=capture_turn):
            search = await self.http.post(url, json=search_body)
            self.assertEqual(search.status_code, 200, search.text)
            self.assertEqual(results[-1]["action"], "local_search")
            self.assertEqual(results[-1]["status"], "found")
            tavern_id = results[-1]["target_id"]
            self.assertEqual(search.json()["state"]["location"], city_id)
            city_visits = session.world_state["scene_state"]["scenes"][city_id][
                "visit_revision"
            ]

            enter = await self.http.post(url, json=enter_body)
            self.assertEqual(enter.status_code, 200, enter.text)
            self.assertEqual(results[-1]["action"], "enter")
            self.assertEqual(results[-1]["status"], "completed")
            self.assertEqual(results[-1]["target_id"], tavern_id)
            self.assertEqual(enter.json()["state"]["location"], tavern_id)

        entered_world = session.world_state
        tavern = entered_world["locations"][tavern_id]
        self.assertEqual(tavern["scene_kind"], "tavern")
        self.assertEqual(tavern["parent_location_id"], city_id)
        self.assertEqual(tavern["exit_location_id"], city_id)
        self.assertEqual(
            sum(
                location.get("scene_kind") == "tavern"
                and location.get("parent_location_id") == city_id
                for location in entered_world["locations"].values()
            ),
            1,
        )
        tavern_visits = entered_world["scene_state"]["scenes"][tavern_id][
            "visit_revision"
        ]
        self.assertGreater(tavern_visits, 0)
        self.assertEqual(
            entered_world["scene_state"]["player_position"]["location_id"],
            tavern_id,
        )
        entered_save = copy.deepcopy(session.serialize_game_state())
        self.assertEqual(
            self.store.get_campaign(campaign_id).payload["engine_save"],
            entered_save,
        )

        # A new manager/store must restore the venue and its visit, not
        # reconstruct a second local tavern when the player exits.
        reloaded_store = CampaignStore(self.store.path)
        reloaded_manager = SessionManager(campaign_store=reloaded_store)
        reloaded_app = create_app(
            session_manager=reloaded_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reloaded_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"], enter.json()["state"])
            session_id = resumed.json()["session_id"]
            loaded = reloaded_manager.get(session_id).game_session
            self.assertEqual(loaded.serialize_game_state(), entered_save)
            resumed_world = loaded.world_state
            self.assertEqual(resumed_world["locations"][tavern_id], tavern)
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][tavern_id]["visit_revision"],
                tavern_visits,
            )
            self.assertEqual(
                resumed_world["scene_state"]["player_position"]["location_id"],
                tavern_id,
            )
            locations_before_exit = copy.deepcopy(resumed_world["locations"])
            exit_body = {
                "message": "Tavernadan dışarı çıkıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            real_exit = loaded.run_player_turn
            exit_results = []

            @wraps(real_exit)
            def capture_exit(*args, **kwargs):
                result = real_exit(*args, **kwargs)
                exit_results.append(copy.deepcopy(result["action_result"]))
                return result

            turn_url = f"/api/game/sessions/{session_id}/turn"
            with patch.object(loaded, "run_player_turn", new=capture_exit):
                exit_response = await http.post(turn_url, json=exit_body)
            self.assertEqual(exit_response.status_code, 200, exit_response.text)
            self.assertEqual(exit_results[0]["action"], "exit")
            self.assertEqual(exit_results[0]["status"], "completed")
            self.assertEqual(exit_results[0]["target_id"], city_id)
            self.assertEqual(exit_response.json()["state"]["location"], city_id)
            self.assertEqual(resumed_world["locations"], locations_before_exit)
            self.assertEqual(
                resumed_world["scene_state"]["player_position"]["location_id"],
                city_id,
            )
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][tavern_id]["visit_revision"],
                tavern_visits,
            )
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][city_id]["visit_revision"],
                city_visits + 1,
            )
            exited_save = copy.deepcopy(loaded.serialize_game_state())
            self.assertEqual(
                reloaded_store.get_campaign(campaign_id).payload["engine_save"],
                exited_save,
            )

            # All three receipts must replay historical responses, even though
            # the current location is now different from the search/enter turns.
            with patch.object(
                loaded, "run_player_turn",
                side_effect=AssertionError("Receipt replay must not execute a turn"),
            ):
                for body, original in (
                    (search_body, search),
                    (enter_body, enter),
                    (exit_body, exit_response),
                ):
                    replay = await http.post(turn_url, json=body)
                    self.assertEqual(replay.status_code, 200, replay.text)
                    self.assertEqual(
                        replay.json(), {**original.json(), "session_id": session_id}
                    )
                    self.assertEqual(loaded.serialize_game_state(), exited_save)
            self.assertEqual(
                reloaded_store.get_campaign(campaign_id).payload["engine_save"],
                exited_save,
            )
            self.assertEqual(len(reloaded_store.get_campaign(campaign_id).history), 3)

            # A fresh action is a second visit, not a replay of the first entry.
            revisit_body = {
                "message": "Enter the tavern.",
                "action_id": str(uuid.uuid4()),
            }
            self.assertNotIn(
                revisit_body["action_id"],
                {body["action_id"] for body in (search_body, enter_body, exit_body)},
            )
            revisit_results = []
            real_revisit = loaded.run_player_turn

            @wraps(real_revisit)
            def capture_revisit(*args, **kwargs):
                result = real_revisit(*args, **kwargs)
                revisit_results.append(copy.deepcopy(result["action_result"]))
                return result

            # The real second entry completes in the engine, but a failed
            # autosave must leave both the live session and disk at the exit.
            exited_record = reloaded_manager.get(session_id)
            exited_journal = copy.deepcopy(exited_record.journal)
            exited_memory = copy.deepcopy(exited_record.narrative_memory)
            exited_receipts = copy.deepcopy(exited_record.turn_action_receipts)
            exited_campaign = reloaded_store.get_campaign(campaign_id)
            with (
                patch.object(loaded, "run_player_turn", new=capture_revisit),
                patch.object(
                    reloaded_store,
                    "save_campaign",
                    side_effect=CampaignStorageError("database unavailable"),
                ) as failed_save,
            ):
                failed_revisit = await http.post(turn_url, json=revisit_body)
            failed_save.assert_called_once()
            self.assertEqual(failed_revisit.status_code, 503, failed_revisit.text)
            self.assertEqual(
                failed_revisit.json()["detail"]["code"],
                "campaign_storage_unavailable",
            )
            self.assertNotIn("database unavailable", failed_revisit.text)
            self.assertEqual(len(revisit_results), 1)
            self.assertEqual(revisit_results[0]["action"], "enter")
            self.assertEqual(revisit_results[0]["status"], "completed")
            self.assertEqual(revisit_results[0]["target_id"], tavern_id)
            self.assertEqual(loaded.serialize_game_state(), exited_save)
            self.assertEqual(resumed_world["location"], city_id)
            self.assertEqual(
                resumed_world["scene_state"]["player_position"]["location_id"],
                city_id,
            )
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][tavern_id]["visit_revision"],
                tavern_visits,
            )
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][city_id]["visit_revision"],
                city_visits + 1,
            )
            self.assertEqual(exited_record.journal, exited_journal)
            self.assertEqual(exited_record.narrative_memory, exited_memory)
            self.assertEqual(exited_record.turn_action_receipts, exited_receipts)
            self.assertNotIn(revisit_body["action_id"], exited_record.turn_action_receipts)
            failed_campaign = reloaded_store.get_campaign(campaign_id)
            self.assertEqual(failed_campaign.payload, exited_campaign.payload)
            self.assertEqual(failed_campaign.metadata, exited_campaign.metadata)
            self.assertEqual(failed_campaign.history, exited_campaign.history)
            self.assertEqual(len(failed_campaign.history), 3)
            self.assertIsNone(
                reloaded_store.get_turn_action(campaign_id, revisit_body["action_id"])
            )

            # Independently reopening after the failure must see the city exit,
            # with no uncommitted second visit, history entry, or action receipt.
            failed_resume_store = CampaignStore(self.store.path)
            failed_resume_manager = SessionManager(campaign_store=failed_resume_store)
            failed_resume_app = create_app(
                session_manager=failed_resume_manager,
                ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=failed_resume_app),
                base_url="http://testserver",
            ) as failed_resume_http:
                failed_resume = await failed_resume_http.post(
                    f"/api/game/campaigns/{campaign_id}/resume"
                )
            self.assertEqual(failed_resume.status_code, 200, failed_resume.text)
            self.assertEqual(failed_resume.json()["state"], exit_response.json()["state"])
            failed_resume_record = failed_resume_manager.get(
                failed_resume.json()["session_id"]
            )
            self.assertEqual(
                failed_resume_record.game_session.serialize_game_state(), exited_save
            )
            self.assertEqual(
                failed_resume_store.get_campaign(campaign_id).history,
                exited_campaign.history,
            )
            self.assertIsNone(
                failed_resume_store.get_turn_action(
                    campaign_id, revisit_body["action_id"]
                )
            )

            # Retry the same uncommitted action after storage recovers.
            with patch.object(loaded, "run_player_turn", new=capture_revisit):
                revisit = await http.post(turn_url, json=revisit_body)
            self.assertEqual(revisit.status_code, 200, revisit.text)
            self.assertEqual(len(revisit_results), 2)
            self.assertEqual(revisit_results[-1]["action"], "enter")
            self.assertEqual(revisit_results[-1]["status"], "completed")
            self.assertEqual(revisit_results[-1]["target_id"], tavern_id)
            self.assertEqual(revisit.json()["state"]["location"], tavern_id)
            self.assertEqual(resumed_world["locations"], locations_before_exit)
            self.assertEqual(resumed_world["locations"][tavern_id], tavern)
            self.assertEqual(
                resumed_world["locations"][tavern_id]["parent_location_id"], city_id
            )
            self.assertEqual(
                resumed_world["locations"][tavern_id]["exit_location_id"], city_id
            )
            self.assertEqual(
                resumed_world["scene_state"]["player_position"]["location_id"],
                tavern_id,
            )
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][tavern_id]["visit_revision"],
                tavern_visits + 1,
            )
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][city_id]["visit_revision"],
                city_visits + 1,
            )
            revisited_save = copy.deepcopy(loaded.serialize_game_state())
            self.assertEqual(
                reloaded_store.get_campaign(campaign_id).payload["engine_save"],
                revisited_save,
            )
            self.assertEqual(len(reloaded_store.get_campaign(campaign_id).history), 4)
            self.assertEqual(
                reloaded_store.get_turn_action(
                    campaign_id, revisit_body["action_id"]
                )["response"],
                revisit.json(),
            )

            with patch.object(
                loaded, "run_player_turn",
                side_effect=AssertionError("Revisit replay must not execute a turn"),
            ):
                replay = await http.post(turn_url, json=revisit_body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), revisit.json())
            self.assertEqual(loaded.serialize_game_state(), revisited_save)
            self.assertEqual(
                reloaded_store.get_campaign(campaign_id).payload["engine_save"],
                revisited_save,
            )
            self.assertEqual(len(reloaded_store.get_campaign(campaign_id).history), 4)

        # Another fresh manager must restore the second visit from disk.
        revisited_store = CampaignStore(self.store.path)
        revisited_manager = SessionManager(campaign_store=revisited_store)
        revisited_app = create_app(
            session_manager=revisited_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=revisited_app),
            base_url="http://testserver",
        ) as http:
            restored = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(restored.status_code, 200, restored.text)
            self.assertEqual(restored.json()["state"], revisit.json()["state"])
            restored_session = revisited_manager.get(
                restored.json()["session_id"]
            ).game_session
            self.assertEqual(restored_session.serialize_game_state(), revisited_save)
            restored_world = restored_session.world_state
            self.assertEqual(restored_world["location"], tavern_id)
            self.assertEqual(restored_world["locations"], locations_before_exit)
            self.assertEqual(restored_world["locations"][tavern_id], tavern)
            self.assertEqual(
                restored_world["scene_state"]["player_position"]["location_id"],
                tavern_id,
            )
            self.assertEqual(
                restored_world["scene_state"]["scenes"][tavern_id]["visit_revision"],
                tavern_visits + 1,
            )
            self.assertEqual(
                revisited_store.get_campaign(campaign_id).payload["engine_save"],
                revisited_save,
            )
            self.assertEqual(len(revisited_store.get_campaign(campaign_id).history), 4)

    async def test_stale_resume_keeps_corrected_disclosure_private_to_original_npc(self):
        from api.narrative_memory import build_narrative_context

        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        active_record = self.manager.get(created["session_id"])
        active_session = active_record.game_session
        location_id = active_session.world_state["location"]
        active_session.world_state["npcs"] = [
            {
                "id": "npc_private_mira",
                "name": "Mira",
                "role": "innkeeper",
                "location": location_id,
                "memory": [],
            },
            {
                "id": "npc_private_aldren",
                "name": "Aldren",
                "role": "patron",
                "location": location_id,
                "memory": [],
            },
        ]
        self.manager.save_campaign(campaign_id)
        active_url = f"/api/game/sessions/{created['session_id']}/turn"
        old_body = {
            "message": "Benim adım Arven.",
            "target_id": "npc_private_mira",
            "action_id": str(uuid.uuid4()),
        }
        old_turn = await self.http.post(active_url, json=old_body)
        self.assertEqual(old_turn.status_code, 200, old_turn.text)
        self.assertIn("Arven", old_turn.json()["narration"])
        old_saved = self.store.get_campaign(campaign_id)

        def receipt_rows():
            with closing(sqlite3.connect(self.store.path)) as connection:
                return connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id",
                    (campaign_id,),
                ).fetchall()

        stale_store = CampaignStore(self.store.path)
        stale_manager = SessionManager(campaign_store=stale_store)
        stale_app = create_app(
            session_manager=stale_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=stale_app),
            base_url="http://testserver",
        ) as stale_http:
            resume_url = f"/api/game/campaigns/{campaign_id}/resume"
            first_resume = await stale_http.post(resume_url)
            self.assertEqual(first_resume.status_code, 200, first_resume.text)
            stale_id = first_resume.json()["session_id"]
            stale_record = stale_manager.get(stale_id)
            stale_session = stale_record.game_session
            self.assertIsNot(stale_session, active_session)
            stale_memory = copy.deepcopy(stale_record.narrative_memory)
            self.assertEqual(stale_memory, old_saved.payload["narrative_memory"])

            corrected_body = {
                "message": "Benim adım Rowan.",
                "target_id": "npc_private_mira",
                "action_id": str(uuid.uuid4()),
            }
            corrected_turn = await self.http.post(active_url, json=corrected_body)
            self.assertEqual(corrected_turn.status_code, 200, corrected_turn.text)
            self.assertIn("Rowan", corrected_turn.json()["narration"])
            latest = self.store.get_campaign(campaign_id)
            self.assertEqual(latest.history[:-1], old_saved.history)
            self.assertNotEqual(latest.payload["narrative_memory"], stale_memory)
            self.assertEqual(stale_record.narrative_memory, stale_memory)
            prior_receipts = receipt_rows()
            self.assertEqual(len(prior_receipts), 2)

            # Refresh the older manager, rather than opening a third manager.
            refreshed = await stale_http.post(resume_url)
            self.assertEqual(refreshed.status_code, 200, refreshed.text)
            self.assertEqual(refreshed.json()["session_id"], stale_id)
            self.assertIs(stale_manager.get(stale_id), stale_record)
            self.assertIs(stale_record.game_session, stale_session)
            self.assertEqual(refreshed.json()["history"], latest.history)
            self.assertEqual(
                stale_session.serialize_game_state(), latest.payload["engine_save"]
            )
            self.assertEqual(
                stale_record.narrative_memory, latest.payload["narrative_memory"]
            )
            after_resume = stale_store.get_campaign(campaign_id)
            self.assertEqual(after_resume.payload, latest.payload)
            self.assertEqual(after_resume.history, latest.history)
            self.assertEqual(after_resume.metadata["revision"], latest.metadata["revision"])
            self.assertEqual(receipt_rows(), prior_receipts)

            npc_a, npc_b = stale_session.world_state["npcs"]
            a_memory = copy.deepcopy(npc_a["memory"])
            self.assertEqual(npc_b["memory"], [])
            self.assertEqual(
                [entry["text"] for entry in a_memory if entry["speaker"] == "player"],
                [old_body["message"], corrected_body["message"]],
            )
            recall_body = {
                "message": "Bana adımla hitap et",
                "target_id": "npc_private_aldren",
                "action_id": str(uuid.uuid4()),
            }
            packet, _ = build_narrative_context(
                stale_record.narrative_memory,
                game.build_world_context(npc_target=npc_b, session=stale_session),
                recall_body["message"],
                {"npc_id": npc_b["id"]},
            )
            recent_players = [
                turn["player"]
                for turn in packet["relevant_continuity"]["recent_turns"]
            ]
            self.assertNotIn(old_body["message"], recent_players)
            self.assertNotIn(corrected_body["message"], recent_players)

            real_turn = stale_session.run_player_turn
            results = []

            @wraps(real_turn)
            def capture_recall(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result["action_result"]))
                return result

            with patch.object(stale_session, "run_player_turn", new=capture_recall):
                recall = await stale_http.post(
                    f"/api/game/sessions/{stale_id}/turn", json=recall_body
                )
            self.assertEqual(recall.status_code, 200, recall.text)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["npc_id"], npc_b["id"])
            self.assertEqual(results[0]["status"], "answered_from_npc_memory")
            self.assertIn("Aldren", recall.json()["narration"])
            for private_name in ("Arven", "Rowan", "Mira"):
                self.assertNotIn(private_name, recall.json()["narration"])
            self.assertEqual(npc_a["memory"], a_memory)
            self.assertFalse(any(
                "Arven" in entry["text"] or "Rowan" in entry["text"]
                for entry in npc_b["memory"]
            ))

            after_recall = stale_store.get_campaign(campaign_id)
            self.assertEqual(after_recall.history[:-1], latest.history)
            self.assertEqual(after_recall.history[-1]["player_message"], recall_body["message"])
            self.assertEqual(after_recall.history[-1]["narration"], recall.json()["narration"])
            self.assertEqual(after_recall.metadata["revision"], latest.metadata["revision"] + 1)
            final_receipts = receipt_rows()
            self.assertEqual(len(final_receipts), len(prior_receipts) + 1)
            for receipt in prior_receipts:
                self.assertIn(receipt, final_receipts)
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, recall_body["action_id"])["response"],
                recall.json(),
            )
            self.assertEqual(
                after_recall.payload["narrative_memory"], stale_record.narrative_memory
            )

    async def test_stale_resume_refreshes_journal_and_conversation_memory(self):
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        active_id = created["session_id"]
        active_record = self.manager.get(active_id)
        active_session = active_record.game_session
        location_id = active_session.world_state["location"]
        active_session.world_state["npcs"] = [
            {
                "id": "npc_resume_mira",
                "name": "Mira",
                "role": "innkeeper",
                "location": location_id,
                "memory": [],
            },
            {
                "id": "npc_resume_aldren",
                "name": "Aldren",
                "role": "patron",
                "location": location_id,
                "memory": [],
            },
        ]
        self.manager.save_campaign(campaign_id)
        active_url = f"/api/game/sessions/{active_id}/turn"
        old_body = {
            "message": "Benim adım Arven.",
            "target_id": "npc_resume_mira",
            "action_id": str(uuid.uuid4()),
        }
        old_turn = await self.http.post(active_url, json=old_body)
        self.assertEqual(old_turn.status_code, 200, old_turn.text)
        self.assertIn("Arven", old_turn.json()["narration"])
        old_saved = self.store.get_campaign(campaign_id)
        old_receipt = self.store.get_turn_action(campaign_id, old_body["action_id"])

        stale_store = CampaignStore(self.store.path)
        stale_manager = SessionManager(campaign_store=stale_store)
        stale_app = create_app(
            session_manager=stale_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=stale_app),
            base_url="http://testserver",
        ) as stale_http:
            resume_url = f"/api/game/campaigns/{campaign_id}/resume"
            first_resume = await stale_http.post(resume_url)
            self.assertEqual(first_resume.status_code, 200, first_resume.text)
            stale_id = first_resume.json()["session_id"]
            stale_record = stale_manager.get(stale_id)
            stale_session = stale_record.game_session
            self.assertIsNot(stale_session, active_session)
            stale_engine = copy.deepcopy(stale_session.serialize_game_state())
            stale_journal = copy.deepcopy(stale_record.journal)
            stale_memory = copy.deepcopy(stale_record.narrative_memory)
            stale_version = stale_session._campaign_persistence_version
            self.assertEqual(stale_journal, old_saved.payload["journal"])
            self.assertEqual(stale_memory, old_saved.payload["narrative_memory"])
            self.assertEqual(first_resume.json()["history"], old_saved.history)
            self.assertEqual(
                {npc["npc_id"] for npc in stale_journal["known_npcs"]},
                {"npc_resume_mira"},
            )

            new_body = {
                "message": "Benim adım Rowan.",
                "target_id": "npc_resume_mira",
                "action_id": str(uuid.uuid4()),
            }
            meet_body = {
                "message": "Adın ne?",
                "target_id": "npc_resume_aldren",
                "action_id": str(uuid.uuid4()),
            }
            new_turn = await self.http.post(active_url, json=new_body)
            meet_turn = await self.http.post(active_url, json=meet_body)
            for response in (new_turn, meet_turn):
                self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("Rowan", new_turn.json()["narration"])
            self.assertIn("Aldren", meet_turn.json()["narration"])
            latest = self.store.get_campaign(campaign_id)
            self.assertNotEqual(latest.payload["journal"], stale_journal)
            self.assertNotEqual(latest.payload["narrative_memory"], stale_memory)
            self.assertEqual(latest.history[:len(old_saved.history)], old_saved.history)
            self.assertEqual(len(latest.history), len(old_saved.history) + 2)
            receipts = {
                body["action_id"]: self.store.get_turn_action(
                    campaign_id, body["action_id"]
                )
                for body in (old_body, new_body, meet_body)
            }
            self.assertEqual(receipts[old_body["action_id"]], old_receipt)
            # Another manager's accepted turns must not silently update this cache.
            self.assertEqual(stale_session.serialize_game_state(), stale_engine)
            self.assertEqual(stale_record.journal, stale_journal)
            self.assertEqual(stale_record.narrative_memory, stale_memory)
            self.assertEqual(stale_session._campaign_persistence_version, stale_version)

            resumed = await stale_http.post(resume_url)
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["session_id"], stale_id)
            self.assertIs(stale_manager.get(stale_id), stale_record)
            self.assertIs(stale_record.game_session, stale_session)
            self.assertEqual(
                stale_session.serialize_game_state(), latest.payload["engine_save"]
            )
            self.assertEqual(
                stale_session._campaign_persistence_version,
                (campaign_id, latest.metadata["revision"]),
            )
            self.assertEqual(stale_record.journal, latest.payload["journal"])
            self.assertEqual(
                stale_record.narrative_memory, latest.payload["narrative_memory"]
            )
            self.assertEqual(resumed.json()["state"]["journal"], stale_record.journal)
            self.assertEqual(resumed.json()["history"], latest.history)
            self.assertEqual(
                {npc["npc_id"] for npc in stale_record.journal["known_npcs"]},
                {"npc_resume_mira", "npc_resume_aldren"},
            )
            refreshed = stale_store.get_campaign(campaign_id)
            self.assertEqual(refreshed.payload, latest.payload)
            self.assertEqual(refreshed.history, latest.history)
            stale_url = f"/api/game/sessions/{stale_id}/turn"
            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Saved turns must replay without execution"),
                ),
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Replay must not save another turn"),
                ),
            ):
                for body, response in (
                    (old_body, old_turn), (new_body, new_turn), (meet_body, meet_turn)
                ):
                    replay = await stale_http.post(stale_url, json=body)
                    self.assertEqual(replay.status_code, 200, replay.text)
                    expected = response.json()
                    expected["session_id"] = stale_id
                    self.assertEqual(replay.json(), expected)
            self.assertEqual(stale_store.get_campaign(campaign_id), refreshed)
            self.assertEqual(stale_record.journal, latest.payload["journal"])
            self.assertEqual(
                stale_record.narrative_memory, latest.payload["narrative_memory"]
            )

            recall_body = {
                "message": "Bana adımla hitap et",
                "target_id": "npc_resume_mira",
                "action_id": str(uuid.uuid4()),
            }
            recall = await stale_http.post(stale_url, json=recall_body)
            self.assertEqual(recall.status_code, 200, recall.text)
            self.assertIn("Mira", recall.json()["narration"])
            self.assertIn("Rowan", recall.json()["narration"])
            self.assertNotIn("Arven", recall.json()["narration"])
            after_recall = stale_store.get_campaign(campaign_id)
            self.assertEqual(after_recall.history[:-1], latest.history)
            self.assertEqual(
                after_recall.history[-1]["player_message"], recall_body["message"]
            )
            self.assertEqual(after_recall.payload["journal"], stale_record.journal)
            self.assertEqual(
                after_recall.payload["narrative_memory"], stale_record.narrative_memory
            )
            for action_id, receipt in receipts.items():
                self.assertEqual(
                    stale_store.get_turn_action(campaign_id, action_id), receipt
                )
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, recall_body["action_id"])[
                    "response"
                ],
                recall.json(),
            )

    async def test_reopened_city_ruler_question_does_not_answer_with_npc_identity(self):
        # A default campaign has no loaded ruler evidence. Seed only the local
        # scene, as in the living-world regression; do not script query routing.
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        original_session = self.manager.get(created["session_id"]).game_session
        world = original_session.world_state
        local_npcs = [
            {
                "id": "npc_v11_world_subject",
                "name": "Melis",
                "role": "Kent sakini",
                "location": world["location"],
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            },
            {
                "id": "npc_v11_world_subject_other",
                "name": "Darian",
                "role": "Yolcu",
                "location": world["location"],
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            },
        ]
        world["npcs"].extend(local_npcs)
        world["flags"]["active_npc_id"] = local_npcs[0]["id"]
        world["flags"]["active_npc_until_turn"] = world["flags"]["turn_index"] + 6
        saved = await self.http.post(f"/api/game/campaigns/{campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        self.assertEqual(saved_world["npcs"], world["npcs"])
        requests = [
            {
                "message": "Bu şehrin hükümdarı kim?",
                "target_id": local_npcs[0]["id"],
                "action_id": str(uuid.uuid4()),
            },
            {
                "message": "Bu şehrin hükümdarı kim?",
                "action_id": str(uuid.uuid4()),
            },
        ]
        self.assertNotEqual(requests[0]["action_id"], requests[1]["action_id"])
        receipts = {}
        narrations = []

        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            # The real engine answers this deterministically. Any model call
            # fails offline rather than supplying a scripted identity answer.
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            record = reopened_manager.get(session_id)
            session = record.game_session
            self.assertIsNot(session, original_session)
            self.assertEqual(session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(resumed.json()["history"], committed.history)
            real_turn = session.run_player_turn
            results = []

            @wraps(real_turn)
            def capture_question_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result))
                return result

            with patch.object(session, "run_player_turn", new=capture_question_turn):
                for index, body in enumerate(requests):
                    with self.subTest(target_id=body.get("target_id")):
                        self.assertEqual(
                            session.world_state["flags"]["active_npc_id"],
                            local_npcs[0]["id"],
                        )
                        self.assertGreaterEqual(
                            session.world_state["flags"]["active_npc_until_turn"],
                            session.world_state["flags"]["turn_index"],
                        )
                        self.assertIsNone(
                            reopened_store.get_turn_action(campaign_id, body["action_id"])
                        )
                        before = reopened_store.get_campaign(campaign_id)
                        response = await http.post(
                            f"/api/game/sessions/{session_id}/turn", json=body
                        )
                        self.assertEqual(response.status_code, 200, response.text)
                        turn = response.json()
                        self.assertEqual(turn["action_id"], body["action_id"])
                        self.assertEqual(len(results), index + 1)  # Not receipt replay.
                        action = results[-1]["action_result"]
                        self.assertEqual(action["action"], "dialogue")
                        self.assertEqual(action["status"], "unverified")
                        self.assertFalse(action["success"])
                        self.assertEqual(action["state_changes"], [])
                        self.assertNotIn("npc_id", action)
                        narration = results[-1]["narration"]
                        self.assertIn("güvenilir bir doğrulamam yok", narration)
                        for npc in local_npcs:
                            self.assertNotIn(npc["name"], narration)
                        self.assertEqual(turn["narration"], narration)
                        narrations.append(narration)

                        persisted = reopened_store.get_campaign(campaign_id)
                        self.assertEqual(
                            persisted.payload["engine_save"], session.serialize_game_state()
                        )
                        self.assertEqual(persisted.payload["journal"], record.journal)
                        persisted_world = persisted.payload["engine_save"]["world_state"]
                        for key in (
                            "location", "locations", "npcs", "shops", "features",
                            "doors", "containers", "quests", "quest_offers", "inventory",
                        ):
                            self.assertEqual(persisted_world.get(key), saved_world.get(key), key)
                        self.assertEqual(
                            persisted_world["flags"]["turn_index"],
                            saved_world["flags"]["turn_index"] + index + 1,
                        )
                        self.assertEqual(persisted.history[:-1], before.history)
                        self.assertEqual(len(persisted.history), len(before.history) + 1)
                        self.assertEqual(
                            persisted.history[-1]["player_message"], body["message"]
                        )
                        self.assertEqual(persisted.history[-1]["narration"], narration)
                        receipt = reopened_store.get_turn_action(campaign_id, body["action_id"])
                        self.assertEqual(receipt["response"], turn)
                        receipts[body["action_id"]] = copy.deepcopy(receipt)

        # Reopen again without sending either action: both accepted questions,
        # their narration and the unchanged local identities must be durable.
        final_store = CampaignStore(self.store.path)
        final_manager = SessionManager(campaign_store=final_store)
        _, final_record, _, final_history, _ = final_manager.resume_campaign(campaign_id)
        self.assertIsNot(final_record.game_session, session)
        self.assertEqual(
            final_record.game_session.serialize_game_state(), persisted.payload["engine_save"]
        )
        self.assertEqual(final_record.journal, persisted.payload["journal"])
        self.assertEqual(final_history, persisted.history)
        self.assertEqual(final_store.get_campaign(campaign_id).history, persisted.history)
        self.assertEqual(
            [entry["player_message"] for entry in final_history[-2:]],
            [body["message"] for body in requests],
        )
        self.assertEqual([entry["narration"] for entry in final_history[-2:]], narrations)
        for action_id, receipt in receipts.items():
            self.assertEqual(final_store.get_turn_action(campaign_id, action_id), receipt)
            self.assertEqual(final_manager.get_turn_action(final_record, action_id), receipt)

    async def test_selected_npc_identity_query_is_deterministic(self):
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "name": "Selected NPC identity target regression",
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": "fr:city:neverwinter",
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        session = self.manager.get(created["session_id"]).game_session

        look_response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Etrafıma bakıyorum."},
        )
        self.assertEqual(look_response.status_code, 200, look_response.text)
        npc = session.world_state["npcs"][0]

        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Adın ne?", "target_id": npc["id"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        turn = response.json()
        self.assertIn(npc["name"], turn["narration"])
        self.assertIn(npc["role"], turn["narration"])

    async def test_create_list_detail_resume_and_safe_metadata(self):
        created = await self.create_campaign()
        self.assertTrue(created["campaign_id"])
        self.assertTrue(created["session_id"])
        self.assertEqual(created["history"], [])
        self.assertEqual(
            set(created["state"]["journal"]),
            {
                "schema_version",
                "discovered_locations",
                "known_npcs",
                "notable_events",
                "quests",
            },
        )
        self.assertEqual(created["state"]["journal"]["quests"], [])

        campaign_id = created["campaign_id"]
        listed = await self.http.get("/api/game/campaigns")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["campaign_id"], campaign_id)
        self.assertNotIn("engine_hash", listed.text)
        self.assertNotIn("payload_json", listed.text)
        self.assertNotIn("world_state", listed.text)

        detail = await self.http.get(f"/api/game/campaigns/{campaign_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["state"], created["state"])
        self.assertEqual(detail.json()["campaign"]["name"], created["name"])

        resumed = await self.http.post(
            f"/api/game/campaigns/{campaign_id}/resume"
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["campaign_id"], campaign_id)
        self.assertEqual(resumed.json()["state"], created["state"])

    async def test_character_options_and_custom_creation_are_engine_canonical(self):
        options = await self.http.get("/api/game/character-options")
        self.assertEqual(options.status_code, 200)
        self.assertEqual(options.json(), {"races": game.RACES, "classes": game.CLASSES})

        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "character": {
                    "mode": "custom",
                    "name": "  Arven  ",
                    "race": "Elf",
                    "class": "Wizard",
                    "background": "Sage",
                    "alignment": "Neutral Good",
                    "ability_score_method": "standard_array",
                    "ability_scores": {
                        "intelligence": 15,
                        "dexterity": 14,
                        "constitution": 13,
                        "wisdom": 12,
                        "charisma": 10,
                        "strength": 8,
                    },
                    "background_ability_bonuses": {
                        "intelligence": 2,
                        "constitution": 1,
                    },
                    "proficient_skills": [
                        "Arcana",
                        "History",
                        "Investigation",
                        "Insight",
                    ],
                    "languages": ["Common", "Dwarvish", "Elvish"],
                    "background_equipment_option": "A",
                    "equipment_package": "A",
                    "cantrips": ["Fire Bolt", "Mage Hand", "Light"],
                    "spells": [
                        "Magic Missile",
                        "Shield",
                        "Mage Armor",
                        "Detect Magic",
                        "Thunderwave",
                        "Sleep",
                    ],
                }
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        character = created["state"]["character"]
        self.assertEqual(
            (character["name"], character["race"], character["class"]),
            ("Arven", "Elf", "Wizard"),
        )

        session = self.manager.get(created["session_id"]).game_session
        engine_character = session.character
        self.assertEqual(engine_character["level"], 1)
        self.assertEqual(engine_character["proficiency_bonus"], 2)
        self.assertEqual(engine_character["current_hp"], engine_character["max_hp"])
        self.assertEqual(
            engine_character["max_hp"],
            session.calculate_hp(
                "Wizard", session.get_modifier(engine_character["constitution"])
            ),
        )
        self.assertEqual(
            engine_character["armor_class"],
            session.calculate_ac(
                "Wizard",
                session.get_modifier(engine_character["dexterity"]),
                session.get_modifier(engine_character["constitution"]),
                session.get_modifier(engine_character["wisdom"]),
            ),
        )
        self.assertTrue(
            all(
                3 <= engine_character[ability] <= 18
                for ability in (
                    "strength",
                    "dexterity",
                    "constitution",
                    "intelligence",
                    "wisdom",
                    "charisma",
                )
            )
        )
        self.assertEqual(len(engine_character["proficient_skills"]), 4)
        self.assertTrue(
            set(engine_character["proficient_skills"])
            <= set(game.CLASS_SKILL_OPTIONS["Wizard"])
        )
        for ability in (
            "strength",
            "dexterity",
            "constitution",
            "intelligence",
            "wisdom",
            "charisma",
        ):
            self.assertEqual(character[ability], engine_character[ability])

        restarted_manager = SessionManager(campaign_store=self.store)
        restarted_app = create_app(
            session_manager=restarted_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted_app),
            base_url="http://testserver",
        ) as restarted_http:
            resumed = await restarted_http.post(
                f"/api/game/campaigns/{created['campaign_id']}/resume"
            )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["state"], created["state"])

    async def test_random_creation_and_invalid_character_choices(self):
        random_response = await self.http.post(
            "/api/game/campaigns",
            json={"character": {"mode": "random"}},
        )
        self.assertEqual(random_response.status_code, 200, random_response.text)
        random_character = random_response.json()["state"]["character"]
        self.assertIn(random_character["name"], game.RANDOM_NAMES)
        self.assertIn(random_character["race"], game.RACES)
        self.assertIn(random_character["class"], game.CLASSES)
        valid_skills = game.CLASS_SKILL_OPTIONS[random_character["class"]]
        expected_class_skill_count = 4 if random_character["class"] == "Rogue" else 2
        species_bonus_skills = set(random_character["species_bonus_skills"])
        expected_species_skill_count = SPECIES_DEFINITIONS[
            random_character["race"]
        ].get("skill_bonus_count", 0)
        expected_skill_count = (
            expected_class_skill_count + expected_species_skill_count
        )
        self.assertEqual(len(random_character["proficient_skills"]), expected_skill_count)
        self.assertEqual(len(species_bonus_skills), expected_species_skill_count)
        self.assertTrue(
            species_bonus_skills <= set(random_character["proficient_skills"])
        )
        self.assertTrue(
            set(random_character["proficient_skills"])
            <= set(valid_skills) | species_bonus_skills
        )

        invalid_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "character": {
                    "mode": "custom",
                    "name": "Arven",
                    "race": "Not a supported race",
                    "class": "Wizard",
                }
            },
        )
        self.assertEqual(invalid_response.status_code, 422)
        self.assertEqual(
            invalid_response.json()["detail"]["code"],
            "invalid_character",
        )

        forged_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "character": {
                    "mode": "custom",
                    "name": "Arven",
                    "race": "Elf",
                    "class": "Wizard",
                    "max_hp": 999,
                }
            },
        )
        self.assertEqual(forged_response.status_code, 422)

        listed = await self.http.get("/api/game/campaigns")
        self.assertEqual(len(listed.json()), 1)

    async def test_character_creation_rejects_empty_malformed_and_authoritative_fields(self):
        invalid_requests = [
            {
                "character": {
                    "mode": "custom",
                    "name": "   ",
                    "race": "Human",
                    "class": "Fighter",
                }
            },
            {
                "character": {
                    "mode": "custom",
                    "name": "A" * 41,
                    "race": "Human",
                    "class": "Fighter",
                }
            },
            {
                "character": {
                    "mode": "custom",
                    "name": 27,
                    "race": "Human",
                    "class": "Fighter",
                }
            },
            {
                "character": {
                    "mode": "custom",
                    "name": "Arven",
                    "race": "Human",
                }
            },
            {
                "character": {
                    "mode": "custom",
                    "name": "Arven",
                    "race": "Human",
                    "class": "Unsupported Class",
                }
            },
            {
                "character": {
                    "mode": "random",
                    "name": "Client-selected",
                }
            },
            {
                "character": {
                    "mode": "custom",
                    "name": "Arven",
                    "race": "Human",
                    "class": "Fighter",
                    "current_hp": 1,
                    "max_hp": 999,
                    "armor_class": 99,
                    "inventory": ["Forged item"],
                    "combat": {"active": True},
                    "level": 20,
                    "proficiency_bonus": 99,
                    "strength": 30,
                }
            },
        ]
        for body in invalid_requests:
            with self.subTest(body=body):
                response = await self.http.post("/api/game/campaigns", json=body)
                self.assertEqual(response.status_code, 422, response.text)

        listed = await self.http.get("/api/game/campaigns")
        self.assertEqual(listed.json(), [])

    async def test_campaign_creation_ids_and_sessions_are_isolated(self):
        async def create(name, race, character_class):
            if character_class == "Wizard":
                char_payload = {
                    "mode": "custom",
                    "name": name,
                    "race": race,
                    "class": character_class,
                    "background": "Sage",
                    "alignment": "Neutral Good",
                    "ability_score_method": "standard_array",
                    "ability_scores": {
                        "intelligence": 15,
                        "dexterity": 14,
                        "constitution": 13,
                        "wisdom": 12,
                        "charisma": 10,
                        "strength": 8,
                    },
                    "background_ability_bonuses": {
                        "intelligence": 2,
                        "constitution": 1,
                    },
                    "proficient_skills": [
                        "Arcana",
                        "History",
                        "Investigation",
                        "Insight",
                    ],
                    "languages": ["Common", "Dwarvish", "Elvish"],
                    "background_equipment_option": "A",
                    "equipment_package": "A",
                    "cantrips": ["Fire Bolt", "Mage Hand", "Light"],
                    "spells": [
                        "Magic Missile",
                        "Shield",
                        "Mage Armor",
                        "Detect Magic",
                        "Thunderwave",
                        "Sleep",
                    ],
                }
            else:
                char_payload = {
                    "mode": "custom",
                    "name": name,
                    "race": race,
                    "class": character_class,
                    "background": "Acolyte",
                    "alignment": "Lawful Good",
                    "ability_score_method": "standard_array",
                    "ability_scores": {
                        "wisdom": 15,
                        "constitution": 14,
                        "strength": 13,
                        "dexterity": 12,
                        "intelligence": 10,
                        "charisma": 8,
                    },
                    "background_ability_bonuses": {
                        "wisdom": 2,
                        "intelligence": 1,
                    },
                    "proficient_skills": [
                        "Insight",
                        "Religion",
                        "History",
                        "Medicine",
                    ],
                    "languages": ["Common", "Dwarvish", "Elvish"],
                    "background_equipment_option": "A",
                    "equipment_package": "A",
                    "cantrips": ["Light", "Sacred Flame", "Thaumaturgy"],
                    "spells": ["Bless", "Cure Wounds"],
                }
            response = await self.http.post(
                "/api/game/campaigns",
                json={"character": char_payload},
            )
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()

        first = await create("Arven", "Elf", "Wizard")
        second = await create("Mira", "Dwarf", "Cleric")
        self.assertNotEqual(first["campaign_id"], second["campaign_id"])
        self.assertNotEqual(first["session_id"], second["session_id"])

        first_session = self.manager.get(first["session_id"]).game_session
        second_session = self.manager.get(second["session_id"]).game_session
        second_before = copy.deepcopy(second_session.serialize_game_state())
        first_session.character["name"] = "Changed only in the first session"
        first_session.world_state["inventory"].append("Isolation check")
        self.assertEqual(second_session.serialize_game_state(), second_before)

        for response in (first, second):
            self.assertNotIn("OLLAMA_PROXY_TOKEN", str(response))
            self.assertNotIn("SESSION_SECRET", str(response))
            self.assertNotIn("Authorization", str(response))

    async def test_blank_target_id_is_rejected(self):
        created = await self.create_campaign()
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Bandit'e saldırıyorum.", "target_id": "   "},
        )
        self.assertEqual(response.status_code, 422, response.text)

    async def test_attack_turn_returns_only_safe_structured_combat_result(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        target = {
            "id": "npc_bandit",
            "name": "Bandit",
            "role": "bandit",
            "location": session.world_state["location"],
            "max_hp": 14,
            "current_hp": 7,
            "armor_class": 12,
            # Serializer fixture only: satisfy authoritative range validation.
            # This injected distance is not native production encounter evidence.
            "distance_ft": 5,
            "combat_status": "active",
            "memory": [],
        }
        session.world_state["npcs"].append(target)
        with patch.object(session.rng, "randint", side_effect=[20, 1]):
            session.start_combat(target)
        received_target_ids = []

        def attack_turn(_message, *, target_id=None):
            received_target_ids.append(target_id)
            return {
                "narration": "The blade catches the bandit.",
                "action_result": {
                    "action": "attack",
                    "status": "resolved",
                    "success": True,
                    "outcome": "critical_hit",
                    "actor": "player",
                    "target": "npc_bandit",
                    "target_id": "npc_bandit",
                    "target_name": "Bandit",
                    "weapon": "Longsword",
                    "attack_roll": 20,
                    "attack_bonus": 4,
                    "attack_total": 24,
                    "target_ac": 12,
                    "critical": True,
                    "damage": 7,
                    "target_hp_before": 14,
                    "target_hp_after": 7,
                    "target_status": "active",
                    "combat_started": True,
                    "combat_ended": False,
                    "enemy_action": {
                        "action": "enemy_attack",
                        "status": "resolved",
                        "success": True,
                        "outcome": "hit",
                        "actor": "npc_bandit",
                        "target": "player",
                        "target_id": "player",
                        "target_name": "Arven",
                        "weapon": "Dagger",
                        "attack_roll": 12,
                        "attack_bonus": 2,
                        "attack_total": 14,
                        "target_ac": 13,
                        "critical": False,
                        "damage": 2,
                        "target_hp_before": 11,
                        "target_hp_after": 9,
                        "target_status": "active",
                        "direct_response": "must not leave the engine",
                    },
                    "enemy_actions": [
                        {
                            "action": "enemy_attack",
                            "actor": "npc_bandit",
                            "actor_name": "Bandit",
                            "outcome": "hit",
                            "attack_roll": 12,
                            "damage": 2,
                            "private_state": "must not leave the engine",
                        },
                        {
                            "action": "enemy_attack",
                            "actor": "npc_archer",
                            "actor_name": "Archer",
                            "outcome": "miss",
                            "attack_roll": 4,
                            "damage": 0,
                            "private_state": "must not leave the engine",
                        },
                    ],
                    "direct_response": "must not leave the engine",
                    "state_changes": {"private": "must not leave the engine"},
                },
            }

        session.run_player_turn = attack_turn
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Bandit'e saldırıyorum.", "target_id": "npc_bandit"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(received_target_ids, ["npc_bandit"])
        result = response.json()["combat_result"]
        self.assertEqual(result["outcome"], "critical_hit")
        self.assertEqual(result["attack_roll"], 20)
        self.assertEqual(result["damage"], 7)
        self.assertEqual(result["enemy_action"]["attack_total"], 14)
        self.assertEqual(result["enemy_action"]["damage"], 2)
        self.assertNotIn("direct_response", result)
        self.assertNotIn("state_changes", result)
        self.assertNotIn("direct_response", result["enemy_action"])
        self.assertEqual(
            [(enemy["actor"], enemy["actor_name"], enemy["outcome"])
             for enemy in result["enemy_actions"]],
            [
                ("npc_bandit", "Bandit", "hit"),
                ("npc_archer", "Archer", "miss"),
            ],
        )
        self.assertNotIn("private_state", result["enemy_actions"][0])
        history_entry = response.json()["combat_history_entry"]
        self.assertEqual(history_entry["result"], result)
        self.assertRegex(
            history_entry["event_id"],
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        )
        self.assertEqual(history_entry["turn_index"], response.json()["state"]["turn_index"])
        self.assertNotIn("direct_response", history_entry["result"])
        self.assertNotIn("state_changes", history_entry["result"])

        detail = await self.http.get(
            f"/api/game/campaigns/{created['campaign_id']}"
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["combat_history"], [history_entry])
        resumed = await self.http.post(
            f"/api/game/campaigns/{created['campaign_id']}/resume"
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["combat_history"], [history_entry])

    async def test_engine_failure_does_not_append_campaign_combat_history(self):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        saved_before = self.store.get_campaign(created["campaign_id"]).payload

        def fail_after_mutation(_message):
            record.game_session.character["current_hp"] = 0
            record.game_session.world_state["inventory"].clear()
            raise RuntimeError("private engine failure")

        record.game_session.run_player_turn = fail_after_mutation
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "I attack."},
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            self.store.get_campaign(created["campaign_id"]).payload,
            saved_before,
        )
        self.assertEqual(
            self.store.get_campaign(created["campaign_id"]).combat_history,
            [],
        )
        self.assertEqual(record.combat_history, [])

    async def test_skill_check_turn_returns_only_allowlisted_canonical_result(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        session.character["modifiers"]["wisdom"] = 2
        session.character["modifiers"]["strength"] = 3
        session.character["proficient_skills"] = ["Perception"]
        session.character["proficiency_bonus"] = 2

        def perception_turn(_message):
            return {
                "narration": "Bir ses duyuyorsun.",
                "action_result": {
                    "action": "skill_check",
                    "skill": "Perception",
                    "ability": "wisdom",
                    "dice": 14,
                    "modifier": 2,
                    "proficiency_bonus": 2,
                    "total": 18,
                    "dc": 15,
                    "outcome": "success",
                    "success": True,
                    "status": "resolved",
                    "target_type": "door",
                    "direct_response": "must not leave the engine",
                    "state_changes": ["private"],
                    "model_result": {"d20": 20, "outcome": "critical_success"},
                },
            }

        session.run_player_turn = perception_turn
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Kapının arkasından ses dinliyorum."},
        )

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["skill_check_result"]
        self.assertEqual(
            result,
            {
                "skill": "Perception",
                "ability": "wisdom",
                "d20": 14,
                "proficient": True,
                "ability_modifier": 2,
                "proficiency_modifier": 2,
                "total_modifier": 4,
                "total": 18,
                "difficulty": "medium",
                "dc": 15,
                "outcome": "success",
            },
        )
        self.assertNotIn("direct_response", result)
        self.assertNotIn("state_changes", result)
        self.assertNotIn("model_result", result)
        self.assertIsNone(response.json()["combat_result"])

        def athletics_turn(_message):
            return {
                "narration": "Tırmanışın başarılı olur.",
                "action_result": {
                    "action": "skill_check",
                    "skill": "Athletics",
                    "ability": "strength",
                    "dice": 13,
                    "modifier": 3,
                    "proficiency_bonus": 0,
                    "total": 16,
                    "dc": 15,
                    "outcome": "success",
                    "success": True,
                    "status": "resolved",
                    "state_changes": ["private"],
                },
            }

        session.run_player_turn = athletics_turn
        nonproficient_response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Tırmanıyorum."},
        )
        self.assertEqual(
            nonproficient_response.status_code,
            200,
            nonproficient_response.text,
        )
        nonproficient = nonproficient_response.json()["skill_check_result"]
        self.assertEqual(nonproficient["skill"], "Athletics")
        self.assertEqual(nonproficient["ability"], "strength")
        self.assertFalse(nonproficient["proficient"])
        self.assertEqual(nonproficient["proficiency_modifier"], 0)
        self.assertEqual(nonproficient["total_modifier"], 3)
        self.assertEqual(nonproficient["total"], 16)

    async def test_four_new_skill_results_serialize_for_the_existing_client_contract(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        session.character["modifiers"].update({
            "charisma": 1,
            "dexterity": 1,
            "wisdom": 1,
        })
        session.character["proficiency_bonus"] = 2

        cases = (
            ("Persuasion", "charisma", True),
            ("Deception", "charisma", False),
            ("Acrobatics", "dexterity", True),
            ("Survival", "wisdom", False),
        )
        for skill, ability, proficient in cases:
            with self.subTest(skill=skill):
                session.character["proficient_skills"] = [skill] if proficient else []
                proficiency_modifier = 2 if proficient else 0
                total = 12 + 1 + proficiency_modifier
                outcome = "success" if total >= 15 else "failure"

                def skill_turn(_message):
                    return {
                        "narration": "A canonical skill result.",
                        "action_result": {
                            "action": "skill_check",
                            "skill": skill,
                            "ability": ability,
                            "dice": 12,
                            "modifier": 1,
                            "proficiency_bonus": proficiency_modifier,
                            "total": total,
                            "dc": 15,
                            "outcome": outcome,
                            "success": outcome == "success",
                            "status": "resolved",
                        },
                    }

                session.run_player_turn = skill_turn
                response = await self.http.post(
                    f"/api/game/sessions/{created['session_id']}/turn",
                    json={"message": f"I attempt {skill}."},
                )
                self.assertEqual(response.status_code, 200, response.text)
                projected = response.json()["skill_check_result"]
                self.assertEqual(projected["skill"], skill)
                self.assertEqual(projected["ability"], ability)
                self.assertEqual(projected["proficient"], proficient)
                self.assertEqual(projected["proficiency_modifier"], proficiency_modifier)
                self.assertEqual(projected["total"], total)
                self.assertEqual(projected["outcome"], outcome)

    async def test_invalid_skill_check_projection_rolls_back_turn(self):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        session = record.game_session
        before = copy.deepcopy(session.serialize_game_state())
        before_rng = session.rng.getstate()

        def invalid_skill_turn(_message):
            session.character["current_hp"] -= 1
            session.rng.randint(1, 20)
            return {
                "narration": "This result must not be committed.",
                "action_result": {
                    "action": "skill_check",
                    "skill": "Perception",
                    "ability": "charisma",
                    "dice": 14,
                    "modifier": 2,
                    "proficiency_bonus": 0,
                    "total": 16,
                    "dc": 15,
                    "outcome": "success",
                },
            }

        session.run_player_turn = invalid_skill_turn
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Kapının arkasından ses dinliyorum."},
        )

        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json()["detail"]["code"], "engine_error")
        self.assertEqual(session.serialize_game_state(), before)
        self.assertEqual(session.rng.getstate(), before_rng)

    async def test_turn_request_rejects_client_skill_mechanics(self):
        created = await self.create_campaign()
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={
                "message": "Kapının arkasından ses dinliyorum.",
                "skill": "Perception",
                "d20": 20,
                "dc": 1,
                "outcome": "critical_success",
                "skill_check_result": {"skill": "Perception", "d20": 20},
            },
        )

        self.assertEqual(response.status_code, 422, response.text)

    async def test_successful_turn_is_autosaved_with_history(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session

        def complete_turn(_message):
            session.character["current_hp"] -= 1
            session.world_state["location"] = "tavern"
            session.world_state["inventory"].append("Lantern")
            npc = {
                "id": "npc_api",
                "name": "Mira",
                "role": "innkeeper",
                "location": "tavern",
                "memory": [
                    {"speaker": "player", "text": "My name is Arven."},
                    {"speaker": "npc", "text": "Welcome, Arven."},
                ],
            }
            session.world_state["npcs"].append(npc)
            return {
                "narration": "Mira welcomes Arven.",
                "action_result": {
                    "action": "dialogue",
                    "npc_id": "npc_api",
                    "status": "resolved",
                },
            }

        session.run_player_turn = complete_turn
        turn = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Mira'ya adım Arven diyorum."},
        )
        self.assertEqual(turn.status_code, 200, turn.text)
        self.assertIsNone(turn.json()["combat_result"])
        self.assertIsNone(turn.json()["skill_check_result"])
        self.assertIn("Lantern", turn.json()["state"]["inventory"])
        self.assertEqual(turn.json()["state"]["location"], "tavern")

        detail = await self.http.get(
            f"/api/game/campaigns/{created['campaign_id']}"
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["state"], turn.json()["state"])
        self.assertEqual(len(detail.json()["history"]), 1)
        self.assertEqual(
            detail.json()["history"][0]["player_message"],
            "Mira'ya adım Arven diyorum.",
        )
        self.assertEqual(
            detail.json()["state"]["npcs"][0]["name"],
            "Mira",
        )
        journal = turn.json()["state"]["journal"]
        self.assertEqual(
            [item["location_id"] for item in journal["discovered_locations"]],
            ["tavern"],
        )
        self.assertEqual(journal["known_npcs"][0]["npc_id"], "npc_api")
        self.assertEqual(journal["quests"], [])
        self.assertEqual(
            [item["event_type"] for item in journal["notable_events"]],
            ["location_discovered", "npc_met", "item_gained"],
        )
        stored = self.store.get_campaign(created["campaign_id"])
        self.assertEqual(stored.payload["journal"], journal)

    async def test_failed_autosave_rolls_back_turn_and_keeps_last_good_save(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        record = self.manager.get(created["session_id"])
        from api.narrative_memory import (
            empty_narrative_memory,
            update_narrative_memory,
        )

        record.narrative_memory = update_narrative_memory(
            empty_narrative_memory(),
            player_message="I promise Mira I will ask about the caravan.",
            narration="The hearth glows softly in the old inn.",
            action_result={
                "action": "dialogue",
                "status": "success",
                "npc_id": "npc-mira",
            },
            world_state_before={},
            world_state_after={
                "location": "loc-inn",
                "npcs": [
                    {
                        "id": "npc-mira",
                        "name": "Mira",
                        "role": "merchant",
                        "location": "loc-inn",
                    }
                ],
            },
        )
        self.manager.save_campaign(created["campaign_id"])
        before = copy.deepcopy(session.serialize_game_state())
        journal_before = copy.deepcopy(record.journal)
        memory_before = copy.deepcopy(record.narrative_memory)
        saved_before = self.store.get_campaign(created["campaign_id"]).payload

        def mutate_then_succeed(_message):
            session.character["current_hp"] -= 2
            session.world_state["inventory"].append("Uncommitted")
            return {
                "narration": "This turn will not be committed.",
                "action_result": {
                    "action": "attack",
                    "status": "resolved",
                    "success": True,
                    "attack_roll": 14,
                },
            }

        session.run_player_turn = mutate_then_succeed
        with patch.object(
            self.store,
            "save_campaign",
            side_effect=CampaignStorageError("database unavailable"),
        ):
            response = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/turn",
                json={"message": "This write will fail."},
            )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("database unavailable", response.text)
        self.assertEqual(session.serialize_game_state(), before)
        self.assertEqual(
            record.journal,
            journal_before,
        )
        self.assertEqual(record.narrative_memory, memory_before)
        self.assertEqual(
            self.store.get_campaign(created["campaign_id"]).payload,
            saved_before,
        )
        self.assertEqual(
            self.store.get_campaign(created["campaign_id"]).combat_history,
            [],
        )
        self.assertEqual(
            self.manager.get(created["session_id"]).combat_history,
            [],
        )

    async def test_create_rejects_client_supplied_canonical_state(self):
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "name": "Forged",
                "current_hp": 0,
                "inventory": ["forged"],
                "location": "forest",
            },
        )
        self.assertEqual(response.status_code, 422)
        listed = await self.http.get("/api/game/campaigns")
        self.assertEqual(listed.json(), [])

    async def test_explicit_save_uses_active_server_session_and_unknown_campaign_is_404(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        session.world_state["location"] = "tavern"

        saved = await self.http.post(
            f"/api/game/campaigns/{created['campaign_id']}/save"
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["location"], "tavern")

        missing = "00000000-0000-4000-8000-000000000000"
        unavailable = await self.http.post(
            f"/api/game/campaigns/{missing}/resume"
        )
        self.assertEqual(unavailable.status_code, 404)
        self.assertEqual(
            unavailable.json()["detail"]["code"],
            "campaign_not_found",
        )

    async def test_journal_survives_explicit_save_and_a_new_session_manager(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        session.world_state["location"] = "tavern"
        session.plan_living_world_turn("Etrafıma bakıyorum.")

        def visit_tavern(_message):
            session.world_state["location"] = "tavern"
            return {
                "narration": "The room comes into view.",
                "action_result": {"action": "travel", "status": "completed", "success": True},
            }

        session.run_player_turn = visit_tavern
        turn = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Taverna'ya giriyorum."},
        )
        self.assertEqual(turn.status_code, 200, turn.text)
        saved = await self.http.post(
            f"/api/game/campaigns/{created['campaign_id']}/save"
        )
        self.assertEqual(saved.status_code, 200, saved.text)

        restarted_manager = SessionManager(campaign_store=self.store)
        _, _, _, _, resumed_state = restarted_manager.resume_campaign(
            created["campaign_id"]
        )
        self.assertEqual(
            resumed_state["journal"],
            turn.json()["state"]["journal"],
        )
        self.assertEqual(resumed_state["scene"]["id"], "scene:tavern")
        self.assertTrue(
            resumed_state["scene"]["visit_revision"] >= 1
        )

    async def test_store_save_without_journal_argument_preserves_existing_journal(self):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        session = record.game_session
        session.world_state["location"] = "tavern"
        record.journal = create_initial_campaign_journal(
            session.world_state,
            session.world_metadata,
        )
        self.store.save_campaign(
            created["campaign_id"],
            session,
            journal=record.journal,
        )

        self.store.save_campaign(created["campaign_id"], session)
        stored = self.store.get_campaign(created["campaign_id"])
        self.assertEqual(stored.payload["journal"], record.journal)

    async def test_legacy_save_without_narrative_memory_migrates_to_empty_memory(self):
        from api.narrative_memory import empty_narrative_memory

        created = await self.create_campaign()
        connection = sqlite3.connect(self.store.path)
        try:
            row = connection.execute(
                "SELECT payload_json FROM campaigns WHERE campaign_id = ?",
                (created["campaign_id"],),
            ).fetchone()
            payload = json.loads(row[0])
            payload.pop("narrative_memory")
            connection.execute(
                "UPDATE campaigns SET payload_json = ? WHERE campaign_id = ?",
                (json.dumps(payload), created["campaign_id"]),
            )
            connection.commit()
        finally:
            connection.close()

        restarted_manager = SessionManager(campaign_store=self.store)
        _, record, _, _, _ = restarted_manager.resume_campaign(
            created["campaign_id"]
        )
        self.assertEqual(record.narrative_memory, empty_narrative_memory())
        migrated = self.store.get_campaign(created["campaign_id"])
        self.assertEqual(
            migrated.payload["narrative_memory"],
            empty_narrative_memory(),
        )

    async def test_legacy_save_without_journal_migrates_to_empty_ledger(self):
        created = await self.create_campaign()
        connection = sqlite3.connect(self.store.path)
        try:
            row = connection.execute(
                "SELECT payload_json FROM campaigns WHERE campaign_id = ?",
                (created["campaign_id"],),
            ).fetchone()
            payload = json.loads(row[0])
            payload.pop("journal")
            connection.execute(
                "UPDATE campaigns SET payload_json = ? WHERE campaign_id = ?",
                (json.dumps(payload), created["campaign_id"]),
            )
            connection.commit()
        finally:
            connection.close()

        restarted_manager = SessionManager(campaign_store=self.store)
        _, record, _, _, state = restarted_manager.resume_campaign(
            created["campaign_id"]
        )
        self.assertEqual(record.journal["quests"], [])
        self.assertEqual(state["journal"], record.journal)
        migrated = self.store.get_campaign(created["campaign_id"])
        self.assertEqual(migrated.payload["journal"]["discovered_locations"], [])
        self.assertEqual(migrated.payload["journal"]["quests"], [])

    async def test_turn_request_cannot_inject_journal_sections(self):
        created = await self.create_campaign()
        forged_fields = {
            "discovered_locations": [{"location_id": "forged"}],
            "known_npcs": [{"npc_id": "forged"}],
            "notable_events": [{"summary": "forged"}],
            "quests": [{"title": "Forged quest"}],
        }
        for field, value in forged_fields.items():
            response = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/turn",
                json={"message": "continue", field: value},
            )
            self.assertEqual(response.status_code, 422, response.text)
        state = await self.http.get(
            f"/api/game/sessions/{created['session_id']}/state"
        )
        self.assertEqual(state.status_code, 200, state.text)
        self.assertEqual(state.json()["journal"]["quests"], [])
        self.assertEqual(
            state.json()["journal"]["discovered_locations"],
            [],
        )

    async def test_narration_cannot_create_or_complete_quests(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        session.run_player_turn = lambda _message: {
            "narration": "Görev tamamlandı; ödülün sana verildi."
        }
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Ne oldu?"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        journal = response.json()["state"]["journal"]
        self.assertEqual(journal["quests"], [])
        self.assertEqual(journal["notable_events"], [])

    async def test_ambient_event_outcome_is_authoritative_idempotent_and_persistent(self):
        created = await self.create_campaign()
        session_id = created["session_id"]
        record = self.manager.get(session_id)
        session = record.game_session
        event_instance_id = self.install_test_ambient_event(session)
        action_id = "00000000-0000-4000-8000-000000000051"
        event_url = (
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{event_instance_id}/actions"
        )
        npc_count = len(session.world_state["npcs"])

        applied = await self.http.post(
            event_url,
            json={"action_id": action_id, "action": "interact"},
        )
        self.assertEqual(applied.status_code, 200, applied.text)
        applied_body = applied.json()
        result = applied_body["result"]
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(result["event_instance_id"], event_instance_id)
        self.assertEqual(len(session.world_state["npcs"]), npc_count + 1)
        self.assertIn(
            result["transition_id"],
            {item["id"] for item in applied_body["state"]["npcs"]},
        )
        self.assertTrue(result["canonical_event_id"])
        ambient_records = [
            item for item in record.journal["notable_events"]
            if item.get("event_type") == "ambient_event_outcome"
        ]
        self.assertEqual(len(ambient_records), 1)
        self.assertEqual(
            ambient_records[0]["event_id"],
            result["canonical_event_id"],
        )
        self.assertEqual(
            ambient_records[0]["event_result"]["event_instance_id"],
            event_instance_id,
        )

        state_after_apply = copy.deepcopy(session.serialize_game_state())
        journal_after_apply = copy.deepcopy(record.journal)
        replay = await self.http.post(
            event_url,
            json={"action_id": action_id, "action": "interact"},
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["result"]["status"], "ALREADY_APPLIED")
        self.assertEqual(
            replay.json()["result"]["canonical_event_id"],
            result["canonical_event_id"],
        )
        self.assertEqual(session.serialize_game_state(), state_after_apply)
        self.assertEqual(record.journal, journal_after_apply)
        different_action_replay = await self.http.post(
            event_url,
            json={
                "action_id": "00000000-0000-4000-8000-000000000052",
                "action": "interact",
            },
        )
        self.assertEqual(
            different_action_replay.json()["result"]["status"],
            "ALREADY_APPLIED",
        )
        self.assertEqual(session.serialize_game_state(), state_after_apply)
        self.assertEqual(record.journal, journal_after_apply)

        reloaded_manager = SessionManager(campaign_store=self.store)
        reloaded_app = create_app(
            session_manager=reloaded_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        reloaded_http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reloaded_app),
            base_url="http://testserver",
        )
        try:
            resumed = await reloaded_http.post(
                f"/api/game/campaigns/{created['campaign_id']}/resume"
            )
            self.assertEqual(resumed.status_code, 200, resumed.text)
            loaded_session_id = resumed.json()["session_id"]
            loaded_record = reloaded_manager.get(loaded_session_id)
            loaded_scene = resumed.json()["state"]["scene"]
            self.assertEqual(
                loaded_scene["ambient_event"]["instance_id"],
                event_instance_id,
            )
            loaded_replay = await reloaded_http.post(
                f"/api/game/sessions/{loaded_session_id}/ambient-events/"
                f"{event_instance_id}/actions",
                json={"action_id": action_id, "action": "interact"},
            )
            self.assertEqual(loaded_replay.status_code, 200, loaded_replay.text)
            self.assertEqual(
                loaded_replay.json()["result"]["status"],
                "ALREADY_APPLIED",
            )
            self.assertEqual(
                loaded_replay.json()["result"]["canonical_event_id"],
                result["canonical_event_id"],
            )
            self.assertEqual(
                len([
                    item for item in loaded_record.journal["notable_events"]
                    if item.get("event_type") == "ambient_event_outcome"
                ]),
                1,
            )
        finally:
            await reloaded_http.aclose()

    async def test_ambient_event_rejections_no_effect_and_campaign_isolation(self):
        created = await self.create_campaign()
        session_id = created["session_id"]
        record = self.manager.get(session_id)
        session = record.game_session
        green_instance_id = self.install_test_ambient_event(session, "GREEN")
        before_world = copy.deepcopy(session.serialize_game_state())
        before_journal = copy.deepcopy(record.journal)
        green_result = await self.http.post(
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{green_instance_id}/actions",
            json={
                "action_id": "00000000-0000-4000-8000-000000000053",
                "action": "interact",
            },
        )
        self.assertEqual(green_result.status_code, 200, green_result.text)
        self.assertEqual(green_result.json()["result"]["status"], "REJECTED")
        self.assertEqual(session.serialize_game_state(), before_world)
        self.assertEqual(record.journal, before_journal)

        blue_instance_id = self.install_test_ambient_event(session)
        observe_id = "00000000-0000-4000-8000-000000000054"
        before_world = copy.deepcopy(session.serialize_game_state())
        before_journal = copy.deepcopy(record.journal)
        no_effect = await self.http.post(
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{blue_instance_id}/actions",
            json={"action_id": observe_id, "action": "observe"},
        )
        self.assertEqual(no_effect.status_code, 200, no_effect.text)
        self.assertEqual(no_effect.json()["result"]["status"], "NO_EFFECT")
        self.assertEqual(session.serialize_game_state(), before_world)
        self.assertEqual(record.journal, before_journal)
        invalid_action = await self.http.post(
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{blue_instance_id}/actions",
            json={
                "action_id": "00000000-0000-4000-8000-000000000055",
                "action": "grant_gold",
            },
        )
        self.assertEqual(invalid_action.status_code, 422, invalid_action.text)
        self.assertEqual(session.serialize_game_state(), before_world)
        self.assertEqual(record.journal, before_journal)
        invalid_uuid = await self.http.post(
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{blue_instance_id}/actions",
            json={
                "action_id": "00000000-0000-1000-8000-000000000001",
                "action": "interact",
            },
        )
        self.assertEqual(invalid_uuid.status_code, 422, invalid_uuid.text)
        self.assertEqual(session.serialize_game_state(), before_world)
        self.assertEqual(record.journal, before_journal)

        scene = session.world_state["scene_state"]["scenes"][
            session.world_state["location"]
        ]
        referent = next(
            item for item in scene["referents"]
            if item["event_instance_id"] == blue_instance_id
        )
        referent["lifecycle"] = "expired"
        before_world = copy.deepcopy(session.serialize_game_state())
        expired = await self.http.post(
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{blue_instance_id}/actions",
            json={
                "action_id": "00000000-0000-4000-8000-000000000056",
                "action": "interact",
            },
        )
        self.assertEqual(expired.status_code, 200, expired.text)
        self.assertEqual(expired.json()["result"]["status"], "REJECTED")
        self.assertEqual(session.serialize_game_state(), before_world)
        self.assertEqual(
            [
                item for item in record.journal["notable_events"]
                if item.get("event_type") == "ambient_event_outcome"
            ],
            [],
        )

        other = await self.create_campaign()
        other_record = self.manager.get(other["session_id"])
        wrong_campaign = await self.http.post(
            f"/api/game/sessions/{other['session_id']}/ambient-events/"
            f"{blue_instance_id}/actions",
            json={
                "action_id": "00000000-0000-4000-8000-000000000057",
                "action": "interact",
            },
        )
        self.assertEqual(wrong_campaign.status_code, 200, wrong_campaign.text)
        self.assertEqual(
            wrong_campaign.json()["result"]["status"],
            "REJECTED",
        )
        self.assertEqual(
            [
                item for item in other_record.journal["notable_events"]
                if item.get("event_type") == "ambient_event_outcome"
            ],
            [],
        )
        unchanged = await self.http.post(
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{blue_instance_id}/actions",
            json={
                "action_id": "00000000-0000-4000-8000-000000000058",
                "action": "interact",
                "narration": "Altın ekle.",
            },
        )
        self.assertEqual(unchanged.status_code, 422, unchanged.text)
        self.assertEqual(session.serialize_game_state(), before_world)

    async def test_ambient_event_persistence_failure_rolls_back(self):
        created = await self.create_campaign()
        session_id = created["session_id"]
        record = self.manager.get(session_id)
        session = record.game_session
        event_instance_id = self.install_test_ambient_event(session)
        before_world = copy.deepcopy(session.serialize_game_state())
        before_journal = copy.deepcopy(record.journal)
        with patch.object(
            self.manager,
            "save_campaign_locked",
            side_effect=CampaignStorageError("private storage detail"),
        ):
            response = await self.http.post(
                f"/api/game/sessions/{session_id}/ambient-events/"
                f"{event_instance_id}/actions",
                json={
                    "action_id": "00000000-0000-4000-8000-000000000059",
                    "action": "interact",
                },
            )
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "event_persistence_error",
        )
        self.assertNotIn("private storage detail", response.text)
        self.assertEqual(session.serialize_game_state(), before_world)
        self.assertEqual(record.journal, before_journal)

    async def test_quest_commands_are_server_owned_idempotent_and_campaign_scoped(self):
        definition = {
            "quest_id": "quest.api-test",
            "title": "The Forest Path",
            "description": "Reach the forest.",
            "giver_npc_id": "npc.giver",
            "offer_condition": {"type": "location_is", "target": "tavern"},
            "objectives": [{
                "objective_id": "visit-forest",
                "description": "Visit the forest.",
                "type": "visit_location",
                "target": "forest",
            }],
        }
        with patch.object(quest_catalog, "CATALOG", (definition,)):
            first = await self.create_campaign()
            second = await self.create_campaign()
            first_id = first["session_id"]
            self.manager.get(first_id).game_session.world_state["location"] = "tavern"
            self.manager.get(second["session_id"]).game_session.world_state[
                "location"
            ] = "tavern"
            quest_url = f"/api/game/sessions/{first_id}/quests/quest.api-test"
            first_state = await self.http.get(f"/api/game/sessions/{first_id}/state")
            self.assertEqual(first_state.status_code, 200, first_state.text)

            self.assertEqual(
                [item["quest_id"] for item in first_state.json()["quest_offers"]],
                ["quest.api-test"],
            )
            self.assertEqual(first_state.json()["quests"], [])
            self.assertEqual(first_state.json()["journal"]["quests"], [])

            unavailable = await self.http.post(
                f"/api/game/sessions/{first_id}/quests/unknown/accept"
            )
            self.assertEqual(unavailable.status_code, 404)

            accepted = await self.http.post(
                f"{quest_url}/accept",
                json={
                    "status": "completed",
                    "quest_id": "forged",
                    "objectives": [{"objective_id": "forged"}],
                },
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            accepted_body = accepted.json()
            self.assertEqual(accepted_body["quest"]["quest_id"], "quest.api-test")
            self.assertEqual(accepted_body["quest"]["status"], "accepted")
            self.assertEqual(
                accepted_body["quest"]["objectives"][0]["objective_id"],
                "visit-forest",
            )
            self.assertEqual(accepted_body["outcome"]["transition"], "accepted")
            self.assertEqual(accepted_body["state"]["quests"][0]["status"], "accepted")
            self.assertEqual(accepted_body["state"]["quest_offers"], [])

            repeated_accept = await self.http.post(f"{quest_url}/accept")
            self.assertEqual(repeated_accept.status_code, 200, repeated_accept.text)
            self.assertIsNone(repeated_accept.json()["outcome"])

            second_state = await self.http.get(
                f"/api/game/sessions/{second['session_id']}/state"
            )
            self.assertEqual(second_state.status_code, 200, second_state.text)
            self.assertEqual(second_state.json()["quests"], [])
            self.assertEqual(
                [item["quest_id"] for item in second_state.json()["quest_offers"]],
                ["quest.api-test"],
            )

            cancelled = await self.http.post(
                f"{quest_url}/cancel",
                json={"status": "completed", "progress": 999},
            )
            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertEqual(cancelled.json()["quest"]["status"], "cancelled")
            self.assertEqual(
                cancelled.json()["quest"]["objectives"][0]["status"], "cancelled"
            )
            self.assertEqual(cancelled.json()["outcome"]["transition"], "cancelled")

            repeated_cancel = await self.http.post(f"{quest_url}/cancel")
            self.assertEqual(repeated_cancel.status_code, 200, repeated_cancel.text)
            self.assertIsNone(repeated_cancel.json()["outcome"])

            resumed = await self.http.post(
                f"/api/game/campaigns/{first['campaign_id']}/resume"
            )
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"]["quests"][0]["status"], "cancelled")
            self.assertEqual(resumed.json()["state"]["quest_offers"], [])

    async def test_quest_offer_conditions_and_autosave_failure_roll_back(self):
        definition = {
            "quest_id": "quest.rollback-test",
            "title": "Forest Path",
            "description": "Reach the forest.",
            "offer_condition": {"type": "location_is", "target": "forest"},
            "objectives": [{
                "objective_id": "visit-forest",
                "description": "Visit the forest.",
                "type": "visit_location",
                "target": "forest",
            }],
        }
        with patch.object(quest_catalog, "CATALOG", (definition,)):
            created = await self.create_campaign()
            session = self.manager.get(created["session_id"]).game_session
            self.assertEqual(created["state"]["quest_offers"], [])

            not_offerable = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/quests/"
                "quest.rollback-test/accept"
            )
            self.assertEqual(not_offerable.status_code, 404)

            session.world_state["location"] = "forest"
            state = await self.http.get(
                f"/api/game/sessions/{created['session_id']}/state"
            )
            self.assertEqual(
                [item["quest_id"] for item in state.json()["quest_offers"]],
                ["quest.rollback-test"],
            )
            before = copy.deepcopy(session.serialize_game_state())
            world_ref = session.world_state
            rng_state = session.rng.getstate()
            saved_before = self.store.get_campaign(created["campaign_id"]).payload
            with patch.object(
                self.store,
                "save_campaign",
                side_effect=CampaignStorageError("database unavailable"),
            ):
                failed = await self.http.post(
                    f"/api/game/sessions/{created['session_id']}/quests/"
                    "quest.rollback-test/accept"
                )

            self.assertEqual(failed.status_code, 503)
            self.assertNotIn("database unavailable", failed.text)
            self.assertIs(session.world_state, world_ref)
            self.assertEqual(session.serialize_game_state(), before)
            self.assertEqual(session.rng.getstate(), rng_state)
            self.assertEqual(
                self.store.get_campaign(created["campaign_id"]).payload,
                saved_before,
            )

    async def test_active_quest_is_not_completed_by_narration(self):
        definition = {
            "quest_id": "quest.narration-test",
            "title": "Forest Path",
            "description": "Reach the forest.",
            "offer_condition": {"type": "location_is", "target": "tavern"},
            "objectives": [{
                "objective_id": "visit-forest",
                "description": "Visit the forest.",
                "type": "visit_location",
                "target": "forest",
            }],
        }
        with patch.object(quest_catalog, "CATALOG", (definition,)):
            created = await self.create_campaign()
            session = self.manager.get(created["session_id"]).game_session
            session.world_state["location"] = "tavern"
            accepted = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/quests/"
                "quest.narration-test/accept"
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)

            session.run_player_turn = lambda _message: {
                "action_result": {},
                "narration": "The quest is accepted and the objective is complete.",
            }
            turn = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/turn",
                json={"message": "What happened?"},
            )
            self.assertEqual(turn.status_code, 200, turn.text)
            self.assertEqual(turn.json()["quest_outcomes"], [])
            self.assertEqual(turn.json()["state"]["quests"][0]["status"], "accepted")
            self.assertEqual(
                turn.json()["state"]["quests"][0]["objectives"][0]["progress"], 0
            )

    async def test_journal_state_is_isolated_between_campaigns(self):
        first = await self.create_campaign()
        second = await self.create_campaign()
        session = self.manager.get(first["session_id"]).game_session

        def enter_forest(_message):
            session.world_state["location"] = "forest"
            return {
                "narration": "Ormana ilerliyorsun.",
                "action_result": {"action": "travel", "status": "completed", "success": True},
            }

        session.run_player_turn = enter_forest
        changed = await self.http.post(
            f"/api/game/sessions/{first['session_id']}/turn",
            json={"message": "Ormana gidiyorum."},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(
            changed.json()["state"]["journal"]["discovered_locations"][0]["location_id"],
            "forest",
        )

        untouched = await self.http.get(
            f"/api/game/sessions/{second['session_id']}/state"
        )
        self.assertEqual(untouched.status_code, 200, untouched.text)
        self.assertEqual(
            untouched.json()["journal"]["discovered_locations"],
            [],
        )

    async def test_failed_tavern_exit_after_resume_rolls_back_and_retries_once(self):
        city_id = "fr:city:neverwinter"
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        campaign_id = created["campaign_id"]
        initial_url = f"/api/game/sessions/{created['session_id']}/turn"
        for message in ("Yakınlarda bir taverna arıyorum.", "Enter the tavern."):
            entered = await self.http.post(
                initial_url,
                json={"message": message, "action_id": str(uuid.uuid4())},
            )
            self.assertEqual(entered.status_code, 200, entered.text)
        tavern_id = entered.json()["state"]["location"]
        self.assertNotEqual(tavern_id, city_id)

        # Resume the real, persisted venue before injecting an exit save failure.
        store = CampaignStore(self.store.path)
        manager = SessionManager(campaign_store=store)
        app = create_app(
            session_manager=manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"], entered.json()["state"])
            session_id = resumed.json()["session_id"]
            record = manager.get(session_id)
            session = record.game_session
            world = session.world_state
            self.assertEqual(world["location"], tavern_id)
            self.assertEqual(world["locations"][tavern_id]["scene_kind"], "tavern")
            self.assertEqual(world["locations"][tavern_id]["exit_location_id"], city_id)
            before_save = copy.deepcopy(session.serialize_game_state())
            before_campaign = store.get_campaign(campaign_id)
            self.assertEqual(before_campaign.payload["engine_save"], before_save)
            self.assertEqual(len(before_campaign.history), 2)
            before_position = copy.deepcopy(world["scene_state"]["player_position"])
            self.assertEqual(before_position["location_id"], tavern_id)
            city_visits = world["scene_state"]["scenes"][city_id]["visit_revision"]
            tavern_visits = world["scene_state"]["scenes"][tavern_id]["visit_revision"]
            before_journal = copy.deepcopy(record.journal)
            before_memory = copy.deepcopy(record.narrative_memory)
            before_receipts = copy.deepcopy(record.turn_action_receipts)
            exit_body = {
                "message": "Tavernadan dışarı çıkıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            turn_url = f"/api/game/sessions/{session_id}/turn"
            real_turn = session.run_player_turn
            exit_results = []
            exit_worlds = []

            @wraps(real_turn)
            def capture_exit(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                exit_results.append(copy.deepcopy(result["action_result"]))
                exit_worlds.append(copy.deepcopy(session.world_state))
                return result

            with (
                patch.object(session, "run_player_turn", new=capture_exit),
                patch.object(
                    store, "save_campaign",
                    side_effect=CampaignStorageError("database unavailable"),
                ) as failed_save,
            ):
                failed = await http.post(turn_url, json=exit_body)
            failed_save.assert_called_once()
            self.assertEqual(failed.status_code, 503, failed.text)
            self.assertEqual(
                failed.json()["detail"]["code"], "campaign_storage_unavailable"
            )
            self.assertNotIn("database unavailable", failed.text)
            self.assertEqual(len(exit_results), 1)
            self.assertEqual(exit_results[0]["action"], "exit")
            self.assertEqual(exit_results[0]["status"], "completed")
            self.assertEqual(exit_results[0]["target_id"], city_id)
            # Prove the engine actually exited before the save was rejected.
            self.assertEqual(exit_worlds[0]["location"], city_id)
            self.assertEqual(
                exit_worlds[0]["scene_state"]["player_position"]["location_id"],
                city_id,
            )
            self.assertEqual(
                exit_worlds[0]["scene_state"]["scenes"][city_id]["visit_revision"],
                city_visits + 1,
            )
            self.assertEqual(session.serialize_game_state(), before_save)
            self.assertEqual(world["location"], tavern_id)
            self.assertEqual(world["scene_state"]["player_position"], before_position)
            self.assertEqual(
                world["scene_state"]["scenes"][city_id]["visit_revision"], city_visits
            )
            self.assertEqual(record.journal, before_journal)
            self.assertEqual(record.narrative_memory, before_memory)
            self.assertEqual(record.turn_action_receipts, before_receipts)
            self.assertNotIn(exit_body["action_id"], record.turn_action_receipts)
            failed_campaign = store.get_campaign(campaign_id)
            self.assertEqual(failed_campaign.payload, before_campaign.payload)
            self.assertEqual(failed_campaign.metadata, before_campaign.metadata)
            self.assertEqual(failed_campaign.history, before_campaign.history)
            self.assertEqual(failed_campaign.combat_history, before_campaign.combat_history)
            self.assertIsNone(store.get_turn_action(campaign_id, exit_body["action_id"]))

            # A separate manager must still restore the tavern, not the failed exit.
            fresh_store = CampaignStore(self.store.path)
            fresh_manager = SessionManager(campaign_store=fresh_store)
            fresh_app = create_app(
                session_manager=fresh_manager,
                ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=fresh_app),
                base_url="http://testserver",
            ) as fresh_http:
                restored = await fresh_http.post(
                    f"/api/game/campaigns/{campaign_id}/resume"
                )
            self.assertEqual(restored.status_code, 200, restored.text)
            self.assertEqual(restored.json()["state"], entered.json()["state"])
            self.assertEqual(restored.json()["history"], resumed.json()["history"])
            fresh_record = fresh_manager.get(restored.json()["session_id"])
            self.assertEqual(fresh_record.game_session.serialize_game_state(), before_save)
            self.assertEqual(fresh_record.turn_action_receipts, before_receipts)
            self.assertIsNone(
                fresh_store.get_turn_action(campaign_id, exit_body["action_id"])
            )

            # Reuse the failed action ID once storage is healthy.
            with patch.object(session, "run_player_turn", new=capture_exit):
                retry = await http.post(turn_url, json=exit_body)
            self.assertEqual(retry.status_code, 200, retry.text)
            self.assertEqual(len(exit_results), 2)
            self.assertEqual(exit_results[-1]["action"], "exit")
            self.assertEqual(exit_results[-1]["status"], "completed")
            self.assertEqual(exit_results[-1]["target_id"], city_id)
            self.assertEqual(retry.json()["state"]["location"], city_id)
            self.assertEqual(world["location"], city_id)
            self.assertEqual(
                world["scene_state"]["player_position"]["location_id"], city_id
            )
            self.assertEqual(
                world["scene_state"]["scenes"][city_id]["visit_revision"],
                city_visits + 1,
            )
            self.assertEqual(
                world["scene_state"]["scenes"][tavern_id]["visit_revision"], tavern_visits
            )
            committed_save = copy.deepcopy(session.serialize_game_state())
            committed = store.get_campaign(campaign_id)
            self.assertEqual(committed.payload["engine_save"], committed_save)
            self.assertEqual(len(committed.history), len(before_campaign.history) + 1)
            self.assertEqual(committed.history[:-1], before_campaign.history)
            # Campaign receipts are store-owned, unlike transient session receipts.
            self.assertEqual(
                manager.get_turn_action(record, exit_body["action_id"])["response"],
                retry.json(),
            )

            with patch.object(
                session, "run_player_turn",
                side_effect=AssertionError("Exit replay must not execute another turn"),
            ):
                replay = await http.post(turn_url, json=exit_body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), retry.json())
            self.assertEqual(session.serialize_game_state(), committed_save)
            replayed = store.get_campaign(campaign_id)
            self.assertEqual(replayed.payload, committed.payload)
            self.assertEqual(replayed.metadata, committed.metadata)
            self.assertEqual(replayed.history, committed.history)

    async def test_stale_resumed_tavern_cannot_overwrite_saved_exit_but_can_replay(self):
        city_id = "fr:city:neverwinter"
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        campaign_id = created["campaign_id"]
        initial_url = f"/api/game/sessions/{created['session_id']}/turn"
        for message in ("Yakınlarda bir taverna arıyorum.", "Enter the tavern."):
            entered = await self.http.post(
                initial_url,
                json={"message": message, "action_id": str(uuid.uuid4())},
            )
            self.assertEqual(entered.status_code, 200, entered.text)
        tavern_id = entered.json()["state"]["location"]
        self.assertNotEqual(tavern_id, city_id)

        active_store = CampaignStore(self.store.path)
        stale_store = CampaignStore(self.store.path)
        active_manager = SessionManager(campaign_store=active_store)
        stale_manager = SessionManager(campaign_store=stale_store)
        active_app = create_app(
            session_manager=active_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        stale_app = create_app(
            session_manager=stale_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=active_app),
                base_url="http://testserver",
            ) as active_http,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=stale_app),
                base_url="http://testserver",
            ) as stale_http,
        ):
            # Both independent managers open the same saved tavern before the exit.
            active_resume = await active_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            stale_resume = await stale_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            for response in (active_resume, stale_resume):
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["state"], entered.json()["state"])
            active_id = active_resume.json()["session_id"]
            stale_id = stale_resume.json()["session_id"]
            active_session = active_manager.get(active_id).game_session
            stale_record = stale_manager.get(stale_id)
            stale_session = stale_record.game_session
            self.assertIsNot(active_session, stale_session)
            self.assertIsNot(active_session.world_state, stale_session.world_state)
            before = active_store.get_campaign(campaign_id)
            stale_save = copy.deepcopy(stale_session.serialize_game_state())
            stale_world = stale_session.world_state
            stale_position = copy.deepcopy(stale_world["scene_state"]["player_position"])
            city_visits = stale_world["scene_state"]["scenes"][city_id]["visit_revision"]
            tavern_visits = stale_world["scene_state"]["scenes"][tavern_id]["visit_revision"]
            self.assertEqual(stale_world["location"], tavern_id)
            self.assertEqual(stale_position["location_id"], tavern_id)
            self.assertEqual(stale_save, before.payload["engine_save"])

            exit_body = {
                "message": "Tavernadan dışarı çıkıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            accepted = await active_http.post(
                f"/api/game/sessions/{active_id}/turn", json=exit_body
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(accepted.json()["state"]["location"], city_id)
            committed = active_store.get_campaign(campaign_id)
            committed_world = committed.payload["engine_save"]["world_state"]
            self.assertEqual(committed_world["location"], city_id)
            self.assertEqual(
                committed_world["scene_state"]["player_position"]["location_id"], city_id
            )
            self.assertEqual(
                committed_world["scene_state"]["scenes"][city_id]["visit_revision"],
                city_visits + 1,
            )
            self.assertEqual(
                committed_world["scene_state"]["scenes"][tavern_id]["visit_revision"],
                tavern_visits,
            )
            self.assertEqual(committed.metadata["revision"], before.metadata["revision"] + 1)
            self.assertEqual(committed.history[:-1], before.history)
            self.assertEqual(len(committed.history), len(before.history) + 1)
            self.assertEqual(committed.history[-1]["player_message"], exit_body["message"])
            exit_receipt = active_store.get_turn_action(campaign_id, exit_body["action_id"])
            self.assertEqual(exit_receipt["response"], accepted.json())
            with closing(sqlite3.connect(self.store.path)) as connection:
                receipts_before = connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id", (campaign_id,),
                ).fetchall()
            self.assertEqual(len(receipts_before), 3)

            # Do not resume again: this manager must keep its old tavern context.
            self.assertEqual(stale_session.serialize_game_state(), stale_save)
            stale_body = {
                "message": "Tavernadan dışarı çıkıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            stale_url = f"/api/game/sessions/{stale_id}/turn"
            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Stale requests must not run the engine"),
                ) as blocked_turn,
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Stale requests must not save"),
                ) as blocked_save,
            ):
                rejected = await stale_http.post(stale_url, json=stale_body)
                self.assertEqual(rejected.status_code, 409, rejected.text)
                self.assertEqual(rejected.json()["detail"]["code"], "campaign_stale")
                rejected_campaign = stale_store.get_campaign(campaign_id)
                self.assertEqual(rejected_campaign.payload, committed.payload)
                self.assertEqual(rejected_campaign.metadata, committed.metadata)
                self.assertEqual(rejected_campaign.history, committed.history)
                self.assertEqual(rejected_campaign.combat_history, committed.combat_history)
                self.assertIsNone(stale_store.get_turn_action(campaign_id, stale_body["action_id"]))
                self.assertEqual(
                    stale_store.get_turn_action(campaign_id, exit_body["action_id"]),
                    exit_receipt,
                )

                replay = await stale_http.post(stale_url, json=exit_body)
                self.assertEqual(replay.status_code, 200, replay.text)
                expected_replay = copy.deepcopy(accepted.json())
                expected_replay["session_id"] = stale_id
                self.assertEqual(replay.json(), expected_replay)
                blocked_turn.assert_not_called()
                blocked_save.assert_not_called()

            self.assertEqual(stale_session.serialize_game_state(), stale_save)
            self.assertEqual(stale_world["scene_state"]["player_position"], stale_position)
            replayed_campaign = stale_store.get_campaign(campaign_id)
            self.assertEqual(replayed_campaign.payload, committed.payload)
            self.assertEqual(replayed_campaign.metadata, committed.metadata)
            self.assertEqual(replayed_campaign.history, committed.history)
            self.assertEqual(replayed_campaign.combat_history, committed.combat_history)
            with closing(sqlite3.connect(self.store.path)) as connection:
                receipts_after = connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id", (campaign_id,),
                ).fetchall()
            self.assertEqual(receipts_after, receipts_before)

    async def test_stale_tavern_resume_refreshes_city_and_rejected_action_commits_once(self):
        city_id = "fr:city:neverwinter"
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        campaign_id = created["campaign_id"]
        for message in ("Yakınlarda bir taverna arıyorum.", "Enter the tavern."):
            entered = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/turn",
                json={"message": message, "action_id": str(uuid.uuid4())},
            )
            self.assertEqual(entered.status_code, 200, entered.text)
        tavern_id = entered.json()["state"]["location"]
        self.assertNotEqual(tavern_id, city_id)

        def receipt_rows():
            with closing(sqlite3.connect(self.store.path)) as connection:
                return connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id", (campaign_id,),
                ).fetchall()

        active_store = CampaignStore(self.store.path)
        stale_store = CampaignStore(self.store.path)
        active_manager = SessionManager(campaign_store=active_store)
        stale_manager = SessionManager(campaign_store=stale_store)
        active_app = create_app(
            session_manager=active_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        stale_app = create_app(
            session_manager=stale_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=active_app),
                base_url="http://testserver",
            ) as active_http,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=stale_app),
                base_url="http://testserver",
            ) as stale_http,
        ):
            resume_url = f"/api/game/campaigns/{campaign_id}/resume"
            active_resume = await active_http.post(resume_url)
            stale_resume = await stale_http.post(resume_url)
            for response in (active_resume, stale_resume):
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["state"], entered.json()["state"])
            active_id = active_resume.json()["session_id"]
            stale_id = stale_resume.json()["session_id"]
            stale_record = stale_manager.get(stale_id)
            stale_session = stale_record.game_session
            self.assertIsNot(active_manager.get(active_id).game_session, stale_session)
            stale_save = copy.deepcopy(stale_session.serialize_game_state())
            before = active_store.get_campaign(campaign_id)
            self.assertEqual(
                stale_session._campaign_persistence_version,
                (campaign_id, before.metadata["revision"]),
            )
            exit_body = {
                "message": "Tavernadan dışarı çıkıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            accepted = await active_http.post(
                f"/api/game/sessions/{active_id}/turn", json=exit_body
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(accepted.json()["state"]["location"], city_id)
            committed = active_store.get_campaign(campaign_id)
            self.assertEqual(committed.metadata["revision"], before.metadata["revision"] + 1)
            self.assertEqual(committed.history[:-1], before.history)
            self.assertEqual(len(committed.history), len(before.history) + 1)
            prior_receipts = receipt_rows()
            self.assertEqual(len(prior_receipts), 3)
            exit_receipt = active_store.get_turn_action(campaign_id, exit_body["action_id"])
            self.assertEqual(exit_receipt["response"], accepted.json())

            # This is a new request, not replay of the already accepted exit.
            retry_body = {
                "message": "Enter the tavern.",
                "action_id": str(uuid.uuid4()),
            }
            turn_url = f"/api/game/sessions/{stale_id}/turn"
            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Stale requests must not run the engine"),
                ) as blocked_turn,
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Stale requests must not save"),
                ) as blocked_save,
            ):
                rejected = await stale_http.post(turn_url, json=retry_body)
            self.assertEqual(rejected.status_code, 409, rejected.text)
            self.assertEqual(rejected.json()["detail"]["code"], "campaign_stale")
            blocked_turn.assert_not_called()
            blocked_save.assert_not_called()
            self.assertEqual(stale_session.serialize_game_state(), stale_save)
            rejected_campaign = stale_store.get_campaign(campaign_id)
            self.assertEqual(rejected_campaign, committed)
            self.assertIsNone(stale_store.get_turn_action(campaign_id, retry_body["action_id"]))
            self.assertEqual(receipt_rows(), prior_receipts)

            # Explicit resume through the SAME manager must refresh its cached session.
            refreshed = await stale_http.post(resume_url)
            self.assertEqual(refreshed.status_code, 200, refreshed.text)
            self.assertEqual(refreshed.json()["session_id"], stale_id)
            self.assertIs(stale_manager.get(stale_id), stale_record)
            self.assertEqual(refreshed.json()["state"], accepted.json()["state"])
            self.assertEqual(refreshed.json()["history"], committed.history)
            self.assertEqual(
                stale_session.serialize_game_state(), committed.payload["engine_save"]
            )
            self.assertEqual(
                stale_session._campaign_persistence_version,
                (campaign_id, committed.metadata["revision"]),
            )
            refreshed_campaign = stale_store.get_campaign(campaign_id)
            self.assertEqual(
                refreshed_campaign.metadata["revision"], committed.metadata["revision"]
            )
            self.assertEqual(refreshed_campaign.history, committed.history)
            self.assertEqual(refreshed_campaign.payload, committed.payload)
            self.assertEqual(receipt_rows(), prior_receipts)
            self.assertIsNone(stale_store.get_turn_action(campaign_id, retry_body["action_id"]))

            # Keep the rejected ID: it should execute from the refreshed city exactly once.
            world = stale_session.world_state
            self.assertEqual(world["scene_state"]["player_position"]["location_id"], city_id)
            city_visits = world["scene_state"]["scenes"][city_id]["visit_revision"]
            tavern_visits = world["scene_state"]["scenes"][tavern_id]["visit_revision"]
            real_turn = stale_session.run_player_turn
            retry_results = []

            @wraps(real_turn)
            def capture_retry(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                retry_results.append(copy.deepcopy(result["action_result"]))
                return result

            with patch.object(stale_session, "run_player_turn", new=capture_retry):
                retry = await stale_http.post(turn_url, json=retry_body)
            self.assertEqual(retry.status_code, 200, retry.text)
            self.assertEqual(len(retry_results), 1)
            self.assertEqual(retry_results[0]["action"], "enter")
            self.assertEqual(retry_results[0]["status"], "completed")
            self.assertEqual(retry_results[0]["target_id"], tavern_id)
            self.assertEqual(retry.json()["state"]["location"], tavern_id)
            self.assertEqual(world["scene_state"]["player_position"]["location_id"], tavern_id)
            self.assertEqual(
                world["scene_state"]["scenes"][tavern_id]["visit_revision"], tavern_visits + 1
            )
            self.assertEqual(
                world["scene_state"]["scenes"][city_id]["visit_revision"], city_visits
            )
            retried = stale_store.get_campaign(campaign_id)
            self.assertEqual(retried.metadata["revision"], committed.metadata["revision"] + 1)
            self.assertEqual(
                stale_session._campaign_persistence_version,
                (campaign_id, retried.metadata["revision"]),
            )
            self.assertEqual(retried.history[:-1], committed.history)
            self.assertEqual(len(retried.history), len(committed.history) + 1)
            self.assertEqual(retried.history[-1]["player_message"], retry_body["message"])
            retried_save = copy.deepcopy(stale_session.serialize_game_state())
            self.assertEqual(retried.payload["engine_save"], retried_save)
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, retry_body["action_id"])["response"],
                retry.json(),
            )
            committed_receipts = receipt_rows()
            self.assertEqual(len(committed_receipts), len(prior_receipts) + 1)
            self.assertTrue(all(row in committed_receipts for row in prior_receipts))
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, exit_body["action_id"]), exit_receipt
            )

            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Replay must not run another turn"),
                ) as replay_turn,
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Replay must not save again"),
                ) as replay_save,
            ):
                replay = await stale_http.post(turn_url, json=retry_body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), retry.json())
            replay_turn.assert_not_called()
            replay_save.assert_not_called()
            self.assertEqual(stale_session.serialize_game_state(), retried_save)
            self.assertEqual(stale_store.get_campaign(campaign_id), retried)
            self.assertEqual(receipt_rows(), committed_receipts)

    async def test_stale_city_cannot_overwrite_merchant_discovery_but_can_replay(self):
        city_id = "fr:city:neverwinter"
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        campaign_id = created_response.json()["campaign_id"]
        active_store = CampaignStore(self.store.path)
        stale_store = CampaignStore(self.store.path)
        active_manager = SessionManager(campaign_store=active_store)
        stale_manager = SessionManager(campaign_store=stale_store)
        active_app = create_app(
            session_manager=active_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        stale_app = create_app(
            session_manager=stale_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=active_app),
                base_url="http://testserver",
            ) as active_http,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=stale_app),
                base_url="http://testserver",
            ) as stale_http,
        ):
            # Load both independent sessions before any merchant is discovered.
            active_resume = await active_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            stale_resume = await stale_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            for response in (active_resume, stale_resume):
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["state"]["location"], city_id)
            active_id = active_resume.json()["session_id"]
            stale_id = stale_resume.json()["session_id"]
            active_session = active_manager.get(active_id).game_session
            stale_record = stale_manager.get(stale_id)
            stale_session = stale_record.game_session
            self.assertIsNot(active_session, stale_session)
            self.assertIsNot(active_session.world_state, stale_session.world_state)
            stale_save = copy.deepcopy(stale_session.serialize_game_state())
            stale_journal = copy.deepcopy(stale_record.journal)
            before = active_store.get_campaign(campaign_id)
            self.assertEqual(stale_save, before.payload["engine_save"])
            self.assertEqual(stale_save["world_state"]["shops"], [])

            body = {
                "message": "Bir tüccar arıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            results = []
            real_turn = active_session.run_player_turn

            @wraps(real_turn)
            def capture_search(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result["action_result"]))
                return result

            # Observe the real deterministic engine, not a scripted discovery.
            with patch.object(active_session, "run_player_turn", new=capture_search):
                accepted = await active_http.post(
                    f"/api/game/sessions/{active_id}/turn", json=body
                )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(accepted.json()["action_id"], body["action_id"])
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["action"], "local_search")
            self.assertEqual(results[0]["status"], "found")
            self.assertTrue(results[0]["success"])
            committed = active_store.get_campaign(campaign_id)
            world = committed.payload["engine_save"]["world_state"]
            self.assertEqual(world["location"], city_id)
            self.assertEqual(len(world["shops"]), 1)
            shop = world["shops"][0]
            self.assertEqual(shop["id"], results[0]["shop_id"])
            self.assertEqual(shop["shopkeeper_id"], results[0]["target_id"])
            self.assertEqual(shop["location"], city_id)
            shopkeepers = [
                npc for npc in world["npcs"] if npc["id"] == shop["shopkeeper_id"]
            ]
            self.assertEqual(len(shopkeepers), 1)
            self.assertEqual(shopkeepers[0]["shop_id"], shop["id"])
            self.assertEqual(shopkeepers[0]["location"], city_id)
            self.assertEqual(
                [npc["id"] for npc in world["npcs"] if npc.get("shop_id") == shop["id"]],
                [shop["shopkeeper_id"]],
            )
            self.assertEqual(committed.payload["engine_save"], active_session.serialize_game_state())
            self.assertEqual(committed.metadata["revision"], before.metadata["revision"] + 1)
            self.assertEqual(len(committed.history), len(before.history) + 1)
            self.assertEqual(committed.history[:-1], before.history)
            self.assertEqual(committed.history[-1]["player_message"], body["message"])
            receipt = copy.deepcopy(active_store.get_turn_action(campaign_id, body["action_id"]))
            self.assertEqual(receipt["response"], accepted.json())
            with closing(sqlite3.connect(self.store.path)) as connection:
                receipts_before = connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id", (campaign_id,),
                ).fetchall()
            self.assertEqual(len(receipts_before), 1)

            # No second resume: this session still has the merchant-free city.
            self.assertEqual(stale_session.serialize_game_state(), stale_save)
            stale_body = {
                "message": "Yakınlarda bir satıcı bulunuyor mu?",
                "action_id": str(uuid.uuid4()),
            }
            self.assertNotEqual(stale_body["message"], body["message"])
            self.assertNotEqual(stale_body["action_id"], body["action_id"])
            stale_url = f"/api/game/sessions/{stale_id}/turn"

            def assert_discovery_preserved():
                persisted = stale_store.get_campaign(campaign_id)
                self.assertEqual(persisted, committed)
                saved_world = persisted.payload["engine_save"]["world_state"]
                self.assertEqual(saved_world["shops"], [shop])
                self.assertEqual(
                    [npc for npc in saved_world["npcs"] if npc.get("shop_id") == shop["id"]],
                    shopkeepers,
                )
                self.assertEqual(
                    stale_store.get_turn_action(campaign_id, body["action_id"]), receipt
                )
                self.assertIsNone(
                    stale_store.get_turn_action(campaign_id, stale_body["action_id"])
                )
                self.assertEqual(stale_session.serialize_game_state(), stale_save)
                self.assertEqual(stale_record.journal, stale_journal)
                with closing(sqlite3.connect(self.store.path)) as connection:
                    receipts_after = connection.execute(
                        "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                        "ORDER BY action_id", (campaign_id,),
                    ).fetchall()
                self.assertEqual(receipts_after, receipts_before)

            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Stale discovery and replay must not run the engine"),
                ) as blocked_turn,
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Stale discovery and replay must not save"),
                ) as blocked_save,
            ):
                rejected = await stale_http.post(stale_url, json=stale_body)
                self.assertEqual(rejected.status_code, 409, rejected.text)
                self.assertEqual(rejected.json()["detail"]["code"], "campaign_stale")
                blocked_turn.assert_not_called()
                blocked_save.assert_not_called()
                assert_discovery_preserved()

                replay = await stale_http.post(stale_url, json=body)
                self.assertEqual(replay.status_code, 200, replay.text)
                expected_replay = copy.deepcopy(accepted.json())
                expected_replay["session_id"] = stale_id
                self.assertEqual(replay.json(), expected_replay)
                blocked_turn.assert_not_called()
                blocked_save.assert_not_called()
                assert_discovery_preserved()

            # Refresh the cached stale session over HTTP, keeping its rejected ID.
            refreshed = await stale_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            self.assertEqual(refreshed.status_code, 200, refreshed.text)
            self.assertEqual(refreshed.json()["session_id"], stale_id)
            self.assertIs(stale_manager.get(stale_id), stale_record)
            self.assertIs(stale_record.game_session, stale_session)
            self.assertEqual(refreshed.json()["state"], accepted.json()["state"])
            self.assertEqual(refreshed.json()["history"], committed.history)
            self.assertEqual(
                stale_session.serialize_game_state(), committed.payload["engine_save"]
            )
            self.assertEqual(stale_record.journal, committed.payload["journal"])
            self.assertEqual(
                stale_session._campaign_persistence_version,
                (campaign_id, committed.metadata["revision"]),
            )
            refreshed_campaign = stale_store.get_campaign(campaign_id)
            # Resume may refresh metadata timestamps, but not gameplay or receipts.
            self.assertEqual(refreshed_campaign.payload, committed.payload)
            self.assertEqual(refreshed_campaign.history, committed.history)
            self.assertEqual(
                refreshed_campaign.metadata["revision"], committed.metadata["revision"]
            )
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, body["action_id"]), receipt
            )
            self.assertIsNone(
                stale_store.get_turn_action(campaign_id, stale_body["action_id"])
            )
            with closing(sqlite3.connect(self.store.path)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                        "ORDER BY action_id", (campaign_id,),
                    ).fetchall(),
                    receipts_before,
                )

            real_retry = stale_session.run_player_turn
            retry_results = []

            @wraps(real_retry)
            def capture_retry(*args, **kwargs):
                result = real_retry(*args, **kwargs)
                retry_results.append(copy.deepcopy(result["action_result"]))
                return result

            with (
                patch.object(stale_session, "run_player_turn", new=capture_retry),
                patch.object(
                    stale_store, "save_campaign", wraps=stale_store.save_campaign
                ) as retry_save,
            ):
                retried_response = await stale_http.post(stale_url, json=stale_body)
            self.assertEqual(retried_response.status_code, 200, retried_response.text)
            self.assertEqual(retried_response.json()["action_id"], stale_body["action_id"])
            retry_save.assert_called_once()
            self.assertEqual(len(retry_results), 1)
            self.assertEqual(retry_results[0]["action"], "local_search")
            self.assertEqual(retry_results[0]["status"], "found")
            self.assertTrue(retry_results[0]["success"])
            self.assertEqual(retry_results[0]["shop_id"], shop["id"])
            self.assertEqual(retry_results[0]["target_id"], shop["shopkeeper_id"])
            retried = stale_store.get_campaign(campaign_id)
            retried_save = copy.deepcopy(stale_session.serialize_game_state())
            self.assertEqual(retried.payload["engine_save"], retried_save)
            self.assertEqual(retried.payload["journal"], stale_record.journal)
            retry_world = retried_save["world_state"]
            self.assertEqual(retry_world["location"], city_id)
            self.assertEqual(retry_world["shops"], [shop])
            self.assertEqual(
                [npc for npc in retry_world["npcs"] if npc["id"] == shop["shopkeeper_id"]],
                shopkeepers,
            )
            self.assertEqual(
                [npc["id"] for npc in retry_world["npcs"] if npc.get("shop_id") == shop["id"]],
                [shop["shopkeeper_id"]],
            )
            for collection in ("shops", "npcs"):
                self.assertEqual(
                    [item["id"] for item in retry_world[collection]],
                    [item["id"] for item in world[collection]],
                )
            self.assertEqual(retried.metadata["revision"], committed.metadata["revision"] + 1)
            self.assertEqual(
                stale_session._campaign_persistence_version,
                (campaign_id, retried.metadata["revision"]),
            )
            self.assertEqual(len(retried.history), len(committed.history) + 1)
            self.assertEqual(retried.history[:-1], committed.history)
            self.assertEqual(retried.history[-1]["player_message"], stale_body["message"])
            recovered_receipt = stale_store.get_turn_action(
                campaign_id, stale_body["action_id"]
            )
            self.assertEqual(recovered_receipt["response"], retried_response.json())
            self.assertEqual(
                stale_manager.get_turn_action(stale_record, stale_body["action_id"]),
                recovered_receipt,
            )
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, body["action_id"]), receipt
            )
            with closing(sqlite3.connect(self.store.path)) as connection:
                receipts_after = connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id", (campaign_id,),
                ).fetchall()
            self.assertEqual(len(receipts_after), len(receipts_before) + 1)
            self.assertTrue(all(row in receipts_after for row in receipts_before))

            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Recovered replay must not run another turn"),
                ) as replay_turn,
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Recovered replay must not save again"),
                ) as replay_save,
            ):
                replay = await stale_http.post(stale_url, json=stale_body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), retried_response.json())
            replay_turn.assert_not_called()
            replay_save.assert_not_called()
            self.assertEqual(stale_session.serialize_game_state(), retried_save)
            self.assertEqual(stale_record.journal, retried.payload["journal"])
            self.assertEqual(stale_store.get_campaign(campaign_id), retried)
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, body["action_id"]), receipt
            )
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, stale_body["action_id"]),
                recovered_receipt,
            )
            with closing(sqlite3.connect(self.store.path)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                        "ORDER BY action_id", (campaign_id,),
                    ).fetchall(),
                    receipts_after,
                )

    async def test_reopened_merchant_search_with_equivalent_wording_reuses_saved_identities(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        requests = [
            {"message": message, "action_id": str(uuid.uuid4())}
            for message in (
                "Buralarda bir tücaar var mı?",
                "Bir tüccar arıyorum.",
                "Yakınlarda bir satıcı bulunuyor mu?",
            )
        ]
        self.assertEqual(len({body["message"] for body in requests}), 3)
        self.assertEqual(len({body["action_id"] for body in requests}), 3)
        results = []
        receipts = {}

        async def search(http, manager, store, session_id, body):
            record = manager.get(session_id)
            session = record.game_session
            before = store.get_campaign(campaign_id)
            self.assertIsNone(store.get_turn_action(campaign_id, body["action_id"]))
            real_turn = session.run_player_turn
            captured = []

            @wraps(real_turn)
            def capture_search(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                captured.append(copy.deepcopy(result["action_result"]))
                return result

            # Observe the real offline engine; no scripted discovery or replay.
            with patch.object(session, "run_player_turn", new=capture_search):
                searched = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=body
                )
            self.assertEqual(searched.status_code, 200, searched.text)
            self.assertEqual(searched.json()["action_id"], body["action_id"])
            self.assertEqual(len(captured), 1)
            result = captured[0]
            self.assertEqual(result["action"], "local_search")
            self.assertEqual(result["status"], "found")
            self.assertTrue(result["success"])
            results.append(result)

            persisted = store.get_campaign(campaign_id)
            self.assertEqual(
                persisted.payload["engine_save"], session.serialize_game_state()
            )
            self.assertEqual(persisted.payload["journal"], record.journal)
            self.assertEqual(len(persisted.history), len(before.history) + 1)
            self.assertEqual(persisted.history[:-1], before.history)
            self.assertEqual(
                persisted.history[-1]["player_message"], body["message"]
            )
            world = persisted.payload["engine_save"]["world_state"]
            self.assertEqual(world["location"], city_id)
            self.assertEqual(len(world["shops"]), 1)
            shop = world["shops"][0]
            self.assertEqual(shop["id"], results[0]["shop_id"])
            self.assertEqual(shop["shopkeeper_id"], results[0]["target_id"])
            self.assertEqual(shop["location"], city_id)
            self.assertEqual(result["shop_id"], shop["id"])
            self.assertEqual(result["target_id"], shop["shopkeeper_id"])
            self.assertEqual(
                [npc["id"] for npc in world["npcs"]
                 if npc.get("shop_id") == shop["id"]],
                [shop["shopkeeper_id"]],
            )
            shopkeepers = [
                npc for npc in world["npcs"] if npc["id"] == shop["shopkeeper_id"]
            ]
            self.assertEqual(len(shopkeepers), 1)
            self.assertEqual(shopkeepers[0]["location"], city_id)
            if len(results) > 1:
                previous_world = before.payload["engine_save"]["world_state"]
                for collection in ("shops", "npcs"):
                    self.assertEqual(
                        [item["id"] for item in world[collection]],
                        [item["id"] for item in previous_world[collection]],
                    )

            for action_id, receipt in receipts.items():
                self.assertEqual(store.get_turn_action(campaign_id, action_id), receipt)
                self.assertEqual(manager.get_turn_action(record, action_id), receipt)
            receipt = store.get_turn_action(campaign_id, body["action_id"])
            self.assertIsNotNone(receipt)
            self.assertEqual(receipt["response"], searched.json())
            self.assertEqual(manager.get_turn_action(record, body["action_id"]), receipt)
            receipts[body["action_id"]] = copy.deepcopy(receipt)
            self.assertEqual(
                len({item["request_hash"] for item in receipts.values()}),
                len(receipts),
            )
            return persisted

        committed = await search(
            self.http, self.manager, self.store, created["session_id"], requests[0]
        )
        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            loaded_record = reopened_manager.get(session_id)
            self.assertEqual(
                loaded_record.game_session.serialize_game_state(),
                committed.payload["engine_save"],
            )
            self.assertEqual(resumed.json()["history"], committed.history)
            for body in requests[1:]:
                with self.subTest(message=body["message"]):
                    committed = await search(
                        http, reopened_manager, reopened_store, session_id, body
                    )

        # A second reopen verifies the paraphrases are durable independent turns.
        final_store = CampaignStore(self.store.path)
        final_manager = SessionManager(campaign_store=final_store)
        final_id, _, _, _, _ = final_manager.resume_campaign(campaign_id)
        final_record = final_manager.get(final_id)
        self.assertEqual(
            final_record.game_session.serialize_game_state(),
            committed.payload["engine_save"],
        )
        self.assertEqual(final_record.journal, committed.payload["journal"])
        final_campaign = final_store.get_campaign(campaign_id)
        self.assertEqual(final_campaign.history, committed.history)
        self.assertEqual(
            [entry["player_message"] for entry in final_campaign.history],
            [body["message"] for body in requests],
        )
        for action_id, receipt in receipts.items():
            self.assertEqual(final_store.get_turn_action(campaign_id, action_id), receipt)
            self.assertEqual(final_manager.get_turn_action(final_record, action_id), receipt)

    async def test_reopened_declined_merchant_search_does_not_rediscover_or_duplicate(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        discovery_body = {
            "message": "Bir tüccar arıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        discovered = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json=discovery_body,
        )
        self.assertEqual(discovered.status_code, 200, discovered.text)
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        self.assertEqual(len(saved_world["shops"]), 1)
        shop = saved_world["shops"][0]
        self.assertEqual(shop["location"], city_id)
        self.assertEqual(saved_world["flags"]["active_npc_id"], shop["shopkeeper_id"])
        discovery_receipt = self.store.get_turn_action(
            campaign_id, discovery_body["action_id"]
        )
        self.assertEqual(discovery_receipt["response"], discovered.json())

        class DeclinedSearchOllamaClient(FakeOllamaClient):
            def chat(self, *args, **kwargs):
                # Only the model boundary is scripted; Python still plans,
                # resolves and persists the actual resumed turn.
                if "intent" in kwargs["format"]["properties"]:
                    packet = {
                        "intent": "narrative",
                        "action": "decline_search",
                        "target": {"type": "none", "reference": ""},
                        "completion": "completed",
                        "confidence": 1.0,
                    }
                else:
                    packet = {
                        "narration": "Sokaktaki sesler sürüyor; tezgâh yerinde duruyor.",
                        "world_updates": {},
                        "lore_claims": [],
                    }
                return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}

        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(DeclinedSearchOllamaClient()),
        )
        declined_body = {
            "message": "Bir tüccar aramıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        self.assertNotEqual(declined_body["action_id"], discovery_body["action_id"])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            record = reopened_manager.get(session_id)
            session = record.game_session
            self.assertEqual(session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(resumed.json()["history"], committed.history)
            self.assertEqual(
                session.world_state["flags"]["active_npc_id"], shop["shopkeeper_id"]
            )
            self.assertGreaterEqual(
                session.world_state["flags"]["active_npc_until_turn"],
                session.world_state["flags"]["turn_index"],
            )
            before = reopened_store.get_campaign(campaign_id)
            self.assertIsNone(
                reopened_store.get_turn_action(campaign_id, declined_body["action_id"])
            )
            real_turn = session.run_player_turn
            results = []

            @wraps(real_turn)
            def capture_declined_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result))
                return result

            # Preserve dispatch's signature and observe a real new offline turn,
            # with the saved merchant still active, rather than receipt replay.
            with patch.object(session, "run_player_turn", new=capture_declined_turn):
                declined = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=declined_body
                )
            self.assertEqual(declined.status_code, 200, declined.text)
            self.assertEqual(declined.json()["action_id"], declined_body["action_id"])
            self.assertEqual(len(results), 1)
            action = results[0]["action_result"]
            self.assertEqual(action["action"], "narrative")
            self.assertEqual(action["status"], "resolved")
            self.assertTrue(action["success"])
            self.assertEqual(action["state_changes"], [])
            self.assertNotIn("shop_id", action)
            self.assertNotEqual(declined.json()["narration"], discovered.json()["narration"])
            self.assertEqual(declined.json()["narration"], results[0]["narration"])

            persisted = reopened_store.get_campaign(campaign_id)
            self.assertEqual(
                persisted.payload["engine_save"], session.serialize_game_state()
            )
            self.assertEqual(persisted.payload["journal"], record.journal)
            world = persisted.payload["engine_save"]["world_state"]
            self.assertEqual(world["location"], city_id)
            self.assertEqual(
                world["flags"]["turn_index"],
                saved_world["flags"]["turn_index"] + 1,
            )
            for collection in ("shops", "npcs"):
                self.assertEqual(
                    [item["id"] for item in world[collection]],
                    [item["id"] for item in saved_world[collection]],
                )
            self.assertEqual(world["shops"], saved_world["shops"])
            self.assertEqual(
                [npc["id"] for npc in world["npcs"] if npc.get("shop_id") == shop["id"]],
                [shop["shopkeeper_id"]],
            )
            self.assertEqual(len(persisted.history), len(before.history) + 1)
            self.assertEqual(persisted.history[:-1], before.history)
            self.assertEqual(
                persisted.history[-1]["player_message"], declined_body["message"]
            )
            self.assertEqual(
                persisted.history[-1]["narration"], results[0]["narration"]
            )
            declined_receipt = reopened_store.get_turn_action(
                campaign_id, declined_body["action_id"]
            )
            self.assertEqual(declined_receipt["response"], declined.json())
            self.assertEqual(
                reopened_manager.get_turn_action(record, declined_body["action_id"]),
                declined_receipt,
            )
            self.assertEqual(
                reopened_store.get_turn_action(campaign_id, discovery_body["action_id"]),
                discovery_receipt,
            )

        # Another fresh load checks the non-search history and result persisted;
        # no replay or additional action is sent here.
        final_store = CampaignStore(self.store.path)
        final_manager = SessionManager(campaign_store=final_store)
        final_id, final_record, _, _, _ = final_manager.resume_campaign(campaign_id)
        self.assertEqual(
            final_record.game_session.serialize_game_state(), persisted.payload["engine_save"]
        )
        self.assertEqual(final_record.journal, persisted.payload["journal"])
        self.assertEqual(final_store.get_campaign(campaign_id).history, persisted.history)
        self.assertEqual(
            final_store.get_turn_action(campaign_id, declined_body["action_id"]),
            declined_receipt,
        )
        self.assertEqual(
            final_manager.get_turn_action(final_manager.get(final_id), declined_body["action_id"]),
            declined_receipt,
        )

    async def test_failed_merchant_discovery_is_rolled_back_and_retry_commits_once(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        session = record.game_session
        url = f"/api/game/sessions/{created['session_id']}/turn"
        observation_body = {
            "message": "Şehirde dolanırken etrafımda neler var gözlemliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        observation_results = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_observation(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            observation_results.append(copy.deepcopy(result["action_result"]))
            return result

        # Commit real city progress before testing a later failed discovery.
        with patch.object(session, "run_player_turn", new=capture_observation):
            observed = await self.http.post(url, json=observation_body)
        self.assertEqual(observed.status_code, 200, observed.text)
        self.assertEqual(len(observation_results), 1)
        self.assertEqual(observation_results[0]["action"], "explore")
        self.assertEqual(observation_results[0]["status"], "observed")
        self.assertTrue(observation_results[0]["success"])
        self.assertNotEqual(observed.json()["state"], created["state"])
        self.assertTrue(record.journal["notable_events"])
        self.assertIn(
            city_id,
            [entry["location_id"] for entry in record.journal["discovered_locations"]],
        )
        observation_receipt = copy.deepcopy(
            self.manager.get_turn_action(record, observation_body["action_id"])
        )
        self.assertEqual(observation_receipt["response"], observed.json())
        self.assertEqual(
            self.store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        body = {
            "message": "Buralarda bir tücaar var mı?",
            "action_id": str(uuid.uuid4()),
        }
        before_save = copy.deepcopy(session.serialize_game_state())
        before_journal = copy.deepcopy(record.journal)
        before_memory = copy.deepcopy(record.narrative_memory)
        before_receipts = copy.deepcopy(record.turn_action_receipts)
        before_campaign = self.store.get_campaign(campaign_id)
        before_world = before_save["world_state"]
        self.assertEqual(before_world["location"], city_id)
        self.assertEqual(before_world["shops"], [])
        self.assertTrue(before_world["scene_state"]["scenes"][city_id]["materialized"])
        self.assertEqual(len(before_campaign.history), 1)
        self.assertEqual(before_campaign.payload["engine_save"], before_save)
        self.assertEqual(before_campaign.payload["journal"], before_journal)
        results = []
        attempted_saves = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            results.append(copy.deepcopy(result["action_result"]))
            return result

        def fail_save(*args, **kwargs):
            # Fail at the actual persistence boundary, after the real engine
            # has created both related records, not before discovery executes.
            attempted_saves.append(copy.deepcopy(session.serialize_game_state()))
            raise CampaignStorageError("database unavailable")

        with (
            patch.object(session, "run_player_turn", new=capture_turn),
            patch.object(self.store, "save_campaign", side_effect=fail_save) as failed_save,
        ):
            failed = await self.http.post(url, json=body)
        failed_save.assert_called_once()
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(
            failed.json()["detail"]["code"], "campaign_storage_unavailable"
        )
        self.assertNotIn("database unavailable", failed.text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "local_search")
        self.assertEqual(results[0]["status"], "found")
        self.assertTrue(results[0]["success"])
        uncommitted_shop_id = results[0]["shop_id"]
        uncommitted_npc_id = results[0]["target_id"]
        attempted_world = attempted_saves[0]["world_state"]
        self.assertEqual(len(attempted_world["shops"]), 1)
        attempted_shop = attempted_world["shops"][0]
        self.assertEqual(attempted_shop["id"], uncommitted_shop_id)
        self.assertEqual(attempted_shop["shopkeeper_id"], uncommitted_npc_id)
        self.assertEqual(attempted_shop["location"], city_id)
        new_shopkeepers = [
            npc for npc in attempted_world["npcs"]
            if npc.get("shop_id") == uncommitted_shop_id
        ]
        self.assertEqual(len(new_shopkeepers), 1)
        self.assertEqual(new_shopkeepers[0]["id"], uncommitted_npc_id)
        self.assertEqual(new_shopkeepers[0]["location"], city_id)

        # Rollback covers the entire engine and the API-owned side effects.
        self.assertEqual(session.serialize_game_state(), before_save)
        self.assertEqual(session.world_state["shops"], before_world["shops"])
        self.assertEqual(session.world_state["npcs"], before_world["npcs"])
        self.assertEqual(record.journal, before_journal)
        self.assertEqual(record.narrative_memory, before_memory)
        self.assertEqual(record.turn_action_receipts, before_receipts)
        self.assertEqual(
            self.manager.get_turn_action(record, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertIsNone(self.manager.get_turn_action(record, body["action_id"]))
        self.assertEqual(self.store.get_campaign(campaign_id), before_campaign)
        self.assertEqual(
            self.store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertIsNone(self.store.get_turn_action(campaign_id, body["action_id"]))

        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["state"], observed.json()["state"])
        self.assertEqual(resumed.json()["history"], before_campaign.history)
        reopened_record = reopened_manager.get(resumed.json()["session_id"])
        self.assertEqual(
            reopened_record.game_session.serialize_game_state(), before_save
        )
        self.assertEqual(reopened_record.journal, before_journal)
        self.assertEqual(reopened_record.narrative_memory, before_memory)
        self.assertEqual(reopened_record.turn_action_receipts, before_receipts)
        self.assertEqual(
            reopened_manager.get_turn_action(
                reopened_record, observation_body["action_id"]
            ),
            observation_receipt,
        )
        reopened_campaign = reopened_store.get_campaign(campaign_id)
        # Resume can refresh metadata timestamps without changing saved progress.
        self.assertEqual(reopened_campaign.payload, before_campaign.payload)
        self.assertEqual(reopened_campaign.history, before_campaign.history)
        self.assertEqual(reopened_campaign.combat_history, before_campaign.combat_history)
        reopened_world = reopened_record.game_session.world_state
        self.assertNotIn(
            uncommitted_shop_id, [shop["id"] for shop in reopened_world["shops"]]
        )
        self.assertNotIn(
            uncommitted_npc_id, [npc["id"] for npc in reopened_world["npcs"]]
        )
        self.assertEqual(
            reopened_store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertIsNone(
            reopened_store.get_turn_action(campaign_id, body["action_id"])
        )

        # Recovery re-executes the identical action once, then receipts replay it.
        with patch.object(session, "run_player_turn", new=capture_turn):
            retry = await self.http.post(url, json=body)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["action_id"], body["action_id"])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[-1]["action"], "local_search")
        self.assertEqual(results[-1]["status"], "found")
        self.assertTrue(results[-1]["success"])
        world = session.world_state
        self.assertEqual(len(world["shops"]), 1)
        shop = world["shops"][0]
        self.assertEqual(shop["id"], results[-1]["shop_id"])
        self.assertEqual(shop["shopkeeper_id"], results[-1]["target_id"])
        self.assertEqual(shop["location"], city_id)
        shopkeepers = [npc for npc in world["npcs"] if npc["id"] == shop["shopkeeper_id"]]
        self.assertEqual(len(shopkeepers), 1)
        self.assertEqual(shopkeepers[0]["location"], city_id)
        self.assertEqual(
            len([npc for npc in world["npcs"] if npc.get("shop_id") == shop["id"]]),
            1,
        )
        self.assertEqual(retry.json()["state"]["location"], city_id)
        committed_save = copy.deepcopy(session.serialize_game_state())
        committed_journal = copy.deepcopy(record.journal)
        committed_campaign = self.store.get_campaign(campaign_id)
        self.assertEqual(committed_campaign.payload["engine_save"], committed_save)
        self.assertEqual(committed_campaign.payload["journal"], committed_journal)
        self.assertEqual(len(committed_campaign.history), len(before_campaign.history) + 1)
        self.assertEqual(committed_campaign.history[:-1], before_campaign.history)
        self.assertEqual(
            self.store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertEqual(
            self.manager.get_turn_action(record, body["action_id"])["response"],
            retry.json(),
        )
        self.assertEqual(
            self.store.get_turn_action(campaign_id, body["action_id"])["response"],
            retry.json(),
        )
        with patch.object(
            session, "run_player_turn",
            side_effect=AssertionError("Discovery replay must not execute a turn"),
        ):
            replay = await self.http.post(url, json=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), retry.json())
        self.assertEqual(session.serialize_game_state(), committed_save)
        self.assertEqual(record.journal, committed_journal)
        self.assertEqual(self.store.get_campaign(campaign_id), committed_campaign)

        # A second fresh manager proves the recovered discovery and receipt
        # actually persisted, and replay after reopening cannot create duplicates.
        restarted_store = CampaignStore(self.store.path)
        restarted_manager = SessionManager(campaign_store=restarted_store)
        restarted_app = create_app(
            session_manager=restarted_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            loaded_record = restarted_manager.get(session_id)
            loaded = loaded_record.game_session
            self.assertEqual(loaded.serialize_game_state(), committed_save)
            self.assertEqual(loaded_record.journal, committed_journal)
            with patch.object(
                loaded, "run_player_turn",
                side_effect=AssertionError("Saved receipt must not rediscover a merchant"),
            ):
                replay = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=body
                )
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), {**retry.json(), "session_id": session_id})
            self.assertEqual(loaded.serialize_game_state(), committed_save)
            self.assertEqual(loaded_record.journal, committed_journal)
            persisted = restarted_store.get_campaign(campaign_id)
            self.assertEqual(persisted.payload["engine_save"], committed_save)
            self.assertEqual(persisted.payload["journal"], committed_journal)
            self.assertEqual(persisted.history, committed_campaign.history)
            self.assertEqual(len(loaded.world_state["shops"]), 1)
            self.assertEqual(
                len([
                    npc for npc in loaded.world_state["npcs"]
                    if npc.get("shop_id") == shop["id"]
                ]),
                1,
            )

            # A new request is not a receipt replay: the real offline search
            # must find the saved merchant without materializing another one.
            new_body = {**body, "action_id": str(uuid.uuid4())}
            self.assertNotEqual(new_body["action_id"], body["action_id"])
            previous_receipt = copy.deepcopy(
                restarted_store.get_turn_action(campaign_id, body["action_id"])
            )
            previous_world = persisted.payload["engine_save"]["world_state"]
            previous_shop_ids = [item["id"] for item in previous_world["shops"]]
            previous_npc_ids = [item["id"] for item in previous_world["npcs"]]
            new_results = []
            loaded_real_turn = loaded.run_player_turn

            @wraps(loaded_real_turn)
            def capture_new_search(*args, **kwargs):
                result = loaded_real_turn(*args, **kwargs)
                new_results.append(copy.deepcopy(result["action_result"]))
                return result

            with patch.object(loaded, "run_player_turn", new=capture_new_search):
                searched = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=new_body
                )
            self.assertEqual(searched.status_code, 200, searched.text)
            self.assertEqual(searched.json()["action_id"], new_body["action_id"])
            self.assertEqual(len(new_results), 1)
            self.assertEqual(new_results[0]["action"], "local_search")
            self.assertEqual(new_results[0]["status"], "found")
            self.assertTrue(new_results[0]["success"])
            self.assertEqual(new_results[0]["shop_id"], shop["id"])
            self.assertEqual(new_results[0]["target_id"], shop["shopkeeper_id"])

            searched_campaign = restarted_store.get_campaign(campaign_id)
            searched_world = searched_campaign.payload["engine_save"]["world_state"]
            self.assertEqual(
                searched_campaign.payload["engine_save"], loaded.serialize_game_state()
            )
            self.assertEqual(
                [item["id"] for item in searched_world["shops"]], previous_shop_ids
            )
            self.assertEqual(
                [item["id"] for item in searched_world["npcs"]], previous_npc_ids
            )
            self.assertEqual(len(searched_world["shops"]), 1)
            self.assertEqual(searched_world["shops"][0]["shopkeeper_id"], shop["shopkeeper_id"])
            self.assertEqual(
                [npc["id"] for npc in searched_world["npcs"]
                 if npc.get("shop_id") == shop["id"]],
                [shop["shopkeeper_id"]],
            )
            self.assertEqual(len(searched_campaign.history), len(persisted.history) + 1)
            self.assertEqual(searched_campaign.history[:-1], persisted.history)
            self.assertEqual(
                searched_campaign.history[-1]["player_message"], new_body["message"]
            )
            self.assertEqual(
                restarted_store.get_turn_action(campaign_id, body["action_id"]),
                previous_receipt,
            )
            self.assertEqual(
                restarted_store.get_turn_action(campaign_id, new_body["action_id"])["response"],
                searched.json(),
            )
            self.assertEqual(
                restarted_manager.get_turn_action(loaded_record, new_body["action_id"])["response"],
                searched.json(),
            )

    async def test_failed_merchant_discovery_retries_once_from_a_fresh_resume(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        session = record.game_session
        turn_url = f"/api/game/sessions/{created['session_id']}/turn"
        observation_body = {
            "message": "Şehirde dolanırken etrafımda neler var gözlemliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        results = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            results.append(copy.deepcopy(result["action_result"]))
            return result

        # Establish real committed city progress, rather than injecting state.
        with patch.object(session, "run_player_turn", new=capture_turn):
            observed = await self.http.post(turn_url, json=observation_body)
        self.assertEqual(observed.status_code, 200, observed.text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "explore")
        self.assertEqual(results[0]["status"], "observed")
        self.assertTrue(results[0]["success"])
        observation_receipt = copy.deepcopy(
            self.store.get_turn_action(campaign_id, observation_body["action_id"])
        )
        self.assertEqual(observation_receipt["response"], observed.json())
        before_save = copy.deepcopy(session.serialize_game_state())
        before_journal = copy.deepcopy(record.journal)
        before_memory = copy.deepcopy(record.narrative_memory)
        before_receipts = copy.deepcopy(record.turn_action_receipts)
        before_campaign = self.store.get_campaign(campaign_id)
        self.assertEqual(before_save["world_state"]["location"], city_id)
        self.assertEqual(before_save["world_state"]["shops"], [])
        self.assertTrue(
            before_save["world_state"]["scene_state"]["scenes"][city_id]["materialized"]
        )
        self.assertEqual(len(before_campaign.history), 1)
        self.assertEqual(
            before_campaign.history[0]["player_message"], observation_body["message"]
        )
        discovery_body = {
            "message": "Buralarda bir tücaar var mı?",
            "action_id": str(uuid.uuid4()),
        }
        attempted_saves = []

        def fail_save(*args, **kwargs):
            # Fail after discovery really creates the shop and linked keeper.
            attempted_saves.append(copy.deepcopy(session.serialize_game_state()))
            raise CampaignStorageError("database unavailable")

        with (
            patch.object(session, "run_player_turn", new=capture_turn),
            patch.object(self.store, "save_campaign", side_effect=fail_save) as failed_save,
        ):
            failed = await self.http.post(turn_url, json=discovery_body)
        failed_save.assert_called_once()
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(
            failed.json()["detail"]["code"], "campaign_storage_unavailable"
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[-1]["action"], "local_search")
        self.assertEqual(results[-1]["status"], "found")
        self.assertTrue(results[-1]["success"])
        attempted_world = attempted_saves[0]["world_state"]
        self.assertEqual(len(attempted_world["shops"]), 1)
        attempted_shop = attempted_world["shops"][0]
        self.assertEqual(attempted_shop["id"], results[-1]["shop_id"])
        self.assertEqual(attempted_shop["shopkeeper_id"], results[-1]["target_id"])
        self.assertEqual(
            [npc["id"] for npc in attempted_world["npcs"]
             if npc.get("shop_id") == attempted_shop["id"]],
            [attempted_shop["shopkeeper_id"]],
        )
        self.assertEqual(session.serialize_game_state(), before_save)
        self.assertEqual(record.journal, before_journal)
        self.assertEqual(record.narrative_memory, before_memory)
        self.assertEqual(record.turn_action_receipts, before_receipts)
        self.assertEqual(self.store.get_campaign(campaign_id), before_campaign)
        self.assertIsNone(
            self.store.get_turn_action(campaign_id, discovery_body["action_id"])
        )

        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"], observed.json()["state"])
            self.assertEqual(resumed.json()["history"], before_campaign.history)
            resumed_record = reopened_manager.get(resumed.json()["session_id"])
            resumed_session = resumed_record.game_session
            self.assertIsNot(resumed_session, session)
            self.assertEqual(resumed_session.serialize_game_state(), before_save)
            self.assertEqual(resumed_record.journal, before_journal)
            self.assertEqual(resumed_record.narrative_memory, before_memory)
            self.assertEqual(resumed_record.turn_action_receipts, before_receipts)
            reopened_campaign = reopened_store.get_campaign(campaign_id)
            self.assertEqual(reopened_campaign.payload, before_campaign.payload)
            self.assertEqual(reopened_campaign.history, before_campaign.history)
            self.assertIsNone(
                reopened_manager.get_turn_action(
                    resumed_record, discovery_body["action_id"]
                )
            )
            self.assertIsNone(
                reopened_store.get_turn_action(campaign_id, discovery_body["action_id"])
            )
            self.assertEqual(
                reopened_manager.get_turn_action(
                    resumed_record, observation_body["action_id"]
                ),
                observation_receipt,
            )
            resumed_url = f"/api/game/sessions/{resumed.json()['session_id']}/turn"
            resumed_real_turn = resumed_session.run_player_turn
            retry_results = []

            @wraps(resumed_real_turn)
            def capture_retry(*args, **kwargs):
                result = resumed_real_turn(*args, **kwargs)
                retry_results.append(copy.deepcopy(result["action_result"]))
                return result

            with (
                patch.object(
                    session, "run_player_turn",
                    side_effect=AssertionError("Retry must use the resumed session"),
                ) as original_turn,
                patch.object(resumed_session, "run_player_turn", new=capture_retry),
                patch.object(
                    reopened_store, "save_campaign", wraps=reopened_store.save_campaign
                ) as retry_save,
            ):
                retry = await http.post(resumed_url, json=discovery_body)
            self.assertEqual(retry.status_code, 200, retry.text)
            original_turn.assert_not_called()
            retry_save.assert_called_once()
            self.assertEqual(len(retry_results), 1)
            self.assertEqual(retry_results[0]["action"], "local_search")
            self.assertEqual(retry_results[0]["status"], "found")
            self.assertTrue(retry_results[0]["success"])
            self.assertEqual(retry.json()["action_id"], discovery_body["action_id"])
            self.assertEqual(retry.json()["state"]["location"], city_id)
            committed_save = copy.deepcopy(resumed_session.serialize_game_state())
            world = committed_save["world_state"]
            self.assertEqual(len(world["shops"]), 1)
            shop = world["shops"][0]
            self.assertEqual(shop["id"], retry_results[0]["shop_id"])
            self.assertEqual(shop["shopkeeper_id"], retry_results[0]["target_id"])
            self.assertEqual(shop["location"], city_id)
            self.assertEqual(
                [npc["id"] for npc in world["npcs"] if npc.get("shop_id") == shop["id"]],
                [shop["shopkeeper_id"]],
            )
            shopkeepers = [npc for npc in world["npcs"] if npc["id"] == shop["shopkeeper_id"]]
            self.assertEqual(len(shopkeepers), 1)
            self.assertEqual(shopkeepers[0]["location"], city_id)
            committed_campaign = reopened_store.get_campaign(campaign_id)
            self.assertEqual(committed_campaign.payload["engine_save"], committed_save)
            self.assertEqual(committed_campaign.payload["journal"], resumed_record.journal)
            self.assertEqual(len(committed_campaign.history), len(before_campaign.history) + 1)
            self.assertEqual(committed_campaign.history[:-1], before_campaign.history)
            self.assertEqual(
                committed_campaign.history[-1]["player_message"], discovery_body["message"]
            )
            self.assertEqual(
                committed_campaign.history[-1]["narration"], retry.json()["narration"]
            )
            for manager, receipt_record in (
                (self.manager, record), (reopened_manager, resumed_record)
            ):
                self.assertEqual(
                    manager.get_turn_action(receipt_record, observation_body["action_id"]),
                    observation_receipt,
                )
            self.assertEqual(
                reopened_store.get_turn_action(campaign_id, observation_body["action_id"]),
                observation_receipt,
            )
            discovery_receipt = copy.deepcopy(
                reopened_manager.get_turn_action(resumed_record, discovery_body["action_id"])
            )
            self.assertEqual(discovery_receipt["response"], retry.json())
            self.assertEqual(
                reopened_store.get_turn_action(campaign_id, discovery_body["action_id"]),
                discovery_receipt,
            )
            with (
                patch.object(
                    resumed_session, "run_player_turn",
                    side_effect=AssertionError("Replay must not execute another turn"),
                ) as replay_turn,
                patch.object(
                    reopened_store, "save_campaign",
                    side_effect=AssertionError("Replay must not save again"),
                ) as replay_save,
            ):
                replay = await http.post(resumed_url, json=discovery_body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), retry.json())
            replay_turn.assert_not_called()
            replay_save.assert_not_called()
            self.assertEqual(resumed_session.serialize_game_state(), committed_save)
            self.assertEqual(resumed_record.journal, committed_campaign.payload["journal"])
            self.assertEqual(reopened_store.get_campaign(campaign_id), committed_campaign)
            for action_id, receipt in (
                (observation_body["action_id"], observation_receipt),
                (discovery_body["action_id"], discovery_receipt),
            ):
                self.assertEqual(reopened_store.get_turn_action(campaign_id, action_id), receipt)
                self.assertEqual(reopened_manager.get_turn_action(resumed_record, action_id), receipt)

    async def test_altered_exit_retry_conflicts_before_stale_campaign_check(self):
        city_id = "fr:city:neverwinter"
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        campaign_id = created["campaign_id"]
        initial_url = f"/api/game/sessions/{created['session_id']}/turn"
        for message in ("Yakınlarda bir taverna arıyorum.", "Enter the tavern."):
            entered = await self.http.post(
                initial_url,
                json={"message": message, "action_id": str(uuid.uuid4())},
            )
            self.assertEqual(entered.status_code, 200, entered.text)
        tavern_id = entered.json()["state"]["location"]
        self.assertNotEqual(tavern_id, city_id)

        active_store = CampaignStore(self.store.path)
        stale_store = CampaignStore(self.store.path)
        active_manager = SessionManager(campaign_store=active_store)
        stale_manager = SessionManager(campaign_store=stale_store)
        active_app = create_app(
            session_manager=active_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        stale_app = create_app(
            session_manager=stale_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=active_app),
                base_url="http://testserver",
            ) as active_http,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=stale_app),
                base_url="http://testserver",
            ) as stale_http,
        ):
            active_resume = await active_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            stale_resume = await stale_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            for response in (active_resume, stale_resume):
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["state"], entered.json()["state"])
            active_id = active_resume.json()["session_id"]
            stale_id = stale_resume.json()["session_id"]
            stale_record = stale_manager.get(stale_id)
            stale_session = stale_record.game_session
            self.assertIsNot(active_manager.get(active_id).game_session, stale_session)
            stale_save = copy.deepcopy(stale_session.serialize_game_state())
            before = active_store.get_campaign(campaign_id)
            self.assertEqual(stale_save["world_state"]["location"], tavern_id)
            self.assertEqual(stale_save, before.payload["engine_save"])

            # Execute a real exit, while the other manager keeps its tavern state.
            exit_body = {
                "message": "Tavernadan dışarı çıkıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            accepted = await active_http.post(
                f"/api/game/sessions/{active_id}/turn", json=exit_body
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(accepted.json()["state"]["location"], city_id)
            committed = active_store.get_campaign(campaign_id)
            self.assertEqual(committed.payload["engine_save"]["world_state"]["location"], city_id)
            self.assertEqual(committed.metadata["revision"], before.metadata["revision"] + 1)
            self.assertEqual(committed.history[:-1], before.history)
            self.assertEqual(committed.history[-1]["player_message"], exit_body["message"])
            exit_receipt = copy.deepcopy(
                active_store.get_turn_action(campaign_id, exit_body["action_id"])
            )
            self.assertEqual(exit_receipt["response"], accepted.json())
            self.assertEqual(stale_session.serialize_game_state(), stale_save)

            altered_body = {**exit_body, "message": "Tavernada bekliyorum."}
            stale_url = f"/api/game/sessions/{stale_id}/turn"
            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Conflicting retries must not run the engine"),
                ) as blocked_turn,
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Conflicting retries must not save"),
                ) as blocked_save,
            ):
                rejected = await stale_http.post(stale_url, json=altered_body)
                self.assertEqual(rejected.status_code, 409, rejected.text)
                self.assertEqual(rejected.json()["detail"]["code"], "action_id_conflict")
                rejected_campaign = stale_store.get_campaign(campaign_id)
                self.assertEqual(rejected_campaign.payload, committed.payload)
                self.assertEqual(rejected_campaign.metadata, committed.metadata)
                self.assertEqual(rejected_campaign.history, committed.history)
                self.assertEqual(rejected_campaign.combat_history, committed.combat_history)
                self.assertEqual(
                    stale_store.get_turn_action(campaign_id, exit_body["action_id"]),
                    exit_receipt,
                )
                self.assertEqual(stale_session.serialize_game_state(), stale_save)
                blocked_turn.assert_not_called()
                blocked_save.assert_not_called()

                # The conflict must not poison the accepted action's valid replay.
                replay = await stale_http.post(stale_url, json=exit_body)
                self.assertEqual(replay.status_code, 200, replay.text)
                expected_replay = copy.deepcopy(accepted.json())
                expected_replay["session_id"] = stale_id
                self.assertEqual(replay.json(), expected_replay)
                blocked_turn.assert_not_called()
                blocked_save.assert_not_called()

            replayed_campaign = stale_store.get_campaign(campaign_id)
            self.assertEqual(replayed_campaign.payload, committed.payload)
            self.assertEqual(replayed_campaign.metadata, committed.metadata)
            self.assertEqual(replayed_campaign.history, committed.history)
            self.assertEqual(replayed_campaign.combat_history, committed.combat_history)
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, exit_body["action_id"]),
                exit_receipt,
            )
            self.assertEqual(stale_session.serialize_game_state(), stale_save)
if __name__ == "__main__":
    unittest.main()
