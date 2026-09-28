# AI Pipeline V10 Promotion Checkpoint

Date: 2026-09-28

## Production source

- C:\Users\Kadir\Desktop\AI-DND\game.py
- Final SHA-256: 67BE354A2E6C25AC5028FD9CFA11C53886B04E2D2A5889B84E219E37C6E92DC8
- Byte-identical to the approved staging source.
- Hash before remaining promotion gates and after all gates/smoke: unchanged.

## Validation results on actual main

- Syntax: PASS
- Narrator safety: 18/18 PASS
- AI semantic suite: 87/87 PASS
- Combat V2: 24/24 PASS
- Combat V1: 10/10 PASS (A-J)
- Regression: 22/22 PASS
- Acceptance: 20/20 PASS
  - Exact source loaded: C:\Users\Kadir\Desktop\AI-DND\game.py
  - Exact location-name input: buranın adı ne?
  - Contradictions: 0
  - State issues: 0
- Real Ollama smoke: PASS against actual main using local qwen3:8b, without mocked parser/intents or trace_ai_pipeline.
  - Sequence: tavern travel, exploration, presence, NPC dialogue, NPC name, tavern name, current location, forest travel, forest exploration.
  - Canonical NPC dialogue and identity query worked.
  - Location queries returned Taverna.
  - Natural exploration succeeded.
  - Total model calls: 14 across 9 turns.
  - Maximum calls per turn: 2 (all turns at or below the limit).
  - Fallbacks: 3, each due to a specific security check:
    1. Turn 1: narrator phrased completed travel conditionally ("if you opened the door"); guarded as conditional/uncommitted narration.
    2. Turn 2: Qwen used “müşteriler” in a tavern description. The security filter checks this person term against NPC facts, while the world feature already mentions customers; it conservatively fell back to registered-state narration. This was a single false-positive observation; the other smoke exploration turns narrated naturally, so safe exploration was not repeatedly rejected.
    3. Turn 8: narrator claimed the player swung a sword during travel, which the input did not request; guarded as an invented player action.
  - No repeated generic-fallback pattern observed.
  - Full UTF-8 transcript: work\promotion_qwen_smoke_utf8.txt in the Codex validation workspace.

## Protected backups

- game_backup.py: SHA-256 B68FBC56606255611AD33E7E9D1518CA255F5315E85EBF938682B03755611E5B
- game_v10_backup_20260927.py: SHA-256 2E78DB08E6879CCA00786A355B8F0F449A8BF268273EE3261EFC08AB5A2BFBBA
- game_v10_backup_before_v11_20260927.py: SHA-256 2E78DB08E6879CCA00786A355B8F0F449A8BF268273EE3261EFC08AB5A2BFBBA
- All protected backups remained unchanged.

## Architecture invariant

PYTHON DECIDES REALITY. QWEN UNDERSTANDS INTENT AND DESCRIBES REALITY.

No production code was changed during post-promotion validation. No Combat V3 work was started.