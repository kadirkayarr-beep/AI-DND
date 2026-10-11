# Wave3 GO — conversation UX / held weapon / narration / POSIX

**Branch:** `repair/pre04-wave3-conversation-ux` @ `2c79299` (+ local suite evidence below)  
**Date:** 2026-10-07  
**Verdict:** **Wave3 GO** for the scoped items below. This is **not** the general game-stability GO.

## In scope — closed

| Item | Evidence | Status |
| --- | --- | --- |
| Conversation modes (say / do / ask_dm) + active interlocutor | prior Wave3 live + `evidence.json` / followups | PASS (prior) |
| `weapon_not_held` false reject (catalog vs `item_*` identity) | `WEAPON_NOT_HELD_FIX_REPORT.json`, `evidence_weapon_fix_live.json` | PASS |
| Rejected narration / no-retry (≤4 model turns) | `evidence_rejected_narration_live.json` (1 turn used) | PASS |
| POSIX HttpEvidence SIGTERM / SIGKILL | `evidence_posix_httpevidence_wsl.json`, `WSL_POSIX_STATUS.md` | PASS (WSL) |
| Release deterministic gates | `full_suite_release_gates_retry.log` — 22/22 | PASS |

## Full suite (context only)

See `FULL_SUITE_CHECK.json`.

- Release gates: PASS.
- API discover: 1406 ran, **11 fail**, 2 skip.
- All 11 fails are `DevelopmentToolingTests` (environment / health tooling; Wave3 suite note: `missing_tools: ['pnpm']` on the health path). **Not** weapon, narration, or combat regressions.
- 2 skips: Windows POSIX signal tests (already PASS under WSL).

These 11 fails **do not block Wave3 GO**. Fix ownership: **Game stability plan → Faz 7** (`oyun_stabilizasyon_planı`), not this Wave3 closeout.

## Explicitly out of scope here (other agent)

Owned by [Game stability implementation plan](file:///C:/Users/Kadir/.cursor/plans/oyun_stabilizasyon_planı_94c2a461.plan.md) on workspace `AI - DND`:

- Faz 0: smoke summary error-code preservation
- Faz 1: turn integrity, swallowed rollback, intent infra errors, hükümdar/lore WIP
- Faz 2: save/load/resume, corrupt save reject, query side-effects
- Faz 3–6: intent/lore cross, narration false-positives, combat/inventory retests, UI↔server sync / labels
- Faz 7: OpenAPI/diagnostics **and** the 11 `DevelopmentToolingTests` / pnpm PATH health split
- Faz 8: exit gate (two deterministic runs, seeded 30-turn, browser campaign)

Do **not** implement those on this Wave3 tree while that plan is in progress.

## Suite practice (Windows, this tree)

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
cd ai-dnd
python -u run_tests.py
# Full API discover is optional and noisy; expect DevelopmentTooling red if pnpm/PATH unhealthy.
```

Service/runtime logs under this report folder are gitignored; keep JSON evidence and `*_retry.log` summaries.

## Desktop copies

`AI - DND` is the active stability workspace — **do not delete**. Broader Desktop duplicate cleanup is deferred until that plan exits or the user names disposable folders.
