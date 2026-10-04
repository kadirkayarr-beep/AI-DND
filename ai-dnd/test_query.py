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


@offline_model(game)
def run_tests():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    # Test "senin adın ne?"
    result = session.run_player_turn('senin adın ne?', [{'role': 'system', 'content': 'test'}])
    print(f"Action: {result['action_result'].get('action')}")
    print(f"Direct response: {result['action_result'].get('direct_response')}")
    print(f"Narration: {result['narration']}")
    assert result["action_result"].get("query_type") != "npc_identity", "An NPC identity must not be invented without an NPC"
    assert session.world_state["npcs"] == [], "An ambiguous identity question must not create an NPC"

if __name__ == '__main__':
    run_tests()
