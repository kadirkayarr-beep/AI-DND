with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = 'print("  (Target resolution handles location mismatch)")'
new = 'assert target is None, "NPC in different location should not be a valid target"\nprint(f"  Target resolved: {target} -> PASS")'

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Old text not found')
    idx = content.find('Target resolution handles location')
    if idx >= 0:
        print(f'Found at index {idx}')
        print(repr(content[idx:idx+100]))
    else:
        print('Not found at all')