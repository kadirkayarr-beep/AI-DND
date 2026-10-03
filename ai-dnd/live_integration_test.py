#!/usr/bin/env python3
"""Explicit smoke runner: mocked by default, authenticated live model via --live."""
import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
GAME_FILE = PROJECT_DIR / "game.py"
engine = None
game = None
ollama_mock = None
NARRATIVE_INTENT_RESPONSE = {
    "message": {"content": '{"intent":"narrative","action":"test","target":{"type":"none","reference":""},"completion":"unclear","confidence":0.5}'}
}


def _ensure_project_import_path():
    project_path = str(PROJECT_DIR)
    if project_path not in sys.path:
        sys.path.insert(0, project_path)


def _initialize_mock_engine():
    """Load the engine with a mock only for the explicitly invoked offline run."""
    global engine, game, ollama_mock
    from unittest.mock import MagicMock, patch

    _ensure_project_import_path()
    if "game" in sys.modules:
        raise RuntimeError(
            "Run the offline smoke in a fresh Python process to isolate its mock."
        )
    ollama_mock = MagicMock()
    ollama_mock.chat.return_value = NARRATIVE_INTENT_RESPONSE
    with patch.dict(sys.modules, {"ollama": ollama_mock}):
        import game as loaded_engine

    engine = loaded_engine
    game = engine.create_session()
    game.system_prompt = """
Sen Dungeons & Dragons oyununda yaratıcı Dungeon Master ve anlatıcısısın.
Python gerçek oyun motorudur; world state içindeki kayıtlar kalıcı olgulardır.

Python tek başına yönetir: karakter verisi, HP, hasar, inventory, eşya transferi,
konum, kapılar, zarlar, modifiers, proficiency, DC ve mekanik sonuçlar. Bunları
world_updates içinde asla değiştirmeye çalışma.

Oyuncunun yapmadığı bir hareketi, sözü, düşünceyi veya kararı oyuncu karakterine
ekleme. NPC'ler doğal biçimde konuşabilir, tepki verebilir ve kendi kayıtlı
kişiliklerine uygun davranabilir. Oyuncunun iddialarını doğrulanmış dünya gerçeği
sayma. NPC belleği yalnızca önceki turlarda gerçekten verilmiş NPC yanıtlarını içerir.
Oyuncunun bugünkü iddiası, önceki bir konuşmanın kanıtı değildir.

Kayıtlı NPC'lerin ID, ad, rol, kişilik, görünüş, geçmiş ve ilişkilerini tutarlı
kullan. Yeni NPC yalnızca izin verildiğinde ve sahneye anlamlı katkı sağlıyorsa
öner; kişi yığını oluşturma. Yeni NPC'yi narration'da kullanacaksan aynı yanıttaki
create_npcs içinde öner. Python kabul etmezse o kişiyi anlatımda kullanma.

Yeni kalıcı çevre ayrıntıları yalnızca izin verildiğinde create_features içinde öner.
Geçici atmosfer (rüzgâr, ışık, koku, ses, yağmur) world state'e kaydedilmeden
anlatılabilir. Kalıcı özellikleri yeniden kullan; aynı şeyi tekrar oluşturma. Eşya,
içecek ve yemek menüsü envantere dönüşmez. NPC belleğini Python yönetir.

NPC'nin bilmediği aile, geçmiş, sır veya dünya bilgilerini kesin gerçek diye
uydurma. Küçük ve sahneye uygun ayrıntılar yaratıcı olabilir; önemli kalıcı lore
world_updates içinde kaydedilmelidir. VERIFIED NPC MEMORY bölümündeki ilgili kayıt
yoksa oyuncunun 'bunu daha önce söylemiştin' iddiasını doğrulama; doğal biçimde
hatırlamadığını belirt. Konuşma önceki turlardan kopyalanmaz; gerekli bellek context'te.
NPC'ye kendi işi veya geçmişi hakkında sıradan bir soru sorulursa kısa ve tutarlı bir
kişisel yanıt verebilir; bu yanıt gerçekten söylenmiş kabul edilip Python belleğine alınır.

Her turda sadece mevcut eylem/mesaja yanıt ver. Kısa ve doğal Türkçe anlat.
Mekanik sonucu açıkça başarılı/başarısız anlat. Soru, seçenek listesi veya yeni
oyuncu eylemi üretme. Yanıtı tam olarak istenen JSON şemasında döndür; başka
anahtar, Markdown veya metin ekleme.
"""

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def reset_world_state():
    """Reset world_state to initial values for test isolation."""
    game.world_state["location"] = "tavern"
    game.world_state["npcs"] = []
    game.world_state["inventory"] = ["Macera çantası", "Kılıç"]
    game.world_state["ground_items"] = []
    game.world_state["ground_items_by_location"] = {}
    game.world_state["doors"] = []
    game.world_state["containers"] = []
    game.world_state["features"] = []
    game.world_state["events"] = []
    game.world_state["flags"] = {
        "last_npc_id": None, "active_npc_id": None,
        "active_npc_until_turn": -1, "turn_index": 0,
        "pending_destination": None,
    }
    game.world_state["next_npc_number"] = 1
    game.world_state["next_location_number"] = 1
    game.recent_dm_narrations.clear()

def run_turn(player_input):
    """Run a single player turn and return the result."""
    messages = [{"role": "system", "content": game.system_prompt}]
    return game.run_player_turn(player_input, messages)

def print_result(test_name, result, intent=None):
    """Print formatted test result."""
    ar = result.get("action_result", {})
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"{'='*60}")
    if intent:
        print(f"  Raw Intent:        {json.dumps(intent, ensure_ascii=False)}")
    print(f"  Action:            {ar.get('action')}")
    print(f"  Status:            {ar.get('status')}")
    print(f"  Success:           {ar.get('success')}")
    if 'query_type' in ar:
        print(f"  Query Type:        {ar.get('query_type')}")
    if 'outcome' in ar:
        print(f"  Outcome:           {ar.get('outcome')}")
    state_changes = ar.get('state_changes', [])
    if state_changes:
        print(f"  State Changes:     {state_changes}")
    narration = result.get("narration", "")[:200]
    print(f"  Narration:         {narration}...")
    print(f"{'-'*60}")


LIVE_INTENT_CASES = (
    {
        "label": "self_name_question",
        "message": "Benim adım ne?",
        "expected_kind": "self_name",
    },
    {
        "label": "self_name_without_turkish_diacritics",
        "message": "Benim adim ne?",
        "expected_kind": "self_name",
    },
    {
        "label": "attack_named_npc",
        "message": "Gromm'a kılıcımla saldırıyorum",
        "expected_kind": "attack",
        "npc_count": 1,
    },
    {
        "label": "attack_curly_apostrophe",
        "message": "Gromm’a kılıcımla saldırıyorum",
        "expected_kind": "attack",
        "npc_count": 1,
    },
    {
        "label": "attack_accusative_verb_variant",
        "message": "Gromm'u kılıçla vuruyorum",
        "expected_kind": "attack",
        "npc_count": 1,
    },
    {
        "label": "negated_attack",
        "message": "Gromm'a saldırmak istemiyorum",
        "expected_kind": "negative_attack",
        "npc_count": 1,
    },
    {
        "label": "attack_without_target",
        "message": "Saldırıyorum",
        "expected_kind": "targetless_attack",
        "npc_count": 1,
    },
    {
        "label": "attack_with_ambiguous_pronoun",
        "message": "Ona saldırıyorum",
        "expected_kind": "ambiguous_pronoun_attack",
        "npc_count": 2,
    },
)

ATTACK_EXPECTED_KINDS = {"attack"}
TARGETLESS_ATTACK_EXPECTED_KINDS = {
    "targetless_attack",
    "ambiguous_pronoun_attack",
}


def _gromm_reference_matches(reference):
    return bool(re.fullmatch(
        r"gromm(?:['’](?:ya|ye|yı|yi|yu|yü|a|e|ı|i|u|ü))?",
        str(reference).casefold().strip(),
    ))


def _intent_fields(raw, live_engine):
    raw = raw if isinstance(raw, dict) else {}
    intent = str(raw.get("intent", "unknown")).strip().casefold()
    if intent not in live_engine.INTENT_TYPES:
        intent = "unknown"
    query_type = raw.get("query_type")
    if query_type not in {"self", "location", "presence", "npc_identity"}:
        query_type = None
    target = raw.get("target")
    target = target if isinstance(target, dict) else {}
    target_type = target.get("type")
    if target_type not in {"location", "npc", "item", "feature", "none"}:
        target_type = "none"
    return {
        "intent": intent,
        "query_type": query_type,
        "target_type": target_type,
        "target_reference": (
            target.get("reference")
            if isinstance(target.get("reference"), str)
            else ""
        ),
    }


def _classification_matches(expected_kind, fields):
    if expected_kind == "self_name":
        return fields["intent"] == "query" and fields["query_type"] == "self"
    if expected_kind in ATTACK_EXPECTED_KINDS:
        return (
            fields["intent"] in {"attack", "combat"}
            and fields["target_type"] == "npc"
            and _gromm_reference_matches(fields["target_reference"])
        )
    if expected_kind == "negative_attack":
        return fields["intent"] not in {"attack", "combat"}
    if expected_kind in TARGETLESS_ATTACK_EXPECTED_KINDS:
        return (
            fields["intent"] in {"attack", "combat"}
            and fields["target_type"] == "none"
            and not fields["target_reference"].strip()
        )
    return False


def _engine_execution_matches(expected_kind, session, action_result):
    if not isinstance(action_result, dict):
        return False
    if expected_kind == "self_name":
        expected_name = str(session.character.get("name", ""))
        response = str(action_result.get("direct_response", ""))
        return (
            action_result.get("action") in {"character_query", "query"}
            and bool(expected_name)
            and expected_name.casefold() in response.casefold()
        )
    if expected_kind in ATTACK_EXPECTED_KINDS:
        return (
            action_result.get("action") == "attack"
            and action_result.get("status") == "resolved"
            and action_result.get("target_id") == "npc_001"
            and action_result.get("target_name") == "Gromm"
        )
    if expected_kind == "negative_attack":
        npc = session.world_state.get("npcs", [{}])[0]
        combat = session.world_state.get("combat", {})
        return (
            action_result.get("action") != "attack"
            and npc.get("current_hp") == 20
            and not combat.get("active")
        )
    if expected_kind in TARGETLESS_ATTACK_EXPECTED_KINDS:
        npc = session.world_state.get("npcs", [{}])[0]
        combat = session.world_state.get("combat", {})
        expected_outcome = (
            "missing_target"
            if expected_kind == "targetless_attack"
            else "ambiguous_target"
        )
        return (
            action_result.get("action") == "attack"
            and action_result.get("status") == "clarification"
            and action_result.get("outcome") == expected_outcome
            and npc.get("current_hp") == 20
            and not combat.get("active")
        )
    return False


def _public_classification(fields, expected_kind):
    if fields is None:
        return {
            "status": "BLOCKED",
            "intent": None,
            "query_type": None,
            "target_type": None,
            "target_matches_expected": False,
        }
    return {
        "status": (
            "PASS"
            if _classification_matches(expected_kind, fields)
            else "FAIL"
        ),
        "intent": fields["intent"],
        "query_type": fields["query_type"],
        "target_type": fields["target_type"],
        "target_matches_expected": (
            _gromm_reference_matches(fields["target_reference"])
            if expected_kind in ATTACK_EXPECTED_KINDS
            else None
        ),
    }


def run_live_model_smoke():
    """Run authenticated live-model checks only when explicitly requested."""
    _ensure_project_import_path()
    try:
        import game as live_engine
        from api.ollama_adapter import (
            AuthenticatedOllamaAdapter,
            MAX_MODEL_CALLS_PER_TURN,
            MODEL_NAME,
        )
    except Exception as error:
        print(json.dumps({
            "status": "FAIL",
            "stage": "smoke_import",
            "error_type": type(error).__name__,
        }, ensure_ascii=False, indent=2))
        return 1

    adapter = AuthenticatedOllamaAdapter.from_environment()
    if adapter is None:
        print(json.dumps({
            "status": "FAIL",
            "stage": "configuration",
            "reason": "authenticated_ollama_configuration_unavailable",
            "model": MODEL_NAME,
        }, ensure_ascii=False, indent=2))
        return 1

    try:
        adapter.ensure_required_model()
    except Exception as error:
        print(json.dumps({
            "status": "FAIL",
            "stage": "authenticated_model_preflight",
            "error_type": type(error).__name__,
            "model": MODEL_NAME,
        }, ensure_ascii=False, indent=2))
        return 1

    previous_chat = live_engine.ollama.chat
    previous_list = live_engine.ollama.list
    adapter.install_for_engine()
    authenticated_chat = live_engine.ollama.chat
    results = []

    try:
        for index, case in enumerate(LIVE_INTENT_CASES):
            session = live_engine.create_session(seed=5600 + index)
            session.world_state["location"] = "tavern"
            session.world_state["inventory"] = ["Macera çantası", "Kılıç"]
            captured_intents = []
            classifier_call_count = 0
            turn_call_attempts = 0
            turn_cap_hit = False

            session.world_state["npcs"] = [
                {
                    "id": f"npc_{npc_index:03d}",
                    "name": "Gromm" if npc_index == 1 else "Lyra",
                    "role": "Barmen" if npc_index == 1 else "Muhafız",
                    "location": "tavern",
                    "personality": "",
                    "appearance": "",
                    "relationship": "neutral",
                    "knowledge": [],
                    "memory": [],
                    "backstory": "",
                    "combat_status": "active",
                    "current_hp": 20 if npc_index == 1 else 24,
                    "max_hp": 20 if npc_index == 1 else 24,
                    "armor_class": 10,
                }
                for npc_index in range(1, case.get("npc_count", 0) + 1)
            ]

            def tracked_chat(*args, **kwargs):
                nonlocal classifier_call_count
                nonlocal turn_call_attempts, turn_cap_hit
                is_classifier_call = (
                    kwargs.get("format") == live_engine.INTENT_SCHEMA
                )
                if is_classifier_call:
                    classifier_call_count += 1
                turn_call_attempts += 1
                if turn_call_attempts > MAX_MODEL_CALLS_PER_TURN:
                    turn_cap_hit = True
                    raise RuntimeError("Per-turn model-call limit exceeded.")
                response = authenticated_chat(*args, **kwargs)
                if is_classifier_call:
                    parsed = live_engine._extract_json_object(
                        live_engine.ollama_response_content(response)
                    )
                    captured_intents.append(_intent_fields(parsed, live_engine))
                return response

            live_engine.ollama.chat = tracked_chat
            result = None
            turn_error_type = None
            turn_calls = []
            turn_failures = []
            try:
                with adapter.capture_model_calls() as turn_calls:
                    with adapter.capture_model_failures() as turn_failures:
                        try:
                            result = session.run_player_turn(case["message"])
                        except Exception as error:
                            turn_error_type = type(error).__name__
            finally:
                live_engine.ollama.chat = authenticated_chat

            classification_source = "turn"
            classifier_calls = classifier_call_count
            classifier_failures = []
            fields = captured_intents[0] if captured_intents else None
            probe_calls = 0

            if fields is None:
                classification_source = "standalone_probe"
                try:
                    with adapter.capture_model_calls() as calls:
                        with adapter.capture_model_failures() as failures:
                            raw_classification = session.parse_player_intent(
                                case["message"]
                            )
                    probe_calls = len(calls)
                    classifier_calls += probe_calls
                    classifier_failures = list(failures)
                    fields = _intent_fields(raw_classification, live_engine)
                except Exception as error:
                    classifier_failures = [type(error).__name__]

            classification = _public_classification(
                fields, case["expected_kind"]
            )
            if classifier_failures:
                classification["status"] = "BLOCKED"

            action_result = (
                result.get("action_result")
                if isinstance(result, dict)
                else None
            )
            engine_passed = (
                turn_error_type is None
                and _engine_execution_matches(
                    case["expected_kind"], session, action_result
                )
            )
            call_limit_passed = (
                not turn_cap_hit
                and len(turn_calls) <= MAX_MODEL_CALLS_PER_TURN
            )
            case_passed = (
                classification["status"] == "PASS"
                and engine_passed
                and call_limit_passed
                and not turn_failures
                and not classifier_failures
                and turn_error_type is None
            )
            results.append({
                "case": case["label"],
                "status": "PASS" if case_passed else "FAIL",
                "classification": {
                    **classification,
                    "source": classification_source,
                    "classifier_model_calls": classifier_calls,
                    "standalone_probe_model_calls": probe_calls,
                },
                "engine_execution": {
                    "status": "PASS" if engine_passed else "FAIL",
                    "action": (
                        action_result.get("action")
                        if isinstance(action_result, dict)
                        else None
                    ),
                    "action_status": (
                        action_result.get("status")
                        if isinstance(action_result, dict)
                        else None
                    ),
                    "target_matches_expected": (
                        action_result.get("target_id") == "npc_001"
                        if case["expected_kind"] in ATTACK_EXPECTED_KINDS
                        and isinstance(action_result, dict)
                        else None
                    ),
                    "error_type": turn_error_type,
                },
                "turn_model_calls": len(turn_calls),
                "turn_model_call_attempts": turn_call_attempts,
                "turn_model_call_limit": MAX_MODEL_CALLS_PER_TURN,
                "turn_model_call_limit_status": (
                    "PASS" if call_limit_passed else "FAIL"
                ),
                "turn_model_call_limit_blocked": turn_cap_hit,
                "turn_model_error_types": list(turn_failures),
                "classifier_error_types": classifier_failures,
            })
    finally:
        live_engine.ollama.chat = previous_chat
        live_engine.ollama.list = previous_list

    passed = all(case["status"] == "PASS" for case in results)
    print(json.dumps({
        "status": "PASS" if passed else "FAIL",
        "mode": "authenticated_live_model",
        "model": MODEL_NAME,
        "cases": results,
    }, ensure_ascii=False, indent=2))
    return 0 if passed else 1


# ============================================================
# MAIN TEST RUNNER
# ============================================================
def run_mock_suite():
    _initialize_mock_engine()
    results = []

    # Check the mocked client; this script does not make external requests.
    try:
        test_resp = ollama_mock.chat(
            model="qwen3:8b",
            messages=[{"role": "user", "content": "ping"}],
            options={"temperature": 0.0, "num_predict": 5}
        )
        print("✅ Mocked Ollama client ready; no external connection")
    except Exception as e:
        print(f"❌ Mocked client setup failed ({type(e).__name__})")
        return 1

    # ---- TEST 1: SELF QUERY ----
    print("\n" + "="*70)
    print("MOCK TEST 1: SELF QUERY - 'benim adım ne?'")
    print("="*70)
    reset_world_state()
    result = run_turn("benim adım ne?")
    ar = result["action_result"]
    expected_name = game.character.get("name", "").casefold()
    direct_response = ar.get("direct_response", "").casefold()
    passed = (
        ar.get("action") == "character_query"
        and bool(expected_name)
        and expected_name in direct_response
    )
    results.append(("SELF QUERY", passed, ar.get("action"), ar.get("status")))

    # ---- TEST 2: NPC IDENTITY ----
    print("\n" + "="*70)
    print("MOCK TEST 2: NPC IDENTITY - 'senin adın ne?' (mit NPC)")
    print("="*70)
    reset_world_state()
    game.world_state["npcs"].append({
        "id": "npc_001", "name": "Gromm", "role": "Barmen",
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": ""
    })
    result = run_turn("senin adın ne?")
    ar = result["action_result"]
    passed = "Gromm" in ar.get("direct_response", "") or "Gromm" in result.get("narration", "")
    results.append(("NPC IDENTITY", passed, ar.get("action"), ar.get("status")))

    # ---- TEST 3: LOCATION QUERY ----
    print("\n" + "="*70)
    print("MOCK TEST 3: LOCATION QUERY - 'buranın adı ne?'")
    print("="*70)
    reset_world_state()
    result = run_turn("buranın adı ne?")
    ar = result["action_result"]
    passed = "Taverna" in ar.get("direct_response", "") or "Taverna" in result.get("narration", "")
    results.append(("LOCATION QUERY", passed, ar.get("action"), ar.get("status")))

    # ---- TEST 4: PRESENCE ----
    print("\n" + "="*70)
    print("MOCK TEST 4: PRESENCE - 'burada kimler var?'")
    print("="*70)
    reset_world_state()
    game.world_state["npcs"].append({
        "id": "npc_001", "name": "Gromm", "role": "Barmen",
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": ""
    })
    result = run_turn("burada kimler var?")
    ar = result["action_result"]
    passed = "Gromm" in ar.get("direct_response", "") or "Gromm" in result.get("narration", "")
    results.append(("PRESENCE", passed, ar.get("action"), ar.get("status")))

    # ---- TEST 5: UNLOCKED DOOR ----
    print("\n" + "="*70)
    print("MOCK TEST 5: UNLOCKED DOOR - 'kapıyı açıyorum'")
    print("="*70)
    reset_world_state()
    game.world_state["doors"].append({
        "name": "Taverna Kapısı", "description": "Taverna giriş kapısı.",
        "locked": False, "open": False, "broken": False, "location": "tavern"
    })
    result = run_turn("kapıyı açıyorum")
    ar = result["action_result"]
    door = game._current_door()
    passed = ar.get("action") != "skill_check" and door.get("open") == True
    results.append(("UNLOCKED DOOR", passed, ar.get("action"), ar.get("status")))

    # ---- TEST 6: ENTER THROUGH DOOR ----
    print("\n" + "="*70)
    print("MOCK TEST 6: ENTER THROUGH DOOR - 'içeri giriyorum'")
    print("="*70)
    reset_world_state()
    game.world_state["doors"].append({
        "name": "Taverna Kapısı", "description": "Taverna giriş kapısı.",
        "locked": False, "open": False, "broken": False, "location": "tavern"
    })
    result = run_turn("içeri giriyorum")
    ar = result["action_result"]
    door = game._current_door()
    passed = ar.get("action") != "skill_check" and door.get("open") == True
    results.append(("ENTER THROUGH DOOR", passed, ar.get("action"), ar.get("status")))

    # ---- TEST 7: FAILED STEALTH / NARRATOR SAFETY ----
    print("\n" + "="*70)
    print("MOCK TEST 7: FAILED STEALTH / NARRATOR SAFETY - 'gizleniyorum'")
    print("="*70)
    reset_world_state()
    original_roll = engine.roll_d20
    engine.roll_d20 = lambda: 1
    try:
        result = run_turn("gizleniyorum")
    finally:
        engine.roll_d20 = original_roll
    ar = result["action_result"]
    narration = result.get("narration", "").lower()
    passed = ar.get("outcome") in ("failure", "critical_failure") and "başarılı" not in narration
    results.append(("FAILED STEALTH SAFETY", passed, ar.get("action"), ar.get("status")))

    # ---- TEST 8: GROUND ITEM LOCATION ----
    print("\n" + "="*70)
    print("MOCK TEST 8: GROUND ITEM LOCATION - tavernada bırak, forestta al")
    print("="*70)
    reset_world_state()
    game.world_state["ground_items_by_location"]["tavern"] = ["Kılıç"]
    game.world_state["inventory"].remove("Kılıç")
    game.world_state["location"] = "forest"
    result = run_turn("kılıcı alıyorum")
    ar = result["action_result"]
    passed = "Kılıç" not in game.world_state["inventory"]
    results.append(("GROUND ITEM LOCATION", passed, ar.get("action"), ar.get("status")))

    # ---- TEST 9: DYNAMIC LOCATION ----
    print("\n" + "="*70)
    print("MOCK TEST 9: DYNAMIC LOCATION - 'Eski Ay Kulesi'ne gidiyorum'")
    print("="*70)
    reset_world_state()
    result = run_turn("Eski Ay Kulesi'ne gidiyorum")
    ar = result["action_result"]
    passed = ar.get("action") in ("travel", "narrative") and ar.get("status") in ("completed", "intended", "awaiting_proposal", "resolved")
    results.append(("DYNAMIC LOCATION", passed, ar.get("action"), ar.get("status")))

    # ---- TEST 10: MOCKED ATTACK INTENT RESOLUTION ----
    print("\n" + "="*70)
    print("MOCK TEST 10: ATTACK INTENT RESOLUTION - 'Gromm'a kılıcımla saldırıyorum'")
    print("="*70)
    reset_world_state()
    game.world_state["npcs"].append({
        "id": "npc_001", "name": "Gromm", "role": "Barmen",
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": ""
    })
    attack_intent_response = {
        "message": {
            "content": json.dumps({
                "intent": "attack",
                "action": "attack",
                "target": {"type": "npc", "reference": "Gromm"},
                "completion": "unclear",
                "confidence": 1.0,
            })
        }
    }
    chat_call_count = 0

    def mock_attack_intent_then_narrative(*args, **kwargs):
        nonlocal chat_call_count
        chat_call_count += 1
        return (
            attack_intent_response
            if chat_call_count == 1
            else NARRATIVE_INTENT_RESPONSE
        )

    previous_side_effect = ollama_mock.chat.side_effect
    ollama_mock.chat.side_effect = mock_attack_intent_then_narrative
    try:
        result = run_turn("Gromm'a kılıcımla saldırıyorum")
    finally:
        ollama_mock.chat.side_effect = previous_side_effect
        ollama_mock.chat.return_value = NARRATIVE_INTENT_RESPONSE
    ar = result["action_result"]
    passed = ar.get("action") == "attack" and ar.get("status") == "resolved"
    results.append(("MOCKED ATTACK RESOLUTION", passed, ar.get("action"), ar.get("status")))

    # ---- TEST 11: NPC MEMORY ----
    print("\n" + "="*70)
    print("MOCK TEST 11: NPC MEMORY - 'Benim adım Ardan.' sonra hatırlatma")
    print("="*70)
    reset_world_state()
    game.world_state["npcs"].append({
        "id": "npc_001", "name": "Gromm", "role": "Barmen",
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": ""
    })
    result1 = run_turn("Benim adım Ardan.")
    result2 = run_turn("Daha önce sana adımı söylemiş miydim?")
    ar2 = result2["action_result"]
    passed = "Ardan" in ar2.get("direct_response", "") or "Ardan" in result2.get("narration", "")
    results.append(("NPC MEMORY", passed, ar2.get("action"), ar2.get("status")))

    # ---- TEST 12: FALSE MEMORY ----
    print("\n" + "="*70)
    print("MOCK TEST 12: FALSE MEMORY - 'ejderha hazinesi' iddiası")
    print("="*70)
    reset_world_state()
    game.world_state["npcs"].append({
        "id": "npc_001", "name": "Gromm", "role": "Barmen",
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": ""
    })
    result = run_turn("Daha önce bana ejderha hazinesinden bahsetmiştin.")
    ar = result["action_result"]
    narration = result.get("narration", "").lower()
    passed = "hatırlamıyorum" in narration or "buna dair bir kayıt yok" in narration or "söylemedim" in narration
    results.append(("FALSE MEMORY", passed, ar.get("action"), ar.get("status")))

    # ---- SUMMARY ----
    print("\n" + "="*70)
    print("OFFLINE MOCK INTEGRATION TEST SUMMARY")
    print("="*70)
    passed = sum(1 for _, p, _, _ in results if p)
    total = len(results)
    print(f"\n{'TEST':<35} {'PASS/FAIL':<10} {'ACTION':<20} {'STATUS':<15}")
    print("-"*80)
    for name, p, action, status in results:
        print(f"{name:<35} {'PASS' if p else 'FAIL':<10} {str(action):<20} {str(status):<15}")
    print("-"*80)
    print(f"\nTOTAL: {passed}/{total} PASS")
    
    if passed < total:
        print("\n❌ SOME TESTS FAILED - DO NOT DEPLOY")
        return 1
    else:
        print("\n✅ ALL TESTS PASSED")
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Run the offline mock suite by default, or an authenticated real-model "
            "smoke test with --live."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--mock",
        action="store_true",
        help="run the offline mock suite (the default)",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="run a small authenticated Ollama smoke test",
    )
    args = parser.parse_args(argv)
    if args.live:
        return run_live_model_smoke()
    return run_mock_suite()


if __name__ == "__main__":
    sys.exit(main())