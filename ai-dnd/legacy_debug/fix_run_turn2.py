with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the exact line with run_turn
old = 'run_turn("Gromm'
if old in content:
    content = content.replace(old, 'run_player_turn("Gromm')
    with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Not found')
    # Search for variations
    for variant in ['run_turn', 'run_player_turn']:
        idx = content.find(variant)
        if idx >= 0:
            print(f'Found {variant} at index {idx}')
        else:
            print(f'{variant} not found')