# F03-P01 Field Path Manifest — 2026-10-10

**Gate: BLOCKED.** This is a narrow contract capture, not an F03 phase PASS.

## Isolated capture

Evidence: `.local/evidence/F03/20261010T155441Z/field-paths.json`

The capture used `POST /api/game/campaigns` through an in-process FastAPI ASGI transport and a fresh `TemporaryDirectory` SQLite store. A valid custom Wizard was created through the public campaign API. The store was temporary and removed after the probe. The response was HTTP 200 and included `campaign_id` and `state` in the same JSON object. The raw temporary ID is not recorded; its SHA-256 fingerprint binds the manifest rows to that response.

No real Qwen call, turn, owner campaign, live saves database, browser action, or deployment operation was used. No code, serializer, schema, save format, or `.gitignore` change was made.

## Manifest

The exact paths, JSON types, owners, presence states, and same-response evidence are recorded row-by-row in `field-paths.json`. Summary:

| Field | Path | Observation |
|---|---|---|
| HP | `$.state.character.current_hp` | Present, integer |
| XP | `$.state.character.xp` | Present, integer `0` |
| Inventory | `$.state.inventory` | Present, non-empty array |
| Time | `$.state.campaign_time` | Present, `null`; no concrete clock value |
| Location | `$.state.location` | Present string, but unresolved placeholder |
| Combat ID | `$.state.combat.combat_id` | Present, `null`; no active ID |
| Shop | `$.state.shops` | Present, empty array |
| Quest | `$.state.quests` | Present, empty array |
| NPC | `$.state.npcs` | Present, empty array |
| Narration | `$.history[*].narration` | **Absent**; response has `history=[]` |
| `campaign_id` | `$.campaign_id` | Present string; redacted and fingerprinted |
| AC | `$.state.character.armor_class` | Present, integer |
| Spell slots | `$.state.spellcasting.slots` | Present, non-empty object |
| Prepared spells | `$.state.spellcasting.prepared` | Present, empty array; not inferred from spellbook |

The isolated Wizard response closes the earlier XP/slot/prepared-path evidence gap: XP is explicitly `0`, slots contain level `1` with value `2`, and prepared is explicitly `[]`. These are response observations, not fabricated state. The empty prepared array is validly distinguished from a missing path.

P01 remains blocked because the required narration path is not present in this response. The response also does not establish non-null campaign time, a resolved location, or a non-null active combat ID. Empty shop/quest/NPC arrays prove those array paths and types only; they do not prove item shapes. The existing bounded encounter HTTP fixture has useful populated fields, but combining its different campaign with this isolated campaign would violate the same-`campaign_id` evidence rule.

## Read-only F03 AC001–AC006 gap review

| AC | Current evidence / gap |
|---|---|
| AC001 | **BLOCKED by P01.** Same-response fields are mapped, but narration is absent; time and combat ID are null; location is unresolved. No visible-text equality/browser proof was performed. |
| AC002 | **NOT TESTED.** No duplicate or conflicting replay POST was issued; no receipt/SQLite before-after comparison was made. |
| AC003 | **NOT TESTED.** No refresh, process restart, active-combat restore, or second-campaign isolation check was run. |
| AC004 | **NOT TESTED.** No injected save failure or rollback/second-event check was run. |
| AC005 | **NOT TESTED.** No delayed campaign-A response was delivered while campaign B was open. |
| AC006 | **NOT TESTED.** No API/Qwen outage was induced. This packet made zero Qwen calls and does not claim outage behavior. |

Bible v2.3.2 separately states that browser evidence is required for the F03 scenarios; this packet did not start those scenarios.

## Exact next packet: F03-P02 replay

Do not use owner campaigns. In a fresh isolated SQLite/API worker:

1. Create one campaign through supported API routes and establish a valid replayable turn/action request with a unique `action_id`; capture the pre-request canonical save, HP, time, action economy, and receipt state.
2. POST the payload once; capture the response and post-request state/receipt snapshot.
3. POST the identical payload with the same `action_id`; require the replay response to equal the first response, one receipt only, and no second roll, damage, reward, time advance, or action-economy consumption.
4. Reuse that `action_id` with a materially different payload; require a conflict/rejection and unchanged canonical state/receipt count.
5. Record sanitized requests/responses and isolated SQLite deltas. Do not call real Qwen unless the approved test path explicitly requires it; preserve the two-call ceiling and Python ownership.

P02 was not run as part of this packet.
