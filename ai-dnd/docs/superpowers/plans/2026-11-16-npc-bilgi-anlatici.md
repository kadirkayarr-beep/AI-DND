# NPC Knowledge, Heard Rumours and Narrator Implementation Plan (D-249 + D-250)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every implementer prompt carries `docs/agents/implementer-preamble.md`.

**Goal:** NPCs know more about their town, a place or trail an NPC names is recorded as a heard rumour the player can follow, and arrival narration gets longer, freer limits.

**Architecture:** A new module `ai-dnd/heard_rumours.py` owns the rumour lane: it validates the optional `mentions` field of an NPC speech packet and records a `rumoured` local place and/or a `world["heard_rumours"]` entry. Python validates and commits; the model never writes the world. `town_knowledge` reads those records back into NPC knowledge; a follow-time safety net lets the narrator create a place whose name an NPC said. Narrator changes are prompt/limit edits in `arrival_narration.py` and a cloud-only style block in `api/ollama_adapter.py`.

**Tech Stack:** Python 3, unittest, the existing fake-model doubles (`api/tests/speech_double.py`), journey runner (`api/tests/journeys`).

**Spec:** `docs/design/NPC_BILGI_ANLATICI_TASARIM_20261116.md` (approved, Kadir 2026-11-16). Parent: `MOTOR_HAKEM_MODEL_YAZAR_TASARIM_20261113.md` §4b (Ş4, Ş6).

**Branch/worktree:** `task/d249-tasarim-20261116` in `C:\Users\Kadir\Desktop\AI-DND-k2-d249-tasarim` (from origin/main 4ea8145c; already carries the design doc). Ledger: `.superpowers/sdd/2026-11-16-npc-bilgi-anlatici/progress.md`.

## Global Constraints

- At most 2 model calls per turn (`MAX_MODEL_CALLS_PER_TURN = 2`); this plan adds no model call.
- No money, item, XP, quest, reward or thread is ever created from a rumour.
- No old-save migration (owner rule): new keys get defaults via `INITIAL_WORLD_STATE`; readers use `setdefault`/`.get`.
- Haiku: no `temperature`; JSON schema must pass `model_chain._haiku_schema`. Temperature unchanged everywhere in this slice.
- Every new campaign test fixes the seed (`api/tests/town_seed.py` → `fixed_town`; journeys `campaign_seed`).
- Tests run only through slots: `bash C:/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh <slot> <worktree> test <run> <timeout> <modules>`. No browser tests.
- Every task's targeted run adds the neighbour set: `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys` (04_consume is a known break).
- Tests that pin old behaviour are rewritten only at equal strictness, marked "gevşetme olabilir", and added to the approval list (`docs/agents/onay-listesi-20261115.md`).
- Lane toggle: `AI_DND_RUMOUR_LANE=0` (or `off`) disables recording and removes `mentions` from the schema; default on.
- Name limit 60 chars, `about` limit 120 chars, place description in knowledge 120 chars.
- Bugs found off-task go to `docs/agents/debt-register.md` (8 `|` per row), not fixed in passing.

## Rulings (KOD 2, made while planning)

- `mentions` is a single optional object (like `commitment`), not an array — Haiku grammar limit; spec §9 left it to the builder. Cost if wrong: a schema change in Task 2.
- Rumour entries carry `settlement_id` (spec lists `{id,text,said_by,place_id,turn}`): knowledge must filter per town. Cost if wrong: one extra key.
- `heard_rumours` cap: 64 entries per world, oldest dropped (spec §9).
- Town portrait (spec 7.4): `arrival_narration` only narrates local places and inns, not settlements. The portrait is therefore taken from the main narrator's text on a successful travel turn into a settlement whose `town_portrait` is missing and whose narration source is a model. Knowledge falls back to the settlement's own `description` (the Python fallback the spec names); the fallback is never written. Cost if wrong: Task 6 hook moves.
- `CLOUD_STYLE_RULES` lives in `api/ollama_adapter.py` next to `LOCAL_STYLE_RULES`, because that is where narration-vs-schema calls are told apart (`style = not (in_classifier_call() or in_front_call())`); spec named `model_chain.py`. Cost if wrong: a move.
- Money/claim cleaning of `about`: `validate_location_proposal`'s `mechanical_terms` check plus `town_knowledge.without_unbacked_money` (no new word list).

## Review Focus

1. Model puts a person's name (an existing NPC) in `mentions.name` with `kind: place` → reject silently, nothing recorded, speech unchanged. Test in Task 1.
2. Name arrives with a Turkish case suffix ("Eski Mahzen'de") → stored as "Eski Mahzen"; a later "Eski Mahzen'e git" finds it. Tests in Task 1 and Task 4.
3. Same NPC repeats the same rumour over turns → one place, one rumour entry (dedupe on folded name + settlement). Test in Task 1.
4. Lane switched off after rumoured places exist → places stay reachable and listed; schema has no `mentions`; nothing new recorded. Test in Task 2.
5. Empty, whitespace-only or >60-char name, or `place` without a valid `place_kind` → rejected silently. Test in Task 1.

---

### Task 1: Rumour lane core (`heard_rumours.py`)

**Files:**
- Create: `ai-dnd/heard_rumours.py`
- Modify: `ai-dnd/local_places.py` (`create_local_place` cap count; `arrival_parts` realization)
- Modify: `ai-dnd/game.py` (module-level `world_state`: add `"heard_rumours": []` beside `"next_location_number"`)
- Test: `ai-dnd/api/tests/test_heard_rumours.py`

**Interfaces:**
- Produces:
  - `MAX_RUMOURED_PER_SETTLEMENT = 24`, `MAX_HEARD = 64`
  - `lane_enabled() -> bool` — `os.environ.get("AI_DND_RUMOUR_LANE", "1").strip().casefold() not in {"0", "off"}`
  - `base_name(text: str) -> str` — drops everything from an apostrophe (`'` or `’`) to the end of that word, trims, collapses spaces.
  - `record_mention(game, world: dict, npc: dict, mention: Any, turn: int) -> dict | None` — returns the stored rumour entry or `None` (rejected / lane off). Never raises on bad model input.
  - Rumour entry: `{"id": "rumour_###", "text": str, "said_by": npc_id, "place_id": str | None, "settlement_id": str, "turn": int}`
  - Rumoured place: a normal `local_places` record plus `rumoured: True`, `provenance: {"source": "npc_rumour", "said_by": npc_id, "turn": turn}`.
- Consumes: `local_places.settlement_of`, `local_places.create_local_place(world, settlement_id, kind, *, name=...)`, `local_places.PLACE_KINDS`, `game.validate_location_proposal`, `game.resolve_location_reference`, `town_knowledge.without_unbacked_money`, `npc_statements.fold`.

Rules inside `record_mention` (in order): lane off → `None`; not a dict / bad `kind` → `None`; name = `base_name(name)`, empty or >60 → `None`; folded name equals any NPC's folded name → `None`; `about` cleaned through `validate_location_proposal({"name": name, "type": "building", "description": about})` and `without_unbacked_money` (a claim empties `about`, the mention still records); settlement = `settlement_of(world, npc location)`, none → `None`; `kind == "place"`: existing place by `resolve_location_reference(name)` → link, no new record; else `place_kind` not in `PLACE_KINDS` → `None`; else if 24 rumoured places under this settlement, delete the oldest unvisited rumoured one (by `provenance.turn`) from `world["locations"]` and blank `place_id` on its rumours; then `create_local_place(..., name=name)` (`None` from the 80 cap → record the rumour without a place); dedupe: same folded name + settlement already in `heard_rumours` → return that entry; append, trim to 64.

`create_local_place` cap count skips records with `rumoured` true. `arrival_parts` pops `rumoured` where it sets `visited`.

- [ ] **Step 1: Write the failing tests** (`fixed_town` world, fake `game` = the real module)
  - `test_place_mention_records_rumoured_place_under_current_settlement`: `record_mention(... {"kind":"place","name":"Eski Mahzen","place_kind":"archive","about":"Kuyunun altında"} ...)` → one new location with `rumoured is True`, `parent_location_id == settlement`, `provenance["source"] == "npc_rumour"`, `provenance["said_by"] == npc["id"]`; one `heard_rumours` entry with that `place_id`.
  - `test_money_claim_in_about_is_emptied_and_no_money_moves`: about `"İçeride 50 altın var"` → entry recorded, place description has no "altın", `world` purse/money keys unchanged.
  - `test_existing_place_name_links_instead_of_creating`: name of an existing place → `len(world["locations"])` unchanged, entry `place_id` = that id.
  - `test_25th_rumoured_place_evicts_oldest_unvisited`: 24 rumoured places (turns 1..24, place turn 1 marked `visited` and `rumoured` popped by `arrival_parts`) + one more → oldest *unvisited* (turn 2) gone, realized place kept, new place present, rumours of evicted place have `place_id is None`.
  - `test_full_local_cap_still_records_rumoured_place`: settlement with 8 local places → mention still creates the rumoured place; a plain `create_local_place` after it still returns `None`.
  - `test_rumour_opens_no_thread_quest_or_reward`: `world_threads` data and quest/reward keys equal before/after.
  - `test_first_arrival_realizes_rumoured_place`: `arrival_parts(..., first_visit=False)` on a rumoured record → `"rumoured" not in record`, `record["visited"] is True`.
  - Review Focus 1: `test_person_name_is_not_a_place` → `None`, no change.
  - Review Focus 2: `test_suffix_is_stripped_from_name` → name `"Eski Mahzen'de"` stored as `"Eski Mahzen"`.
  - Review Focus 3: `test_repeated_mention_is_one_place_one_rumour`.
  - Review Focus 5: `test_bad_names_and_kinds_are_rejected_silently` (subTests: `""`, `"   "`, 61 chars, `place_kind: "castle"`, `kind: "npc"`).
  - `test_lane_off_records_nothing` (patch env `AI_DND_RUMOUR_LANE=0`).
- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: heard_rumours`): slot run `api.tests.test_heard_rumours`.
- [ ] **Step 3: Implement** `heard_rumours.py`, the two `local_places` edits and the `world_state` default.
- [ ] **Step 4: Run, expect PASS**: `api.tests.test_heard_rumours api.tests.test_town_knowledge` + neighbour set + any `local_places` test module (`grep -l local_places api/tests/test_*.py` → pick the ones testing `create_local_place`/`arrival_parts`).
- [ ] **Step 5: Commit** `Rumour lane core: NPC-named places and trails recorded as heard rumours (D-249)`.

### Task 2: Wire `mentions` into NPC speech (schema, prompt, turn, undo, save)

**Files:**
- Modify: `ai-dnd/game.py` — `_EXPERIMENTAL_NPC_SPEECH_SCHEMA` (new optional `mentions` object), its specialisation in `ask_dungeon_master` (drop `mentions` when `heard_rumours.lane_enabled()` is false; fill `place_kind` enum from `local_places.PLACE_KINDS`), the NPC speech system prompt (one rule line), the `valid_speech_packet` key allowlist (add `"mentions"`), and the speech-accept site that calls `_remember_experimental_npc_speech` with a valid packet (call `heard_rumours.record_mention`).
- Test: `ai-dnd/api/tests/test_heard_rumours_turn.py`; `ai-dnd/api/tests/speech_double.py` (let `speech_packet` take `mentions=None`).

**Interfaces:**
- Consumes: Task 1 `record_mention`, `lane_enabled`.
- Produces: schema property
  `"mentions": {"type": "object", "properties": {"kind": {"type":"string","enum":["place","trail"]}, "name": {"type":"string","maxLength":60}, "place_kind": {"type":"string","enum":[...PLACE_KINDS]}, "about": {"type":"string","maxLength":120}}, "required": ["kind","name"], "additionalProperties": False}`; not in top-level `required`.
- Prompt rule (Turkish, exact): `"mentions: Konuşmada adını verdiğin bir yer ya da iz varsa yalnız birini yaz; yer için türü listeden seç. Para, ödül, görev ya da eşya yazma. Yoksa alanı hiç yazma."` Replace any existing line that tells the NPC it cannot name/create places with this rule only when the lane is on (keep the existing "cannot write canon" wording for money/items).

- [ ] **Step 1: Failing tests** (API client + `routed_chat`/`speech_packet`, patch `game.ollama.chat`, `fixed_town`):
  - `test_npc_mention_is_recorded_on_the_speech_turn`: speech packet with mentions → after the turn, `heard_rumours` has 1 entry, rumoured place exists, the NPC's spoken text shown unchanged.
  - `test_rejected_mention_shows_no_error`: invalid `place_kind` → turn succeeds, no error text in narration, nothing recorded.
  - `test_undo_removes_rumour_and_place`: speech turn with mention, then the product undo route (copy the pattern of an existing undo test: `grep -ln "undo" api/tests/test_*.py`) → `heard_rumours == []`, place gone.
  - `test_save_load_keeps_rumour_and_place`: save → load in a fresh session manager → same `heard_rumours` and place record.
  - Review Focus 4: `test_lane_off_keeps_old_places_and_drops_schema_field`: with a rumoured place in the world, `AI_DND_RUMOUR_LANE=0` → schema sent to the model (captured from `routed_chat` kwargs `format`) has no `mentions`; the place still resolves by name; a packet with `mentions` records nothing.
  - `test_schema_passes_haiku_shaping`: `model_chain._haiku_schema(schema)` keeps `mentions` with its enums (offline).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** the edits above.
- [ ] **Step 4: Run, expect PASS**: new module + `api.tests.test_heard_rumours api.tests.test_npc_never_bare_unknown api.tests.test_model_chain api.tests.test_f04_greeting_agency_quality` + neighbour set.
- [ ] **Step 5: Commit** `NPC speech may name one place or trail; Python records it as a heard rumour (D-249)`.

### Task 3: NPC knowledge widens (`town_knowledge`, `town_rumours`)

**Files:**
- Modify: `ai-dnd/town_knowledge.py` (`MAX_ITEMS = 10`, `MAX_BYTES = 1500`; `_places` item text; new town item first in `public_knowledge`)
- Modify: `ai-dnd/town_rumours.py` (`rumour_for` up to 2; heard rumours as a source)
- Test: `ai-dnd/api/tests/test_town_knowledge.py` (add; rewrite any test pinning 5/600 or one rumour — "gevşetme olabilir", approval list)

**Interfaces:**
- Consumes: Task 1 entry shape (`settlement_id`, `said_by`, `place_id`, `text`).
- Produces: knowledge item kinds `"town"` (text = first sentence of `town_portrait`, else of the settlement `description`; `location_id` = settlement) and the widened `"place"` text: `f"{name} ({noun}): {first sentence of description, ≤120}"` + `f"; dert: {local_issue short}"` when present + `f"; orada: {roles}"` (roles of NPCs whose location is that place, e.g. "bir demirci, iki muhafız"; no names).
- `rumour_for(...)` returns at most 2 items: open troubles (today's rule) then `heard_rumours` of this settlement; the speaker (`said_by`) always gets it, others via `percent(npc.id, "rumour", rumour_id) < HEARD_PERCENT`. Rumour item `location_id` = its `place_id` (may be `None`).

- [ ] **Step 1: Failing tests**:
  - `test_place_item_carries_description_issue_and_roles` (text contains the first description sentence ≤120, "dert", a role word, no NPC name).
  - `test_town_item_comes_first_from_portrait_or_description` (subTest with/without `town_portrait`).
  - `test_up_to_two_rumours_per_npc`.
  - `test_speaker_always_knows_own_rumour_and_others_follow_coverage` (fixed seed; assert the speaker has it; assert the set of other NPCs equals the `_percent` rule result).
  - `test_hidden_place_still_not_listed`.
  - `test_knowledge_stays_within_10_items_and_1500_bytes`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS**: `api.tests.test_town_knowledge api.tests.test_npc_never_bare_unknown api.tests.test_heard_rumours` + every module importing `town_rumours` (`grep -l town_rumours api/tests/*.py`) + neighbour set.
- [ ] **Step 5: Commit** `NPC knowledge: town line, richer places, up to two rumours incl. heard ones (D-249)`.

### Task 4: Follow-time safety net (spec 7.3)

**Files:**
- Modify: `ai-dnd/heard_rumours.py` (add `heard_in_speech`)
- Modify: `ai-dnd/game.py` — `_may_propose_local_place` (allow off-street when heard), `_accepted_local_place` (name = `base_name(target_reference)`), `_settle_local_place` (provenance `npc_rumour` when heard)
- Test: `ai-dnd/api/tests/test_heard_rumours_follow.py`

**Interfaces:**
- Produces: `heard_in_speech(world: dict, settlement_id: str, reference: str) -> str | None` — returns the speaking NPC id when `fold(base_name(reference))` occurs as a substring of `fold(entry["npc"])` in `world["npc_speech_log"][npc_id]` for an NPC whose location's `settlement_of` is `settlement_id`; else `None`.
- Consumes: Task 1 `base_name`; `npc_statements.fold`; `local_places.settlement_of`.

- [ ] **Step 1: Failing tests** (fake model; NPC speech packet without `mentions` whose text names "Eski Mahzen"; player not on an open street):
  - `test_unrecorded_name_said_by_npc_becomes_a_place_when_followed`: player "Eski Mahzen'e gidiyorum" + narrator proposal → a real local place (no `rumoured`), parent = settlement, `provenance["source"] == "npc_rumour"`, name `"Eski Mahzen"`.
  - `test_name_nobody_said_keeps_todays_behaviour` (off-street, no speech match → no place created).
  - `test_speech_in_another_settlement_does_not_count`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS**: new module + `api.tests.test_narration_proposal_marker api.tests.test_heard_rumours` + neighbour set.
- [ ] **Step 5: Commit** `Safety net: a place an NPC named can be created when the player follows it (D-249)`.

### Task 5: Narrator limits and cloud style (D-250)

**Files:**
- Modify: `ai-dnd/arrival_narration.py` — `RULES` ("en çok 6" first visit, "en çok 4" return; remove "Havadan söz etme."; keep quote ban and the "Yeni kişi, eşya, çıkış, yol, ücret, para ya da görev ekleme." rule), `_shaped` `limit = 6 if first else 4`, `facts` `son_anlatim` cut 1200.
- Modify: `ai-dnd/api/ollama_adapter.py` — `CLOUD_STYLE_RULES` constant; in `OllamaAdapter.chat`, the call handed to `self._chain.chat` gets it appended to the first system message when `style` is true; local path unchanged.
- Test: `ai-dnd/api/tests/test_arrival_narration.py`, `ai-dnd/api/tests/test_model_chain.py` (or the adapter's own test module — `grep -l LOCAL_STYLE_RULES api/tests/*.py`).

**Interfaces:**
- Produces: `CLOUD_STYLE_RULES: str` (Turkish; content per spec 7.5: sensory detail, varied sentence length, dark-fantasy tone, answer bound to the scene instead of a short reply; 18+ scope, no softening). Draft:
  `"BULUT ANLATIM KURALLARI: Sahneyi duyularla kur: ses, koku, ışık, dokunuş. Cümle uzunluğunu değiştir; kısa vuruşlu cümleyi uzun betimlemeyle dengele. Ton karanlık fantezi: sert, somut, yetişkin; yumuşatma. Tek satırlık kuru cevap verme; cevabı sahnedeki kişiye, yere ve ana bağla. Verilen kurallar ve sınırlar bu kuralların üstündedir."`

- [ ] **Step 1: Failing tests**:
  - `test_first_visit_keeps_six_sentences_return_keeps_four` (fake narration of 8 sentences).
  - `test_weather_sentence_is_no_longer_banned_by_rules` (`"Havadan söz etme" not in RULES`).
  - `test_quotes_still_dropped_and_no_new_things_rule_kept`.
  - `test_last_narration_passed_up_to_1200_chars`.
  - `test_cloud_call_gets_cloud_style_on_narration_only`: fake chain records the call → narration call system text ends with `CLOUD_STYLE_RULES`; a classifier call (inside `in_classifier_call()` scope) has no `CLOUD_STYLE_RULES`; the local call has `LOCAL_STYLE_RULES` and no `CLOUD_STYLE_RULES`.
  - Rewrite any existing test pinning 4/3 sentences, the weather ban or 400 chars at equal strictness ("gevşetme olabilir", approval list).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS**: `api.tests.test_arrival_narration api.tests.test_model_chain` + adapter test module + neighbour set.
- [ ] **Step 5: Commit** `Narrator: 6/4 sentence caps, weather allowed, longer history, cloud style block (D-250)`.

### Task 6: Town portrait (spec 7.4)

**Files:**
- Modify: `ai-dnd/game.py` — in `_narrate_resolved_turn`, after the final narration is fixed: when `action_result["action"] == "travel"` and success, the new location is a settlement (`local_places.settlement_of(world, loc) == loc`), its record has no `town_portrait`, and the narration source is a model (not Python fallback) → `record["town_portrait"] = first two sentences` (`_split_sentences_keep_speech`, quotes dropped, `town_knowledge.without_unbacked_money`).
- Test: `ai-dnd/api/tests/test_town_portrait.py`

**Interfaces:**
- Produces: settlement location key `town_portrait: str` (read by Task 3's town item).

- [ ] **Step 1: Failing tests** (fake model, two-settlement fixed world):
  - `test_first_model_arrival_writes_two_sentence_portrait`.
  - `test_python_fallback_arrival_writes_nothing` (model raises → no key).
  - `test_second_arrival_does_not_overwrite`.
  - `test_undo_removes_portrait`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS**: new module + `api.tests.test_town_knowledge` + neighbour set.
- [ ] **Step 5: Commit** `Town portrait: first model arrival's opening lines kept for NPC knowledge (D-249)`.

### Task 7: Fixed-seed journey 96 (heard place end to end)

**Files:**
- Create: `ai-dnd/api/tests/journeys/scenarios/96_duyulmus_yer.json`
- Modify: `ai-dnd/api/tests/journeys/runner.py` (speech reply may carry `mentions`; observed key `duyulan` = list of `{"ad": place name or None, "metin": text}` from `heard_rumours` of the current settlement), `schema.py` (allow both), `report.py` `_KINDS` (new group `("Söylenti ve duyulmuş yer", ("96",))`)
- Test: neighbour set covers runner/schema/report; `api.tests.test_journeys` runs 96.

Steps of scenario 96 (fixed `campaign_seed`): NPC A speaks with `mentions` (place "Eski Mahzen", archive) → expect `duyulan` has it; ask NPC B about the town → expect B's speech call input (`konusmaya_giden`) contains "Eski Mahzen"; player goes "Eski Mahzen'e gidiyorum" → expect location name "Eski Mahzen"; `reload` → equal; `undo` → back at the previous place, place still recorded (the mention turn was earlier); every step zero tolerance.

- [ ] **Step 1: Write scenario + runner/schema/report edits; run `api.tests.test_journeys` → expect 96 FAIL before Tasks 1-4 are present (on this branch they are; instead verify the scenario fails when `AI_DND_RUMOUR_LANE=0` is set in the scenario env).**
- [ ] **Step 2: Run neighbour set → PASS (04_consume known break only).**
- [ ] **Step 3: Commit** `Journey 96: a heard place is known by another NPC, followed, saved and undone`.

### Task 8: Gated checks (need Kadir)

- [ ] **Step 1: Haiku schema live check** (spec §8.4): one real Haiku call with the new speech schema. Before running, show Kadir the estimate (1 call, under 0.01 USD) and wait for approval. Pass = HTTP 200 and a reply that `_shaped` accepts. Record in ledger.
- [ ] **Step 2: Measurement (spec 7.6)** is NOT run in this plan: budget estimate goes to Kadir as a separate item.

### Slice end

- [ ] Full suite once (slot run), result in ledger; any new red traced to its commit.
- [ ] `graphify update .`
- [ ] Independent whole-branch review on Opus (save, Geri Al and world keys touched) — not fable.
- [ ] Approval list updated with every rewritten test.
- [ ] Push/PR only with Kadir's approval; CI checked after push.
- [ ] Kadir plays ≥10 minutes (play gate); ledger "oynayış bekliyor" until then.
