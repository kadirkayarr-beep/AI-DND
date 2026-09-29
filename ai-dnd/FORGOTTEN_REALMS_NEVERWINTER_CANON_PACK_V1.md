# Forgotten Realms — Neverwinter Canon Pack V1

**Disposition:** PASS after manual review  
**Date:** 2026-09-29  
**Engine SHA-256 (`ai-dnd/game.py`):** `463b0d9b1a8079b37744f6535748358af50bee6dfca7180de68560fcf89a18cb`  
**Related history:** [Initial failed run and retest log](NEVERWINTER_CANON_SMOKE_REPORT_2026-09-29.md)

## Scope

This report records the Phase 1 / Phase 2 Neverwinter validation. The final test used the existing reviewed Forgotten Realms lore pack and added no canon facts. It validated one explicitly requested campaign-local shop and shopkeeper, stable IDs/tags and persistence, no narration-only NPCs, no economy or quest mechanics, and NPC name recall only after explicit player disclosure to that same stable NPC ID.

## Test setup and result

- Smoke command: `python -m api.tests.live_neverwinter_canon_smoke`
- Model: `qwen3:8b`
- Database: a temporary disposable SQLite database created by the smoke script. The temporary directory was removed after exit; the shared campaign database was not used.
- Campaign UUID: `fb2a3608-424d-4fce-a92d-8fe8b0e50c13`
- Binding remained `fr:world:forgotten_realms`, `fr:epoch:1501_dr`, `fr:region:the_north`, and `fr:city:neverwinter`.
- Exactly 20 meaningful turns completed: 19 before API restart, followed by resume and one final turn.
- Model calls: 15 total, at most 2 per turn. Maximum retrieved fact count: 9.
- Every turn had current-turn narrative-safety diagnostics. The smoke script reported `MECHANICAL_PASS_NEEDS_MANUAL_NARRATION_REVIEW`; manual review of all 20 turns passed.

## Turn-by-turn review

| Turn | Player intent | Manual review |
|---:|---|---|
| 1 | Neverwinter’s condition in 1501 DR | Answered that Neverwinter is rebuilding, using loaded facts. |
| 2 | Dagult Neverember’s role | Directly identified him as the current Lord of Neverwinter without unrelated lore. |
| 3 | Neverwinter’s Lords’ Alliance membership and purpose | Answer included both verified membership and the Alliance’s stated safety-and-prosperity purpose. Both matching fact IDs were retrieved. |
| 4 | Whether The North and the Sword Coast are the same region | Correctly stated that The North is distinct from the Sword Coast; retrieved the reviewed distinction fact. |
| 5 | High Road route and safety | Returned the verified northern trade-route role, renewed safety status, and continuation as the Trade Way. |
| 6 | Route and distance from Neverwinter to Phandalin | Marked the unsupported connection/distance as unverified; did not invent a route. |
| 7 | Invented King Vharion | Rejected the unsupported ruler and residence claim as unverified. |
| 8 | Invented city Nythravel and deity Velmoryx | Rejected both unsupported entity claims as unverified. |
| 9 | Investigation of Neverwinter’s rebuilding | Investigation succeeded (d20 20 against DC 15). The response explicitly added no object or clue. |
| 10 | Explicit request not to create a local shop | Confirmed no shop or shopkeeper was added; state stayed unchanged. |
| 11 | Asked whether a shop or merchant was already present | Correctly reported that no campaign-registered shop or shopkeeper was present yet; did not create one. |
| 12 | Explicitly requested one local shop and its keeper | Created exactly one shop and one shopkeeper in Neverwinter. |
| 13 | Requested another merchant | Rejected the duplicate; shop and keeper counts stayed at one each. |
| 14 | Asked about stock, prices, and buying a sword | Refused unsupported economy mechanics; inventory and currency stayed unchanged. |
| 15 | Traveled to the tavern | Travel succeeded. The existing Python travel mechanic created its predefined tavern door; see the state note below. No lore entity or NPC was created. |
| 16 | Claimed that unregistered Elara remembered a name | Rejected the memory claim because Elara had no registered stable NPC ID. No NPC or memory was created. |
| 17 | Returned to Neverwinter | Returned to the bound Neverwinter location without adding setting lore. |
| 18 | Explicitly disclosed the name “Arven” to the shopkeeper | The shopkeeper acknowledged the disclosure; audit recorded it against `npc_001`. |
| 19 | Asked for an active quest with an empty production catalog | No quest or quest offer was created; the response did not invent quest content. |
| 20 | Asked the shopkeeper to recall the disclosed name after API restart | The same `npc_001` recalled “Arven”; the disclosure remained bound to that ID after resume. |

## Campaign state and persistence

The explicit shop request created:

- Shop: `shop_001`, “Küçük Taş Mağazası”, at `fr:city:neverwinter`, tags `campaign_local` and `shop`, with `shopkeeper_id: npc_001`.
- Shopkeeper: `npc_001`, “Geddis Kırktaş”, role `Shopkeeper`, at `fr:city:neverwinter`, with tags `campaign_local`, `shopkeeper`, and `shop:shop_001`, and `shop_id: shop_001`.

There was exactly one registered shop and one NPC from turn 12 onward. The reciprocal IDs, tags, location, and explicit-name memory survived API restart and campaign resume.

Across the full run:

- `features`, `quests`, and `quest_offers` remained empty.
- Campaign canon overrides, lore discoveries, player-known facts, and NPC-known facts remained empty.
- The only `procedural_entity_refs` were the intended campaign-local `shop_001` and `npc_001`; no setting-level procedural entity was added.
- Player inventory stayed `Macera çantası`, `Kılıç`; currency, spells, and XP did not change.
- The setting, epoch, region, and current canonical location remained bound to Forgotten Realms / 1501 DR / The North / Neverwinter.
- The tavern travel turn added the pre-defined Python-owned `Taverna Kapısı` entry in `world_state.doors`. It is a mechanical travel fixture, not a lore entity or feature, and did not enter the campaign’s lore procedural references.
- Combat was skipped because there was no canonical hostile participant.

## Lore retrieval and safety

- The Alliance question retrieved both `fr:fact:neverwinter_member_of_lords_alliance` and `fr:fact:lords_alliance_purpose`.
- The regional-comparison question retrieved `fr:fact:the_north_distinct_from_sword_coast`.
- The High Road question retrieved its route role, safety status, and continuation facts.
- Unsupported route/distance, ruler, city, deity, and unregistered-NPC memory claims were rejected or answered with Python-owned safe responses rather than accepted as canon.
- The exact loaded-fact response for Dagult’s role was focused on his current lordship.
- No new source fact, spell, XP, economy data, or additional region was added.

## Verification

Passed:

- `python -m unittest api.tests.test_lore_authority` — 14 tests
- `python -m unittest api.tests.test_lore_engine_integration` — 6 tests
- `python -m unittest test_narrative_safety_calibration` — 20 tests
- Python compilation for the changed engine, retrieval, test, and smoke files
- `git diff --check`
- Full disposable 20-turn smoke, followed by manual review of every turn, audit action, selected fact IDs, state transition, and post-restart name recall

**Decision:** The Neverwinter Canon Pack V1 smoke passed manual review. This report was created only after the final disposable run passed; the earlier failed run remains documented separately in the linked historical report.