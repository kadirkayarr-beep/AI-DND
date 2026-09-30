import sys
import io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))
from unittest.mock import MagicMock

ollama_mock = MagicMock()
ollama_mock.chat.return_value = {
    "message": {"content": '{"intent":"narrative","action":"test","target":{"type":"none","reference":""},"completion":"unclear","confidence":0.5}'}
}
sys.modules['ollama'] = ollama_mock

# We'll test the logic directly without running the full game
# by checking the _detect_query_type and _handle_query functions

# First, let's just check the query detection logic
from unittest.mock import MagicMock

ollama_mock = MagicMock()
ollama_mock.chat.return_value = {
    "message": {
        "content": '{"intent":"dialogue","action":"talk","target":{"type":"npc","reference":"Barmen"},"completion":"completed","confidence":1.0}'
    }
}
sys.modules["ollama"] = ollama_mock
import game

session = game.create_session()
session.world_state["location"] = "tavern"
session.world_state["npcs"] = []
session.recent_dm_narrations.clear()

# Test with active NPC
session.world_state['npcs'].append({
    "id": "npc_001", "name": "Barmen", "role": "Barmen",
    "location": "tavern", "personality": "", "appearance": "",
    "relationship": "neutral", "knowledge": [], "memory": [],
    "backstory": ""
})

# Get the NPC target (as would be resolved by resolve_npc_reference)
npc_target = session.active_npcs()[0]
print(f"NPC target: {npc_target['name']}")

# Test 1: active NPC + "adın ne?"
result1 = session._detect_query_type("adın ne?", npc_target)
print(f"'adın ne?' with NPC: {result1}")
assert result1 == "npc_identity"

# Test 2: active NPC + "senin adın ne?"
result2 = session._detect_query_type("senin adın ne?", npc_target)
print(f"'senin adın ne?' with NPC: {result2}")
assert result2 == "npc_identity"

# Test 3: no NPC + "adın ne?"
result3 = session._detect_query_type("adın ne?", None)
print(f"'adın ne?' without NPC: {result3}")
assert result3 is None

# Test 4: active NPC + "kimsin?"
result4 = session._detect_query_type("kimsin?", npc_target)
print(f"'kimsin?' with NPC: {result4}")
assert result4 == "npc_identity"

# Test 5: no NPC + "kimsin?"
result5 = session._detect_query_type("kimsin?", None)
print(f"'kimsin?' without NPC: {result5}")
assert result5 is None

print("\n--- Response handling ---")
if result1:
    resp = session._handle_query("adın ne?", result1, npc_target)
    print(f"Response to 'adın ne?' with NPC: {resp}")
    assert resp is not None and "Barmen" in resp

if result3:
    resp = session._handle_query("adın ne?", result3, None)
    print(f"Response to 'adın ne?' without NPC: {resp}")
else:
    print("'adın ne?' without NPC: No query type detected (correct - safe fallback)")
    assert result3 is None

if result5:
    resp = session._handle_query("kimsin?", result5, None)
    print(f"Response to 'kimsin?' without NPC: {resp}")
else:
    print("'kimsin?' without NPC: No query type detected (correct - safe fallback)")
    assert result5 is None