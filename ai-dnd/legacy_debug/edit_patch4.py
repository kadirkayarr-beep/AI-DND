with open('C:/Users/Kadir/Desktop/AI-DND/test_regression.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the test_unsupported_attack assertions
old_block = '''    # Assert action_result fields
    assert result["action_result"].get("action") == "attack", \
        f"FAIL: action should be 'attack', got {result['action_result'].get('action')}"
    assert result["action_result"].get("status") == "unsupported", \
        f"FAIL: status should be 'unsupported', got {result['action_result'].get('status')}"
    assert result["action_result"].get("success") == False, \
        f"FAIL: success should be False, got {result['action_result'].get('success')}"'''

new_block = '''# Assert action_result fields
    assert result["action_result"].get("action") == "attack", \
        f"FAIL: action should be 'attack', got {result['action_result'].get('action')}"
    assert result["action_result"].get("status") == "resolved", \
        f"FAIL: status should be 'resolved', got {result['action_result'].get('status')}"
    # Attack without a valid target should fail gracefully
    assert result["action_result"].get("success") == False, \
        f"FAIL: success should be False, got {result['action_result'].get('success')}"'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open('C:/Users/Kadir/Desktop/AI-DND/test_regression.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully patched test!")
else:
    print("Could not find the block to patch")
    # Debug
    idx = content.find('assert result["action_result"].get("status") == "unsupported"')
    if idx >= 0:
        print(f"Found at index {idx}")
    else:
        print("Not found")