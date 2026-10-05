# Package #2 — Equipment, Loot & Economy V1

## Contract and audit — 2026-10-05

Starting HEAD: `062c5804ef734a3ab8655847905c0e4e1d0c62ec` (`main`).
Package #1 is closed; its interpretation, canonical plans, conditions, journal,
model budget and persistence behavior remain locked.

### Existing owners and gaps

| Concern | Existing authority / finding |
|---|---|
| Player possessions | `game.py` world `inventory`; legacy name strings. Character creation installs verified selected equipment here. |
| Ground possessions | `ground_items_by_location`, with existing legacy `ground_items` migration. |
| NPC possessions | NPC `inventory`, when explicitly present. Combat equipment/defaults are not ownership evidence. |
| Equipment / attacks | Existing `equipment` main/off-hand mapping and `weapon_attack.py`; weapon catalog resolves profiles. Dict item instances already partially supported by combat, but save validation previously allowed only strings. |
| Armor | Character creation calculates AC from selected equipment; full armor don/doff needs Campaign Time and armor owners, not instantaneous inventory changes. |
| Shops | Existing shops and shopkeeper IDs; generated shop proposals explicitly exclude economics. No authoritative stock/price/cash producer exists. |
| Rewards | Python quest journal/catalog; production catalog deliberately empty. Adventure seeds have `reward_pattern=none`. No model-authored reward may become treasure. |
| Persistence | Engine snapshots plus SessionManager/CampaignStore atomic state/history/receipt commit; existing failure restoration and revision coordination. |
| API / UI | Existing message turn and receipt path; primary experience InventoryPanel consumes `GameState.inventory: string[]`. Preserve that presentation contract; canonical records must project to labels, not leak dicts into React children. |
| Currency / transactions | No general native balance or transaction owner. Extend the same world state and turn path, not a second inventory, database or endpoint. |

### Uploaded mechanical sources

- Uploaded PHB: `attached_assets/D&D_5e_-_Players_Handbook_2024_1790967864536.pdf`,
  PDF page 212 / printed page 213: CP=1, SP=10, EP=50, GP=100,
  PP=1000 copper-value units. Equipment resale is half cost; trade goods and
  valuables retain full value. Availability/listed price remains a DM decision.
- PHB PDF page 218 / printed page 219: armor don/doff durations, armor training,
  shield training, one suit/one shield. Armor changes are not implemented as
  free instantaneous equip commands in this slice.
- Uploaded DMG: `attached_assets/D&D_5e_-_Dungeon_Master_Guide_2024_1790967864536.pdf`,
  PDF pages 216–217 / printed pages 213–214: treasure categories, coin values
  referred to PHB, trade goods and gemstones. OCR misreads GP as CP in several
  tables; do not ingest those table values without visual verification.

Existing translated starting-package labels are not a verified price catalog.
Unknown labels retain identity but have no invented price/mechanics. A bounded
verified catalog may supply prices; merchant availability, consent and reward
definitions must come from trusted Python producers, never Qwen/client payloads.

### Canonical model and permitted operations

Extend entries in the existing possession lists to explicit records with stable
`item_id` and `name` (plus optional catalog `weapon_id`). The containing list is
the sole ownership authority: player inventory, an NPC inventory or a registered
location's ground inventory. No separate mirror inventory or owner ledger.
Legacy strings remain readable and migrate only at an explicit inventory action.
Duplicate names are distinct instances; duplicate IDs anywhere are invalid.
Movement preserves the record and ID. Unknown/ambiguous requests fail closed.

Wallets are integer copper-value accounting balances in existing world state,
not physical coin stacks or an encumbrance simulation. Missing wallets mean no
known spendable funds, not starting wealth. No strings, narration or social roll
may mint money. Trusted existing producers must explicitly install balances.

Use the existing `/turn` message path, action IDs, campaign lock, snapshots,
autosave and receipt replay. Commands are deterministic and require no Qwen call:
`/item list`, `/item drop <id>`, `/item take <id>`, `/item equip <id> <hand>`,
`/item unequip <hand>`, `/item give <id> <npc-id>`,
`/item receive <id> <npc-id>`, `/item buy <id> <shop-id>`,
`/item sell <id> <shop-id>`, `/item reward <quest-id>`.
All mutation commands are unavailable during active combat, unconsciousness,
terminal death or an unfinished combat reaction; existing owners retain priority.

### Transfers, loot and rewards

- Both parties must exist at the same authoritative location and be available.
  An NPC-owned item requires explicit Python-owned, item-bound, recipient-bound
  consent. High persuasion/deception results and narrated consent are not consent.
- Player gifting is an explicit player decision; NPC acceptance still requires
  a trusted acceptance policy. Consent is consumed atomically with transfer.
- Removing a held item clears its existing hand references. Armor removal fails
  closed until the armor owner can update AC/time consistently.
- Loot is only a present canonical ground instance. Dead NPC inventories do not
  automatically become free loot; no treasure is generated from descriptions,
  monster defaults, containers or defeated actors.
- Rewards require an existing completed Python quest and a server-owned reward
  definition with explicit source items/funds. Reward redemption is once-only,
  persisted, and atomic with all source debits. No automatic quest fabrication.
- Merchant foundations use the existing shopkeeper's own canonical inventory,
  explicit item availability/prices, buyback policy and funded wallets. Missing
  stock, prices, location, funds or consent reject. No shop creation grants stock.
- Equipment/valuable resale classifications and prices require trusted rules
  provenance. Unknown/magic item pricing, effects, crafting, progression, spells,
  full faction/Living World simulation and general exploration remain excluded.

### Atomicity and verification

An operation validates the complete candidate state before commit. Any error
restores world/character in place; persistence errors use the existing outer
rollback, including RNG/history/receipts. Successful retries replay the existing
receipt before stale-context validation; conflicts cannot repeat a transaction.
No cross-session global mutable economic state. No model retries or clock writes.

Focused verification must cover duplicate prevention, canonical identity across
movement, equipment cleanup, denied/consented two-party transfers, location and
insufficient funds, merchant/reward rollback, legacy saves, malformed saves,
replay/conflict/restart and isolation. Then run existing bounded regression and
gate without changing gate policy or committing to obtain a GO. Evidence must
name base HEAD and hash changed source because the work remains uncommitted.

## Genuine rules-source blocker

The uploaded PHB PDF page 177 / printed page 178 was read as text and visually
checked against the original page (temporary reference rendering, not app/UI
screenshots). Acolyte option A is Calligrapher's Supplies, prayer book, Holy
Symbol, ten parchments, robe and **8 GP**; Artisan option A is the chosen
Artisan's Tools, two pouches, Traveler's Clothes and **32 GP**. Both have a
**50 GP** option B.

The active `BACKGROUND_DEFINITIONS` used by `configure_character()` instead gives
Acolyte **15 Altın** and a different item list, and Artisan **20 Altın** and a
different item list. Option B agrees on 50 GP. This is an existing rules-source
conflict, not an OCR-only uncertainty. Do not mint balances by parsing these
disputed starting labels, silently replace historical possessions, or present the
current background packages as verified 2024 equipment.

Further package expansion stops at this conflict. The existing locked character
creation owners and historical saves have not been rewritten. Resolving it needs
an explicit new-character versus historical-save compatibility policy and a
source-verified starting equipment catalog. No automatic wealth conversion is
implemented.

Status: **PARTIAL / BLOCKED FOR FULL PACKAGE ACCEPTANCE**. Native producers
missing at audit are explicit acceptance gaps, not implemented merely because
fixture tests can supply their data.

## Implemented bounded slice and final verification

The new `equipment_economy.py` is an operation owner over the existing possession
containers, not a second inventory. It is connected to the existing engine turn
dispatch and API serializer; no new endpoint, database, client state or economy
engine was introduced.

- Legacy name-string inventories remain readable; explicit `/item` actions
  materialize unique instance IDs, including distinct instances of duplicate
  names. Instances move between existing lists without new IDs or cloning.
- Drop/take, conservative one-handed weapon equip/unequip, consent-bound
  give/receive, catalog-priced merchant buy/sell, funded reward redemption and
  persisted reward duplicate prevention are implemented.
- Transfers resolve on a candidate world copy; rejection cannot expose partial
  source debits, hand cleanup or consumed consent. Player/NPC/location and
  funds/policy validations are Python-owned. Active combat/death owners cannot
  be bypassed. No Campaign Time write or RNG draw is performed by this owner.
- Legacy sword phrasing remains usable after instance migration. Existing
  context, scene evidence and quest acquisition comparisons accept labels
  from canonical records. Save validation rejects duplicate instance IDs and
  malformed economic balances.
- The public API continues returning inventory **strings**, now labeled with
  IDs and canonical held markers where available. The existing primary
  experience inventory and chat consume those strings without new frontend
  assets or generated types. `/item list` narrates authoritative wallet,
  ground items and explicitly available merchant/consent commands; it does not
  reveal all private NPC inventories.
- Qwen neither interprets nor narrates `/item` commands: these deterministic
  commands use **zero inference calls**. Ordinary Package #1/model paths and
  their ceiling/no-retry tests remain unchanged. Generated NPC/shop updates
  cannot install these inventories, consents, prices, wallets or rewards.

### Evidence on the final runtime source

Base HEAD remained **`062c5804ef734a3ab8655847905c0e4e1d0c62ec`**, branch
**`main`**. This is an **uncommitted working-tree implementation**, not a claim
that the new code is contained in that commit. Gate source was stable during
execution (`source_changed_during_run=false`).

| Verification | Result |
|---|---|
| New equipment unit + HTTP contracts | **27/27 PASS** |
| Bounded equipment, HTTP, persistence/idempotency, campaign persistence, weapon and character-creation integration | **267/267 PASS** |
| Existing unchanged gate Python selection, including locked Package #1 | **161/161 PASS**, zero failures/errors/skips |
| Shared frontend libraries + primary frontend typechecks | **PASS** |
| Existing primary frontend tests | **57/57 PASS** |
| Primary frontend build | **PASS** |
| Existing Final Gate decision | **NO-GO**, exit **1**: intentional dirty tree and infrastructure-only scope policy |
| Restarted existing FastAPI service | Startup complete; proxied `/api/game/health` returned `status=ok` |

Counts overlap; they are separate runs, not additive coverage. HTTP contracts
use the real ASGI handler and temporary SQLite persistence, with trusted
fixtures and an offline model adapter. They prove canonical transfer, identical
receipt replay, payload conflict, persisted resume, failure restoration including
equipment/consent/RNG, and session isolation. They are **not** remote/live-Qwen
or native social-consent/treasure-production acceptance.

Commands:

```text
cd ai-dnd
python -m unittest api.tests.test_equipment_economy api.tests.test_equipment_economy_http -q
python -m unittest api.tests.test_equipment_economy api.tests.test_equipment_economy_http api.tests.test_persistence_idempotency api.tests.test_campaign_persistence api.tests.test_weapon_attack api.tests.test_character_creation_2024 -q
# From repository root:
python ai-dnd/scripts/final_gate.py --archive-root /tmp/package2-gate
```

Retained transient evidence:
`/tmp/package2-final-focused.log`, `/tmp/package2-final-integration.log`,
gate `/tmp/package2-gate/20261005T082803Z-575c53a13f284c0797fbcaf87a9780d0/run.json`,
and regression `/tmp/package2-gate/20261005T082803Z-8478d0f8f0474d588fb076f5908a5782/run.json`
(with their `output.log` files). These paths are not permanent storage;
this document retains the decision, commands, counts and runtime fingerprints.

SHA-256 fingerprints of the tested runtime/test changes (the documentation
summary was appended afterward; no runtime source changed):

| File | SHA-256 |
|---|---|
| `ai-dnd/equipment_economy.py` | `c895c9d7d4f5214abc7483c448920a6892766e3ac551d60cb7306f3c15bd9613` |
| `ai-dnd/game.py` | `293e841b359731831c2deec8e07b0d94fb93ebb314904647df56a0589015c251` |
| `ai-dnd/api/serializers.py` | `253c902a2c839d8acb0409aae6fe0a5d6acf8c79513820214ec1ee8611ec9d57` |
| `ai-dnd/api/tests/test_equipment_economy.py` | `245bc09eca6d3dbac061216f94c59f89465629c13abed71591691962f15cba05` |
| `ai-dnd/api/tests/test_equipment_economy_http.py` | `99da548088b111c723b2871e94ab70a96e3e06166106d09400e0d36363ba2461` |

### Exact remaining acceptance gaps

1. **Rules-source blocker:** repair/verify the starting equipment catalog and
   define historical-save compatibility before initializing spendable starting
   wealth. No starting currency labels were monetized.
2. **#75 native completion:** the transaction/consent consumer exists and is
   tested, but the existing Package #1 social path still reports
   `transfer_possible=false`. Native Python producers of actual NPC possessions
   and explicit consent are not installed. Persuasion success alone never grants
   an item. This is not full native #75 acceptance.
3. **Merchant/reward/loot production:** transaction foundations consume trusted
   data; no new production stock, item offers, funded NPC wallets, reward
   definitions, corpse-to-ground loot or treasure tables were authored.
   Existing production quests remain empty. Fixture success does not remove
   these gaps.
4. **Lifecycle breadth:** armor/shields and AC/time synchronization, two-handed
   equipment transitions, item stacks/consumption/destruction, encumbrance,
   fractional copper resale and full trade-good/valuable price catalog are
   unsupported and fail closed rather than inventing rules.
5. **Presentation breadth:** no dedicated wallet/shop/equipment/reward UI or
   native purchase/social journey was added; existing inventory/chat expose the
   bounded command results. Interactive browser acceptance is **NOT RUN**.
6. **Remote evidence:** live development transaction/Qwen inference, GitHub
   Actions and production deployment acceptance are **NOT RUN**. The health
   request above is not a live gameplay/model acceptance run.

**Final decision: PARTIAL / BLOCKED — bounded transaction slice is verified;
Package #2 is not complete or closed.** No gate policy, locked Package #1
document, dependencies, generated types or frontend source changed. No commit,
push, merge, rebase, history rewrite or backup branch was performed by this pass.
