# UI presentation closeout

Scope: the remaining date/year, player wording and current-scene presentation gaps.
No Python source, OpenAPI contract or existing spellcasting projection was changed.

## Date truth

Active campaign header, character reveal and World panel read the existing
`campaign_time` fields. Formatting does not consult the browser clock or a fixed
era. No campaign date is asserted on the opening screen before campaign state
exists. Missing time produces no invented date. The library's real-world
last-played timestamps remain separate from campaign time.

## Current context

The existing World tab now prioritizes current location and description, the
matching scene's NPC list, accepted quests, actual combat actor/round and actual
player combat status. Details show only scene features/current-location doors.
When scene data is absent or belongs to another location, only canonical exact
location membership is used. Global NPC candidates do not override the matching
scene's visibility list. Discovered locations and encounters remain in Journal.
No narration parsing, RNG, quests, locations, NPCs or other game truth is created.

## Player wording and diagnostics

Controlled player copy no longer describes servers or implementation plumbing.
Ability failure does not render raw transport exceptions. Existing raw effect/error
diagnostics require both development mode and explicit `?diagnostics=1`; ordinary
player screens do not display them. Gameplay result messages and current character
resources remain available, and the spell panel is unchanged.

Campaign library identifiers are joined only to existing start-catalog names.
Unknown legacy IDs produce an explicit availability note, not an inferred place.
Species/class readouts and the campaign branding use Turkish display labels;
canonical values and existing setting/spell names remain unchanged. The active
location ribbon uses the existing Turkish environment labels.

## Verification evidence

Fresh evidence: `evidence/ui-presentation-closeout/`. Existing historical evidence
was not overwritten.

- Frontend: final 56 passed. The initial 54-pass/1-failure SSR provider-identity
  attempt is retained separately; its test harness was corrected.
- Frontend typecheck: passed.
- Frontend build: passed, with source-map and bundle-size warnings.
- Relevant API/regression: 71 passed; archive:
  `evidence/suite-runs/20261004T165412Z-cdcf960233cc4f90adc41af330b2b959/`.
- Python production guard: identical before/after fingerprints; zero changes.
- Browser: live eight-step creation, reveal/adventure, authoritative date,
  spell-list/slot comparison, all four context tabs, 390x844 layout and drawers
  passed. Date was 1 Mirtul 1501 DR, 09:00, equal to the live response.
- Live state was noncombat/Normal/active with empty quests, people and objects.
  Nonempty quests, current combat actor and stable unconscious context have
  renderer tests; they were not falsely claimed as live browser scenarios.
- Deletion: cancel caused no DELETE; a specifically injected 503 retained the
  disposable card and displayed a friendly failure; real DELETE then removed
  only that disposable campaign. All 23 initial campaign IDs were preserved.
- Initial browser localization/identifier failure is retained in
  `browser-initial.json`. After correction, the same tester's focused recheck
  passed with live catalog names, Turkish card labels and no exposed raw IDs.
  No user campaign was opened or changed in either pass.
- No live cast, resource consumption, active combat or alternate-year browser
  fixture was used. Spell owner tests and changed-year renderer tests supply
  those separate contract/presentation checks.

No commit, push, merge, reset, rebase or publishing was performed. No #13 work.