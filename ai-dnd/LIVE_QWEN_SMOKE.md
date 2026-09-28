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

## Quest Outcomes V1 API smoke — 2026-09-29

- Source tested: post-Phase-B `ai-dnd/game.py`, SHA-256 `b20c1635cbf81905185a784c8baebcb90dae41df646b6733a9ad2715226427c0`.
- The artifact-owned FastAPI service was restarted after the code changes. The smoke used its shared-proxy HTTP route, authenticated `qwen3:8b`, and one disposable in-memory session; no campaign was created or changed.
- Sequence: tavern travel, tavern exploration, presence, NPC greeting, NPC identity, and current-location query. All six turns returned HTTP 200, and each returned state matched the canonical state endpoint.
- Result: **PASS**, zero smoke issues, **9 model calls across 6 turns**, maximum **2 per turn**. Workflow logs confirmed real `qwen3:8b` calls.
- This general live smoke does not exercise quest lifecycle transitions. Those are covered by the deterministic engine and API persistence/isolation/rollback/narration tests. The production quest catalog intentionally remains empty pending owner-approved quest definitions.
- The historical `CHECKPOINT_CURRENT.sha256` was not changed; the new protected major checkpoint remains due after Phase D.

### Historical note — planned stage as of 2026-09-28

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

This was the planned integration path before the browser frontend work; the React/Vite experience and FastAPI connection have since been implemented. The Express/Postgres scaffold remains separate from the game engine. Do not add a Node-to-Python subprocess bridge. Combat V3 remains a later approved phase.