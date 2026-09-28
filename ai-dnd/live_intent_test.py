#!/usr/bin/env python3
"""
LIVE qwen3:8b Intent Parser Integration Test
Uses REAL Ollama - NO MOCKS
"""
import sys
import io
import json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_DIR = Path(__file__).resolve().parent
GAME_FILE = PROJECT_DIR / "game.py"
sys.path.insert(0, str(PROJECT_DIR))

# Import REAL ollama
try:
    import ollama
    print(f"✅ ollama module imported: {type(ollama)}")
except Exception as e:
    print(f"❌ Failed to import ollama: {e}")
    sys.exit(1)

# Verify Ollama connectivity and qwen3:8b availability
print("\n=== OLLAMA CONNECTIVITY CHECK ===")
try:
    models_response = ollama.list()
    model_names = [m.model for m in models_response.models]
    print(f"Available models: {model_names}")
    
    qwen_available = any('qwen3:8b' in name for name in model_names)
    if qwen_available:
        print("✅ qwen3:8b FOUND")
    else:
        print("❌ qwen3:8b NOT FOUND")
        print("Available models:", model_names)
        sys.exit(1)
except Exception as e:
    print(f"❌ Ollama connectivity failed: {e}")
    sys.exit(1)

# Now load game.py functions (without executing main loop)
print("\n=== LOADING GAME.PY FUNCTIONS ===")
import game
session = game.create_session()

# Extract functions we need
parse_player_intent = session.parse_player_intent
normalize_intent = session.normalize_intent
validate_intent = session.validate_intent

print("✅ Game functions loaded (parse_player_intent, normalize_intent, validate_intent)")

# Test helper
def test_intent_parser(player_input, test_name):
    print(f"\n{'='*70}")
    print(f"LIVE TEST: {test_name}")
    print(f"Input: {player_input}")
    print(f"{'='*70}")
    
    # Step 1: RAW parse_player_intent (calls real qwen3:8b)
    print("\n--- RAW parse_player_intent ---")
    raw = parse_player_intent(player_input)
    print(f"Raw model output: {json.dumps(raw, ensure_ascii=False)}")
    
    # Step 2: Normalize
    print("\n--- normalize_intent ---")
    normalized = normalize_intent(raw, player_input)
    print(f"Normalized: {json.dumps(normalized, ensure_ascii=False)}")
    
    # Step 3: Validate
    print("\n--- validate_intent ---")
    validated = validate_intent(normalized, player_input)
    print(f"Validated: {json.dumps(validated, ensure_ascii=False)}")
    
    return raw, normalized, validated

# ============================================================
# TEST A: ATTACK CLASSIFICATION
# ============================================================
print("\n" + "="*70)
print("TEST A: ATTACK CLASSIFICATION")
print("="*70)

raw_a, norm_a, val_a = test_intent_parser(
    "Gromm'a kılıcımla saldırıyorum",
    "ATTACK - Gromm'a kılıcımla saldırıyorum"
)

intent_a = val_a.get('intent')
passed_a = intent_a in ('attack', 'combat')
print(f"\n>>> RESULT: {'PASS' if passed_a else 'FAIL'} - intent = {intent_a}")

# ============================================================
# TEST B: DIALOGUE CLASSIFICATION
# ============================================================
print("\n" + "="*70)
print("TEST B: DIALOGUE CLASSIFICATION")
print("="*70)

raw_b, norm_b, val_b = test_intent_parser(
    "Gromm, bugün nasılsın?",
    "DIALOGUE - Gromm, bugün nasılsın?"
)

intent_b = val_b.get('intent')
passed_b = intent_b in ('dialogue', 'narrative') and intent_b not in ('attack', 'combat')
print(f"\n>>> RESULT: {'PASS' if passed_b else 'FAIL'} - intent = {intent_b}")

# ============================================================
# TEST C: TRAVEL CLASSIFICATION
# ============================================================
print("\n" + "="*70)
print("TEST C: TRAVEL CLASSIFICATION")
print("="*70)

raw_c, norm_c, val_c = test_intent_parser(
    "Eski Ay Kulesi'ne gidiyorum",
    "TRAVEL - Eski Ay Kulesi'ne gidiyorum"
)

intent_c = val_c.get('intent')
completion_c = val_c.get('completion')
passed_c = intent_c == 'travel' and completion_c in ('completed', 'intended')
print(f"\n>>> RESULT: {'PASS' if passed_c else 'FAIL'} - intent = {intent_c}, completion = {completion_c}")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "="*70)
print("LIVE INTENT PARSER TEST SUMMARY")
print("="*70)
print(f"Ollama module: {type(ollama)}")
print(f"Model used: qwen3:8b (verified)")
print(f"{'TEST':<30} {'PASS/FAIL':<10} {'RAW INTENT':<15} {'VALIDATED INTENT':<15}")
print("-"*70)
print(f"{'A) ATTACK':<30} {'PASS' if passed_a else 'FAIL':<10} {raw_a.get('intent'):<15} {val_a.get('intent'):<15}")
print(f"{'B) DIALOGUE':<30} {'PASS' if passed_b else 'FAIL':<10} {raw_b.get('intent'):<15} {val_b.get('intent'):<15}")
print(f"{'C) TRAVEL':<30} {'PASS' if passed_c else 'FAIL':<10} {raw_c.get('intent'):<15} {val_c.get('intent'):<15}")
print("-"*70)

total_passed = sum([passed_a, passed_b, passed_c])
print(f"\nTOTAL: {total_passed}/3 PASS")

if total_passed == 3:
    print("✅ ALL LIVE TESTS PASSED")
    sys.exit(0)
else:
    print("❌ SOME LIVE TESTS FAILED")
    sys.exit(1)