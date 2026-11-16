"""D-109 (Kadir kararı 2026-11-15): the reading says whether the act is done now; only a now act changes the world.

No word list: the reading's own ``timing`` field decides. A crime or a hurt tie is asked first with one short
question; eating and drinking is never asked (a wrong reading there is Undo's to take back).
Real app, real adapter, real engine; only the Ollama client is scripted.
"""

from __future__ import annotations

import copy
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import equipment_economy
import front_proposal
import game
import relationships
import world_happenings
import world_threads
from api.tests.test_front_proposal import FrontTable
from api.tests.test_said_is_real import ClassifiedClient
from api.tests.test_species_traits import make_session
from api.tests.town_seed import fixed_town

_LISTED = {"people": [{"id": "npc-1", "name": "Marek"}], "speaking_with": "npc-1", "places": [], "things": [],
           "offers": [{"id": "thread_001", "person_id": "npc-1", "item": None, "said": ""}],
           "bag": [{"id": "beer1", "name": "Bira"}], "parcels": [], "goods": [], "wants": [],
           "jobs": [{"id": "thread_002", "person_id": "npc-1", "said": ""}]}


class TheReadingCarriesWhen(unittest.TestCase):
    def test_the_schema_asks_when_and_requires_it(self):
        schema = front_proposal.schema(_LISTED)
        self.assertEqual(schema["properties"]["timing"]["enum"], list(front_proposal.TIMINGS))
        self.assertIn("timing", schema["required"])
        self.assertEqual(front_proposal.TIMINGS[0], "now")
        self.assertIn("timing", front_proposal.guidance(_LISTED))

    def test_an_act_not_done_now_changes_nothing_lasting(self):
        reads = {
            "consume": ({"kind": "consume", "item_id": "beer1"}, {"kind": "talk_around"}),
            "hand_over": ({"kind": "hand_over", "person_id": "npc-1", "item_id": "beer1"},
                          {"kind": "speak_to", "id": "npc-1"}),
            "work": ({"kind": "work", "job_id": "thread_002"}, {"kind": "speak_to", "id": "npc-1"}),
            "accept": ({"kind": "offer_answer", "offer_id": "thread_001", "answer": "accept"},
                       {"kind": "speak_to", "id": "npc-1"}),
            "take": ({"kind": "take", "offer_id": "thread_001"}, {"kind": "speak_to", "id": "npc-1"}),
            "take_word": ({"kind": "take", "thing_word": "defter"}, {"kind": "talk_around"}),
            "strike": ({"kind": "speak_to", "strike_to": "npc-1"}, {"kind": "speak_to", "id": "npc-1"}),
        }
        for name, (front, quiet) in reads.items():
            for timing in ("later", "hypothetical", "negated", "observe", "sonra"):
                route = front_proposal.validate({"front": {**front, "timing": timing}}, _LISTED)
                self.assertEqual(route, quiet, (name, timing))
            self.assertNotEqual(front_proposal.validate({"front": {**front, "timing": "now"}}, _LISTED), quiet, name)

    def test_a_threat_a_deed_or_a_roll_not_done_now_is_none(self):
        front = {"kind": "attempt", "threat_to": "npc-1", "deed": "steal", "check": "Intimidation"}
        for timing in ("later", "hypothetical", "negated", "observe"):
            reply = {"front": {**front, "timing": timing}}
            self.assertIsNone(front_proposal.threat_in(reply, _LISTED), timing)
            self.assertEqual(front_proposal.deed_in(reply), "", timing)
            self.assertEqual(front_proposal.check_in(reply, "adama gözdağı veriyorum"), "", timing)
        now = {"front": {**front, "timing": "now"}}
        self.assertEqual(front_proposal.threat_in(now, _LISTED), "npc-1")
        self.assertEqual(front_proposal.deed_in(now), "steal")

    def test_a_reply_with_no_timing_reads_as_now(self):
        """Ruling: the schema requires the field, so only an old record or an old script lacks it; it reads as before."""
        self.assertTrue(front_proposal.acts_now({"front": {"kind": "consume"}}))
        self.assertTrue(front_proposal.acts_now({"front": {"kind": "consume", "timing": None}}))
        self.assertFalse(front_proposal.acts_now({"front": {"kind": "consume", "timing": "maybe"}}))
        self.assertFalse(front_proposal.acts_now(None))


class ABeerIsDrunkOnlyNow(FrontTable):
    async def bar(self):
        with fixed_town(self, 10901):
            await self.begin()
        equipment_economy.grant_named_item(self.world, "Bira")
        self.beer = next(row["id"] for row in front_proposal._bag(self.world) if row["name"] == "Bira")

    def beers(self):
        return sum(1 for item in self.world["inventory"] if isinstance(item, dict) and item.get("name") == "Bira")

    async def test_kadirs_four_lines_leave_the_beer_in_the_bag(self):
        await self.bar()
        for line, timing in (("Biramı içsem mi?", "hypothetical"), ("Biramı yarın içeceğim", "later"),
                             ("Biramı içmiyorum", "negated"), ("Biraya bakıyorum", "observe")):
            self.client.front = {"kind": "consume", "item_id": self.beer, "timing": timing}
            await self.line(line)
            self.assertEqual(self.beers(), 1, (line, self.routes()[-1]))
            self.assertNotEqual(self.routes()[-1]["owner"], "consume", line)

    async def test_drinking_it_now_drinks_it_with_no_question(self):
        await self.bar()
        self.client.front = {"kind": "consume", "item_id": self.beer, "timing": "now"}
        await self.line("Biramı içiyorum")
        self.assertEqual(self.beers(), 0)
        self.assertEqual(self.routes()[-1]["owner"], "consume")
        self.assertIsNone(getattr(self.session, "_heavy_asked", None))

    async def test_a_beer_handed_over_tomorrow_stays_in_the_bag(self):
        await self.bar()
        self.client.front = {"kind": "hand_over", "person_id": self.npc["id"], "item_id": self.beer,
                             "timing": "later"}
        await self.line("Birayı sana yarın veririm")
        self.assertEqual(self.beers(), 1)
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")


class ACrimeOrAThreatIsAskedFirst(FrontTable):
    async def table(self):
        with fixed_town(self, 10911):
            await self.begin()

    def score(self):
        return relationships.score(self.world, self.npc["id"])

    async def test_a_threat_said_now_is_asked_and_moves_nothing_until_yes(self):
        await self.table()
        before = self.score()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "threat_to": self.npc["id"],
                             "timing": "now"}
        reply = await self.line("dukkanini yakarim dikkat et", "Tehdit mi bu?")
        self.assertEqual(self.session._heavy_asked["what"], "threat")
        self.assertEqual(self.routes()[-1]["status"], "clarification")
        self.assertIn("tehdit", reply["narration"])
        self.assertNotIn("Tehdit mi bu?", reply["narration"])  # asked, not yet said to them
        self.assertEqual(self.score(), before)
        await self.line("evet", "Tehdit mi bu?")
        self.assertEqual(self.score(), before - 1)
        self.assertIsNone(self.session._heavy_asked)

    async def test_a_threat_answered_no_moves_nothing(self):
        await self.table()
        before = self.score()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "threat_to": self.npc["id"],
                             "timing": "now"}
        await self.line("dukkanini yakarim dikkat et")
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "timing": "now"}
        await self.line("hayir, vazgectim")
        self.assertEqual(self.score(), before)
        self.assertIsNone(self.session._heavy_asked)

    async def test_a_threat_said_for_later_is_neither_asked_nor_counted(self):
        await self.table()
        before = self.score()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "threat_to": self.npc["id"],
                             "timing": "hypothetical"}
        await self.line("ya dukkanini yaksam ne yaparsin")
        self.assertIsNone(getattr(self.session, "_heavy_asked", None))
        self.assertEqual(self.score(), before)

    async def test_a_theft_is_asked_and_rolls_only_on_yes(self):
        await self.table()
        self.client.front = {"kind": "attempt", "deed": "steal", "timing": "now"}
        reply = await self.line("kalabaligi firsat bilip adamin belindekini usulca kendime katiyorum")
        self.assertEqual(self.session._heavy_asked["deed"], "steal")
        self.assertEqual(self.routes()[-1]["status"], "clarification")
        self.assertIn("suç", reply["narration"])
        self.assertFalse(self.world["flags"].get("deeds"))
        self.assertNotEqual(self.routes()[-1]["owner"], "theft")
        await self.line("evet")
        self.assertEqual(self.routes()[-1]["owner"], "theft")

    async def test_a_fire_answered_no_burns_nothing(self):
        await self.table()
        self.client.front = {"kind": "attempt", "deed": "burn", "timing": "now"}
        await self.line("su dukkani bastan asagi tutusturuyorum")
        self.assertEqual(self.session._heavy_asked["deed"], "burn")
        self.client.front = {"kind": "unclear", "timing": "now"}
        await self.line("hayir")
        self.assertFalse(self.world["flags"].get("fires"))
        self.assertNotEqual(self.routes()[-1]["owner"], "arson")

    async def test_undo_of_the_asking_turn_forgets_the_question(self):
        await self.table()
        self.client.front = {"kind": "attempt", "deed": "burn", "timing": "now"}
        action_id = str(uuid.uuid4())
        response = await self.http.post(self.turn_url, json={"message": "su dukkani bastan asagi tutusturuyorum",
                                                             "action_id": action_id})
        self.assertEqual(response.status_code, 200, response.text)
        live = self.manager.get(self.session_id).game_session
        self.assertEqual(live._heavy_asked["deed"], "burn")
        undone = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": action_id})
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertIsNone(self.manager.get(self.session_id).game_session._heavy_asked)

    async def test_a_threat_and_a_theft_in_one_line_are_each_asked_once_and_done_once(self):
        """Review: two asks on one line used to loop threat/deed forever; each yes now holds, and the tie moves once."""
        await self.table()
        before = self.score()
        self.client.front = {"kind": "attempt", "threat_to": self.npc["id"], "deed": "steal", "timing": "now"}
        line = "sesini cikarirsan gebertirim deyip adamin belindekini usulca kendime katiyorum"
        await self.line(line)
        self.assertEqual(self.session._heavy_asked["what"], "threat")
        self.assertEqual(self.score(), before)
        await self.line("evet")
        self.assertEqual(self.session._heavy_asked["what"], "deed")
        self.assertEqual(self.score(), before - 1)
        self.assertFalse(self.world["flags"].get("deeds"))
        await self.line("evet")
        self.assertIsNone(self.session._heavy_asked)
        self.assertEqual(self.routes()[-1]["owner"], "theft")
        threats = [reason for reason in self.world["relationships"][self.npc["id"]]["events"]
                   if reason.startswith("threat:")]
        self.assertEqual(len(threats), 1, threats)  # the threat was not said a second time (the theft has its own cost)

    async def test_a_theft_with_no_reading_is_still_asked_first(self):
        """Review: a dead model (or the reading switched off) used to let the old words steal with no question."""
        await self.table()
        self.client.fails = ConnectionError("gone")
        line = "kesesini fark ettirmeden calmak icin zar atiyorum"
        await self.line(line)
        self.assertEqual(self.session._heavy_asked["deed"], "steal")
        self.assertEqual(self.routes()[-1]["route"], "fallback:failed")
        self.assertFalse(self.world["flags"].get("deeds"))
        self.assertNotIn("theft", [row.get("owner") for row in self.routes()])
        await self.line("evet")
        self.assertIsNone(self.session._heavy_asked)
        self.assertEqual(self.routes()[-1]["owner"], "theft")

    async def test_a_fire_with_the_reading_switched_off_is_still_asked_first(self):
        await self.table()
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "0"}):
            await self.line("su dukkani bastan asagi tutusturuyorum")
            self.assertEqual(self.session._heavy_asked["deed"], "burn")
            self.assertFalse(self.world["flags"].get("fires"))
            await self.line("hayir")
            self.assertFalse(self.world["flags"].get("fires"))
            self.assertIsNone(self.session._heavy_asked)

    async def test_a_yes_undone_or_spent_never_lets_the_same_line_through_unasked(self):
        """Review: the yes outlived Undo, so the same threat written again was done with no question."""
        await self.table()
        before = self.score()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "threat_to": self.npc["id"],
                             "timing": "now"}
        line = "dukkanini yakarim dikkat et"

        async def turn(message):
            action_id = str(uuid.uuid4())
            response = await self.http.post(self.turn_url, json={"message": message, "action_id": action_id})
            self.assertEqual(response.status_code, 200, response.text)
            return action_id, self.manager.get(self.session_id).game_session

        _, live = await turn(line)
        self.assertEqual(live._heavy_asked["what"], "threat")
        yes_id, live = await turn("evet")
        self.assertEqual(self.score(), before - 1)
        undone = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": yes_id})
        self.assertEqual(undone.status_code, 200, undone.text)
        live = self.manager.get(self.session_id).game_session
        self.assertIsNone(getattr(live, "_heavy_confirmed", None))
        self.assertEqual(self.score(), before)
        _, live = await turn(line)  # written again after Undo: asked again, nothing moves
        self.assertEqual(live._heavy_asked["what"], "threat")
        self.assertEqual(self.score(), before)
        _, live = await turn("evet")
        self.assertEqual(self.score(), before - 1)
        _, live = await turn(line)  # and once more with no Undo: a new threat is a new question
        self.assertEqual(live._heavy_asked["what"], "threat")
        self.assertEqual(self.score(), before - 1)

    def _world_changes(self, before):
        """The world's top-level keys that differ from ``before``. Left out: the opening's one-time nudge (set on any first
        line) and the one-turn entry pointer every turn's end writes afresh (a fight question's turn too)."""
        after = copy.deepcopy(self.world)
        for world in (before, after):
            world.get("flags", {}).pop("opening_nudge", None)
            world.get("scene_state", {}).pop("entry_target_reference", None)
        return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))

    async def _the_asking_turn_changes_nothing(self, kind):
        await self.table()
        before = copy.deepcopy(self.world)
        self.client.front = {"kind": kind, "person_id": self.npc["id"], "threat_to": self.npc["id"], "timing": "now"}
        await self.line("hana gidip hanciyi tehdit ediyorum, dukkanini yakarim")
        self.assertEqual(self.session._heavy_asked["what"], "threat")
        self.assertEqual(self._world_changes(before), [])
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "timing": "now"}
        await self.line("hayir")
        self.assertEqual(len(self.world["npcs"]), len(before["npcs"]))
        self.assertEqual(self.world.get("next_npc_number"), before.get("next_npc_number"))

    async def test_the_asking_turn_of_a_threat_said_to_a_face_leaves_the_world_as_it_was(self):
        """Re-review: the scene planner still ran on the asked line (a new person, a new spot) and a no kept them."""
        await self._the_asking_turn_changes_nothing("speak_to")

    async def test_the_asking_turn_of_a_threat_on_the_way_leaves_the_world_as_it_was(self):
        await self._the_asking_turn_changes_nothing("go_to")

    async def _the_reply_may_say_warned(self):
        await self.table()
        self.client = ClassifiedClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.client.speech_extra = {"threat": world_happenings.PLAYER_THREATENED}

    def guarded(self):
        state = world_threads.view(self.world) or {"history": []}
        return [row for row in world_happenings.links(state) if row.get("kind") == world_happenings.GUARDED]

    async def test_a_reply_saying_warned_hurts_no_tie_the_player_did_not_threaten_now_and_confirm(self):
        """Re-review: the reply's own threat="warned" cut the tie with no question; only an asked yes may (D-109)."""
        await self._the_reply_may_say_warned()
        before = self.score()
        speak = {"kind": "speak_to", "person_id": self.npc["id"]}
        cases = (({**speak, "timing": "now"}, "merhaba usta, nasilsin", {}),
                 ({**speak, "threat_to": self.npc["id"], "timing": "hypothetical"}, "seni tehdit etsem mi acaba?", {}),
                 # no reading at all: a line typed as speech skips it (a gone model gives a stock line, no reply to settle)
                 ({**speak, "threat_to": self.npc["id"], "timing": "now"}, "kapina dayanirim haberin olsun",
                  {"mode": "say", "target": True}))
        for front, line, how in cases:
            self.client.front = front
            reply = await self.line(line, "Beni tehdit mi ediyorsun?", **how)
            self.assertIn("Beni tehdit mi ediyorsun?", reply["narration"], line)  # the reply was spoken and settled
            self.assertIsNone(getattr(self.session, "_heavy_asked", None), line)
            self.assertEqual(self.score(), before, line)
            self.assertEqual(self.guarded(), [], line)

    async def test_a_reply_saying_warned_after_the_asked_yes_cuts_the_tie_once(self):
        await self._the_reply_may_say_warned()
        before = self.score()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "threat_to": self.npc["id"],
                             "timing": "now"}
        await self.line("dukkanini yakarim dikkat et", "Beni tehdit mi ediyorsun?")
        self.assertEqual(self.session._heavy_asked["what"], "threat")
        self.assertEqual(self.score(), before)
        self.assertEqual(self.guarded(), [])
        await self.line("evet", "Beni tehdit mi ediyorsun?")
        self.assertEqual(self.score(), before - 1)
        self.assertEqual(len(self.guarded()), 1)

    def test_a_given_yes_rides_the_rollback_snapshot_as_it_was(self):
        """A rolled-back turn puts the yes back as it stood before the turn (Undo then forgets it, see above)."""
        session = game.GameSession()
        given = {"said": "yakiyorum", "allowed": [["deed", None, "burn"]]}
        session._heavy_confirmed = copy.deepcopy(given)
        snapshot = session._capture_runtime_snapshot()
        session._heavy_confirmed = None
        session._restore_runtime_snapshot(snapshot)
        self.assertEqual(session._heavy_confirmed, given)

    def test_a_load_forgets_the_question_and_the_yes(self):
        session = make_session("Human")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "before-question.json"
            session.save_game(path)
            session._heavy_asked = {"what": "deed", "deed": "burn", "id": None, "said": "yakiyorum"}
            session._heavy_confirmed = {"said": "yakiyorum", "allowed": [["deed", None, "burn"]]}
            session.load_game(path)
        self.assertIsNone(session._heavy_asked)
        self.assertIsNone(session._heavy_confirmed)

    def test_the_open_question_rides_the_rollback_snapshot(self):
        session = game.GameSession()
        session._heavy_asked = {"what": "deed", "deed": "burn", "id": None, "said": "yakiyorum"}
        snapshot = session._capture_runtime_snapshot()
        session._heavy_asked = None
        session._restore_runtime_snapshot(snapshot)
        self.assertEqual(session._heavy_asked["deed"], "burn")


if __name__ == "__main__":
    unittest.main()
