# Cursor integration handoff — Stage 10A narration / intent repair v1

Date: 9 October 2026 (Europe/Istanbul). Owner explicitly removed READ ONLY and supplied the second Codex implementation approval in this chat.

## Acceptance status

**Scoped repair VERIFIED. Final 20-turn manual narration review PASS within this scenario. Overall Stage 10A NOT CERTIFIED; Stage 10B BLOCKED; production NO-GO.** No broader acceptance, deployment, activation or merge is approved.

Final raw smoke remains `MECHANICAL_PASS_NEEDS_MANUAL_NARRATION_REVIEW`; its separate completed review is `manual-narration-review.json` / `MANUAL_NARRATION_REVIEW.md`. Do not rewrite the raw transcript status. The scenario has no canonical hostile participant and explicitly skips live combat. Offline real `start_combat` travel-block coverage passed, but cannot certify live combat narration. Local Windows/Qwen evidence does not replace Replit integration/runtime approval or whole-repository acceptance.

## Checkout and ownership

Work only in `C:\Users\Kadir\Desktop\AI-DND-phase8-expansion`, branch `phase8/emergent-storytelling-expansion`, HEAD `f63d952506064cd59e960f1e3efa6627d4e52053`. Worktree was dirty before this session and remains dirty. No commit, push, merge, reset, clean, stash, checkout restore, schema change, production DB/save access, city activation or Phase 9 action occurred.

The previous shop/gameplay handoffs and evidence were preserved. `shop_creation.py` is byte-identical to the prior shop owner. The Neverwinter pack files are unchanged, verified with before/final SHA-256. `api/main.py`, lore authority and prior freeze/admission edits were not rewritten by this session. Synced `sources/` files were read-only throughout.

## Narrow changes

- Existing explicit shop detector no longer treats English find/get/want/need as creation verbs. `Find a local merchant for this campaign` uses the existing Python merchant search and finds the saved keeper. When a local shop already exists, that search skips unrelated scene materialization; owner creation/validators/identity/link/capacity rules remain unchanged.
- Shop refusal and unsupported economy answers now use player-facing language. Capacity refusal no longer turns an implementation limit into city geography. The negative acknowledgment is for the current request; it does not introduce a new persisted never-create preference.
- `local_dialogue.unresolved_named_address` detects a bounded capitalized vocative. Unknown Elara cannot inherit the bartender/active conversation. The current turn answers invalid target with no NPC or name-memory creation. Existing known names/visible roles and explicit stable target IDs retain their owner routing.
- `living_world` maps public role labels into Turkish, keeps canonical role/name strings intact, and builds natural scene lists. Unknown appearance descriptions are not displayed as personal names. Legacy identity visibility remains compatible; the legacy test also asserts its raw `Traveler` role remains unchanged.
- `resolved_presentation.py` only renders already resolved checks/verified context. Lore rejection no longer hides Investigation success/failure. The specific Neverwinter rebuilding Investigation is bounded to the actual result plus loaded rebuilding fact; unrelated Investigation is not forced into this template. This also rejects otherwise accepted English prose about crouching, workers or new discoveries. No findings, lore, inventory, quests, mechanics or persistence are authored by this presentation helper.
- Successful explicit shop creation retains one narrator call, but ungrounded prose is deterministically replaced by the shop owner's resolved scene. Crowd/props/trembling/first-person drift cannot establish shop scene facts. This conservative exact resolved-scene check is limited to shop creation and the bounded rebuilding investigation, not general narration.
- Loaded lore presentation qualifies The North/Sword Coast as the book's regional grouping, and renders High Road's existing `renewed` safety fact as safe to travel again. No lore fact/pack was added or changed; travel encounter safety is not guaranteed.
- Temporary `_agent_debug_log` and all marked calls were removed from `game.py`. Original `C:\Users\Kadir\Desktop\AI-DND-phase8\debug-6a7cc6.log` was copied before retirement; its original/copy hashes match and the original was not deleted or modified.
- Smoke-only observers retain ordered model phase/gate traces and raw NPC memory, never model prompts or credentials. Their wrappers exist only in the isolated child smoke process. The harness requires trace/count agreement, <=1 narration call, no post-gate call and <=2 total calls, plus success/failure narration compatibility and existing merchant search. Original mechanical/isolation/restart assertions remain. No acceptance failure was removed or deferred away.

## Exact files and final SHA-256

| File | Final SHA-256 |
|---|---|
| `ai-dnd/api/tests/live_neverwinter_canon_smoke.py` | `62eadaaa18ceb1ec01fd52860cf25b95b157ad2bac200623a0f447f2235304b7` |
| `ai-dnd/api/tests/test_live_neverwinter_smoke_diagnostics.py` | `2dbbd9ca65314b4c6f5819388549e7a7739b2dd7d81bdfc22ce2744bbd4e8aaf` |
| `ai-dnd/api/tests/test_lore_engine_integration.py` | `3943803d11d581ba28e6b3b9f315503cbc1e6abb3b3369b0f8a4c9f1aa7a7cd2` |
| `ai-dnd/game.py` | `7c2a449b88a934f196ffe275ee7fc6cc862c7cdde52dd8994962a26f15921c37` |
| `ai-dnd/living_world.py` | `de19ff6d3fd30b22ccf18c053836b1984efec8ed83786665c58ba61c457126de` |
| `ai-dnd/local_dialogue.py` | `a93ef3a778d1e5fb6163a7197a5ed58f3706becf0770f7ab78c2609333655118` |
| `ai-dnd/test_playable_living_world.py` | `8f28c8276da12e66b76f1eb313bf39eae3fa64d1541564b18c7370db897aadfa` |
| `ai-dnd/test_shops.py` | `d43f3fe0c1aefdd812e8cdc397eef36abea4318485dcfb19dd76685ef0269c13` |
| `ai-dnd/resolved_presentation.py` | `123b120356fd522ebd97d8b3eb5def10e782d206f32259a9a37503047f7a87a3` |
| `ai-dnd/api/tests/test_stage10a_narration_intent.py` | `24a349b3ba8ae7534d53216627c04aab3100aa02cfb9ea44cd9dd1e4bd790e80` |
| `ai-dnd/shop_creation.py` (unchanged) | `3f86af37ecc79bc870c2d8c3f0e6188c8eea404cfb6f61a31f2d94b8c3779c6d` |

File names above are repository-relative. All absolute paths resolve under the checkout named above. `this-session-only.patch` compares to the captured dirty starting files and includes the two new modules; `tracked-diff-final.patch` also includes pre-existing work and must not be used as a wholesale restore/reapply patch. Two pre-edit test copies (lore integration and smoke diagnostics) were reconstructed by reversing only the exact string substitutions, and are identified here; other before copies were captured directly before editing.

## Tests with actual evidence

Run from `ai-dnd`, with `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`.

| Evidence log | Observed result | Scope / timing |
|---|---|---|
| focused-final.log | 33 tests OK, exit 0 | Initial narrow repair |
| regressions.log | 277 tests OK, exit 0, 93.211s | Shop, lore/freeze, campaign/persistence/idempotency/equipment, safety/blockers, gameplay and new initial tests |
| final-affected-regressions.log | 245 tests OK, exit 0, 2.061s | Final production code, after bounded accepted-prose repair; adds scene/foundation/narrative suites |
| success-failure-final.log | 12 tests OK, exit 0, 0.138s | Final test-only seed subcases: real Python rolls 5/DC15 failure and 20/DC15 success, rejected invented prose, no narration retry |
| scene-narrative-regressions-final.log | 159 tests OK, exit 0 | Scene/living-world foundation/narrative director/memory/rebalance |

Do not add these counts; suites overlap. This is not whole-repository certification. Early fixture mistakes and the expected-label failure are retained in `focused-initial.log`, `focused-rerun.log`, `grounded-focused.log` and `scene-narrative-regressions.log`. The raw legacy role test was updated for translated public presentation while additionally protecting its stored role. Existing shop creation tests now say Create rather than Find; a separate new Find test strictly verifies search/no duplicate IDs. Original state/isolation/rollback/economy assertions were retained.

Final affected command:

```text
python -m unittest api.tests.test_stage10a_narration_intent api.tests.test_stage10a_gameplay_repairs api.tests.test_explicit_shop_creation api.tests.test_live_neverwinter_smoke_diagnostics test_shops api.tests.test_lore_engine_integration test_narrative_safety_calibration test_checkpoint_blockers test_playable_living_world test_narrative_rebalance api.tests.test_living_world_v2_foundation api.tests.test_narrative_memory api.tests.test_narrative_director -q
```

277-test command is preserved in `commands.txt`. `git diff --check` exit 0. Negative-path ERROR logs in passing suites are expected autosave/rollback coverage.

## Real isolated Qwen smoke and manual results

Model `qwen3:8b`, process-local `OLLAMA_HOST=http://127.0.0.1:11434`. Each run creates a separate temporary SQLite campaign and port, performs API restart/resume, and retains logs under a unique `live-api-*` directory. No production save or database, live RNG seed/state injection, inserted hostile, or fabricated route was used. These were new smoke runs after source changes, not retries of rejected narration.

| Run | Mechanical | Manual |
|---|---|---|
| live-smoke-01.json | 20 turns, exit 0 | Investigation 14/DC15 failure rendered correctly; remaining awkward scene list prompted presentation edit. |
| live-smoke-02.json | 20 turns, exit 0 | FAIL at turn 9: 13/DC15 failure had accepted invented English scene/action prose. Evidence retained; no PASS was granted. |
| live-smoke-03.json | 20 turns, exit 0 | All 20 reviewed, scoped manual PASS; Investigation exactly 15/DC15 success rendered correctly after deterministic fallback. |

Final run: total 4 calls; turn7 one intent, turn9 one intent + one narration, turn12 one narration, all other turns zero. Turn9 gate `UNGROUNDED_RESOLVED_CHECK`, turn12 `UNGROUNDED_SHOP_SCENE`; neither is followed by a model call. Max calls per turn 2. Turn13 finds the same shop/keeper. Turn16 explicitly rejects unknown Elara with all NPC memories empty. Turn18 Arven appears only in npc_001 player-origin memory; turn20 the same keeper recalls it after restart; npc_002/003/004 contain no Arven in any raw memory entry. Shop `shop_001` ↔ `npc_001` survives.

Turn15's child/coin texture is visible in the public scene's Python-authored BLUE event/referent and does not transfer coins, grant a quest or create an official lore fact. Turn12 contains only the resolved shop/keeper presence, with no generated atmosphere persisted. All 20 per-turn review notes/narrations are in the manual JSON/Markdown.

## Uploaded book verification

Read-only uploaded `Forgotten Realms - Heroes of Faerun.pdf` was rendered and visually inspected at one-based PDF pages 59,63,89,90,97. `lore-source/source-manifest.json` records its absolute source path/hash. `lore-source/SOURCE_REVIEW.md` records bounded paraphrases and interpretation limits. These independently support turns1–5, including current1501/year, rebuilding/lord, Alliance, book regional grouping, High Road safety/trade/Trade Way. No claim of full lore-pack or whole-book review is made.

## Remaining gates and Cursor continuation

- Overall Stage10A remains NOT CERTIFIED because this scenario does not provide live combat evidence, and no broader/Replit production acceptance was performed. Stage10B BLOCKED and production NO-GO remain.
- Do not reopen persistence/schema, shop owner, lore pack, city activation, Phase9 or merge anything based on this handoff.
- Do not reapply existing shop owner/routing or overwrite the pre-existing dirty lore work. Review `this-session-only.patch` and new modules.
- A future live combat gate must use an authorized canonical participant through existing owners, not a smoke fixture injected to obtain PASS.
- If additional smoke is needed, use a new evidence path/run number. Never retry a rejected narration within its turn.

## Durable evidence

`C:\Users\Kadir\Desktop\AI-DND-phase8-expansion\.local\evidence\stage10a-narration-intent-20261009-014406`

Contains three full raw transcripts/exit codes/stderr, isolated API logs/audits, all test logs, original debug log/hash, before/final Git snapshots, source hashes, own patch and completed manual/source reviews. `evidence-hashes.json` provides SHA-256 for retained artifacts.
