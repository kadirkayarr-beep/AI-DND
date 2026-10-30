# C06/XP zero-HP consistency correction — 2026-10-29

## Narrow accepted fix
Independent review approved three positive-current conditions: XP's multi-level HP loop and both unpaid progression branches. Maximum HP always gains the existing amount; current HP gains it only when already positive. Current0 and canonical unstable/stable/dead state remain unchanged. Existing positive-current compatibility, cap4, receipts and reported maximum gain remain. No healing calls, action/combat gates or normalization of already-corrupt states were added.

`hit_points_gained` reports advancement maximum gain, not guaranteed restored current HP. This is a conservative consistency integration preserving existing death/healing ownership, not a claim that source rules grant revival on leveling.

## Reachability and tests
Real pending dynamic quest reward settlement reaches XP independently of an unconscious player action. Regression completes quest evidence while alive, then enters zero via actual damage/stabilization/death owners before real settlement. Normal combat-end guards protect zero-HP victory; do not misattribute the defect to that route.

Actual RED5 methods/19 assertions/0 errors. Original5 GREEN. Added postimplementation interaction verification covers15 cases: XP1→2/3→4 and unpaid Sorcerer1→2/2→3/Barbarian1→2 across unstable/stable/dead, canonical serialize→fresh restore→real healing or dead refusal. It preserves levels/max/receipts/death/status/timers/recovery/RNG. This added test is postimplementation evidence, not original RED.

Final regression module6 PASS; focused related277 PASS. Expanded415 retains7 FAIL+1 ERROR across six NPC conversation/profile methods. A separate genuine-history pre-fix reference, exact source overlay and reverse-only patch reproduced all eight event IDs and entire traceback/terminal signatures; only differing absolute candidate path prefixes were normalized. Old focused set excluding new regression passed271.

This proves those observed eight signatures pre-existed this correction. It is not full API baseline equivalence, original-a963 full-suite reproduction, or a clean expanded suite. No unrelated NPC fixes made.

## Evidence and limits
See docs/acceptance/evidence/c06-zero-hp-progression-20261029 for PASS and FAIL records, raw logs, exact comparison, reverse patch and source provenance. Independent reviewer inspected final code, new interaction test and evidence; no independent rerun. Historical oldHEAD96e0 + dirty recovered candidate remains actual tested identity; authentic a963 now exists separately for eventual integration. No commits, push, merge, deployment or personal-record migration.
