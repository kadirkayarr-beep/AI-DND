# Preparatory C06 selected ASI / maximum-HP projection

PROPOSED for independent review. No product/test edits made. No level4 preview readiness, apply/create entitlement, stored feat grant, HTTP/UI change or full ASI acceptance.

## One behavior

Project the selected **Ability Score Improvement, Constitution +2** dependency for an existing Sorcerer with applied level3 and raw level3 or4. Compute the already-paid versus unpaid base-level HP and the separate retroactive maximum-HP delta using an existing C03 feat delta. This is a preparation calculator inside the existing progression owner, not another feat resolver or a new mutation/receipt authority. Detached target-level4 eligibility is explicitly hypothetical and must never be interpreted as an applied level.

Proposed internal interface (not currently implemented): `character_progression._project_selected_asi_hp(character, target_level, choice) -> dict`. Exact supported contract is Sorcerer applied3, raw3/4, target4, selected ASI and `increase: {'constitution': 2}`. Other choices return an explicit unsupported preparatory status; no automatic choice, source widening or suggestion that PHB prohibits other eligible feats. Independently review whether this narrow bridge is worth implementing before any persistent feat ledger work.

## Source and existing owners

- Byte-verified C06 feat_asi_links.md PDF201: ASI requires4+, +2 one or +1 two scores, cap20, repeatable. `feat_rules.apply_feat_choice` remains the source of eligibility and ability changes, invoked on a deep detached target4 character with source class_asi. Check shape/types before invoking it; propagate legitimate cap/prerequisite rejection rather than duplicating rules.
- Byte-verified C06 advancement.md PDF41: increased Constitution modifier raises maximum HP once per attained level. Existing `xp.hit_point_gain` owns the base fixed gain and species/feat additions.
- `game.set_player_max_hp` (2979–2988) is the eventual maximum-change consumer. It preserves current HP under increases and does not heal. Its implementation is policy evidence; source only says maximum. This distinction must remain explicit in evidence.

## Projection calculations and invariants

Validate integer levels, scores and HP before numeric calculations; booleans are not integers here. Work on copies only, keep raw and applied input separate, and leave the character/world/RNG untouched. The result carries no ready/applicable progression token and cannot be passed off as `preview_level_up` output.

For selected target4:
- `unpaid_base_gain = xp.hit_point_gain(original_character)` when raw3, else0 when raw4. This is a projection, not a grant.
- Obtain old/new Constitution from the C03 delta and calculate modifier difference.
- `retroactive_max_gain = modifier_difference * 4` for this bounded single-class target; validate no negative/inconsistent transition.
- Projected maximum = existing maximum + unpaid base gain + retroactive maximum gain.
- Report the base-gain component separately. Retroactive ASI current-HP gain is always0 under the existing maximum owner. After base gain, a later maximum application would retain that current HP. Do not represent a max-HP increase as healing or call `heal_player`.
- CON14/maxHP20 at applied/raw3: base6 + retro4 -> max30. XP-first applied3/raw4/max26: base0 + retro4 -> max30. Existing current10/max26 -> current10/max30. Raw3 current4/max20 projects base current10/max26 then ASI current10/max30; this positive-HP example does not authorize base gain at zero/dead.

## Zero/dead boundary and creation nuance

Existing `game.require_player_can_act` rejects player-originated mutations while unconscious/dead. `set_player_max_hp` is an authoritative non-healing consumer, not permission to act. Current XP/progression arithmetic directly adds to current HP; its death-state integration must be separately characterized before actual level4 application. This preparatory calculator must not run or bypass action guards, initialize death state, revive, clear conditions, or certify zero/dead advancement. It may report maximum-only arithmetic while explicitly leaving application unsupported; simplest first contract rejects nonpositive current HP without mutating anything. Existing canonical max-owner tests at zero/stable/dead remain characterization/regression evidence, not permission to apply a feat there.

For future **new** level4 creation, full-final-HP initialization is a separate creation finalization step after all accepted choices, not retroactive healing of an existing character. Do not reuse existing-character no-healing semantics to create an accidentally injured fresh character. No creation4 support in this leaf.

## Test-first proposal

1. Genuine new bridge assertion RED, not missing-import failure. Real existing Sorcerer3 fixture and explicit detached future target premise; no patched MAX or feature-complete claims.
2. Raw3 and raw4 pair produces equal max30 without double base HP. Preserve character snapshot and RNG; input choice unmodified. Existing actual preview/apply/create4 remains blocked.
3. Damaged existing current10/max26 produces maximum30/current10 projection. Spy that no mutation/healing/max setter is invoked by the pure bridge. Separately characterize canonical `set_player_max_hp` on an isolated existing session: current10 remains10; use existing death tests for zero/stable/status/RNG preservation.
4. Cap20 / invalid bool / malformed choice / unsupported class or raw/applied combination reject clearly and preserve inputs. C03 owner already covers split ASI and general eligibility; do not duplicate its resolver or call those paths implemented by this narrow bridge.
5. Positive/current-HP bound checks and explicit zero/dead application exclusion; no fabricated “ready” state or save grant. Existing C03, C06, starting-XP, Hit Dice and death maximum-owner regressions remain unchanged.

Use external frozen interpreter and reviewed guard, unique labels, actual RED/GREEN evidence and independent review. Stop after the narrow pure bridge if approved. Earned feat provenance/save schema, all-stat recomputation, fifth-cantrip choice, seventh PHB prepared option, actual level4 atomic apply and full-final-HP creation remain subsequent obligations.

## Independent review refinement: concrete caller and output contract

The future caller is the atomic `apply_level_choices` level4 branch, only after validated selection and after feat persistence, derived-stat coherence, action/death authorization and rollback integration are accepted. That caller must recompute this projection from pre-mutation state; client/saved projections are never authoritative. No caller is enabled in this leaf. The caller separately consumes `unpaid_base_gain` (existing base progression HP owner), `retroactive_max_gain` and `resulting_maximum` (existing maximum setter; no healing). It must not apply the projected total and then add either component again.

Private helper `_project_selected_asi_hp(character, target_level, choice)` returns status `projected` plus those three numeric fields and the detached existing C03 `feat_delta`, or status `rejected`/`unsupported` with a reason. Never returns a ready/apply token. Input choice is exactly `{'increase': {'constitution': 2}}`; use existing ASI resolver for eligibility/cap and attach `source: class_asi` internally. Supported premise: actual Sorcerer applied3/raw3 or4, target4; no MAX change. Validate only needed typed values and source-owner prerequisites; malformed input fails without mutation.

This refinement supersedes the earlier suggestion to use positive current HP as an exclusion gate: a character-only interface cannot authorize death/world state. It projects maximum-only arithmetic and does not inspect current HP as proof of life. Caller authorization is mandatory before any mutation. Separate existing setter characterization first initializes normal death state, then proves a max increase does not heal; do not claim that `set_player_max_hp` is universally side-effect-free, since it invokes `ensure_death_state`.

## Confirmed current XP ceiling and future caller restriction

Current `xp.py:17–29` has MAX_LEVEL=4 and its threshold table stops at level4/2700 XP. A real XP award cannot produce raw5 from Sorcerer3. `xp.apply_xp` preserves already-existing higher levels but does not grant them. Therefore this preparatory leaf deliberately supports only raw3/4 with applied3 and rejects raw>4 explicitly; its retroactive multiplier4 is not a formula for higher attained levels. No future-state fixture or XP entitlement expansion is included.

Before the XP owner expands or any caller attempts raw>4, revisit this bridge with source-backed per-attained-level retroactive delta (at least max(raw level, target level)) and already-paid base HP accounting. Until that reviewed extension exists, the future caller must respect the explicit unsupported result. Do not reinterpret raw>4 as target4 or silently fall back to multiplying by4. This boundary is accepted as a limitation of the preparatory leaf, not full1–20 progression support.
