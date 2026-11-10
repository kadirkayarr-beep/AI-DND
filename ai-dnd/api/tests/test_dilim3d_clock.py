"""Dilim 3D Task 1 (#3, #167, #166): one length said twice in a line moves the clock once, through the API.

A line that names two different lengths of one unit moves nothing and asks; Undo and a replayed action id stay whole.
"""
import collections
import copy
import os
import unittest
import uuid
from unittest.mock import patch

import campaign_time
import front_proposal
import timed_gameplay
from api.tests import test_campaign_api as fixtures
from api.tests.journeys.runner import ScriptedClient
from api.tests.test_campaign_time import Q027, Q028, Q084, Q104, Q105, Q167
from api.tests.town_seed import fixed_town

START = {"setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
         "region_id": "fr:region:the_north", "starting_location_id": "fr:city:neverwinter"}


class DurationSaidTwiceTurn(unittest.IsolatedAsyncioTestCase):
    asyncSetUp_base = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    post_scene_turn = fixtures.CampaignApiTests.post_scene_turn

    async def asyncSetUp(self):
        await self.asyncSetUp_base()
        self.client = ScriptedClient({})
        with fixed_town(self, 4501):
            created = await self.http.post("/api/game/campaigns", json={"campaign_start": START})
        self.assertEqual(created.status_code, 200, created.text)
        self.session_id = created.json()["session_id"]

    def session(self):
        return self.manager.get(self.session_id).game_session

    def elapsed(self):
        return self.session().world_state["campaign_time"]["elapsed_seconds"]

    def snapshot(self):
        session = self.session()
        return copy.deepcopy({"world_state": session.world_state, "messages": session.messages})

    async def turn(self, line, *, front=None, action_id=None):
        """One API turn; front given = the front reading is on and answers it."""
        self.client.script = {"front": front} if front is not None else {}
        self._last_action_id = action_id or str(uuid.uuid4())
        with patch.dict(os.environ, {front_proposal.FLAG: "1" if front is not None else "0"}):
            return await self.post_scene_turn(f"/api/game/sessions/{self.session_id}/turn", self.client,
                                              {"message": line, "action_id": self._last_action_id})

    async def undo(self):
        reply = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                     json={"action_id": str(uuid.uuid4()), "target_action_id": self._last_action_id})
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply

    async def test_167_turn_moves_the_clock_sixteen_hours(self):
        before = self.elapsed()
        reply = await self.turn(Q167)
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(self.elapsed() - before, 16 * 3600)
        self.assertNotIn("32 saat", reply.json()["narration"])

    async def test_167_read_as_a_wait_by_the_front_moves_sixteen_hours(self):
        before = self.elapsed()
        reply = await self.turn(Q167, front={"kind": "wait"})
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(self.elapsed() - before, 16 * 3600)
        self.assertNotIn("32 saat", reply.json()["narration"])

    async def test_replayed_action_id_moves_the_clock_once(self):
        before = self.elapsed()
        action_id = str(uuid.uuid4())
        first = await self.turn(Q167, action_id=action_id)
        again = await self.turn(Q167, action_id=action_id)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["narration"], first.json()["narration"])
        self.assertEqual(self.elapsed() - before, 16 * 3600)

    async def test_undo_takes_the_sixteen_hours_back(self):
        before = self.snapshot()  # world_state, messages
        reply = await self.turn(Q167)
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertNotEqual(self.snapshot(), before)
        await self.undo()
        self.assertEqual(self.snapshot(), before)

    def assert_asked_and_wrote_nothing(self, before, reply):
        """The clarification is said; the clock, messages and world stay (only the turn's own flags bookkeeping moves)."""
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertIn(campaign_time.DURATION_CONFLICT, reply.json()["narration"])
        after = self.snapshot()
        self.assertEqual(after["world_state"]["campaign_time"], before["world_state"]["campaign_time"])
        self.assertEqual(after["messages"], before["messages"])
        unflagged = lambda world: {key: value for key, value in world.items() if key != "flags"}
        self.assertEqual(unflagged(after["world_state"]), unflagged(before["world_state"]))

    async def test_a_conflict_moves_nothing_and_asks(self):
        before = self.snapshot()
        self.assert_asked_and_wrote_nothing(before, await self.turn("2 saat bekliyorum, yok 3 saat"))

    async def test_a_conflict_read_as_a_wait_by_the_front_moves_nothing_and_asks(self):
        before = self.snapshot()
        self.assert_asked_and_wrote_nothing(before, await self.turn("2 saat bekliyorum, yok 3 saat", front={"kind": "wait"}))

    async def test_a_conflict_read_as_an_attempt_by_the_front_moves_nothing_and_asks(self):
        # no wait word: only names_a_stretch turns the front's 'attempt' into the wait owner, which asks
        before = self.snapshot()
        self.assert_asked_and_wrote_nothing(
            before, await self.turn("kapıyı 2 saat zorluyorum, yok 3 saat", front={"kind": "attempt"}))

    async def test_undo_after_a_conflict_gives_back_the_same_state(self):
        before = self.snapshot()
        reply = await self.turn("2 saat bekliyorum, yok 3 saat")
        self.assertEqual(reply.status_code, 200, reply.text)
        await self.undo()
        self.assertEqual(self.snapshot(), before)

    async def test_replayed_conflict_answers_the_same_and_writes_nothing(self):
        action_id = str(uuid.uuid4())
        first = await self.turn("2 saat bekliyorum, yok 3 saat", action_id=action_id)
        self.assertEqual(first.status_code, 200, first.text)
        after_first = self.snapshot()
        again = await self.turn("2 saat bekliyorum, yok 3 saat", action_id=action_id)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json(), first.json())
        self.assertEqual(self.snapshot(), after_first)

    async def test_two_steps_of_one_length_ask(self):
        # 'sonra ... daha': the same length again is more time, not a restatement; it is asked, never silently halved
        before = self.snapshot()
        self.assert_asked_and_wrote_nothing(before, await self.turn("2 saat bekliyorum, sonra 2 saat daha uyuyorum"))

    async def test_166_a_second_long_rest_too_soon_says_so(self):
        first = await self.turn("8 saat uyuyorum. Uzun dinlenme yapıyorum.")  # QA #028, verbatim
        self.assertEqual(first.status_code, 200, first.text)
        reply = await self.turn("sekiz saat uyuyarak uzun dinlenme yapıyorum.")  # QA #166's sleep clause
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertIn("Daha yeni dinlenmiştin", reply.json()["narration"])
        self.assertNotEqual(reply.json()["narration"].strip(), "8 saat geçiyor.")


class TimedOwnersAsk(unittest.TestCase):
    """Both timed owners turn two lengths of one unit into the same clarification and move nothing."""

    def setUp(self):
        from api.tests import test_death_system as death_fixtures
        self.session = death_fixtures.make_session()
        campaign_time.initialize(self.session.world_state)
        self.before = copy.deepcopy(self.session.world_state)

    def assert_asks(self, result):
        self.assertEqual(result["direct_response"], campaign_time.DURATION_CONFLICT)
        self.assertEqual(result["status"], "clarification")
        self.assertFalse(result["success"])
        self.assertEqual(self.session.world_state, self.before)

    def test_pass_time_asks(self):
        import timed_gameplay
        self.assert_asks(timed_gameplay.pass_time(self.session, "2 saat bekliyorum, yok 3 saat"))

    def test_resolve_input_asks(self):
        import timed_gameplay
        self.assert_asks(timed_gameplay.resolve_input(self.session, "2 saat bekliyorum, yok 3 saat"))

    def test_names_a_stretch_takes_a_conflict(self):
        import timed_gameplay
        self.assertTrue(timed_gameplay.names_a_stretch(self.session.world_state, "kapıyı 2 saat zorluyorum, yok 3 saat"))
        self.assertEqual(self.session.world_state, self.before)

    def test_primal_knowledge_refuses_a_conflict_line_as_timed(self):
        import combat_lifecycle
        with self.assertRaises(combat_lifecycle.CombatRequestError) as caught:
            self.session.primal_knowledge_check_admission("2 saat bekliyorum, yok 3 saat")
        self.assertEqual(caught.exception.code, "primal_knowledge_immediate_check_only")
        self.assertEqual(self.session.world_state, self.before)

    def test_resolve_input_asks_before_a_rest(self):
        import timed_gameplay
        self.assert_asks(timed_gameplay.resolve_input(self.session, "8 saat uyuyorum, yok 9 saat"))


class DurationConflictWhileDown(unittest.TestCase):
    """game._down_outside_combat_turn reads the line's length: two lengths read as none, the body sleeps till it wakes."""

    def test_a_stable_body_with_two_lengths_sleeps_until_it_wakes(self):
        from api.tests import test_death_system as death_fixtures
        session = death_fixtures.make_session()
        campaign_time.initialize(session.world_state)
        session._apply_player_damage(session.character["current_hp"], took_damage=True)
        with patch.object(session.rng, "randint", return_value=1):
            session.stabilize_player()
        recovery_at = session.ensure_death_state()["recovery"]["at"]
        session.run_player_turn("2 saat bekliyorum, yok 3 saat")
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], recovery_at)
        self.assertEqual(session.character["current_hp"], 1)


Outcome = collections.namedtuple("Outcome", "delta action status long_rest_at narration")


class EnglishClockParity(unittest.IsolatedAsyncioTestCase):
    """Dilim 3D Task 2 (#027, #084, #104): an English line moves the clock and rests exactly as its Turkish twin.

    Each line is played in a campaign of its own, in a store of its own, on the same pinned town (seed 4511), so two
    outcomes can only differ by how the line itself was read."""
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    post_scene_turn = fixtures.CampaignApiTests.post_scene_turn
    maxDiff = None

    PAIRS = ((Q027, Q028), (Q104, Q105), (Q084, "Bir saat dinleniyorum."),
             ("I wait two hours without sleeping", "uyumadan iki saat bekliyorum"),
             ("I sleep for 2 hours", "2 saat uyuyorum"),
             ("I wait sixteen hours", "on altı saat bekliyorum"))

    async def outcome(self, line, *, front=None):
        """A fresh campaign on the pinned town plays one turn: (clock delta, action, status, long rest, narration)."""
        await self.asyncTearDown()
        await fixtures.CampaignApiTests.asyncSetUp(self)
        self._town_creations = 0  # a new store each time: the same town may be founded again
        with fixed_town(self, 4511):
            created = await self.http.post("/api/game/campaigns", json={"campaign_start": START})
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["session_id"]
        world = self.manager.get(session_id).game_session.world_state
        before = world["campaign_time"]["elapsed_seconds"]
        client = ScriptedClient({"front": front} if front is not None else {})
        with patch.dict(os.environ, {front_proposal.FLAG: "1" if front is not None else "0"}):
            reply = await self.post_scene_turn(f"/api/game/sessions/{session_id}/turn", client,
                                               {"message": line, "action_id": str(uuid.uuid4())})
        self.assertEqual(reply.status_code, 200, reply.text)
        world = self.manager.get(session_id).game_session.world_state
        body = reply.json()
        return Outcome(world["campaign_time"]["elapsed_seconds"] - before, (body.get("turn_outcome") or {}).get("action"),
                       (body.get("turn_outcome") or {}).get("status"), world.get("last_long_rest_completed_at"),
                       body["narration"])

    async def test_english_line_gives_the_turkish_lines_clock_and_rest(self):
        for english, turkish in self.PAIRS:
            for front in (None, {"kind": "wait"}):
                if (english, front) == (Q104, None):
                    continue  # Park P3: with no reading, Q105 itself moves nothing ("yapmıyorum" read as a no)
                with self.subTest(english=english, front=front):
                    en = await self.outcome(english, front=front)
                    tr = await self.outcome(turkish, front=front)
                    self.assertEqual(tuple(en), tuple(tr))  # a plain tuple: the full diff is shown
                    self.assertNotIn("Yarım saat geçiyor", en.narration)

    async def test_104_with_no_reading_waits_the_hour(self):
        # The one pair left out above: the English line is held to the right hour, not to its twin's park P3 defect.
        outcome = await self.outcome(Q104)
        self.assertEqual((outcome.delta, outcome.action, outcome.status, outcome.long_rest_at),
                         (3600, "wait", "completed", None))
        self.assertTrue(outcome.narration.startswith("1 saat geçiyor."), outcome.narration)

    async def test_027_takes_the_long_rest(self):
        outcome = await self.outcome(Q027)
        self.assertEqual((outcome.delta, outcome.action), (8 * 3600, "rest"))
        self.assertIsNotNone(outcome.long_rest_at)

    async def test_084_takes_a_short_rest(self):
        outcome = await self.outcome(Q084)
        self.assertEqual((outcome.delta, outcome.action, outcome.long_rest_at), (3600, "rest", None))
        self.assertIn("Kısa dinlenme tamamlandı", outcome.narration)

    async def test_english_rest_only_no(self):
        for front in (None, {"kind": "wait"}):
            with self.subTest(front=front):
                outcome = await self.outcome("I wait two hours without sleeping", front=front)
                self.assertEqual((outcome.delta, outcome.action, outcome.long_rest_at), (7200, "wait", None))

    async def test_english_rest_said_no_waits_only(self):
        for line in ("I don't want to rest, I wait two hours", "I wait two hours, but I do not rest"):
            with self.subTest(line=line):
                outcome = await self.outcome(line)
                self.assertEqual((outcome.delta, outcome.action, outcome.long_rest_at), (7200, "wait", None))
                self.assertNotIn("dinlenme", outcome.narration)

    # Fix round 1 (review Critical 1, Important 2): a sleeping someone else, or a sleep said no to a few words away,
    # is no sleep of the player's; the Turkish twins go to the model and move no time.
    NOT_THE_PLAYERS_SLEEP = (
        ("I sneak past the sleeping guard", "uyuyan muhafızın yanından sinsice geçiyorum"),
        ("The guard sleeps at his post", "muhafız nöbet yerinde uyuyor"),
        ("I look at a sleeping dragon", "uyuyan bir ejderhaya bakıyorum"),
        ("I don't want to sleep yet, I look around", "henüz uyumak istemiyorum, etrafıma bakıyorum"),
        ("I'm not going to sleep, I keep watch all night", "uyumuyorum, bütün gece nöbet tutuyorum"))

    async def test_someone_elses_sleep_or_a_sleep_said_no_moves_no_time(self):
        for english, turkish in self.NOT_THE_PLAYERS_SLEEP:
            for front in (None, {"kind": "attempt"}):
                with self.subTest(english=english, front=front):
                    en = await self.outcome(english, front=front)
                    tr = await self.outcome(turkish, front=front)
                    self.assertEqual((en.delta, en.long_rest_at), (0, None))
                    self.assertEqual((tr.delta, tr.long_rest_at), (0, None))
                    self.assertNotIn(en.action, {"wait", "rest"})  # no timed owner took it: it is the model's line
                    self.assertNotIn(timed_gameplay._ASK_HOW_LONG, en.narration)
                    if ", " not in turkish:
                        # A Turkish comma line goes to the Turkish-only clause recorder ("interaction"/"recorded"),
                        # which English lines never reach (D-1 b); the clock and the rest above stay equal.
                        self.assertEqual((en.action, en.status), (tr.action, tr.status))

    # Fix round 2 (re-review recall regression): "I <do something> and sleep" and "I would like / decide to sleep"
    # are the player's own sleep, as "uzanıp uyuyorum" is (the QA #027 shape).
    THE_PLAYERS_SLEEP = (
        ("I lie down and sleep", "uzanıp uyuyorum"),
        ("I make camp and sleep", "kamp kurup uyuyorum"),
        ("I curl up and sleep", "kıvrılıp uyuyorum"),
        ("We camp and sleep through the night", "kamp kurup gece boyunca uyuyorum"),
        ("I settle in and sleep until dawn", "yerleşip uyuyorum"),  # English named hours are out of scope (D-1 b)
        ("I would like to sleep", "uyuyacağım"),
        ("I decide to sleep", "uyuyayım"),
        ("I lie down and sleep for eight hours", "uzanıp sekiz saat uyuyorum"),
        ("I make camp and sleep for eight hours", "kamp kurup sekiz saat uyuyorum"),
        ("I would like to sleep for eight hours", "sekiz saat uyuyacağım"))

    async def test_the_players_sleep_after_another_act_is_a_sleep(self):
        for english, turkish in self.THE_PLAYERS_SLEEP:
            for front in (None, {"kind": "wait"}):
                with self.subTest(english=english, front=front):
                    en = await self.outcome(english, front=front)
                    tr = await self.outcome(turkish, front=front)
                    self.assertEqual((en.delta, en.action, en.long_rest_at), (8 * 3600, "rest", 8 * 3600))
                    self.assertEqual(tuple(en), tuple(tr))


class EnglishTimedOwners(unittest.TestCase):
    """The timed owners read English sleep, wait, rest and their no as they read the Turkish words."""

    def setUp(self):
        from api.tests import test_death_system as death_fixtures
        self.session = death_fixtures.make_session()
        campaign_time.initialize(self.session.world_state)
        self.before = copy.deepcopy(self.session.world_state)

    def test_markers(self):
        import timed_gameplay
        for line in ("i sleep", "i am sleeping", "i go to sleep"):
            with self.subTest(line=line):
                self.assertTrue(timed_gameplay._SLEEPING.search(campaign_time.normalize(line)))
        for line in ("i wait without sleeping", "i do not sleep", "i don't sleep", "i never sleep", "uyumadan bekliyorum"):
            with self.subTest(line=line):
                self.assertFalse(timed_gameplay._SLEEPING.search(campaign_time.normalize(line)))
        for line in ("i wait", "i am waiting", "i rest", "i take a long rest", "i rest on the bench"):
            with self.subTest(line=line):
                self.assertTrue(timed_gameplay.input_route_markers(self.session.world_state, campaign_time.normalize(line))[1])

    def test_only_the_players_own_sleep_is_a_sleep(self):
        # Fix round 1 (review Critical 1, Important 2): first person and intent, as the Turkish "uyuyorum" forms
        import timed_gameplay
        for line in ("I sleep", "I'm going to sleep", "I want to sleep", "Let me sleep", "I'll sleep", "We sleep here",
                     "I go to bed", "I'm going to bed", "I lie down to sleep", "I am sleeping", "Let's sleep"):
            with self.subTest(line=line):
                self.assertTrue(timed_gameplay._SLEEPING.search(campaign_time.normalize(line)))
        for line in ("I sneak past the sleeping guard", "the guard sleeps", "a sleeping dragon", "I watch him sleep",
                     "I search the sleeping man's pockets", "two hours ago I was sleeping", "I can't sleep",
                     "I don't want to sleep yet, I look around", "I'm not going to sleep, I keep watch all night",
                     "I won't sleep", "I sit on the bed", "uyuyan muhafız",
                     # fix round 2: the "... and sleep" form keeps someone else's sleep and a no out
                     "I tell the guard to go and sleep", "I watch him eat and sleep", "I don't eat and sleep",
                     "I never camp and sleep here", "the guard eats and sleeps", "they camp and sleep",
                     "I search the room and the sleeping man"):
            with self.subTest(line=line):
                self.assertFalse(timed_gameplay._SLEEPING.search(campaign_time.normalize(line)))

    def test_the_players_sleep_after_another_act_reads_as_sleep(self):
        # Fix round 2 (re-review): a short first-person clause, then "and"/"then", then sleep; and more intents
        import timed_gameplay
        for line in ("I lie down and sleep", "I make camp and sleep", "I curl up and sleep",
                     "We camp and sleep through the night", "I settle in and sleep until dawn", "I would like to sleep",
                     "I'd like to sleep", "I decide to sleep", "I decided to sleep", "I plan to sleep", "I need to sleep",
                     "I have to sleep", "I'm ready to sleep", "I eat, then sleep", "I eat and then sleep",
                     "I lie down and go to sleep"):
            with self.subTest(line=line):
                self.assertTrue(timed_gameplay._SLEEPING.search(campaign_time.normalize(line)))

    def test_a_sleep_said_no_a_few_words_away_is_left_to_the_model(self):
        import timed_gameplay
        for line in ("I don't want to sleep yet, I look around", "I'm not going to sleep, I keep watch all night",
                     "I have no intention to rest, I look around", "I won't wait, I look around"):
            with self.subTest(line=line):
                self.assertIsNone(timed_gameplay.resolve_input(self.session, line))
                self.assertEqual(self.session.world_state, self.before)

    def test_a_noun_rest_under_a_wait_reading_is_a_while_not_a_rest(self):
        # Fix round 1 (review Minor 3): "the rest" and "rest my hand" are no rest; a real short rest asks as Turkish does
        import timed_gameplay
        def fresh():
            from api.tests import test_death_system as death_fixtures
            session = death_fixtures.make_session()
            campaign_time.initialize(session.world_state)
            return session
        for line in ("I give him the rest", "I leave the rest to you", "I rest my hand on the hilt"):
            with self.subTest(line=line):
                result = timed_gameplay.pass_time(fresh(), line)
                self.assertEqual((result["action"], result["time_result"]["elapsed_seconds"]), ("wait", 1800))
        english = timed_gameplay.pass_time(fresh(), "I take a short rest")
        turkish = timed_gameplay.pass_time(fresh(), "biraz dinleniyorum")
        self.assertEqual((english["action"], english["status"], english["direct_response"]),
                         (turkish["action"], turkish["status"], turkish["direct_response"]))

    def test_a_no_to_waiting_is_a_no_to_the_line(self):
        import timed_gameplay
        for line in ("I don't wait two hours", "I will not wait an hour"):
            with self.subTest(line=line):
                self.assertTrue(timed_gameplay.says_no(line))
                self.assertIsNone(timed_gameplay.resolve_input(self.session, line))
                self.assertEqual(self.session.world_state, self.before)

    def test_a_no_to_the_rest_is_no_no_to_the_line(self):
        import timed_gameplay
        for line in ("I wait two hours without sleeping", "I wait two hours without resting",
                     "I don't want to rest, I wait two hours"):
            with self.subTest(line=line):
                self.assertFalse(timed_gameplay.says_no(line))

    def test_the_rest_of_the_night_is_no_rest(self):
        import timed_gameplay
        result = timed_gameplay.resolve_input(self.session, "I wait two hours for the rest of the guards")
        self.assertEqual((result["action"], result["time_result"]["elapsed_seconds"]), ("wait", 7200))

    def test_a_short_english_sleep_is_a_sleep(self):
        import timed_gameplay
        english = timed_gameplay.resolve_input(self.session, "I sleep for 2 hours")
        self.assertEqual((english["action"], english["time_result"]["reason"],
                          english["time_result"]["elapsed_seconds"]), ("wait", "sleep", 7200))


if __name__ == "__main__":
    unittest.main()
