"""Trails (Dilim 2, Task 7): a delivered errand leaves a known ledger row and may open one follow-on job by the town's
own rule; the quest log shows only trails that point at a live record, and following one is read, never written."""
from __future__ import annotations

import copy
import json
from contextlib import closing, contextmanager
from unittest.mock import patch
from uuid import uuid4

import game
import local_places
import quest_log
import world_happenings
import world_threads
from adventure import dialogue_jobs
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, ScriptedModel, _front_setting, apply_setup
from api.tests.journeys.schema import Step, load_scenario

_LETTER_ID = "thread_950"
_LETTER_KINDS = ("temple", "graveyard", "library", "archive", "bakery", "stable", "market", "barracks", "estate")


def _step(line=None, front=None, **flags):
    return Step(say=line, command=None, economic_action=None, combat_action=None,
                script={"front": front} if front else None, expect={}, known_broken=(), real_chain=False,
                independent=True, **flags)


class TrailCase(JourneyCase):
    scenario = "19d_delivery_undo.json"

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.setup = load_scenario(SCENARIO_DIR / self.scenario).setup
        await self.fresh_campaign()

    async def fresh_campaign(self):
        campaign = await self._journey_campaign(self.setup)
        apply_setup(self, campaign, self.setup)
        self.campaign_id = campaign["campaign_id"]
        self.session_id = campaign["session_id"]
        self.last_session_id = self.session_id

    # --- the world ------------------------------------------------------------------------------------------------
    @property
    def session(self):
        return self.manager.get(self.session_id).game_session

    @property
    def world(self):
        return self.session.world_state

    def state(self):
        return world_threads.view(self.world)

    def save(self):
        self.manager.save_campaign(self.campaign_id)

    def rows(self, kind):
        return [row for row in world_happenings.ledger(self.state()) if row["kind"] == kind]

    def thread_ids(self):
        return {t["thread_id"] for t in self.state()["threads"]}

    def npc(self, npc_id):
        return next(n for n in self.world["npcs"] if n.get("id") == npc_id)

    def delivered_thread(self):
        return world_threads.by_id(self.world, self.thread_id)

    def follow_on_thread(self):
        [row] = self.rows("delivered")
        return world_threads.by_id(self.world, row["next_thread_id"])

    def letter_thread(self):
        return world_threads.by_id(self.world, _LETTER_ID)

    def public_place_name(self, place_id):
        return self.world["locations"][place_id]["name"]

    def trail(self, source):
        [found] = [t for t in quest_log.trails(self.world) if t["source"] == source]
        return found

    def add_npc_at(self, place_id, npc_id):
        self.world["npcs"].append({"id": npc_id, "name": "Kerem", "role": "Yolcu", "current_hp": 10,
                                   "location": place_id})
        self.save()
        return self.npc(npc_id)

    @contextmanager
    def engine(self):
        token = game._ACTIVE_SESSION.set(self.session)
        try:
            yield
        finally:
            game._ACTIVE_SESSION.reset(token)

    # --- turns ----------------------------------------------------------------------------------------------------
    async def post_turn(self, line, front=None, action_id=None):
        body = {"action_id": action_id or str(uuid4()), "message": line}
        self.last_turn_action_id = body["action_id"]
        with _front_setting(self.setup), ScriptedModel().bind(self, _step(line, front)):
            return await self.http.post(f"/api/game/sessions/{self.session_id}/turn", json=body)

    async def say(self, line, front=None, action_id=None):
        response = await self.post_turn(line, front=front, action_id=action_id)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def undo(self):
        self.assertEqual(await self._undo(self.session_id, _step(undo=True), ScriptedModel()), [])

    async def restart(self):
        failures, _ = await self._reload(self.session_id, _step(reload=True), ScriptedModel())
        self.assertEqual(failures, [])
        self.session_id = self.last_session_id

    async def walk_to(self, place_id):
        if self.world["location"] == place_id:   # already standing there: step out first, so this is an arrival
            await self.say("dışarı çıkıyorum", front={"kind": "go_to", "place_id": self.world["locations"][place_id]
                                                       ["parent_location_id"]})
        await self.say("oraya gidiyorum", front={"kind": "go_to", "place_id": place_id})
        self.assertEqual(self.world["location"], place_id)

    # --- the job --------------------------------------------------------------------------------------------------
    async def accept(self):
        await self.say("olur, götürürüm")
        [thread] = [t for t in self.state()["threads"] if t.get("status") == "accepted"]
        self.thread_id, self.quest_id, self.tuna = thread["thread_id"], thread["quest_id"], thread["recipient_npc_id"]

    def at_recipient(self):
        self.world["location"] = self.delivered_thread()["target_place_id"]
        self.save()

    async def deliver(self):
        """Straight through the product's delivery (dialogue_jobs.deliver), at Tuna's door."""
        await self.accept()
        self.at_recipient()
        with self.engine():
            dialogue_jobs.deliver(self.session, self.delivered_thread(), self.npc(self.tuna), "Tuna, getirdim")
        self.save()
        self.assertEqual(self.delivered_thread()["status"], "done")

    async def deliver_by_turn(self, path=None):
        """An HTTP hand-over turn (Task 5's fixture); ``path`` repeats it the way Task 5's three proofs do."""
        await self.accept()
        self.at_recipient()
        front = {"kind": "hand_over", "person_id": self.tuna, "item_id": "none"}
        action_id = str(uuid4())
        if path == "failed_save_then_retry":
            with closing(self.store._connect()) as db:
                db.execute("""CREATE TRIGGER reject_receipt BEFORE INSERT ON campaign_turn_actions
                              BEGIN SELECT RAISE(ABORT, 'injected late failure'); END""")
            failed = await self.post_turn("Tuna, iade takımını getirdim", front=front, action_id=action_id)
            self.assertEqual(failed.status_code, 503, failed.text)
            self.assertEqual(self.rows("delivered"), [])
            with closing(self.store._connect()) as db:
                db.execute("DROP TRIGGER reject_receipt")
        await self.say("Tuna, iade takımını getirdim", front=front, action_id=action_id)
        if path == "replay":
            await self.say("Tuna, iade takımını getirdim", front=front, action_id=action_id)
        elif path == "restart":
            await self.restart()
            await self.say("Tuna, iade takımını getirdim", front=front, action_id=action_id)
        self.assertEqual(self.delivered_thread()["status"], "done")

    def open_job_like_the_first(self, number):
        """A live, public job of the town (a copy of the scenario's own job record, not offered to anyone)."""
        job = copy.deepcopy(self.state()["threads"][0])
        for key in ("offered_at", "offered_turn", "offer_line", "offer_line_turn", "owner_npc_id", "quest_id",
                    "accepted_at", "accepted_turn", "recipient_npc_id"):
            job.pop(key, None)
        job.update(thread_id=f"thread_{900 + number:03d}", status="open")
        self.state()["threads"].append(job)
        return job

    def leave_the_rule_nothing_to_open(self):
        """The town has no work of the kinds a delivery can grow into (only hiring is left in the catalog)."""
        catalog = world_threads.catalog()
        bare = {**catalog, "templates": [t for t in catalog["templates"] if t["type"] not in {"trouble", "errand"}]}
        return patch.object(world_threads, "catalog", return_value=bare)

    def write_known_rows(self, n):
        live = list(self.state()["threads"])
        live += [self.open_job_like_the_first(i) for i in range(1, n - len(live) + 1)]
        rows = [world_happenings.write(self.state(), live[0], "delivered", i, f"iz {i}", known=True,
                                       next_thread_id=live[i - 1]["thread_id"]) for i in range(1, n + 1)]
        self.save()
        return rows

    def trouble_at(self, place):
        template = next(t for t in world_threads.catalog()["templates"] if t["type"] == "trouble")
        with self.engine():
            trouble = world_threads._open_thread(self.world, self.state(), template, self.world["locations"][place["id"]]
                                                 ["parent_location_id"], create=False, now=world_threads._now(self.world),
                                                 place=place)
        self.assertIsNotNone(trouble)
        return trouble

    async def accept_sealed_letter(self):
        """A sealed letter from someone at the player's side to someone at a new place where a trouble is open; taken on
        by the product's own accept and hand-over (the way test_play_consequences.Sealed carries one)."""
        here = self.world["location"]
        settlement = local_places.settlement_of(self.world, here)
        target = next(record for kind in _LETTER_KINDS
                      if local_places.find_local_place(self.world, settlement, kind) is None
                      for record in (local_places.create_local_place(self.world, settlement, kind),) if record)
        sender = {"id": "sender", "name": "Selin", "role": "Kâtip", "current_hp": 10, "location": here, "inventory": []}
        addressee = {"id": "addressee", "name": "Ozan", "role": "Kâhya", "current_hp": 10, "location": target["id"],
                     "place_role_of": target["id"], "inventory": []}
        self.world["npcs"] += [sender, addressee]
        self.trouble_at(target)
        letter = copy.deepcopy(self.state()["threads"][0] if self.state()["threads"] else self.delivered_thread())
        for key in ("quest_id", "accepted_at", "accepted_turn", "recipient_npc_id", "paid_cp", "closed_at",
                    "outcome_known_turn", "delivered_late", "seal_broken", "letter_line"):
            letter.pop(key, None)
        line = "Mühürlü mektubu Ozan'a götür, mührü sakın bozma. On bakır."
        letter.update(thread_id=_LETTER_ID, type="errand", template_id="sealed_letter", status="offered",
                      place_id=here, target_place_id=target["id"], owner_npc_id="sender", owner_name="Selin",
                      recipient_name="Ozan", item_noun="mühürlü mektup", owner_line=line, offer_line=line,
                      terms={"pay": 10, "work_days": None, "pay_basis": "per_trip", "pay_timing": "on_delivery",
                             "deadline_text": "bir gün içinde"})
        self.state()["threads"].append(letter)
        letter = self.letter_thread()
        sender, addressee = self.npc("sender"), self.npc("addressee")
        with self.engine(), patch("world_threads.recipient_of", return_value=addressee):
            self.assertTrue(dialogue_jobs.accept_thread_job(self.session, letter, sender))
            dialogue_jobs.hand_over(self.session, letter, sender)
        self.assertTrue(dialogue_jobs.holds_parcel(self.world, letter))
        self.save()

    async def read_the_letter(self):
        out = await self.say("mührü kırıp mektubu okuyorum")
        self.assertIn("yazıyor", out["narration"])
        self.assertTrue(self.letter_thread().get("letter_line"))


class DeliveredRow(TrailCase):
    async def test_19d_setup_finds_a_follow_on(self):
        # the 19d scenario's own steps: accept, walk to the harbor, an idless hand-over to Tuna
        await self.accept()
        await self.say("iskeleye gidiyorum")
        await self.say("Tuna, iade takımını getirdim, buyur", front={"kind": "hand_over"})
        [row] = self.rows("delivered")
        self.assertIsNotNone(row["next_thread_id"])

    async def test_a_delivered_errand_writes_a_known_row_and_may_open_one_follow_on(self):
        await self.deliver()
        [row] = [r for r in world_happenings.ledger(self.state()) if r["kind"] == "delivered"]
        self.assertTrue(row["known_to_player"]); self.assertIsNotNone(row["next_thread_id"])
        self.assertLessEqual(len(row["line"].encode("utf-8")), world_happenings.MAX_LINE_BYTES)
        [trail] = quest_log.trails(self.world)
        self.assertEqual(trail["source"], "teslim"); self.assertFalse(trail["followed"])
        self.assertEqual((trail["what"], trail["where"]),
                         (row["line"], self.public_place_name(self.follow_on_thread()["place_id"])))
        self.assertEqual(set(trail), {"id", "what", "where", "who", "source", "followed"})

    async def test_no_follow_on_means_no_trail(self):
        with self.leave_the_rule_nothing_to_open():
            await self.deliver()
        [row] = self.rows("delivered")
        self.assertIsNone(row["next_thread_id"])
        self.assertEqual(quest_log.trails(self.world), [])     # nothing invented

    async def test_a_trail_to_a_closed_record_is_gone(self):
        await self.deliver()
        follow = self.follow_on_thread()
        self.state()["threads"].remove(follow)
        follow["status"] = "expired"
        self.state()["history"].append(follow)
        self.assertEqual(quest_log.trails(self.world), [])

    async def test_the_validator_knows_the_delivered_kind(self):
        await self.deliver()
        world_happenings.validate(world_happenings.ledger(self.state()))   # does not raise with a "delivered" row
        self.assertIn("delivered", world_happenings.KINDS)

    async def test_trails_are_newest_first_and_at_most_six(self):
        rows = self.write_known_rows(8)                              # 8 known rows, each next_thread_id -> a live job
        trails = quest_log.trails(self.world)
        self.assertEqual(len(trails), quest_log.MAX_TRAILS)
        self.assertEqual(quest_log.MAX_TRAILS, 6)
        self.assertEqual([t["what"] for t in trails], [r["line"] for r in sorted(rows, key=lambda r: r["at"], reverse=True)][:6])
        self.assertEqual(quest_log.view(self.world)["trails"], trails)


class Letter(TrailCase):
    async def test_a_read_letter_points_to_the_trouble_at_its_place(self):
        await self.accept_sealed_letter(); await self.read_the_letter()
        trouble = world_happenings._trouble_at_end_of(self.world, self.letter_thread())
        self.assertIsNotNone(trouble)
        [trail] = [t for t in quest_log.trails(self.world) if t["source"] == "mektup"]
        self.assertEqual(trail["where"], self.public_place_name(self.letter_thread()["target_place_id"]))
        self.assertFalse(trail["followed"])

    async def test_an_unread_letter_is_no_trail(self):
        await self.accept_sealed_letter()
        self.assertEqual(quest_log.trails(self.world), [])


class Following(TrailCase):
    async def test_following_a_trail_is_read_not_written(self):
        await self.deliver_by_turn()
        place = self.follow_on_thread()["place_id"]
        town = self.world["locations"][place]["parent_location_id"]
        await self.say("dışarı çıkıyorum", front={"kind": "go_to", "place_id": town})   # a walk somewhere else first,
        self.assertEqual(self.world["location"], town)                               # so the world holds what a walk writes
        [trail] = quest_log.trails(self.world)
        self.assertFalse(trail["followed"])
        keys_before = set(self.world)
        flags_before = set(self.world.get("flags") or {})
        await self.walk_to(place)                                    # the follow-on job's own place
        [trail] = quest_log.trails(self.world)
        self.assertTrue(trail["followed"])
        self.assertEqual(set(self.world), keys_before)               # no new world_state key
        self.assertNotIn("followed", json.dumps(self.state(), ensure_ascii=False))
        self.assertEqual({k for k in self.world["flags"] if k not in flags_before and "trail" in k}, set())

    async def test_undo_of_the_delivery_removes_the_row_and_the_follow_on(self):
        before = self.thread_ids()
        await self.deliver_by_turn()                                 # an HTTP turn, so undo has a snapshot
        self.assertEqual(len(self.rows("delivered")), 1)
        self.assertEqual(len(self.thread_ids() - before), 1)
        await self.undo()
        self.assertEqual(self.rows("delivered"), [])
        self.assertEqual(self.thread_ids(), before)
        self.assertEqual(quest_log.trails(self.world), [])

    async def test_replay_restart_and_a_failed_save_leave_one_delivered_row(self):
        # J-014 #7: the delivered row and the follow-on are part of the atomic delivery (tasarım karar 60)
        for path in ("replay", "restart", "failed_save_then_retry"):
            with self.subTest(path=path):
                await self.fresh_campaign(); before = self.thread_ids()
                await self.deliver_by_turn(path=path)
                self.assertEqual(len(self.rows("delivered")), 1)
                self.assertEqual(len(self.thread_ids() - before), 1 if self.rows("delivered")[0]["next_thread_id"] else 0)


class WhoHears(TrailCase):
    async def test_a_trail_reaches_only_npcs_in_its_jobs(self):
        # J-014 #8: a place is not knowledge (tasarım karar 61, Dilim 1 D28)
        await self.deliver()                                             # the delivery trail: the potter's job to a follow-on
        await self.accept_sealed_letter(); await self.read_the_letter()  # a private letter trail
        follow = self.follow_on_thread()
        giver, recipient = self.npc(self.delivered_thread()["owner_npc_id"]), self.npc(self.delivered_thread()["recipient_npc_id"])
        bystander = self.add_npc_at(follow.get("target_place_id") or follow["place_id"], npc_id="bystander")
        letter = self.letter_thread()
        sender, addressee = self.npc(letter["owner_npc_id"]), self.npc(letter["recipient_npc_id"])
        self.assertEqual(len({giver["id"], recipient["id"], sender["id"], addressee["id"]}), 4)
        self.assertEqual(quest_log.card_lines(self.world, npc=bystander), [])
        for npc in (giver, recipient):
            with self.subTest(npc=npc["id"]):
                self.assertEqual([l for l in quest_log.card_lines(self.world, npc=npc) if l.startswith("izler:")],
                                 [f"izler: {self.trail('teslim')['what']} → {self.trail('teslim')['where']}"])
        for npc in (sender, addressee):
            with self.subTest(npc=npc["id"]):
                self.assertIn(f"izler: {self.trail('mektup')['what']} → {self.trail('mektup')['where']}",
                              quest_log.card_lines(self.world, npc=npc))
        self.assertNotIn(f"izler: {self.trail('mektup')['what']} → {self.trail('mektup')['where']}",
                         quest_log.card_lines(self.world, npc=giver))           # the potter is not in the letter's job
        self.assertNotIn("_from_thread_id", json.dumps(quest_log.trails(self.world)))
        self.assertNotIn("_to_thread_id", json.dumps(quest_log.view(self.world)))

    async def test_the_narrator_sees_at_most_two_trails(self):
        self.write_known_rows(5)
        lines = [l for l in quest_log.card_lines(self.world) if l.startswith("izler:")]
        self.assertEqual(lines, [f"izler: {t['what']} → {t['where']}" for t in quest_log.trails(self.world)][:2])

    async def test_a_known_link_about_the_players_job_is_heard_news(self):
        await self.accept()
        job = self.delivered_thread()
        with self.engine():
            link = world_happenings.tie(self.world, world_happenings.CALLER, "warned", self.npc("potter"),
                                        job["place_id"], about=job["thread_id"])
        self.assertIsNotNone(link)
        [trail] = quest_log.trails(self.world)
        self.assertEqual((trail["source"], trail["where"]), ("haber", self.public_place_name(job["place_id"])))
        bystander = self.add_npc_at(job["place_id"], "bystander")
        izler = lambda npc: [l for l in quest_log.card_lines(self.world, npc=npc) if l.startswith("izler:")]  # noqa: E731
        self.assertEqual(izler(bystander), [])
        self.assertEqual(izler(self.npc("potter")), [f"izler: {trail['what']} → {trail['where']}"])
