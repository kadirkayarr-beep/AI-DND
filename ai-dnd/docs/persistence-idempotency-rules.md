# Persistence / Idempotency Rules

## Audit before hardening

The existing authoritative owner is `CampaignStore`, backed by SQLite.
`save_campaign` writes the engine/RNG envelope, narrative history, combat history
and action receipt in one `BEGIN IMMEDIATE` transaction. FastAPI mutation handlers
are synchronous worker-thread handlers serialized by `ManagedSession.turn_lock`.
`SessionManager` caches one record per campaign in each manager.

Existing request identity is a deterministic SHA-256 of the validated request
fields, including structured combat actions and combat context, not prose alone.
Receipts are keyed by `(campaign_id, action_id)`; anonymous-session receipts live
only in their record. Existing durable fingerprints are reusable without change.

Existing coverage mapped before additions:

- Campaign API: replay/conflict, autosave rollback, quests/events, memory defaults.
- Campaign persistence/lore persistence: envelope restore, RNG and legacy schemas.
- Campaign Time/edges: lost response, event/travel progress, save failure, Normal rollback.
- Combat/economy/initiative/monster/death/spell suites and Combat Test Matrix:
  representative canonical state, replay, recovery, resource and rollback boundaries.
- Narrative director/model isolation/rebalance/safety: context/prose authority,
  ceiling, fallback and no retry.
- Death tests: transactional cascade, repeated deletion and session revocation.

Gaps selected for focused additions: independently loaded stale writers;
deterministic concurrent duplicate/different requests; actual late SQL failure
after state/history writes; structured request conflict and fresh-manager receipt
replay; scoped IDs; additive schema migration with preserved existing receipts.

Confirmed production gap before fixes: no persisted revision check prevents one
independently loaded campaign from silently overwriting a newer accepted state.
Final contract and verification are recorded below after bounded hardening.

## Final authoritative owners

- `api/persistence/campaign_store.py`: `_initialize`, `_transaction`,
  `create_campaign`, `save_campaign`, `get_campaign`, `get_turn_action`,
  `assert_current`, `_reserve_legacy_events`, `delete_campaign`.
- `api/persistence/campaign_validation.py`: `serialize_campaign_payload`,
  `validate_campaign_payload`, `restore_campaign_session`; unchanged canonical
  engine/RNG envelope and defaults.
- `api/persistence/campaign_serializer.py`: `restore_stored_campaign` binds the
  restored runtime to the loaded campaign/revision.
- `api/session_manager.py`: runtime registry, one active record per campaign per
  manager, resume/save/autosave, receipt scope and deletion revocation.
- `api/main.py`: validated request hashes, receipt-before-context replay, request
  lock, snapshot/restore, canonical mutation handlers and safe HTTP failures.
- `api/core_resolution.py`: action scope and distinct child `resolution_id`
  (`action_id:resolution_type:counter`); embedded results persist without regeneration.
- Existing `game.py`, `campaign_time.py`, `scheduled_events.py`, initiative,
  action-economy, monster, Death, spell, inventory and quest owners decide mechanics.
  Persistence does not decide new mechanics.

## State / identity classification

Legend: **Tx** is the existing atomic campaign save transaction (payload, RNG,
history, combat history, receipt and trimming). **Restore** means the API's
pre-action engine/world/messages/RNG plus external journal, metadata, lore and
selected-memory snapshots. **Resume** means fresh-manager envelope restoration.
Campaign scope is the SQLite campaign ID; session scope is an opaque runtime ID.

| State / identity | Runtime authority | Persistent representation | Save boundary | Replay | Restart | Isolation | Failed-save rollback | Notes |
|---|---|---|---|---|---|---|---|---|
| Campaign identity | Manager/store | `campaigns` PK + world campaign ID | Create/Tx | Campaign-scoped lookup | Same stable ID | Campaign | No ID rewrite | Save is UPDATE, never resurrection INSERT |
| Session identity | Manager registry | Not persisted | None | Response rebases outer session ID | New opaque ID | Record | Existing registry unchanged | Anonymous sessions are not durable campaigns |
| Player state | `GameSession.character` | Envelope `engine_save.player` | Tx | No second mutation | Resume | Campaign/record | Restore | Existing save validation |
| World state | `GameSession.world_state` | `engine_save.world_state` | Tx | No reapply | Resume | Campaign/record | Restore | No frontend-owned reconciliation |
| Campaign Time | Existing clock owner | World clock | Tx | No second advance | Resume | Campaign | Restore | Gameplay time only |
| Scheduled events | `scheduled_events` | World scheduled occurrences/decisions | Tx | No duplicate occurrence/effect/knowledge | Resume | Campaign | Restore | Existing #01/#02 order/interruption |
| Travel/long actions | Existing game/time scheduler | Existing pending progress/destination/decision fields | Tx | No extra progress/rolls | Resume | Campaign | Restore | No new travel system |
| Combat | Lifecycle/game | World combat identity/status/participants | Tx | Replay before stale context | Resume | Campaign | Restore | Closed identity preserved |
| Initiative | Existing scheduler | Combat order/cursor/results | Tx | No reroll/advance | Resume | Campaign | Restore | Retained unconscious slots unchanged |
| Action Economy | Existing ledger | World economy budgets/turn markers | Tx | No reconsume/reset | Resume | Campaign | Restore | Actor-bound refresh unchanged |
| HP/Death | Existing damage/Death owners | Player/world Death data | Tx | No extra damage/save/recovery | Resume | Campaign | Restore | NPC Policy A and historical unconscious compatibility |
| Normal checkpoint | #08 checkpoint owner/hooks | Existing checkpoint plus campaign-owned snapshot | Tx | Fatal action receipt retained | Resume | Campaign | Restore transaction, not gameplay checkpoint | Normal rollback intentionally does not rewind RNG/receipts |
| Monsters/resources | Monster/HP/resource owners | World NPC profiles/state/resource ledgers | Tx | No repeated use/recharge/damage | Resume | Campaign | Restore | Combat ID cannot refresh limited uses |
| Spell resources | `spell_scope` | World spell ledger/slots/turn marker | Tx | No second cast/consumption | Resume | Campaign | Restore | Actual bounded #09 modes only |
| Inventory | Existing inventory owners | World inventory/equipment/items/containers | Tx | Turn receipt prevents repeated mutation | Resume | Campaign | Restore | No invented reward route |
| Quest state | Python quest owner | World quests + journal quest ledger | Tx | Existing status/transition idempotency | Resume | Campaign | Restore | Production quest definitions remain owner-gated |
| Journal/events | Journal + canonical event owners | Envelope journal; history/combat-history tables | Tx | IDs/receipts deduplicate | Resume | Campaign | Restore | Narrative history is not verified sentence-by-sentence canon |
| Canonical/selected memory | Existing memory/knowledge owners | World knowledge + selected narrative memory | Tx | No prose-created facts | Resume | Campaign | Restore | Existing authority constraints |
| Lore/metadata | Lore authority/metadata owner | Envelope lore/world metadata + SQL metadata | Tx | No new binding on replay | Resume | Campaign | Restore | No mode/location reinterpretation |
| RNG | `GameSession.rng` | Envelope `rng_state` | Tx | Zero extra draws | Exact continuation | Campaign/record | Restore RNG | Bare engine JSON is not the campaign RNG envelope |
| Action receipts | Store/record | `campaign_turn_actions`; anonymous record cache | Tx | Same hash returns durable result | SQL lookup | Campaign or anonymous record | Failed action has none | SQL PK `(campaign_id, action_id)` |
| `action_id` | Validated API request/action scope | Receipt PK/result IDs | Tx | Same ID/different canonical request conflicts | Retained | Scoped, not globally unique across campaigns | Failed ID can retry | Omitted ID generates a new action; caller must retain retry ID |
| `resolution_id` | Shared resolution scope | Nested authoritative result/checkpoints/receipt | Tx | Original ID, no reroll | Retained in result | Parent action/type/counter | Restore | Not collapsed into root action ID |
| Revision/load token | Store + serializer | SQL `revision`; server-only runtime token | Tx increments revision | Replay precedes stale check | Bind loaded revision | Campaign | Token advances only after COMMIT | Not a gameplay RNG or second save format |
| Deletion/revocation | Store + manager | Transactional FK cascade; missing campaign row | Delete transaction | Repeated/unknown delete false | No campaign to resume | Related records only | No false deletion success | No mode automatically deletes |

## Request and receipt contract

Turn hashes retain the existing deterministic sorted, compact UTF-8 JSON
representation of validated message, target, structured combat action and supplied
combat identity/round/index. Species-action hashes retain their existing command
namespace and validated action fields. Ordered action steps remain ordered.
Action IDs are excluded from request identity itself.

Ambient commands use the same receipt table, with deterministic namespace,
event-instance ID and action. They preserve the locked `ALREADY_APPLIED`
projection and original transition/canonical-event IDs rather than executing again.
Their durable response is referenced within the existing receipt JSON.
Cross-command reuse of an ID conflicts.

- Same scoped ID + same canonical request: return stored authoritative resolution;
  no models, mechanics, RNG, time or resources repeat.
- Same ID + different request: deterministic conflict; original receipt remains.
  Turn/species routes use HTTP 409; the existing ambient route uses its locked
  `REJECTED / action_id_conflict` result.
- Root action IDs and child resolution IDs retain their distinct ownership.
- SQL receipts are never trimmed with narrative/combat history.

## Atomicity, concurrency and stale copies

`BEGIN IMMEDIATE` covers state, RNG, metadata, dependent history, receipt and
combat-history trimming. COMMIT precedes success publication. A receipt-insertion
trigger failure after earlier UPDATE/INSERTs proves the entire transaction rolls
back. The API restores its pre-action snapshots; successful retry commits once.

Synchronous FastAPI worker threads can overlap. The existing record lock spans
receipt lookup, resolution and commit. Deterministic barrier tests make two
requests arrive concurrently: duplicate spell requests execute/draw once; distinct
wait actions both commit their accumulated time with no lost update.

Independent managers have independent locks/copies. An additive SQL revision and
server-only `(campaign_id, revision)` load token reject stale/cross-campaign saves.
The check occurs under SQLite's write transaction, so simultaneous stale writers
cannot both replace the same revision. API new-action checks reject already-stale
copies before execution. A race after that precheck still loses safely at commit
and is restored. Explicit resume refreshes a stale cache from accepted durable truth.
Read reconstruction uses one SQL snapshot for payload and dependent history.

Deletion still cascades transactionally. A stale copy cannot INSERT/recreate the
deleted ID. Cached sessions are revoked locally, or rejected on a later existence
check in another manager; unrelated campaigns remain intact.

## Compatibility and legacy provenance

SQLite schema 3 → 4 adds only `revision INTEGER NOT NULL DEFAULT 0`; engine/campaign
formats, IDs, modes and payload bytes are unchanged. Existing 1/2 migrations still
work. Concurrent schema openers recheck the version after acquiring the write lock.
Load/save stamps are server-owned and not gameplay checkpoint state.

Existing SHA-256 receipts require no new fingerprint field or guessed request.
Malformed receipts fail safely rather than executing again.
Startup reserves known structured pre-hardening ambient identities from retained
canonical journals in the existing receipt table. Only actual event/action/ID
provenance is used; historical narration/response state is not invented.
Reservations survive later bounded journal trimming. Conflicting/unverifiable
legacy identities reserve an unmatchable marker and cannot authorize a new action.
Existing SQL receipts are never overwritten. Corrupt campaigns do not block
unrelated campaigns opening.

Actions whose historic identity was never stored, or had already been discarded
before hardening, cannot be retroactively reconstructed or certified.

## Rollback distinction and model boundary

Failed persistence restores the failed transaction's pre-action HP/world,
position, time/events, action resources, spell/monster resources, RNG, journal,
memory, lore and metadata as applicable. No successful receipt exists for it.

Normal-mode death instead performs its already locked gameplay checkpoint
rollback, intentionally retaining its existing RNG/receipt semantics. It is not
changed into failed-persistence rollback. Permadeath/Ironman and no-auto-deletion
semantics are unchanged.

Qwen/frontends cannot declare commit, choose replay, reconcile saves, roll gameplay
RNG or turn prose into mechanics. Existing <=2 calls, fallback and no narration
retry remain protected by the combined regression.

## Verification and evidence

Focused selection: `api.tests.test_persistence_idempotency`,
`api.tests.test_combat_test_matrix`, `api.tests.test_campaign_persistence`.
Combined selection is the exact #10 selection plus focused #11, campaign
persistence, lore persistence and journal suites. Exact commands/IDs/counts/source
identity are in the final runner records linked from the task report/evidence.
All 600 previous executed test IDs were checked against the new executed IDs.

Restart verification is fresh-manager/store reconstruction of temporary SQLite
campaigns, not a claimed real OS-process crash or power-loss test. Failed runs
remain retained. No frontend, gameplay-rule, Git-history or publishing changes.

Final focused: **31 pass / 0 fail / 0 errors / 0 skips** —
`evidence/suite-runs/20261004T134310Z-1a37be2d55934349ac793a6394605563/run.json`.

Final combined: **643 pass / 0 fail / 0 errors / 0 skips** —
`evidence/suite-runs/20261004T134325Z-353a94756065413c81b5a95647300ccb/run.json`.
Each directory retains `output.log` alongside the machine-readable record.

The genuine pre-fix stale-write failure is retained at
`evidence/suite-runs/20261004T132523Z-b66bef1e60824ce38840c9b96092a4f8/run.json`.
Intermediate migration-fixture and unresolved-scene fixture failures remain
retained separately, not presented as gameplay failures or overwritten.

Starting status/hashes: `evidence/persistence-idempotency/start.json`.
Exact production comparison and prior-600 ID check:
`evidence/persistence-idempotency/production-guard.json`.
Only the five declared API persistence/session owner files changed; 126 guarded
Python files, including gameplay owners, are unchanged.