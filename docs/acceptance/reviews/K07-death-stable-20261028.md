# Independent review: K07 death/stable and THP-at-zero

Decision: ACCEPTED for the bounded core and THP-at-zero mechanics, plus the Human THP compatibility fixes. Not acceptance of all K07, C06, the full release, real model, real authentication, or deployment.

The independent reviewer inspected actual owner paths, bounded PHB source excerpts, the 14 core + 1 THP cases, save validation and rollback snapshots. No blocking product defect remained. Review was static; product tests were executed by the implementing workspace, not independently rerun by the reviewer.

Findings addressed through observed RED/GREEN: Human THP expiry on completed Long Rest; absent-field legacy load compatibility; ordinary damage not introducing an absent zero field; real THP setup/absorption in the massive-damage fixture. Short/interrupted rest preservation and positive Human save/load are covered.

The reviewer requested a focused Human rest rollback/retry/replay proof. It was added through the existing HTTP/rest owner with a real synthetic SQL receipt-insert failure: removal/recovery was observed before failure, snapshot restoration preserved THP, same-action retry removed it once, replay did not run the rest again, and reopening preserved the committed state. The final combined guarded run contains 190 passing methods.

Clarification: healing or becoming Stable resets death-save counters; death itself is not described as resetting them. The separate THP replacement-choice leaf remains OPEN.

Limits: one nested-subprocess terminal compatibility test remains BLOCKED; full release/API discovery, live model, browser/UI and real Clerk were not run. Runtime data uses the authentic verified addendum; no personal campaign or live service was used. Dice and storage faults are deterministic mocks/fixtures, not real-service acceptance.
