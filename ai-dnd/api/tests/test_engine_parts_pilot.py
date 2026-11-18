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
        self.assertEqual(game._PART_MODULES, ("game_parts.character_rules", "game_parts.text_rules_a"))  # Task 18 (pilot a), Task 19 (pilot b)
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
        show = "print(game.roll_d20.__module__); print(game._inside_speech.__module__)"
        for code in ("import game, game_parts; " + show, "import game_parts, game; " + show):
            done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
            self.assertEqual((done.returncode, done.stdout.split()),
                             (0, ["game_parts.character_rules", "game_parts.text_rules_a"]), done.stderr)


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
        # _split_sentences_keep_speech stays in game.py and reads _SPEECH_SPAN_RE; expected value captured on 5da99a42
        self.assertEqual(game._split_sentences_keep_speech.__module__, "game")
        text = "Kapı açıldı. “Dur! Kim var? Çık dışarı.” dedi muhafız. Sonra sustu."
        self.assertEqual(game._split_sentences_keep_speech(text),
                         ["Kapı açıldı.", "“Dur! Kim var? Çık dışarı.” dedi muhafız.", "Sonra sustu."])


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


if __name__ == "__main__":
    unittest.main()
