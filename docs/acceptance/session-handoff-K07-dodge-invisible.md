# K07 Dodge / Invisible Initiative checkpoint — 2026-10-28

## Scope and status
- `K07.dodge_benefits_loss`: independently accepted, bounded static review. Existing attack/save behavior characterized; source oracle added. No attack/save behavior change.
- `K07.initiative_invisible`: independently accepted for the bounded Initiative effect. Static review found no blockers; B02 evidence binding validated.
- Full K07/C06 and broad conditions/initiative families remain OPEN.

## Sources
K07 release_v2, checksum-file SHA256 `2996a18aa245c98ac1076e09c4b2ed09ec57ff25883e173ff1edaa3ed7ff55b4`, matched current SOURCE_ACCEPTANCE_INDEX. Fourteen received registered members verified, including glossary, chapter text, scope and correction logs. This is a partial text transfer of a previously bounded source-accepted package; no fresh visual audit or complete155member transfer claimed.
Dodge PDF365, Incapacitated368, Invisible369, Restrained372, Speed373. Use PDF ordinals, not guessed printed labels.

## Work
Dodge: positive capacity, Incapacitated, Speed0, Speed1, Grappled, Restrained, and visibility interaction. Exhausted remaining movement alone does not cancel Dodge. Old monster test incorrectly expected one die for Restrained; source-correct two dice/lower remains after losing Dodge's advantage. Test now uses [1,20] and asserts failure.
Invisible: existing Initiative owner now adds `invisible_2024`; normalized condition handling preserved. Player/NPC, enabled dictionary/tuple/set, feature-source combination, Surprise and Incapacitated cancellation, no reroll after condition ends are covered. The attack visibility exception is not applied to Initiative.

## Verification
- Dodge behavior characterization passed before changes under QG-1; missing oracle binding assertion failed before adding adapter.
- Invisible behavioral RED: four methods, nine assertion failures, zero errors (`invisible-red-clean`). Initial attempt had exhausted mocked dice and is not the clean RED.
- Invisible oracle binding independently failed before adapter addition.
- Latest combined related run: `k07-dodge-invisible-regression`, 515 executions, 499 unique qualified methods (16 repeated imported methods), all OK, exit0. Do not sum earlier365/112/190 overlapping runs.
- Guard verified inside child before imports, pin `d0803047bca67beec76a27d7825cef6f655bafee81d290d5c940d530ec0a51c5`.
- Full release/UI/browser/live model/auth NOT RUN. Existing terminal subprocess test remains BLOCKED; no permission weakened.

## Review follow-ups
Dodge nonblocking: add explicit no-Dodge and non-Dexterity negative cases later. Activation/expiry and broader action-family oracle coverage remain separate; open-family wording clarified.

## Repository and rollback
Local import HEAD `1616c7f9507f0c62ba2a673dbf42f98769bb7023` is not upstream Git history. Feature changes uncommitted. No push/merge/deploy. Preserve previous death checkpoint. Rollback must remove only this bounded delta, never reset/clean the shared candidate or overwrite other work.

Independent static review accepted both bounded leaves. Evidence record, exact515execution/499method ledger, final raw log and scoped source digests retained locally in `evidence/k07-dodge-invisible-20261028/`. Invisible malformed-input negative tests and clearer remaining-effect wording are nonblocking follow-ups. No independent rerun claimed.
