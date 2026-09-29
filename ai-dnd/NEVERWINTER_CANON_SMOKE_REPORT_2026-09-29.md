# Neverwinter / The North live canon smoke report

**Date:** 2026-09-29  
**Initial run result:** **FAIL** for the original 18-turn run documented below.
**Final disposition (2026-09-29):** **PASS after manual review** of a separate 20-turn disposable retest; see the addendum and `FORGOTTEN_REALMS_NEVERWINTER_CANON_PACK_V1.md`.

## Scope and setup

- Used the existing authenticated API and `qwen3:8b`; no other model or region was started.
- Completed 18 meaningful turns. Each turn used two model calls (36 total), within the two-call limit.
- Tested campaign: `349182d8-643c-4ced-a2db-337f90452fba`, bound to Forgotten Realms / The North / Neverwinter, 1501 DR.
- No source facts were added. `game.py` was not modified.
- The live API was restarted after the run. The campaign resumed at turn 18 in Neverwinter with its saved state intact.
- The disposable campaign was deleted by its exact UUID. Campaign count changed from 5 to 4; the deleted UUID now returns HTTP 404. No other campaign records were inspected or changed.

## Retrieval audit

Every turn retrieved the same 20 official facts below. There were no campaign overrides, player-known facts, NPC-known facts, or procedural local facts in the packet. The diagnostic reported zero withheld secrets on each reviewed turn.

| Fact ID | Retrieved value | Source reference |
|---|---|---|
| `fr:fact:dagult_neverember_current_lord` | Dagult Neverember is Neverwinter's current lord | PDF p.192 — Alliance Members / Neverwinter |
| `fr:fact:hotenow_eruption_nearly_destroyed_city` | Neverwinter was nearly destroyed by Mount Hotenow | PDF p.90 — The North / Neverwinter |
| `fr:fact:neverwinter_chasm_opened_to_underdark` | The chasm opened to the Underdark | PDF p.90 — The North / Neverwinter |
| `fr:fact:neverwinter_chasm_sealed` | The chasm is sealed | PDF p.90 — The North / Neverwinter |
| `fr:fact:neverwinter_gardens_warmed_by_river` | The gardens are warmed by the Neverwinter River | PDF p.90 — The North / Neverwinter |
| `fr:fact:neverwinter_known_as_city_of_skilled_hands` | Neverwinter is known as the City of Skilled Hands | PDF p.90 — The North / Neverwinter |
| `fr:fact:neverwinter_known_for_craft_goods` | Neverwinter is known for master crafts and fine goods | PDF p.90 — The North / Neverwinter |
| `fr:fact:neverwinter_member_of_lords_alliance` | Neverwinter is a member of the Lords' Alliance | PDF p.192 — Alliance Members / Neverwinter |
| `fr:fact:neverwinter_rebuilding` | Neverwinter is rebuilding | PDF p.90 — The North / Neverwinter |
| `fr:fact:high_road_continues_as_trade_way` | The High Road continues as the Trade Way | PDF p.89 — The North / High Road |
| `fr:fact:high_road_is_northern_trade_route` | The High Road is a major northern trade route | PDF p.89 — The North / High Road |
| `fr:fact:high_road_safety_restored` | The High Road's safety has been renewed | PDF p.89 — The North / High Road |
| `fr:fact:present_year_dr` | The current year is 1501 DR | PDF p.59 — Realms Timeline |
| `fr:fact:present_year_name` | The year is the Year of the Shining Mythral | PDF p.59 — Realms Timeline |
| `fr:fact:the_north_distinct_from_sword_coast` | The North is distinct from the Sword Coast | PDF p.63 — Regions of the Realms |
| `fr:fact:charter_company_contributed_to_road_safety` | The High Road Charter Company contributed to restored road safety | PDF p.89 — The North / High Road |
| `fr:fact:hotenow_wrath_spent` | Mount Hotenow's eruption status is spent | PDF p.90 — The North / Neverwinter |
| `fr:fact:lords_alliance_not_a_realm` | The Lords' Alliance is a settlement coalition, not a realm | PDF p.191 — Lords' Alliance |
| `fr:fact:lords_alliance_purpose` | Its purpose includes settlement safety and prosperity | PDF p.191 — Lords' Alliance / Goals and Activities |
| `fr:fact:neverwinter_river_flows_from_hotenow` | The Neverwinter River flows from Mount Hotenow | PDF p.90 — The North / Neverwinter |

Retrieval was consistent, but consistent retrieval did **not** prevent the model from adding unsupported claims.

## Turn-by-turn review

All 18 turns used two model calls. State shorthand below: “unchanged” means location stayed in Neverwinter, inventory remained `Macera çantası` and `Kılıç`, and NPCs, features, and quests remained empty.

| Turn | Intent | Review and state |
|---:|---|---|
| 1 | Describe current Neverwinter | Rebuilding was supported. “Recent calamities” and people “working tirelessly” added broad unsourced texture. State unchanged. |
| 2 | Give the year and Dagult's role | Year and current-lord facts were correct. The response also attributed rebuilding efforts to Dagult; that link was not in the retrieved facts. State unchanged. |
| 3 | Explain “City of Skilled Hands” | The title was supported; the claim that the city specialized in silver and metalworking was not. State unchanged. |
| 4 | Verify Dagult's current role | Correctly identified Dagult as Lord of Neverwinter. State unchanged. |
| 5 | Verify Alliance membership and whether it is a kingdom | Membership and “not a realm” were correct. The answer added a governance description beyond the retrieved purpose facts. State unchanged. |
| 6 | Ask about The North and the Sword Coast | Returned the generic Python fallback rather than answering. No unsupported geography was committed; state unchanged. |
| 7 | Ask about the High Road and its safety | The northern trade-route and restored-safety points matched the packet. The connection wording went beyond the structured route facts. State unchanged. |
| 8 | Ask for the route and distance to Phandalin | **Failure:** asserted a High Road route and an approximately 20-mile distance, neither present in the packet. It also credited the Lords' Alliance with the road work without retrieved support. State unchanged. |
| 9 | Ask whether King Vharion rules Neverwinter | **Failure:** invented “King Vharion” and claimed he lived north of Neverwinter. Neither entity nor location was in the packet. State unchanged. |
| 10 | Register the invented city Nythravel as official geography | Repeated-narration fallback; no geography or state mutation was added. The fallback did not clearly explain that the entity was unverified. |
| 11 | Verify the invented deity Velmoryx | Repeated-narration fallback; no deity or state mutation was added. Again, the response did not clearly state that the claim was unverified. |
| 12 | Investigate signs that Neverwinter is rebuilding | Investigation check succeeded: d20 16 + 4 = 20 against DC 15. The response said no new object or clue was added; narration fell back on an unverified-lore claim. State unchanged. |
| 13 | Find a local merchant | **Failure:** accepted narration introduced a market, merchant “Elara,” and a trading post. The engine state still had no NPC, feature, or procedural entity reference. This was narrative-only, untracked fiction. |
| 14 | Ask Elara for stock and prices | Repeated-narration fallback. No shop state or transaction data existed; state unchanged. |
| 15 | Attempt to buy a sword from Elara | Response said the sword was already in inventory. No price, currency, stock, or purchase transaction was applied. Elara still had no registered entity ID; state unchanged. |
| 16 | Travel to the tavern | Travel worked: location changed to `tavern`. No NPC or feature was created. The narration safety layer used an unverified-lore fallback. |
| 17 | Return to Neverwinter | Travel back worked. **Failure:** accepted narration added an unsupported High Road/River Neverwinter junction and references to the fall of the Silver Marches and rise of the Lords' Alliance. Location returned to `fr:city:neverwinter`; other state stayed unchanged. |
| 18 | Ask Elara to recall a name supposedly shared earlier | **Failure:** with no `target_id`, no NPC in state, and no prior name disclosure, accepted narration said “You have already introduced yourself to me.” It did not supply a name, but still asserted false continuity. No NPC memory or lore state was persisted. |

### State and feature checks

- The only location changes were Neverwinter → `tavern` → Neverwinter.
- No NPC, feature, quest, inventory, or currency changes occurred during the 18 turns.
- The campaign's persisted lore state had empty campaign overrides, discoveries, procedural entity references, and NPC/player fact knowledge.
- Quest offers remained empty; no quest was accepted or fabricated.
- Combat was not attempted: there was no canonical hostile NPC or combat participant to target.
- The merchant and shop flow was not actually available as engine state. Elara existed only in accepted narration.

## Conclusion for the original 18-turn run

The smoke **fails** because unsupported geography, history, crafts, and NPC continuity were presented as fact in accepted narration. Some claims were safely rejected or fell back, but the failures on turns 8, 9, 13, 17, and 18 are sufficient to block release.

`FORGOTTEN_REALMS_NEVERWINTER_CANON_PACK_V1` was **not** created, and no `game.py` SHA-256 was recorded because the required smoke did not pass. Do not promote this run as a validated canon pack.

## Cleanup and verification

- Restarted the API and resumed the disposable campaign at turn 18; the persisted location and empty NPC/quest state matched the live run.
- Deleted only campaign UUID `349182d8-643c-4ced-a2db-337f90452fba`. Database campaign count: 5 before, 4 after. The deleted campaign and its history were absent afterward.
- Restarted the API after removing temporary, campaign-specific diagnostics. Final health returned `ok` with model `qwen3:8b`; the deleted UUID returned HTTP 404; campaign count remained 4.
- Retained the region ID/display-name matching fix and its regression test. `game.py` remained unchanged.
- Full Python API test suite: 153 tests passed. Python compilation and `git diff --check` passed.

## Post-fix retest addendum — 2026-09-29

The 18-turn failure above remains the result of that historical run. It was not promoted. Later, separate 20-turn runs used only temporary disposable SQLite databases:

- One run failed because the Lords' Alliance purpose fact was retrieved but the Neverwinter membership fact was omitted. The retrieval registry was updated to recognize and prioritize membership, purpose, and regional-distinction intents. That failure did not create the V1 report.
- The next run passed its mechanical assertions, but manual review found an off-target Dagult role answer, an inaccurate explanation for a declined shop request, and a non-answer to the ordinary shop-presence question. These paths were changed to return focused answers grounded in loaded lore or current campaign state.
- The final 20-turn run below passed mechanical checks and manual narration review. It is the only run used for the V1 promotion decision.

### Final retest

- Campaign UUID: `fb2a3608-424d-4fce-a92d-8fe8b0e50c13`; disposable database only. The temporary directory was removed after the run; the shared campaign database was not used.
- Model: `qwen3:8b`. The run completed 20 meaningful turns: 19 before API restart, then the same campaign resumed with its state intact for the final memory-recall turn.
- Model calls: 15 total, no more than 2 on any turn. Maximum retrieved fact count: 9. Each turn had current-turn narrative-safety diagnostics.
- Lore binding remained Forgotten Realms / 1501 DR / The North / Neverwinter. The turn 3 packet contained both `fr:fact:neverwinter_member_of_lords_alliance` and `fr:fact:lords_alliance_purpose`; turn 4 retrieved `fr:fact:the_north_distinct_from_sword_coast`.
- Unsupported claims about a Phandalin route/distance, King Vharion, Nythravel, and Velmoryx were rejected as unverified. A claim of prior name disclosure to unregistered Elara was rejected because there was no stable NPC ID.
- The negative shop request caused no state change; the ordinary shop question correctly reported no registered shop before creation. The explicit request then created exactly one campaign-local shop (`shop_001`) and one shopkeeper (`npc_001`). Their reciprocal links and tags persisted across API restart.
- The second shop request did not create a duplicate. Stock, prices, and purchases were refused; player inventory and currency did not change. The empty production quest catalog produced no quest or quest offer.
- The player disclosed “Arven” explicitly to `npc_001`; after API restart that same stable NPC ID recalled the name. No name memory was created for Elara.
- No features, quests, quest offers, campaign canon overrides, lore discoveries, player-known facts, or NPC-known facts were added. The only campaign-local lore references were the intended `shop_001` and `npc_001`. The region binding remained The North; no other region was bound or loaded as the campaign region.
- Existing travel behavior added its predefined Python-owned `Taverna Kapısı` mechanical door when the player traveled to the tavern. It is stored in `world_state.doors`, is not a lore entity or feature, and is absent from `procedural_entity_refs`; it was not generated by narration or promoted as setting canon.
- Inventory remained `Macera çantası`, `Kılıç`; currency, spells, and XP did not change. Combat was skipped because no canonical hostile participant existed.
- Focused checks passed: lore-authority tests (14), lore-engine integration tests (6), narrative-safety calibration (20), Python compilation, and `git diff --check`.
- Final `ai-dnd/game.py` SHA-256: `463b0d9b1a8079b37744f6535748358af50bee6dfca7180de68560fcf89a18cb`.

The final run passed after reviewing all 20 responses, safety actions, retrieved fact IDs, campaign state, and post-restart memory. The V1 report was created only after that review: [`FORGOTTEN_REALMS_NEVERWINTER_CANON_PACK_V1.md`](FORGOTTEN_REALMS_NEVERWINTER_CANON_PACK_V1.md).