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

## Rules-source conflict — resolved for new Acolyte/Artisan characters

The uploaded PHB PDF page 177 / printed page 178 was read as text and visually
checked against the original page (temporary reference rendering, not app/UI
screenshots). Acolyte option A is Calligrapher's Supplies, prayer book, Holy
Symbol, ten parchments, robe and **8 GP**; Artisan option A is the chosen
Artisan's Tools, two pouches, Traveler's Clothes and **32 GP**. Both have a
**50 GP** option B.

The earlier translated catalog listed **15 Altın** and **20 Altın** with different
items. New Acolyte and Artisan option A packages now follow the uploaded PHB:
Calligrapher's Supplies, prayer book, Holy Symbol, 10 parchment, robe, **8 GP**;
chosen Artisan's Tools, two pouches, Traveler's Clothes, **32 GP**. Option B
supplies **50 GP** for any background. A selected Artisan tool is chosen from
the 17 PHB artisan tool options and surfaced in character creation.

Only the new-character creation owner installs these confirmed coin amounts
as integer CP-value wallet balances, removing that *new* background coin label
from gameplay inventory. Historical saved inventories, coin strings and missing
wallets remain unchanged on load/resume; no load-time currency migration exists.
Unverified legacy option A money on other backgrounds is **not** monetized.
Character creation's selected-package record continues to show the chosen
source package, including its original coin label.

## Earlier bounded slice and verification (historical evidence)

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

The following results belonged to the **previous bounded slice**, initially
tested as uncommitted changes relative to
`062c5804ef734a3ab8655847905c0e4e1d0c62ec`. It was later committed at
`17fd1a0a23fc13844bb162e1926af5312b51df01`. These are **not** current
verification results for the new native producers below. Earlier gate source
was stable during its execution (`source_changed_during_run=false`).

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

Earlier transient evidence (may not survive workspace restart):
`/tmp/package2-final-focused.log`, `/tmp/package2-final-integration.log`,
gate `/tmp/package2-gate/20261005T082803Z-575c53a13f284c0797fbcaf87a9780d0/run.json`,
and regression `/tmp/package2-gate/20261005T082803Z-8478d0f8f0474d588fb076f5908a5782/run.json`
(with their `output.log` files). These paths are not permanent storage;
this document retains the decision, commands, counts and runtime fingerprints.

SHA-256 fingerprints of the **earlier** tested runtime/test changes. They
cannot certify later edits to these files:

| File | SHA-256 |
|---|---|
| `ai-dnd/equipment_economy.py` | `c895c9d7d4f5214abc7483c448920a6892766e3ac551d60cb7306f3c15bd9613` |
| `ai-dnd/game.py` | `293e841b359731831c2deec8e07b0d94fb93ebb314904647df56a0589015c251` |
| `ai-dnd/api/serializers.py` | `253c902a2c839d8acb0409aae6fe0a5d6acf8c79513820214ec1ee8611ec9d57` |
| `ai-dnd/api/tests/test_equipment_economy.py` | `245bc09eca6d3dbac061216f94c59f89465629c13abed71591691962f15cba05` |
| `ai-dnd/api/tests/test_equipment_economy_http.py` | `99da548088b111c723b2871e94ab70a96e3e06166106d09400e0d36363ba2461` |

### Earlier acceptance gaps (historical audit, superseded below)

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

The earlier bounded slice was **PARTIAL/BLOCKED** at the time of that audit;
that decision does not adjudicate the native producer changes below.

## Native bounded V1 producer contract

All gameplay commands use the existing turn/snapshot/receipt/autosave path.
No parallel inventory/economy persistence or client-provided stock exists.
The stock policy here is deliberately campaign-local and Python-owned, **not
a claimed PHB rule about starting merchant cash or treasure**:

- `/item market` is an explicit player request at a registered location. It
  prefers a local existing shopkeeper/shop with no economics. Otherwise the
  existing validated shop/NPC creation owner creates one anonymous equipment
  counter. Maximum one native counter per location. It never overwrites an
  existing NPC inventory, equipped weapon, existing explicit stock or wallet.
  Provisioning appends **one Dagger**, offered at its PHB 2024 catalog cost
  **2 GP**, and **one Club**, explicitly marked by NPC policy as releasable to
  this player; this is a server-defined transfer decision, not a social roll.
  Working capital is **1000 CP (=10 GP)** only if the shopkeeper has no wallet.
  These quantities/capital are V1 campaign policy, not invented PHB prices or
  backstory. A shop with explicit preexisting economics retains its own values.
- `/item request <item-id> <npc-id>` asks the Interaction & Quest owner to
  record an item-specific, operation-specific, recipient-specific NPC consent
  only when the *actual NPC-owned item* has an exact trusted release policy or
  an existing exact grant. It consumes the grant and moves the same item ID
  in a single candidate-state commit; equipped source-hand references are
  cleared. The natural `request` interaction routes through that same owner;
  Qwen may propose the intent, but its speech, social success or missing/default
  equipment cannot authorize possession or transfer. Other NPCs without a
  policy/grant reject. Replay is handled by the existing campaign receipt.
- `/item work <npc-id>` creates one player-origin, NPC-bound talk objective in
  the *existing* Interaction & Quest thread ledger for the Python-seeded
  merchant. It reserves **100 CP (=1 GP)** from that NPC's actual wallet.
  `/item talk <npc-id> <player-words>` records only the actual player words and
  supplies a dialogue action to the existing objective observer. No model can
  mark the objective completed. `/item reward <thread-id>` succeeds only after
  that thread is canonically succeeded, debits the source NPC and claims it
  once. Merchant buybacks cannot spend the reserved reward funds.
  This is a minimal cooperation reward, not a general production quest catalog
  or new lore. Existing production quest definitions remain unchanged.
- `/item loot <defeated-npc-id> <item-id>` requires the actor's authoritative
  defeated/dead state, actual local NPC inventory and a unique instance ID.
  `/item loot <open-container-id> <item-id>` requires an explicitly accessible
  local unlocked/open container with actual contents. Existing location ground
  loot remains `/item take <item-id>`. Defeat descriptions, default equipment,
  unopened containers and Qwen narration cannot supply items. Held references
  clear consistently; armor/shields fail closed until their AC/time owner exists.
- Item prices come solely from the existing PHB 2024 weapon catalog. Sale
  requires the shop's buyback policy and a funded wallet. Unknown/valuable or
  magic prices are not invented. Wallets conserve integer CP value; there is
  no general mint-on-narration path.

**Explicit V1 exclusions:** crafting, encumbrance, broad trade-goods and
valuable catalogs, magic-item economics, advanced stacks/consumption,
armor/shield AC/time changes, two-handed transitions, physical coin weights,
unrestricted corpse loot and arbitrary quest treasure definitions. Never
upgrade a model proposal to a price, stock, purse, consent or reward.

## Current validation and decision

**Feature decision: READY FOR REVIEW for the bounded native gameplay described
above. Repository/release decision: NOT GO.** No known functional P0/P1 blocker
remains in the exercised bounded paths. This does not certify excluded mechanics,
the entire PHB background catalog, arbitrary generated shops or live Qwen intent
quality.

Final observed branch is `main`, HEAD
**`17fd1a0a23fc13844bb162e1926af5312b51df01`**. The new work is **uncommitted
working-tree source** on that HEAD, not code contained in the commit. Accordingly,
these are final **HEAD + exact source-fingerprint** results, not a certificate
for a newly committed final HEAD. No commit/push/merge/force-push was performed.
Documentation/memory summaries may be updated after verification; no tested
runtime/frontend source was changed after the results below.

| Final-source verification | Result |
|---|---|
| Focused equipment/native/character creation | **76/76 PASS** |
| Bounded integration: those paths + persistence, idempotency, weapon attacks, journal | **297/297 PASS** |
| Unmodified Final Gate selected Python regression | **161/161 PASS**, zero skipped |
| Frontend library check/typecheck | **PASS** |
| Frontend tests | **57/57 PASS** |
| Frontend production build | **PASS** |
| Real proxied HTTP | **PASS**: native transfer, merchant sell/buy/sell, exact replay for each, changed-body `409`, funded once-only reward, resume/receipt and wallet preservation |
| Final Gate verifier-source stability | **PASS**, `source_changed_during_run=false` |
| Final Gate repository decision | **NO-GO**, exit **1**, dirty working tree and unchanged infrastructure-only scope policy |

The native module contributes 16 executed tests: 11 unit/boundary cases, two
native HTTP flows and three inherited fixture-based compatibility contracts.
The main native transfer/market/work/reward HTTP flows create their possessions,
consent, wallets and reward through gameplay, **not fixture injection**.
Boundary tests explicitly supply an existing shop's historical possessions,
container contents/open state, an underfunded merchant wallet or a combat owner's
defeat state. They do not constitute a fresh combat-to-loot or arbitrary
container-content producer demonstration.

The existing journal owner now compares actual labels across legacy strings and
canonical instance records. Identity materialization cannot report a false item
loss; real canonical transfers still produce the original item-gained/lost
events. The journal schema, encounter authority and inventory owner are unchanged.

Live proof used the real public campaign-start API and only chat turn commands:
`market → list → request → sell → buy → sell → work → talk → reward → resume`.
Each transfer/sale/purchase replay returned the same receipt without another
movement or payment. Reusing its action ID for another body returned `409`.
Player balance was **650 CP** after trading, **750 CP** after the funded reward,
and remained **750 CP** after a rejected second claim and resume/replay. The
single temporary acceptance campaign was then removed through its normal API.
No existing user campaign was edited or deleted.

Gate `Live HTTP`, `Live Qwen` and GitHub Actions remain **NOT RUN by that gate**.
The separate live HTTP log is the acceptance proof above; no live Qwen or
GitHub Actions completion is claimed. Final frontend preview renders normally.
A temporary Vite optimized-dependency `504`/missing-dependency state was isolated
from healthy source routes and resolved by restarting the same managed frontend,
without changing app code or routing. The known root Replit dev-banner `502`
remains infrastructure preview noise, not an AI-DND request.

Reproduction:

```sh
cd ai-dnd
python -m unittest api.tests.test_equipment_native api.tests.test_equipment_economy api.tests.test_equipment_economy_http api.tests.test_character_creation_2024 -q
python -m unittest api.tests.test_equipment_native api.tests.test_equipment_economy api.tests.test_equipment_economy_http api.tests.test_persistence_idempotency api.tests.test_campaign_persistence api.tests.test_weapon_attack api.tests.test_character_creation_2024 api.tests.test_campaign_journal -q
# from workspace root:
python ai-dnd/scripts/final_gate.py --archive-root /tmp/package2-native-final-gate
```

Retained **new** development evidence:

- `/tmp/package2-native-targeted.log`
- `/tmp/package2-native-integration.log`
- `/tmp/package2-native-live-http.log`
- `/tmp/package2-native-source-identity.json`
- `/tmp/package2-native-final-gate/20261005T093136Z-d6ca27d604754c10aa53abdc7bc604db/run.json`
- `/tmp/package2-native-final-gate/20261005T093137Z-efa26cc5170b40e885147fb83cce8743/run.json`

Final runtime/test/frontend SHA-256 fingerprints:

```text
ef556af446a0178ab5113b6440cc708ec5c1c1065d7cc9a76be3980225dd2e5d  ai-dnd/api/campaign_journal.py
2dc586bf8cf5af2fa5475addcad34d53f17ba7ca7ee1cb4824f7a8fd4b416947  ai-dnd/api/character_creation.py
f740af6f278233006f6917ec60717e168cab024701693c50a728d2ec1d5aab37  ai-dnd/api/dnd_2024_rules.py
842d77077bc9542a21a44a6dfb2066e3f77589cf2d2fad5fcba0cfeb7d135503  ai-dnd/equipment_economy.py
2fcf0a1b2c1fe195cfb33ce1b575b0909529f7a4a279ddb48f82ac14bfd9dc5b  ai-dnd/equipment_native.py
3791004e61b353e2abc1a179455fce490edce956877e0029a8bd7d53ce531ae8  ai-dnd/interaction_adventure.py
c317a989a8538afbe568c6c413e88fd9913110157ee65505af825088af072cf2  ai-dnd/api/tests/test_equipment_native.py
51e955d6467598386a95f51d2215c434715ad608b52ad854c860c49192f84276  artifacts/ai-dnd-experience/src/components/character-creation-screen.tsx
7a602a387eb31ca73ce0d00b123cbe6adb830d6fa3f76016aa0a2c72c6ede548  artifacts/ai-dnd-experience/src/lib/character-catalog-defaults.ts
```

The infrastructure-only policy was not relaxed to manufacture a GO.
Committing an approved tree and obtaining an appropriate feature-level gate
authorization remain repository/release prerequisites, not failed economy
transactions. There is no automatic permission to push/merge or rewrite that
policy.
