with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add the function import from the game_namespace
old = "run_turn = game_namespace['run_player_turn']"
new = """# run_player_turn is defined in the main block, we need to extract it
import sys
# Make sure the function is available
if 'run_player_turn' not in game_namespace:
    # The function is in the main block, let's extract it
    exec_globals = {}
    exec(final_source, exec_globals)
    # Now we should have it
    run_player_turn = exec_globals.get('run_player_turn', game_namespace.get('run_player_turn'))
else:
    run_player_turn = game_namespace['run_player_turn']

print(f"run_player_turn available: {'run_player_turn' in dir()}")"""

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Not found')