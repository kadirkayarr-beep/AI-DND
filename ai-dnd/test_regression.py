"""
V10.1 Regression Tests for AI-DND game.py
Tests run without Ollama - they verify Python-side logic only.
"""
import sys
import io
import json
import re
from pathlib import Path
from unittest.mock import patch, MagicMock

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Mock ollama before importing game
ollama_mock = MagicMock()
ollama_mock.chat.return_value = {
    "message": {"content": '{"intent":"narrative","action":"test","target":{"type":"none","reference":""},"completion":"unclear","confidence":0.5}'}
}
sys.modules['ollama'] = ollama_mock

# Mock input to return "2" for random character, then "TestHero" for name
input_responses = iter(["2", "TestHero"])
with patch('builtins.input', lambda prompt='': next(input_responses)):
    import game as engine
game = engine.create_session()

# Re-mock ollama after import
sys.modules['ollama'] = ollama_mock
engine.ollama = ollama_mock


def reset_world_state():
    """Reset world_state to initial values for test isolation."""
    game.world_state["location"] = "tavern"
    game.world_state["npcs"] = []
    game.world_state["inventory"] = ["Macera çantası", "Kılıç"]
    game.world_state["ground_items"] = []
    game.world_state["ground_items_by_location"] = {}
    game.world_state["doors"] = []
    game.world_state["containers"] = []
    game.world_state["features"] = []
    game.world_state["events"] = []
    game.world_state["flags"] = {
        "last_npc_id": None, "active_npc_id": None,
        "active_npc_until_turn": -1, "turn_index": 0,
        "pending_destination": None,
    }
    game.world_state["next_npc_number"] = 1
    game.world_state["next_location_number"] = 1
    game.recent_dm_narrations.clear()


def run_turn(player_input):
    """Run a single player turn and return the result."""
    messages = [{"role": "system", "content": "test"}]
    return game.run_player_turn(player_input, messages)


# =========================================================
# TEST 1: Failed Stealth + Narrator Success Contradiction
# =========================================================
def test_failed_stealth_narrator_contradiction():
    """Qwen should not be able to narrate success when Python says failure."""
    reset_world_state()

    # Mock Qwen to return a success narration
    ollama_mock.chat.return_value = {
        "message": {"content": json.dumps({
            "world_updates": {"create_locations": [], "create_npcs": [], "update_npcs": [], "create_features": [], "events": []},
            "narration": "Saklanma girişimin başarılı olur; kimse seni fark etmez."
        })}
    }

    # Force a failed stealth check by patching roll_d20
    original_roll = engine.roll_d20
    engine.roll_d20 = lambda: 1
    try:
        result = run_turn("gizleniyorum")
    finally:
        engine.roll_d20 = original_roll

    narration = result["narration"]
    # The narration should NOT contain success language
    assert "başarılı olur" not in narration.lower() or "başarısız" in narration.lower(), \
        f"FAIL: Narrator contradicted Python failure result: {narration}"
    print("PASS: test_failed_stealth_narrator_contradiction")


# =========================================================
# TEST 2: Unlocked Door Normal Open (No Skill Check)
# =========================================================
def test_unlocked_door_normal_open():
    """Unlocked door should open without skill check."""
    reset_world_state()

    # Add an unlocked door
    game.world_state["doors"].append({
        "name": "Test Kapısı", "description": "Test kapısı",
        "locked": False, "open": False, "broken": False,
        "location": "tavern"
    })

    result = run_turn("kapıyı açıyorum")

    # Door should be open
    door = game._current_door()
    assert door["open"] == True, f"FAIL: Door should be open, got {door}"
    # Should NOT be a skill check
    assert result["action_result"].get("action") != "skill_check", \
        f"FAIL: Unlocked door should not trigger skill check"
    print("PASS: test_unlocked_door_normal_open")


# =========================================================
# TEST 3: Locked Door Requires Skill Check
# =========================================================
def test_locked_door_requires_check():
    """Locked door should require skill check."""
    reset_world_state()

    # Add a locked door
    game.world_state["doors"].append({
        "name": "Kilitli Kapı", "description": "Kilitli kapı",
        "locked": True, "open": False, "broken": False,
        "location": "tavern"
    })

    result = run_turn("kapıyı açıyorum")

    # Should be a skill check
    assert result["action_result"].get("action") == "skill_check", \
        f"FAIL: Locked door should trigger skill check, got {result['action_result'].get('action')}"
    print("PASS: test_locked_door_requires_check")


# =========================================================
# TEST 4: Force Door Requires Skill Check
# =========================================================
def test_force_door_requires_check():
    """Forcing a door should require skill check."""
    reset_world_state()

    game.world_state["doors"].append({
        "name": "Kapı", "description": "Kapı",
        "locked": False, "open": False, "broken": False,
        "location": "tavern"
    })

    result = run_turn("kapıyı zorla açıyorum")

    assert result["action_result"].get("action") == "skill_check", \
        f"FAIL: Force door should trigger skill check, got {result['action_result'].get('action')}"
    print("PASS: test_force_door_requires_check")


# =========================================================
# TEST 5: Enter Through Door
# =========================================================
def test_enter_through_door():
    """Entering through a door should update door state."""
    reset_world_state()

    game.world_state["doors"].append({
        "name": "Taverna Kapısı", "description": "Taverna giriş kapısı",
        "locked": False, "open": False, "broken": False,
        "location": "tavern"
    })

    result = run_turn("içeri giriyorum")

    # Door should be open after entering
    door = game._current_door()
    assert door["open"] == True, f"FAIL: Door should be open after entering, got {door}"
    print("PASS: test_enter_through_door")


# =========================================================
# TEST 6: "Buranın adı ne?" vs "Senin adın ne?"
# =========================================================
def test_location_name_vs_character_name():
    """Location name and character name questions should be handled differently."""
    reset_world_state()

    # "Buranın adı ne?" should be about location
    result1 = run_turn("buranın adı ne?")
    # Should NOT be treated as NPC dialogue
    assert result1["action_result"].get("action") != "dialogue" or \
           result1["action_result"].get("direct_response") is not None, \
        "FAIL: Location name question should not be NPC dialogue"

    # "Senin adın ne?" WITHOUT active NPC should NOT return character info
    # Should use safe fallback
    result2 = run_turn("senin adın ne?")
    assert result2["action_result"].get("action") != "character_query", \
        "FAIL: 'senin adın ne?' without NPC should not be self query"

    # Add an active NPC
    game.world_state["npcs"].append({
        "id": "npc_001", "name": "TestNPC", "role": "Barmen",
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": ""
    })

    # "Senin adın ne?" WITH active NPC should return NPC identity
    result3 = run_turn("senin adın ne?")
    assert result3["action_result"].get("action") == "query", \
        f"FAIL: 'senin adın ne?' with NPC should be query, got {result3['action_result'].get('action')}"
    assert result3["action_result"].get("query_type") == "npc_identity", \
        f"FAIL: query_type should be npc_identity, got {result3['action_result'].get('query_type')}"
    assert "TestNPC" in result3["action_result"].get("direct_response", ""), \
        f"FAIL: NPC identity response should contain NPC name"

    # "Benim adım ne?" should return character info (explicit self reference)
    result4 = run_turn("benim adım ne?")
    assert result4["action_result"].get("action") == "character_query", \
        f"FAIL: 'benim adım ne?' should be character_query, got {result4['action_result'].get('action')}"
    char_name = game.character['name']
    assert char_name in result4["action_result"].get("direct_response", ""), \
        f"FAIL: Self query should return character name ({char_name})"

    print("PASS: test_location_name_vs_character_name")


# =========================================================
# TEST 7: "Burada kimler var?"
# =========================================================
def test_who_is_here():
    """'Who is here?' should list NPCs in current location."""
    reset_world_state()

    # Add an NPC
    game.world_state["npcs"].append({
        "id": "npc_001", "name": "TestNPC", "role": "Barmen",
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": ""
    })

    result = run_turn("burada kimler var?")

    narration = result.get("narration", "")
    assert "TestNPC" in narration or "kimse" in narration.lower(), \
        f"FAIL: Should list NPCs or say none, got: {narration}"
    print("PASS: test_who_is_here")


# =========================================================
# TEST 8: "Buradan çıkıyorum"
# =========================================================
def test_exit_location():
    """'Buradan çıkıyorum' should be recognized as travel intent."""
    reset_world_state()

    result = run_turn("buradan çıkıyorum")

    # Should be treated as travel or narrative, not skill check
    action = result["action_result"].get("action")
    assert action != "skill_check", \
        f"FAIL: Exit should not be skill check, got {action}"
    print("PASS: test_exit_location")


# =========================================================
# TEST 9: "Geri dönüyorum"
# =========================================================
def test_return_travel():
    """'Geri dönüyorum' should be recognized as travel intent."""
    reset_world_state()

    result = run_turn("geri dönüyorum")

    action = result["action_result"].get("action")
    assert action != "skill_check", \
        f"FAIL: Return should not be skill check, got {action}"
    print("PASS: test_return_travel")


# =========================================================
# TEST 10: Named Location Return
# =========================================================
def test_named_location_return():
    """Returning to a named location should work."""
    reset_world_state()

    # Set current location to forest
    game.world_state["location"] = "forest"

    result = run_turn("tavernaya geri dönüyorum")

    # Should resolve to tavern
    assert game.world_state["location"] == "tavern", \
        f"FAIL: Should return to tavern, got {game.world_state['location']}"
    print("PASS: test_named_location_return")


# =========================================================
# TEST 11: Ground Item Same Location
# =========================================================
def test_ground_item_same_location():
    """Ground items should be location-specific."""
    reset_world_state()

    # Drop sword in tavern (use new format)
    game.world_state["ground_items_by_location"]["tavern"] = ["Kılıç"]
    game.world_state["inventory"].remove("Kılıç")

    # Pick up in same location
    result = run_turn("kılıcı alıyorum")

    assert "Kılıç" in game.world_state["inventory"], \
        f"FAIL: Should pick up sword in same location"
    print("PASS: test_ground_item_same_location")


# =========================================================
# TEST 12: Ground Item Different Location
# =========================================================
def test_ground_item_different_location():
    """Ground items should NOT be accessible from different location."""
    reset_world_state()

    # Drop sword in tavern (use new format)
    game.world_state["ground_items_by_location"]["tavern"] = ["Kılıç"]
    game.world_state["inventory"].remove("Kılıç")

    # Move to forest
    game.world_state["location"] = "forest"

    # Try to pick up
    result = run_turn("kılıcı alıyorum")

    # Should NOT pick up
    assert "Kılıç" not in game.world_state["inventory"], \
        f"FAIL: Should not pick up sword from different location"
    print("PASS: test_ground_item_different_location")


# =========================================================
# TEST 13: Player Said Memory
# =========================================================
def test_player_said_memory():
    """Player statements should be recorded separately from NPC statements."""
    reset_world_state()

    npc = {
        "id": "npc_001", "name": "TestNPC", "role": "Barmen",
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": ""
    }
    game.world_state["npcs"].append(npc)

    # Record an NPC interaction
    game.record_npc_interaction(npc, "Merhaba, hoş geldin.", "merhaba")

    # Check that memory contains structured entries for both player and NPC
    assert len(npc["memory"]) > 0, "FAIL: NPC memory should have entries"
    # First entry should be player_said
    assert len(npc["memory"]) >= 2, "FAIL: Should have both player and NPC entries"
    assert npc["memory"][0].get("speaker") == "player", "FAIL: First entry should be player_said"
    assert npc["memory"][1].get("speaker") == "npc", "FAIL: Second entry should be npc_said"
    assert "Merhaba" in npc["memory"][1].get("text", ""), "FAIL: NPC entry should contain NPC reply"
    print("PASS: test_player_said_memory")


# =========================================================
# TEST 14: False Memory Claim
# =========================================================
def test_false_memory_claim():
    """Player claims about NPC speech should be denied if not in memory."""
    reset_world_state()

    npc = {
        "id": "npc_001", "name": "TestNPC", "role": "Barmen",
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": ""
    }
    game.world_state["npcs"].append(npc)

    # Player claims NPC said something
    result = run_turn("daha önce bana bir hikaye anlatmıştın")

    narration = result.get("narration", "")
    assert "hatırlamıyorum" in narration.lower() or "buna dair bir kayıt yok" in narration.lower(), \
        f"FAIL: Should deny false memory claim, got: {narration}"
    print("PASS: test_false_memory_claim")


# =========================================================
# TEST 15: Draw Weapon
# =========================================================
def test_draw_weapon():
    """Drawing a weapon should update state."""
    reset_world_state()

    result = run_turn("kılıcı çekiyorum")

    # Should not be unsupported
    assert result["action_result"].get("status") != "unsupported", \
        f"FAIL: Draw weapon should be supported, got {result['action_result']}"
    print("PASS: test_draw_weapon")


# =========================================================
# TEST 16: Sheathe Weapon
# =========================================================
def test_sheathe_weapon():
    """Sheathing a weapon should update state."""
    reset_world_state()

    result = run_turn("kılıcı kılına koyuyorum")

    # Should not be unsupported
    assert result["action_result"].get("status") != "unsupported", \
        f"FAIL: Sheathe weapon should be supported, got {result['action_result']}"
    print("PASS: test_sheathe_weapon")


# =========================================================
# TEST 17: Unsupported Attack
# =========================================================
def test_unsupported_attack():
    """Attack actions should not change world state."""
    reset_world_state()

    # Snapshot world state before
    before_snapshot = game._world_snapshot()

    # Patch parse_player_intent to return attack intent
    original_parse = engine.parse_player_intent
    engine.parse_player_intent = lambda player_input: {
        "intent": "attack",
        "action": "attack",
        "target": {"type": "npc", "reference": "düşman"},
        "completion": "completed",
        "confidence": 1.0
    }
    try:
        result = run_turn("düşmanı saldırıyorum")
    finally:
        engine.parse_player_intent = original_parse

    # Assert action_result fields
    assert result["action_result"].get("action") == "attack", \
        f"FAIL: action should be 'attack', got {result['action_result'].get('action')}"
    assert result["action_result"].get("status") == "resolved", \
        f"FAIL: status should be 'unsupported', got {result['action_result'].get('status')}"
    assert result["action_result"].get("success") == False, \
        f"FAIL: success should be False, got {result['action_result'].get('success')}"

    # Assert world state unchanged (mechanical state)
    after_snapshot = game._world_snapshot()
    mechanical_fields = [
        "location", "inventory", "ground_items_by_location",
        "doors", "npcs", "features", "events"
    ]
    for field in mechanical_fields:
        assert before_snapshot[field] == after_snapshot[field], \
            f"FAIL: World state field '{field}' changed unexpectedly"

    print("PASS: test_unsupported_attack")


# =========================================================
# TEST 18: Ordinary Environment Look
# =========================================================
def test_ordinary_environment_look():
    """Ordinary look should not trigger skill check."""
    reset_world_state()

    result = run_turn("etrafıma bakıyorum")

    assert result["action_result"].get("action") != "skill_check", \
        f"FAIL: Ordinary look should not be skill check, got {result['action_result'].get('action')}"
    print("PASS: test_ordinary_environment_look")


# =========================================================
# TEST 19: Successful Investigation
# =========================================================
def test_successful_investigation():
    """Successful investigation should use structured action_result."""
    reset_world_state()

    # Mock a successful investigation
    original_roll = engine.roll_d20
    engine.roll_d20 = lambda: 20
    try:
        result = run_turn("etrafı araştırıyorum")
    finally:
        engine.roll_d20 = original_roll

    assert result["action_result"].get("action") == "skill_check", \
        f"FAIL: Investigation should be skill check, got {result['action_result'].get('action')}"
    assert result["action_result"].get("outcome") in ("success", "critical_success"), \
        f"FAIL: Should be success, got {result['action_result'].get('outcome')}"
    print("PASS: test_successful_investigation")


# =========================================================
# TEST 20: Failed Investigation
# =========================================================
def test_failed_investigation():
    """Failed investigation should use structured action_result."""
    reset_world_state()

    original_roll = engine.roll_d20
    engine.roll_d20 = lambda: 1
    try:
        result = run_turn("etrafı araştırıyorum")
    finally:
        engine.roll_d20 = original_roll

    assert result["action_result"].get("action") == "skill_check", \
        f"FAIL: Investigation should be skill check, got {result['action_result'].get('action')}"
    assert result["action_result"].get("outcome") in ("failure", "critical_failure"), \
        f"FAIL: Should be failure, got {result['action_result'].get('outcome')}"
    print("PASS: test_failed_investigation")


# =========================================================
# TEST 21: Malformed Intent JSON
# =========================================================
def test_malformed_intent_json():
    """Malformed JSON from Qwen should fallback gracefully."""
    reset_world_state()

    ollama_mock.chat.return_value = {
        "message": {"content": "this is not json at all"}
    }

    result = run_turn("merhaba")

    # Should not crash
    assert "narration" in result, "FAIL: Should return narration even with malformed JSON"
    print("PASS: test_malformed_intent_json")


# =========================================================
# TEST 22: Ollama Unavailable Fallback
# =========================================================
def test_ollama_unavailable():
    """When Ollama is unavailable, Python fallback should work."""
    reset_world_state()

    ollama_mock.chat.side_effect = Exception("Connection refused")

    result = run_turn("merhaba")

    assert "narration" in result, "FAIL: Should return narration even when Ollama fails"
    print("PASS: test_ollama_unavailable")


# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    tests = [
        test_failed_stealth_narrator_contradiction,
        test_unlocked_door_normal_open,
        test_locked_door_requires_check,
        test_force_door_requires_check,
        test_enter_through_door,
        test_location_name_vs_character_name,
        test_who_is_here,
        test_exit_location,
        test_return_travel,
        test_named_location_return,
        test_ground_item_same_location,
        test_ground_item_different_location,
        test_player_said_memory,
        test_false_memory_claim,
        test_draw_weapon,
        test_sheathe_weapon,
        test_unsupported_attack,
        test_ordinary_environment_look,
        test_successful_investigation,
        test_failed_investigation,
        test_malformed_intent_json,
        test_ollama_unavailable,
    ]

    passed = 0
    failed = 0
    failures = []

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            failed += 1
            failures.append((test.__name__, str(e)))
            print(f"FAIL: {test.__name__}: {e}")
        except Exception as e:
            failed += 1
            failures.append((test.__name__, f"ERROR: {type(e).__name__}: {e}"))
            print(f"ERROR: {test.__name__}: {type(e).__name__}: {e}")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    if failures:
        print("\nFailures:")
        for name, msg in failures:
            print(f"  - {name}: {msg}")
    print(f"{'='*50}")
    raise SystemExit(1 if failed else 0)
