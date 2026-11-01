"""The line is understood and answered in the right voice: blows, stock lines, hands on people, bare walks, two parts.

Real app, real adapter, real engine; only the model client is scripted. The lines are the owner's own, as typed.
"""

from __future__ import annotations

from unittest.mock import patch

import game
import grounded_action
import interaction_adventure
import living_world
import npc_speech_boundary
from api.tests.test_front_proposal import FrontTable


class AnyBlowIsAnAttack(FrontTable):
    async def begin(self, **kwargs):
        await super().begin(**kwargs)
        self.npc.update(armor_class=10, max_hp=12, current_hp=12)  # what a person of the town really carries

    async def blow(self, line, **front):
        await self.begin()
        self.client.front = {"kind": "strike", "person_id": self.npc["id"], **front}
        return await self.line(line, "Ne yapıyorsun sen?")

    def assert_attacked(self, reply):
        self.assertEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertEqual(reply["turn_outcome"]["target_name"], self.npc["name"])
        self.assertTrue(self.world["combat"]["active"] or reply["combat_result"]["combat_status"] == "ended")
        self.assertEqual(self.routes()[-1]["route"], "front:strike")

    def assert_no_blow(self, reply):
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertFalse(self.world["combat"]["active"])
        self.assertNotIn("Nereden bileyim", reply["narration"])

    async def test_a_fist_is_an_attack_and_a_bare_one(self):
        reply = await self.blow("güldüm. ona bi yumruk çakıyorum, kılıç yok daha", thing_word="yumruk")
        self.assert_attacked(reply)
        self.assertEqual(reply["combat_result"]["weapon"], "Unarmed Strike")

    async def test_a_mug_in_the_face_is_an_attack_with_no_sword_in_it(self):
        reply = await self.blow("suratına bira bardağını geçiriyorum", thing_word="bira bardağı")
        self.assert_attacked(reply)
        self.assertEqual(reply["combat_result"]["weapon"], "Unarmed Strike")

    async def test_a_thrown_mug_is_an_attack_too(self):
        reply = await self.blow("elimdeki bardağı adamın kafasına fırlatıyorum", thing_word="bardak")
        self.assert_attacked(reply)
        self.assertEqual(reply["combat_result"]["weapon"], "Unarmed Strike")

    async def test_a_swung_sword_is_an_attack_with_the_sword(self):
        reply = await self.blow("savuruyorum, omzuna")
        self.assert_attacked(reply)
        self.assertNotEqual(reply["combat_result"]["weapon"], "Unarmed Strike")

    async def test_a_reading_with_no_name_in_it_means_the_one_being_spoken_to(self):
        await self.begin()
        self.client.front = {"kind": "strike"}
        reply = await self.line("şuna bi tane patlatıyorum")
        self.assert_attacked(reply)

    async def test_a_question_about_a_blow_strikes_nobody(self):
        self.assert_no_blow(await self.blow("ona bi tane vursam ne olur?"))

    async def test_a_threat_strikes_nobody_and_is_said_to_them(self):
        reply = await self.blow("bi daha bana bakarsan suratını dağıtırım")
        self.assert_no_blow(reply)
        self.assertIn("Ne yapıyorsun sen?", reply["narration"])
        reply = await self.line("dişlerini sökerim senin")
        self.assert_no_blow(reply)

    async def test_a_refused_blow_strikes_nobody(self):
        self.assert_no_blow(await self.blow("hayır ona yumruk atmıyorum, gerek yok"))

    async def test_a_blow_only_quoted_strikes_nobody(self):
        self.assert_no_blow(await self.blow('"sana bi yumruk atıyorum" diyorum gülerek'))

    async def test_a_person_nobody_listed_is_struck_by_nobody(self):
        await self.begin()
        self.client.front = {"kind": "strike", "person_id": "npc_nobody"}
        reply = await self.line("şuna bi tane patlatıyorum")
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack")

    async def test_the_reading_tells_the_model_what_a_blow_is(self):
        await self.begin()
        self.client.front = {"kind": "look"}
        await self.line("etrafa bakıyorum")
        self.assertIn("strike", self.front_calls()[0]["properties"]["front"]["properties"]["kind"]["enum"])
        self.assertIn("strike =", str(self.client.message_batches[0]))

    async def test_no_blow_is_left_behind_for_the_next_turn(self):
        await self.blow("ona bi yumruk çakıyorum, kılıç yok daha", thing_word="yumruk")
        self.assertFalse(getattr(self.session, "_front_strike", None))


class StockLinesNeverAnswerAPerson(FrontTable):
    MOUTH = "hâlâ aynı yerdesin"

    async def said(self, line, reply="", **front):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], **front}
        return await self.line(line, reply)

    def assert_a_person_spoke(self, reply):
        text = reply["narration"]
        self.assertIsNone(game._SCENE_LEVEL_FALLBACK_RE.search(text), text)
        self.assertIn(living_world.public_npc_name(self.npc), text)

    def stock_owner(self, stock):
        def owner(*args, **kwargs):
            return {"messages": self.session.messages, "narration": stock, "model_calls": 0,
                    "action_result": {"action": "narrative", "status": "resolved", "success": True,
                                      "state_changes": [], "direct_response": stock}}
        return owner

    async def test_saying_i_am_here_to_a_person_is_not_told_where_you_are(self):
        reply = await self.said("selam, carius ben. eski askerim, efendinin kılıç işi varsa ben buradayım")
        self.assert_a_person_spoke(reply)
        self.assertNotIn(self.MOUTH, reply["narration"])

    async def test_asking_a_person_for_work_is_not_told_what_lies_around(self):
        reply = await self.said("senin belgen mi? bana iş ver hallederim")
        self.assert_a_person_spoke(reply)
        self.assertNotIn("diye bir şey göremiyorsun", reply["narration"])

    async def test_a_claim_about_where_you_stand_leaves_the_person_their_own_words(self):
        reply = await self.said("efendin varsa söyle ben buradayım", "Efendim bugün kimseyi görmüyor.")
        self.assertIn("Efendim bugün kimseyi görmüyor.", reply["narration"])
        self.assertEqual(reply["turn_outcome"]["action"], "dialogue")

    async def test_a_quoted_joke_read_as_a_deed_is_still_said_to_the_person(self):
        await self.begin()
        self.client.front = {"kind": "attempt"}
        reply = await self.line('"sakin ol, sandık tuzak olabilir diye baktım" diyip sırıtıyorum', "Tuzakmış, yürü git.")
        self.assertIn("Tuzakmış, yürü git.", reply["narration"])
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")

    async def test_a_quote_beside_a_listed_door_keeps_the_hand_on_the_door(self):
        await self.begin()
        door = {"id": "door_voice_test", "name": "Mavi Kapak", "description": "Mavi bir kapak",
                "location": self.world["location"], "open": False, "locked": False, "broken": False}
        self.world.setdefault("doors", []).append(door)
        self.client.front = {"kind": "attempt", "thing_id": door["id"]}
        reply = await self.line('"açıl" diyip mavi kapağa yaklaşıyorum')
        self.assertIn("Mavi Kapak", reply["narration"])

    async def test_a_stock_line_from_any_owner_is_turned_into_the_person_at_the_door(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        stock = game._GENERIC_NO_CHANGE_RESPONSE
        real = game._dispatch_player_turn
        modes = []

        def owner(*args, **kwargs):
            modes.append(args[7] if len(args) > 7 else kwargs.get("interaction_mode"))
            return self.stock_owner(stock)() if len(modes) == 1 else real(*args, **kwargs)

        with patch("game._dispatch_player_turn", owner):
            reply = await self.line("sana diyorum, burda ne dönüyor", "Benden uzak dur, derim.")
        self.assertIn("Benden uzak dur, derim.", reply["narration"])
        self.assertNotIn(stock, reply["narration"])
        self.assertEqual(modes[1:], ["say"])

    async def test_a_stock_line_with_no_call_left_is_the_person_too(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        stock = "Marek, “Çevrede şimdilik belirgin bir değişiklik olmuyor.”"
        with patch("game._dispatch_player_turn", self.stock_owner(stock)), \
                patch("api.ollama_adapter.model_calls_left", return_value=0):
            reply = await self.line("sakin ol ya, şaka yaptım")
        self.assert_a_person_spoke(reply)
        self.assertNotIn("Nereden bileyim", reply["narration"])

    async def test_a_look_at_the_scene_keeps_the_scene_voice(self):
        await self.begin()
        self.client.front = {"kind": "look"}
        stock = game._GENERIC_NO_CHANGE_RESPONSE
        with patch("game._dispatch_player_turn", self.stock_owner(stock)):
            reply = await self.line("etrafa bakıyorum")
        self.assertEqual(reply["narration"], stock)

    async def test_a_blow_the_reading_missed_never_gets_an_i_do_not_know(self):
        await self.begin()
        self.client.front = {"kind": "attempt"}
        reply = await self.line("güldüm. ona bi yumruk çakıyorum, kılıç yok daha", "")
        self.assertNotIn("Nereden bileyim", reply["narration"])
        for line in interaction_adventure._UNKNOWN_LINES:
            self.assertNotIn(line.format(n=living_world.public_npc_name(self.npc)), reply["narration"])

    def test_i_do_not_know_answers_a_question_and_nothing_else(self):
        npc = {"id": "npc_a", "name": "Veyra"}
        unknown = {line.format(n="Veyra") for line in interaction_adventure._UNKNOWN_LINES}
        for line in ("efendin nerde", "soylu tanıyor musun", "kim yazdı bunu?"):
            self.assertIn(interaction_adventure.immersive_unknown(npc, line), unknown, line)
        for line in ("sakin ol ya", "omzunu itiyorum", "ver şu parayı artık"):
            self.assertNotIn(interaction_adventure.immersive_unknown(npc, line), unknown, line)

    def test_a_person_may_use_one_word_of_the_players_quote(self):
        line = '"sakin ol, sahipsiz sandık düşman tuzağı olabilir diye kontrol ediyordum" diyip sırıtıyorum'
        kept = "Burada ne sandık var ne de asker ocağı, tezgâhın önünü kapatıyorsun."
        self.assertEqual(npc_speech_boundary.strip_player_echo(kept, line), kept)
        said_back = "Sahipsiz sandık düşman tuzağı olabilir, doğru."
        self.assertEqual(npc_speech_boundary.strip_player_echo(said_back, line), "")


class AHandOnAPersonBeatsTheFurniture(FrontTable):
    BLOCKED = "açılacak bir şey değil"
    LINE = "yakasına yapışıp tezgaha bastırıyorum, korkutarak konuşturmaya çalışıyorum"

    async def begin(self, **kwargs):
        await super().begin(**kwargs)
        self.bench = {"id": "feature_voice_bench", "name": "Çalışma tezgâhı", "description": "Talaş dolu bir tezgâh",
                      "location": self.world["location"], "kind": "furnishing", "aliases": ["tezgah"]}
        self.world.setdefault("features", []).append(self.bench)

    async def test_the_person_answers_a_hand_on_their_collar(self):
        await self.begin()
        self.client.front = {"kind": "grab", "person_id": self.npc["id"]}
        reply = await self.line(self.LINE, "Çek ellerini!")
        self.assertIn("Çek ellerini!", reply["narration"])
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")

    async def test_a_reading_that_took_the_bench_is_corrected_by_the_collar(self):
        await self.begin()
        self.client.front = {"kind": "attempt", "thing_id": self.bench["id"]}
        reply = await self.line(self.LINE, "Çek ellerini!")
        self.assertNotIn(self.BLOCKED, reply["narration"])
        self.assertIn("Çek ellerini!", reply["narration"])

    async def test_no_reading_at_all_still_leaves_the_bench_alone(self):
        await self.begin()
        self.client.fails = RuntimeError("dead")
        reply = await self.line(self.LINE, "Çek ellerini!")
        self.assertNotIn(self.BLOCKED, reply["narration"])

    async def test_my_own_hand_on_the_bench_is_about_the_bench(self):
        await self.begin()
        self.assertFalse(grounded_action.hands_on_a_body("elimi tezgaha bastırıyorum"))
        self.assertFalse(grounded_action.hands_on_a_body("kolumu tezgaha dayıyorum"))

    async def test_the_handle_of_a_door_is_no_arm(self):
        await self.begin()
        self.assertFalse(grounded_action.hands_on_a_body("kapının kolunu çeviriyorum"))

    def test_the_ways_a_person_is_held(self):
        for line in ("gırtlağına yapışıp duvara dayıyorum", "omzundan tutup masaya bastırıyorum",
                     "kolunu büküp tezgaha yapıştırıyorum", "adamın boğazını sıkıyorum", "saçından tutup kapıya itiyorum"):
            self.assertTrue(grounded_action.hands_on_a_body(line), line)

    async def test_the_reading_tells_the_model_what_a_hand_on_a_person_is(self):
        await self.begin()
        self.client.front = {"kind": "look"}
        await self.line("etrafa bakıyorum")
        self.assertIn("grab", self.front_calls()[0]["properties"]["front"]["properties"]["kind"]["enum"])
        self.assertIn("grab =", str(self.client.message_batches[0]))
