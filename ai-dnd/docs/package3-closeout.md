# Package 3 closeout — NO-GO

## Completion contract v1.0

This records the current user-requested contract, not a claim that the package
is complete. Preserve the existing implementation and owners. Python owns
mechanics and canonical state; the lore authority owns Forgotten Realms facts.
Qwen may parse ambiguous intent or narrate eligible verified outcomes, with at
most two calls and one deterministic fallback, never a narration retry.
Player-facing payloads must contain only player-known reality.

Required scope includes PHB2024 pace tables (400/300/200 ft/min,
4/3/2 mi/hour, 30/24/18 mi/day), terrain/good-road caps, slowed travel,
extended-travel CON saves and Exhaustion, bounded stages/navigation/tracking,
Perception notice versus Investigation reasoning, passive/local discovery,
persistent challenge-specific retries, authored/standard lock and tool
policies, source/lifecycle policies, no automatic rests, and optional supplies
that are safely disabled for legacy campaigns. No parallel mechanical owner,
rewrite, decomposition, new mission, task queue, or publish is authorized.

GO requires complete scope and fresh acceptance evidence. Only GO authorizes a
normal commit/push, fresh remote fetch, HEAD == origin/main and a clean tracked
tree. Current decision is **NO-GO**. No manual commit, fetch, push, or publish
was performed.

## Preserved and implemented

- Existing catalog geography, IDs, strict saved-definition checks and
  travel/time/check/damage/combat/save owners remain in place.
- Player projection filters undiscovered catalog locations, inaccessible local
  entities, hidden interactables and nonlocal doors. Scene referents receive
  the same server-filtered view. An exit's destination is nullable until known;
  descriptions do not name the room behind a still-closed door.
- Discovery knowledge persists. Arrival/opening records adjacent known reality;
  passive notice is local, roll-free and not triggered by state GET requests.
- Active searching uses Perception. A second paid careful pass can resolve the
  authored local search after a failed first roll without infinite rerolls.
  Investigation operates on an already-discovered local clue and records its
  reasoning separately. Known conclusions do not consume another roll/time.
- New distance journeys use the PHB hourly table, terrain caps, a one-step
  good-road adjustment and the existing speed owner for slowed solo travel.
  Pace modifiers no longer leak into STOPPED, INTERRUPTED, ARRIVED or combat
  checks. Legacy saved journeys retain their previous duration convention.
- Stage metadata is persisted internally without invented intermediate nodes.
- Eligible dungeon/environment narration receives a small verified packet,
  not the hidden catalog. Rejection falls back once without world proposals.
  The adapter rejects a third chat call before sending it to the network.
- Local rule/provenance metadata was added outside the frozen saved geography.

## Mandatory acceptance still open

These are unfinished parts of this request, **not follow-up tasks**:

1. Extended-travel accounting, CON save thresholds, and full Exhaustion
   integration through canonical condition/save/rest/death owners.
2. Tracking/reacquire with the confined 10-minute and outdoors one-hour rules.
3. Standard DMG lock quality/complexity defaults and canonical thieves'
   tools/proficiency policy; existing local authored lock behavior is retained.
4. Complete player-facing richer-stage projection/rendering. Current stage
   metadata is internal; the existing progress view is not full acceptance.
5. Removal/containment of the legacy general turn path's validated model world
   proposals. The new scoped narration branch does not certify all older
   narration paths against the stricter package boundary.
6. Explicit optional-supplies policy and enabled-mode resource behavior.
7. A clean fresh aggregate regression/release run after all remaining scope
   is complete. Passing selected checks does not certify the whole package.

There was no credential/environment blocker preventing the work performed.
These incomplete mechanics are the reason for NO-GO; do not describe the
package as finished or production-ready.

## Fresh evidence from this work

Logs are local development evidence, not historical certification:

| Check | Actual result | Log |
|---|---|---|
| `python -m unittest api.tests.test_exploration_package api.tests.test_exploration_closeout -q` | 36 passed, 18.938s | `/tmp/package3-focused-final.txt` |
| Added local Investigation refusal/known-clue check | Passed on targeted recheck | `/tmp/package3-rechecks.txt` |
| `pnpm --filter @workspace/ai-dnd-experience test` | 61 passed | `/tmp/package3-frontend-final.txt` |
| Experience `tsc --noEmit` | Passed | shell exit 0 |
| Experience production build | Passed, 10.42s; existing chunk-size warning | `/tmp/package3-build-final.txt` |
| API unittest discovery | 1264 run, 1 failure + 1 error, 384.228s | `/tmp/package3-api-regressions.txt` |
| API failure/error rechecks | Both passed independently | `/tmp/package3-evidence-recheck.txt`, `/tmp/package3-rechecks.txt` |
| `python run_tests.py` release gates | Failed the persistence gate | `/tmp/package3-release.txt` |
| Corrected persistence validation gate | 6 passed, 0.098s | `/tmp/package3-persistence-fixed.txt` |

The API-discovery failure correctly detected source edits during its own
evidence subprocess; the error was a 10-second SIGKILL fixture timeout under
concurrent checks. Neither is waived: targeted rechecks passed, but the original
aggregate run remains failed. Persistence exposed invalid list-valued flags
raising AttributeError; validation now rejects that input with ValueError before
mutation, and its six-case gate passed. No fresh aggregate PASS is claimed.

Real authenticated Qwen evidence: a disposable separate SQLite campaign using
actual qwen3:8b HTTP inference traversed entry → hall. Look, search, clue
Investigation, disarm and door operations each used zero chats; the resolved
room transition used one; identical replay returned exactly the saved response
with zero chats. HP remained 12. Evidence: `/tmp/package3-live-qwen.txt`.
The adapter's fake-client boundary test additionally proved chat #3 cannot
reach the client. Rejected narration was tested to fall back once without
canonical mutation.

One real browser pass succeeded using the separately named disposable campaign
and seed 11, prepared through actual navigation/travel owners without changing
production odds or adding a public test backdoor. It checked the entire ordinary
resume payload before discovery, Perception/Investigation cards, wire disarm,
unlock/open, hall traversal, lever/rubble neutralization, vault traversal,
marker discovery and save/reload/resume. Final location: Eski Mahzen, turn 22,
HP 12, time 1 Mirtul 1501 DR 17:21:18; no duplicated time or damage.
390px mobile had no horizontal overflow; nested vertical panel scrolling remains.
Prior-room obstacle persistence was supported by saved history/traversal,
not a claim that the final-room projection displayed those obstacles.

Browser screenshots: `lpjbha` entry before search, `kjwtzb` hall,
`dfttmr` reopened vault, `oc5yyc` mobile restored clue view.
The disposable browser campaign remains clearly labeled for inspection.

## Git evidence

At start and the final inspected state:

- Branch: `main`.
- Local HEAD: `9d8b751be3fde16ef3ac3ccb4871bd951069bf00`.
- Cached origin/main: `5983853dbb6ae7d4852f4a3f8e070c3fe1e440f1`.
- Cached comparison: 249 ahead, 0 behind. This is not a fresh remote check.
- Start was clean; end has this work's uncommitted changes.
- `git diff --check` passed before the closeout documentation was added.

No GO-only remote synchronization or publishing action was taken.
