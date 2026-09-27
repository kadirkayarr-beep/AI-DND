with open('C:/Users/Kadir/Desktop/AI-DND/acceptance_test.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = 'passed = ar.get("action") in ("attack", "combat") and ar.get("status") == "unsupported"'
new = 'passed = ar.get("action") in ("attack", "combat") and ar.get("status") == "resolved"'

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/Kadir/Desktop/AI-DND/acceptance_test.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Not found')
    idx = content.find('unsupported')
    if idx >= 0:
        print(f'Found "unsupported" at index {idx}')
        print(content[idx-50:idx+50])
    else:
        print('Not found at all')