with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = """# Try to attack through full pipeline
result = run_turn(\"Gromm'a k\u0131l\u0131c\u0131mla s\u0131ld\u0131r\u0131yorum\")"""

new = """# Try to attack through full pipeline
messages = [{\"role\": \"system\", \"content\": \"test\"}]
result = run_player_turn(\"Gromm'a k\u0131l\u0131c\u0131mla s\u0131ld\u0131r\u0131yorum\", messages)"""

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Not found')
    idx = content.find('run_turn')
    if idx >= 0:
        print(f'Found at index {idx}')
        print(repr(content[idx:idx+200]))
    else:
        print('Not found at all')