with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = """run_turn = game_namespace['run_turn']"""
new = """# Debug: print available keys
print("Available keys:", [k for k in game_namespace.keys() if 'run' in k.lower()])
run_turn = game_namespace['run_turn']"""

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Not found')