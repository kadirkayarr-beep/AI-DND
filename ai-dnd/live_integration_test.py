#!/usr/bin/env python3
"""Offline integration smoke tests using a mocked Ollama client."""
import sys
import io
import json
import re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_DIR = Path(__file__).resolve().parent
GAME_FILE = PROJECT_DIR / "game.py"
sys.path.insert(0, str(PROJECT_DIR))

# Mock ollama BEFORE loading game source
from unittest.mock import MagicMock
ollama_mock = MagicMock()
NARRATIVE_INTENT_RESPONSE = {
    "message": {"content": '{"intent":"narrative","action":"test","target":{"type":"none","reference":""},"completion":"unclear","confidence":0.5}'}
}
ollama_mock.chat.return_value = NARRATIVE_INTENT_RESPONSE
sys.modules['ollama'] = ollama_mock

import game as engine
game = engine.create_session()

# Define system_prompt directly (it's a constant string in game.py)
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

# ============================================================
# MAIN TEST RUNNER
# ============================================================
def main():
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
        print(f"❌ Ollama nicht erreichbar: {e}")
        return

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

if __name__ == "__main__":
    sys.exit(main())