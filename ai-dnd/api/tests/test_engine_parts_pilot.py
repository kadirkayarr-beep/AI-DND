"""The bound-session wrapper filter reads an explicit list of part modules (game.py split, T2.1)."""
import ast
import dataclasses
import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import game  # noqa: E402
from api.auth import FixedAuthenticator  # noqa: E402
from api.main import create_app  # noqa: E402
from api.session_manager import SessionManager  # noqa: E402
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
        self.assertEqual(game._PART_MODULES, ("game_parts.character_rules", "game_parts.intent", "game_parts.places",
                                              "game_parts.text_rules_a", "game_parts.text_rules_b"))
        # Task 18 (pilot a), Task 19 (pilot b), Plan 2 Task 13, Plan 3 Tasks 8 and 9
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
        show = ("print(game.roll_d20.__module__); print(game._inside_speech.__module__); "
                "print(game._split_sentences_keep_speech.__module__)")
        for code in ("import game, game_parts; " + show, "import game_parts, game; " + show):
            done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
            self.assertEqual((done.returncode, done.stdout.split()),
                             (0, ["game_parts.character_rules", "game_parts.text_rules_a", "game_parts.text_rules_b"]),
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
            self.assertEqual(s.messages[0]["content"], game.system_prompt)  # GameSession.__init__ seeds self.messages


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
            with self.subTest(helper="_salvage_plain_speech", raw=after):
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
        # both names read game._session() (measured on 0b159e30): record what it returns during the session= call
        real = game._session
        with fixed_town(self, 20261201):
            s = game.create_session(seed=11)
            s.character["species"] = "Goliath"
            s.character["proficiency_bonus"] = 2
            default_character = dict(game._session().character)
            for name, args in (("roll_stat", ()), ("initialize_species_trait_state", ("hill",))):
                seen = []

                def record():
                    value = real()
                    seen.append(value)
                    return value

                with self.subTest(name=name), patch.object(game, "_session", side_effect=record):
                    getattr(game, name)(*args, session=s)
                    self.assertTrue(seen)
                    self.assertTrue(all(value is s for value in seen))
            self.assertEqual(s.character["giant_ancestry"], "hill")
            self.assertEqual(dict(game._session().character), default_character)

    def test_cr_helpers_answer_as_before(self):
        # one fixed character (Barbarian, DEX 14, CON 16, WIS 12); expected values captured on 0b159e30 before the move
        self.assertEqual([game.get_modifier(stat) for stat in (8, 10, 15, 20)], [-1, 0, 2, 5])
        dex, con, wis = game.get_modifier(14), game.get_modifier(16), game.get_modifier(12)
        self.assertEqual((dex, con, wis), (2, 3, 1))
        self.assertEqual(game.calculate_hp("Barbarian", con), 15)
        self.assertEqual(game.calculate_ac("Barbarian", dex, con, wis), 15)


PLACES_1 = tuple(batch_names("places-1"))
PLACES_2 = tuple(batch_names("places-2"))


class PlacesPart(unittest.TestCase):
    """T4.2 batches places-1 and places-2: door, feature, location and scene helpers live in game_parts/places.py."""

    def test_places_1_lives_in_the_part(self):
        self.assertEqual(set(PLACES_1) - set(routing_audit.re_exports(ROOT).get("places", ())), set())

    def test_places_2_lives_in_the_part(self):
        self.assertEqual(set(PLACES_2) - set(routing_audit.re_exports(ROOT).get("places", ())), set())

    def test_places_session_helpers_use_the_given_session(self):  # Review Focus 4
        # every name reads game._session() (measured on 33ab2efd): record what it returns during the session= call
        real = game._session
        with fixed_town(self, 20261202):
            s = game.create_session(seed=11)
            s.world_state["location"] = "forest"
            default_world = json.dumps(game._session().world_state, sort_keys=True, default=str)
            cases = (
                ("resolve_location_reference", ("ormanı",), "forest"),
                ("update_inventory_from_player", ("kılıcı yere bırakıyorum",), None),
                ("_walked_there", ({"kind": "go_to"}, {"action": "travel", "status": "already_here", "target_id": "forest"},
                                   None), True),
            )
            for name, args, expected in cases:
                seen = []

                def record():
                    value = real()
                    seen.append(value)
                    return value

                with self.subTest(name=name), patch.object(game, "_session", side_effect=record):
                    answer = getattr(game, name)(*args, session=s)
                    if expected is not None:
                        self.assertEqual(answer, expected)
                    self.assertTrue(seen)
                    self.assertTrue(all(value is s for value in seen))
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


INTENT_1 = tuple(batch_names("intent-1"))
INTENT_2 = tuple(batch_names("intent-2"))


class IntentPart(unittest.TestCase):
    """T4.3 batches intent-1 and intent-2: intent reading and validation helpers live in game_parts/intent.py."""

    def test_intent_1_lives_in_the_part(self):
        self.assertEqual(set(INTENT_1) - set(routing_audit.re_exports(ROOT).get("intent", ())), set())

    def test_intent_2_lives_in_the_part(self):
        self.assertEqual(set(INTENT_2) - set(routing_audit.re_exports(ROOT).get("intent", ())), set())

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
            default_world = json.dumps(game._session().world_state, sort_keys=True, default=str)
            cases = (
                ("is_npc_historical_claim", ("Bu adam dün beni soydu.",), False),
                ("known_character_answer", ("Benim adım ne?",), f"Adın {s.character['name']}."),
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
            self.assertEqual(json.dumps(game._session().world_state, sort_keys=True, default=str), default_world)

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


if __name__ == "__main__":
    unittest.main()
