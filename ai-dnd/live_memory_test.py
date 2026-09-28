#!/usr/bin/env python3
"""
LIVE qwen3:8b NPC Memory Integration Test
Uses REAL Ollama - NO MOCKS
Tests the two scenarios from the requirements:
1. Player says name -> NPC recalls it
2. False memory claim -> NPC denies
"""
import sys
import io
import json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_DIR = Path(__file__).resolve().parent
GAME_FILE = PROJECT_DIR / "game.py"
sys.path.insert(0, str(PROJECT_DIR))

# Import REAL ollama
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

def add_npc():
    world_state["npcs"].append({
        "id": "npc_001", "name": "Gromm", "role": "Barmen",
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": ""
    })

def get_npc_memory():
    return world_state["npcs"][0].get("memory", []) if world_state["npcs"] else []

# ============================================================
# TEST 1: Player introduces self -> NPC recalls
# ============================================================
print("="*70)
print("LIVE MEMORY TEST 1: Player name recall")
print("="*70)
reset_world_state()
add_npc()

print("\n--- Turn 1: 'Gromm, benim adım Ardan.' ---")
result1 = run_turn("Gromm, benim adım Ardan.")
print(f"Narration: {result1['narration'][:200]}...")
print(f"Memory after turn 1: {json.dumps(get_npc_memory(), ensure_ascii=False, indent=2)}")

print("\n--- Turn 2: 'Daha önce sana adımı söylemiş miydim?' ---")
result2 = run_turn("Daha önce sana adımı söylemiş miydim?")
narration2 = result2['narration']
print(f"Narration: {narration2[:300]}...")

memory = get_npc_memory()
print(f"\nMemory after 2 turns: {json.dumps(memory, ensure_ascii=False, indent=2)}")

# Check: NPC should recall "Ardan"
memory_text = " ".join([e.get("text", "") if isinstance(e, dict) else str(e) for e in memory])
passed1 = "Ardan" in narration2 or "Ardan" in memory_text
print(f"\n>>> TEST 1: {'PASS' if passed1 else 'FAIL'} - NPC recalls 'Ardan'")

# ============================================================
# TEST 2: False memory claim -> NPC denies
# ============================================================
print("\n" + "="*70)
print("LIVE MEMORY TEST 2: False memory denial")
print("="*70)
reset_world_state()
add_npc()

print("\n--- Turn 1: 'Daha önce bana ejderha hazinesinden bahsetmiştin.' ---")
result3 = run_turn("Daha önce bana ejderha hazinesinden bahsetmiştin.")
narration3 = result3['narration']
print(f"Narration: {narration3[:300]}...")

# Check: NPC should deny (no memory of dragon treasure)
passed2 = ("hatırlamıyorum" in narration3.lower() or 
           "kayıt yok" in narration3.lower() or 
           "söylemedim" in narration3.lower() or
           "bilmiyorum" in narration3.lower() or
           "hatırlamadım" in narration3.lower())
print(f">>> TEST 2: {'PASS' if passed2 else 'FAIL'} - NPC denies false claim")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "="*70)
print("LIVE MEMORY TEST SUMMARY")
print("="*70)
print(f"TEST 1 (Player name recall): {'PASS' if passed1 else 'FAIL'}")
print(f"TEST 2 (False memory denial): {'PASS' if passed2 else 'FAIL'}")

if passed1 and passed2:
    print("\n✅ ALL LIVE MEMORY TESTS PASSED")
    sys.exit(0)
else:
    print("\n❌ SOME LIVE MEMORY TESTS FAILED")
    sys.exit(1)