# Combat lifecycle lock

## Read-only audit findings

The existing Python scheduler already supplied canonical participants, initiative,
Core Resolution attacks, death-save scheduling, completed-round Campaign Time,
session-bound execution, and atomic campaign/action-receipt persistence.
The Experience already rendered server-owned participant/turn state and history.
Those mechanisms were retained.

The audit found these lifecycle gaps:

- Closing an encounter discarded its ID; public state/results did not expose it.
- Missing active IDs could be silently invented by a routine state read.
- HTTP actions had no optional combat/round/turn optimistic precondition.
- Some invalid actions could become ordinary results/history entries.
- Direct mechanical entry points did not consistently check the current actor and
  combat membership. Model-classified combat was insufficiently tied to a real
  player decision.
- Normal travel had early paths that could bypass combat context.
- Real NPC relocation could invalidate a participant projection instead of ending
  the participant's engagement through a deterministic lifecycle transition.

## Authoritative lifecycle

The existing active/ended/death_resolution representation remains. Python starts
combat through the existing start function, owns its stable ID and turn sequence,
orchestrates existing resolution, validates transitions, and closes the encounter.
An unconscious player retains the existing automatic death-save/stable boundary.
Neither hostility alone, threats, narration, nor client context starts combat.

Closed state keeps its combat ID while transient participants/order/actions are
cleared. Historical results remain in the existing bounded combat history.
Closing is idempotent and adds no time. A later real encounter receives a new ID.
Missing/duplicate participant identities and inconsistent active state are rejected,
not repaired with invented outcomes. Authoritative relocation makes an NPC inactive
for this engagement; if no opponent remains, the encounter ends without spatial
simulation.

## Requests, results and retries

Optional request fields combat_id, combat_round, combat_turn_index form an all-or-none
optimistic precondition. New Experience combat requests send them. They are not
commands to create or mutate combat. Legacy callers without these fields retain
canonical actor/target validation but cannot express a stale-turn precondition.

The successful action receipt is checked **before** current-context validation.
A lost-response retry must replay even after a round advances, the encounter closes,
or a campaign resumes. Context is included in the existing request fingerprint only
when provided, preserving old receipt hashes. Changed payloads keep the existing
409 conflict. The browser preserves original context with a pending action ID rather
than substituting refreshed context on retry; definite request rejection clears the
pending request and refreshes canonical state.

Invalid actor/target/weapon/travel/model-trigger requests cannot consume dice,
resources, rounds, time, history or journal consequences. Rejection/clarification
does not serialize as a canonical combat result. A valid miss is a real, replayable
result, not a rejected request.

The existing result contract now includes canonical combat identity and current
status/round/turn boundary, alongside existing Core Resolution rolls, damage,
HP before/after, conditions and next actor where resolved.

Combat outcomes use the existing deterministic Python combat renderer before the
API's atomic save. Uncommitted combat outcomes are not sent to a narration model;
an intent-model call may still interpret a request. No model retry was added.
Maximum two calls per turn remains enforced. Failed persistence returns an error
and restores the existing snapshot/RNG/journal/history boundary.

## Scope preserved

No changes to initiative ordering, attack/damage formulae, action-economy rules,
monster tactics, spell mechanics, Death System rules, persistence architecture
or UI architecture. The current actor/membership guards are lifecycle validation,
not a new action-economy model.

Completed rounds still use the existing six-second Campaign Time path. Combat
exit does not resume interrupted event tasks, travel or rest. Campaign Time's
pending decisions and actual progress remain intact.

## Verification

Focused lifecycle tests cover the required boundaries, alongside existing Campaign
Time, event handoff, species, death, persistence, receipt and model-call regressions.
The affected live model path is checked separately on isolated in-memory state,
without changing a saved user campaign. Full live smoke and the future comprehensive
combat test matrix are outside this work.