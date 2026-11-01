"""Answering a job offer: the player's own words, read from lists, only after a shown, current offer."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import campaign_time
import relationships
import world_threads

HOUR = 3600


def offered(seed="offer", *, status="offered", kind="hiring", last="Yirmi bakır, iki gün. İster misin?"):
    world = {
        "location": "city",
        "locations": {"city": {"id": "city", "name": "Neverwinter", "type": "city", "scene_kind": "city"}},
        "npcs": [],
        "flags": {"turn_index": 3},
        "scene_state": {"campaign_seed": seed},
    }
    campaign_time.initialize(world)
    world_threads.ensure(world)
    thread = world[world_threads.KEY]["threads"][0]
    thread.update(status=status, type=kind, offered_at=0, offered_turn=3, offer_line=last,
                  terms={"pay": 20, "work_days": 2, "pay_basis": "total", "pay_timing": "end_of_day",
                         "deadline_text": "iki gün içinde"})
    if kind == "errand":
        thread["item_noun"] = "mektup"
    npc = {"id": "npc_owner", "name": "Kalila", "role": "Usta", "location": "city", "place_role_of": thread["place_id"]}
    world["npcs"].append(npc)
    world["npc_speech_log"] = {npc["id"]: [{"player": "iş var mı?", "npc": last}]}
    return world, thread, npc


class ClearAnswers(unittest.TestCase):
    def decide(self, line, **fields):
        world, thread, npc = offered(**fields)
        return world_threads.bind_player_decision(world, thread, line, npc)

    def test_a_yes_to_a_shown_offer_is_a_yes(self):
        for line in ("evet", "olur", "tamam", "tamam yaparım", "yaparım", "yapalım", "varım", "kabul", "anlaştık",
                     "Tamam.", "olur, ne zaman başlıyorum?", "tmm", "evett", "Teklifini kabul ediyorum",
                     "tamam kanka, teklifini kabul ettim", "hayır demiyorum, kabul ediyorum", "anlaştık dostum",
                     "işi alıyorum", "tamam tamam uzatmayalım. işi alıyorum. ne zaman başlıyorum?"):
            self.assertEqual(self.decide(line), "accepted", line)

    def test_a_no_to_a_shown_offer_is_a_no(self):
        for line in ("yok", "yok ya", "yok sağ ol", "hayır", "istemiyorum", "kalsın", "gerek yok", "ilgilenmiyorum",
                     "olmaz", "kabul etmiyorum", "kabul etmem", "bu işe girmem", "nah kabul ederim bu teklifi",
                     "yok, istemiyorum", "başkasını bul", "hayr", "pas"):
            self.assertEqual(self.decide(line), "declined", line)

    def test_a_word_inside_something_else_decides_nothing(self):
        for line in ("hadi oradan", "hadi ya", "hemen gitmem lazım", "tabii canım", "olur mu?", "tamam düşüneyim",
                     "olur olur diyorsun ama", "tamam mı diyeyim", "kabul etsem ne olur", "kabul ederim dedim mi",
                     "hayır demedim", "kabul etmiyor değilim", "vazgeçsem mi",
                     "bir düşüneyim", "bakarız", "olabilir", "sen bilirsin", "hmm", "aynen", "eyvallah", "anladım",
                     "teklife “tamam” dedi", "“kabul ediyorum” yazmış", "tamamen saçma", "olurdu belki",
                     "evet, hayır", "tamam, kalsın", "tamam, gitmem lazım", "peki ama nasıl"):
            self.assertIsNone(self.decide(line), line)

    def test_a_plain_yes_said_any_way_is_a_yes(self):
        for line in ("tamam dedim", "olur dedim", "tamam dedim sana", "tamam diyorum", "evet diyorum",
                     "\"tamam\" diyorum", "“tamam”", "peki tamam", "evet tamam", "abi tamam", "hadi tamam",
                     "kabul ettim", "kabul abi", "evet evet", "tamam abi olur"):
            self.assertEqual(self.decide(line), "accepted", line)

    def test_a_plain_no_said_any_way_is_a_no(self):
        for line in ("hayır dedim", "yok dedim sana", "abi yok", "yok hayır"):
            self.assertEqual(self.decide(line), "declined", line)

    def test_someone_else_s_words_or_an_old_answer_stay_nobody_s_decision(self):
        for line in ("ona tamam dedim", "dün tamam dedim", "tamam dedim ona", "teklife “tamam” dedi",
                     "“tamam” dedim ona", "tamam demiştim", "bir şey yok"):
            self.assertIsNone(self.decide(line), line)

    def test_a_yes_and_a_walk_with_no_comma_is_a_yes_and_a_walk(self):
        for line in ("tamam gidiyorum", "olur gidelim", "tamam oraya gidiyorum"):
            self.assertEqual(self.decide(line, kind="errand"), "accepted", line)
            self.assertTrue(world_threads.read_answer(line)["move"], line)

    def test_a_bare_word_before_a_question_on_something_else_decides_nothing(self):
        for line in ("peki, sen kimsin?", "peki, adın ne?", "tamam, kardeşin nasıl?", "evet, sen kimsin?",
                     "tamam, neden ben?", "hayır, sen kimsin?", "yok, sen kimsin?", "tamam, ailen nerede?"):
            self.assertIsNone(self.decide(line), line)

    def test_a_yes_with_a_question_about_the_work_is_a_yes(self):
        for line in ("olur, ne zaman başlıyorum?", "tamam, ne zaman?", "peki, nereden başlayayım?",
                     "tamam, nereye gideceğim?", "evet, bu iş kaç gün?", "olur, kime?"):
            self.assertEqual(self.decide(line), "accepted", line)
        self.assertEqual(self.decide("tamam, mektubu kime vereceğim?", kind="errand"), "accepted")

    def test_a_full_answer_stands_even_if_the_subject_changes(self):
        for line in ("tamam yaparım, adın ne senin?", "işi alıyorum, adın ne?"):
            self.assertEqual(self.decide(line), "accepted", line)
        self.assertEqual(self.decide("yok sağ ol, sen kimsin?"), "declined")

    def test_a_hanging_but_is_not_yet_a_yes(self):
        for line in ("olur ama", "olur ama...", "tamam ama...", "yaparım ama", "olur fakat"):
            self.assertIsNone(self.decide(line), line)

    def test_asking_about_the_money_leaves_the_offer_standing(self):
        for line in ("peki ne kadar veriyorsun", "önce parayı görelim", "olur ama önce parayı görelim",
                     "tamam da para ne zaman", "tamam da ne kadar", "ne kadar vereceksin", "ama peşin isterim",
                     "dokuz bakır mı? dalga mı geçiyosun", "ücret artarsa kabul ederim"):
            world, thread, npc = offered()
            self.assertEqual(world_threads.bind_player_decision(world, thread, line, npc), "questioning_terms", line)
            self.assertEqual(thread["status"], "offered")
            self.assertNotIn("currency", world)

    def test_a_shown_offer_is_also_how_the_list_binds_a_changed_mind(self):
        world, thread, npc = offered()
        self.assertEqual(world_threads.bind_player_decision(world, thread, "yok ya... neyse olur", npc), "accepted")


class OnlyAfterACurrentOffer(unittest.TestCase):
    def test_nothing_answers_a_job_nobody_offered(self):
        for status in ("open", "heard", "expired", "done"):
            world, thread, npc = offered(status=status)
            self.assertIsNone(world_threads.bind_player_decision(world, thread, "tamam", npc), status)

    def test_a_bare_yes_answers_the_last_question_not_an_old_offer(self):
        world, thread, npc = offered()
        world["npc_speech_log"][npc["id"]].append({"player": "hava soğuk", "npc": "Bir şey içer misin?"})
        self.assertIsNone(world_threads.bind_player_decision(world, thread, "olur", npc))

    def test_a_yes_that_names_the_work_still_binds(self):
        world, thread, npc = offered()
        world["npc_speech_log"][npc["id"]].append({"player": "hava soğuk", "npc": "Bir şey içer misin?"})
        self.assertEqual(world_threads.bind_player_decision(world, thread, "o işi yaparım", npc), "accepted")

    def test_an_offer_ending_on_another_question_does_not_take_a_bare_yes(self):
        world, thread, npc = offered(last="Yirmi bakır, iki gün. Bu arada adın ne senin?")
        self.assertIsNone(world_threads.bind_player_decision(world, thread, "olur", npc))

    def test_a_line_closing_the_offer_with_a_question_about_it_takes_a_bare_yes(self):
        for last in ("Yirmi bakır, iki gün. Yapar mısın?", "Yirmi bakır. Ne dersin?", "Yirmi bakır. Anlaştık mı?"):
            world, thread, npc = offered(last=last)
            self.assertEqual(world_threads.bind_player_decision(world, thread, "olur", npc), "accepted", last)


class AfterAYes(unittest.TestCase):
    def test_only_the_withdraw_list_ends_an_accepted_job(self):
        for line in ("vazgeçtim", "vazgeçiyorum", "bırakıyorum", "iptal", "bu işi yapamam", "bu anlaşmadan çekiliyorum",
                     "vazgeciyorum", "tamam demiştim ama vazgeçtim"):
            world, thread, npc = offered(status="accepted")
            self.assertEqual(world_threads.bind_player_decision(world, thread, line, npc), "abandoned", line)

    def test_small_talk_does_not_end_an_accepted_job(self):
        for line in ("Tamam.", "bugün gelemem", "şimdi konuşamam", "hayır", "aç çalışamam", "olmaz", "yok"):
            world, thread, npc = offered(status="accepted")
            self.assertIsNone(world_threads.bind_player_decision(world, thread, line, npc), line)

    def test_a_withdraw_word_on_an_unanswered_offer_is_a_refusal(self):
        world, thread, npc = offered()
        self.assertEqual(world_threads.bind_player_decision(world, thread, "vazgeçtim", npc), "declined")


class TurnedDown(unittest.TestCase):
    def test_a_refusal_shortens_the_window_and_can_be_taken_back(self):
        world, thread, npc = offered()
        self.assertTrue(world_threads.decline(world, thread, 4))
        self.assertEqual(thread["expires_at"], 6 * HOUR)
        self.assertEqual(world_threads.bind_player_decision(world, thread, "olur", npc), "accepted")

    def test_after_the_window_there_is_nothing_to_take_back(self):
        world, thread, npc = offered()
        world_threads.decline(world, thread, 4)
        tid = thread["thread_id"]
        world["campaign_time"]["elapsed_seconds"] = 7 * HOUR
        world_threads.tick(world, 7 * HOUR)
        late = world_threads.by_id(world, tid)
        self.assertIn(late["status"], {"filled_by_other", "expired"})
        self.assertIsNone(world_threads.bind_player_decision(world, late, "olur", npc))

    def test_a_refusal_keeps_a_later_day_short_of_the_original_end(self):
        world, thread, _ = offered()
        thread["expires_at"] = 2 * HOUR
        world_threads.decline(world, thread, 4)
        self.assertEqual(thread["expires_at"], 2 * HOUR)


class WhoWillOffer(unittest.TestCase):
    def test_someone_let_down_gives_no_more_work(self):
        world, thread, npc = offered()
        world["relationships"] = {}
        relationships.note(world, npc["id"], -1, "thread:old:failed")
        world[world_threads.KEY]["history"].append(
            dict(thread, thread_id="thread_900", status="failed", offered_at=0, closed_at=0))
        self.assertEqual(world_threads.owner_mood(world, thread, npc), "no")

    def test_a_grudge_with_no_broken_job_is_not_a_ban(self):
        world, thread, npc = offered()
        relationships.note(world, npc["id"], -1, "thread:old:quarrel")
        self.assertNotEqual(world_threads.owner_mood(world, thread, npc), "no")

    def test_some_owners_size_a_stranger_up_first_and_not_all_do(self):
        moods = set()
        for number in range(60):
            world, thread, npc = offered(f"mood-{number}")
            moods.add(world_threads.owner_mood(world, thread, npc, this_exchange=1))
        self.assertEqual(moods, {"yes", "wary"})

    def test_someone_they_have_spoken_with_is_no_stranger(self):
        for number in range(60):
            world, thread, npc = offered(f"mood-{number}")
            self.assertNotEqual(world_threads.owner_mood(world, thread, npc), "wary", number)


class OfferOpening(unittest.TestCase):
    def test_the_figure_counts_in_digits_and_in_words(self):
        for text, number in (("Teslim edene dokuz bakır var.", 9), ("Otuz sekiz bakır veririm.", 38), ("38 bakır", 38),
                             ("otuz sekize olur", 38), ("Ücret 20 bakır", 20), ("yirmi bakır", 20)):
            self.assertTrue(world_threads.names_number(text, number), text)

    def test_another_figure_does_not_count(self):
        for text, number in (("yüz seksen bakır", 8), ("Otuz bakır", 38), ("138 bakır", 38), ("onu al", 10),
                             ("otuz sekiz bakır", 8)):
            self.assertFalse(world_threads.names_number(text, number), text)

    def test_marking_records_the_terms_the_player_saw(self):
        world, thread, npc = offered(status="heard")
        self.assertTrue(world_threads.mark_offered(world, thread, npc, "Yirmi bakır, iki gün.", 7))
        self.assertEqual(thread["status"], "offered")
        self.assertEqual(thread["offered_terms_shown"]["pay"], 20)
        self.assertEqual(thread["offer_line"], "Yirmi bakır, iki gün.")
        self.assertEqual(thread["offered_turn"], 7)

    def test_the_answer_lists_are_copied_data_with_nothing_lost(self):
        root = Path(world_threads.__file__).resolve().parents[1]
        data = json.loads((root / "content" / "world" / "offer_answers.json").read_text(encoding="utf-8"))
        table = world_threads.answer_table()
        for section, name in (("kabul", "accept"), ("ret", "decline"), ("vazgeçme", "withdraw"), ("belirsizler", "unclear")):
            self.assertEqual(len(data[section]) >= 30, True)
            for entry in data[section]:
                self.assertIn(world_threads._folded(entry["expression"]), table[name])

    def test_every_listed_answer_reads_as_its_own_meaning(self):
        root = Path(world_threads.__file__).resolve().parents[1]
        data = json.loads((root / "content" / "world" / "offer_answers.json").read_text(encoding="utf-8"))
        for section, meaning in (("kabul", "accept"), ("ret", "decline"), ("vazgeçme", "withdraw")):
            for entry in data[section]:
                self.assertEqual(world_threads.read_answer(entry["expression"])["meaning"], meaning, entry["expression"])
        for entry in data["belirsizler"]:
            self.assertIsNone(world_threads.read_answer(entry["expression"])["meaning"], entry["expression"])


if __name__ == "__main__":
    unittest.main()
