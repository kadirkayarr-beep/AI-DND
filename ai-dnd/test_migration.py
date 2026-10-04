import sys
import io
from pathlib import Path
PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))
from offline_test_support import offline_model

import game
session = game.create_session()

# Test legacy format migration

@offline_model(game)
def run_tests():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    print("=== Testing Legacy Format Migration ===")

    # Reset with legacy format
    world_state = session.world_state
    world_state['location'] = 'tavern'
    world_state['npcs'] = []
    world_state['inventory'] = ['Macera çantası', 'Kılıç']
    world_state['ground_items'] = ['Kılıç', 'Kalkan']  # Legacy format
    world_state['ground_items_by_location'] = {}
    world_state['doors'] = []
    world_state['containers'] = []
    world_state['features'] = []
    world_state['events'] = []
    world_state['flags'] = {'last_npc_id': None, 'active_npc_id': None, 'active_npc_until_turn': -1, 'turn_index': 0, 'pending_destination': None}
    world_state['next_npc_number'] = 1
    world_state['next_location_number'] = 1

    print(f"Before migration:")
    print(f"  ground_items (legacy): {world_state['ground_items']}")
    print(f"  ground_items_by_location: {world_state['ground_items_by_location']}")

    # Call normalization
    session._normalize_ground_items()

    print(f"After migration:")
    print(f"  ground_items (legacy): {world_state['ground_items']}")
    print(f"  ground_items_by_location: {world_state['ground_items_by_location']}")

    # Verify items moved to current location (tavern)
    assert world_state['ground_items'] == [], "Legacy list should be empty"
    assert 'tavern' in world_state['ground_items_by_location'], "Should have tavern key"
    assert 'Kılıç' in world_state['ground_items_by_location']['tavern'], "Kılıç should be in tavern"
    assert 'Kalkan' in world_state['ground_items_by_location']['tavern'], "Kalkan should be in tavern"

    print("\n✅ Legacy migration works correctly!")

    # Test that items don't appear in other locations
    world_state['location'] = 'forest'
    session._normalize_ground_items()  # Should not duplicate items
    print(f"\nAfter location change to forest:")
    print(f"  ground_items_by_location: {world_state['ground_items_by_location']}")
    assert 'forest' not in world_state['ground_items_by_location'] or world_state['ground_items_by_location'].get('forest') == [], "Forest should not have items"

    print("✅ Items don't leak to other locations!")

if __name__ == '__main__':
    run_tests()
