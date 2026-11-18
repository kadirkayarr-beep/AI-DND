# Tests that read the engine's source (game.py split, T0.3)

Measured 2026-11-18 on base e0988ecd. Search: test files under `ai-dnd` (`test_*.py`, `*_test.py`, `api/tests/`) that
mention `game.__file__`, `"game.py"`, `inspect.getsource(game` or glob `*.py`: **41 files**. Files that contain the
text `game.py` anywhere (comments included): **32** (the plan said 25, the pre-flight regex said 29).

Helper: `api/tests/engine_sources.py` -> `engine_source_files()` / `engine_source_text()` (game.py + `game_parts/*.py`).

Classes: **A** reads engine text or AST to assert something; **B** uses the path only to find a folder or a function
object; **C** executes the file (Task 12).

## A, rewritten to use the helper (10 files)

| Test | Present form (before) | Now |
|---|---|---|
| `test_exits.OnlyExitsReadsTests` | `root.glob("*.py")` text search for three needles (top level only: parts missed) | top level plus the `game_parts` files, same skip rules |
| `test_refusals.RefusalTexts.test_the_old_vague_line_is_gone` | `assertNotIn` on `game.py` text | `assertNotIn` on `engine_source_text()` |
| `test_refusal_census.RefusalCensus` (2 tests) | AST of `game.py` for `fail(...)` codes; AST of `game.py` for `combat_refusal_turn` | the same AST walks over every engine file |
| `test_roadmap_k02 ...test_every_npc_damage_caller_mitigates_first` | 40-line window search per `game.py` line | same window search per engine file |
| `test_roadmap_w01 ...test_no_mind_reading_mechanic_discloses_thoughts_today` | `assertNotIn` on `game.py` text | same, per engine file |
| `test_game_name` (banner; save format id) | `inspect.getsource(game)` and `ai-dnd/game.py` text | `engine_source_text()` |
| `test_tr_names ...test_game_prompt_carries_the_narrator_note` | `inspect.getsource(game).count(...) >= 2` | count over `engine_source_text()` |
| `test_combat_v2_authoritative.test_W_single_end_combat_definition` | AST of `game.py`: exactly one `end_combat` | exactly one across every engine file |
| `test_narration_source_record.TheListIsTheEngines` (2 tests) | `game.py` + `dialogue_runtime.py` text; `rglob` module set must equal reporters | engine text for the `game.py` entry; a `game_parts` file counts as `game.py` (marked: may loosen) |
| `test_d053_product_no_test_imports` | `AI_DND.glob("*.py")` + dirs with `__init__.py` | plus the `game_parts` files even without `__init__.py` |

## A, already covers `game_parts` (no change; whole-tree `rglob`)

`test_talk_mode_writers` (4 tests), `test_tr_case`, `test_dilim4c_4b_review_fixes` (two scans),
`test_game_name.test_env_variable_name_set_is_unchanged`. `test_coin_writers` is not touched (spec).
Note: `test_talk_mode_writers` pins `("game.py", ...)` file names in two expected lists; a later move task that moves
those calls must update them.

## B

`test_dilim4a_death_audit`, `test_roadmap_w03` (`inspect.getsource` of one function object: follows the function),
the `_LIVE = Path(game.__file__).parent / "saves"` tests (campaign_ownership, campaign_ownership_schema_migration,
clerk_http, http_auth_gate, http_two_player_isolation, local_person_replay_review, local_play_auth, oidc_boundary,
session_ownership, startup_safety), `GAME_FILE` constants that are never read (`test_actual_logic`, `test_combat`,
`test_door_enter`, `test_query`, `test_self_query`, `test_validate`), `test_regression_evidence`,
`test_development_tooling` (temp repos), comment-only mentions.

## C (left for Task 12)

`test_sessions` (exec and subprocess of `game.__file__`), `test_engine_surface` (`spec_from_file_location`).

## Not touched (other T0 tasks' tooling tests)

`test_engine_move_check`, `test_engine_move_tool`, `test_engine_patch_census`, `test_engine_split_inventory`,
`test_engine_sensitivity`.
