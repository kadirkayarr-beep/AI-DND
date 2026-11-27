"""D-240: when the front reading comes back unusable, a plain yes to an open offer and a plain walk out of town
still work through the engine's own word readers, and the log says which check failed (names only)."""

from __future__ import annotations

import json
import unittest
import uuid
from unittest.mock import patch

import front_proposal
import grounded_action
import local_places
import money_owner
import world_threads
from api.tests import test_front_proposal as front_tests
from api.tests.town_seed import fixed_town

TOWN_SEED = 2701


class OptionsClient(front_tests.FrontClient):
    def __init__(self):
        super().__init__()
        self.options = []

    def chat(self, *args, **kwargs):
        if "front" in ((kwargs.get("format") or {}).get("properties") or {}):
            self.options.append(kwargs.get("options") or {})
        return super().chat(*args, **kwargs)


class CutClient(front_tests.FrontClient):
    """The front reading arrives, but not as a usable answer."""

    def __init__(self, how):
        super().__init__()
        self.how = how

    def chat(self, *args, **kwargs):
        schema = kwargs.get("format") or {}
        if "front" not in (schema.get("properties") or {}):
            return super().chat(*args, **kwargs)
        self.chat_calls += 1
        self.schemas.append(schema)
        self.message_batches.append(kwargs.get("messages", []))
        if self.how == "cut":
            return {"message": {"content": '{"intent": "narrative", "front": {"kind": "spe'}, "done_reason": "length"}
        if self.how == "not_json":
            return {"message": {"content": "tamam, anladım"}, "done_reason": "stop"}
        raise AssertionError(self.how)


class FailedReading(unittest.IsolatedAsyncioTestCase):
    # The parent table's helpers only: its own tests are not run again here.
    asyncSetUp = front_tests.FrontTable.asyncSetUp
    asyncTearDown = front_tests.FrontTable.asyncTearDown
    campaign_with_npc = front_tests.FrontTable.campaign_with_npc
    open_job = front_tests.FrontTable.open_job
    line = front_tests.FrontTable.line
    status = front_tests.FrontTable.status
    offer = front_tests.FrontTable.offer
    routes = front_tests.FrontTable.routes

    def lose_the_reading(self):
        """The reading comes back but is no JSON: the old chain answers (G6); a lost provider would refuse the line."""
        self.client = CutClient("not_json")
        self.enterContext(front_tests.patch.object(self.app.state.ollama_adapter, "_client", self.client))

    async def begin(self, *, seed=TOWN_SEED, **kwargs):
        # A new campaign's town comes from its id: each campaign of a test takes the next seed from ``seed``.
        with fixed_town(self, seed):
            await front_tests.FrontTable.begin(self, **kwargs)

    def usage(self):
        path = self.route_file.with_name(f"{self.route_file.stem}.usage{self.route_file.suffix}")
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    async def test_a_dead_provider_asks_to_try_again_and_takes_the_yes_on_the_retry(self):
        # Owner rule G6 ("Tekrar dene", 2026-11-19): a lost provider refuses the line and the offer stays open.
        await self.begin()
        self.offer()
        self.client.fails = ConnectionError("gone")
        failed = await self.http.post(self.turn_url, json={"message": "tamam, yaparım", "action_id": str(uuid.uuid4())})
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertIs(failed.json()["detail"]["not_applied"], True)
        self.assertEqual(self.status(), "offered")
        self.client.fails = None  # the provider is back: the same line, on a new id, is read and taken once
        self.client.front = {"kind": "offer_answer", "offer_id": self.thread["thread_id"], "answer": "accept"}
        await self.line("tamam, yaparım")
        self.assertEqual(self.status(), "accepted")
        self.assertEqual(self.routes()[-1]["route"], "front:offer_answer")

    async def test_a_cut_reading_still_takes_a_plain_yes_to_an_open_offer(self):
        await self.begin()
        self.offer()
        self.enterContext(front_tests.patch.object(self.app.state.ollama_adapter, "_client", CutClient("cut")))
        await self.line("kabul ediyorum")
        self.assertEqual(self.status(), "accepted")
        self.assertEqual(self.routes()[-1]["route"], "fallback:unusable:offer_answer")

    async def test_a_long_accepting_line_is_still_a_yes_when_the_reading_failed(self):
        for line in ("Zivanel'e iade eşyasını teslim etme görevini kabul ediyorum ve teslim edilecek eşyayı alıyorum.",
                     "Teklifini kabul ediyorum, işe başlıyorum.", "Tamam, kabul. Ne zaman başlıyoruz?"):
            with self.subTest(line=line):
                await self.begin()
                self.offer()
                self.lose_the_reading()
                await self.line(line)
                self.assertEqual(self.status(), "accepted")

    async def test_a_coin_held_out_in_a_recovered_walk_out_is_still_decided_and_moves_nothing(self):
        # D-403 (2): the recovery path used to leave the coin in the words with no decision and no note.
        await self.begin()
        self.lose_the_reading()
        before = self.world["location"]
        purse = self.world.get("currency", {}).get("player")  # the walk meets new people, who carry purses of their own
        made, real = [], money_owner.decide
        with patch.object(money_owner, "decide", side_effect=lambda *a, **k: (made.append(real(*a, **k)), made[-1])[1]):
            await self.line("5 bakır bırakıp şehrin dışına gidiyorum")
        self.assertEqual(self.routes()[-1]["route"], "fallback:unusable:go_to")
        self.assertNotEqual(self.world["location"], before)
        self.assertEqual([(d.amount_cp, d.source) for d in made], [(5, "structural")])
        self.assertEqual(self.world.get("currency", {}).get("player"), purse)

    async def test_a_yes_with_no_open_offer_accepts_nothing(self):
        await self.begin()
        self.lose_the_reading()
        await self.line("tamam, yaparım")
        self.assertEqual(self.status(), "open")

    async def test_a_no_to_an_open_offer_is_not_a_yes(self):
        await self.begin()
        self.offer()
        self.lose_the_reading()
        await self.line("hayır, yapmıyorum")
        self.assertNotEqual(self.status(), "accepted")

    # Review of D-240: the fallback is conservative. In doubt it answers nothing and the old chain decides.

    async def no_yes(self, line):
        await self.begin()
        self.offer()
        self.lose_the_reading()
        await self.line(line)
        # the old chain may still decide such a line by its own readers; the fallback must not claim it
        self.assertNotIn(":offer_answer", self.routes()[-1]["route"], line)

    async def test_a_deferred_denied_or_untrue_yes_is_no_yes_when_the_reading_failed(self):
        for line in ("Şimdi değil, kabul ederim.", "Kabul ettim sanma.", "Kabul ediyorum diye yalan söylüyorum.",
                     "Kabul ediyorum demedim, eşyayı alıyorum."):
            with self.subTest(line=line):
                await self.no_yes(line)

    async def test_a_yes_that_also_does_something_else_is_left_to_the_old_chain(self):
        for line in ("Kabul ediyorum ve adamı soyuyorum.", "Kabul ediyorum ve kılıcımı çekiyorum.",
                     "Adamı soyuyorum ve kabul ediyorum."):
            with self.subTest(line=line):
                await self.no_yes(line)

    async def no_walk(self, line):
        await self.begin()
        here = self.world["location"]
        self.lose_the_reading()
        await self.line(line)
        self.assertEqual(self.world["location"], here, line)

    async def test_a_walk_out_that_is_late_untrue_or_not_alone_is_no_walk_when_the_reading_failed(self):
        for line in ("Yarın şehrin dışına giderim.", "Şehirden çıkıyorum diye yalan söylüyorum.",
                     "Şehrin dışına gidiyorum ve Zivanel'i soyuyorum.", "Şehrin dışına gidiyorum ve kılıcımı çekiyorum."):
            with self.subTest(line=line):
                await self.no_walk(line)

    async def robs_a_townsman_on_the_way_out(self, seed):
        # D-377: in these towns Zivanel keeps a place in town, so the old chain walks there (a walk to a named person).
        # The fallback must not take the line for a walk out of town.
        line = "Şehrin dışına gidiyorum ve Zivanel'i soyuyorum."
        await self.begin(seed=seed)
        step = grounded_action.plan(self.session, line)["steps"][0]
        self.assertEqual((step.get("target") or {}).get("kind"), "place")  # this town has a Zivanel: the case pinned
        self.lose_the_reading()
        await self.line(line)
        self.assertEqual(self.routes()[-1]["route"], "fallback:unusable")
        record = self.world["locations"][self.world["location"]]
        self.assertFalse(local_places.PLACE_KINDS.get(record.get("place_kind"), {}).get("outdoors"))

    async def test_a_walk_out_that_robs_a_townsman_is_no_walk_out_in_town_12(self):
        await self.robs_a_townsman_on_the_way_out(12)

    async def test_a_walk_out_that_robs_a_townsman_is_no_walk_out_in_town_27(self):
        await self.robs_a_townsman_on_the_way_out(27)

    async def test_a_walk_out_that_robs_a_townsman_is_no_walk_out_in_town_32(self):
        await self.robs_a_townsman_on_the_way_out(32)

    async def test_a_yes_naming_another_offer_s_owner_is_not_taken_for_the_one_spoken_to(self):
        await self.begin()
        import copy
        self.offer()
        other = copy.deepcopy(self.npc)
        other.update(id="npc_borvan", name="Borvan", public_name="Borvan", place_role_of="place_borvan")
        self.world["npcs"].append(other)
        state = world_threads.view(self.world)
        second = copy.deepcopy(self.thread)
        second.update(thread_id="thread_900", place_id="place_borvan", status="open", item_noun="mühür")
        state["threads"].append(second)
        world_threads.mark_offered(self.world, second, other, "On bakır, bir gün.", 0)
        self.lose_the_reading()
        await self.line("Borvan'ın teklifini kabul ediyorum ve eşyayı alıyorum.")
        self.assertNotEqual(self.status(), "accepted")
        self.assertEqual(world_threads.by_id(self.world, "thread_900")["status"], "offered")

    def test_nothing_is_recovered_while_a_question_waits_for_its_answer(self):
        import game
        listed = {"offers": [{"id": "t", "person_id": "n", "item": None}], "people": [], "speaking_with": "n"}
        for flag in ({"_attack_asked": True}, {"_heavy_asked": {"what": "threat"}}):
            session = game.GameSession()
            for name, value in flag.items():
                setattr(session, name, value)
            self.assertIsNone(game._front_recovery("Kabul ediyorum ve eşyayı alıyorum.", listed, session=session))

    async def test_the_label_follows_the_gate_when_it_overruled_the_yes(self):
        await self.begin()
        self.offer()
        self.lose_the_reading()
        await self.line("Kabul ediyorum, parayı ver.")
        self.assertEqual(self.routes()[-1]["route"], "fallback:unusable")

    async def test_a_plain_walk_out_of_town_still_walks_when_the_reading_failed(self):
        await self.begin()
        before = self.world["location"]
        self.client.front = {"kind": "go_to", "place_id": front_proposal.WAY_OUT}
        await self.line("şehrin dışına gidiyorum")
        after_ok = self.world["location"]
        name_ok = self.world["locations"][after_ok].get("place_kind")
        await self.begin()
        self.lose_the_reading()
        await self.line("şehrin dışına gidiyorum")
        after_failed = self.world["location"]
        name_failed = self.world["locations"][after_failed].get("place_kind")
        self.assertNotEqual(after_ok, before)
        self.assertNotEqual(after_failed, before)
        self.assertEqual(name_failed, name_ok)
        self.assertEqual(self.routes()[-1]["route"], "fallback:unusable:go_to")

    async def test_the_log_names_the_check_that_failed(self):
        await self.begin()
        self.client.fails = RuntimeError("no outage")  # an outage refuses the line (G6); any other error goes on
        await self.line("etrafa şöyle bir göz atayım")
        self.assertIn("front:local:RuntimeError", self.usage()[-1]["causes"])

    async def test_the_log_names_a_cut_reading(self):
        await self.begin()
        self.enterContext(front_tests.patch.object(self.app.state.ollama_adapter, "_client", CutClient("cut")))
        await self.line("etrafa şöyle bir göz atayım")
        self.assertIn("front:local:cut", self.usage()[-1]["causes"])

    async def test_the_log_names_a_reply_that_is_no_json(self):
        await self.begin()
        self.enterContext(front_tests.patch.object(self.app.state.ollama_adapter, "_client", CutClient("not_json")))
        await self.line("etrafa şöyle bir göz atayım")
        self.assertIn("front:local:not_json", self.usage()[-1]["causes"])

    async def test_a_turn_with_no_failure_logs_no_causes(self):
        await self.begin()
        self.client.front = {"kind": "look"}
        await self.line("etrafa şöyle bir göz atayım")
        self.assertNotIn("causes", self.usage()[-1])

    async def test_a_reading_that_names_no_open_offer_and_no_walk_keeps_its_old_label(self):
        await self.begin()
        self.lose_the_reading()
        await self.line("etrafa şöyle bir göz atayım")
        self.assertEqual(self.routes()[-1]["route"], "fallback:unusable")

    async def test_a_walk_back_into_town_is_no_walk_out_when_the_reading_failed(self):
        await self.begin()
        here = self.world["location"]
        self.lose_the_reading()
        for line in ("şehrin dışına gitmiyorum", "şehrin dışına gidiyor muyum?", "şehrin dışına gitsem mi"):
            await self.line(line)
            self.assertEqual(self.world["location"], here, line)

    async def test_a_doubt_or_a_no_in_a_long_line_is_no_yes_when_the_reading_failed(self):
        for line in ("Görevi kabul etmiyorum ve eşyayı almıyorum.", "Görevi kabul ediyorum ama önce parayı ver.",
                     "Görevi kabul edersem eşyayı alırım.", "Görevi kabul ediyorum diyebilir miyim?",
                     "Belki görevi kabul ediyorum ve eşyayı alıyorum."):
            with self.subTest(line=line):
                await self.begin()
                self.offer()
                self.lose_the_reading()
                await self.line(line)
                self.assertNotEqual(self.status(), "accepted")

    async def test_the_front_reading_has_room_to_finish(self):
        await self.begin()
        client = OptionsClient()
        self.enterContext(front_tests.patch.object(self.app.state.ollama_adapter, "_client", client))
        await self.line("etrafa şöyle bir göz atayım")
        self.assertGreaterEqual(client.options[-1].get("num_predict"), 700)

    async def test_a_log_row_holds_no_player_words(self):
        await self.begin()
        self.lose_the_reading()
        await self.line("etrafa şöyle bir göz atayım")
        self.assertNotIn("göz atayım", json.dumps(self.usage()[-1], ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
