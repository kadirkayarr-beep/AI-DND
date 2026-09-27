with open('C:/Users/Kadir/Desktop/AI-DND/test_regression.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = 'assert result["action_result"].get("status") == "unsupported",'
new = 'assert result["action_result"].get("status") == "resolved",'

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/Kadir/Desktop/AI-DND/test_regression.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Not found - searching...')
    idx = content.find('unsupported')
    if idx >= 0:
        print(f'Found "unsupported" at index {idx}')
        print(content[idx-50:idx+50])
    else:
        print('Not found at all')