# Living World V2.1 — Ambient Event Outcome Boundary

## Purpose and authority

This is a narrow API-to-`GameSession` boundary for one persistent ambient-event outcome. `GameSession` validates and applies the transition; the campaign journal records the engine-confirmed result; the existing campaign store persists both. Narration and model output are not inputs to this operation.

The event catalog remains declarative. It does not execute state changes.

## Event and action identities

- Each newly selected event occurrence receives a UUIDv4 `instance_id`, separate from the catalog's `event_id`. The instance ID is stored in the scene and ambient-event history, and appears in the public scene projection.
- Legacy saved events without an instance ID are migrated deterministically with UUIDv5 from campaign seed, location, event definition, occurrence count, and turn. Their identity remains stable across reloads.
- Each request supplies a UUIDv4 `action_id`. The journal stores it with the event instance and action.
- A canonical result is recorded at most once per event instance. Replaying the same action returns `ALREADY_APPLIED`; another action ID cannot apply the same event again. Reusing the original action ID for a different action returns `REJECTED`.

## Result contract

The endpoint returns structured status and identifiers, not narration:

- `APPLIED`: the supported transition completed and was persisted.
- `REJECTED`: the event is missing, is not an interactive BLUE event, is not in the current scene, has no matching referent, has expired, or the action is invalid.
- `NO_EFFECT`: the supported `observe` action made no state change, or the promotion helper could not produce a canonical NPC.
- `ALREADY_APPLIED`: the event already has a canonical result or its referent has already been promoted.

Successful results include the event instance ID, action ID, transition ID, and canonical journal event ID. Rejected and no-effect results do not create canonical journal entries.

## Validation and supported outcome

The session resolves an event only when its instance ID matches the ambient event in the session's current location, that event is BLUE, and its referenced scene referent is still presented and within its existing turn expiry. The action must be `interact` or `observe`.

The sole persistent result is promotion of the event's temporary scene referent to a canonical local NPC, using the existing `_promote_scene_referent` engine helper. This is the only ambient outcome enabled here. GREEN remains atmospheric. BLUE remains temporary unless a player explicitly submits `interact`; `observe` is non-mutating.

This boundary does not add generic items, gold, quest progress, combat, relationship scores, or new memory writes. Existing systems remain authoritative for their own operations.

## Idempotency, session isolation, and persistence

The request is scoped to a managed session, and lookup is restricted to that session's current scene. A campaign-backed session is required for `interact`; an event ID from another session or campaign cannot select or mutate that session's event.

For a successful interaction, the API snapshots in-memory session state and journal, applies the engine transition, derives the canonical journal entry from the resulting state, then calls the existing `save_campaign_locked` path. The campaign store writes the campaign payload transactionally. If application or persistence raises, the in-memory state and journal are restored and the API does not return success.

The canonical journal entry stores the event instance, action identity, `APPLIED` status, transition ID, and related NPC. It does not store model-generated narration.

## Qwen boundary

The endpoint is deterministic and makes no model call. Its input schema rejects extra fields such as player-supplied narration or mutation claims. The existing maximum model-call budget is unchanged.

## Failure behavior

Validation failures return `REJECTED` without an event-result journal entry. Observation returns `NO_EFFECT` without mutation or persistence. A persistence failure rolls back in-memory state and journal and returns a generic `event_persistence_error`; internal storage details are not sent to the caller.

## Future ORANGE/RED extension point

Future persistent event outcomes must call an existing authoritative engine capability, validate its preconditions in `GameSession`, produce a structured result, and reuse the campaign journal and persistence transaction. No execution logic belongs in the event catalog. If no safe existing capability supports an outcome, it remains unavailable rather than being simulated by narration.