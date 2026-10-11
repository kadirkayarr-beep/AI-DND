# AI-DND

AI-DND is a Turkish-language terminal D&D game.

## Player path

The campaign UI talks to the FastAPI adapter, not the Node `artifacts/api-server`.

```powershell
# From the repository root (Desktop\AI - DND)
.\start_local.ps1
```

Default local ports: FastAPI `:8008`, Ollama `:11434`, experience Vite (see the script).
Set `OLLAMA_HOST` (and `OLLAMA_PROXY_TOKEN` if the proxy requires it). Optional
`AI_DND_CAMPAIGN_DB` points at a sqlite file. Required model: `qwen3:8b`.
Check `GET http://127.0.0.1:11434/api/tags` and `GET http://127.0.0.1:8008/api/game/health`.
Do not use interactive `ollama run` for this path.

Product UI: `artifacts/ai-dnd-experience`. `artifacts/ai-dnd-web` is session-only.

## Run (terminal)

From the repository root:

```bash
python main.py
```

The game requires a reachable Ollama service for Qwen intent parsing and
narration. The deterministic engine still falls back safely when Ollama is
unavailable.

During play, use `/save` and `/load` (or `/kaydet` and `/yükle`).
The default file is `ai-dnd/saves/adventure.json`. Supply a path after the
command to use another slot, for example `/save saves/forest.json`.
Saving replaces the chosen slot; loading replaces the current session.
Saves include character, world state, NPC memories, and recent narration.
They are local JSON files, not tamper-proof or signed saves.
If the default save exists at startup, choose to continue it directly or
create a new character. Loading another slot remains available with `/load PATH`.

## Independent adventures

Imported callers can create independent adventures without changing the
terminal's default game:

```python
import game

first = game.create_session(seed=42)
second = game.create_session(seed=99)
result = game.execute_intent({"intent": "attack"}, "Gobline saldır", session=first)
first.save_game("saves/first.json")
```

Each session owns its character dictionary, world, recent narrations, chat
messages, and random generator. Helpers accept `session=`; bound calls such as
`first.run_player_turn("Etrafa bak")` select the same session for nested rules.
Calls without a session keep using the terminal's default adventure, including
module character aliases (such as `game.current_hp`) and caller-held
world/narration references. Plain `exec` dictionaries are not a character-state
input: use `create_session()`, edit `session.character`, and call session-bound
helpers instead.
Loading preserves the top-level character/world/history containers; nested
world records may be replaced. Engine JSON saves use format version 5.
Versions 1 through 4 still load. Versions 1 through 3 migrate to an empty
spell list and zero remaining slots. Versions 1 through 4 migrate to 0 XP
and keep their existing level and hit points. Corrupt or unsupported
versions are rejected. Terminal JSON saves do
not include the random generator or chat messages. Campaign SQLite saves are
a separate store: they include RNG, journal, lore, narrative memory, and
bounded combat history.

## Verify

Daily (Windows): UTF-8 is required or emoji in pipeline tests fail.

```powershell
.\dev.ps1
.\dev.ps1 -List
```

Equivalent:

```bash
python ai-dnd/run_tests.py
```

The default runner selects release deterministic gates (`--suite release` is
equivalent). Combat coverage includes `test_combat.py` and
`test_combat_v2_authoritative.py`, the authoritative scheduler contract.
Death-save scheduler boundaries are also gated by
`api/tests/test_death_bounded.py` and `api/tests/test_initiative.py`, run through
`unittest` from the project directory so their engine and API assertions execute.
Narrative coverage includes `test_narrative_rebalance.py` and
`test_narrative_safety_calibration.py`: active-NPC character questions must
return canonical sheet facts without model calls, and NPC name disclosure and
recall must stay scoped to supported player evidence. These suites block
unexpected Ollama calls; model-response scenarios use explicit offline mocks.
Every selected gate is source-preflighted before execution; failures remain
nonzero and are listed even when later gates pass.

Each child gate has a **300-second timeout**, covering API imports, `load_tests`,
and test/script execution. Override it for either suite with a positive, finite
number of seconds (fractions are allowed):

```bash
python ai-dnd/run_tests.py --gate-timeout 600
```

On the supported POSIX runtime, each gate starts in a separate session/process
group. A timeout sends `SIGKILL` to that whole group (the direct child and its
inherited-group descendants, including grandchildren), then waits up to **5
seconds** to reap the direct child. It reports `GATE TIMED OUT` with the gate's
name and limit and marks that gate failed even if it wrote a completion receipt.
If the child cannot be reaped within that cleanup limit, `GATE CLEANUP FAILED`
is also reported; cleanup never waits indefinitely. Offline copied-runner tests
on Linux verify sleeping descendants, including ones ignoring `SIGTERM`, have
no live work left before the later gate runs for scripts, API import/loading
hooks, and prototype selection. Orphan zombies are left for their adopting
parent to reap; descendants deliberately leaving the group are outside this
guarantee. Later gates still run; the final failure list stays in inventory order.
This is a per-gate deadline, not a whole-suite deadline. Listing and source-only
preflight do not execute child gates.

Runner interruption is verified separately from timeout behavior. During an
active gate, Ctrl+C (`SIGINT`/`KeyboardInterrupt`), `SIGTERM`, and `SIGHUP` stop
the active gate's entire inherited process group with `SIGKILL` and bound the
direct-child reap to the same **5 seconds**. Repeated catchable signals cannot
interrupt that cleanup. The runner then exits nonzero without starting later
gates or reporting suite success, even if an API gate wrote a completion receipt
early. Offline Linux copied-runner fixtures verify scripts in default/explicit
release and prototype selections, plus API import, loading, and execution,
including grandchildren ignoring termination signals. This does not cover
uncatchable termination of the runner (`SIGKILL`), machine loss, or descendants
that deliberately detach from the gate's group.

The retired `test_combat_v2.py` and `test_combat_v2_fixed.py` are historical
prototype diagnostics, **not release gates**. Their obsolete fixture assumptions
may fail against the current engine. The fixed entry point delegates to the
same prototype scenarios, so these commands are not independent coverage.
They remain available explicitly, with their own nonzero failure reporting:

```bash
python ai-dnd/run_tests.py --suite prototype
python ai-dnd/run_tests.py --list
python ai-dnd/run_tests.py --suite prototype --list
```

Listing only shows the selected inventory; it does not certify a passing run.
Prototype results cannot certify or block the default release selection.

Full API discover and live 30-turn smokes are **not** the daily gate:

```powershell
.\dev.ps1 -ApiDiscover
```

POSIX signal tests skip on Windows. Run them under WSL on a native Linux filesystem copy; a Windows worktree `.git` pointer is not resolvable under `/mnt/c`.

The runner covers the portable deterministic gates, including both historical
V2 commands. `test_combat_v2.py` contains 15 turn-pipeline scenarios with fresh
sessions, scripted initiative/attack/damage dice, and scoped model stubs.
`test_combat_v2_fixed.py` is a compatibility entry point to that same suite,
not an additional set of scenarios. The authoritative V2 suite remains separate.
Initiative precedes attacks; a surviving exchange advances one round per command.
Live tests are separate:

```bash
python ai-dnd/acceptance_test.py
python ai-dnd/live_intent_test.py
python ai-dnd/live_memory_test.py
```

Those live suites require the `qwen3:8b` model to be installed and available
through Ollama.

To compare the current session-based engine with the checkpoint's nine-turn
smoke, run `python ai-dnd/live_narration_smoke.py` with a local Ollama service
hosting `qwen3:8b` and `OLLAMA_HOST` / `OLLAMA_PROXY_TOKEN` available in the
environment. The runner sends the bearer token only as an HTTP header and never
prints it. It prints a UTF-8 JSON transcript with the source hash,
raw/normalized/validated intents, rule results, model replies and per-turn
call counts, final narrations, fallback replacements, issues, and state deltas.
It also adds two safety turns for remote NPC presence and unsupported claims.
An unavailable model exits 2 with `BLOCKED`; it is not a passing live test.
The recorded checkpoint's 14 calls/9 turns and 3 fallbacks are comparison
figures from the original Windows source, not results for this engine.

## AI pipeline import

The uploaded `CHECKPOINT_AI_PIPELINE_V10.md` records the validation of the
original Codex source (`game.py` SHA-256 `67be354a…`) on the original Windows
machine. The uploaded RAR remains in `attached_assets/`. A second uploaded
archive contains the focused test scripts and live Ollama traces for that same
source hash. Its standalone
`game.py` was **not** copied over this project's session and save architecture:
intent/query/exploration grounding and narration safeguards were adapted
into the current engine. `test_ai_pipeline_port.py` covers session-specific
regressions; `test_ai_pipeline_semantics.py` runs the recovered 87 semantic,
24 query-grounding, and 18 narration-safety checks against the current engine.
The archived smoke traces are historical evidence, not proof that this engine
was live-tested on the original machine. A separate nine-turn smoke against
the current engine and configured Qwen service is recorded in the checkpoint
addendum; its model output and fallback count varied between runs.