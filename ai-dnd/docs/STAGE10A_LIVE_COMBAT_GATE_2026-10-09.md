# Cursor integration handoff — Stage 10A live combat gate, 9 October 2026

## Acceptance

The live combat gate’s mechanical checks passed and the four Python sentences match published HP, the miss, and the 6-damage critical. **Stage 10A is not certified. Stage 10B remains BLOCKED. Production remains NO-GO.**

Qwen was configured and the isolated health check reported `qwen3:8b`. No combat turn called the model. The existing courtyard, end-turn, and attack owners returned direct sentences. This run does not certify live model combat prose.

## Checkout

`C:\Users\Kadir\Desktop\AI-DND-phase8-expansion`, branch `phase8/emergent-storytelling-expansion`, HEAD `f63d952506064cd59e960f1e3efa6627d4e52053`. Dirty tree preserved. No commit, push, merge, reset, or clean. Shop owner, lore pack, `game.py`, and the 20-turn narration evidence were not edited.

`game.py` SHA-256 remains `7c2a449b88a934f196ffe275ee7fc6cc862c7cdde52dd8994962a26f15921c37`. `shop_creation.py` remains `3f86af37ecc79bc870c2d8c3f0e6188c8eea404cfb6f61a31f2d94b8c3779c6d`.

## What was added

One new runner, `ai-dnd/api/tests/live_neverwinter_combat_gate.py`, SHA-256 `c6cd854bbe798a7eefb3a29a1aebe4a280d58e98bb8eee81d09df53a8f5fda54`.

It starts the existing isolated Neverwinter API, creates a normal campaign, and sends only the authored player lines `Avlu karşılaşmasına gir`, `Avlu çatışmasını başlat`, `Turumu bitiriyorum`, and `Saldırıyorum.` with the participant ID the courtyard owner just published. It does not insert an NPC, patch dice, or send a `combat_action` fixture.

## Evidence

`.local/evidence/stage10a-live-combat-20261009/live-combat-gate.json`

Command, from `ai-dnd`, with `PYTHONUTF8=1` and `OLLAMA_HOST=http://127.0.0.1:11434`:

```text
python -m api.tests.live_neverwinter_combat_gate
```

Exit 0. Status `MECHANICAL_PASS_NEEDS_MANUAL_NARRATION_REVIEW`. Four turns, all 0 model calls, no narration retry.

| Check | Result |
|---|---|
| Origin | Opt-in `open_courtyard_commoner_v1`; absent before the enter line. |
| Participant | `npc_001`, statblock `mm2024.commoner`, source printed p.77. |
| Initiative | Order `player`, `npc_001`. Combat ID `8a086007-2f86-4d3c-89f2-bfd702b9d0a4`. |
| Action economy | Commoner `movement_used` 55, `dash_count` 1, then returned the turn to the player. |
| Rolls and HP | Player roll 1, 0 damage, commoner stays 4/4. Enemy roll 20, 6 damage. Player 12 to 6. |
| Narration | Turn 4 states the miss and 6 damage. Review: `MANUAL_NARRATION_REVIEW.md` in the same evidence folder. |
| Calls | 0 on every turn. Limit of 2 held. No post-gate call. |
| Persistence | Resume kept that combat ID active and HP 6 / 4. |
| Isolation | A second campaign had no courtyard and no active combat. |
| Rewards | XP stayed 0. Quests, inventory, and currency stayed unchanged. |

Dice were the session RNG. The test did not choose the 1 or the 20.

## Remaining blockers

- No Qwen combat sentence exists, so model combat narration is still unverified.
- Turn 1’s owner sentence says “Avlu saldırganı” while the public name is “Yakındaki kişi”.
- Turn 3 does not mention the commoner’s close to 5 feet.
- Live combat still has no canonical Neverwinter hostile outside this opt-in courtyard.
- Replit, whole-repository acceptance, Stage 10B, and production remain unapproved.
