# C06 manual browser scenario — 2026-10-29

## Result
PASS for the observed Sorcerer3 visible create → save → new backend process → visible resume happy path. The user operated class/level/background/species/abilities/spell/Metamagic/subclass controls, created a synthetic character, saved it and resumed it after the agent restarted the owned fixture. Agent observed both reveal and resumed character panel.

Verified values: applied/raw level3, XP900, HP20/20, CON14, PB2, four cantrips, six prepared spells, slots4+2, Quickened/Twinned and Aberrant Sorcery ID. Exact selected request fields, HTTP200 create/save/resume for the same campaign, distinct session/generation IDs, equal stored selected state and equal complete-payload hashes are retained under docs/acceptance/evidence/c06-manual-browser-20261029.

## Runtime identity
Frozen runtime archive SHA256803668f0747920d0d18f7da7bc26bdabedf7e6184c6cfbddc663675b0aba8be3. It contains accepted Sorcerer3+starting-XP source, reviewed diagnostic launcher and compiled actual GameBrowser. It does not contain later Barbarian changes. Fixed synthetic identity, real HTTP and SQLite, no real Clerk or model. Cloud native terminal launched the finite owned supervisor beside the managed Chromium browser; no security settings changed. An earlier shell-tool network namespace was unreachable from the browser and was stopped, not exposed broadly.

Windows is separately BLOCKED: standalone loopback client returned WSAEACCES10013 with TokenIsAppContainer1. No bypass or system/network setting change attempted there. It is not a successful Windows server/browser test.

## Review and limits
Independent reviewer verified retained hashes, request events and before/after records; no material report overclaim. Visible UI actions are observer attestations, not independently reproducible from JSON alone. Initial PID40 is in observation report; new PID47 is separately in after snapshot. Payload equality uses recorded hashes; full payload deliberately not packaged. Cleanup records terminal prompt/readiness removal, not a captured exact supervisor exit code or independent proof of every descendant termination.

This is not whole-UI/full-C06 acceptance, production auth/model proof, combat/class-effect validation, mobile/keyboard/source-loss/class-switch regression or blanket user product acceptance. Pending features remain clearly displayed in UI. No push, merge or deployment.

## Cleanup
Owned stop requested after the successful scenario. Supervisor returned to terminal prompt; ready.json removed; immutable runtime bundle reverified unchanged. Synthetic DB retained privately for evidence, not included in source distribution.
