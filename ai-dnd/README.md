# AI-DND

AI-DND is a Turkish-language terminal D&D game.

## Run

From the repository root:

```bash
python main.py
```

The game requires a reachable Ollama service for Qwen intent parsing and
narration. The deterministic engine still falls back safely when Ollama is
unavailable.

During play, use `/save` and `/load` (or `/kaydet` and `/yükle`).
The default file is `ai-dnd/saves/adventure.json`. Supply a path after the
command to use another slot, for example `/save saves/forest.json`.
Saving replaces the chosen slot; loading replaces the current session.
Saves include character, world state, NPC memories, and recent narration.
They are local JSON files, not tamper-proof or signed saves.

## Independent adventures

Imported callers can create independent adventures without changing the
terminal's default game:

```python
import game

first = game.create_session(seed=42)
second = game.create_session(seed=99)
result = game.execute_intent({"intent": "attack"}, "Gobline saldır", session=first)
first.save_game("saves/first.json")
```

Each session owns its character dictionary, world, recent narrations, chat
messages, and random generator. Helpers accept `session=`; bound calls such as
`first.run_player_turn("Etrafa bak")` select the same session for nested rules.
Calls without a session keep using the terminal's default adventure, including
legacy character globals and caller-held world/narration references.
Loading preserves the top-level character/world/history containers; nested
world records may be replaced. Saves remain version 1; random-generator state
and chat messages are not included in that format.

## Verify

```bash
python ai-dnd/run_tests.py
```

The runner covers the portable deterministic gates. Live tests are separate:

```bash
python ai-dnd/acceptance_test.py
python ai-dnd/live_intent_test.py
python ai-dnd/live_memory_test.py
```

Those live suites require the `qwen3:8b` model to be installed and available
through Ollama.