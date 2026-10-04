import sys
import io
from pathlib import Path
PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))
from offline_test_support import offline_model

import game
session = game.create_session()
world_state = session.world_state


@offline_model(game)
def run_tests():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    print("=== Testing Legacy Migration Hardening ===")

    # Scenario: ground_items_by_location key completely missing
    world_state['location'] = 'tavern'
    world_state['npcs'] = []
    world_state['inventory'] = ['Macera çantası', 'Kılıç']
    world_state['ground_items'] = ['Kılıç', 'Kalkan']
    world_state['doors'] = []
    world_state['containers'] = []
    world_state['features'] = []
    world_state['events'] = []
    world_state['flags'] = {'last_npc_id': None, 'active_npc_id': None, 'active_npc_until_turn': -1, 'turn_index': 0, 'pending_destination': None}
    world_state['next_npc_number'] = 1
    world_state['next_location_number'] = 1

    # Remove ground_items_by_location entirely (simulate legacy state)
    if 'ground_items_by_location' in world_state:
        del world_state['ground_items_by_location']

    print(f"Before migration:")
    print(f"  ground_items: {world_state.get('ground_items')}")
    print(f"  ground_items_by_location: {'MISSING' if 'ground_items_by_location' not in world_state else world_state.get('ground_items_by_location')}")

    # This should NOT crash
    session._normalize_ground_items()

    print(f"After migration:")
    print(f"  ground_items: {world_state.get('ground_items')}")
    print(f"  ground_items_by_location: {world_state.get('ground_items_by_location')}")

    # Verify
    assert world_state['ground_items'] == [], "Legacy list should be empty"
    assert 'tavern' in world_state['ground_items_by_location'], "Should have tavern key"
    assert 'Kılıç' in world_state['ground_items_by_location']['tavern'], "Kılıç should be in tavern"
    assert 'Kalkan' in world_state['ground_items_by_location']['tavern'], "Kalkan should be in tavern"

    print("\n✅ Legacy migration hardening works!")

    # Test duplicate prevention - call again
    session._normalize_ground_items()
    assert len(world_state['ground_items_by_location']['tavern']) == 2, "Should not duplicate"
    print("✅ No duplicates on repeated calls!")

    # Test that calling with already normalized state is no-op
    session._normalize_ground_items()
    session._normalize_ground_items()
    assert len(world_state['ground_items_by_location']['tavern']) == 2, "Should still be 2"
    print("✅ Idempotent - no-op when already normalized!")

if __name__ == '__main__':
    run_tests()
