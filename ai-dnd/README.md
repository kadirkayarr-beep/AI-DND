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