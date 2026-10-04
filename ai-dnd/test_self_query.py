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
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    # Test "benim adım ne?"
    print("Testing 'benim adım ne?'")
    result = session.run_player_turn("benim adım ne?", [{'role': 'system', 'content': 'test'}])
    print(f"Action: {result['action_result'].get('action')}")
    print(f"Direct response: {result['action_result'].get('direct_response')}")
    print(f"Query type: {result['action_result'].get('query_type')}")
    print(f"Narration: {result['narration'][:100]}")
    action_result = result["action_result"]
    assert action_result.get("action") == "character_query", (
        f"Explicit player-name question should be a character query, got {action_result.get('action')}"
    )
    assert session.character["name"] in action_result.get("direct_response", ""), (
        "The character query should return the player's registered character name"
    )

if __name__ == '__main__':
    run_tests()
