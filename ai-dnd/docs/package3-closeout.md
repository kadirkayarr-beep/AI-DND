# Package 3 closeout — GO

Acceptance completed on 2026-10-06. This supersedes the earlier NO-GO report;
earlier failed or lost runs are not counted as passing evidence.

## Completion contract

Preserve the existing implementation and owners. Python owns mechanics and
canonical state; lore authority owns Forgotten Realms facts. Qwen may interpret
ambiguous intent or narrate verified outcomes, with at most two calls and one
deterministic fallback, never a narration retry. Model world proposals do not
establish canon. Public payloads contain only player-known reality.

No rewrite, parallel mechanical owner, geography/catalog replacement, new
mission, task queue, merge/rebase/reset/force push or publish was performed.
Only full GO authorizes normal commit/push and fresh remote parity verification.

## Completed scope

- Preserved catalog geography, IDs, saved-definition compatibility, existing
  travel/time/check/damage/combat/rest/death owners and atomic rollback/replay.
- Retained PHB2024 pace tables: 400/300/200 ft/min, 4/3/2 mi/hour,
  30/24/18 mi/day, terrain/good-road caps and slowed travel. Legacy saved
  journeys retain their established duration convention.
- Actual walking accumulates by calendar day. Hour 9 uses CON DC11; hour 10
  uses DC12. Failed saves add canonical Exhaustion, with penalties, speed,
  lethal level-six boundaries and explicit long-rest recovery. Waiting does
  not count as walking or perform a rest. Fatal movement stops immediately.
- Bounded tracking/reacquire uses 600 seconds in confined areas and 3600
  seconds outdoors. Partial progress, bounded attempts and saved results
  survive reopening; missing/hidden trails grant no action.
- Standard locks use quality DC10/15/20 and simple/complex durations 6/60
  seconds, owned thieves' tools and existing proficiency/check rules.
  Missing prerequisites do not mutate time/RNG. Authored local lock policy
  remains distinct and compatible.
- Stages and expedition state are projected into the generated API clients
  and Turkish primary frontend. Known-only destinations, durations,
  progress, obstacles, decisions and actions remain server-owned.
- Public extended-travel save history includes native DC, dice, selected
  roll, modifiers, total and outcome. It renders after reload without local
  rolls or reconstruction. Current-day projection hides stale prior-day
  walking counters without mutating the retained internal ledger.
- Optional supplies remain explicitly disabled for legacy campaigns.
  Enabled mode consumes canonical inventory units, records daily receipts,
  forages only authored known ground resources and applies owned missing-
  resource conditions. Replays do not consume twice. Lethal supplies stop
  rest at midnight without healing/revival.
- General narration cannot commit model-proposed locations, NPCs, shops,
  features or events. Existing lore/named-entity/smalltalk safety and resolved
  fallbacks remain intact; the narrow exploration narration template is not
  imposed on every general action.
- Preserved Perception discovery versus known-clue Investigation, passive
  local notice, challenge-specific retries, hidden/nonlocal filtering,
  lifecycle boundaries, session isolation and no automatic rests.

## Final frozen-source evidence

Source manifest: `.local/evidence/package3-completion/source-complete.json`.
It fingerprints 879 tracked/nonignored source files. SHA256:

`44d1262fb88b49398c682c4110505f0c48d7cb078aeb92761ccc6b693d5e1b8a`

No fingerprinted source changed during final acceptance. Logs below are
durable local development evidence, not certification of historical runs.

| Check | Actual final result | Log under `.local/evidence/package3-completion/` |
|---|---|---|
| Focused package/closeout/new boundaries | 57 passed, 25.446s | `focused-complete.log` |
| Full API unittest discovery | 1285 passed, 403.157s | `api-complete.log` |
| Release deterministic gates | All 22 passed | `release-complete.log` |
| Primary frontend | 63 passed | `frontend-complete.log` |
| Shared-library codegen/typecheck | Passed | `codegen-checks.log` |
| Primary frontend typecheck | Passed | `typecheck-complete.log` |
| Production build | Passed, 10.14s | `build-complete.log` |
| Actual HTTP/authenticated Qwen/replay | Passed | `http-qwen-complete.log` |
| Targeted browser correction/reload | Passed | `browser-fixed.json` |

The shell build initially omitted the artifact's required PORT/BASE_PATH.
Supplying the existing service configuration fixed the invocation without
changing source. The existing >500kB chunk warning remains non-blocking.
SIGKILL evidence still requires the actual signal and full-tree fingerprints;
its subprocess startup budget includes hashing time rather than waiving proof.

## Real HTTP/Qwen and browser acceptance

A disposable isolated SQLite campaign used a real socket HTTP server and the
existing authenticated qwen3:8b adapter, without parser/model mocks. Look,
search, Investigation, disarm, unlock and open used zero chats. The
entry-to-hall resolved transition contacted Qwen exactly once; its rejected
narration used the deterministic verified fallback. Identical replay and
replay after reopening returned the exact saved response with zero chats and
no additional canonical public-state mutation.

One comprehensive browser pass used only the explicitly named disposable
fixtures with persisted RNG seed 11; production odds were not changed:

- Complete fixture: known trail DC10 took 600s; standard good/simple lock
  DC15 took 6s and retained tools; supplies toggle and known-resource forage
  worked. The 6-mile/two-hour journey crossed hours 9 and 10 without resting.
  Native saved results were DC11 SUCCESS (17 + 2 = 19) and DC12 FAILURE
  (7 + 2 = 9), ending with Exhaustion 1, HP12, 10h walking and 11 inventory
  entries. Reload/resume retained time 11:10:06 and all results/resources.
- Dungeon fixture: initial payload did not reveal wire/hall/vault/lever/
  rubble/marker. Perception, Investigation, disarm, unlock/open, hall
  traversal, lever/rubble neutralization, vault traversal and marker discovery
  worked. Reload retained Eski Mahzen, turn22, HP12 and 17:21:18, without
  repeated time/damage. Prior-room outcomes remained in history, not falsely
  exposed as current-room obstacles. Quest journal remained empty.

The first browser pass correctly found that saves were internal but missing
from public state/UI. That gap was fixed and only the affected saved-result
flow was rechecked by the same tester. Both native saved rows now survive
resume; the entire API/release matrix was rerun on the corrected source.

390px mobile had no horizontal overflow, named controls remained accessible,
and reduced-motion preference was active. The root Replit banner-script 502
is known preview noise; game API requests succeeded. Screenshots: `53ku4o`,
`k77mid` (walkthrough), `j3jyoq`, `d4ccqx` (corrected saved checks),
`mk06hr` (details guidance). The fixture campaigns remain disposable and
clearly labeled.

## Git closeout

GO was reached on `main`, before the authorized normal commit/push.
Pre-commit HEAD was `05647e582754c6483145da39fd891b4a0dc9b418`.
Cached origin/main was `5983853dbb6ae7d4852f4a3f8e070c3fe1e440f1`;
that cached value is not a fresh remote comparison.

The final synchronization evidence is recorded after this report's commit in
`.local/evidence/package3-completion/git-final.log`: normal commit/push,
fresh fetch, exact HEAD/origin-main equality, ahead/behind 0/0 and clean tracked
tree are required. No destructive synchronization or publishing is authorized.
