# Current-engine Qwen live smoke

Run: 2026-09-28, authenticated Ollama endpoint, `qwen3:8b`

- Source tested: current session-based `game.py`, SHA-256 `a068932dc4d42ecb873d3d0fc072036a418dc00f1efae59e1990f0a79d56950e`
- Sequence: tavern travel, tavern exploration, presence, NPC greeting, NPC identity, tavern name, current location, forest travel, forest exploration, remote-presence check, unsupported historical claim.
- First nine turns match the checkpoint smoke's action coverage: **14 model calls**, maximum 2 per turn. The two added safety turns used 3 more calls, for **17 calls across 11 turns**.
- Turn-level checks: **0 contradictions, 0 state/routing issues**; every turn used at most 2 model calls.
- The original checkpoint's nine-turn run also reported 14 calls. Its transcript is unavailable, so comparisons below use only the checkpoint summary, not a turn-by-turn diff.

## Narration guard replacements

Four model narrations were replaced with Python-grounded fallback text:

1. Tavern travel: the model made arrival conditional (“if you opened the door”) despite Python committing the travel.
2. Tavern exploration: the model mentioned unregistered customers; the safety guard rejected the unsupported people.
3. NPC greeting: the reply suggested choosing a drink/glass, which the player had not requested.
4. Forest exploration: the model described the registered “Gizli Yol” as becoming more visible to the player. The name-safety guard rejected it as an unregistered person/name; this appears to be a false positive on a title-cased feature name.

The checkpoint reported 3 fallbacks on its different run. This run had one additional fallback and did not reproduce the checkpoint's invented-sword travel narration.

## State changes

- Tavern travel committed `Henüz belirlenmedi` → `tavern` and accepted one ambient feature, `Sıcak Hava`.
- Tavern look and NPC interactions changed only Gromm's conversation memory; no player movement or inventory changes.
- Forest travel committed `tavern` → `forest` and accepted one NPC (`Kahraman Ağaç`) plus two location features (`Gizli Yol`, `Karanlık Çukur`).
- Forest exploration and the unsupported historical claim did not change world state.
- Presence in the forest named the forest NPC, not tavern NPC Gromm. The unsupported claim did not create or alter memories.

The complete UTF-8 JSON trace was emitted by `python ai-dnd/live_narration_smoke.py`; the model host and bearer token are not included in the trace.