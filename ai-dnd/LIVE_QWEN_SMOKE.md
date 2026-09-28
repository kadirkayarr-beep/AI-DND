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

## Session engine final live freeze — 2026-09-28

- Source tested: current session-based `game.py`, SHA-256 `e971f4cade451828697ab7c49900b634a9cf1a6a1997aa8c733d2a13e0a9c24a`.
- Authenticated preflight: remote service reachable **YES**; `/api/tags` **OK**; `qwen3:8b` detected **YES**.
- Live smoke: **PASS** against the current source hash, with the real `qwen3:8b` service and no fake parser, intent, or model responses.
- Turns: **11** — tavern travel, tavern exploration, presence, NPC greeting, NPC identity, tavern name, current location, forest travel, forest exploration, remote-presence check, and unsupported historical claim.
- Model calls: **17 total**, maximum **2 per turn**.
- Narration replacements: **1**. During tavern exploration, the model named the player character (`TestHero`) in non-travel narration. The Python safety guard rejects player-name narration outside a completed travel arrival, so it replaced the prose with the grounded list of registered tavern entities.
- Contradictions and state/routing issues: **0**. The exploration turn only recorded its expected dialogue memory; world location and inventory remained unchanged.
- `game.py` SHA-256 remained `e971f4cade451828697ab7c49900b634a9cf1a6a1997aa8c733d2a13e0a9c24a` after the deterministic gates, authenticated preflight, and live smoke.
- `CHECKPOINT_CURRENT.sha256` now records the current engine hash. Historical checkpoint hashes were not changed; `game.py` was not modified.

**SESSION ENGINE + AI PIPELINE VERIFIED**

Architectural invariant: **PYTHON DECIDES REALITY. QWEN UNDERSTANDS INTENT AND DESCRIBES REALITY.**

### Next planned stage — not implemented

```text
React/browser frontend
        ↓
Python FastAPI adapter
        ↓
GameSession
        ↓
game.py rules engine
        ↓
authenticated Ollama qwen3:8b
```

The existing Express/Postgres scaffold is not connected to the game. The Python API should import the engine directly; do not add a Node-to-Python subprocess bridge. No UI or Combat V3 work was started during this verification.