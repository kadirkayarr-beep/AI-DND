"""The bound-session wrapper filter reads an explicit list of part modules (game.py split, T2.1)."""
import ast
import dataclasses
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import game  # noqa: E402
import local_dialogue  # noqa: E402
from api.auth import FixedAuthenticator  # noqa: E402
from api.main import create_app  # noqa: E402
from api.narrative_director import install_narrative_context_adapter, narrative_turn_context  # noqa: E402
from api.narrative_memory import empty_narrative_memory  # noqa: E402
from api.session_manager import SessionManager  # noqa: E402
from api.tests import test_campaign_api as campaign_api  # noqa: E402
from api.tests import test_front_proposal as front_tests  # noqa: E402
from api.tests import test_heard_rumours_turn as rumour_turn  # noqa: E402
from api.tests import test_local_person_persistence as local_person  # noqa: E402
from api.tests import test_thread_gate as thread_gate_tests  # noqa: E402
from api.tests.auth_fixture import TEST_PLAYER  # noqa: E402
from api.tests.engine_sources import batch_names, engine_source_files  # noqa: E402
from api.tests.guard_bound import CHILD_PROCESS, guard_bound  # noqa: E402
from api.tests.town_seed import fixed_town  # noqa: E402
from engine_split import routing_audit  # noqa: E402

TABLES = tuple(batch_names("tables"))
SCHEMAS = tuple(batch_names("schemas"))
TEXT_A1 = tuple(batch_names("text-a1"))
TEXT_A2 = tuple(batch_names("text-a2"))
TEXT_B1 = tuple(batch_names("text-b1"))
TEXT_B2 = tuple(batch_names("text-b2"))


def _canonical(value):
    """A form of a table value that is the same in every process (repr of a set of str is not: hash seed order).

    set/frozenset -> sorted list, dict -> same order (str keys only), tuple/list -> list, compiled regex ->
    [pattern, flags without the UNICODE bit re adds to every str pattern], frozen dataclass instance (EffectSpec)
    -> [class name, [[field, value] ...] in declaration order]; any other type raises TypeError naming it.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (set, frozenset)):
        return sorted(_canonical(item) for item in value)
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError(f"_canonical: dict key of type {sorted({type(k).__name__ for k in value})}")
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, re.Pattern):
        return [value.pattern, value.flags & ~re.UNICODE.value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return [type(value).__qualname__,
                [[field.name, _canonical(getattr(value, field.name))] for field in dataclasses.fields(value)]]
    raise TypeError(f"_canonical: no digest form for type {type(value).__name__}")


def value_digest(names) -> str:
    """sha256 of the canonical values of game.<name> for names, in name order (Tasks 9-14 pin one per batch)."""
    pairs = [[name, _canonical(getattr(game, name))] for name in sorted(names)]
    return hashlib.sha256(json.dumps(pairs, ensure_ascii=False).encode("utf-8")).hexdigest()


class WrapperFilter(unittest.TestCase):
    def test_the_wrapper_filter_reads_an_explicit_part_list(self):
        self.assertEqual(game._PART_MODULES, ("game_parts.character_rules", "game_parts.coin",
                                              "game_parts.combat_flow", "game_parts.dialogue", "game_parts.intent",
                                              "game_parts.living_world_turn", "game_parts.lore", "game_parts.narration",
                                              "game_parts.narration_safety", "game_parts.new_game", "game_parts.places",
                                              "game_parts.savefile", "game_parts.text_rules_a",
                                              "game_parts.text_rules_b", "game_parts.turn", "game_parts.turn_front"))
        # Task 18 (pilot a), Task 19 (pilot b), Plan 2 Task 13, Plan 3 Tasks 8, 9, 10, 11, 12, 13, 14 and 15,
        # Plan 4 Tasks 7, 8 and 9, Plan 5 Tasks 6 and 9
        tree = ast.parse(engine_source_files()[0].read_text(encoding="utf-8"))
        assign = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "_ENGINE_FUNCTIONS")
        self.assertIn("_PART_MODULES", {n.id for n in ast.walk(assign) if isinstance(n, ast.Name)})


class PilotRollD20(unittest.TestCase):
    """Pilot (a): roll_d20 lives in game_parts/character_rules.py and still behaves as an engine function."""

    def test_a_moved_function_still_binds_the_session_it_is_given(self):
        with fixed_town(self, 20261120):
            s = game.create_session(seed=5)
            default_state = game._session().rng.getstate()
            before = s.rng.getstate()
            value = game.roll_d20(session=s)
            self.assertIn(value, range(1, 21))
            self.assertNotEqual(s.rng.getstate(), before)
            self.assertEqual(game._session().rng.getstate(), default_state)
        self.assertTrue(game.roll_d20._session_bound)
        self.assertEqual(game.roll_d20.__module__, "game_parts.character_rules")

    def test_a_part_reads_engine_names_through_game(self):
        fake = MagicMock()
        fake.rng.randint.return_value = 7
        with patch.object(game, "_session", return_value=fake):
            self.assertEqual(game.roll_d20.__wrapped__(), 7)  # the part's own function, without the session wrapper
        fake.rng.randint.assert_called_once_with(1, 20)

    def test_a_patch_on_game_roll_d20_reaches_engine_callers(self):
        with fixed_town(self, 20261121):
            character = game._session().character
            with patch.object(game, "roll_d20", return_value=20) as rolled:
                result = game.perform_skill_check("Perception", 12, character["modifiers"],
                                                  character["proficient_skills"], character["proficiency_bonus"])
        rolled.assert_called()
        self.assertEqual(result["dice"], 20)

    @guard_bound(CHILD_PROCESS)
    def test_both_import_orders_work_in_a_fresh_interpreter(self):
        # Plan 3 Task 15: one function per new part (places, intent, dialogue, lore, narration, narration_safety,
        # living_world_turn, new_game); Plan 4 Task 7: combat_flow; Task 8: coin; Task 9: savefile; Plan 5 Task 6:
        # turn_front; Plan 5 Task 9: turn
        names = ("roll_d20", "_inside_speech", "_split_sentences_keep_speech", "_current_door", "validate_intent",
                 "resolve_npc_reference", "_is_registered_lore_name", "should_generate_npcs",
                 "_narration_safety_decision", "ensure_campaign_clock", "initialize_game", "ensure_death_state",
                 "_shop_presence_question", "save_game", "_thread_gate", "_dispatch_player_turn")
        show = "; ".join(f"print(game.{name}.__module__)" for name in names)
        for code in ("import game, game_parts; " + show, "import game_parts, game; " + show):
            done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
            self.assertEqual((done.returncode, done.stdout.split()),
                             (0, ["game_parts.character_rules", "game_parts.text_rules_a", "game_parts.text_rules_b",
                                  "game_parts.places", "game_parts.intent", "game_parts.dialogue", "game_parts.lore",
                                  "game_parts.narration", "game_parts.narration_safety",
                                  "game_parts.living_world_turn", "game_parts.new_game", "game_parts.combat_flow",
                                  "game_parts.coin", "game_parts.savefile", "game_parts.turn_front",
                                  "game_parts.turn"]),
                             done.stderr)


class PilotSpeechSpan(unittest.TestCase):
    """Pilot (b): _SPEECH_SPAN_RE and its pure reader _inside_speech live in game_parts/text_rules_a.py."""

    def test_the_constant_is_one_object_under_both_names(self):
        # no test imports game_parts (N3 R2): reach the part's namespace through the unwrapped helper
        self.assertIs(game._SPEECH_SPAN_RE, game._inside_speech.__wrapped__.__globals__["_SPEECH_SPAN_RE"])

    def test_the_helper_gives_the_same_answers_as_before(self):
        # inputs from test_ownerless_shop's speech tests; expected values captured on 5da99a42 before the move
        cases = (("Bir dükkâncı: “Özpil konakta olur, Marek sana bir iş verir.”", "Marek", True),
                 ("Tezgâhın ardında Marek yaklaşır.", "Marek", False),
                 ("Özpil, “Hoş geldin, yolcu.” der.", "Hoş", True))
        for text, word, expected in cases:
            with self.subTest(text=text, word=word):
                self.assertIs(game._inside_speech(text, text.index(word)), expected)

    def test_the_helper_is_session_bound_and_lives_in_the_part(self):
        self.assertTrue(game._inside_speech._session_bound)
        self.assertEqual(game._inside_speech.__module__, "game_parts.text_rules_a")

    def test_the_reader_left_in_game_py_still_works(self):
        # _split_sentences_keep_speech reads _SPEECH_SPAN_RE through game (it moved to text_rules_b in Plan 2 Task 13;
        # the id is kept so TM2 does not count it LOST); expected value captured on 5da99a42
        text = "Kapı açıldı. “Dur! Kim var? Çık dışarı.” dedi muhafız. Sonra sustu."
        self.assertEqual(game._split_sentences_keep_speech(text),
                         ["Kapı açıldı.", "“Dur! Kim var? Çık dışarı.” dedi muhafız.", "Sonra sustu."])

    def test_the_speech_reader_lives_in_text_rules_b(self):
        self.assertEqual(game._split_sentences_keep_speech.__module__, "game_parts.text_rules_b")


class TablesPart(unittest.TestCase):
    """T3.1: the twenty data tables live in game_parts/tables.py; game.py re-exports them unchanged."""

    def test_the_digest_form_sorts_sets(self):
        self.assertEqual(_canonical({"b", "a", "c"}), ["a", "b", "c"])
        self.assertEqual(_canonical(frozenset({"y", "x"})), ["x", "y"])
        self.assertEqual(_canonical(re.compile("a", re.I)), ["a", re.I.value])
        self.assertEqual(_canonical(game.INNER_RADIANCE_SPEC),
                         ["EffectSpec", [["effect_id", "inner_radiance"], ["range_ft", 10],
                                         ["source_ref", "PHB 2024 p.185 (PDF) Aasimar: Inner Radiance"],
                                         ["excludes_allies", False]]])
        with self.assertRaisesRegex(TypeError, "object"):
            _canonical(object())

    def test_the_tables_live_in_the_part(self):
        self.assertEqual(set(TABLES) - set(routing_audit.re_exports(ROOT).get("tables", [])), set())

    def test_the_table_values_did_not_change(self):
        # captured on 714b3b0f before the move (slot Python 3.13; PYTHONHASHSEED=1 and =2 gave this same hex)
        self.assertEqual(value_digest(TABLES), "3fe2c4fd649ce85ff068164b70be9699701d63c784534753646e94a190f709eb")

    def test_a_patched_class_table_reaches_the_api_reader(self):
        # GET /api/character-options (api/main.py character_creation_options) reads game.CLASSES at call time
        app = create_app(session_manager=SessionManager(), ollama_adapter=None,
                         authenticator=FixedAuthenticator(TEST_PLAYER))
        reader = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/character-options")
        with patch("game.CLASSES", ["Wizard"]):
            self.assertEqual(reader()["classes"], ["Wizard"])


class SchemasPart(unittest.TestCase):
    """T3.2: the schema and prompt constants live in game_parts/schemas.py; game.py re-exports them unchanged."""

    def test_the_schemas_live_in_the_part(self):
        self.assertEqual(set(SCHEMAS) - set(routing_audit.re_exports(ROOT).get("schemas", [])), set())

    def test_the_schema_values_did_not_change(self):
        # captured on 7240d31c before the move, batch without the held _EXPERIMENTAL_NPC_SPEECH_SCHEMA and
        # _EXPERIMENTAL_NPC_SPEECH_OPTIONS (slot Python 3.13; PYTHONHASHSEED=1 and =2 gave this same hex)
        self.assertEqual(value_digest(SCHEMAS), "bcd588f6fa318cc64ed3b88ab1dc7786e8bb5b364ca37bdbd7150288ceaea97f")

    def test_the_system_prompt_is_one_object_for_module_and_sessions(self):
        self.assertIs(game.messages[0]["content"], game.system_prompt)
        with fixed_town(self, 20261121):
            s = game.create_session(seed=7)
            self.assertIs(s.messages[0]["content"], game.system_prompt)  # GameSession.__init__ seeds it (D-380)

    def test_the_npc_speech_options_live_in_schemas(self):
        self.assertIn("_EXPERIMENTAL_NPC_SPEECH_OPTIONS", routing_audit.re_exports(ROOT).get("schemas", ()))

    def test_the_npc_speech_options_did_not_change(self):
        # captured on f5cbace6 before the move (slot Python 3.13; PYTHONHASHSEED=1 and =2 gave this same hex)
        self.assertEqual(value_digest(("_EXPERIMENTAL_NPC_SPEECH_OPTIONS",)),
                         "6b73f273148a6af846bf9cfbeab27fcb438259f54666d1eaf1e810388a7a7b49")

    def test_the_npc_speech_schema_lives_in_schemas(self):  # Plan 4 T5.4a
        self.assertIn("_EXPERIMENTAL_NPC_SPEECH_SCHEMA", routing_audit.re_exports(ROOT).get("schemas", ()))

    def test_the_npc_speech_schema_did_not_change(self):
        # captured on 0b1dca5a before the move with p4t10-capture.py (slot Python 3.13; PYTHONHASHSEED=1 and =2 gave
        # this same hex)
        self.assertEqual(value_digest(("_EXPERIMENTAL_NPC_SPEECH_SCHEMA",)),
                         "1cdfc93bed84fd11110e13f2996b79e1975082c19cab463bb2dcaa85585c1900")


class TextA1Part(unittest.TestCase):
    """T3.3 batch text-a1: text helpers and regexes live in game_parts/text_rules_a.py; game.py re-exports them."""

    def test_text_a1_lives_in_the_part(self):
        self.assertEqual(set(TEXT_A1) - set(routing_audit.re_exports(ROOT)["text_rules_a"]), set())

    def test_text_a1_helpers_answer_as_before(self):
        # inputs from each helper's existing tests (test_ai_pipeline_port, test_lr00_p1_intent, test_dilim3d_small,
        # test_narration_proposal_marker) or, for _drop_repeated_sentences, strings its split regex matches;
        # expected values captured on 26f93dfd before the move (slot Python 3.13)
        cases = (
            (game.clean_dm_response,
             ("<think>plan</think>```json\nKapı gıcırdayarak açılır.\nDC 12 zar sonucu 9\n1. Kaç\n- Saklan\n"
              "Hangisini seçersin?\nİçerisi karanlık.```",),
             "Kapı gıcırdayarak açılır.\nİçerisi karanlık."),
            (game.clean_dm_response,
             ("Odun dumanı hafifçe havaya karışır.\n\n\nAlçak konuşmalar uğultu oluşturur.\nNe yaparsın?",),
             "Odun dumanı hafifçe havaya karışır.\nAlçak konuşmalar uğultu oluşturur."),
            (game._affirmative_door_verb, ("kapiyi kirmaya calisiyorum", r"kapiyi\s+", ("kir",)), True),
            (game._affirmative_door_verb, ("kapiyi kirmayacagim", r"kapiyi\s+", ("kir",)), False),
            (game._reads_english, ("A chest on the bench",), True),
            (game._reads_english, ("Tezgâhta the sandık",), False),
            (game._strip_proposal_markers, ("[[n1]]Marek, [[l2]]arşiv, [[f12]]kapı [[s1]]dükkân [not] [[x1]]",),
             "Marek, arşiv, kapı dükkân [not] [[x1]]"),
            (game._strip_proposal_markers, (None,), None),
            (game._drop_repeated_sentences,
             ("Kapı açıldı. Rüzgâr esti. Bir köpek havladı.", ["Rüzgâr esti. Sessizlik."]),
             "Kapı açıldı. Bir köpek havladı."),
            (game._drop_repeated_sentences, ("Kapı açıldı. Rüzgâr esti.", ["Kapı açıldı. Rüzgâr esti."]),
             "Kapı açıldı. Rüzgâr esti."),
        )
        for helper, args, expected in cases:
            with self.subTest(helper=helper.__name__, args=args):
                self.assertEqual(helper(*args), expected)

    def test_a_moved_text_helper_still_takes_a_session(self):  # spec §6: session binding survives the move
        # real claim: the moved helper is still wrapped as an engine function (it accepts session= and is marked
        # _session_bound); a pure helper answers the same either way, so the binding proof stays with PilotRollD20
        with fixed_town(self, 20261122):
            s = game.create_session(seed=9)
            self.assertEqual(game._strip_proposal_markers("a", session=s), game._strip_proposal_markers("a"))
        self.assertTrue(game._strip_proposal_markers._session_bound)

    def test_a_patch_on_a_moved_helper_reaches_its_caller_in_game_py(self):
        # test_talk_front patches game._topic_place_name; its caller _run_player_turn_internal stays in game.py
        # and reads the module global at call time (flag off: no front reading, the name line answers)
        self.enterContext(patch.dict(os.environ))
        os.environ.pop("AI_DND_FRONT_PROPOSAL", None)
        with fixed_town(self, 20261123):
            s = game.create_session(seed=9)
            with patch.object(game, "_topic_place_name", return_value="X") as named:
                result = game.run_player_turn("Peki oranın adı ne?", session=s)
        named.assert_called_once()
        self.assertEqual(result["narration"], "Adı X.")


class TextA2Part(unittest.TestCase):
    """T3.4 batch text-a2: more text helpers and regexes live in game_parts/text_rules_a.py; game.py re-exports them."""

    def test_text_a2_lives_in_the_part(self):
        self.assertEqual(set(TEXT_A2) - set(routing_audit.re_exports(ROOT)["text_rules_a"]), set())

    def test_text_a2_helpers_answer_as_before(self):
        # inputs carry Turkish letters, curly quotes, emoji and an unclosed JSON object;
        # expected values captured on 19a181d8 before the move (slot Python 3.13)
        cases = (
            (game._fold_keep_punctuation, ("İstanbul’un KAPISI`nda Dükkâncı",), "istanbulun kapisinda dukkanci"),
            (game._fold_keep_punctuation, ("Şükrü'nün ÇIRAĞI, hâlâ orada!",), "sukrunun ciragi, hala orada!"),
            (game._extract_json_object,
             ('<think>plan</think>```json\n{"say": "“Selam,” dedi {köşede}", "list": [1, {"a": "çiğ"}',),
             {"say": "“Selam,” dedi {köşede}", "list": [1, {"a": "çiğ"}]}),
            (game._extract_json_object, ('Önce söz: {"a": "x\\"y", "b": [2, 3]} sonra artık }',),
             {"a": 'x"y', "b": [2, 3]}),
            (game._strip_pictographs, ("Selam 👋🏽 dostum ❤️ nasılsın?",), "Selam  dostum  nasılsın?"),
            (game._strip_pictographs, ("“Çarşı açık” ✨ dedi‍ ☕",), "“Çarşı açık”  dedi "),
            (game._normalize_turkish_typos, ("Dükkâncı’ya GİT, şimdi!",), "dukkanci ya git simdi"),
            (game._normalize_turkish_typos, ("  Kâtip'in   ÇIRAĞI?  “Işık” ",), "katip in ciragi isik"),
            (game._without_real_world_faith, ("Aleyküm selam. İnşallah yarın gelirim.",),
             "Selam. Tanrılar izin verirse yarın gelirim."),
            (game._without_real_world_faith, ("“Maşallah,” dedi. Allah’a emanet ol, elhamdülillah!",),
             "“Vay be,” dedi. Tymora yar olsun, tanrılara şükür!"),
        )
        for helper, args, expected in cases:
            with self.subTest(helper=helper.__name__, args=args):
                self.assertEqual(helper(*args), expected)


class TextB1Part(unittest.TestCase):
    """T3.5 batch text-b1: lore and narration text helpers live in game_parts/text_rules_b.py; game.py re-exports them."""

    def test_text_b1_lives_in_the_part(self):
        self.assertEqual(set(TEXT_B1) - set(routing_audit.re_exports(ROOT).get("text_rules_b", [])), set())

    def test_text_b1_helpers_answer_as_before(self):
        # inputs carry Turkish letters and curly quotes; expected values captured on 86bdd45a before the move
        # (slot Python 3.13)
        cases = (
            (game._split_sentences_keep_speech,
             ("Muhafız bağırdı: “Dur! Kim var orada? Çık dışarı.” Sonra İlkay güldü. Şükrü sustu…",),
             ["Muhafız bağırdı: “Dur! Kim var orada? Çık dışarı.” Sonra İlkay güldü.", "Şükrü sustu…"]),
            (game._split_sentences_keep_speech,
             ("Kâtip: “Defter kapandı. Yarın gel!” dedi! Çarşı boşaldı?  Işıklar söndü.",),
             ["Kâtip: “Defter kapandı. Yarın gel!” dedi!", "Çarşı boşaldı?", "Işıklar söndü."]),
            (game._unseen_speakers,
             ("Marek yaklaşır ve tezgâha eğilir. Şükrü: “Hoş geldin, yolcu.”",
              {"marek": "Marek Özpil", "şükrü": "Şükrü"}),
             [(0, 5), (34, 39)]),
            (game._unseen_speakers,
             ("Özpil, “Marek yaklaşır sanma.” der. Özpil Marek yaklaşır.", {"marek": "Özpil Marek"}), [(36, 47)]),
            (game._lore_guard_text, ("Kral’ın Şövalyesi IŞIK Çarşısı'nda, 1492 DR’de “öldü”.",),
             "kral sovalyesi isik carsisi 1492 dr oldu"),
            (game._lore_guard_text, ("  Özgür Ağa'nın gölgesi, Çiğdem’s Inn!  ",), "ozgur aga golgesi cigdem inn"),
            (game._is_generic_speaker_label, ("Yakındaki kişi",), True),
            (game._is_generic_speaker_label, ("  bir yaşlı kadın ",), True),
            (game._is_generic_speaker_label, ("Kapıdaki uzun boylu biri",), True),
            (game._is_generic_speaker_label, ("Marek Özpil",), False),
            (game._is_generic_speaker_label, ("Bir “muhafız”",), False),
        )
        for helper, args, expected in cases:
            with self.subTest(helper=helper.__name__, args=args):
                self.assertEqual(helper(*args), expected)
        salvage = (
            ({"interaction": {"operation": "none", "conversation": {"meaning": "other", "topic": "hava"}},
              "narration": "Özpil: “Hoş geldin.”"},
             True, {"interaction": {"operation": "none", "conversation": None}, "narration": "Özpil: “Hoş geldin.”"}),
            ({"interaction": {"operation": None, "conversation": {"meaning": "identity"}},
              "narration": "“Ben kimim?” diye sorar."},
             False, {"interaction": {"operation": None, "conversation": {"meaning": "identity"}},
                     "narration": "“Ben kimim?” diye sorar."}),
            ({"interaction": {"operation": "trade", "conversation": None}, "narration": "“Şu kılıcı al.”"},
             False, {"interaction": {"operation": "trade", "conversation": None}, "narration": "“Şu kılıcı al.”"}),
            ({"interaction": {"operation": "none", "conversation": None}, "narration": "   "},
             False, {"interaction": {"operation": "none", "conversation": None}, "narration": "   "}),
            ("düz metin", False, "düz metin"),
        )
        for raw, expected, after in salvage:
            with self.subTest(helper="_salvage_plain_speech", after=after):
                self.assertIs(game._salvage_plain_speech(raw), expected)
                self.assertEqual(raw, after)


class TextB2Part(unittest.TestCase):
    """T3.6 batch text-b2: narration and combat-text helpers live in game_parts/text_rules_b.py; game.py re-exports them."""

    def test_text_b2_lives_in_the_part(self):
        self.assertEqual(set(TEXT_B2) - set(routing_audit.re_exports(ROOT)["text_rules_b"]), set())

    def test_text_b2_helpers_answer_as_before(self):
        # inputs carry Turkish letters and curly quotes; expected values captured on 1c1c820b before the move
        # (slot Python 3.13)
        cases = (
            (game._trim_dangling_quote, ("…alırız.’ Fırın kokusu çarşıyı sarar.",), "Fırın kokusu çarşıyı sarar."),
            (game._trim_dangling_quote, ("Kâtip: “Defter kapandı.” Işıklar söner.",),
             "Kâtip: “Defter kapandı.” Işıklar söner."),
            (game._trim_dangling_quote, ("Gidelim artık.”",), ""),
            (game._trim_dangling_quote, ("Hiç tırnak yok, Şükrü güler.",), "Hiç tırnak yok, Şükrü güler."),
            (game._turkish_genitive_form, ("Şükrü",), "Şükrü'nün"),
            (game._turkish_genitive_form, ("İlkay",), "İlkay'ın"),
            (game._turkish_genitive_form, ("Özpil",), "Özpil'in"),
            (game._turkish_genitive_form, ("Kâtip",), "Kâtip'in"),
            (game._turkish_genitive_form, ("  Marek ",), "Marek'in"),
            (game._turkish_genitive_form, ("Kale",), "Kale'nin"),
            (game._turkish_genitive_form, ("Brr",), "Brr"),
            (game._turkish_genitive_form, ("",), ""),
            (game._turkish_genitive_form, (None,), ""),
            (game._word_root, ("takımını",), "takımı"),
            (game._word_root, ("emanetini",), "emaneti"),
            (game._word_root, ("çarşı",), "çarşı"),
            (game._word_root, ("kılıçlarımızı",), "kılıçlarımı"),
            (game._word_root, ("ışıklı",), "ışıkl"),
            (game._singular_narrator,
             ("Siz kapıya yaklaşırken etrafınızda fısıltılar yükselir; gözleriniz kararır.",),
             "Sen kapıya yaklaşırken etrafında fısıltılar yükselir; gözlerin kararır."),
            (game._singular_narrator,
             ("Muhafız size bakar: “Siz kimsiniz?” Sonra adımlarınızı izler, gidiyorsunuz, durdunuz.",),
             "Muhafız sana bakar: “Siz kimsiniz?” Sonra adımlarını izler, gidiyorsun, durdun."),
            (game._singular_narrator, (42,), 42),
            (game._attack_verb_tokens, ("muhafiza saldiriyorum ve vuruyorum",), ["saldiriyorum", "vuruyorum"]),
            (game._attack_verb_tokens, ("kesinlikle kestirme yoldan bicakla gidiyorum",), []),
            (game._attack_verb_tokens, ("kestrin keskin saldirgan vurmadim dovdum",), ["vurmadim", "dovdum"]),
        )
        for helper, args, expected in cases:
            with self.subTest(helper=helper.__name__, args=args):
                self.assertEqual(helper(*args), expected)


CR = tuple(batch_names("cr"))


class CharacterRulesPart(unittest.TestCase):
    """T4.1 batch cr: character, skill and dice helpers live in game_parts/character_rules.py; game.py re-exports them."""

    def test_cr_lives_in_the_part(self):
        self.assertEqual(set(CR) - set(routing_audit.re_exports(ROOT)["character_rules"]), set())

    def test_a_patched_roll_d20_reaches_a_moved_roll_attack(self):
        # the new path after the move: part roll_attack -> game.roll_d20 (R9)
        with patch.object(game, "roll_d20", return_value=20) as rolled:
            self.assertEqual(game.roll_attack(), 20)
        rolled.assert_called_once_with()

    def test_character_rules_session_helpers_use_the_given_session(self):  # Review Focus 4
        # every name reads game._session() (measured on 0b159e30; perform_skill_check on 0b1dca5a): record what it
        # returns during the session= call
        real = game._session
        with fixed_town(self, 20261201):
            s = game.create_session(seed=11)
            s.character["species"] = "Goliath"
            s.character["proficiency_bonus"] = 2
            # Plan 4 T5.4b (D-447): a slow-paced journey gives Perception advantage, and only s travels
            s.world_state["journey"] = {"status": "TRAVELLING", "pace": "slow"}
            self.assertNotEqual((game._session().world_state.get("journey") or {}).get("status"), "TRAVELLING")
            default_character = dict(game._session().character)
            answers = {}
            for name, args in (("roll_stat", ()), ("initialize_species_trait_state", ("hill",)),
                               ("perform_skill_check", ("Perception", 10, s.character["modifiers"],
                                                        s.character["proficient_skills"], 2))):
                seen = []

                def record():
                    value = real()
                    seen.append(value)
                    return value

                with self.subTest(name=name), patch.object(game, "_session", side_effect=record):
                    answers[name] = getattr(game, name)(*args, session=s)
                    self.assertTrue(seen)
                    self.assertTrue(all(value is s for value in seen))
            self.assertEqual(s.character["giant_ancestry"], "hill")
            self.assertIs(answers["perform_skill_check"]["advantage"], True)
            self.assertEqual(dict(game._session().character), default_character)

    def test_perform_skill_check_lives_in_character_rules(self):  # Plan 4 T5.4b
        self.assertIn("perform_skill_check", routing_audit.re_exports(ROOT)["character_rules"])

    def test_a_patched_perform_skill_check_reaches_its_staying_caller(self):
        # _hideout_check stays in game.py and calls perform_skill_check bare; 24 patch sites patch it on game
        with fixed_town(self, 20261340):
            character = game._session().character
            with patch.object(game, "perform_skill_check", return_value={"result": "BAŞARILI"}) as checked:
                self.assertIs(game._hideout_check("Stealth", 13), True)
        checked.assert_called_once_with("Stealth", 13, character["modifiers"],
                                        character.get("proficient_skills") or [],
                                        character.get("proficiency_bonus") or 2,
                                        expertise_skills=character.get("expertise_skills") or ())

    def test_cr_helpers_answer_as_before(self):
        # one fixed character (Barbarian, DEX 14, CON 16, WIS 12); expected values captured on 0b159e30 before the move
        self.assertEqual([game.get_modifier(stat) for stat in (8, 10, 15, 20)], [-1, 0, 2, 5])
        dex, con, wis = game.get_modifier(14), game.get_modifier(16), game.get_modifier(12)
        self.assertEqual((dex, con, wis), (2, 3, 1))
        self.assertEqual(game.calculate_hp("Barbarian", con), 15)
        self.assertEqual(game.calculate_ac("Barbarian", dex, con, wis), 15)


PLACES_1 = tuple(batch_names("places-1"))
PLACES_2 = tuple(batch_names("places-2"))
PLACES_S = tuple(batch_names("places-s"))


class PlacesPart(unittest.TestCase):
    """T4.2 batches places-1 and places-2: door, feature, location and scene helpers live in game_parts/places.py."""

    def test_places_1_lives_in_the_part(self):
        self.assertEqual(set(PLACES_1) - set(routing_audit.re_exports(ROOT).get("places", ())), set())

    def test_places_2_lives_in_the_part(self):
        self.assertEqual(set(PLACES_2) - set(routing_audit.re_exports(ROOT).get("places", ())), set())

    def test_places_s_lives_in_the_part(self):  # Plan 4 T5.4d
        self.assertEqual(set(PLACES_S) - set(routing_audit.re_exports(ROOT).get("places", ())), set())

    def test_places_session_helpers_use_the_given_session(self):  # Review Focus 4
        # every name reads game._session() (measured on 33ab2efd): record what it returns during the session= call
        real = game._session
        with fixed_town(self, 20261202):
            s = game.create_session(seed=11)
            s.world_state["location"] = "forest"
            # a place only the given session has: an answer the default session cannot give (Task 16 Fault 8)
            s.world_state["locations"]["t16_kuyu"] = {"id": "t16_kuyu", "name": "Kuyu Başı", "type": "city",
                                                      "description": ""}
            default_world = json.dumps(game._session().world_state, sort_keys=True, default=str)
            cases = (
                ("resolve_location_reference", ("ormanı",), "forest"),
                ("resolve_location_reference", ("t16_kuyu",), "t16_kuyu"),
                ("update_inventory_from_player", ("kılıcı yere bırakıyorum",), None),
                ("_walked_there", ({"kind": "go_to"}, {"action": "travel", "status": "already_here", "target_id": "forest"},
                                   None), True),
                # Plan 4 T5.4d (D-447): the walk and the new person go to the place only s has
                ("commit_location_change", ("t16_kuyu",), True),
                ("create_npc_from_ai", ({"name": "Dorn", "role": "Muhafız", "location": "t16_kuyu"},), None),
            )
            answers = {}
            for name, args, expected in cases:
                seen = []

                def record():
                    value = real()
                    seen.append(value)
                    return value

                with self.subTest(name=name), patch.object(game, "_session", side_effect=record):
                    answer = answers[name] = getattr(game, name)(*args, session=s)
                    if expected is not None:
                        self.assertEqual(answer, expected)
                    self.assertTrue(seen)
                    self.assertTrue(all(value is s for value in seen))
            self.assertEqual(s.world_state["location"], "t16_kuyu")
            self.assertEqual((answers["create_npc_from_ai"]["name"], answers["create_npc_from_ai"]["location"]),
                             ("Dorn", "t16_kuyu"))
            self.assertIn(answers["create_npc_from_ai"], s.world_state["npcs"])
            self.assertEqual(json.dumps(game._session().world_state, sort_keys=True, default=str), default_world)

    def test_places_helpers_answer_as_before(self):
        # a new session's three places (tavern, forest, castle); expected values captured on 33ab2efd before the move
        with fixed_town(self, 20261203):
            s = game.create_session(seed=11)
            self.assertEqual(game.normalize_location_id("tavern", session=s), "tavern")
            self.assertEqual(game.normalize_location_id("ormanı", session=s), "forest")
            self.assertEqual(game.location_display_name("tavern", session=s), "Taverna")
            self.assertEqual(game.location_display_name("Kuzey Kapısı", session=s), "Kuzey Kapısı")
        self.assertTrue(game._reference_token_matches("han", "hanlar"))
        self.assertTrue(game._reference_token_matches("kapı", "kapıdan"))
        self.assertFalse(game._reference_token_matches("han", "kapı"))

    def test_a_created_npc_gets_its_written_purse_from_the_part(self):  # Plan 4 T5.4d, the test_d207_written_purse shape
        import equipment_economy
        with fixed_town(self, 20261341):
            s = game.create_session(seed=11)
            s.world_state["location"] = "tavern"  # a new session has not placed the player yet
            default_before = _session_snapshot(game._DEFAULT_SESSION)
            guard = game.create_npc_from_ai({"name": "Dorn", "role": "Muhafız", "location": "tavern"}, session=s)
            self.assertIsNotNone(guard)
            self.assertIn(guard, s.world_state["npcs"])
            self.assertEqual(s.world_state["currency"][guard["id"]], equipment_economy.person_purse(s.world_state, guard))
            self.assertEqual(_session_snapshot(game._DEFAULT_SESSION), default_before)

    def test_grounded_action_still_reaches_create_npc_from_ai(self):  # Plan 4 T5.4d
        # grounded_action._create_venue calls run.game.create_npc_from_ai(..., session=run.session) for a new shop
        import grounded_action
        with fixed_town(self, 20261342):
            s = game.create_session(seed=11)
            settlement = s.world_state["location"]
            run = grounded_action._Run(s, "")
            with patch.object(game, "create_npc_from_ai", wraps=game.create_npc_from_ai) as created:
                record = grounded_action._create_venue(run, settlement, name="Kavaf Dükkânı", kind="generic",
                                                       noun="dukkan", provenance={"source": "test"})
        created.assert_called_once()
        self.assertIs(created.call_args.kwargs["session"], s)
        self.assertTrue(created.call_args.kwargs["allow_other_location"])
        owners = [npc for npc in s.world_state["npcs"] if npc.get("place_role_of") == record["id"]]
        self.assertEqual([(npc["name"], npc["location"]) for npc in owners], [(record["resident_name"], record["id"])])


INTENT_1 = tuple(batch_names("intent-1"))
INTENT_2 = tuple(batch_names("intent-2"))
INTENT_S = tuple(batch_names("intent-s"))


class IntentPart(unittest.TestCase):
    """T4.3 batches intent-1 and intent-2: intent reading and validation helpers live in game_parts/intent.py."""

    def test_intent_1_lives_in_the_part(self):
        self.assertEqual(set(INTENT_1) - set(routing_audit.re_exports(ROOT).get("intent", ())), set())

    def test_intent_2_lives_in_the_part(self):
        self.assertEqual(set(INTENT_2) - set(routing_audit.re_exports(ROOT).get("intent", ())), set())

    def test_intent_s_lives_in_the_part(self):  # Plan 4 T5.4e
        self.assertEqual(set(INTENT_S) - set(routing_audit.re_exports(ROOT).get("intent", ())), set())

    def test_a_rebound_validate_intent_reaches_a_moved_caller(self):  # Review Focus 5
        # analyze_player_action (moved in intent-1) reads game.parse_player_intent, game.normalize_intent and
        # game.validate_intent, three of the four names trace_ai_pipeline.py rebinds; no session, model or campaign
        seen = []

        def validate(intent, player_input):
            seen.append((intent, player_input))
            return {"intent": "perception", "skill": "Perception", "difficulty": "hard"}

        with patch.object(game, "parse_player_intent", return_value={"raw": 1}) as parse, \
             patch.object(game, "normalize_intent", return_value={"norm": 1}) as norm, \
             patch.object(game, "validate_intent", side_effect=validate):
            out = game.analyze_player_action("Etrafa bakıyorum.", "Fighter", [])
        parse.assert_called_once_with("Etrafa bakıyorum.")
        norm.assert_called_once_with({"raw": 1}, "Etrafa bakıyorum.")
        self.assertEqual(seen, [({"norm": 1}, "Etrafa bakıyorum.")])
        self.assertEqual(out, {"action_type": "check", "skill": "Perception", "difficulty": "hard"})

    def test_intent_session_helpers_use_the_given_session(self):  # Review Focus 4
        # both names read game._session() (measured on d9bbb857): record what it returns during the session= call
        real = game._session
        with fixed_town(self, 20261204):
            s = game.create_session(seed=11)
            # a hero name only the given session has (D-447): the default session's hero would make the claim True
            s.character["name"] = "Torvald Kaya"
            # Plan 4 T5.4e (D-447): a place only the given session has; the default session cannot name it as the target
            s.world_state["location"] = "forest"
            s.world_state["locations"]["t16_kuyu"] = {"id": "t16_kuyu", "name": "Kuyu Başı", "type": "city",
                                                      "description": ""}
            default_world = json.dumps(game._session().world_state, sort_keys=True, default=str)
            cases = (
                ("is_npc_historical_claim", ("Bu adam dün beni soydu.",), False),
                ("is_npc_historical_claim", ("Adımı söyledim, Torvald.",), False),
                ("known_character_answer", ("Benim adım ne?",), f"Adın {s.character['name']}."),
                # Plan 4 T5.4e: captured on 3619f580 before the move; no road is known, so nothing is written
                ("execute_intent", ({"intent": "travel", "target": {"type": "location", "reference": "Kuyu Başı"}},
                                    "Kuyu Başı'na gidiyorum."),
                 {"action": "travel", "success": False, "status": "unverified", "state_changes": [],
                  "completion": "completed", "target_reference": "Kuyu Başı", "target": "t16_kuyu",
                  "previous_location": "forest", "direct_response": "Oraya giden bir yol bilmiyorsun."}),
            )
            for name, args, expected in cases:
                seen = []

                def record():
                    value = real()
                    seen.append(value)
                    return value

                with self.subTest(name=name), patch.object(game, "_session", side_effect=record):
                    self.assertEqual(getattr(game, name)(*args, session=s), expected)
                    self.assertTrue(seen)
                    self.assertTrue(all(value is s for value in seen))
            self.assertEqual(s.world_state["location"], "forest")
            self.assertEqual(json.dumps(game._session().world_state, sort_keys=True, default=str), default_world)

    def test_an_immediate_check_snapshots_the_given_session(self):  # Review Focus 4, Plan 4 Task 16 Fault 6
        # execute_intent reads game._session() only when check_feature is set: the snapshot taken before the check
        # and restored after a failed check must belong to the given session, never the default one
        real = game._session
        real_capture = game.GameSession._capture_runtime_snapshot
        real_restore = game.GameSession._restore_runtime_snapshot
        with fixed_town(self, 20261352):
            s = game.create_session(seed=11)
            s.world_state["location"] = "forest"
            default_world = json.dumps(game._session().world_state, sort_keys=True, default=str)
            seen, captured, restored = [], [], []

            def record():
                value = real()
                seen.append(value)
                return value

            def capture(owner):
                captured.append(owner)
                return real_capture(owner)

            def restore(owner, snapshot):
                restored.append(owner)
                return real_restore(owner, snapshot)

            def failing_check(*args, **kwargs):
                # the check writes into the active session, then fails: execute_intent must roll the write back
                game._session().world_state["location"] = "castle"
                raise RuntimeError("t16 check failure")

            with patch.object(game, "_session", side_effect=record), \
                 patch.object(game, "primal_knowledge_check_admission", return_value=None), \
                 patch.object(game, "perform_skill_check", side_effect=failing_check) as check, \
                 patch.object(game.GameSession, "_capture_runtime_snapshot", autospec=True, side_effect=capture), \
                 patch.object(game.GameSession, "_restore_runtime_snapshot", autospec=True, side_effect=restore):
                with self.assertRaisesRegex(RuntimeError, "t16 check failure"):
                    game.execute_intent({"intent": "unknown"}, "Takla atıyorum.", check_feature="primal_knowledge",
                                        session=s)
            check.assert_called_once()
            self.assertEqual(captured, [s])
            self.assertEqual(restored, [s])
            self.assertTrue(seen)
            self.assertTrue(all(value is s for value in seen))
            self.assertEqual(s.world_state["location"], "forest")
            self.assertEqual(json.dumps(game._session().world_state, sort_keys=True, default=str), default_world)

    def test_a_presence_query_creates_its_person_with_a_purse_from_the_part(self):  # Plan 4 TM4, D-456
        # the HELD money path of intent-s: _handle_query's presence branch in an empty, unseen place reaches
        # materialize_scene(create_npc=game.create_npc_from_ai) -> equipment_economy.give_person_purse; every person and
        # purse it writes must land in the given session, never in the default one
        import equipment_economy
        real = game._session
        real_purse = equipment_economy.give_person_purse
        with fixed_town(self, 20261353):
            s = game.create_session(seed=11)
            s.world_state["locations"]["tm4_meydan"] = {"id": "tm4_meydan", "name": "Taş Meydan", "type": "city",
                                                       "description": ""}
            s.world_state["location"] = "tm4_meydan"
            self.assertEqual(game.active_npcs("tm4_meydan", session=s), [])
            before_ids = {npc["id"] for npc in s.world_state["npcs"]}
            default_world = json.dumps(game._session().world_state, sort_keys=True, default=str)
            seen, purses = [], []

            def record():
                value = real()
                seen.append(value)
                return value

            def purse(world, npc):
                purses.append((world, npc["id"]))
                return real_purse(world, npc)

            with patch.object(game, "_session", side_effect=record), \
                 patch.object(equipment_economy, "give_person_purse", side_effect=purse):
                text = game._handle_query("Burada kimler var?", "presence", session=s)
            new = [npc for npc in s.world_state["npcs"] if npc["id"] not in before_ids]
            self.assertTrue(new)
            self.assertTrue(all(npc["location"] == "tm4_meydan" for npc in new))
            self.assertEqual([npc_id for _world, npc_id in purses], [npc["id"] for npc in new])
            self.assertTrue(all(world is s.world_state for world, _npc_id in purses))
            for npc in new:
                self.assertIn(npc["id"], s.world_state["currency"])
            self.assertIsInstance(text, str)
            self.assertTrue(seen)
            self.assertTrue(all(value is s for value in seen))
            default_after = game._session().world_state
            self.assertEqual(json.dumps(default_after, sort_keys=True, default=str), default_world)
            self.assertFalse({npc["id"] for npc in new} & set(default_after.get("currency", {})))

    def test_a_rebound_execute_intent_reaches_its_moved_caller(self):  # Plan 4 T5.4e, Review Focus 5
        # trace_ai_pipeline.py rebinds game.execute_intent; update_world_state_from_player (moved in intent-s) must call
        # the rebound name; the parse/normalize/validate patches are the shape test_shops.py uses
        seen = []

        def record(intent, player_input, *args, **kwargs):
            seen.append((intent, player_input, args, kwargs))
            return {"action": "narrative", "success": True, "state_changes": []}

        with fixed_town(self, 20261350):
            s = game.create_session(seed=11)
            s.world_state["location"] = "tavern"
            with patch.object(game, "parse_player_intent", return_value={}),                  patch.object(game, "normalize_intent", return_value={}),                  patch.object(game, "validate_intent", return_value={"intent_type": "narrative"}),                  patch.object(game, "execute_intent", side_effect=record):
                out = game.update_world_state_from_player("The wind is blowing.", session=s)
        self.assertEqual(seen, [({"intent_type": "narrative"}, "The wind is blowing.", (), {})])
        self.assertEqual(out, {"action": "narrative", "success": True, "state_changes": []})

    def test_a_patched_ollama_reaches_the_moved_parse(self):  # Plan 4 T5.4e
        # parse_player_intent (moved in intent-s) asks the model through game.ollama; a patched module must answer it
        fixed = {"intent": "perception", "skill": "Perception", "difficulty": "medium",
                 "target": {"type": "none", "reference": ""}}
        with fixed_town(self, 20261351):
            s = game.create_session(seed=11)
            with patch.object(game, "ollama") as model:
                model.chat.return_value = {"message": {"content": json.dumps(fixed)}, "done_reason": "stop"}
                out = game.parse_player_intent("Etrafa bakıyorum.", session=s)
        model.chat.assert_called_once()
        self.assertEqual(out, fixed)

    def test_intent_helpers_answer_as_before(self):
        # expected values captured on d9bbb857 before the move; a new session's places are tavern, forest, castle
        self.assertTrue(game.is_dialogue_or_emotion("Merhaba, nasılsın?"))
        self.assertFalse(game.is_dialogue_or_emotion("Kılıcımı çekiyorum."))
        self.assertTrue(game._reads_as_question("Burası neresi?"))
        self.assertFalse(game._reads_as_question("Kapıyı açıyorum."))
        with fixed_town(self, 20261205):
            s = game.create_session(seed=11)
            self.assertTrue(game._normalize_turkish_location("Ormana gidiyorum", "forest", session=s))
            self.assertFalse(game._normalize_turkish_location("Kaleye yürüyorum", "orman", session=s))

    def test_the_intent_error_is_one_class(self):
        # the moved _detect_query_type is on the turn path in both flags (measured on d9bbb857); game.active_npcs (an
        # existing census target) raises game.IntentInfrastructureError only when that moved caller reads it, and the
        # staying handler in _run_player_turn must catch it as its own class and restore the world
        real = game.active_npcs
        planted = game.IntentInfrastructureError("planted")
        callers = []

        def active_npcs(*args, **kwargs):
            callers.append(sys._getframe(1).f_code.co_name)
            if callers[-1] == "_detect_query_type":
                raise planted
            return real(*args, **kwargs)

        active_npcs._session_bound = True  # GameSession.__getattr__ hands out only session-bound engine helpers
        with fixed_town(self, 20261206):
            s = game.create_session(seed=11)
            before = json.dumps(s.world_state, sort_keys=True, default=str)
            with patch.object(game, "active_npcs", new=active_npcs), \
                 patch.object(game.ollama, "chat", side_effect=RuntimeError("no model in this test")):
                result = s.run_player_turn("Etrafa bakıyorum.")
            self.assertEqual(callers[-1], "_detect_query_type")
            self.assertEqual(result["action_result"]["status"], "infrastructure_failure")
            self.assertEqual(result["action_result"]["infrastructure_code"], "planted")
            self.assertEqual(json.dumps(s.world_state, sort_keys=True, default=str), before)



DIALOGUE_1 = tuple(batch_names("dialogue-1"))
DIALOGUE_2 = tuple(batch_names("dialogue-2"))
DIALOGUE_S = tuple(batch_names("dialogue-s"))


class DialoguePart(unittest.TestCase):
    """T4.4 batches dialogue-1 and dialogue-2: conversation and NPC speech helpers live in game_parts/dialogue.py."""

    def test_dialogue_1_lives_in_the_part(self):
        self.assertEqual(set(DIALOGUE_1) - set(routing_audit.re_exports(ROOT).get("dialogue", ())), set())

    def test_dialogue_2_lives_in_the_part(self):
        self.assertEqual(set(DIALOGUE_2) - set(routing_audit.re_exports(ROOT).get("dialogue", ())), set())

    def test_dialogue_s_lives_in_the_part(self):  # Plan 4 T5.4f
        self.assertEqual(set(DIALOGUE_S) - set(routing_audit.re_exports(ROOT).get("dialogue", ())), set())

    def test_the_stock_said_deque_is_one_object(self):
        # a call with no session (_session() gives None) uses the module deque; the re-export keeps one object
        with patch.object(game, "_session", return_value=None):
            self.assertIs(game._stock_said.__wrapped__(), game._STOCK_SAID)

    def test_dialogue_session_helpers_use_the_given_session(self):  # Review Focus 4
        # every name reads game._session() (measured on cc1e9321; _direct_npc_smalltalk_response on 7ed9615a): record
        # what it returns during the session= call
        real = game._session
        with fixed_town(self, 20261207):
            s = game.create_session(seed=11)
            bela = {"id": "npc_t10_bela", "name": "Bela", "role": "hancı", "location": s.world_state["location"],
                    "name_known_to_player": True, "role_known_to_player": True}
            s.world_state["npcs"].append(bela)
            # an inn only the given session has (D-447): the default session knows no inn here
            s.world_state["locations"]["t17_han"] = {"id": "t17_han", "name": "Kuyu Hanı", "type": "tavern",
                                                     "parent_location_id": s.world_state["location"],
                                                     "description": ""}
            # Plan 4 T5.4f (D-447): the rest of the line only the given session holds; the default session has none
            s._front_rest = "Kuyu nerede?"
            default_world = json.dumps(game._session().world_state, sort_keys=True, default=str)
            cases = (
                ("resolve_npc_reference", ("Bela, merhaba",), {"status": "found", "npc": "npc_t10_bela"}),
                ("_npc_speech_is_claim_refusal", ("Hayır, öyle bir şey hatırlamıyorum.", bela), True),
                ("_npc_speech_is_claim_refusal", ("Evet, söz vermiştim.", bela), False),
                ("record_npc_interaction", (bela, "Hoş geldin yolcu.", "Merhaba, nasılsın?", bela), None),
                ("_direct_npc_smalltalk_response", ("Nasılsın?", bela),
                 "Bela, “Fena değil, teşekkür ederim. Sorduğun için sağ ol,” diye karşılık verir."),
                ("_direct_npc_smalltalk_response", ("Yakınlarda bir han var mı?", bela),
                 "Bela, “Yakınlarda Kuyu Hanı var,” diye yanıt verir."),
                # Plan 4 T5.4f: the note's own lines (its second line), captured on 893655cc before the move, after
                # the cases above (Bela's earlier words are in it)
                ("_experimental_speech_note", (s.world_state, bela, None, "Merhaba, nasılsın?"),
                 "Konuşan sensin; sahnedeki “Bela” sensin, oyuncu karşındaki kişidir. Konuşma biçimin: Alaycıdır; "
                 "kuru bir laf sokuşturur. Sıradan birisin, herkese yardım etmek zorunda değilsin. Adın Bela; "
                 "sorulmadıkça tekrar etme. Oyuncu aynı sözde şunu da söyledi: Kuyu nerede? Buna da cevap ver. "
                 "Daha önce sen gerçekten şunları söyledin: Hoş geldin yolcu. Oyuncu bunlardan söz ediyorsa inkâr "
                 "etme; kendi sözün olarak karşılık ver.   Oyuncunun üstünde gerçekten olanlar: Macera çantası, "
                 "Kılıç. Başka bir şey onun elinde değildir."),
            )
            for name, args, expected in cases:
                seen = []

                def record():
                    value = real()
                    seen.append(value)
                    return value

                with self.subTest(name=name, text=args[0]), patch.object(game, "_session", side_effect=record):
                    answer = getattr(game, name)(*args, session=s)
                    if isinstance(answer, dict):
                        answer = {key: value.get("id") if isinstance(value, dict) else value
                                  for key, value in answer.items()}
                    if name == "_experimental_speech_note":
                        answer = answer.split("\n")[1]
                    self.assertEqual(answer, expected)
                    self.assertTrue(seen)
                    self.assertTrue(all(value is s for value in seen))
            said = game.npc_statements.view(s.world_state)["statements"].get("npc_t10_bela")
            self.assertEqual([(entry["player"], entry["text"]) for entry in said],
                             [("Merhaba, nasılsın?", "Hoş geldin yolcu.")])
            self.assertEqual(json.dumps(game._session().world_state, sort_keys=True, default=str), default_world)

    def test_dialogue_helpers_answer_as_before(self):
        # expected values captured on cc1e9321 before the move; the NPCs are plain dicts, no session is created
        self.assertTrue(game._is_end_conversation_request("konuşmayı bitiriyorum"))
        self.assertTrue(game._is_end_conversation_request("Sohbeti sonlandırıyorum."))
        self.assertFalse(game._is_end_conversation_request("konuşmaya devam"))
        guard = {"id": "npc_t10_guard", "name": "Dorn", "role": "muhafız"}
        traveller = {"id": "npc_t10_plain", "name": "Ilka", "role": "yolcu"}
        self.assertTrue(game._words_fit_person(guard, "muhafiz"))
        self.assertTrue(game._words_fit_person(guard, "bekci"))
        self.assertFalse(game._words_fit_person(guard, "hanci"))
        self.assertFalse(game._words_fit_person(traveller, "muhafiz"))
        self.assertEqual(game.historical_claim_denial(guard, "Dün bana söz verdin."),
                         "Dorn sesini alçaltıyor. “Söz verdiysem hatırlardım; sözümü tutmayan biri olarak anılmak "
                         "istemem. Ama bu benim ağzımdan çıkmadı.”")
        self.assertEqual(game.historical_claim_denial(None, "x"),
                         "Bu kişi omuz silkiyor. “Yanlış kapıyı çalıyorsun, dostum. Ben böyle bir şey söylemedim.”")

    def test_coin_persuasion_answers_as_before(self):  # Plan 4 T5.4f
        # captured on 893655cc before the move: a Persuasion this turn rolled is reused against the DC, never
        # rerolled; a roll of another skill gives no coin; no session and no fresh roll is needed for either
        persuasion = game._coin_persuasion({"action": "skill_check", "skill": "Persuasion", "total": 15})
        self.assertEqual(persuasion(12, False), {"success": True})
        self.assertEqual(persuasion(16, False), {"success": False})
        athletics = game._coin_persuasion({"action": "skill_check", "skill": "Athletics", "total": 19})
        self.assertIsNone(athletics(12, False))


LORE = tuple(batch_names("lore"))


class LorePart(unittest.TestCase):
    """T4.5 batch lore: lore authority and stage-direction helpers live in game_parts/lore.py."""

    def test_lore_lives_in_the_part(self):
        self.assertEqual(set(LORE) - set(routing_audit.re_exports(ROOT).get("lore", ())), set())

    def test_lore_helpers_answer_as_before(self):
        # inputs from test_place_consistency and test_local_place_travel; values captured on 2d8bed3d before the move
        def street(**extra):
            return {
                "location": "city",
                "locations": {"city": {"id": "city", "name": "Neverwinter", "type": "city", "description": ""}},
                "features": [], "npcs": [{"id": "n", "name": "Mira", "role": "Kent sakini", "location": "city"}],
                **extra,
            }

        inn = street()
        inn["locations"]["city"]["scene_kind"] = "tavern"
        stall = street()
        stall["npcs"][0]["role"] = "Tüccar"
        cases = (
            (street(), "Masanın kenarına yaslanıyor. Başını hafifçe sallıyor.", "Başını hafifçe sallıyor."),
            (street(), "Tezgâhın arkasında duruyor.", ""),
            (street(), "Omuz silkiyor.", "Omuz silkiyor."),
            (inn, "Tezgâhın arkasında duruyor.", "Tezgâhın arkasında duruyor."),
            (stall, "Tezgâhına yaslanıyor.", "Tezgâhına yaslanıyor."),
        )
        for world, stage, expected in cases:
            with self.subTest(stage=stage):
                self.assertEqual(game._stage_within_the_street(stage, world), expected)
                self.assertEqual(game._shown_stage_direction(stage, world), expected)
        self.assertEqual(game._shown_stage_direction("   ", street()), "")
        self.assertEqual(game._shown_stage_direction(None, street()), "")
        district = {"location": "d", "locations": {"d": {"name": "Liman Mahallesi", "type": "district"}}}
        city = {"location": "c", "locations": {"c": {"name": "Neverwinter", "type": "city"}}}
        self.assertTrue(game._names_the_district_here("mahallenin", district))
        self.assertTrue(game._names_the_district_here("Semtin", district))
        self.assertFalse(game._names_the_district_here("sokağın", district))
        self.assertFalse(game._names_the_district_here("mahallenin", city))

    def test_the_empty_lore_context_is_a_fresh_value_each_call(self):
        # measured on 2d8bed3d: two calls give equal dicts, never the same object (nor shared section lists)
        first, second = game._empty_lore_authority_context(), game._empty_lore_authority_context()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertIsNot(first["sections"], second["sections"])
        self.assertIsNot(first["sections"]["campaign_canon"], second["sections"]["campaign_canon"])
        self.assertEqual(set(first), {"authority_boundary", "sections"})
        self.assertTrue(all(first["authority_boundary"].values()))
        self.assertEqual(first["sections"], {
            "official_forgotten_realms_lore": [], "campaign_canon": [], "player_known_lore": [],
            "npc_known_lore": [], "procedural_local_content": [], "unknown_or_unloaded": [],
        })

    def test_lore_entity_names_lives_in_lore(self):  # Plan 4 T5.4c
        self.assertIn("_lore_entity_names", routing_audit.re_exports(ROOT).get("lore", ()))

    def test_lore_entity_names_answer_as_before(self):
        # values captured on 0b1dca5a before the move with p4t10-capture.py (PYTHONHASHSEED=1 and =2 gave the same)
        lore = {"sections": {"verified_entities": [
            {"entity_id": "t10_neverwinter", "canonical_name": "Neverwinter", "aliases": ["Kış Diyarı", "Mücevher Şehri"]},
            {"entity_id": "t10_river", "canonical_name": "Neverwinter River", "aliases": []},
            "not a dict",
        ]}}
        world = {
            "location": "t10_square",
            "locations": {"t10_square": {"name": "Pazar Meydanı", "aliases": ["Meydan"]}, "t10_road": {"name": "North Road"}},
            "npcs": [{"id": "t10_mira", "name": "Mira Taşkalp", "role": "Demirci", "location": "t10_square"},
                     {"id": "t10_osric", "name": "Osric", "role": "Muhafız", "location": "t10_road",
                      "aliases": ["Yaşlı Asker"]}],
            "features": [{"feature_id": "t10_well", "name": "Eski Kuyu"}],
            "shops": [{"id": "t10_shop", "name": "Kuyu Dükkanı"}, "skip"],
        }
        by_id, phrases, tokens = game._lore_entity_names(lore, world)
        self.assertEqual(by_id, {
            "t10_mira": {"demirci", "mira taskalp"}, "t10_neverwinter": {"kis diyari", "mucevher sehri", "neverwinter"},
            "t10_osric": {"osric", "yasli asker"}, "t10_river": {"neverwinter river"}, "t10_road": {"north road"},
            "t10_shop": {"kuyu dukkani"}, "t10_square": {"meydan", "pazar meydani"}, "t10_well": {"eski kuyu"},
        })
        self.assertEqual(phrases, {"demirci", "eski kuyu", "kis diyari", "kuyu dukkani", "meydan", "mira taskalp",
                                   "mucevher sehri", "neverwinter", "neverwinter river", "north road", "osric",
                                   "pazar meydani", "yasli asker"})
        self.assertEqual(tokens, {"asker", "demirci", "diyari", "dukkani", "eski", "kuyu", "meydan", "meydani", "mira",
                                  "mucevher", "neverwinter", "osric", "pazar", "sehri", "taskalp", "yasli"})
        self.assertEqual(game._lore_entity_names(None, None), ({}, set(), set()))


NARRATION = tuple(batch_names("narration"))
NARRATION_S_1 = tuple(batch_names("narration-s-1"))
NARRATION_S_2 = tuple(batch_names("narration-s-2"))


def _model_reply(narration):
    """What game.ollama.chat returns for one narration with no world updates (shape of ollama_response_content)."""
    return {"message": {"content": json.dumps({"narration": narration, "world_updates": {}, "lore_claims": []},
                                              ensure_ascii=False)}, "done_reason": "stop"}


class NarrationPart(unittest.TestCase):
    """T4.6 batch narration: fallback, inspection and repair helpers live in game_parts/narration.py."""

    def test_narration_lives_in_the_part(self):
        self.assertEqual(set(NARRATION) - set(routing_audit.re_exports(ROOT).get("narration", ())), set())

    def test_narration_s_1_lives_in_the_part(self):  # Plan 4 T5.4g
        self.assertEqual(set(NARRATION_S_1) - set(routing_audit.re_exports(ROOT).get("narration", ())), set())

    def test_narration_s_2_lives_in_the_part(self):  # Plan 4 T5.4h
        self.assertEqual(set(NARRATION_S_2) - set(routing_audit.re_exports(ROOT).get("narration", ())), set())

    def test_the_narrative_adapter_reaches_the_moved_ask(self):  # Review Focus 5
        # the adapter is permanent and installs once (create_app does the same); inside the director's turn frame an
        # offline model call must reach the build wrapper through game.build_world_context (the frame gets its
        # diagnostics) and the finalize wrapper through game.finalize_narration (it hands the frame's claims to the
        # original finalize, counted here once); expected values measured on 83804208 before the move
        install_narrative_context_adapter(game)
        finalize = game.finalize_narration
        cell = finalize.__closure__[finalize.__code__.co_freevars.index("original_finalize")]
        original = cell.cell_contents
        counted = MagicMock(wraps=original)
        with fixed_town(self, 20261381):
            s = game.create_session(seed=11)
            cell.cell_contents = counted
            try:
                with patch.object(game, "ollama") as model,                         narrative_turn_context(empty_narrative_memory(), "Etrafa bakıyorum.") as frame:
                    model.chat.side_effect = ConnectionError("offline")
                    answer = game.ask_dungeon_master([], "Etrafa bakıyorum.", session=s)
            finally:
                cell.cell_contents = original
        self.assertEqual(model.chat.call_count, 1)
        self.assertEqual(answer, "Çevrede şimdilik belirgin bir değişiklik olmuyor.")
        self.assertIn("selected_counts", frame.diagnostics)
        self.assertEqual(counted.call_count, 1)
        self.assertEqual(counted.call_args.kwargs.get("fallback_reason_code"), "MODEL_UNAVAILABLE")
        self.assertIn("supported_player_claims", counted.call_args.kwargs)

    def test_a_patched_ollama_reaches_the_moved_ask(self):
        # census import target: the moved ask must call game.ollama (measured on 83804208 before the move)
        with fixed_town(self, 20261382):
            s = game.create_session(seed=11)
            with patch.object(game, "ollama") as model:
                model.chat.return_value = _model_reply("Rüzgâr kepenkleri sallıyor.")
                answer = game.ask_dungeon_master([], "Etrafa bakıyorum.", return_details=True, session=s)
        self.assertEqual(model.chat.call_count, 1)
        self.assertEqual(answer, {"narration": "Rüzgâr kepenkleri sallıyor.", "world_updates": {}, "lore_claims": [],
                                  "player_line": None, "item_claims": None, "valid_response": True,
                                  "fallback_reason_code": None})

    def test_narration_session_helpers_use_the_given_session(self):  # Review Focus 4
        # both names read game._session() (measured on 8cc9a805): record what it returns during the session= call
        real = game._session
        with fixed_town(self, 20261208):
            s = game.create_session(seed=11)
            # inputs only the given session has (D-447): its no-change line already stepped once this turn (the
            # default session would give the first line) and a well where it stands (the default session has none)
            s._variation_state = {("no_change",): (s.world_state.get("flags", {}).get("turn_index", 0), 1)}
            s.world_state.setdefault("features", []).append({"id": "t17_kuyu", "name": "Kuyu",
                                                             "location": s.world_state["location"],
                                                             "description": "Taş bilezikli eski bir kuyu."})
            # and Tarvek the well digger where it stands (Plan 4 T5.4g; the default session has nobody there)
            s.world_state["npcs"].append({"id": "npc_t14_tarvek", "name": "Tarvek", "role": "kuyucu",
                                          "location": s.world_state["location"], "name_known_to_player": True,
                                          "role_known_to_player": True})
            default_world = json.dumps(game._session().world_state, sort_keys=True, default=str)
            tracks_failed = {"target_kind": "tracks", "target_id": None, "target_name": "izler", "found": False,
                             "text": "İzler birbirine karışmış; bu bakışla bir şey çıkaramıyorsun."}
            well_failed = {"target_kind": "feature", "target_id": "t17_kuyu", "target_name": "Kuyu", "found": False,
                           "text": "Kuyu üzerinde bu bakışla yeni bir ayrıntı seçemiyorsun."}
            cases = (
                ("_generic_no_change_response", (), {},
                 "Çevrede şimdilik belirgin bir değişiklik olmuyor; herkes kendi işine bakıyor, söz sende."),
                ("_inspection_findings", ("izlere bakıyorum", "failure"), {}, tracks_failed),
                ("_inspection_findings", ("etrafa bakıyorum", "failure"), {}, None),
                ("_inspection_findings", ("kuyuya bakıyorum", "failure"), {}, well_failed),
                # Plan 4 T5.4g, captured on afd69027 before the move: the people the context shows
                ("build_world_context", (), {}, ["Tarvek"]),
                # Plan 4 T5.4h, captured on 83804208 before the move: Tarvek's mark reads as his name (the default
                # session drops it); the model (game.ollama, patched below) answers once, for the ask
                ("finalize_narration", ("[[npc_t14_tarvek]] başını kaldırıp sana bakıyor.", "Kuyucuya bakıyorum."), {},
                 "Tarvek başını kaldırıp sana bakıyor."),
                ("ask_dungeon_master", ([], "Kuyucuya bakıyorum."), {}, "Tarvek başını kaldırıp sana bakıyor."),
            )
            views = {"build_world_context": lambda context: [npc.get("name") for npc in context["npcs"]]}
            model_patch = patch.object(game, "ollama")
            model = model_patch.start()
            self.addCleanup(model_patch.stop)
            model.chat.return_value = _model_reply("[[npc_t14_tarvek]] başını kaldırıp sana bakıyor.")
            for name, args, kwargs, expected in cases:
                seen = []

                def record():
                    value = real()
                    seen.append(value)
                    return value

                with self.subTest(name=name, args=args), patch.object(game, "_session", side_effect=record):
                    answer = getattr(game, name)(*args, session=s, **kwargs)
                    self.assertEqual(views.get(name, lambda value: value)(answer), expected)
                    self.assertTrue(seen)
                    self.assertTrue(all(value is s for value in seen))
            self.assertEqual(model.chat.call_count, 1)
            self.assertEqual(json.dumps(game._session().world_state, sort_keys=True, default=str), default_world)

    def test_world_updates_validate_as_before(self):
        # two update dicts from test_shops.py (a shopkeeper through generic NPC updates; a plain shop proposal);
        # expected values captured on afd69027 before the move
        shop = {"name": "Green Lantern", "description": "A small timber storefront with a painted green sign.",
                "shopkeeper": {"name": "Mira", "personality": "Patient and observant.",
                               "appearance": "A short-haired human in a plain apron."}}
        empty = {"create_locations": [], "create_npcs": [], "update_npcs": [], "create_features": [],
                 "create_shops": [], "events": []}
        with fixed_town(self, 20261380):
            s = game.create_session(seed=11)
            s.world_state["location"] = "tavern"
            updates = {"create_npcs": [{"name": "Mira", "role": "Merchant", "location": "tavern"}],
                       "create_shops": [shop]}
            self.assertEqual(game.validate_world_updates(updates, allow_new_npcs=True, allow_new_shops=False,
                                                         session=s), empty)
            self.assertEqual(game.validate_world_updates({"create_shops": [shop]}, allow_new_shops=True, session=s),
                             dict(empty, create_shops=[dict(shop, location="tavern", proposal_key="s1")]))

    def test_narration_helpers_answer_as_before(self):
        # one open street with one person (Mira); expected values captured on 8cc9a805 before the move
        with fixed_town(self, 20261211):
            s = game.create_session(seed=11)
            s.world_state["locations"]["t12_street"] = {"id": "t12_street", "name": "Pazar Sokağı", "type": "city",
                                                         "description": ""}
            s.world_state["location"] = "t12_street"
            s.world_state["npcs"].append({"id": "npc_t12_mira", "name": "Mira", "role": "Kent sakini",
                                          "location": "t12_street", "name_known_to_player": True,
                                          "role_known_to_player": True})
            repairs = (
                ("[[npc_t12_mira]] “Hoş geldin,” diyor.", "Mira “Hoş geldin,” diyor."),
                ("npc_t12_mira’nın gözleri parlıyor.", "Mira’nın gözleri parlıyor."),
                ("“Merhaba,” diyor Mira.", "“Merhaba,” diyor Mira."),
                ("Biri [[x9]] diye fısıldıyor.", "Biri diye fısıldıyor."),
            )
            for text, expected in repairs:
                with self.subTest(repair=text):
                    self.assertEqual(game._repair_internal_marks(text, session=s), expected)
            drops = (
                ("Mira tezgâhın arkasında duruyor. “Buyur,” diyor.", "“Buyur,” diyor."),
                ("“Hoş geldin,” diyor Mira. Rüzgâr esiyor.", "“Hoş geldin,” diyor Mira. Rüzgâr esiyor."),
                (None, None),
            )
            for text, expected in drops:
                with self.subTest(drop=text):
                    self.assertEqual(game._drop_absent_counter_sentences(text, session=s), expected)

    def test_a_patched_should_generate_npcs_reaches_its_staying_caller(self):
        # the census site (test_sessions) patches it around a turn; _run_player_turn_internal stays in game.py and
        # hands its answer to the narrator as allow_new_npcs (unpatched it is False for this input; measured 8cc9a805)
        for value in (True, False):
            with self.subTest(value=value), fixed_town(self, 20261209):
                s = game.create_session(seed=11)
                s.world_state["location"] = "tavern"
                s.world_state["locations"]["tavern"] = {"name": "Taverna"}
                with patch.object(game, "parse_player_intent", return_value={"intent": "unknown"}), \
                        patch.object(game, "should_generate_npcs", return_value=value) as generate, \
                        patch.object(game, "ask_dungeon_master", return_value={
                            "narration": "Lamba alevi titriyor.", "world_updates": {}, "lore_claims": [],
                            "valid_response": True}) as narrator:
                    s.run_player_turn("Rüzgar esiyor.")
                self.assertTrue(generate.called)
                self.assertEqual([call.kwargs.get("allow_new_npcs") for call in narrator.call_args_list], [value])


NSAFETY_1 = tuple(batch_names("nsafety-1"))
NSAFETY_2 = tuple(batch_names("nsafety-2"))


class NarrationSafetyPart(unittest.TestCase):
    """T4.7 batches nsafety-1, nsafety-2: narration safety checks live in game_parts/narration_safety.py."""

    def test_nsafety_1_lives_in_the_part(self):
        self.assertEqual(set(NSAFETY_1) - set(routing_audit.re_exports(ROOT).get("narration_safety", ())), set())

    def test_nsafety_helpers_answer_as_before(self):
        # inputs from test_narrator_voice and test_ai_pipeline_semantics; values captured on d0d42842 before the move
        text = "Masaya tırmanıyorsun. Liora'nın elindeki bez yavaşça duruyor. Omuzları hafifçe gerginleşiyor."
        removals = (
            ({"reason_code": "UNREGISTERED_PERSISTENT_OBJECT",
              "trigger_span": "bez yavasca duruyor omuzlari hafifce gerginlesi"}, None,
             "Masaya tırmanıyorsun. Omuzları hafifçe gerginleşiyor."),
            ({"reason_code": "UNREGISTERED_PERSISTENT_OBJECT", "trigger_span": "hic gecmeyen bir ifade burada"},
             None, None),
            ({"reason_code": "UNRELATED_GREETING_REPLY", "trigger_span": "Masaya"}, None, None),
            ({"reason_code": "UNREGISTERED_PERSISTENT_OBJECT", "trigger_span": "Masaya"}, {"action": "attack"}, None),
            ({"reason_code": "INVENTED_PLAYER_ACTION", "trigger_span": "Masaya tırmanıyorsun"}, {"action": "attack"},
             "Liora'nın elindeki bez yavaşça duruyor. Omuzları hafifçe gerginleşiyor."),
            ({"reason_code": "UNREGISTERED_PERSISTENT_OBJECT", "trigger_span": ""}, None, None),
        )
        for decision, action_result, expected in removals:
            with self.subTest(decision=decision, action_result=action_result):
                self.assertEqual(game._remove_trigger_sentence(text, decision, action_result), expected)
        with fixed_town(self, 20261212):
            s = game.create_session(seed=11)
            assertions = (
                ("haydut görüyorum", True), ("karşımda ejderha var", True), ("barmenin adı Gromm", True),
                ("burada on asker var", True), ("Ben aslında kralım.", True), ("Kapı açık.", True),
                ("Etrafa bakıyorum.", False), ("Barmene merhaba diyorum.", False),
            )
            for phrase, expected in assertions:
                with self.subTest(phrase=phrase):
                    self.assertIs(game.is_player_world_assertion(phrase, session=s), expected)

    def test_nsafety_2_lives_in_the_part(self):
        self.assertEqual(set(NSAFETY_2) - set(routing_audit.re_exports(ROOT).get("narration_safety", ())), set())

    def test_the_safety_decision_answers_as_before(self):
        # safe and unsafe inputs from test_f04_greeting_agency_quality; the repaired one follows its invented-feeling
        # case (one sentence removed by _remove_trigger_sentence). Decisions captured on 612ce004 before the move.
        def decision(unsafe, reason_code, trigger_span):
            return {"unsafe": unsafe, "reason_code": reason_code, "trigger_span": trigger_span,
                    "scene_type": "exploration"}

        with fixed_town(self, 20261213):
            s = game.create_session(seed=11)
            world = json.dumps(s.world_state, sort_keys=True, default=str)
            safe = game._narration_safety_decision("içeri girersin.", "içeri giriyorum.", action_result={}, session=s)
            self.assertEqual(safe, decision(False, None, None))
            inspect = "Han girişindeki taş işçiliğini dikkatlice inceliyorum."
            unsafe = game._narration_safety_decision("Sonra hana girersin.", inspect, action_result={}, session=s)
            self.assertEqual(unsafe, decision(True, "INVENTED_PLAYER_ACTION", "girersin"))
            text = "Oymalar yıpranmış. Korkmuş hissedersin."
            first = game._narration_safety_decision(text, inspect, action_result={}, session=s)
            self.assertEqual(first, decision(True, "INVENTED_PLAYER_MENTAL_STATE", "hissedersin"))
            repaired = game._remove_trigger_sentence(text, first, {}, session=s)
            self.assertEqual(repaired, "Oymalar yıpranmış.")
            self.assertEqual(game._narration_safety_decision(repaired, inspect, action_result={}, session=s),
                             decision(False, None, None))
            self.assertEqual(json.dumps(s.world_state, sort_keys=True, default=str), world)


LWT = tuple(batch_names("lwt"))
LWT_S = tuple(batch_names("lwt-s"))


class LivingWorldTurnPart(unittest.TestCase):
    """T4.8 batch lwt: the campaign clock and scene seating helpers live in game_parts/living_world_turn.py."""

    def test_lwt_lives_in_the_part(self):
        self.assertEqual(set(LWT) - set(routing_audit.re_exports(ROOT).get("living_world_turn", ())), set())

    def test_lwt_s_lives_in_the_part(self):  # Plan 4 T5.5
        self.assertEqual(set(LWT_S) - set(routing_audit.re_exports(ROOT).get("living_world_turn", ())), set())

    def test_a_patched_uuid4_reaches_the_moved_clock(self):
        # an unconscious hero outside combat with no episode id gets one from game.uuid4 when the clock moves
        import campaign_time
        fixed = "00000000-0000-4000-8000-000000000015"
        with fixed_town(self, 20261370):
            s = game.create_session(seed=11)
            campaign_time.initialize(s.world_state)
            game._apply_player_damage(s.character["current_hp"], session=s)
            death = game.ensure_death_state(session=s)
            self.assertEqual(death["noncombat_next_save_at"], 6)
            death["noncombat_episode_id"] = None
            with patch.object(game, "uuid4", return_value=fixed) as made:
                result = game.advance_campaign_time(1, "wait", session=s)
        made.assert_called_once_with()
        self.assertEqual(game.ensure_death_state(session=s)["noncombat_episode_id"], fixed)
        self.assertEqual(result["elapsed_seconds"], 1)
        self.assertEqual(result["death_results"], [])

    def test_the_rule_order_is_read_from_game(self):
        # advance_campaign_time checks game.RULE_ORDER before the clock moves (K04): a patched, incomplete table refuses
        import campaign_time
        import event_order
        with fixed_town(self, 20261371):
            s = game.create_session(seed=11)
            campaign_time.initialize(s.world_state)
            clock = json.dumps(s.world_state["campaign_time"], sort_keys=True)
            with patch.object(game, "RULE_ORDER", {"effect_expiry": 0, "damage": 1, "death": 2}), \
                 self.assertRaises(event_order.UnresolvedRuleOrder) as caught:
                game.advance_campaign_time(60, "wait", session=s)
        self.assertEqual(str(caught.exception), "Rule order table is missing: regeneration")
        self.assertEqual(json.dumps(s.world_state["campaign_time"], sort_keys=True), clock)

    def test_living_world_session_helpers_use_the_given_session(self):  # Review Focus 4
        # both names read game._session() (measured on 30c48f41): record what it returns during the session= call
        # Plan 4 T5.5: advance_campaign_time joins (measured on 7bb78b5e); the clock exists only in s (D-447)
        real = game._session
        with fixed_town(self, 20261214):
            s = game.create_session(seed=11)
            s.world_state["locations"]["t14_square"] = {"id": "t14_square", "name": "Çeşme Meydanı", "type": "city",
                                                         "description": ""}
            s.world_state["location"] = "t14_square"
            s.world_state.pop("campaign_time", None)
            default_world = json.dumps(game._session().world_state, sort_keys=True, default=str)
            for name, args in (("ensure_campaign_clock", ()), ("_living_world_prompt_context", ()),
                               ("advance_campaign_time", (60, "wait"))):
                seen = []

                def record():
                    value = real()
                    seen.append(value)
                    return value

                with self.subTest(name=name), patch.object(game, "_session", side_effect=record):
                    answer = getattr(game, name)(*args, session=s)
                    self.assertTrue(seen)
                    self.assertTrue(all(value is s for value in seen))
                    if name == "ensure_campaign_clock":
                        self.assertIs(answer, s.world_state["campaign_time"])
                        self.assertEqual(answer["elapsed_seconds"], 0)
                    elif name == "advance_campaign_time":
                        self.assertEqual([answer[key] for key in ("elapsed_seconds", "requested_seconds",
                                                                  "remaining_seconds", "interrupted")], [60, 60, 0, False])
                        self.assertEqual(answer["before"]["detail"], "1 Mirtul 1501 DR — 09:00:00")
                        self.assertEqual(answer["death_results"], [])
                        self.assertEqual(s.world_state["campaign_time"]["elapsed_seconds"], 60)
                    else:
                        context = json.loads(answer)
                        self.assertEqual(context["location_id"], "t14_square")
                        self.assertEqual(context["location_name"], "Çeşme Meydanı")
            self.assertEqual(json.dumps(game._session().world_state, sort_keys=True, default=str), default_world)


NEWGAME = tuple(batch_names("newgame"))


class NewGamePart(unittest.TestCase):
    """T4.9 batch newgame: initialize_game lives in game_parts/new_game.py."""

    def test_newgame_lives_in_the_part(self):
        self.assertEqual(set(NEWGAME) - set(routing_audit.re_exports(ROOT).get("new_game", ())), set())

    def test_the_import_time_game_is_initialized_by_the_moved_function(self):  # Review Focus 3
        # game.py calls initialize_game at import time, after _bind_session_engine (functools.wraps sets __wrapped__)
        self.assertEqual(game.initialize_game.__wrapped__.__module__, "game_parts.new_game")
        character = game._DEFAULT_SESSION.character
        self.assertTrue(character["name"])
        self.assertGreater(character["max_hp"], 0)


COMBAT_1 = tuple(batch_names("combat-1"))
COMBAT_2 = tuple(batch_names("combat-2"))
COMBAT_3 = tuple(batch_names("combat-3"))


def _session_snapshot(session):
    return json.dumps([session.character, session.world_state], sort_keys=True, default=str)


class CombatFlowPart(unittest.TestCase):
    """T5.1 batches combat-1, combat-2 and combat-3: death, damage and combat turns live in game_parts/combat_flow.py."""

    def test_combat_1_lives_in_the_part(self):
        self.assertEqual(set(COMBAT_1) - set(routing_audit.re_exports(ROOT).get("combat_flow", ())), set())

    def test_combat_2_lives_in_the_part(self):
        self.assertEqual(set(COMBAT_2) - set(routing_audit.re_exports(ROOT).get("combat_flow", ())), set())

    def test_the_player_cannot_act_error_is_one_class(self):
        # the staying handler in game.py's _front_work re-raises PlayerCannotAct and swallows any other error (returns
        # None): the class require_player_can_act raises must be the class game.py's own handler names
        import world_threads
        with fixed_town(self, 20261310):
            s = game.create_session(seed=11)
            s.character["current_hp"] = 0
            s.world_state["player_combat_status"] = "unconscious"
            person = {"id": "t7_odunci", "name": "Odunculu Remzi"}
            with patch.object(game, "active_npcs", return_value=[person]), \
                 patch.object(world_threads, "by_id", return_value={"status": "accepted"}), \
                 patch.object(world_threads, "says_later", return_value=False):
                with self.assertRaises(game.PlayerCannotAct) as caught:
                    game._front_work({"id": "t7_is", "person_id": "t7_odunci"}, "Odun kırıyorum.", session=s)
        self.assertIs(type(caught.exception), game.PlayerCannotAct)
        self.assertEqual(str(caught.exception), "Bilinçsiz karakter eylem gerçekleştiremez.")
        self.assertTrue(issubclass(game.PlayerCannotAct, ValueError))

    def test_a_patched_uuid4_reaches_moved_combat_code(self):
        fixed = "00000000-0000-4000-8000-000000000007"
        with fixed_town(self, 20261311):
            s = game.create_session(seed=11)
            hp = s.character["current_hp"]
            with patch.object(game, "uuid4", return_value=fixed) as made:
                result = game._apply_player_damage(hp, session=s)
        made.assert_called_once_with()
        self.assertEqual(result["status"], "unconscious")
        self.assertEqual(s.world_state["death_state"]["noncombat_episode_id"], fixed)

    def test_combat_session_helpers_use_the_given_session(self):  # Review Focus 4
        # every name reads game._session() (measured on 36fb0ddd): record what it returns during the session= call;
        # each input exists only in the given session (D-447)
        real = game._session
        with fixed_town(self, 20261312):
            s = game.create_session(seed=11)
            s.character["max_hp"] = 40
            s.character["current_hp"] = 37
            s.world_state["death_state"] = {"mode": "IRONMAN"}
            s.world_state.pop("combat", None)
            s.world_state["player_combat_status"] = "t7_unknown"
            default_before = _session_snapshot(game._session())
            cases = (("ensure_death_state", ()), ("ensure_combat_state", ()), ("_apply_player_damage", (5,)),
                     ("_capture_combat_death_checkpoint", ()), ("_restore_combat_death_checkpoint", ("t7_cause",)))
            answers = {}
            for name, args in cases:
                seen = []

                def record():
                    value = real()
                    seen.append(value)
                    return value

                if name == "_capture_combat_death_checkpoint":
                    s.world_state["death_state"]["mode"] = "NORMAL"  # IRONMAN keeps no checkpoint
                with self.subTest(name=name), patch.object(game, "_session", side_effect=record):
                    answers[name] = getattr(game, name)(*args, session=s)
                    self.assertTrue(seen)
                    self.assertIs(seen[0], s)
                    # the restore checks the saved hero on a fresh candidate GameSession of its own; never the default
                    others = [value for value in seen if value is not s]
                    self.assertTrue(all(isinstance(value, game.GameSession) and value is not game._DEFAULT_SESSION
                                        for value in others))
                    if name != "_restore_combat_death_checkpoint":
                        self.assertEqual(others, [])
                    if name == "ensure_death_state":  # the restore below swaps s.world_state's dicts for copies
                        self.assertIs(answers[name], s.world_state["death_state"])
                        self.assertEqual(answers[name]["mode"], "IRONMAN")
                    if name == "ensure_combat_state":
                        self.assertIs(answers[name], s.world_state["combat"])
                        self.assertEqual(s.world_state["player_combat_status"], "active")
            self.assertEqual(answers["_apply_player_damage"]["hp_before"], 37)
            self.assertEqual(answers["_apply_player_damage"]["hp_after"], 32)
            self.assertEqual(answers["_restore_combat_death_checkpoint"]["cause"], "t7_cause")
            self.assertEqual(s.character["current_hp"], 32)  # the checkpoint was taken on s after the damage
            self.assertEqual(_session_snapshot(game._session()), default_before)

        # combat-2 (measured on the combat-2 base): attack, species, death-turn and scheduler helpers on a second
        # session whose Aasimar hero and enemies exist only there (D-447)
        from api.tests.test_death_system import start_test_combat
        from api.tests.test_species_traits import attack_fixture, make_session
        s2 = make_session("Aasimar", level=3)
        shrouded = {"id": "t7_golge", "name": "Gölge Avcısı", "combat_status": "active", "current_hp": 10,
                    "max_hp": 10, "armor_class": 10, "attack_bonus": 0, "damage_die": 8, "damage_dice": 1,
                    "damage_modifier": 0, "charisma_save_bonus": 0}
        attack_fixture(s2, shrouded)
        default_before = _session_snapshot(game._session())

        def on_s2(name, *args, **kwargs):
            seen = []

            def record():
                value = real()
                seen.append(value)
                return value

            with self.subTest(name=name), patch.object(game, "_session", side_effect=record):
                answer = getattr(game, name)(*args, session=s2, **kwargs)
                self.assertTrue(seen)
                self.assertTrue(all(value is s2 for value in seen))
            return answer

        with patch.object(game, "roll_d20", return_value=1):
            shroud = on_s2("resolve_species_trait_action", "celestial_revelation", form="necrotic_shroud")
        self.assertEqual([save["target_id"] for save in shroud["effects"]["saves"]], ["t7_golge"])
        with patch.object(game, "roll_d20", side_effect=[13, 18]), patch.object(game, "roll_damage", return_value=1):
            attack = on_s2("resolve_enemy_attack", shrouded)
        self.assertEqual(attack["attack_rolls"], [13, 18])
        start_test_combat(s2)
        enemy_id = "death-save-enemy"
        on_s2("_begin_combat_actor_turn", enemy_id)
        self.assertEqual(s2.world_state["combat"]["current_actor_id"], enemy_id)
        with patch.object(game, "resolve_enemy_attack", return_value={"action": "enemy_attack", "outcome": "miss"}):
            turns = on_s2("_resolve_enemy_turns_until_player")
        self.assertTrue(turns)
        self.assertEqual(s2.world_state["combat"]["current_actor_id"], "player")
        s2.character["current_hp"] = 0
        s2.world_state["player_combat_status"] = "unconscious"
        with patch.object(game, "roll_d20", return_value=9):
            death_turn = on_s2("_resolve_player_death_turn")
        self.assertEqual((death_turn["roll"], death_turn["outcome"]), (9, "failure"))
        self.assertEqual(_session_snapshot(game._session()), default_before)

    def test_a_patched_resolve_saving_throw_reaches_the_moved_species_action(self):
        # census import target: the moved resolve_species_trait_action reads game.resolve_saving_throw
        from api.tests.test_species_traits import attack_fixture, make_session
        s = make_session("Aasimar", level=3)
        attack_fixture(s, {"id": "t7_kurt", "name": "Kurt", "combat_status": "active", "current_hp": 10, "max_hp": 10,
                           "armor_class": 10, "charisma_save_bonus": 0})
        planted = {"selected_roll": 4, "outcome": "FAILURE", "t7_planted": True}
        with patch.object(game, "resolve_saving_throw", return_value=planted) as saved:
            result = game.resolve_species_trait_action("celestial_revelation", form="necrotic_shroud", session=s)
        saved.assert_called_once()
        self.assertIs(saved.call_args.kwargs["roll_fn"], game.roll_d20)
        self.assertIs(result["effects"]["saves"][0]["resolution"], planted)
        self.assertTrue(result["effects"]["saves"][0]["frightened"])

    def test_combat_death_checkpoint_round_trips_from_the_part(self):  # Review Focus 2
        with fixed_town(self, 20261313):
            default_before = _session_snapshot(game._DEFAULT_SESSION)
            s = game.create_session(seed=21)
            game.ensure_combat_state(session=s)
            character = json.dumps(s.character, sort_keys=True, default=str)
            death = dict(s.world_state["death_state"])
            combat = json.dumps(s.world_state["combat"], sort_keys=True, default=str)
            game._capture_combat_death_checkpoint(session=s)
            self.assertIsNotNone(s.world_state["death_state"]["combat_checkpoint"])
            damage = game._apply_player_damage(s.character["current_hp"], session=s)
            self.assertEqual((damage["status"], s.character["current_hp"]), ("unconscious", 0))
            resolution = game._restore_combat_death_checkpoint("t7_round_trip", session=s)
        self.assertEqual(resolution, {"mode": "NORMAL", "outcome": "rolled_back", "cause": "t7_round_trip",
                                      "rolled_back": True, "terminal": False})
        self.assertEqual(json.dumps(s.character, sort_keys=True, default=str), character)
        self.assertEqual(s.world_state["death_state"], {**death, "last_resolution": resolution})
        self.assertEqual(json.dumps(s.world_state["combat"], sort_keys=True, default=str), combat)
        self.assertEqual(_session_snapshot(game._DEFAULT_SESSION), default_before)

    def test_combat_3_lives_in_the_part(self):
        self.assertEqual(set(COMBAT_3) - set(routing_audit.re_exports(ROOT).get("combat_flow", ())), set())

    def test_combat_texts_answer_as_before(self):
        # expected lines captured on 36fb0ddd (unmoved) with p4t7-capture.py, on a bare GameSession(seed=5)
        s = game.GameSession(seed=5)
        self.assertEqual(game._public_combatant_label("player", player_fallback="Kara Yolcu", session=s), "Kara Yolcu")
        self.assertEqual(game._public_combatant_label("t7_yok", fallback="Yabancı Tüccar", session=s), "Yabancı Tüccar")
        s.world_state["npcs"] = [{"id": "t7_bekci", "name": "Bekçi Halil", "location": "x"}]
        self.assertEqual(game._public_combatant_label("t7_bekci", session=s), "Bekçi Halil")
        self.assertEqual(game._death_save_line({"roll": 12, "outcome": "success"}, session=s),
                         "Ölüm kurtarma zarın: 12. Karanlıkta yatıyorsun, bedenin sana uymuyor; hayata tutunuyorsun. "
                         "Ölüm kurtarma: 0 başarı, 0 başarısızlık.")
        self.assertEqual(game._death_save_line({"roll": 20, "outcome": "revived"}, session=s),
                         "Ölüm kurtarma zarın: 20. Bir anda ciğerlerine hava doluyor; gözlerini açıyorsun, canın az da "
                         "olsa geri döndü.")


COIN = tuple(batch_names("coin"))


class CoinPart(unittest.TestCase):
    """T5.2 batch coin: shop and purse helpers live in game_parts/coin.py."""

    def test_coin_lives_in_the_part(self):
        self.assertEqual(set(COIN) - set(routing_audit.re_exports(ROOT).get("coin", ())), set())

    def test_the_coin_left_behind_alias_is_money_owners_object(self):
        import money_owner
        self.assertIs(game.COIN_LEFT_BEHIND, money_owner.COIN_LEFT_BEHIND)

    def test_a_patched_create_shop_from_proposal_reaches_its_staying_caller(self):
        # merge_world_updates (stays in game.py until Task 14) calls create_shop_from_proposal bare
        proposal = {"name": "t8_Kuyu Dükkanı", "shopkeeper": {"name": "t8_Sekiz"}}
        keeper = {"id": "t8_keeper", "name": "Sekiz Usta"}
        with fixed_town(self, 20261320):
            s = game.create_session(seed=11)
            default_before = _session_snapshot(game._DEFAULT_SESSION)
            with patch.object(game, "create_shop_from_proposal",
                              return_value={"id": "t8_shop", "shopkeeper": keeper}) as made:
                created = s.merge_world_updates({"create_shops": [proposal]})
            self.assertEqual(_session_snapshot(game._DEFAULT_SESSION), default_before)
        made.assert_called_once_with(proposal)
        self.assertEqual(created, [keeper])

    def test_shop_requests_answer_as_before(self):
        # expected answers captured on 36fb0ddd (unmoved) with p4t8-capture.py
        cases = (("_shop_economy_request", "Bu kılıcın fiyatı ne kadar?", True),
                 ("_shop_economy_request", "Kapıyı yavaşça açıyorum.", False),
                 ("_explicit_campaign_shop_negative_request", "Burada dükkan açma, sadece yürüyelim.", True),
                 ("_explicit_campaign_shop_negative_request", "Dükkan sahibine selam veriyorum.", False),
                 ("_shop_presence_question", "Bu kasabada bir tüccar var mı?", True),
                 ("_shop_presence_question", "Tüccar burada bekliyor.", False))
        for name, text, expected in cases:
            with self.subTest(name=name, text=text):
                self.assertIs(getattr(game, name)(text), expected)


SAVE_1 = tuple(batch_names("save-1"))
SAVE_2 = tuple(batch_names("save-2"))


class SavefilePart(unittest.TestCase):
    """T5.3 batches save-1 and save-2: save validation, repair, writing and loading live in game_parts/savefile.py."""

    def test_save_1_lives_in_the_part(self):
        self.assertEqual(set(SAVE_1) - set(routing_audit.re_exports(ROOT).get("savefile", ())), set())

    def test_save_2_lives_in_the_part(self):
        self.assertEqual(set(SAVE_2) - set(routing_audit.re_exports(ROOT).get("savefile", ())), set())

    def test_the_save_repair_warnings_log_under_game(self):  # Review Focus 3
        # one broken row per repair function; the lines were captured on 2df1d98f (unmoved) with p4t9-preflight.py
        with fixed_town(self, 20261330), tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "t9_repair.json"
            game.save_game(path, session=game.create_session(seed=31))
            payload = json.loads(path.read_text(encoding="utf-8"))
            flags = payload["world_state"].setdefault("flags", {})
            flags["money_declined"] = {"t9_osman": "bad"}  # _repair_dilim1_fields (economic_actions.repair_declines)
            flags["active_npc_id"] = "t9_nobody"  # _repair_dilim2_fields: a talk with someone not in the save
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            loaded = game.create_session(seed=32)
            with self.assertLogs("game", "WARNING") as logged:
                game.load_game(path, session=loaded)
        self.assertEqual([(record.name, record.levelname, record.getMessage()) for record in logged.records],
                         [("game", "WARNING", "dilim1 load repaired: money_declined.t9_osman"),
                          ("game", "WARNING", "dilim2 load repaired: talk:nobody")])

    def test_save_round_trip_after_the_move(self):  # Review Focus 3
        with fixed_town(self, 20261331), tempfile.TemporaryDirectory() as folder:
            default_before = _session_snapshot(game._DEFAULT_SESSION)
            s = game.create_session(seed=31)
            path = Path(folder) / "t9_round.json"
            game.save_game(path, session=s)
            saved = json.loads(path.read_text(encoding="utf-8"))
            loaded = game.create_session(seed=33)
            game.load_game(path, session=loaded)
            again = json.loads(json.dumps(game.serialize_game_state(session=loaded), ensure_ascii=False))
            self.assertEqual(_session_snapshot(game._DEFAULT_SESSION), default_before)
        self.assertEqual(saved["format"], "ai-dnd-save")
        self.assertEqual(again, saved)

    def test_a_patched_os_reaches_the_moved_save_game(self):
        # save_game reads os for its fsync only; the replace is pathlib's
        with fixed_town(self, 20261332), tempfile.TemporaryDirectory() as folder:
            s = game.create_session(seed=31)
            with patch.object(game, "os", wraps=os) as patched:
                written = game.save_game(Path(folder) / "t9_os.json", session=s)
            self.assertTrue(written.is_file())
        patched.fsync.assert_called_once()
        self.assertEqual([call[0] for call in patched.mock_calls], ["fsync"])

    def test_save_session_helpers_use_the_given_session(self):  # Review Focus 4
        # serialize_game_state reads game._session() only: every read must return the given session; the name and the
        # narration exist only there (D-447)
        real = game._session
        with fixed_town(self, 20261333):
            s = game.create_session(seed=31)
            s.character["name"] = "t9_Yalnız Kâtip"
            s.recent_dm_narrations.append("t9_yalnız anlatı")
            default_before = _session_snapshot(game._session())
            seen = []

            def record():
                value = real()
                seen.append(value)
                return value

            with patch.object(game, "_session", side_effect=record):
                payload = game.serialize_game_state(session=s)
            self.assertTrue(seen)
            self.assertTrue(all(value is s for value in seen))
            self.assertEqual(payload["player"]["name"], "t9_Yalnız Kâtip")
            self.assertEqual(payload["recent_dm_narrations"][-1], "t9_yalnız anlatı")
            self.assertEqual(_session_snapshot(game._session()), default_before)


NEVERWINTER = {"campaign_start": {
    "setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north", "starting_location_id": "fr:city:neverwinter"}}


class _UnclearFrontReading:
    """Answers the flag-on front reading (the turn's classifier call) with a valid "unclear" reading, so the old chain
    stays in charge without the "Classifier unavailable" warning; every other call goes to the client the test uses."""

    def __init__(self, inner):
        self.inner = inner

    def chat(self, *args, **kwargs):
        if "front" not in ((kwargs.get("format") or {}).get("properties") or {}):
            return self.inner.chat(*args, **kwargs)
        front = {"kind": "unclear", "person_id": "none", "place_id": "none", "offer_id": "none", "thing_id": "none",
                 "answer": "none", "inside": False, "timing": "now"}
        packet = {"intent": "narrative", "action": "narrative", "target": {"type": "none", "reference": ""},
                  "completion": "unclear", "confidence": 0.9, "front": front}
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}

    def __getattr__(self, name):
        return getattr(self.inner, name)


class TurnIdentityNames(unittest.IsolatedAsyncioTestCase):
    """Plan 5 Task 2 (Ruling J): turn code hands the engine module, not its own module, to arrival and heard rumours.

    Inputs measured on 2f0cc18c in both flags (ledger Task 2 Step 1); the same literals hold with the flag on and off.
    """

    async def asyncSetUp(self):
        await campaign_api.CampaignApiTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await campaign_api.CampaignApiTests.asyncTearDown(self)

    async def _session_id(self, seed):
        with fixed_town(self, seed):
            created = await self.http.post("/api/game/campaigns", json=NEVERWINTER)
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()["session_id"]

    async def _turn(self, session_id, **body):
        response = await self.http.post(f"/api/game/sessions/{session_id}/turn",
                                        json={"action_id": str(uuid.uuid4()), **body})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_a_local_place_turn_hands_the_game_module_to_arrival(self):
        import arrival_narration
        session_id = await self._session_id(20261401)
        adapter = self.app.state.ollama_adapter
        with patch.object(adapter, "_client", _UnclearFrontReading(adapter._client)), \
                patch.object(arrival_narration, "arrive", wraps=arrival_narration.arrive) as arrive, \
                self.assertNoLogs("ai_dnd.api.ollama", level="WARNING"):
            await self._turn(session_id, message="Arşive gidiyorum.")
        arrive.assert_called_once()
        self.assertIs(arrive.call_args.args[0], game)

    async def test_heard_rumours_gets_the_game_module_from_the_turn(self):
        import heard_rumours
        session_id = await self._session_id(20261402)
        world = self.manager.get(session_id).game_session.world_state
        npc = {"id": "npc_t2_edric", "name": "Edric", "role": "Yolcu", "location": world["location"],
               "reality_layer": "PROCEDURAL_LOCAL_FICTION"}
        local_dialogue.ensure_personal_profile(npc)
        world["npcs"].append(npc)
        with patch.object(self.app.state.ollama_adapter, "_client",
                          _UnclearFrontReading(rumour_turn._Client(rumour_turn.MENTION))), \
                patch.object(heard_rumours, "record_mention", wraps=heard_rumours.record_mention) as record, \
                self.assertNoLogs("ai_dnd.api.ollama", level="WARNING"):
            await self._turn(session_id, message="Buralarda duyduğun bir şey var mı?", target_id="npc_t2_edric",
                             interaction_mode="say")
        record.assert_called_once()
        self.assertIs(record.call_args.args[0], game)
        self.assertEqual(len(world["heard_rumours"]), 1)

    async def test_a_preparsed_local_person_reaches_the_turn(self):
        # the locals().get("preparsed_scene_intent") branch of _run_player_turn_internal creates the proposed person
        session_id = await self._session_id(20261403)
        world = self.manager.get(session_id).game_session.world_state
        before = {npc["id"] for npc in world["npcs"]}
        with patch.object(self.app.state.ollama_adapter, "_client", local_person.LocalPersonModel()):
            body = await self._turn(session_id, interaction_mode="say",
                                    message="Sahilde bir balıkçı bulup liman söylentilerini onunla konuşmak istiyorum.")
        self.assertEqual((body["turn_outcome"]["action"], body["turn_outcome"]["status"]),
                         ("dialogue", "created_local_person"))
        new = [(npc["id"], npc["name"], npc["role"]) for npc in world["npcs"] if npc["id"] not in before]
        self.assertEqual(new, [("npc_001", "Neris", "kıyı balıkçısı")])


FRONT_1 = tuple(batch_names("front-1"))
FRONT_2 = tuple(batch_names("front-2"))
FRONT_3 = tuple(batch_names("front-3"))
TRANSIENTS = ("_front_coin", "_economic_turn_key", "_coin_rest_hint")
INTERNAL_TURN = {  # the same in both flags; captured on f1bc2ad1 (unmoved)
    "walk": {"narration": "Oraya giden bir yol bilmiyorsun.", "model_calls": None,
             "action": ("travel", "unverified", None), "reads": True, "only_s": True, "location": "forest", "hp": 12,
             "default_unchanged": True},
    "down": {"narration": "Ölüm kurtarma zarın: 15. Karanlıkta yatıyorsun, bedenin sana uymuyor; hayata tutunuyorsun. "
                          "Ölüm kurtarma: 1 başarı, 0 başarısızlık.", "model_calls": 0,
             "action": ("death_save", "resolved", None), "reads": True, "only_s": True, "location": "forest", "hp": 0,
             "default_unchanged": True},
}


class TurnFrontPart(unittest.TestCase):
    """T6.1 batch front-1: thread turns, intent execution and place turns live in game_parts/turn_front.py."""

    def test_front_1_lives_in_the_part(self):
        self.assertEqual(set(FRONT_1) - set(routing_audit.re_exports(ROOT).get("turn_front", ())), set())

    def test_turn_session_helpers_use_the_given_session(self):  # D-447
        # _execute_intent_internal reads game._session() only: every read must return the given session, and the place
        # it is asked for exists only there; the answer was captured on 2f2d45a1 (unmoved), both flags
        real = game._session
        with fixed_town(self, 20261410):
            s = game.create_session(seed=11)
            s.world_state["location"] = "forest"
            s.world_state["locations"]["t6_kuyu"] = {"id": "t6_kuyu", "name": "Kuyu Başı", "type": "city",
                                                     "description": ""}
            default = game._session()
            default_before = _session_snapshot(default)
            seen = []

            def record():
                value = real()
                seen.append(value)
                return value

            with patch.object(game, "_session", side_effect=record):
                out = game._execute_intent_internal(
                    {"intent": "travel", "target": {"type": "location", "reference": "Kuyu Başı"}},
                    "Kuyu Başı'na gidiyorum.", session=s)
            self.assertEqual(out, {"action": "travel", "success": False, "status": "unverified", "state_changes": [],
                                   "completion": "completed", "target_reference": "Kuyu Başı", "target": "t6_kuyu",
                                   "previous_location": "forest",
                                   "direct_response": "Oraya giden bir yol bilmiyorsun."})
            self.assertTrue(seen)
            self.assertTrue(all(value is s for value in seen))
            # _clear_turn_transients takes its session as an argument, as api/main.py calls it; coin only s holds
            s._front_coin, s._economic_turn_key, s._coin_rest_hint = 7, "t6_tur", "t6_artık"
            default_transients = [getattr(default, name, None) for name in TRANSIENTS]
            game._clear_turn_transients(s)
            self.assertEqual([getattr(s, name) for name in TRANSIENTS], [0, None, ""])
            self.assertEqual([getattr(default, name, None) for name in TRANSIENTS], default_transients)
            self.assertEqual(s.world_state["location"], "forest")
            self.assertEqual(_session_snapshot(default), default_before)
        # T6.2: _run_player_turn_internal takes no session and reads game._session() only (the bound engine wrapper
        # takes session=); every read must return s; "walk" asks for a place only s has, "down" gives only s 0 hit
        # points (the default session would walk); the answers were captured on f1bc2ad1 (unmoved), both flags
        for flag in ("", "1"):
            for kind in ("walk", "down"):
                with self.subTest(helper="_run_player_turn_internal", flag=flag, kind=kind):
                    self.assertEqual(_internal_turn_outcome(self, 20261460, flag, kind), INTERNAL_TURN[kind])

    def test_front_2_lives_in_the_part(self):
        self.assertEqual(set(FRONT_2) - set(routing_audit.re_exports(ROOT).get("turn_front", ())), set())

    def test_turn_money_helpers_use_the_given_session(self):  # Review Focus 5, D-447
        # The coin and the person exist only in s: every game._session() read must return s and the default session
        # stays as it was; the answers were captured on 26f0b226 (unmoved), both flags; fixed_town gives the second
        # session of this test the next seed (20261421)
        with self.subTest(helper="_tell_the_coin"):
            self.assertEqual(_money_helper_outcome(self, "_tell_the_coin", 20261420), {
                "cards": [("prepared", "gift", "t7_oren", 5, "t7-tip")], "purse": 500, "coin_paid": None,
                "narration": "Kese şıngırdıyor. Oren için teklif hazır: en çok 5 bakır. Onaylarsan işlem yapılır.",
                "all_reads_given": True, "default_unchanged": True})
        with self.subTest(helper="_the_rest_of_the_line"):
            self.assertEqual(_money_helper_outcome(self, "_the_rest_of_the_line", 20261420), {
                "said": [("şehirde ne var?", True, "t7_oren", "t7-line", "t7-session", "say", True)],
                "same_result": True, "narration": "Kese şıngırdıyor. Kuzey kapısında bir kule var.", "rest_left": "",
                "all_reads_given": True, "default_unchanged": True})
        with self.subTest(helper="_sleep_after_walk"):  # T6.1c; the third session of this test: seed 20261432
            self.assertEqual(_money_helper_outcome(self, "_sleep_after_walk", 20261430), {  # captured on 25afc54e
                "cards": [("prepared", "room", "t8_marek", None, "t8-walk")], "purse": 500,
                "narration": "Hana giriyorsun. Marek başıyla merdivenleri gösteriyor. “Gecelik 50 bakır.” Marek için "
                             "teklif hazır: en çok 50 bakır. Onaylarsan işlem yapılır.",
                "coin_seen_by": None, "rest_left": "", "all_reads_given": True, "default_unchanged": True})

    def test_a_coin_without_a_reading_answers_as_before(self):
        # D-429's two lines (its row: the beer twin, the named non-innkeeper with a bed asked for), each in both flags,
        # three rows as on 26f0b226; the flag-on beer row is the Task 14 outcome (D-429 fix)
        room = ("Marek başıyla merdivenleri gösteriyor. “Gecelik 50 bakır.” Marek için teklif hazır: en çok 50 bakır. "
                "Onaylarsan işlem yapılır.")
        expected = {
            ("barmene 2 bakır verip bi bira istiyorum", "0"): {
                "route": None, "seen": [], "decision": None, "action": ("shop_offer", "offer_open"), "cards": [],
                "counter": "none", "purse": 500, "narration": "Marek tezgâha dayanıyor. “Bira 4 bakır. Kaç tane?”"},
            ("barmene 2 bakır verip bi bira istiyorum", "1"): {  # D-429 fixed: the counter opens as with the flag off
                "route": "fallback:failed", "seen": [(None, None, 2)], "decision": None,
                "action": ("shop_offer", "offer_open"), "cards": [], "counter": "none", "purse": 500,
                "narration": "Marek tezgâha dayanıyor. “Bira 4 bakır. Kaç tane?” Uzattığın para hesaba katılmadı; "
                             "kesende kalıyor."},
            ("Aldric'e 1 gümüş verip oda tutuyorum", "0"): {
                "route": None, "seen": [], "decision": None, "action": ("lodging", "offered"),
                "cards": [("prepared", "room", "barman")], "counter": None, "purse": 500, "narration": room},
            ("Aldric'e 1 gümüş verip oda tutuyorum", "1"): {
                "route": "fallback:failed", "seen": [(None, None, 10)], "decision": None, "action": ("lodging", "offered"),
                "cards": [("prepared", "room", "barman")], "counter": None, "purse": 500,
                "narration": f"{room} Uzattığın para hesaba katılmadı; kesende kalıyor."},
        }
        for (line, flag), outcome in expected.items():
            with self.subTest(line=line, flag=flag):
                self.assertEqual(_coin_line_outcome(self, 20261423, flag, line), outcome)

    def test_front_3_lives_in_the_part(self):
        self.assertEqual(set(FRONT_3) - set(routing_audit.re_exports(ROOT).get("turn_front", ())), set())



def _money_helper_outcome(test, helper, seed):
    """What `helper` does with session=s when the coin and the person it needs exist only in s (D-447)."""
    from money_owner import CoinDecision
    real = game._session
    with fixed_town(test, seed), patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
        s = game.create_session(seed=7)
        w = s.world_state
        here = w["location"]
        oren = {"id": "t7_oren", "name": "Oren", "role": "Yolcu", "location": here, "current_hp": 10}
        w["npcs"] = [oren]
        w["currency"] = {"player": 500, "t7_oren": 100}
        default = game._session()
        default_before = _session_snapshot(default)
        seen = []

        def record():
            value = real()
            seen.append(value)
            return value

        result = {"narration": "Kese şıngırdıyor.",
                  "action_result": {"action": "narrative", "status": "resolved", "state_changes": ["currency"]}}
        if helper == "_tell_the_coin":
            s._economic_turn_key = "t7-tip"
            s._coin_decision = CoinDecision("gift", "t7_oren", 5, 0, None, "model", here)
            s._coin_paid = (5, oren, here)
            with patch.object(game, "_session", side_effect=record):
                game._tell_the_coin(result, session=s)
            offers = w.get("flags", {}).get("economic_offers", {})
            facts = {"cards": sorted((data["status"], data["proposal"]["purpose"], data["proposal"]["recipient_id"],
                                      data["proposal"]["amount_cp"], data["proposal"]["source_action_id"])
                                     for data in offers.values()),
                     "purse": w["currency"]["player"], "coin_paid": s._coin_paid, "narration": result["narration"]}
        elif helper == "_sleep_after_walk":
            # the walk has moved the player; the innkeeper, the turn key and the line's rest exist only in s
            w["npcs"].append({"id": "t8_marek", "name": "Marek", "role": "Barmen", "location": here, "current_hp": 10})
            w["currency"]["t8_marek"] = 0
            s._economic_turn_key = "t8-walk"
            s._front_rest = "t8-kalan"
            walked = {"narration": "Hana giriyorsun.",
                      "action_result": {"action": "move", "status": "completed", "state_changes": ["location"]}}
            with patch.object(game, "_session", side_effect=record):
                game._sleep_after_walk(walked, "hana gidip bi oda tutayım", "t8-the-street", None, session=s)
            offers = w.get("flags", {}).get("economic_offers", {})
            facts = {"cards": sorted((data["status"], data["proposal"]["purpose"],
                                      data["proposal"].get("recipient_id"), data["proposal"].get("amount_cp"),
                                      data["proposal"].get("source_action_id"))
                                     for data in offers.values()),
                     "purse": w["currency"]["player"], "narration": walked["narration"],
                     "coin_seen_by": walked["action_result"].get("coin_seen_by"), "rest_left": s._front_rest}
        else:
            s._front_rest = "şehirde ne var?"
            s._front_read = {"id": "t7_oren"}
            said = []

            def dispatch(*args, **kwargs):
                said.append((args[0], args[1] is s.messages, args[2], args[4], args[5], args[7], game._session() is s))
                return {"messages": s.messages, "narration": "Kuzey kapısında bir kule var.", "model_calls": 0,
                        "action_result": {"action": "dialogue", "status": "resolved", "npc_id": "t7_oren",
                                          "state_changes": []}}

            with patch.object(game, "_session", side_effect=record), \
                    patch.object(game, "_dispatch_player_turn", side_effect=dispatch), \
                    patch("api.ollama_adapter.model_calls_left", return_value=True):
                out = game._the_rest_of_the_line(result, s.messages, "t7-line", "t7-session", here, session=s)
            facts = {"said": said, "same_result": out is result, "narration": result["narration"],
                     "rest_left": s._front_rest}
        facts["all_reads_given"] = bool(seen) and all(value is s for value in seen)
        facts["default_unchanged"] = _session_snapshot(default) == default_before
    return facts


def _coin_line_outcome(test, seed, flag, line):
    """One coin line at the counter (test_economic_room's table plus a named smith), the flag set, no model answer."""
    import campaign_time
    import money_owner
    original = game._coin_without_a_reading
    with fixed_town(test, seed), patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": flag}), \
            patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
        s = game.create_session(seed=7)
        w = s.world_state
        here = w["location"]
        w["npcs"] = [
            {"id": "barman", "name": "Marek", "role": "Barmen", "location": here, "current_hp": 10},
            {"id": "guest", "name": "Oren", "role": "Yolcu", "location": here, "current_hp": 10},
            {"id": "t7_aldric", "name": "Aldric", "role": "Demirci", "location": here, "current_hp": 10},
        ]
        w["currency"] = {"player": 500, "barman": 100, "guest": 100, "t7_aldric": 100}
        w.setdefault("flags", {})["turn_index"] = 3
        campaign_time.initialize(w)
        seen = []

        def watch(*args):
            original(*args)
            decided = money_owner.current(s)
            seen.append((args[1], None if decided is None else (decided.kind, decided.npc_id, decided.amount_cp),
                         s._front_coin))

        with patch("game._coin_without_a_reading", side_effect=watch):
            result = s.run_player_turn(line)
        decided = money_owner.current(s)
        action = result.get("action_result") or {}
        offers = w.get("flags", {}).get("economic_offers", {})
        counter = w["flags"].get("counter_offer_v1")
        return {"route": getattr(s, "_front_route", None), "seen": seen,
                "decision": None if decided is None else (decided.kind, decided.npc_id, decided.amount_cp),
                "action": (action.get("action"), action.get("status")),
                "cards": sorted((data["status"], data["proposal"]["purpose"], data["proposal"]["recipient_id"])
                                for data in offers.values()),
                "counter": None if counter is None else counter.get("tender_cp", "none"),
                "purse": w["currency"]["player"], "narration": result.get("narration")}


class ThreadGateRoute(unittest.IsolatedAsyncioTestCase):
    """The turn path reads game._thread_gate; the gate reaches _carry_out_thread_turn (test_thread_gate's table)."""

    asyncSetUp = thread_gate_tests.ThreadTable.asyncSetUp
    asyncTearDown = thread_gate_tests.ThreadTable.asyncTearDown
    campaign_with_npc = thread_gate_tests.ThreadTable.campaign_with_npc
    open_job = thread_gate_tests.ThreadTable.open_job
    line = thread_gate_tests.ThreadTable.line
    offer = thread_gate_tests.ThreadTable.offer
    status = thread_gate_tests.ThreadTable.status

    async def test_a_patched_thread_gate_reaches_its_moved_caller(self):
        with fixed_town(self, 20261411):
            await self.open_job()
        self.offer()
        with patch.object(game, "_thread_gate", wraps=game._thread_gate) as gate:
            await self.line("olur", "Güzel, başla bakalım.")
        gate.assert_called()
        self.assertEqual(self.status(), "accepted")


class FrontReadAheadRoute(unittest.IsolatedAsyncioTestCase):
    """api/main.py reads the front reading as session.front_read_ahead: the session finds it in game's namespace
    (test_front_proposal's table, flag on, the reading scripted)."""

    asyncSetUp = front_tests.FrontTable.asyncSetUp
    asyncTearDown = front_tests.FrontTable.asyncTearDown
    campaign_with_npc = front_tests.FrontTable.campaign_with_npc
    open_job = front_tests.FrontTable.open_job
    begin = front_tests.FrontTable.begin
    line = front_tests.FrontTable.line
    routes = front_tests.FrontTable.routes

    async def test_a_patched_front_read_ahead_reaches_its_caller(self):
        with fixed_town(self, 20261422):
            await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        line = "şu adamın bu kasaba hakkında ne düşündüğünü merak ettim"
        with patch.object(game, "front_read_ahead", wraps=game.front_read_ahead) as reading:
            reply = await self.line(line)
        reading.assert_called_once()
        self.assertEqual(reading.call_args.args, (line,))
        self.assertIs(reading.call_args.kwargs["session"], self.session)
        self.assertIn(self.client.narration, reply["narration"])
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")


TURN_1 = tuple(batch_names("turn-1"))
TURN_2 = tuple(batch_names("turn-2"))
TURN_3 = tuple(batch_names("turn-3"))
NOTHING_CHANGED = "Bu hamle tamamlanamadı; dünya durumu değişmedi."


class TurnPart(unittest.TestCase):
    """T6.1 batch turn-1: the owned and keyed turn and the turn dispatch live in game_parts/turn.py."""

    def test_turn_1_lives_in_the_part(self):
        self.assertEqual(set(TURN_1) - set(routing_audit.re_exports(ROOT).get("turn", ())), set())

    def test_turn_2_lives_in_the_part(self):  # T6.1e: _owner_module_reply only (_narrate_resolved_turn held, Task 4)
        self.assertEqual(set(TURN_2) - set(routing_audit.re_exports(ROOT).get("turn", ())), set())

    def test_turn_3_lives_in_the_part(self):  # T6.2: _run_player_turn_internal, whole
        self.assertEqual(set(TURN_3) - set(routing_audit.re_exports(ROOT).get("turn", ())), set())

    def test_an_owner_command_is_answered_for_the_given_session(self):  # D-447, T6.1e
        # the moved _owner_module_reply reads game._session(): /equip clear empties the hands only s has (a weapon
        # only in s), with no model call, and the default session stays; captured on 0e43d241 (unmoved), both flags
        expected = {flag: {"narration": "Elini boşalttın.", "model_calls": 0, "action": ("equip", "resolved", True),
                           "equipment": {"main_hand": None, "off_hand": None}, "default_unchanged": True}
                    for flag in ("", "1")}  # the same in both flags
        for flag, outcome in expected.items():
            with self.subTest(flag=flag):
                self.assertEqual(_owner_turn_outcome(self, 20261450, flag), outcome)

    def test_the_turn_resolved_signal_is_one_class(self):
        # _run_player_turn_internal (in game.py until turn-3) raises TurnResolved; the moved _dispatch_turn_body catches
        # it and narrates the resolved turn, with and without an action id
        with fixed_town(self, 20261440):
            s = game.create_session(seed=13)
            resolved = game.ResolvedTurn(action_result={"action": "look"}, fallback_response="t9", raw_result={})

            def internal(*args, **kwargs):
                raise game.TurnResolved({"t9": "raw"}, resolved)

            for action_id, session_id in ((None, None), ("t9-act", "t9-session")):
                with self.subTest(action_id=action_id), \
                        patch.object(game, "_run_player_turn_internal", side_effect=internal) as inner, \
                        patch.object(game, "_narrate_resolved_turn", return_value={"narration": "t9-told"}) as told:
                    out = game._dispatch_turn_body("t9 bakıyorum", s.messages, None, None, "say", action_id,
                                                   session_id, None, None, session=s)
                    self.assertEqual(out, {"narration": "t9-told"})
                    inner.assert_called_once()
                    told.assert_called_once_with(resolved, "t9 bakıyorum", s.messages, None)
        # one object under both names: the re-export binds game.TurnResolved to the part's class (tests may not name a
        # part module through sys.modules, routing R2), and the catch above reads game.TurnResolved
        self.assertEqual((game.TurnResolved.__module__, game.ResolvedTurn.__module__),
                         ("game_parts.turn", "game_parts.turn"))

    def test_resolved_turn_is_the_same_dataclass(self):  # Ruling L; captured on 8c18ca6b (unmoved)
        missing = dataclasses.MISSING
        self.assertTrue(dataclasses.is_dataclass(game.ResolvedTurn))
        self.assertEqual([(f.name, f.default, f.default_factory) for f in dataclasses.fields(game.ResolvedTurn)],
                         [
            ("action_result", missing, missing), ("fallback_response", missing, missing),
            ("raw_result", missing, missing), ("requires_narration", True, missing),
            ("safety_reason_code", None, missing), ("safety_handling", "accepted", missing),
            ("quest_outcomes", None, missing), ("npc_target", None, missing), ("target_id", None, missing),
            ("lore_context", None, missing), ("intent_source", "deterministic", missing),
            ("intent_model_calls", 0, missing), ("messages", None, missing), ("allow_new_npcs", False, missing),
            ("allow_new_features", False, missing), ("allow_new_locations", False, missing),
            ("allow_new_shops", False, missing), ("expected_location_change", False, missing),
            ("scene_plan", None, missing), ("quest_world_before", None, missing)])

    def test_a_failed_turn_rolls_back_from_the_part(self):  # Review Focus 3, the test_roadmap_c10_primal_failure shape
        # plain: the keyed turn restores s on IntentInfrastructureError and says nothing changed; check: the owned turn
        # restores its own snapshot of s and raises again. Both flags; captured on 8c18ca6b (unmoved)
        expected = {}
        plain = {"seen": [("Kapıyı itiyorum.", True)],
                 "reply": {"narration": NOTHING_CHANGED,
                           "action_result": {"action": "unknown", "status": "infrastructure_failure", "success": False,
                                             "state_changes": [], "infrastructure_code": "intent_timeout",
                                             "direct_response": NOTHING_CHANGED}},
                 "same": True, "runtime_same": True, "marker": False, "default_unchanged": True}
        check = {"seen": [("Kapıyı itiyorum.", True)], "reply": "RuntimeError: t9 failed turn", "same": True,
                 "runtime_same": True, "marker": False, "default_unchanged": True}
        for flag in ("", "1"):  # the same in both flags
            expected[(flag, "plain")], expected[(flag, "check")] = plain, check
        for (flag, kind), outcome in expected.items():
            with self.subTest(flag=flag, kind=kind):
                self.assertEqual(_failed_turn_outcome(self, 20261441, flag, kind), outcome)

    def test_a_patched_dispatch_reaches_the_moved_keyed_turn(self):
        # run_player_turn -> _run_player_turn_owned -> _run_player_turn -> _run_player_turn_keyed reads
        # game._dispatch_player_turn; both flags, captured on 8c18ca6b (unmoved)
        expected = {flag: {"seen": [("Kapıyı itiyorum.", "t9-act", "t9-session", True)],
                           "narration": "Kapı gıcırdayarak açılıyor.", "action": ("narrative", "resolved"),
                           "key_cleared": None, "default_unchanged": True}
                    for flag in ("", "1")}  # the same in both flags
        for flag, outcome in expected.items():
            with self.subTest(flag=flag):
                self.assertEqual(_dispatched_turn_outcome(self, 20261445, flag), outcome)


SPEECH_LINE = "Buralarda duyduğun bir şey var mı?"


class TurnCoreRoute(unittest.IsolatedAsyncioTestCase):
    """T6.2: one person's speech turn over HTTP (TurnIdentityNames' heard-rumours shape) reaches the speech trail and
    the finalize call of _run_player_turn_internal itself; both flags, captured on f1bc2ad1 (unmoved)."""

    maxDiff = None
    asyncSetUp = TurnIdentityNames.asyncSetUp
    asyncTearDown = TurnIdentityNames.asyncTearDown
    _session_id = TurnIdentityNames._session_id
    _turn = TurnIdentityNames._turn

    async def _speech_turn(self, seed, flag):
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": flag}):
            session_id = await self._session_id(seed)
            world = self.manager.get(session_id).game_session.world_state
            npc = {"id": "npc_t11_edric", "name": "Edric", "role": "Yolcu", "location": world["location"],
                   "reality_layer": "PROCEDURAL_LOCAL_FICTION"}
            local_dialogue.ensure_personal_profile(npc)
            world["npcs"].append(npc)
            with patch.object(self.app.state.ollama_adapter, "_client", rumour_turn._Client(rumour_turn.MENTION)):
                return await self._turn(session_id, message=SPEECH_LINE, target_id="npc_t11_edric",
                                        interaction_mode="say")

    async def test_the_speech_debug_trail_patch_still_reaches_the_turn(self):  # D-344
        # _speech_debug_trail stays in game.py (never moved) and writes through game.open, so a game.open patch must
        # still see the turn's own speech record after the turn moves
        for flag in ("", "1"):
            with self.subTest(flag=flag):
                with patch.dict(os.environ, {"AI_DND_SPEECH_DEBUG": "t11-speech-trail.jsonl"}), \
                        patch.object(game, "open", create=True) as opened:
                    await self._speech_turn(20261466, flag)
                written = [json.loads(c.args[0])
                           for c in opened.return_value.__enter__.return_value.write.call_args_list]
                self.assertEqual({
                    "opened": [(c.args, c.kwargs) for c in opened.call_args_list],
                    "records": [(r.get("route"), r.get("player"), r.get("npc_id"), sorted(r)) for r in written],
                }, {  # the same in both flags; one record, the turn's own (no free_v1 route record on this path)
                    "opened": [(("t11-speech-trail.jsonl", "a"), {"encoding": "utf-8"})],
                    "records": [(None, SPEECH_LINE, "npc_t11_edric", [
                        "at", "before_finalize", "cleaned", "finalize_changed_text", "history_echo",
                        "invalid_or_empty", "model_lore_claims", "model_raw", "model_world_updates", "npc_id",
                        "npc_name", "player", "safe_narration", "safety", "shown", "unverified_claim_in_prompt"])],
                })

    async def test_the_narrative_adapter_reaches_the_moved_turn(self):  # Review Focus 4 (amended after G6a)
        # the app installs the adapter once (create_app); the turn's own finalize_narration(...) call (the only one that
        # passes attributed_speech= and python_town_response=) must reach the adapter's wrapper through
        # game.finalize_narration; the wrapped original is counted; counts measured on f1bc2ad1 (unmoved)
        install_narrative_context_adapter(game)
        finalize = game.finalize_narration
        cell = finalize.__closure__[finalize.__code__.co_freevars.index("original_finalize")]
        original = cell.cell_contents
        for flag in ("", "1"):
            with self.subTest(flag=flag):
                counted = MagicMock(wraps=original)
                cell.cell_contents = counted
                try:
                    await self._speech_turn(20261468, flag)
                finally:
                    cell.cell_contents = original
                both = [c for c in counted.call_args_list
                        if {"attributed_speech", "python_town_response"} <= set(c.kwargs)]
                self.assertEqual(len(both), 1)
                self.assertEqual({
                    "calls": [sorted(c.kwargs) for c in counted.call_args_list],
                    "turn_call": (both[0].args[1], both[0].args[2].get("id"),
                                  both[0].kwargs["attributed_speech"].get("spoken_text")),
                }, {  # the same in both flags: the original finalize ran once, from the turn's own call
                    "calls": [["attributed_speech", "fallback_reason_code", "python_town_response",
                               "supported_player_claims"]],
                    "turn_call": (SPEECH_LINE, "npc_t11_edric", rumour_turn.SPOKEN),
                })


def _failed_turn_outcome(test, seed, flag, kind):
    """A turn whose dispatch marks s and rolls its dice, then fails: what s, the default session and the reply show."""
    feature = sorted(game.CHECK_FEATURES)[0]
    with fixed_town(test, seed), patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": flag}), \
            patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
        s = game.create_session(seed=13)
        default = game._session()
        default_before = _session_snapshot(default)
        before = _session_snapshot(s)
        runtime_before = s._capture_runtime_snapshot()
        seen = []

        def dispatch(*args, **kwargs):
            seen.append((args[0], game._session() is s))
            game._session().world_state.setdefault("flags", {})["t9_marker"] = True
            game._session().rng.randint(1, 20)
            if kind == "plain":
                raise game.IntentInfrastructureError("intent_timeout")
            raise RuntimeError("t9 failed turn")

        with patch.object(game, "_dispatch_player_turn", side_effect=dispatch):
            if kind == "plain":
                reply = game.run_player_turn("Kapıyı itiyorum.", interaction_mode="do", session=s)
            else:
                with patch.object(game, "primal_knowledge_check_admission"):
                    try:
                        game.run_player_turn("Kapıyı itiyorum.", interaction_mode="do", check_feature=feature,
                                             check_evidence=[], session=s)
                        reply = "no error"
                    except RuntimeError as error:
                        reply = f"RuntimeError: {error}"
        return {"seen": seen, "reply": reply, "same": _session_snapshot(s) == before,
                "runtime_same": s._capture_runtime_snapshot() == runtime_before,
                "marker": "t9_marker" in s.world_state.get("flags", {}),
                "default_unchanged": _session_snapshot(default) == default_before}


def _dispatched_turn_outcome(test, seed, flag):
    """A turn whose dispatch is patched on game: the keyed turn calls it once, for s, and finishes its answer."""
    with fixed_town(test, seed), patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": flag}), \
            patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
        s = game.create_session(seed=13)
        default = game._session()
        default_before = _session_snapshot(default)
        seen = []

        def dispatch(*args, **kwargs):
            seen.append((args[0], args[4], args[5], game._session() is s))
            return {"messages": s.messages, "narration": "Kapı gıcırdayarak açılıyor.", "model_calls": 0,
                    "action_result": {"action": "narrative", "status": "resolved", "success": True,
                                      "state_changes": []}}

        with patch.object(game, "_dispatch_player_turn", side_effect=dispatch):
            out = game.run_player_turn("Kapıyı itiyorum.", interaction_mode="do", action_id="t9-act",
                                       session_id="t9-session", session=s)
        return {"seen": seen, "narration": out.get("narration"),
                "action": (out["action_result"]["action"], out["action_result"]["status"]),
                "key_cleared": getattr(s, "_economic_turn_key", None),
                "default_unchanged": _session_snapshot(default) == default_before}


def _owner_turn_outcome(test, seed, flag):
    """A slash owner command through the whole turn: held_weapon answers it through _owner_module_reply, for s."""
    with fixed_town(test, seed), patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": flag}), \
            patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
        s = game.create_session(seed=13)
        default = game._session()
        s.world_state["equipment"] = {"main_hand": "t10-blade-only-in-s", "off_hand": None}
        default_before = _session_snapshot(default)
        out = game.run_player_turn("/equip clear", interaction_mode="do", session=s)
        result = out["action_result"]
        return {"narration": out.get("narration"), "model_calls": out.get("model_calls"),
                "action": (result.get("action"), result.get("status"), result.get("success")),
                "equipment": s.world_state.get("equipment"),
                "default_unchanged": _session_snapshot(default) == default_before}


def _internal_turn_outcome(test, seed, flag, kind):
    """One turn through _run_player_turn_internal for s (session=): what it answers, and whom game._session() named."""
    real = game._session
    with fixed_town(test, seed), patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": flag}), \
            patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
        s = game.create_session(seed=11)
        s.world_state["location"] = "forest"
        s.world_state["locations"]["t11_kuyu"] = {"id": "t11_kuyu", "name": "Kuyu Başı", "type": "city",
                                                  "description": ""}
        if kind == "down":
            s.character["current_hp"] = 0
        default = game._session()
        default_before = _session_snapshot(default)
        seen = []

        def record():
            value = real()
            seen.append(value)
            return value

        with patch.object(game, "_session", side_effect=record):
            out = game._run_player_turn_internal("Kuyu Başı'na gidiyorum.", interaction_mode="do", session=s)
        result = out.get("action_result") or {}
        return {"narration": out.get("narration"), "model_calls": out.get("model_calls"),
                "action": (result.get("action"), result.get("status"), result.get("target")),
                "reads": len(seen) > 0, "only_s": all(value is s for value in seen),
                "location": s.world_state["location"], "hp": s.character.get("current_hp"),
                "default_unchanged": _session_snapshot(default) == default_before}


if __name__ == "__main__":
    unittest.main()
