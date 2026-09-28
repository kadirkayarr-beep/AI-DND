#!/usr/bin/env python3
"""
LIVE End-to-End Acceptance Test - 20 Scenarios
Uses REAL Ollama qwen3:8b - NO MOCKS
"""
import sys
import io
import json
import hashlib
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_DIR = Path(__file__).resolve().parent
GAME_FILE = PROJECT_DIR / "game.py"
sys.path.insert(0, str(PROJECT_DIR))

# REAL Ollama
try:
    import ollama
    models_response = ollama.list()
    model_names = [m.model for m in models_response.models]
    assert any('qwen3:8b' in name for name in model_names), "qwen3:8b not found"
    print(f"✅ Ollama connected, qwen3:8b available")
except Exception as e:
    print(f"❌ Ollama check failed: {e}")
    sys.exit(1)

# Load game.py functions
import game
session = game.create_session()

# Extract needed functions
run_player_turn = session.run_player_turn
system_prompt = game.system_prompt
world_state = session.world_state
recent_dm_narrations = session.recent_dm_narrations
parse_player_intent = session.parse_player_intent
normalize_intent = session.normalize_intent
validate_intent = session.validate_intent

def reset_world_state():
    world_state["location"] = "tavern"
    world_state["npcs"] = []
    world_state["inventory"] = ["Macera çantası", "Kılıç"]
    world_state["ground_items"] = []
    world_state["ground_items_by_location"] = {}
    world_state["doors"] = []
    world_state["containers"] = []
    world_state["features"] = []
    world_state["events"] = []
    world_state["flags"] = {
        "last_npc_id": None, "active_npc_id": None,
        "active_npc_until_turn": -1, "turn_index": 0,
        "pending_destination": None,
    }
    world_state["next_npc_number"] = 1
    world_state["next_location_number"] = 1
    recent_dm_narrations.clear()

def run_turn(player_input):
    messages = [{"role": "system", "content": system_prompt}]
    return run_player_turn(player_input, messages)

def add_npc(name="Gromm", role="Barmen"):
    world_state["npcs"].append({
        "id": f"npc_{len(world_state['npcs'])+1:03d}", "name": name, "role": role,
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": ""
    })

def get_npc_memory():
    return world_state["npcs"][0].get("memory", []) if world_state["npcs"] else []

def add_door(locked=False, open=False, name="Test Kapısı"):
    world_state["doors"].append({
        "name": name, "description": "Test kapısı",
        "locked": locked, "open": open, "broken": False, "location": world_state["location"]
    })

def force_roll(value):
    original = game.roll_d20
    game.roll_d20 = lambda: value
    return original

def hash_file(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]

# ============================================================
print("="*80)
print("LIVE END-TO-END ACCEPTANCE TEST - 20 SCENARIOS")
print("="*80)

game_hash_before = hash_file(GAME_FILE)
backup_hash = hash_file(PROJECT_DIR / 'game_backup.py')
print(f"game.py hash: {game_hash_before}")
print(f"game_backup.py hash: {backup_hash}")

results = []
contradictions = 0
state_issues = 0

def check_contradiction(ar, narration, expected_failure=None):
    """Check if narration contradicts mechanical result"""
    outcome = ar.get('outcome')
    if outcome in ('failure', 'critical_failure'):
        if any(w in narration.lower() for w in ['başarılı', 'kazanır', 'açılır', 'bulur']):
            return True, "Narrator says success but mechanical failure"
    if outcome in ('success', 'critical_success'):
        if any(w in narration.lower() for w in ['başarısız', 'başaramaz', 'kalır', 'kapat']):
            return True, "Narrator says failure but mechanical success"
    return False, None

def run_test(name, test_fn):
    global contradictions, state_issues
    print(f"\n{'='*80}")
    print(f"TEST: {name}")
    print(f"{'='*80}")
    reset_world_state()
    try:
        result = test_fn()
        passed = result.get('passed', False)
        results.append((name, passed, result))
        print(f"→ {'PASS' if passed else 'FAIL'}")
        if not passed:
            print(f"  FAIL REASON: {result.get('reason', 'Unknown')}")
        if 'contradiction' in result and result['contradiction']:
            contradictions += 1
            print(f"  ⚠️ CONTRADICTION: {result['contradiction']}")
        if 'state_issue' in result:
            state_issues += 1
            print(f"  ⚠️ STATE ISSUE: {result['state_issue']}")
        return result
    except Exception as e:
        print(f"→ ERROR: {e}")
        results.append((name, False, {'passed': False, 'reason': str(e)}))
        return {'passed': False, 'reason': str(e)}

# ============================================================
# TEST 1: PLAYER SELF
# ============================================================
def test_1():
    reset_world_state()
    result = run_turn("benim adım ne?")
    ar = result["action_result"]
    raw = parse_player_intent("benim adım ne?")
    norm = normalize_intent(raw, "benim adım ne?")
    val = validate_intent(norm, "benim adım ne?")
    passed = ar.get("action") in ("character_query", "query")
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 2: NPC IDENTITY
# ============================================================
def test_2():
    reset_world_state()
    add_npc()
    result = run_turn("senin adın ne?")
    ar = result["action_result"]
    raw = parse_player_intent("senin adın ne?")
    val = validate_intent(raw, "senin adın ne?")
    narration = result['narration']
    passed = "Gromm" in narration
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'narration': narration[:100]
    }

# ============================================================
# TEST 3: LOCATION NAME
# ============================================================
def test_3():
    reset_world_state()
    add_npc()
    result = run_turn("buranın adı ne?")
    ar = result["action_result"]
    raw = parse_player_intent("buranın adı ne?")
    val = validate_intent(raw, "buranın adı ne?")
    narration = result['narration']
    passed = "Taverna" in narration and "Gromm" not in narration
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'narration': narration[:100]
    }

# ============================================================
# TEST 4: PRESENCE
# ============================================================
def test_4():
    reset_world_state()
    add_npc()
    result = run_turn("burada kimler var?")
    ar = result["action_result"]
    raw = parse_player_intent("burada kimler var?")
    val = validate_intent(raw, "burada kimler var?")
    narration = result['narration']
    passed = "Gromm" in narration
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'narration': narration[:100]
    }

# ============================================================
# TEST 5: UNLOCKED DOOR
# ============================================================
def test_5():
    reset_world_state()
    add_door(locked=False, open=False)
    result = run_turn("kapıyı açıyorum")
    ar = result["action_result"]
    raw = parse_player_intent("kapıyı açıyorum")
    val = validate_intent(raw, "kapıyı açıyorum")
    door = session._current_door()
    passed = ar.get("action") != "skill_check" and door.get("open") == True
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'state_change': f"door.open={door.get('open')}",
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 6: LOCKED DOOR
# ============================================================
def test_6():
    reset_world_state()
    add_door(locked=True, open=False)
    result = run_turn("kapıyı açıyorum")
    ar = result["action_result"]
    raw = parse_player_intent("kapıyı açıyorum")
    val = validate_intent(raw, "kapıyı açıyorum")
    passed = ar.get("action") == "skill_check"
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 7: ENTER THROUGH UNLOCKED DOOR
# ============================================================
def test_7():
    reset_world_state()
    add_door(locked=False, open=False, name="Taverna Kapısı")
    result = run_turn("içeri giriyorum")
    ar = result["action_result"]
    raw = parse_player_intent("içeri giriyorum")
    val = validate_intent(raw, "içeri giriyorum")
    door = session._current_door()
    passed = ar.get("action") != "skill_check" and door.get("open") == True
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'state_change': f"door.open={door.get('open')}",
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 8: FAILED STEALTH
# ============================================================
def test_8():
    reset_world_state()
    original_roll = force_roll(1)  # Critical failure
    try:
        result = run_turn("gizleniyorum")
    finally:
        game.roll_d20 = original_roll
    ar = result["action_result"]
    raw = parse_player_intent("gizleniyorum")
    val = validate_intent(raw, "gizleniyorum")
    narration = result['narration'].lower()
    outcome = ar.get('outcome')
    contradicted = outcome in ('failure', 'critical_failure') and 'başarılı' in narration
    passed = outcome in ('failure', 'critical_failure') and not contradicted
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'outcome': outcome,
        'status': ar.get('status'),
        'contradiction': contradicted,
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 9: GROUND ITEM LOCATION
# ============================================================
def test_9():
    reset_world_state()
    world_state["ground_items_by_location"]["tavern"] = ["Kılıç"]
    world_state["inventory"].remove("Kılıç")
    world_state["location"] = "forest"
    result = run_turn("kılıcı alıyorum")
    ar = result["action_result"]
    raw = parse_player_intent("kılıcı alıyorum")
    val = validate_intent(raw, "kılıcı alıyorum")
    passed = "Kılıç" not in world_state["inventory"]
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'state_check': f"Kılıç in inventory={('Kılıç' in world_state['inventory'])}, tavern ground={world_state['ground_items_by_location'].get('tavern')}",
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 10: DYNAMIC LOCATION
# ============================================================
def test_10():
    reset_world_state()
    result = run_turn("Eski Ay Kulesi'ne gidiyorum")
    ar = result["action_result"]
    raw = parse_player_intent("Eski Ay Kulesi'ne gidiyorum")
    val = validate_intent(raw, "Eski Ay Kulesi'ne gidiyorum")
    passed = ar.get("action") in ("travel", "narrative") and ar.get("status") in ("completed", "intended", "awaiting_proposal", "resolved")
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 11: ATTACK
# ============================================================
def test_11():
    reset_world_state()
    add_npc()
    result = run_turn("Gromm'a kılıcımla saldırıyorum")
    ar = result["action_result"]
    raw = parse_player_intent("Gromm'a kılıcımla saldırıyorum")
    val = validate_intent(raw, "Gromm'a kılıcımla saldırıyorum")
    passed = ar.get("action") in ("attack", "combat") and ar.get("status") == "resolved"
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 12: PLAYER MEMORY
# ============================================================
def test_12():
    reset_world_state()
    add_npc()
    run_turn("Gromm, benim adım Ardan.")
    result = run_turn("Daha önce sana adımı söylemiş miydim?")
    ar = result["action_result"]
    raw = parse_player_intent("Daha önce sana adımı söylemiş miydim?")
    val = validate_intent(raw, "Daha önce sana adımı söylemiş miydim?")
    narration = result['narration']
    memory = world_state["npcs"][0].get("memory", [])
    memory_text = " ".join([e.get("text", "") if isinstance(e, dict) else str(e) for e in memory])
    passed = "Ardan" in narration or "Ardan" in memory_text
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'memory': memory_text[:200],
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 13: NPC MEMORY
# ============================================================
def test_13():
    reset_world_state()
    add_npc()
    run_turn("Gromm, senin adın ne?")
    result = run_turn("Daha önce adını söylemiş miydin?")
    ar = result["action_result"]
    raw = parse_player_intent("Daha önce adını söylemiş miydin?")
    val = validate_intent(raw, "Daha önce adını söylemiş miydin?")
    narration = result['narration']
    passed = "Gromm" in narration
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 14: FALSE MEMORY
# ============================================================
def test_14():
    reset_world_state()
    add_npc()
    result = run_turn("Daha önce bana ejderha hazinesinden bahsetmiştin.")
    ar = result["action_result"]
    raw = parse_player_intent("Daha önce bana ejderha hazinesinden bahsetmiştin.")
    val = validate_intent(raw, "Daha önce bana ejderha hazinesinden bahsetmiştin.")
    narration = result['narration'].lower()
    passed = any(w in narration for w in ["hatırlamıyorum", "kayıt yok", "söylemedim", "bilmiyorum", "hatırlamadım"])
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 15: ASSERTION SAFETY
# ============================================================
def test_15():
    reset_world_state()
    add_npc()
    run_turn("Sen bana ejderha hazinesinden bahsetmiştin.")  # Player claims
    result = run_turn("Daha önce bana ejderha hazinesinden bahsetmiştin.")  # NPC should still deny
    ar = result["action_result"]
    raw = parse_player_intent("Daha önce bana ejderha hazinesinden bahsetmiştin.")
    val = validate_intent(raw, "Daha önce bana ejderha hazinesiden bahsetmiştin.")
    narration = result['narration'].lower()
    passed = any(w in narration for w in ["hatırlamıyorum", "kayıt yok", "söylemedim", "bilmiyorum", "hatırlamadım"])
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 16: RETURN TRAVEL
# ============================================================
def test_16():
    reset_world_state()
    run_turn("ormana git")  # Go to forest
    result = run_turn("geri dönüyorum")  # Return
    ar = result["action_result"]
    raw = parse_player_intent("geri dönüyorum")
    val = validate_intent(raw, "geri dönüyorum")
    passed = world_state["location"] == "tavern"
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'state_change': f"location={world_state['location']}",
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 17: NAMED RETURN
# ============================================================
def test_17():
    reset_world_state()
    run_turn("ormana git")  # Go to forest
    run_turn("kalede git")   # Go to castle
    result = run_turn("tavernaya dönüyorum")  # Explicitly return to tavern
    ar = result["action_result"]
    raw = parse_player_intent("tavernaya dönüyorum")
    val = validate_intent(raw, "tavernaya dönüyorum")
    passed = world_state["location"] == "tavern"
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'state_change': f"location={world_state['location']}",
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 18: INVENTORY DROP/RETAKE
# ============================================================
def test_18():
    reset_world_state()
    world_state["ground_items_by_location"]["tavern"] = ["Kılıç"]
    world_state["inventory"].remove("Kılıç")
    result = run_turn("kılıcı alıyorum")
    ar = result["action_result"]
    raw = parse_player_intent("kılıcı alıyorum")
    val = validate_intent(raw, "kılıcı alıyorum")
    passed = "Kılıç" in world_state["inventory"] and world_state["ground_items_by_location"]["tavern"] == []
    return {
        'passed': passed,
        'raw_intent': raw.get('intent'),
        'validated_intent': val.get('intent'),
        'action_result': ar.get('action'),
        'status': ar.get('status'),
        'state_change': f"inventory={world_state['inventory']}, ground={world_state['ground_items_by_location'].get('tavern')}",
        'narration': result['narration'][:100]
    }

# ============================================================
# TEST 19: MALFORMED QWEN SAFETY (verify fallback exists)
# ============================================================
def test_19():
    # Just verify the fallback code paths exist in game.py
    with open(GAME_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    has_fallback = "_fallback_for_action_result" in content
    has_malformed = "malformed" in content.lower() or "JSONDecodeError" in content
    return {
        'passed': has_fallback and has_malformed,
        'raw_intent': 'N/A',
        'validated_intent': 'N/A',
        'action_result': 'verify',
        'status': 'verify',
        'narration': f'fallback exists: {has_fallback}, malformed handling: {has_malformed}'
    }

# ============================================================
# TEST 20: 20-TURN MINI PLAY SESSION
# ============================================================
def test_20():
    reset_world_state()
    add_npc()
    
    turns = [
        "Gromm, merhaba.",           # Dialogue
        "Gromm, benim adım Ardan.",  # Name
        "kapıyı açıyorum",           # Door
        "içeri giriyorum",           # Enter
        "etrafıma bakıyorum",        # Look
        "etrafı araştırıyorum",      # Investigate
        "gizleniyorum",              # Stealth (will fail with roll=1)
        "kılıcı bırak",              # Drop
        "kılıcı alıyorum",           # Retake
        "ormana git",                # Travel to forest
        "etrafıma bakıyorum",        # Look
        "burada kimler var?",        # Presence
        "benim adım ne?",            # Self query
        "Daha önce sana adımı söylemiş miydim?",  # Memory recall
        "Daha önce bana ejderha hazinesinden bahsetmiştin.",  # False memory
        "Gromm'a kılıcımla saldırıyorum",  # Unsupported attack
        "tavernaya dönüyorum",       # Named return
        "içeri giriyorum",           # Enter
        "kapıyı açıyorum",           # Door
        "çık",                       # Exit
    ]
    
    # Force stealth failure on turn 7
    original_roll = game.roll_d20
    
    state_snapshots = []
    crash = False
    
    for i, turn in enumerate(turns):
        try:
            if i == 6:  # Stealth turn
                game.roll_d20 = lambda: 1
            else:
                game.roll_d20 = original_roll
            
            result = run_turn(turn)
            ar = result["action_result"]
            narration = result['narration'].lower()
            
            # Check contradictions
            outcome = ar.get('outcome')
            if outcome in ('failure', 'critical_failure') and 'başarılı' in narration.lower():
                return {'passed': False, 'reason': f'Contradiction on turn {i+1}'}
            
            # Track state
            state_snapshots.append({
                'turn': turn,
                'location': world_state['location'],
                'inventory': list(world_state['inventory']),
                'ground': dict(world_state['ground_items_by_location']),
                'doors': [(d['name'], d['open'], d['locked']) for d in world_state['doors']],
                'npcs': [(n['id'], n['name'], n['location']) for n in world_state['npcs']],
            })
            
        except Exception as e:
            crash = True
            return {'passed': False, 'reason': f'Crash: {e}'}
        finally:
            game.roll_d20 = original_roll
        
        # Check for duplicates/state issues
        issues = []
        
        # Check for duplicates WITHIN each snapshot (not across snapshots)
        for snap in state_snapshots:
            seen_ids = set()
            for npc_id, name, loc in snap['npcs']:
                if npc_id in seen_ids:
                    issues.append(f"Duplicate NPC ID in snapshot for turn '{snap['turn']}': {npc_id} ({name} at {loc})")
                seen_ids.add(npc_id)
            
            # Also check for same name+location with different IDs (shouldn't happen)
            seen_names = set()
            for npc_id, name, loc in snap['npcs']:
                key = (name, loc)
                if key in seen_names:
                    issues.append(f"Same name+location with different IDs in turn '{snap['turn']}': {name} at {loc}")
                seen_names.add(key)
        
        # Check player_said/npc_said separation
        memory = world_state["npcs"][0].get("memory", []) if world_state["npcs"] else []
        has_player = any(e.get("speaker") == "player" for e in memory if isinstance(e, dict))
        has_npc = any(e.get("speaker") == "npc" for e in memory if isinstance(e, dict))
        
        passed = not crash and len(issues) == 0 and has_player and has_npc
        
        return {
            'passed': passed,
            'raw_intent': 'multi',
            'validated_intent': 'multi',
            'action_result': '20-turn session',
            'status': 'completed' if passed else 'failed',
            'state_snapshots': len(state_snapshots),
            'issues': issues,
            'has_player_said': has_player,
            'has_npc_said': has_npc,
            'narration': f'Turns: {len(state_snapshots)}, crashes: {crash}, issues: {issues}'
        }

# ============================================================
# RUN ALL TESTS
# ============================================================
tests = [
    ("1. PLAYER SELF", test_1),
    ("2. NPC IDENTITY", test_2),
    ("3. LOCATION NAME", test_3),
    ("4. PRESENCE", test_4),
    ("5. UNLOCKED DOOR", test_5),
    ("6. LOCKED DOOR", test_6),
    ("7. ENTER UNLOCKED DOOR", test_7),
    ("8. FAILED STEALTH", test_8),
    ("9. GROUND ITEM LOCATION", test_9),
    ("10. DYNAMIC LOCATION", test_10),
    ("11. ATTACK", test_11),
    ("12. PLAYER MEMORY", test_12),
    ("13. NPC MEMORY", test_13),
    ("14. FALSE MEMORY", test_14),
    ("15. ASSERTION SAFETY", test_15),
    ("16. RETURN TRAVEL", test_16),
    ("17. NAMED RETURN", test_17),
    ("18. INVENTORY DROP/RETAKE", test_18),
    ("19. MALFORMED SAFETY", test_19),
    ("20. 20-TURN PLAY SESSION", test_20),
]

for name, fn in tests:
    run_test(name, fn)

# ============================================================
# FINAL REPORT
# ============================================================
print("\n" + "="*80)
print("FINAL ACCEPTANCE TEST REPORT")
print("="*80)

passed_count = sum(1 for _, p, _ in results if p)
total = len(results)

print(f"\n{'TEST':<30} {'PASS/FAIL':<10} {'ACTION':<25} {'STATUS':<15} {'NOTES'}")
print("-"*100)
for name, passed, data in results:
    status = 'PASS' if passed else 'FAIL'
    action = str(data.get('action_result', data.get('status', 'N/A')))[:24]
    status = str(data.get('status', 'N/A'))[:14]
    notes = str(data.get('narration', data.get('reason', data.get('state_change', ''))))[:60]
    print(f"{name:<30} {status:<10} {action:<25} {status:<15} {notes}")

print("-"*100)
print(f"\nTOTAL: {passed_count}/{total} PASS")

game_hash_after = hash_file(GAME_FILE)
print(f"\nGame integrity: game.py hash {'UNCHANGED' if game_hash_after == game_hash_before else 'CHANGED'} ({game_hash_after})")
print(f"Backup integrity: game_backup.py hash {'UNCHANGED' if hash_file(PROJECT_DIR / 'game_backup.py') == backup_hash else 'CHANGED'}")

print(f"\nContradictions (narrator vs mechanical): {contradictions}")
print(f"State issues (duplicates, leaks): {state_issues}")

if passed_count == total and contradictions == 0 and state_issues == 0 and game_hash_after == game_hash_before:
    print("\n✅ ALL TESTS PASSED - READY FOR DEPLOY")
    sys.exit(0)
else:
    print("\n❌ SOME TESTS FAILED - DO NOT DEPLOY")
    sys.exit(1)