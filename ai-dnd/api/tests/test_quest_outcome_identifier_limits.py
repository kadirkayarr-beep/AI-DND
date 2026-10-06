"""Generated quest identifiers versus published bounds, not runtime validation.

The overflow tests deliberately document a real contract violation without
truncating canonical IDs or adding bounds to the permissive runtime model.
"""

import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
import yaml

import game
import quest_catalog
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.schemas import QuestOutcome, TurnResponse
from api.serializers import serialize_session_state
from api.session_manager import SessionManager


SPEC_PATH = Path(__file__).resolve().parents[3] / "lib/api-spec/openapi.yaml"
OUTCOME_SCHEMA = yaml.safe_load(SPEC_PATH.read_text())["components"]["schemas"]["QuestOutcome"]
QUEST_ID = "quest." + "q" * 114
OBJECTIVE_ID = "objective." + "o" * 110


def definition(target):
    return {
        "quest_id": QUEST_ID,
        "title": "Boundary quest",
        "description": "Test-only server-owned quest",
        "objectives": [{
            "objective_id": OBJECTIVE_ID,
            "description": "Visit twice",
            "type": "visit_location",
            "target": target,
            "required_count": 2,
        }],
    }


def register_location(session, target):
    session.world_state["locations"][target] = copy.deepcopy(
        session.world_state["locations"]["forest"]
    )


def visit(session, target, turn):
    before = copy.deepcopy(session.world_state)
    session.world_state["flags"]["turn_index"] = turn
    session.world_state["location"] = target
    return session.evaluate_quest_events(before, {"action": "travel"})


class OutcomeAssertions:
    def assert_turn_projection(self, session, outcomes):
        # This is the exact response model used by api.main's turn endpoint.
        # Test it separately from other endpoint consumers of canonical state.
        projected = TurnResponse(
            session_id="00000000-0000-4000-8000-000000000001",
            action_id="00000000-0000-4000-8000-000000000002",
            narration="Deterministic quest evidence.",
            state=serialize_session_state(session),
            quest_outcomes=outcomes,
        ).model_dump(mode="json")
        self.assertEqual(projected["quest_outcomes"], outcomes)
        return projected

    def assert_outcome(self, outcome, kind, source, turn, *, overflow=False):
        objective = OBJECTIVE_ID if kind.startswith("objective_") else None
        # Equality is essential: merely checking lengths would allow truncation
        # or replacing the canonical source/quest/objective with another ID.
        self.assertEqual(outcome, {
            "event_id": f"quest:{kind}:{QUEST_ID}:{source}",
            "quest_id": QUEST_ID,
            "transition": kind,
            "objective_id": objective,
            "source_event_id": source,
            "turn_index": turn,
        })
        self.assertEqual(set(outcome), set(OUTCOME_SCHEMA["required"]))
        self.assertEqual(
            OUTCOME_SCHEMA["properties"]["objective_id"]["type"],
            ["string", "null"],
        )
        for field, maximum in (
            ("event_id", 300), ("source_event_id", 300),
            ("quest_id", 120), ("objective_id", 120),
        ):
            with self.subTest(transition=kind, field=field):
                self.assertEqual(OUTCOME_SCHEMA["properties"][field]["maxLength"], maximum)
                value = outcome[field]
                if value is None:
                    self.assertEqual(field, "objective_id")
                elif overflow and field == "event_id":
                    self.assertGreater(len(value), maximum)
                else:
                    self.assertLessEqual(len(value), maximum)
        self.assertGreaterEqual(outcome["turn_index"], 0)

    def install(self, target):
        fixture = definition(target)
        # This must be accepted by the real catalog, not bypass its limits.
        quest_catalog.validate_catalog((fixture,))
        self.enterContext(patch.object(quest_catalog, "CATALOG", (fixture,)))


class QuestOutcomeIdentifierEngineTests(OutcomeAssertions, unittest.TestCase):
    def test_boundary_commands_preserve_ids_and_nullable_objective(self):
        self.install("forest")
        self.assertEqual(len(QUEST_ID), 120)
        self.assertEqual(len(OBJECTIVE_ID), 120)
        for cancel_accepted in (False, True):
            with self.subTest(cancel_accepted=cancel_accepted):
                session = game.create_session(seed=7)
                if cancel_accepted:
                    accepted = session.accept_quest(QUEST_ID)["transition"]
                    self.assert_outcome(
                        accepted, "accepted", f"command:accept:{QUEST_ID}:0", 0,
                    )
                    self.assertIsNone(session.accept_quest(QUEST_ID)["transition"])
                cancelled = session.cancel_quest(QUEST_ID)["transition"]
                self.assert_outcome(
                    cancelled, "cancelled", f"command:cancel:{QUEST_ID}:0", 0,
                )
                self.assertIsNone(session.cancel_quest(QUEST_ID)["transition"])

    def test_progress_and_completion_fit_at_exact_event_id_boundary(self):
        # At turn 3, this puts the longest transition at exactly 300 chars.
        target = "l" * 142
        self.install(target)
        session = game.create_session(seed=7)
        register_location(session, target)
        session.accept_quest(QUEST_ID)
        progress = visit(session, target, 1)
        self.assertEqual(len(progress), 1)
        self.assert_outcome(progress[0], "objective_progress", f"location:1:{target}", 1)
        self.assert_turn_projection(session, progress)
        self.assertEqual(visit(session, "tavern", 2), [])
        completed = visit(session, target, 3)
        self.assertEqual([item["transition"] for item in completed],
                         ["objective_completed", "completed"])
        for item in completed:
            self.assert_outcome(item, item["transition"], f"location:3:{target}", 3)
        self.assertEqual(len(completed[0]["event_id"]), 300)
        self.assertIsNone(completed[1]["objective_id"])
        self.assert_turn_projection(session, completed)

    def test_valid_maximum_target_exposes_generated_event_id_overflow(self):
        target = "l" * 160
        self.install(target)
        session = game.create_session(seed=7)
        register_location(session, target)
        session.accept_quest(QUEST_ID)
        progress = visit(session, target, 1)
        self.assertEqual(len(progress), 1)
        self.assert_outcome(
            progress[0], "objective_progress", f"location:1:{target}", 1, overflow=True,
        )
        self.assertEqual(len(progress[0]["event_id"]), 317)
        self.assert_turn_projection(session, progress)
        visit(session, "tavern", 2)
        completed = visit(session, target, 3)
        self.assertEqual([item["transition"] for item in completed],
                         ["objective_completed", "completed"])
        for item, length in zip(completed, (318, 308)):
            self.assert_outcome(
                item, item["transition"], f"location:3:{target}", 3, overflow=True,
            )
            self.assertEqual(len(item["event_id"]), length)
        self.assert_turn_projection(session, completed)

    def test_runtime_model_remains_intentionally_unbounded(self):
        # Construction-time parity cannot establish generation-time compliance.
        outcome = game.GameSession._quest_transition(
            "objective_progress", "q" * 121, "o" * 121, "s" * 301, 1,
        )
        self.assertEqual(QuestOutcome.model_validate(outcome).model_dump(), outcome)

    def test_boundary_source_event_id_exposes_composite_id_overflow(self):
        # Turn indices have no published/runtime upper bound. A 130-digit
        # canonical turn and maximum catalog target yield a 300-char source.
        target = "l" * 160
        self.install(target)
        session = game.create_session(seed=7)
        register_location(session, target)
        session.accept_quest(QUEST_ID)
        turn = 10 ** 129
        progress = visit(session, target, turn)
        self.assertEqual(len(progress), 1)
        source = f"location:{turn}:{target}"
        self.assertEqual(len(source), 300)
        self.assert_outcome(
            progress[0], "objective_progress", source, turn, overflow=True,
        )
        self.assertEqual(len(progress[0]["event_id"]), 446)
        self.assert_turn_projection(session, progress)
        self.assertEqual(visit(session, "tavern", turn + 1), [])
        completed = visit(session, target, turn + 2)
        self.assertEqual([item["transition"] for item in completed],
                         ["objective_completed", "completed"])
        source = f"location:{turn + 2}:{target}"
        self.assertEqual(len(source), 300)
        for item, length in zip(completed, (447, 437)):
            self.assert_outcome(
                item, item["transition"], source, turn + 2, overflow=True,
            )
            self.assertEqual(len(item["event_id"]), length)
        self.assert_turn_projection(session, completed)


class NoModelClient:
    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        raise AssertionError("Identifier projection tests must not call a model")


class QuestOutcomeIdentifierApiTests(OutcomeAssertions, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = SessionManager()
        adapter = AuthenticatedOllamaAdapter(NoModelClient())
        self.enterContext(adapter.engine_binding())
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(
                session_manager=self.manager, ollama_adapter=adapter,
            )),
            base_url="http://testserver",
        )

    async def asyncTearDown(self):
        await self.http.aclose()

    async def new_session(self):
        response = await self.http.post("/api/sessions")
        self.assertEqual(response.status_code, 200, response.text)
        session_id = response.json()["session_id"]
        return session_id, self.manager.get(session_id).game_session

    async def command(self, session_id, kind):
        response = await self.http.post(
            f"/api/game/sessions/{session_id}/quests/{QUEST_ID}/{kind}",
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_command_projection_preserves_boundary_ids_and_null_objective(self):
        self.install("forest")
        for cancel_accepted in (False, True):
            with self.subTest(cancel_accepted=cancel_accepted):
                session_id, session = await self.new_session()
                if cancel_accepted:
                    body = await self.command(session_id, "accept")
                    self.assert_outcome(
                        body["outcome"], "accepted", f"command:accept:{QUEST_ID}:0", 0,
                    )
                    self.assertEqual(body["quest"]["quest_id"], QUEST_ID)
                    self.assertEqual(body["quest"]["objectives"][0]["objective_id"], OBJECTIVE_ID)
                    self.assertIsNone((await self.command(session_id, "accept"))["outcome"])
                body = await self.command(session_id, "cancel")
                self.assert_outcome(
                    body["outcome"], "cancelled", f"command:cancel:{QUEST_ID}:0", 0,
                )
                self.assertEqual(body["quest"]["status"], "cancelled")
                self.assertEqual(body["state"]["quests"][0]["quest_id"], QUEST_ID)
                self.assertIsNone((await self.command(session_id, "cancel"))["outcome"])
                self.assertEqual(session.world_state["quests"][0]["status"], "cancelled")

    async def test_boundary_command_sources_expose_http_composite_id_overflow(self):
        # Extreme but legal canonical integers make the source reach its
        # published boundary. Unlike the long-location case, these commands
        # reach the actual HTTP response with overlong composite event IDs.
        self.install("forest")
        session_id, session = await self.new_session()
        turn = 10 ** 163
        session.world_state["flags"]["turn_index"] = turn
        for command, kind, length in (
            ("accept", "accepted", 436), ("cancel", "cancelled", 437),
        ):
            with self.subTest(command=command):
                body = await self.command(session_id, command)
                source = f"command:{command}:{QUEST_ID}:{turn}"
                self.assertEqual(len(source), 300)
                self.assert_outcome(body["outcome"], kind, source, turn, overflow=True)
                self.assertEqual(len(body["outcome"]["event_id"]), length)

    async def test_turn_endpoint_preserves_boundary_quest_and_objective_ids(self):
        # The endpoint's narrative-memory consumer permits 120-character
        # location IDs. Larger catalog targets are tested at the engine and
        # TurnResponse projection boundary separately.
        target = "l" * 120
        self.install(target)
        session_id, session = await self.new_session()
        register_location(session, target)
        await self.command(session_id, "accept")
        emitted = []

        def deterministic_visit(_message):
            # Only the model-driven turn orchestration is replaced. Outcomes
            # come from actual canonical before/after engine evaluation.
            turn = session.world_state["flags"]["turn_index"] + 1
            location = "tavern" if turn == 2 else target
            outcomes = visit(session, location, turn)
            emitted.append(copy.deepcopy(outcomes))
            return {
                "narration": "A deterministic location change.",
                "action_result": {"action": "travel", "quest_outcomes": outcomes},
            }

        self.enterContext(patch.object(session, "run_player_turn", deterministic_visit))
        for turn, kinds in (
            (1, ["objective_progress"]), (2, []),
            (3, ["objective_completed", "completed"]),
        ):
            response = await self.http.post(
                f"/api/game/sessions/{session_id}/turn",
                json={"message": "Travel"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            outcomes = response.json()["quest_outcomes"]
            self.assertEqual(outcomes, emitted[-1])
            self.assertEqual([item["transition"] for item in outcomes], kinds)
            for item in outcomes:
                self.assert_outcome(
                    item, item["transition"], f"location:{turn}:{target}", turn,
                )
            if turn == 3:
                self.assertEqual(response.json()["state"]["quests"][0]["status"], "completed")
                self.assertEqual(len(outcomes[0]["event_id"]), 278)

    async def test_long_canonical_target_is_rejected_before_http_outcome_projection(self):
        # Do not claim model-level overflow is an emitted successful HTTP reply:
        # today narrative memory rejects this otherwise valid catalog target.
        target = "l" * 160
        self.install(target)
        session_id, session = await self.new_session()
        register_location(session, target)
        await self.command(session_id, "accept")
        before = copy.deepcopy(session.world_state)
        emitted = []

        def deterministic_visit(_message):
            emitted.extend(visit(session, target, 1))
            return {
                "narration": "A deterministic location change.",
                "action_result": {"action": "travel", "quest_outcomes": emitted},
            }

        self.enterContext(patch.object(session, "run_player_turn", deterministic_visit))
        response = await self.http.post(
            f"/api/game/sessions/{session_id}/turn",
            json={"message": "Travel"},
        )
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json()["detail"]["code"], "narrative_memory_error")
        self.assertEqual(len(emitted), 1)
        self.assert_outcome(
            emitted[0], "objective_progress", f"location:1:{target}", 1, overflow=True,
        )
        self.assertEqual(session.world_state, before)


if __name__ == "__main__":
    unittest.main()
