# Lore activation readiness

Nothing in this file was activated. Waterdeep and Baldur's Gate remain unloaded.

Branch: `phase8/emergent-storytelling-expansion`  
HEAD at preparation: `f63d952506064cd59e960f1e3efa6627d4e52053`

## Profiles

| | Neverwinter | Waterdeep | Baldur's Gate |
|---|---|---|---|
| Pack path | `ai-dnd/api/lore_authority/packs/neverwinter_the_north_v1.extraction.json` | `ai-dnd/api/lore_authority/packs/waterdeep_v1.extraction.json` | `ai-dnd/api/lore_authority/packs/baldurs_gate_v1.extraction.json` |
| Review file | `neverwinter_the_north_v1.review.json` | Missing | Missing |
| Schema version | 1 | 1 | 1 |
| Content hash (SHA-256 of the extraction file) | `51b1ce206d8be080de855aff79348a05578a99ca5c5b69c7fee912063d5c64c5` | `09fb42dc45217a029f7898e5884240b6a0978cd9123ca60065f64fe24f741aa5` | `d3aed82e3c2cfb03920e48e06d8454b43f58cca1c75e7a8bb646d0a8c37331fa` |
| Index coverage | `VERIFIED_PARTIAL` | `INCOMPLETE` | `INCOMPLETE` |
| Profile id | `neverwinter.v1` | `waterdeep.v1` | `baldurs_gate.v1` |
| `enabled` | true, and coverage is in the verified set | `false` | `false` |
| `DISABLED` set in `incidents/profiles.py` | no | yes | yes |
| `resolve()` | returns `neverwinter.v1` for Neverwinter | returns `None` for `waterdeep` and `fr:city:waterdeep` | returns `None` for `baldurs_gate` and `fr:city:baldurs_gate` |
| Start catalog | listed in `installed_region_catalog.json` | not listed | not listed |
| Activation status | playable for the reviewed Neverwinter scope | **DISABLED** | **DISABLED** |

An incomplete index row is not loaded. `registry_for_pack` returns the default registry, which answers unknown. The stub JSON is not production canon.

## What the engine permits today

For these two cities, the Reality Envelope is not built. `profiles.resolve` returns `None` before a profile can load. `profiles.load` would also return `None` while the id is in `DISABLED`, `enabled` is false, or pack coverage is not `VERIFIED`, `VERIFIED_PARTIAL`, or `APPROVED`. No incident proposal runs. No city fact is generated.

The dormant `waterdeep.v1` and `baldurs_gate.v1` entries still inherit the generic `_base` role and category tuples. Those tuples are not a city gazetteer and are not active.

## What a later reviewed profile would allow

This describes the current gate. It is not permission to enable the cities.

**Locked setting reality**, once a reviewed pack exists:

- Names collected from that pack as protected identities are rejected if a proposal uses them (`protected_identity`).
- Roles in the forbidden set are rejected, including deity, god, ruler, king, queen, lord, lady, high priest, and creature types (`forbidden_role`).
- Deity or pantheon language is rejected (`new_deity`).
- A subscene kind outside the profile allowlist, or a subscene label that invents a district, city, kingdom, temple, or castle, is rejected (`geography`).
- A proposal that states a published adventure is already concluded is rejected (`adventure_canon`).
- A proposal that makes Netheril or Shadovar the current 1501 government is rejected (`historical_override`).
- Killing a protected name is rejected (`protected_identity`).
- Entity references must already be ids in the envelope (`entity_ref`).
- Hidden facts must not appear in player-facing premise, seed, or surface facts (`hidden_information`).
- Tier 5 persistence is rejected. Coin amounts, XP, and magic-item language are rejected.

**Bounded local fiction**, only inside an enabled reviewed profile's allowlists:

- Minor people whose role is on that profile's role list.
- Incident categories drawn by the profile, such as a disturbance or a lost object, when the profile actually lists them.
- Subscenes whose kind is on the profile list and whose label does not invent geography.
- Rewards at or below the profile ceiling, granted later by Python, not by the proposal text.
- Relationships and one-time coin grants through the existing owners. Narration does not pay and does not create quests.

Silence, occupancy, and the two-call limit still apply. A quiet scene is a valid result.

**Forbidden generation**, including while the profile is disabled:

- A new official district, city, deity, faction leader, or political outcome.
- Treating an adventure hook as history.
- A secret revealed to the player without the knowledge owner.
- Using sourcebook silence as permission to add a major setting fact.
- Enabling the generic `_base` spec and calling it a Waterdeep or Baldur's Gate review.

Ordinary residents, a spilled crate, or a personal argument do not need to be named in a sourcebook. They also cannot appear in these cities until a reviewed profile loads, because the current code refuses the profile entirely.

## Missing evidence before any approval

- Waterdeep setting rows with page citations a human has checked.
- Baldur's Gate setting rows, split into locked facts versus adventure possibilities.
- A review file whose items are exactly the extracted entities, edges, and facts.
- A new SHA-256 taken after that extraction. The hashes above are for the empty stubs.
- A readable check of Heroes. The current file cannot be text-searched.
- A decision about *Dragon Heist* and *Descent into Avernus*. They are not in the supplied pair of books.

## Tests required after a future approval

Run these only after the owner approves a specific hash. Do not run them as a reason to enable the cities now.

1. `profiles.load("waterdeep.v1")` and `profiles.load("baldurs_gate.v1")` return a profile only for the approved pack hash.
2. `profiles.resolve` no longer returns `None` for that city's own location id, and still returns `None` if the hash or review file does not match.
3. A Neverwinter campaign does not enter the other city and does not load its profile.
4. The Reality Gate rejects a protected name, a new deity, an invented district, and a published-adventure conclusion.
5. Hidden facts stay out of the player packet.
6. Incidents still do not create accepted quests or pay from narration.
7. If a start location is added, `installed_region_catalog.json` and `pack_loader.load_production_pack` agree, including geography ancestors.
8. `test_contract_parity` still passes. Do not weaken a contract to make a city startable.

## Activation steps, not performed

Do these only after an explicit owner approval that names the extraction SHA-256.

1. Replace the empty `facts`, `entities`, and `edges` arrays with the approved rows. Leave `extraction_status` as `REVIEW_REQUIRED` until the review file marks each row.
2. Add `waterdeep_v1.review.json` or `baldurs_gate_v1.review.json` with one decision per extracted entity, edge, and fact. `pack_loader` rejects a verified pack if the sets differ.
3. Set that pack's `coverage_status` in `pack_index.json` to the approved value (`VERIFIED` or `VERIFIED_PARTIAL`) and point `review` at the new file.
4. Record the new SHA-256 in the approval note. A later edit must not keep this approval.
5. Remove that profile id from `DISABLED`, set `enabled` to true, and point `pack_id` at the indexed pack. Replace the generic `_base` allowlists with the reviewed city allowlists.
6. Change `profiles.resolve` so the city id resolves to that profile. Today it returns `None` on purpose.
7. Add a start location only if the registry can prove the city sits in a verified region. Skip this step if the city is not a campaign start.
8. Re-run the tests above. A green test is not a substitute for the owner's approval of the hash.

Until those steps are done by a later, explicit change, both cities stay disabled.
