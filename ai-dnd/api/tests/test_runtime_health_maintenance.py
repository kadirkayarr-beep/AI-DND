"""Focused maintenance regressions; disposable saves and offline models only."""

import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import game
from api.main import create_app, _lore_context_for_turn
from api.campaign_journal import create_initial_campaign_journal
from api.lore_authority import EntityType, CampaignLoreState
from api.lore_authority.campaign_state import CANONICAL_LOCATION_TYPES
from api.narrative_memory import update_narrative_memory
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.serializers import serialize_session_state
from api.session_manager import SessionManager
from api.tests.test_lore_authority import entity, verified_registry
from api.tests.test_lore_engine_integration import bound_lore_state


from api.auth import FixedAuthenticator
from api.tests.auth_fixture import TEST_PLAYER
class LegacyDoorResumeTests(unittest.TestCase):
    def test_locked_legacy_door_resumes_without_inventing_an_identity_or_action(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CampaignStore(Path(directory) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
            manager = SessionManager(campaign_store=store)
            cid, _, record, _ = manager.create_campaign("Legacy doors")
            session = record.game_session
            session.world_state["doors"] = [
                {"name": "Legacy door", "description": "An old door.",
                 "location": session.world_state["location"], "locked": True,
                 "open": False, "broken": False},
                {"id": "modern-door", "name": "Modern door", "description": "",
                 "location": session.world_state["location"], "locked": True,
                 "open": False, "broken": False},
            ]
            manager.save_campaign(cid)
            before = copy.deepcopy(session.serialize_game_state())
            rng_before = session.rng.getstate()
            restarted = SessionManager(campaign_store=CampaignStore(store.path, bound_principal=TEST_PLAYER))
            _, resumed, _, _, _ = restarted.resume_campaign(cid)
            projected = serialize_session_state(resumed.game_session, resumed.journal)
            self.assertEqual(resumed.game_session.serialize_game_state(), before)
            self.assertEqual(resumed.game_session.rng.getstate(), rng_before)
            self.assertNotIn("id", resumed.game_session.world_state["doors"][0])
            self.assertTrue(resumed.game_session.world_state["doors"][0]["locked"])
            import timed_gameplay
            actions = timed_gameplay.public_expedition(resumed.game_session)["actions"]
            self.assertIn("/explore door modern-door unlock",
                          [a["message"] for a in actions])
            self.assertFalse(any("Legacy door" in a["label"] for a in actions))
            self.assertIsInstance(projected, dict)
            import exploration
            from combat_lifecycle import CombatRequestError
            with self.assertRaises(CombatRequestError):
                exploration._door_action(resumed.game_session, "", "missing", "unlock")


class CanonicalLocationTypeTests(unittest.TestCase):
    def context_location(self, kind, registered=True):
        target = "location:destination"
        registry = verified_registry(entities=[
            entity("location:start", "Start", entity_type="CITY"),
            *([entity(target, "Destination", entity_type=kind.value)] if registered else []),
        ])
        session = SimpleNamespace(world_state={"location": "runtime", "npcs": []})
        with patch.object(registry, "retrieve_lore_context", return_value={}) as retrieve:
            _lore_context_for_turn(
                SimpleNamespace(lore_authority=bound_lore_state()), session, "", None,
                scene_plan={"lore_location_id": target}, registry=registry,
            )
        return retrieve.call_args.kwargs["current_location_id"]

    def test_registered_canonical_location_types_are_accepted(self):
        for kind in CANONICAL_LOCATION_TYPES:
            with self.subTest(kind=kind):
                self.assertEqual(self.context_location(kind), "location:destination")

    def test_registered_non_location_types_cannot_supply_location_context(self):
        for kind in set(EntityType) - CANONICAL_LOCATION_TYPES:
            with self.subTest(kind=kind):
                self.assertEqual(self.context_location(kind), "location:start")

    def test_unregistered_location_does_not_gain_canonical_authority(self):
        self.assertEqual(self.context_location(EntityType.CITY, registered=False),
                         "location:start")


class CheckpointFailureRollbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.store = CampaignStore(Path(directory) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
        self.manager = SessionManager(campaign_store=self.store)

        class OfflineClient:
            def list(self):
                return {"models": [{"model": "qwen3:8b"}]}

            def chat(self, **kwargs):
                raise RuntimeError("offline injected provider failure")

        self.adapter = AuthenticatedOllamaAdapter(OfflineClient())
        self.enterContext(self.adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=self.adapter, authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),
                                     base_url="http://testserver")
        self.addAsyncCleanup(self.http.aclose)

    def owned_state(self, record):
        session = record.game_session
        return copy.deepcopy({
            "engine": session.serialize_game_state(), "messages": session.messages,
            "rng": session.rng.getstate(), "metadata": session.world_metadata,
            "journal": record.journal, "memory": record.narrative_memory,
            "lore": record.lore_authority.to_dict(),
            "combat_history": record.combat_history,
            "actions": record.turn_action_receipts,
        })

    async def assert_checkpoint_failure_rolls_back(self, model_failure):
        cid, sid, record, _ = self.manager.create_campaign("Checkpoint failure")
        session = record.game_session
        game._capture_combat_death_checkpoint(session=session)
        session.world_state["inventory"].append("Pre-turn item")
        session.world_state["location"] = "tavern"
        session.world_metadata["weather"] = "rain"
        record.journal = create_initial_campaign_journal(
            session.world_state, session.world_metadata)
        record.narrative_memory = update_narrative_memory(
            record.narrative_memory, player_message="I wait here.",
            narration="A quiet moment.", action_result={"action": "wait"},
            world_state_before={}, world_state_after=session.world_state,
        )
        record.lore_authority = CampaignLoreState.from_mapping(bound_lore_state().to_dict())
        session.messages.append({"role": "user", "content": "Before rejected turn"})
        session.rng.random()
        self.manager.save_campaign(cid)
        before = self.owned_state(record)
        persisted_before = self.store.get_campaign(cid).payload
        checkpoint_applied = []

        def failed_turn(message, **kwargs):
            game._restore_combat_death_checkpoint("failed_death_saves", session=session)
            checkpoint_applied.append(self.owned_state(record))
            session.messages.append({"role": "assistant", "content": "Not committed"})
            session.rng.random()
            if model_failure:
                try:
                    self.adapter.chat(model="qwen3:8b", messages=[])
                except RuntimeError:
                    pass  # Mirrors the engine's deterministic model fallback.
                return {"narration": "Not committed", "action_result": {"action": "wait"}}
            raise RuntimeError("injected engine failure after checkpoint restore")

        with patch.object(session, "run_player_turn", new=failed_turn):
            response = await self.http.post(f"/api/game/sessions/{sid}/turn",
                                            json={"message": "Bekle."})
        self.assertEqual(response.status_code, 503 if model_failure else 500, response.text)
        self.assertEqual(len(checkpoint_applied), 1)
        for key in ("engine", "journal", "memory", "lore", "metadata"):
            self.assertNotEqual(checkpoint_applied[0][key], before[key], key)
        self.assertEqual(self.owned_state(record), before)
        self.assertEqual(self.store.get_campaign(cid).payload, persisted_before)
        self.assertEqual(self.store.get_campaign(cid).history, [])

    async def test_engine_failure_after_normal_death_checkpoint_restores_all_owners(self):
        await self.assert_checkpoint_failure_rolls_back(False)

    async def test_model_failure_after_normal_death_checkpoint_restores_all_owners(self):
        await self.assert_checkpoint_failure_rolls_back(True)


class MerchantFixtureIsolationTests(unittest.TestCase):
    def test_repeated_merchant_fixture_restores_uuid_and_engine_model_bindings(self):
        import uuid
        import living_world
        from api.tests.test_campaign_api import CampaignApiTests

        original_uuid4 = uuid.uuid4
        original_ambient_context = living_world.set_ambient_context
        target = game.ollama
        original_list, original_chat = target.list, target.chat
        for _ in range(2):
            result = unittest.TestResult()
            CampaignApiTests(
                "test_reopened_declined_merchant_search_does_not_rediscover_or_duplicate"
            ).run(result)
            self.assertEqual(result.testsRun, 1)
            self.assertEqual(result.failures + result.errors, [])
            self.assertEqual(result.skipped, [])
            self.assertIs(uuid.uuid4, original_uuid4)
            self.assertIs(living_world.set_ambient_context, original_ambient_context)
            self.assertIs(game.ollama, target)
            self.assertIs(target.list, original_list)
            self.assertIs(target.chat, original_chat)
