# Selected earned Sorcerer 4→5 HTTP/UI and Magic Missile slot3 — ACCEPTED

Scope: the existing selected CON+2 character path now earns numeric5, applies two prepared-spell choices through the existing browser/HTTP owner, uses Magic Missile slot3 and survives save/restart/resume. Whole C06/C19/Sorcerer, Sorcerous Restoration, general feats/ASI, spell replacement, full spell effects/catalogue, creation4/5, Clerk/model and deployment remain OPEN. Public creation remains1–3. No push/merge/deploy/auth/security change.

## Implementation and tests
Existing XP/receipt/rollback/class-state/spell/persistence owners remain authoritative. Cap5 threshold6500/PB3; old cap4 overflow saves remain readable unchanged, with catch-up only on the next genuine server award. New format6 is an explicit numeric policy discriminator; default4 and historical v5 rules are retained. Exact runtime format presence/value participates in outer rollback. Prior raw5/applied3→selected4 remains valid with attained-level retroactive HP; no re-awarded baseHP or ASI healing.

Level5 adds exactly two ordinary prepared choices and slot3 capacity2, preserving spent low slots, Hit Dice and previous selections. Fog Cloud/Silent Image are honestly selection-only (missing resolver), not implemented effects. Magic Missile's single-target slot3 uses five darts and one selected debit; defaultslot1/slot2 unchanged. Public magic availability is only action-slot eligibility; target legality stays server-owned.

Evidence under `evidence/c06-level5-http-ui-20261029/` binds final sources, raw test logs, captures and review status. **Backend248PASS** (`c06-five-related-final-20261029-0957`,15.687s). **UI29 focused PASS; full160PASS/1pre-existingSKIP**, declarations/typecheck PASS. These are separate overlapping scopes, not additive. Independent backend/UI code reviews approved. Review identified an actual outer rollback format defect, proved with assertion RED and repaired with real HTTP precommit-failure evidence. Earlier implementation/test failures remain explicitly described in the backend handoff; no whole default suite claim.

## Actual managed Chrome / real HTTP proof
Parent operated a synthetic principal against the finite loopback fixture. Real create3→accepted selected4→real XP award produced raw5/applied4, XP6500. Parent chose Fog Cloud and Silent Image, applied5 and saw slots4/3/2. Using the existing target selector and explicit slot3 control, parent cast Magic Missile against canonical `npc_001`. Actual trace: five darts **[5,5,3,2,5]**, damage20, slot3 remaining1; no low-slot debit. The NPC had4HP, so20 is rolled/resolved damage, not20HP removed. Child diagnostics explicitly show model_calls=0. Apply, cast and save returned200.

Parent observed level5, XP6500, PB3, CON16, **33/37 HP**, five cantrips, nine prepared spells and slots4/3/1. Generation `69555e4e-3047-46d4-afc2-50b2aab958f0` (pid79) restarted as `a4a5fa54-8e22-4a49-9531-ae9d564bb2c5` (pid83); same campaign `694d835b-7b5e-4242-a97e-ec21ff370968` resumed200. Parent saw the same panel and retained20-damage narration.

Read-only SQLite captures prove exact unchanged payload SHA256 `6f38e790061bb6d013ca46db84a455d9f8b8bd5a9efdb376fdf54a963fb448af`, revision4, selected state, combat history and both durable receipts. Across generations: exactly **one level-up POST and one turn POST**, no repeated grant/debit. Full submitted request JSON was not logged: typed request gate, receipt request_hash, resolved result and GUI observations support the path, but are not represented as raw request capture.

Corrected immutable runtime02 ZIP SHA256 `63ef7319d858ee5af497511542ca083d053b63a1e5c40d77ffa58e8038b7855f`; all230manifested members match, including11overlapping reviewed source hashes. This archive verification was measured after restart against launch identity/review manifest, not separately measured before restart. Attempt01 failed before readiness because its synthetic start lacked canonical provenance; preserved evidence and a narrow test-only corrected fixture establish02. No product bypass or unrecorded combat mutation was used.

Parent requested owned stop; native shell prompt returned and ready.json was absent at10:06UTC; tab7 closed. No screenshots were added here. Headless scripted browser matrix remains unclaimed (prior EPERM limitation); this is one actual managed-browser connected flow, not a full matrix or real Clerk acceptance.

## Source / recovery
Official2024BasicRules Magic Missile higher-slot rule, verified by source worker29Oct, gives one extra dart per slot above1; this is not PHB visual acceptance. Source locators/hashes and list/header-only spell provenance remain in bound proposal/backend handoff. No raw books copied.

Downgrade requires matching previous private checkpoint code/client plus pre-level5 saved-state snapshot. Old cap4/table admission must not be used to read new5 saves blindly. Source is frozen for private checkpoint; backup is separate from this scoped acceptance.
