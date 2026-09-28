#!/usr/bin/env python3
"""Test validate_intent function"""
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_DIR = Path(__file__).resolve().parent
GAME_FILE = PROJECT_DIR / "game.py"
sys.path.insert(0, str(PROJECT_DIR))
import game
session = game.create_session()

# Test the normalize_intent function directly
print("Testing normalize_intent for 'tavernaya gidiyorum':")
result = session.normalize_intent({'intent': 'travel', 'target': {'reference': 'tavern'}}, 'tavernaya gidiyorum')
print('normalize_intent result:', result)

print("\nTesting validate_intent for travel:")
result = session.validate_intent({'intent': 'travel', 'target': {'type': 'none', 'reference': 'tavern'}}, 'tavernaya gidiyorum')
print('validate_intent result:', result)

print("\nTesting normalize_intent for 'nerdeyim':")
result = session.normalize_intent({'intent': 'query', 'query_type': 'location'}, 'nerdeyim')
print('normalize_intent result:', result)

print("\nTesting validate_intent for query:")
result = session.validate_intent({'intent': 'query', 'target': {'type': 'none', 'reference': ''}}, 'nerdeyim')
print('validate_intent result:', result)

print("\nTesting normalize_intent for 'etrafımda neler var':")
result = session.normalize_intent({'intent': 'explore', 'explore_type': 'observe'}, 'etrafımda neler var')
print('normalize_intent result:', result)

print("\nTesting validate_intent for explore:")
result = session.validate_intent({'intent': 'explore', 'target': {'type': 'none', 'reference': ''}}, 'etrafımda neler var')
print('validate_intent result:', result)

print("\nTesting typo normalization:")
_normalize_turkish_typos = session._normalize_turkish_typos
print('_normalize_turkish_typos("nerdeyim"):', _normalize_turkish_typos('nerdeyim'))
print('_normalize_turkish_typos("tavernaya gidiyorum"):', _normalize_turkish_typos('tavernaya gidiyorum'))
print('_normalize_turkish_typos("ormana gidiyorum"):', _normalize_turkish_typos('ormana gidiyorum'))