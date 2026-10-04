"""
V10.1 Regression Tests for AI-DND game.py
Tests run without Ollama - they verify Python-side logic only.
"""
import sys
import io
import json
import re
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch, MagicMock

# Fix Windows console encoding

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
    global game
    game = engine.create_session(seed=11)
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
def travel_fixture(*, pending=None, route=False):
    """Known IDs do not imply a route; only this fixture owns its duration."""
    reset_world_state()
    game.ensure_campaign_clock()
    game.world_state["flags"]["pending_destination"] = pending
    if route:
        game.world_state["locations"]["tavern"]["travel_routes"] = {"forest": [420]}
    return game.world_state["campaign_time"]["elapsed_seconds"]


def assert_travel_result(result, *, status, success, location, pending, before, elapsed=0):
    """Reject narrative no-ops and verify both receipt and authoritative state."""
    action = result["action_result"]
    assert action["action"] == "travel", action
    assert action["status"] == status and action["success"] is success, action
    assert game.world_state["location"] == location, game.world_state
    assert game.world_state["flags"]["pending_destination"] == pending
    assert game.world_state["campaign_time"]["elapsed_seconds"] == before + elapsed
    assert action.get("time_result", {}).get("elapsed_seconds", 0) == elapsed, action
    if status == "completed":
        assert action["new_location"] == location, action
        assert game.world_state["journey"]["status"] == "ARRIVED"
    else:
        assert action.get("direct_response"), action
        assert "new_location" not in action, action


def assert_exit_result(result, *, status, success, location, pending, before):
    """Local scene exits are instant transitions, not cross-region journeys."""
    action = result["action_result"]
    assert action["action"] == "exit", action
    assert action["status"] == status and action["success"] is success, action
    assert action.get("direct_response"), action
    assert game.world_state["location"] == location
    assert game.world_state["flags"]["pending_destination"] == pending
    assert game.world_state["campaign_time"]["elapsed_seconds"] == before
    assert action["time_result"]["elapsed_seconds"] == 0, action
    assert game.world_state.get("journey") is None
    if success:
        assert action["target_id"] == location, action
        assert game.world_state["scene_state"]["player_position"]["location_id"] == location
    else:
        assert "target_id" not in action, action


def test_exit_location():
    """No recorded local exit means explicit refusal, even with a pending travel goal."""
    for pending in (None, "forest"):
        before = travel_fixture(pending=pending, route=True)
        result = run_turn("buradan çıkıyorum")
        assert_exit_result(result, status="unresolved", success=False,
                           location="tavern", pending=pending, before=before)
    print("PASS: test_exit_location")


def test_exit_location_known_destination():
    """Exit uses the registered local exit/parent, never an unrelated pending goal."""
    for field in ("exit_location_id", "parent_location_id"):
        before = travel_fixture(pending="castle")
        game.world_state["locations"]["tavern"][field] = "forest"
        result = run_turn("buradan çıkıyorum")
        assert_exit_result(result, status="completed", success=True,
                           location="forest", pending="castle", before=before)


def test_exit_location_invalid_destination():
    """An unregistered local exit must not be fabricated or consume travel time."""
    before = travel_fixture(pending="forest", route=True)
    game.world_state["locations"]["tavern"]["exit_location_id"] = "missing_exit"
    result = run_turn("buradan çıkıyorum")
    assert_exit_result(result, status="unresolved", success=False,
                       location="tavern", pending="forest", before=before)


# =========================================================
# TEST 9: "Geri dönüyorum"
# =========================================================
def test_return_travel():
    """No recorded journey or pending destination means a return needs clarification."""
    before = travel_fixture()
    result = run_turn("geri dönüyorum")
    assert_travel_result(result, status="clarification", success=False,
                         location="tavern", pending=None, before=before)
    assert game.world_state.get("journey") is None
    print("PASS: test_return_travel")


def test_return_travel_known_destination():
    """An explicitly pending return target still requires the server-owned route."""
    before = travel_fixture(pending="forest", route=True)
    with patch.object(game.rng, "randint", return_value=6):
        result = run_turn("geri dönüyorum")
    assert_travel_result(result, status="completed", success=True,
                         location="forest", pending=None, before=before, elapsed=420)


def test_return_travel_retraces_progress():
    """Interrupted, stopped and staged journeys retrace only actual elapsed progress."""
    for state in ("INTERRUPTED", "STOPPED", "TRAVELLING"):
        travel_fixture(pending="forest", route=True)
        game.world_state["locations"]["tavern"]["travel_routes"]["forest"] = [420, 180]
        with patch.object(game.rng, "randint", return_value=1 if state != "TRAVELLING" else 6):
            outward = run_turn("ormana gidiyorum")
        spent = 420 if state == "TRAVELLING" else 210
        assert outward["action_result"]["status"] == (
            "stage_completed" if state == "TRAVELLING" else "interrupted"
        ), outward
        assert outward["action_result"]["action"] == "travel", outward
        assert outward["action_result"]["time_result"]["elapsed_seconds"] == spent, outward
        assert game.world_state["location"] == "tavern"
        assert game.world_state["flags"]["pending_destination"] == "forest"
        assert game.world_state["journey"]["origin"] == "tavern"
        assert game.world_state["journey"]["destination"] == "forest"
        assert game.world_state["journey"]["status"] == (
            "TRAVELLING" if state == "TRAVELLING" else "INTERRUPTED"
        )
        if state == "STOPPED":
            stopped = run_turn("duruyorum")
            assert stopped["action_result"]["status"] == "stopped", stopped
        before = game.world_state["campaign_time"]["elapsed_seconds"]
        assert before == spent
        # A different pending goal must not replace the recorded retrace origin.
        game.world_state["flags"]["pending_destination"] = "forest"
        with patch.object(game.rng, "randint", side_effect=AssertionError("Retrace must not reroll encounters")):
            result = run_turn("geri dönüyorum")
        assert_travel_result(result, status="completed", success=True,
                             location="tavern", pending=None, before=before, elapsed=spent)
        assert game.world_state["journey"]["returning"] is True
        assert game.world_state["journey"]["destination"] == "tavern"


def test_return_travel_route_refusals():
    """Neither a pending goal nor movement language authorizes unknown/blocked routes."""
    for command in ("geri dönüyorum", "ormana geri dönüyorum"):
        for blocked in (False, True):
            before = travel_fixture(pending="forest", route=blocked)
            if blocked:
                game.world_state["blocked_travel_routes"] = {"tavern": {"forest": True}}
            result = run_turn(command)
            assert_travel_result(result, status="blocked" if blocked else "unverified",
                                 success=False, location="tavern", pending="forest", before=before)
            assert game.world_state.get("journey") is None


def test_exit_and_return_combat_refusal():
    """Bare commands cannot evade the existing normal-travel combat restriction."""
    for command in ("buradan çıkıyorum", "geri dönüyorum"):
        for pending in (None, "forest"):
            before = travel_fixture(pending=pending, route=True)
            game.world_state["locations"]["tavern"]["exit_location_id"] = "forest"
            if pending:
                with patch.object(game.rng, "randint", return_value=1):
                    outward = run_turn("ormana gidiyorum")
                assert outward["action_result"]["status"] == "interrupted", outward
                before = game.world_state["campaign_time"]["elapsed_seconds"]
            npc = game.create_npc_from_ai({"name": "Rakip", "role": "Guard", "location": "tavern"})
            with patch.object(engine, "roll_initiative_player", return_value=20), \
                 patch.object(engine, "roll_initiative", return_value=1):
                game.start_combat(npc)
            snapshot = deepcopy(game.world_state)
            try:
                run_turn(command)
            except engine.combat_lifecycle.CombatRequestError as exc:
                assert exc.code == "combat_travel", exc
            else:
                raise AssertionError(f"Combat must refuse travel: {command}")
            assert game.world_state["location"] == "tavern"
            assert game.world_state["flags"]["pending_destination"] == pending
            assert game.world_state["campaign_time"]["elapsed_seconds"] == before
            assert game.world_state.get("journey") == snapshot.get("journey")
            assert game.world_state["combat"] == snapshot["combat"]


# =========================================================
# TEST 10: Named Location Return
# =========================================================
def test_named_location_return():
    """Named return requires a verified route and charges its server-owned time."""
    reset_world_state()

    game.commit_location_change("forest")
    before_time = game.world_state["campaign_time"]["elapsed_seconds"]

    # Registered location names alone do not authorize travel duration.
    result = run_turn("tavernaya geri dönüyorum")
    action = result["action_result"]
    assert action["action"] == "travel", action
    assert action["status"] == "unverified" and action["success"] is False, action
    assert game.world_state["location"] == "forest"
    assert game.world_state["campaign_time"]["elapsed_seconds"] == before_time
    assert game.world_state.get("journey") is None

    # This fixture, not the model, owns the route. Suppress random encounters
    # so this check tests arrival rather than an interrupted journey decision.
    game.world_state["locations"]["forest"]["travel_routes"] = {"tavern": [300]}
    with patch.object(game.rng, "randint", return_value=6):
        result = run_turn("tavernaya geri dönüyorum")

    action = result["action_result"]
    assert action["action"] == "travel", action
    assert action["status"] == "completed" and action["success"] is True, action
    assert action["new_location"] == "tavern", action
    assert game.world_state["location"] == "tavern", \
        f"FAIL: Should return to tavern, got {game.world_state['location']}"
    assert action["time_result"]["elapsed_seconds"] == 300, action
    assert game.world_state["campaign_time"]["elapsed_seconds"] == before_time + 300
    assert game.world_state["journey"]["status"] == "ARRIVED"
    assert game.world_state["flags"]["pending_destination"] is None
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

    # Player claims NPC said something (second person)
    result = run_turn("daha önce bana bir hikaye anlatmıştın")
    narration = result.get("narration", "")
    assert "hatırlamıyorum" in narration.lower() or "buna dair bir kayıt yok" in narration.lower(), \
        f"FAIL: Should deny false memory claim, got: {narration}"

    # Player claims NPC said something (third person with named entity)
    result2 = run_turn("TestNPC bana ejderha hazinesinden bahsetmişti.")
    narration2 = result2.get("narration", "")
    assert "hatırlam" in narration2.lower() or "kayıt yok" in narration2.lower() or "bulunmuyor" in narration2.lower(), \
        f"FAIL: Should deny third-person false memory claim, got: {narration2}"
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
    """Legacy name: an invalid local target must be rejected without side effects."""
    reset_world_state()

    # Reject both a nonexistent enemy and one that exists only elsewhere.
    for remote_enemy in (False, True):
        if remote_enemy:
            game.create_npc_from_ai({
                "name": "Düşman", "role": "Guard", "location": "forest",
            })
        before_world = deepcopy(game.world_state)
        before_character = deepcopy(game.character)
        before_rng = game.rng.getstate()
        before_narrations = list(game.recent_dm_narrations)
        with patch.object(engine, "parse_player_intent") as parse, \
                patch.object(ollama_mock, "chat") as chat:
            try:
                run_turn("düşmana saldırıyorum")
            except engine.combat_lifecycle.CombatRequestError as exc:
                assert exc.code == "invalid_combat_target", exc.code
                assert exc.status_code == 400, exc.status_code
            else:
                raise AssertionError("Invalid local target must raise CombatRequestError")
            parse.assert_not_called()
            chat.assert_not_called()

        assert game.world_state == before_world, "Rejected attack changed world state"
        assert game.character == before_character, "Rejected attack changed character"
        assert game.rng.getstate() == before_rng, "Rejected attack consumed dice"
        assert list(game.recent_dm_narrations) == before_narrations

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

    # Regression coverage for exact phrase "Etrafımda neler var?" with multiple NPCs present
    game.world_state["npcs"] = [
        {"id": "npc_001", "name": "Gromm", "role": "Barmen", "location": "tavern"},
        {"id": "npc_002", "name": "Elaris", "role": "Müşteri", "location": "tavern"},
    ]
    result2 = run_turn("Etrafımda neler var?")
    assert result2["action_result"].get("action") == "explore", \
        f"FAIL: 'Etrafımda neler var?' should resolve as explore, got: {result2['action_result']}"
    assert result2["action_result"].get("status") == "observed", \
        f"FAIL: 'Etrafımda neler var?' should have status observed, got: {result2['action_result']}"
    assert "Bu tanıma uyan birden fazla kişi var" not in result2.get("narration", ""), \
        f"FAIL: 'Etrafımda neler var?' misrouted as dialogue clarification: {result2.get('narration')}"
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
# TEST 23: Terminal /skill command uses active session character
# =========================================================
def test_terminal_skill_command():
    """Verify /skill stealth 15 terminal command executes without NameError and uses active session character."""
    import runpy

    game_file = Path(engine.__file__).resolve()
    save_file = engine.DEFAULT_SAVE_PATH
    inputs = ["1", "2", "SkillHero", "/skill stealth 15", "çık"] if save_file.is_file() else ["2", "SkillHero", "/skill stealth 15", "çık"]
    input_iter = iter(inputs)

    captured_out = io.StringIO()
    with patch("builtins.input", lambda prompt="": next(input_iter)), \
         patch("sys.stdout", captured_out):
        try:
            mod = runpy.run_path(str(game_file), run_name="__main__")
        except SystemExit:
            pass

    output = captured_out.getvalue()
    assert "🎲 SKILL CHECK" in output, f"FAIL: Output should contain SKILL CHECK header:\n{output}"
    assert "Skill: Stealth" in output, f"FAIL: Output should contain Skill: Stealth:\n{output}"
    active_char = mod["_session"]().character
    dex_mod = active_char["modifiers"]["dexterity"]
    expected_mod_str = f"+{dex_mod}" if dex_mod >= 0 else str(dex_mod)
    assert f"Ability Modifier: {expected_mod_str}" in output, \
        f"FAIL: Expected Ability Modifier {expected_mod_str} in output:\n{output}"
    print("PASS: test_terminal_skill_command")


# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    tests = [
        test_failed_stealth_narrator_contradiction,
        test_unlocked_door_normal_open,
        test_locked_door_requires_check,
        test_force_door_requires_check,
        test_enter_through_door,
        test_location_name_vs_character_name,
        test_who_is_here,
        test_exit_location,
        test_exit_location_known_destination,
        test_exit_location_invalid_destination,
        test_return_travel,
        test_return_travel_known_destination,
        test_return_travel_retraces_progress,
        test_return_travel_route_refusals,
        test_exit_and_return_combat_refusal,
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
        test_terminal_skill_command,
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
