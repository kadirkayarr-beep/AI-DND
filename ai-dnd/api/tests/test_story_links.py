"""Threads that touch: a trouble comes to something on the clock, and what the player did changes what comes.

No model is called anywhere in here. Same seed, different choices, different story.
"""
import unittest
from unittest.mock import patch

import campaign_time
import local_dialogue
import relationships
import town_knowledge
import town_rumours
import vouching
import world_happenings
import world_threads
from adventure import dialogue_jobs

from api.tests import test_experimental_npc_dialogue as speech
from api.tests import test_thread_gate as gate_tests
from api.tests.test_world_threads import DAY, HOUR, city


def town(seed="seed-links"):
    world = city(seed)
    world_threads.ensure(world)
    return world, world[world_threads.KEY]


class TheClockComesFirst(unittest.TestCase):
    def test_a_long_wait_opens_new_threads_at_the_hour_it_ended(self):
        world, state = town()
        before = {t["thread_id"] for t in state["threads"]}
        campaign_time.advance(world, 7 * DAY, "rest", "test")
        now = world_threads._now(world)
        state = world[world_threads.KEY]
        fresh = [t for t in state["threads"] if t["thread_id"] not in before]
        self.assertTrue(fresh)
        for thread in fresh:
            self.assertEqual(thread["opened_at"], now)
            self.assertGreater(thread["expires_at"], now)

    def test_a_tick_on_its_own_says_what_time_it_is(self):
        world, state = town()
        before = {t["thread_id"] for t in state["threads"]}
        world_threads.tick(world, 7 * DAY)
        fresh = [t for t in world[world_threads.KEY]["threads"] if t["thread_id"] not in before]
        self.assertTrue(fresh)
        for thread in fresh:
            self.assertEqual(thread["opened_at"], 7 * DAY)


def thread_at(state, kind="trouble"):
    return next(t for t in state["threads"] if t["type"] == kind)


def resident(world, place_id, npc_id="sakin"):
    npc = {"id": npc_id, "name": npc_id.title(), "role": "usta", "location": place_id, "place_role_of": place_id}
    world["npcs"].append(npc)
    return npc


def town_with_trouble(start=0):
    """The first seed from here whose town opened with a trouble."""
    for number in range(start, start + 200):
        world, state = town(f"seed-trouble-{number}")
        if any(t["type"] == "trouble" for t in state["threads"]):
            return world, state
    raise AssertionError("no seed opened a trouble")


def fire(world, thread):
    """The clock reaches the moment. The record is read again by id: a step replaces the state."""
    world_threads.tick(world, thread["fires_at"])
    return world[world_threads.KEY], world_threads.by_id(world, thread["thread_id"])


class TheLedger(unittest.TestCase):
    def test_a_new_town_has_an_empty_ledger_and_an_old_save_gains_one(self):
        world, state = town()
        self.assertEqual(state["happenings"], [])
        del state["happenings"]
        world_threads.validate(state)
        world_threads.ensure(world)
        self.assertEqual(world[world_threads.KEY]["happenings"], [])

    def test_it_keeps_sixteen_and_refuses_a_damaged_row(self):
        world, state = town()
        thread = state["threads"][0]
        for at in range(20):
            world_happenings.write(state, thread, "visit", at, "Bir şey oldu.")
        self.assertEqual([row["at"] for row in state["happenings"]], list(range(4, 20)))
        world_threads.validate(state)
        state["happenings"][0]["kind"] = "savaş"
        with self.assertRaises(ValueError):
            world_threads.validate(state)
        state["happenings"][0].update(kind="visit", line="x" * 91)
        with self.assertRaises(ValueError):
            world_threads.validate(state)

    def test_it_is_not_a_deed_and_someone_nearby_says_it_with_its_label(self):
        world, state = town()
        thread = state["threads"][0]
        here = resident(world, thread["place_id"])
        world_happenings.write(state, thread, "closed", 0, "Dükkân kapanmış.")
        self.assertNotIn("deeds", world["flags"])
        self.assertEqual(town_knowledge.speech_note(world, here).count("Duyduğun: Dükkân kapanmış."), 1)

    def test_someone_across_town_does_not_hear_it_here(self):
        world, state = town()
        thread = state["threads"][0]
        other = next(t for t in state["threads"] if t["place_id"] != thread["place_id"])
        far = resident(world, other["place_id"])
        world_happenings.write(state, thread, "closed", 0, "Dükkân kapanmış.")
        self.assertNotIn("Duyduğun:", town_knowledge.speech_note(world, far))


class ATroubleComesToSomething(unittest.TestCase):
    def test_it_has_a_moment_and_cannot_quietly_run_out_before_it(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        self.assertGreater(thread["fires_at"], thread["opened_at"])
        self.assertEqual(thread["expires_at"], thread["fires_at"])

    def test_no_other_kind_of_thread_has_one(self):
        for number in range(12):
            _, state = town(f"seed-other-{number}")
            for thread in state["threads"]:
                self.assertEqual("fires_at" in thread, thread["type"] == "trouble")

    def test_it_stays_quiet_until_its_moment(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        world_threads.tick(world, thread["fires_at"] - 1)
        self.assertNotIn(thread["thread_id"], [r["thread_id"] for r in world[world_threads.KEY]["happenings"]])
        self.assertIn(world_threads.by_id(world, thread["thread_id"])["status"], world_threads.PUBLIC)

    def test_at_its_moment_it_happens_and_no_deed_is_written(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        state, closed = fire(world, thread)
        self.assertEqual(closed["status"], "fired")
        self.assertEqual(closed["closed_at"], thread["fires_at"])
        row = next(r for r in state["happenings"] if r["thread_id"] == thread["thread_id"])
        self.assertIn(row["kind"], {"visit", "closed", "lost"})
        self.assertEqual(row["at"], thread["fires_at"])
        self.assertEqual(row["place_id"], thread["place_id"])
        self.assertNotIn("deeds", world["flags"])
        world_threads.validate(state)

    def test_nobody_is_named_and_every_line_fits_and_all_three_endings_turn_up(self):
        kinds = set()
        for number in range(40):
            world, state = town(f"seed-end-{number}")
            for thread in [t for t in state["threads"] if t["type"] == "trouble"]:
                state, _ = fire(world, thread)
                row = next(r for r in state["happenings"] if r["thread_id"] == thread["thread_id"])
                kinds.add(row["kind"])
                self.assertLessEqual(len(row["line"].encode("utf-8")), 90)
                self.assertNotIn("{", row["line"])
                self.assertNotIn(thread["owner_name"], row["line"])
        self.assertEqual(kinds, {"visit", "closed", "lost"})

    def test_one_that_was_turned_down_still_happens(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        thread.update(status="declined", declined_turn=1)
        state, closed = fire(world, thread)
        self.assertEqual(closed["status"], "fired")

    def test_a_save_from_before_keeps_the_old_way_of_closing(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        del thread["fires_at"]
        world_threads.tick(world, thread["expires_at"])
        self.assertIn(world_threads.by_id(world, thread["thread_id"])["status"], {"filled_by_other", "expired"})
        self.assertNotIn(thread["thread_id"], [r["thread_id"] for r in world[world_threads.KEY]["happenings"]])

    def test_a_person_in_town_can_tell_it_as_news_and_the_telling_counts(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        here = resident(world, thread["place_id"])
        state, _ = fire(world, thread)
        row = next(r for r in state["happenings"] if r["thread_id"] == thread["thread_id"])
        news = [item for item in town_knowledge.public_knowledge(world, here) if item["kind"] == "news"]
        self.assertEqual([item["text"] for item in news if item["thread_id"] == thread["thread_id"]], [row["line"]])
        self.assertEqual(town_knowledge.speech_note(world, here).count(row["line"]), 1)
        town_knowledge.note_mention(world, here, row["line"])
        self.assertTrue(row["known_to_player"])

    def test_walking_up_to_the_place_afterwards_shows_it_once(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        state, _ = fire(world, thread)
        row = next(r for r in state["happenings"] if r["thread_id"] == thread["thread_id"])
        self.assertFalse(row["known_to_player"])
        self.assertEqual(world_threads.arrival_line(world, thread["place_id"]), row["line"])
        self.assertTrue(row["known_to_player"])
        self.assertIsNone(world_threads.arrival_line(world, thread["place_id"]))

    def test_standing_there_when_it_happens_you_see_it(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        world["location"] = thread["place_id"]
        state, _ = fire(world, thread)
        row = next(r for r in state["happenings"] if r["thread_id"] == thread["thread_id"])
        self.assertTrue(row["known_to_player"])
        self.assertIn({"place": thread["place_id"], "line": row["line"]}, world["flags"]["reaction_lines"])


def owner_of(world, thread):
    thread["owner_npc_id"] = "sahip"
    return resident(world, thread["place_id"], "sahip")


def take_on(world, thread, npc, turn=2):
    world_threads.mark_offered(world, thread, npc, thread["owner_line"], turn)
    return world_threads.apply_decision(world, thread, "accepted", turn)


def ending(world, thread):
    return [r["kind"] for r in world[world_threads.KEY]["happenings"] if r["thread_id"] == thread["thread_id"]]


class SomeoneTakesItOn(unittest.TestCase):
    def test_it_is_listed_as_this_persons_own_with_no_money_in_it(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        npc = owner_of(world, thread)
        self.assertIn(thread, world_threads.jobs_of(world, npc))
        note = town_knowledge.promise_note(world, npc)
        self.assertIn(thread["thread_id"], note)
        self.assertNotIn("None", note)
        self.assertIsNone(thread["terms"]["pay"])

    def test_paid_work_comes_before_a_trouble(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        job = next(t for t in state["threads"] if t["type"] != "trouble")
        job["place_id"] = thread["place_id"]
        state["threads"].sort(key=lambda t: t["type"] != "trouble")
        npc = owner_of(world, thread)
        self.assertEqual(world_threads.jobs_of(world, npc)[0], job)

    def test_taking_it_on_stops_the_clock_on_it(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        npc = owner_of(world, thread)
        moment = thread["fires_at"]
        self.assertTrue(take_on(world, thread, npc))
        self.assertNotIn("fires_at", thread)
        world_threads.tick(world, moment + 60)
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "accepted")
        self.assertEqual(ending(world, thread), [])

    def test_same_seed_seen_through_it_is_averted_left_alone_it_happens(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        npc = owner_of(world, thread)
        take_on(world, thread, npc)
        world_threads._credit_day(world, thread, 0)
        self.assertEqual(thread["status"], "done")
        self.assertEqual(ending(world, thread), ["averted"])
        self.assertGreaterEqual(relationships.score(world, npc["id"]), 1)
        self.assertNotIn("deeds", world["flags"])
        other, other_state = town_with_trouble()
        same = thread_at(other_state)
        self.assertEqual(same["thread_id"], thread["thread_id"])
        _, closed = fire(other, same)
        self.assertEqual(closed["status"], "fired")
        self.assertIn(ending(other, same)[0], {"visit", "closed", "lost"})

    def test_dropping_it_only_buys_six_hours(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        npc = owner_of(world, thread)
        take_on(world, thread, npc)
        world_threads.apply_decision(world, thread, "abandoned", 3)
        closed = world_threads.by_id(world, thread["thread_id"])
        self.assertEqual(closed["status"], "abandoned")
        self.assertEqual(closed["fires_at"], closed["closed_at"] + 6 * HOUR)
        world_threads.tick(world, closed["fires_at"] - 1)
        self.assertEqual(ending(world, thread), [])
        world_threads.tick(world, closed["fires_at"])
        self.assertEqual(len(ending(world, thread)), 1)
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "abandoned")

    def test_leaving_it_undone_comes_to_the_same_thing(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        npc = owner_of(world, thread)
        take_on(world, thread, npc)
        limit = thread["work_until"]
        world_threads.tick(world, limit + 1)
        closed = world_threads.by_id(world, thread["thread_id"])
        self.assertEqual(closed["status"], "failed")
        self.assertEqual(closed["fires_at"], limit + 6 * HOUR)
        world_threads.validate(world[world_threads.KEY])

    def test_no_coin_moves_and_asking_for_some_is_answered_as_such(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        npc = owner_of(world, thread)
        take_on(world, thread, npc)
        self.assertEqual(world_threads.wage_due(world, thread), (0, "no_pay"))
        before = dict(world.get("currency") or {})
        world_threads._credit_day(world, thread, 0)
        self.assertEqual(dict(world.get("currency") or {}), before)

    def test_the_owner_says_it_came_to_this(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        here = resident(world, thread["place_id"])
        thread.update(offered_at=0, offered_turn=1, status="offered", owner_npc_id=here["id"])
        fire(world, thread)
        self.assertIn(world_threads.job_lines("trouble", "fired")[0], town_knowledge.speech_note(world, here))

    def test_a_person_who_has_a_trouble_still_says_no_money_is_in_it(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        note = town_knowledge.speech_note(world, owner_of(world, thread))
        self.assertIn(thread["owner_line"], note)
        self.assertIn(world_threads.job_lines("shared", "trouble"), note)
        self.assertNotIn("ücreti ve süreyi aynen söyle", note)


def fired_rows(count=40):
    """(world, parent thread, its ledger row) for the first trouble of many campaigns."""
    for number in range(count):
        world, state = town(f"seed-chain-{number}")
        thread = next((t for t in state["threads"] if t["type"] == "trouble"), None)
        if thread is None:
            continue
        moment = thread["fires_at"]
        parent = dict(thread)
        world_threads.tick(world, moment)
        state = world[world_threads.KEY]
        yield world, state, parent, next(r for r in state["happenings"] if r["thread_id"] == parent["thread_id"])


class OneThingLeadsToAnother(unittest.TestCase):
    def test_it_opens_something_new_at_that_moment_and_says_which(self):
        followed = 0
        for world, state, parent, row in fired_rows():
            following = world_threads.by_id(world, row["next_thread_id"])
            if following is None:
                continue
            followed += 1
            self.assertEqual(following["opened_at"], parent["fires_at"])
            self.assertNotEqual(following["template_id"], parent["template_id"])
            self.assertIn(following, state["threads"])
        self.assertGreater(followed, 10)

    def test_each_ending_leads_its_own_way(self):
        seen = set()
        for world, state, parent, row in fired_rows(60):
            following = world_threads.by_id(world, row["next_thread_id"])
            if following is None:
                continue
            seen.add(row["kind"])
            if row["kind"] == "visit" and following["place_id"] == parent["place_id"]:
                self.assertEqual(following["type"], "trouble")
            if row["kind"] in {"lost", "closed"}:
                self.assertNotEqual(following["place_id"], parent["place_id"])
                self.assertNotEqual(following["type"], "hiring")
        self.assertEqual(seen, {"visit", "closed", "lost"})

    def test_a_visit_stays_at_the_place_when_something_fits_it(self):
        same = [following["place_id"] == parent["place_id"]
                for world, state, parent, row in fired_rows(60) if row["kind"] == "visit"
                for following in [world_threads.by_id(world, row["next_thread_id"])] if following is not None]
        self.assertTrue(same)
        self.assertGreater(sum(same), len(same) / 2)

    def test_a_closed_place_hires_nobody_for_two_days(self):
        for world, state, parent, row in fired_rows(60):
            if row["kind"] != "closed":
                continue
            template = next(t for t in world_threads.catalog()["templates"]
                            if t["type"] == "hiring" and world["locations"][parent["place_id"]]["place_kind"] in t["place_kinds"])
            record = world["locations"][parent["place_id"]]
            at = parent["fires_at"]
            self.assertIsNone(world_threads._open_thread(world, state, template, parent["settlement_id"], create=False,
                                                         now=at + 2 * DAY - 1, place=record))
            self.assertIsNotNone(world_threads._open_thread(world, state, template, parent["settlement_id"], create=False,
                                                            now=at + 2 * DAY, place=record))
            return
        self.fail("no campaign closed a place")

    def test_a_full_town_opens_nothing_more(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        moment = thread["fires_at"]
        while len(state["threads"]) < world_threads.MAX_ACTIVE:
            state["threads"].append(dict(state["threads"][-1], thread_id=f"thread_{len(state['threads']) + 50}", fires_at=moment + 9 * DAY,
                                         expires_at=moment + 9 * DAY, type="hiring", status="accepted", work_until=moment + 9 * DAY))
        self.assertIsNone(world_happenings._follow_on(world, state, "seed", thread, "visit", moment))
        world_threads.tick(world, moment)
        state = world[world_threads.KEY]
        self.assertLessEqual(len(state["threads"]), world_threads.MAX_ACTIVE)
        world_threads.validate(state)

    def test_seeing_it_through_leads_nowhere_by_itself(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        npc = owner_of(world, thread)
        take_on(world, thread, npc)
        world_threads._credit_day(world, thread, 0)
        self.assertIsNone(world[world_threads.KEY]["happenings"][-1]["next_thread_id"])

    def test_the_same_campaign_takes_the_same_turn(self):
        def run():
            world, state = town_with_trouble(30)
            world_threads.tick(world, thread_at(state)["fires_at"])
            return world[world_threads.KEY]
        self.assertEqual(run(), run())


class Pocket:
    """All a reading needs from a session."""

    def __init__(self, world):
        self.world_state = world
        self.messages = []


def letter_for(world, state, trouble, line="Hesap tutmuyor, bakan biri lazım."):
    """A letter in the player's bag, going to where this trouble is."""
    letter = next(t for t in state["threads"] if t is not trouble)
    letter.update(type="errand", status="accepted", item_noun="mektup", quest_id="q1", target_place_id=trouble["place_id"],
                  owner_line="Mühürlü mektup var.")
    trouble["owner_line"] = line
    world["inventory"] = [{"item_id": "parcel:q1", "name": "Mektup", "quantity": 1}]
    return letter


class ALetterSaysSomething(unittest.TestCase):
    def test_there_are_twice_as_many_and_half_can_carry_a_real_matter(self):
        letters = world_threads.job_lines("errand", "letters")
        self.assertEqual(len(letters), 12)
        self.assertEqual(sum("{matter}" in line for line in letters), 6)

    def test_opened_it_tells_the_trouble_where_it_goes_and_the_player_now_knows_of_it(self):
        world, state = town_with_trouble()
        trouble = thread_at(state)
        letter_for(world, state, trouble)
        shown = dialogue_jobs.read_parcel(Pocket(world), "mektubu açıp okuyorum")["narration"]
        self.assertIn(trouble["owner_line"], shown)
        self.assertEqual(trouble["status"], "heard")
        self.assertEqual(trouble["heard_turn"], world["flags"]["turn_index"])

    def test_read_again_after_the_trouble_is_over_it_still_says_the_same_words(self):
        world, state = town_with_trouble()
        trouble = thread_at(state)
        letter_for(world, state, trouble)
        session = Pocket(world)
        first = dialogue_jobs.read_parcel(session, "mektubu okuyorum")["narration"]
        trouble["status"] = "expired"
        again = dialogue_jobs.read_parcel(session, "mektubu bir daha okuyorum")["narration"]
        self.assertIn(first.split("“")[1], again)

    def test_a_matter_too_long_to_quote_leaves_the_old_kind_of_letter(self):
        world, state = town_with_trouble()
        trouble = thread_at(state)
        letter = letter_for(world, state, trouble, line="ç" * 50)
        trouble["public_line"] = "ş" * 50
        self.assertNotIn("çç", dialogue_jobs.letter_text(world, letter))
        self.assertNotIn("{", dialogue_jobs.letter_text(world, letter))

    def test_a_letter_to_a_quiet_place_is_the_old_kind_too(self):
        world, state = town_with_trouble()
        trouble = thread_at(state)
        letter = letter_for(world, state, trouble)
        trouble["status"] = "accepted"
        words = dialogue_jobs.letter_text(world, letter)
        self.assertNotIn("{", words)
        self.assertNotIn(trouble["owner_line"], words)


def passer_by(world, thread, *, false_one):
    """Someone elsewhere in town who has the rumour of this trouble, and not the trouble itself."""
    other = next(t["place_id"] for t in world[world_threads.KEY]["threads"] if t["place_id"] != thread["place_id"])
    for number in range(400):
        npc = {"id": f"npc_{number}", "name": "Biri", "role": "gezgin", "location": other}
        rumours = [item for item in town_knowledge.public_knowledge(world, npc)
                   if item["kind"] == "rumour" and item["thread_id"] == thread["thread_id"]]
        if rumours:
            return npc, rumours[0]
    return None, None


def town_with_rumour(*, false_one):
    for number in range(60):
        world, state = town_with_trouble(number * 7)
        thread = thread_at(state)
        if town_rumours.is_true(world, thread) is (not false_one):
            npc, item = passer_by(world, thread, false_one=false_one)
            if npc:
                return world, thread, npc, item
    raise AssertionError("no campaign had that rumour")


class HalfTruths(unittest.TestCase):
    def test_a_true_one_says_what_the_street_says(self):
        world, thread, npc, item = town_with_rumour(false_one=False)
        self.assertEqual(item["text"], thread["public_line"])

    def test_a_false_one_has_the_right_place_and_nobody_in_it(self):
        world, thread, npc, item = town_with_rumour(false_one=True)
        place = world["locations"][thread["place_id"]]["name"]
        self.assertIn(place, item["text"])
        self.assertNotIn(thread["owner_name"], item["text"])
        self.assertEqual(item["location_id"], thread["place_id"])

    def test_no_word_of_true_or_false_reaches_the_prompt(self):
        world, thread, npc, item = town_with_rumour(false_one=True)
        self.assertEqual(set(item), {"kind", "text", "location_id", "thread_id"})
        note = town_knowledge.speech_note(world, npc)
        self.assertIn(item["text"], note)
        for word in ("yanlis", "dogru", "yanlış", "doğru"):
            self.assertNotIn(word, item["text"])

    def test_the_owner_never_hears_a_false_one_of_their_own(self):
        world, thread, npc, item = town_with_rumour(false_one=True)
        owner = resident(world, thread["place_id"])
        self.assertNotIn(item["text"], [i["text"] for i in town_knowledge.public_knowledge(world, owner)])

    def test_a_person_carries_one_at_most(self):
        for number in range(30):
            world, state = town(f"seed-rumours-{number}")
            for index in range(20):
                npc = {"id": f"npc_{index}", "name": "Biri", "role": "gezgin", "location": "city"}
                known = town_knowledge.public_knowledge(world, npc)
                self.assertLessEqual(sum(item["kind"] == "rumour" for item in known), 1)
                self.assertLessEqual(len(known), 5)

    def test_it_comes_after_news_and_before_places(self):
        world, thread, npc, item = town_with_rumour(false_one=True)
        kinds = [i["kind"] for i in town_knowledge.public_knowledge(world, npc)]
        self.assertEqual(kinds, sorted(kinds, key=["thread", "news", "rumour", "place"].index))

    def test_a_place_named_alone_is_not_hearing_it(self):
        world, thread, npc, item = town_with_rumour(false_one=True)
        place = world["locations"][thread["place_id"]]["name"]
        town_knowledge.note_mention(world, npc, f"{place} uzaktır, oraya kim gider.")
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "open")

    def test_saying_it_in_your_own_way_is(self):
        world, thread, npc, item = town_with_rumour(false_one=True)
        town_knowledge.note_mention(world, npc, f"Ne bileyim, derler ki {item['text']}")
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "heard")

    def test_when_no_reply_can_be_used_a_rumour_is_not_handed_out_as_fact(self):
        world, thread, npc, item = town_with_rumour(false_one=True)
        self.assertNotIn(item["text"], town_knowledge.fallback_line(world, npc) or "")


class WhatIsComingForThem(unittest.TestCase):
    def ahead(self, hours):
        """A trouble this many hours past the top of the current day."""
        world, state = town_with_trouble()
        thread = thread_at(state)
        hour = campaign_time.public_time(world)["hour"]
        thread["fires_at"] = world_threads._now(world) + (hours - hour) * HOUR
        return world, thread

    def test_the_owner_has_it_in_a_word_and_never_in_a_figure(self):
        words = {12: "bugün", 22: "bu gece", 29: "bu gece", 36: "yarın", 80: "birkaç gün"}
        for hours, word in words.items():
            world, thread = self.ahead(hours)
            note = world_happenings.waiting_note(world, resident(world, thread["place_id"]))
            self.assertEqual(note, f" Seni bekleyen: {thread['public_line'].rstrip('.')}; {word}.", hours)
            self.assertNotRegex(note.replace(thread["public_line"].rstrip("."), ""), r"\d")

    def test_it_is_in_the_prompt_once(self):
        world, thread = self.ahead(36)
        note = town_knowledge.speech_note(world, resident(world, thread["place_id"]))
        self.assertEqual(note.count("Seni bekleyen:"), 1)

    def test_nobody_else_has_it(self):
        world, thread = self.ahead(36)
        other = next(t["place_id"] for t in world[world_threads.KEY]["threads"] if t["place_id"] != thread["place_id"])
        self.assertEqual(world_happenings.waiting_note(world, resident(world, other)), "")

    def test_in_someones_hands_nothing_is_waiting(self):
        world, thread = self.ahead(36)
        npc = owner_of(world, thread)
        take_on(world, thread, npc)
        self.assertEqual(world_happenings.waiting_note(world, npc), "")


def gated_town(start=0, kind="estate"):
    """A town whose first thread stands at a house that does not open to strangers, with a place that could speak for you."""
    for number in range(start, start + 300):
        world, state = town(f"seed-gate-{number}")
        thread = state["threads"][0]
        other = next((t for t in state["threads"] if t["place_id"] != thread["place_id"]), None)
        if other is None:
            continue
        seed = world["scene_state"]["campaign_seed"]
        if world_threads._rank(seed, thread["thread_id"], "wary") % 100 < world_threads.WARY_PERCENT:
            continue
        world["locations"][thread["place_id"]]["place_kind"] = kind
        world["locations"][other["place_id"]]["place_kind"] = vouching.chosen_kinds(world, thread)[0]
        for record in world["locations"].values():
            if record.get("place_kind") not in (None, kind) and record["id"] != other["place_id"]:
                record["place_kind"] = "bakery"
        npc = resident(world, thread["place_id"], "kapici")
        return world, state, thread, npc, resident(world, other["place_id"], "tanidik")
    raise AssertionError("no such town")


class ADoorThatWantsAWord(unittest.TestCase):
    def test_a_stranger_is_wary_met_never_refused(self):
        world, state, thread, npc, friend = gated_town()
        self.assertEqual(world_threads.owner_mood(world, thread, npc), "wary")

    def test_talking_alone_does_not_open_it(self):
        world, state, thread, npc, friend = gated_town()
        with patch.object(world_threads, "WARY_PERCENT", 0):
            self.assertEqual(world_threads.owner_mood(world, thread, npc, this_exchange=5), "wary")

    def test_someone_who_owes_you_one_opens_it(self):
        world, state, thread, npc, friend = gated_town()
        relationships.note(world, friend["id"], 1, "test")
        self.assertEqual(world_threads.owner_mood(world, thread, npc), "yes")

    def test_a_finished_job_at_that_place_is_what_does_it(self):
        world, state, thread, npc, friend = gated_town()
        job = next(t for t in state["threads"] if t["place_id"] == friend["location"])
        job.update(type="hiring", status="accepted", accepted_at=0, work_until=DAY, owner_npc_id=friend["id"])
        job["terms"].update(pay=9, work_days=1, pay_basis="total")
        world_threads._credit_day(world, job, 0)
        self.assertEqual(world_threads.owner_mood(world, thread, npc), "yes")

    def test_someone_of_another_kind_does_not(self):
        world, state, thread, npc, friend = gated_town()
        stranger = {"id": "uzak", "name": "Uzak", "role": "usta", "location": "city"}
        world["npcs"].append(stranger)
        relationships.note(world, stranger["id"], 1, "test")
        self.assertEqual(world_threads.owner_mood(world, thread, npc), "wary")

    def test_having_worked_for_them_is_word_enough(self):
        world, state, thread, npc, friend = gated_town()
        relationships.note(world, npc["id"], 1, "test")
        self.assertEqual(world_threads.owner_mood(world, thread, npc), "yes")

    def test_they_say_where_a_word_would_have_to_come_from(self):
        world, state, thread, npc, friend = gated_town()
        thread.update(type="hiring", status="open")
        note = town_knowledge.speech_note(world, npc)
        self.assertIn(world["locations"][friend["location"]]["name"], note)
        self.assertNotIn(thread["owner_line"], note)

    def test_campaigns_differ_in_who_can_speak_for_you(self):
        picks = set()
        for number in range(30):
            world, state = town(f"seed-word-{number}")
            picks.add(tuple(vouching.chosen_kinds(world, state["threads"][0], "barracks")))
        self.assertGreater(len(picks), 2)
        for pick in picks:
            self.assertEqual(len(pick), 2)

    def test_a_town_where_nobody_could_speak_for_you_leaves_the_door_as_it_was(self):
        world, state, thread, npc, friend = gated_town()
        world["locations"][friend["location"]]["place_kind"] = "bakery"
        self.assertEqual(world_threads.owner_mood(world, thread, npc), "yes")

    def test_a_barracks_is_the_same_and_an_ordinary_shop_is_not(self):
        world, state, thread, npc, friend = gated_town(kind="barracks")
        self.assertEqual(world_threads.owner_mood(world, thread, npc), "wary")
        world["locations"][thread["place_id"]]["place_kind"] = "bakery"
        self.assertEqual(world_threads.owner_mood(world, thread, npc), "yes")


def walk(world, *, turns, hours=2, choose=None):
    """Turns of nothing but time, with an optional choice made on each. Read fresh: a tick replaces the state."""
    for turn in range(turns):
        if choose:
            choose(world, turn)
        campaign_time.advance(world, hours * HOUR, "wait", "test")
    return world[world_threads.KEY]


def outline(state):
    """What a run came to, with every name taken out."""
    rows = state["happenings"]
    chain = sorted(state["threads"] + state["history"], key=lambda t: t["thread_id"])
    return (tuple(t["template_id"] for t in chain), tuple(r["kind"] for r in rows),
            tuple(bool(r["next_thread_id"]) for r in rows))


class SameSeedDifferentStory(unittest.TestCase):
    def test_the_same_turns_twice_are_the_same_town(self):
        def run():
            world, _ = town_with_trouble(11)
            state = walk(world, turns=12)
            return state["happenings"], state["history"], world["flags"].get("deeds")
        self.assertEqual(run(), run())

    def test_taking_a_trouble_on_tells_a_different_story_from_leaving_it(self):
        def run(helping):
            world, state = town_with_trouble(11)
            thread = thread_at(state)
            npc = owner_of(world, thread)
            def choose(world, turn):
                if helping and turn == 0:
                    take_on(world, world_threads.by_id(world, thread["thread_id"]), npc)
                if helping and turn == 3:
                    world_threads._credit_day(world, world_threads.by_id(world, thread["thread_id"]), 1)
            state = walk(world, turns=12, hours=3, choose=choose)
            return ending(world, thread), [r["kind"] for r in state["happenings"]]
        helped, left = run(True), run(False)
        self.assertEqual(helped[0], ["averted"])
        self.assertIn(left[0][0], {"visit", "closed", "lost"})
        self.assertNotEqual(helped[1], left[1])

    def test_twenty_campaigns_are_not_one_skeleton_with_the_names_changed(self):
        shapes = set()
        for number in range(20):
            world, _ = town(f"seed-shape-{number}")
            shapes.add(outline(walk(world, turns=30)))
        self.assertGreaterEqual(len(shapes), 15)
        self.assertGreater(len({shape[1] for shape in shapes}), 8)

    def test_every_trouble_in_a_long_run_came_to_something(self):
        for number in range(12):
            world, _ = town(f"seed-end-of-it-{number}")
            state = walk(world, turns=30, hours=4)
            ended = {r["thread_id"] for r in state["happenings"]}
            for thread in state["history"]:
                if thread["type"] == "trouble":
                    self.assertIn(thread["thread_id"], ended)
            world_threads.validate(state)

    def test_nothing_in_a_long_run_is_a_deed(self):
        for number in range(8):
            world, _ = town(f"seed-no-deed-{number}")
            walk(world, turns=30, hours=6)
            self.assertFalse(world["flags"].get("deeds"))


class SayingYouWillIsNotYourName(unittest.TestCase):
    def test_a_first_person_verb_after_ben_is_no_name(self):
        for line in ("tamam ben hallederim", "bana düşmez, ben karışmayım", "ben yaparım", "ben bakayım", "ben giderim"):
            self.assertIsNone(local_dialogue.explicit_player_name_disclosure(line), line)

    def test_a_name_still_is(self):
        for line, name in (("ben Kerim", "Kerim"), ("ben Carius", "Carius"), ("ben Selim.", "Selim"), ("adım Tarım", "Tarım")):
            self.assertEqual(local_dialogue.explicit_player_name_disclosure(line), name)


class ASaveFromBefore(unittest.TestCase):
    def old_town(self):
        """A save as it stood: no ledger, no moments, an accepted trouble-shaped record among them."""
        world, state = town_with_trouble()
        del state["happenings"]
        for thread in state["threads"]:
            thread.pop("fires_at", None)
        thread = thread_at(state)
        thread.update(status="accepted", accepted_at=0, accepted_turn=1, work_until=9 * DAY, days_worked=0, type="hiring",
                      starts_at=0, shift_seconds=0, paid_cp=0)
        return world, state, thread

    def test_it_loads_gains_the_ledger_and_validates(self):
        world, state, _ = self.old_town()
        world_threads.validate(state)
        world_threads.ensure(world)
        self.assertEqual(world[world_threads.KEY]["happenings"], [])
        world_threads.validate(world[world_threads.KEY])

    def test_work_already_agreed_gets_no_clock_afterwards(self):
        world, state, thread = self.old_town()
        world_threads.ensure(world)
        world_threads.tick(world, 3 * DAY)
        self.assertNotIn("fires_at", world_threads.by_id(world, thread["thread_id"]))
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "accepted")

    def test_a_tick_on_it_needs_no_ensure_first(self):
        world, state, _ = self.old_town()
        world_threads.tick(world, 6 * DAY)
        world_threads.validate(world[world_threads.KEY])


class InPlay(unittest.IsolatedAsyncioTestCase):
    """The player's own loose words, the real turn, a scripted person."""

    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc
    open_job = gate_tests.ThreadTable.open_job
    line = gate_tests.ThreadTable.line
    status = gate_tests.ThreadTable.status

    async def trouble(self):
        await self.open_job(kind="trouble")
        self.thread.update(owner_line="Hesap tutmuyor, bakan biri lazım.", fires_at=2 * DAY, expires_at=2 * DAY,
                           public_line="Burada hesap tutmuyormuş.",
                           terms={"pay": None, "work_days": None, "pay_basis": None, "pay_timing": None, "deadline_text": None})
        world_threads.mark_heard(self.thread, 0)  # help is offered for something the player has heard of

    async def test_saying_you_will_help_takes_it_on(self):
        for line in ("derdini ben hallederim abi", "tamam yardım edeyim sana", "ben bakarım o işe usta", "yardımcı olurum merak etme"):
            await self.trouble()
            await self.line(line, "Sağ ol.", mode="say", target=True)
            self.assertEqual(self.status(), "accepted", line)
            self.assertNotIn("fires_at", self.thread)

    async def test_the_person_answers_it_as_an_offer_and_no_name_is_taken_from_it(self):
        await self.trouble()
        text = (await self.line("tamam ben hallederim", "Sağ ol, bekliyordum.", mode="say", target=True))["narration"]
        self.assertIn("Sağ ol, bekliyordum.", text)
        self.assertEqual(self.status(), "accepted")

    async def test_walking_to_a_place_in_town_takes_time(self):
        await self.trouble()
        place = next(r for r in self.world["locations"].values() if r.get("place_kind") and r["id"] != self.world["location"])
        before = world_threads._now(self.world)
        await self.line(f"{place['name']} tarafına gidiyorum", "Hmm.")
        self.assertEqual(self.world["location"], place["id"])
        self.assertEqual(world_threads._now(self.world) - before, 600)

    async def test_saying_you_will_not_takes_nothing_on(self):
        for line in ("yardım edemem kusura bakma", "derdin bana ne", "hallederim mi bilmem ama yardım etmem"):
            await self.trouble()
            await self.line(line, "Peki.", mode="say", target=True)
            self.assertIn(self.status(), world_threads.PUBLIC, line)

    async def test_asking_for_work_gets_the_trouble_told(self):
        await self.trouble()
        text = (await self.line("bana iş ver", "Hmm.", mode="say", target=True))["narration"]
        self.assertEqual(text.count("Hesap tutmuyor"), 1)
        self.assertEqual(self.status(), "offered")
        await self.line("tamam yaparım", "İyi.", mode="say", target=True)
        self.assertEqual(self.status(), "accepted")

    async def test_the_work_itself_ends_it_and_pays_nothing(self):
        await self.trouble()
        await self.line("yardım edeyim", "Sağ ol.", mode="say", target=True)
        purse = (self.world.get("currency") or {}).get("player")
        out = await self.line("hadi başlayalım", "Hmm.")
        self.assertEqual(out["turn_outcome"]["action"], "work")
        self.assertEqual(self.status(), "done")
        self.assertEqual((self.world.get("currency") or {}).get("player"), purse)
        self.assertEqual(ending(self.world, self.thread), ["averted"])
        self.assertNotIn("bakır", out["narration"])

    async def test_asking_for_money_gets_a_plain_no(self):
        await self.trouble()
        await self.line("yardım edeyim", "Sağ ol.", mode="say", target=True)
        self.world["flags"]["turn_index"] += 3
        await self.line("paramı ver", "Para yok.", mode="say", target=True)
        self.assertEqual(self.session._thread_turn["decision"], "pay_no_pay")
        self.assertEqual(self.status(), "accepted")


if __name__ == "__main__":
    unittest.main()
