# Player condition persistence repair — 2026-10-28

ACCEPTED bounded storage/restore integrity after independent static review. This closes the persistence gap identified while reviewing Charmed runtime consumption, not condition eligibility, expiry, source creation or full effect lifecycles.

Nine existing optional fields are preserved as detached copies: conditions, charmed_by, frightened_by, grappled_by, grapple_escape_dc, prone, frightened_until_player_turn, speed_penalty_ft, speed_penalty_turns_remaining. Loading restores or clears every field, so old runtime source metadata cannot leak into another campaign. Shapes validated before mutation. No invented source IDs or new hand/effect state; existing world equipment remains owner of grapple hand markers. Raw player fields are distinct from derived death/status projections.

Unsupported prior-session concentration is cleared; incoming unsupported serialized concentration is rejected. This does not implement concentration persistence.

Evidence: initial4method/11failure RED; expanded condition-bundle-complete-red7methods/21assertionfailures/zeroerrors;44relatedGREEN; finalcondition-persistence-wide806executions/790uniquemethodsPASS exit0. Static review only. Full release/UI/model/auth not claimed. B02record, raw log, unique-method ledger and scoped source manifest are in evidence/k07-condition-persistence-20261028.

## Rollback boundary
Old saves remain loadable in new code without a save-version rewrite. New condition-bearing saves MUST NOT be silently loaded under the pre-fix loader: it ignores these fields. Preserve pre-change snapshots and restore those if reverting the code. This is one-way compatibility, not downgrade safety. No personal saves or live campaigns were migrated.

No push/merge/deploy; changes remain isolated and uncommitted. The delivered16:43checkpoint predates this repair.
