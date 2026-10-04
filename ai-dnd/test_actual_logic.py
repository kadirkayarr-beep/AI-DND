import sys
import io
from pathlib import Path
PROJECT_DIR = Path(__file__).resolve().parent
GAME_FILE = PROJECT_DIR / "game.py"
sys.path.insert(0, str(PROJECT_DIR))
from offline_test_support import offline_model

import game
session = game.create_session()

def reset():
    session.world_state['location'] = 'tavern'
    session.world_state['npcs'] = []
    session.world_state['inventory'] = ['Macera çantası', 'Kılıç']
    session.world_state['ground_items'] = []
    session.world_state['doors'] = []
    session.world_state['containers'] = []
    session.world_state['features'] = []
    session.world_state['events'] = []
    session.world_state['flags'] = {'last_npc_id': None, 'active_npc_id': None, 'active_npc_until_turn': -1, 'turn_index': 0, 'pending_destination': None}
    session.world_state['next_npc_number'] = 1
    session.world_state['next_location_number'] = 1
    session.recent_dm_narrations.clear()

reset()

# Add NPC
session.world_state["npcs"].append({
    "id": "npc_001", "name": "TestNPC", "role": "Barmen",
    "location": "tavern", "personality": "", "appearance": "",
    "relationship": "neutral", "knowledge": [], "memory": [],
    "backstory": ""
})

@offline_model(game)
def run_tests():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    npc_target = session.active_npcs()[0]
    print(f"Active NPC: {npc_target['name']}")

    # Test with NPC
    print("\n=== With Active NPC ===")
    for t in ["adın ne?", "senin adın ne?", "kimsin?", "ismin ne?"]:
        result = session._detect_query_type(t, npc_target)
        print(f"  '{t}' -> {result}")
        assert result == "npc_identity", f"Active NPC identity question was not recognized: {t!r} -> {result!r}"

    # Test without NPC
    print("\n=== Without NPC ===")
    for t in ["adın ne?", "senin adın ne?", "kimsin?", "ismin ne?"]:
        result = session._detect_query_type(t, None)
        print(f"  '{t}' -> {result}")
        assert result is None, f"NPC identity question without a target must remain unresolved: {t!r} -> {result!r}"


if __name__ == "__main__":
    run_tests()