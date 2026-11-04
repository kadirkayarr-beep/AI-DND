"""Evidence behind the room journeys (03_room_sleep, 07_leave_room), kept as tests so it can be re-checked.

The scenario files say what each step must leave behind (purse, room record, hp, place, text). What they
cannot see is how a step got there: the dice the engine rolled and the turn's own outcome. These tests replay
the scenario files themselves and read exactly that: every step's turn response and every model call's
messages.

What the narrator is told after the room is paid (note item 38, the second half of spec decision (f)) is now
03's own step 4 (``anlaticiya_giden``, known broken [38]); these tests pin why that step breaks.
"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pocket
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, ScriptedClient, ScriptedModel
from api.tests.journeys.schema import load_scenario

ROOM_SLEEP = SCENARIO_DIR / "03_room_sleep.json"
LEAVE_ROOM = SCENARIO_DIR / "07_leave_room.json"
EIGHT_HOURS = 8 * 3600


class RecordingClient(ScriptedClient):
    """The scripted model, keeping every call's kind and messages."""

    def __init__(self, script=None):
        super().__init__(script)
        self.calls: list[tuple[str, list]] = []

    def chat(self, *args, **kwargs):
        answer = super().chat(*args, **kwargs)
        self.calls.append((self.kinds[-1], copy.deepcopy(kwargs.get("messages") or [])))
        return answer

    def narrator_text(self) -> str:
        """Everything the narrator was sent in this step, one message per line."""
        return "\n".join(str(message.get("content", "")) for kind, messages in self.calls
                         if kind == "narration" for message in messages)


class RecordingModel(ScriptedModel):
    """The default driver with a recording client: one client per step that runs, in step order."""

    def __init__(self):
        self.clients: list[RecordingClient] = []

    @contextmanager
    def bind(self, case, step):
        client = RecordingClient(step.script)
        self.clients.append(client)
        with (
            patch("socket.socket.connect",
                  side_effect=AssertionError("External network is disabled in journey tests.")),
            patch.object(case.app.state.ollama_adapter, "_client", client),
        ):
            yield client


def walk_back_to_sleep():
    """07's inn, Fighter and room, at 5 hp: the room is paid, the player walks out to the street and then says
    Kadir's own line from item 38."""
    data = json.loads(LEAVE_ROOM.read_text(encoding="utf-8"))
    data["id"] = "07b_walk_back_to_sleep"
    data["setup"]["current_hp"] = 5
    data["steps"] = [
        {"say": "bi oda tutayım usta", "expect": {"kart": {"max_total_cp": 50}, "kese": 100}},
        {"economic_action": {"kind": "confirm"}, "expect": {"oda": True, "kese": 50, "kart": None}},
        {"say": "dışarı çıkıyorum", "expect": {"konum": "fr:city:neverwinter", "oda": True}},
        {"say": "hana gidip odamda sabaha kadar uyuyorum",
         "expect": {"hp": 28, "oda": True, "kese": 50, "konum": "location_001"}},
    ]
    folder = Path(tempfile.mkdtemp())
    path = folder / "scenario.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        return load_scenario(path)
    finally:
        path.unlink()
        folder.rmdir()


class RoomJourneyEvidence(JourneyCase):
    async def play(self, scenario):
        """Run one scenario; return its step results, each step's turn response and the recording model."""
        scenario = load_scenario(scenario) if isinstance(scenario, Path) else scenario
        model = RecordingModel()
        responses: list[dict] = []
        post = self.http.post

        async def recording_post(url, *args, **kwargs):
            response = await post(url, *args, **kwargs)
            if str(url).endswith("/turn"):
                responses.append(response.json())
            return response

        with patch.object(self.http, "post", recording_post):
            results = await self.run_scenario(scenario, model=model)
        self.assertEqual(len(responses), len(model.clients), "one turn and one client per step that ran")
        return results, responses, model

    def elapsed_seconds(self) -> int:
        world = self.manager.get(self.last_session_id).game_session.world_state
        return world["campaign_time"]["elapsed_seconds"]

    async def test_seed_12_gives_the_bargain_step_a_successful_persuasion_roll(self):
        """03 step 2 needs a successful roll (the plan: "başarılı zarla, seed sabit"). With seed 12 the engine
        rolls Persuasion d20 16, total 17 against DC 15; item 37 is the same 17 against 15."""
        results, responses, _ = await self.play(ROOM_SLEEP)
        self.assertEqual([result.status for result in results],
                         ["pass", "known_broken", "pass", "known_broken", "pass", "pass"], results)
        check = responses[1]["skill_check_result"]
        self.assertEqual(
            {key: check[key] for key in ("skill", "ability", "d20", "total", "dc", "outcome")},
            {"skill": "Persuasion", "ability": "charisma", "d20": 16, "total": 17, "dc": 15,
             "outcome": "success"},
        )
        self.assertEqual(responses[1]["turn_outcome"]["action"], "skill_check")
        # The roll changed nothing: the room card still asks 50 cp (item 37).
        self.assertEqual(results[1].failures, ("gerekli_metin: gerekli metin bulunamadı: indirim",))

    async def test_the_narrator_is_not_told_the_room_is_held(self):
        """03 step 4 (known broken [38], decision (f)): the first narrated turn after the room is paid. The
        narrator is called, but nothing it is sent says the room is held: the confirm turn calls no narrator
        ("50 bakır ödendi."), and the room reaches the narrator only as the player's own unverified words."""
        results, responses, model = await self.play(ROOM_SLEEP)
        self.assertEqual((results[2].status, results[3].status), ("pass", "known_broken"), results)
        self.assertNotIn("narration", model.clients[2].kinds, "the confirm turn calls no narrator")
        told = model.clients[3].narrator_text()
        self.assertTrue(told, "03 step 4 calls the narrator")
        self.assertIn("bi oda tutayım usta", told)
        self.assertEqual(results[3].failures, ("anlaticiya_giden: anlatıcıya giden metinde bulunamadı: oda tutuldu",))
        # The room is held: only the narrator's knowledge of it is missing.
        self.assertTrue(self.last_observations[3]["oda"])
        self.assertEqual(responses[3]["turn_outcome"]["status"], "resolved")

    async def test_the_key_line_and_the_sleep_line_work_on_the_engine_path(self):
        """Item 38 as Kadir met it does not reproduce on the engine path once the room card is confirmed: the
        key line is not answered with the empty-handed pocket line, and the sleep line is a full night's rest."""
        results, responses, model = await self.play(ROOM_SLEEP)
        self.assertEqual([results[2].status, results[4].status, results[5].status], ["pass"] * 3, results)
        self.assertTrue(model.clients[4].narrator_text(), "03 step 5 calls the narrator")
        scenario = load_scenario(ROOM_SLEEP)
        (needle,) = scenario.steps[4].expect["yasak_metin"]
        self.assertIn(needle.casefold(), pocket.EMPTY_HANDED.casefold(),
                      "the scenario's forbidden text is the engine's empty-handed line")
        self.assertNotIn(pocket.EMPTY_HANDED.casefold(), responses[4]["narration"].casefold())
        self.assertEqual(responses[4]["turn_outcome"]["action"], "narrative")
        self.assertEqual((responses[5]["turn_outcome"]["action"], responses[5]["turn_outcome"]["status"]),
                         ("rest", "completed"))
        self.assertEqual(self.elapsed_seconds(), EIGHT_HOURS)

    async def test_kadirs_own_sleep_line_from_the_street_walks_back_and_sleeps(self):
        """Kadir's item-38 line, said on the street after leaving the inn, walks back in and sleeps."""
        # The step's own expectations: hp 28 of 28, back in the inn, the room still held, no second charge.
        results, responses, _ = await self.play(walk_back_to_sleep())
        self.assertEqual([result.status for result in results], ["pass"] * 4, results)
        # One composed turn (walk in, then rest), not a bare rest; the night still passes.
        self.assertEqual(responses[3]["turn_outcome"]["status"], "completed")
        self.assertGreaterEqual(self.elapsed_seconds(), EIGHT_HOURS)


if __name__ == "__main__":
    unittest.main()
