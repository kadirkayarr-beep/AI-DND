"""Task 17: selected player words are bounded sources, never world facts."""
import copy
import json
import unittest
from unittest.mock import patch

import game
import npc_told
import economic_actions as ea
from api.core_resolution import resolution_action_scope
from api.tests import test_campaign_api as api
from api.tests import test_experimental_npc_dialogue as speech

FACT = "Benim köyüm Yeşilova, babam orada değirmenci."


class Sources(unittest.TestCase):
    def setUp(self):
        self.w = {}

    def keep(self, text=FACT, turn=1, npc="gezgin"):
        self.assertTrue(npc_told.remember(self.w, npc, text, turn=turn))

    def test_a_line_up_to_600_chars_is_kept_whole(self):
        text = "Sözüm " * 74 + "son. "
        self.keep(text)
        self.assertEqual(self.w["npc_told_v1"]["gezgin"], [{"turn": 1, "text": text}])

    def test_a_line_over_600_is_cut_at_a_word_and_marked(self):
        self.keep("kelime " * 100)
        row = self.w["npc_told_v1"]["gezgin"][0]
        self.assertTrue(row["cut"])
        self.assertEqual(row["text"], ("kelime " * 85).rstrip())
        self.assertEqual(npc_told.supports(self.w, "gezgin", "kelime", about="memory"), [])

    def test_a_detail_after_char_200_stays_in_the_source_and_the_view_says_shortened(self):
        text = "Uzun yolculuğum " * 17 + "ama bunu kimse bilmiyor."
        self.keep(text)
        self.assertEqual(self.w["npc_told_v1"]["gezgin"][0]["text"], text)
        self.assertIn("(kısaltıldı; tamamı kayıtta)", npc_told.view([text], header="H:"))
        self.assertEqual(npc_told.supports(self.w, "gezgin", "kimse bilmiyor", about="own_words"), [text])

    def test_forty_sources_per_npc_and_the_41st_drops_the_first(self):
        for i in range(41):
            self.keep(f"Anlatılan söz {i}", i)
        rows = self.w["npc_told_v1"]["gezgin"]
        self.assertEqual(len(rows), 40)
        self.assertEqual(rows[0]["text"], "Anlatılan söz 1")
        self.assertEqual(rows[-1]["text"], "Anlatılan söz 40")

    def test_the_33rd_npc_drops_the_longest_unwritten_and_logs_it(self):
        for i in range(32):
            self.keep(turn=i, npc=f"n{i}")
        self.keep(turn=32, npc="n0")
        with self.assertLogs("npc_told", level="INFO") as logs:
            self.keep(turn=33, npc="new")
        self.assertEqual(len(self.w["npc_told_v1"]), 32)
        self.assertNotIn("n1", self.w["npc_told_v1"])
        self.assertIn("n0", self.w["npc_told_v1"])
        self.assertIn("n1", " ".join(logs.output))

    def test_relevant_matches_word_stems_at_most_three(self):
        self.keep()
        self.assertEqual(npc_told.relevant(self.w, "gezgin", "Babamın ne iş yaptığını hatırlıyor musun?"), [FACT])
        for i in range(2, 6):
            self.keep(f"Babam değirmende çalışır {i}", i)
        self.assertEqual(npc_told.relevant(self.w, "gezgin", "babam"),
                         ["Babam değirmende çalışır 5", "Babam değirmende çalışır 4", "Babam değirmende çalışır 3"])
        self.assertEqual(npc_told.relevant(self.w, "other", "babam"), [])

    def test_supports_needs_a_real_overlap_and_an_uncut_row(self):
        self.keep()
        self.keep("Ejderhalar " * 100, 2)
        self.assertEqual(npc_told.supports(self.w, "gezgin", "orman", about="memory"), [])
        self.assertEqual(npc_told.supports(self.w, "gezgin", "ejderhalar", about="memory"), [])
        self.assertEqual(npc_told.supports(self.w, "other", "babam", about="own_words"), [])
        self.assertEqual(npc_told.supports(self.w, "gezgin", "babam", about="npc_words"), [])

    def test_context_rows_are_the_newest_three_and_never_support(self):
        for i in range(4):
            self.keep(f"Anılarım {i}", i)
        before = copy.deepcopy(self.w)
        self.assertEqual(npc_told.context_rows(self.w, "gezgin"), ["Anılarım 3", "Anılarım 2", "Anılarım 1"])
        self.assertEqual(npc_told.supports(self.w, "gezgin", "ejderha", about="memory"), [])
        self.assertEqual(self.w, before)

    def test_the_view_fits_600_bytes_with_header_and_quotes(self):
        rendered = npc_told.view(["ğüşıöç " * 29] * 3, header="Hafıza:")
        self.assertLessEqual(len(rendered.encode("utf-8")), 600)
        self.assertTrue(rendered.startswith("Hafıza:"))
        self.assertIn("«", rendered)
        self.assertIn("(kısaltıldı:", rendered)
        self.assertLessEqual(len(npc_told.view([FACT], header="ğ" * 500).encode("utf-8")), 600)

    def test_repair_drops_bad_rows_and_names_them(self):
        self.w["npc_told_v1"] = {"bad": [None, {"text": "x", "turn": True}],
                                 "many": [{"text": f"Söz {i}", "turn": i} for i in range(45)],
                                 "long": [{"text": "kelime " * 100, "turn": 50}]}
        changed = npc_told.repair(self.w)
        self.assertEqual(set(changed), {"bad", "many", "long"})
        self.assertEqual(len(self.w["npc_told_v1"]["many"]), 40)
        self.assertEqual(self.w["npc_told_v1"]["many"][0]["turn"], 5)
        self.assertTrue(self.w["npc_told_v1"]["long"][0]["cut"])
        self.assertEqual(npc_told.context_rows(self.w, "bad"), [])
        for i in range(33):
            self.w["npc_told_v1"][f"extra{i}"] = [{"text": FACT, "turn": i + 100}]
        self.assertIn("extra0", npc_told.repair(self.w))
        self.assertEqual(len(self.w["npc_told_v1"]), 32)


class Selection(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session(seed=7)
        self.w = self.s.world_state
        self.npc = {"id": "gezgin", "name": "Selim", "role": "resident", "current_hp": 12,
                    "status": "active", "location": self.w["location"],
                    "personal_profile": {"personal_detail": "GizliDeğer"}}
        self.w["npcs"] = [self.npc]
        self.w.setdefault("flags", {}).update(active_npc_id="gezgin", active_npc_until_turn=999)
        token = game._ACTIVE_SESSION.set(self.s)
        self.addCleanup(game._ACTIVE_SESSION.reset, token)
        guard = patch("game.ollama.chat", side_effect=AssertionError("No real model"))
        guard.start()
        self.addCleanup(guard.stop)

    def say(self, text=FACT, remember=True, npc="gezgin"):
        game._remember_experimental_npc_speech(npc, text, "Seni dinliyorum.", remember=remember)

    def test_a_question_a_claim_a_fight_or_a_private_value_is_not_kept(self):
        for text in ("Babamı biliyor musun?", "Sen bana dün kılıç vereceğini söylemiştin.", "GizliDeğer hakkında biliyorum"):
            with self.subTest(text=text):
                self.say(text)
                self.assertEqual(npc_told.context_rows(self.w, "gezgin"), [])
        self.w["combat"]["active"] = True
        self.say()
        self.assertEqual(npc_told.context_rows(self.w, "gezgin"), [])

    def test_only_the_living_present_addressee_can_keep_a_selected_line(self):
        for mutation in (lambda: self.npc.update(location="elsewhere"),
                         lambda: self.npc.update(current_hp=0, status="dead"),
                         lambda: self.w["flags"].update(active_npc_id="other")):
            before = copy.deepcopy(self.w)
            mutation()
            self.say()
            self.assertEqual(npc_told.context_rows(self.w, "gezgin"), [])
            self.w.clear(); self.w.update(before)
            self.npc = self.w["npcs"][0]
        for value in (False, None, "true", 1):
            self.say(remember=value)
        self.assertEqual(npc_told.context_rows(self.w, "gezgin"), [])
        self.say()
        self.assertEqual(npc_told.context_rows(self.w, "gezgin"), [FACT])

    def test_the_speech_note_carries_the_told_lines_in_plain_text(self):
        self.say()
        note = game._experimental_speech_note(self.w, self.npc, "known", "Babam nasıl?")
        self.assertIn("Oyuncunun sana daha önce söyledikleri (söylendi; doğruluğunu bilmezsin):", note)
        self.assertIn(FACT, note)


class ChoosingClient(speech.ScriptedNpcSpeechClient):
    def __init__(self, remember=True):
        super().__init__(narration="Seni dikkatle dinliyorum.")
        self.remember = remember

    def chat(self, *args, **kwargs):
        result = super().chat(*args, **kwargs)
        packet = json.loads(result["message"]["content"])
        packet["remember_player_line"] = self.remember
        result["message"]["content"] = json.dumps(packet, ensure_ascii=False)
        return result


class SpeechPath(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def say(self, url, npc, text=FACT, remember=True):
        client = ChoosingClient(remember)
        response = await api.CampaignApiTests.post_scene_turn(
            self, url, client, speech.ExperimentalNpcDialogueTests.request(npc, message=text))
        self.assertEqual(response.status_code, 200, response.text)
        return client

    async def test_twenty_five_talks_with_thirteen_kept_still_bring_back_the_first_fact(self):
        _, _, session, url, npc = await self.campaign_with_npc()
        for i in range(25):
            await self.say(url, npc, FACT if i == 0 else f"Yolculuğumdaki anı numarası {i}.", i % 2 == 0)
        rows = session.world_state["npc_told_v1"][npc["id"]]
        self.assertEqual(len(rows), 13)
        self.assertEqual(rows[0]["text"], FACT)
        client = await self.say(url, npc, "Babamın ne iş yaptığını hatırlıyor musun?", False)
        messages = "\n".join(m["content"] for batch in client.message_batches for m in batch)
        self.assertIn(FACT, messages)

    async def test_what_was_told_to_a_never_reaches_b(self):
        _, _, session, url, npc = await self.campaign_with_npc()
        await self.say(url, npc)
        world = session.world_state
        world["currency"] = {"player": 100, npc["id"]: 0}
        prepared = ea.prepare_from_turn(session, ea.turn_proposal("gift", npc["id"], amount_cp=5))
        self.assertEqual(prepared.status, "prepared")
        card = next(card for card in world["flags"]["economic_offers"].values() if card["status"] == "prepared")
        with resolution_action_scope("t17-isolation-payment", "t17-session"):
            paid = ea.confirm_offer(ea.EconomicState(world=world, character=session.character),
                offer_id=card["offer_id"], confirmation_digest=card["confirmation_digest"],
                operation_id="offer:t17-isolation-payment", check=lambda skill, dc: "BAŞARILI")
        self.assertEqual((paid.status, paid.net_debit_cp), ("applied", 5))
        self.assertEqual((world["currency"]["player"], world["currency"][npc["id"]]), (95, 5))
        # A leaves the scene: their public presence must not be confused with
        # a leak of private history through B's speech input.
        npc["location"] = "elsewhere"
        other = {"id": "yolcu", "name": "Nermin", "role": "resident", "location": session.world_state["location"], "current_hp": 12}
        session.world_state["npcs"].append(other)
        client = await self.say(url, other, "Babamın işini merak ediyor musun?", False)
        messages = "\n".join(m["content"] for batch in client.message_batches for m in batch)
        self.assertTrue(client.message_batches)
        for absent in (FACT, "Yeşilova", "değirmenci", "sana ödendi:", "5 bakır", npc["id"], npc["name"]):
            self.assertNotIn(absent, messages)

    async def test_same_named_npcs_in_two_campaigns_do_not_share(self):
        _, _, first, url, npc = await self.campaign_with_npc()
        await self.say(url, npc)
        _, _, second, url2, npc2 = await self.campaign_with_npc()
        client = await self.say(url2, npc2, "Babamı biliyor musun?", False)
        self.assertEqual(npc_told.context_rows(first.world_state, npc["id"]), [FACT])
        self.assertEqual(npc_told.context_rows(second.world_state, npc2["id"]), [])
        self.assertNotIn("Yeşilova", str(client.message_batches))

    async def test_a_gift_named_in_a_kept_line_changes_no_inventory(self):
        _, _, session, url, npc = await self.campaign_with_npc()
        world = session.world_state
        def physical():
            return copy.deepcopy((world.get("inventory"), world.get("currency"),
                                  [n.get("inventory") for n in world["npcs"]],
                                  world.get("flags", {}).get("economic_offers")))
        before = physical()
        line = "Kardeşim bana gümüş bir yüzük hediye etti."
        await self.say(url, npc, line)
        self.assertEqual(npc_told.context_rows(world, npc["id"]), [line])
        self.assertEqual(physical(), before)
