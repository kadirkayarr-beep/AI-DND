# Living World V2 gameplay contract

This note records the user-visible guarantees and implementation boundaries for
the Living World V2 foundation. It does not replace the approved design
document or the Python engine's gameplay rules.

## Authority and persistence

- Python owns campaign state, character identity, scene materialization,
  referent lifecycle, lore access, journal transitions, and campaign saves.
- `game.py` remains unchanged. API-layer additions must use its existing
  session, state, save, and turn boundaries; they must not emulate hidden
  engine mutations.
- Campaign starts must resolve to an installed, verified start-catalog entry.
  A character's origin is personal identity only. It does not grant bonuses,
  affiliations, relationships, canon facts, or public recognition.
- Opening and ambient selection make no model calls. Existing per-turn Qwen
  limits and engine-owned narration remain unchanged.
- A saved campaign keeps its opening, scene event history, and event counts.
  Resume projects that saved opening instead of choosing a replacement.

## First scene and ambient events

- The opening uses the selected starting location, Python world metadata,
  character background/origin/backstory, and one context-compatible GREEN
  event. It does not assume an action, assign a quest, or claim that local
  people know the character's origin.
- Legacy campaigns created without a registered starting location keep their
  existing behavior and omit this new opening rather than inventing a place.
- GREEN events are presentation-only. BLUE events may create only the
  existing short-lived, location-scoped scene referent; they do not create
  persistent NPCs or canonical world facts.
- The bounded catalog is selected deterministically from campaign seed,
  location, turn, event context, and recent event history. Recent event IDs
  and repeat groups are avoided when alternatives exist; event counts and the
  recent history are stored with the existing scene state.
- Background and origin can modestly bias eligible event selection. They do
  not override location, time, weather, environment, or scene constraints.
- ORANGE/RED events and events requiring mechanical, quest, faction, economic,
  or other persistent consequences are not enabled by this foundation. Those
  require an explicit engine-authoritative state transition and tests.

## Existing systems remain authoritative

- Lore queries use structured, campaign-bound evidence; unsupported or
  unrelated questions must not mutate the world.
- Narrative memory is narrow, selected, and bound to the relevant NPC ID.
  Generated narration alone is not canonical memory.
- Quest state and journal transitions remain Python-owned. No production
  quest definition is invented by ambient events.
- Skill and combat outcomes are shown only when validated by the engine.
  The client must not create substitute roll results.

## Contract and verification

- `lib/api-spec/openapi.yaml` is the source of truth for shared web API types;
  regenerate client code after modifying it. Never hand-edit generated files.
- Character identity fields must be available in the create request, saved
  campaign state, public character projection, and reveal UI.
- Verify with deterministic Python tests, workspace typechecking, and the
  running preview. Do not use live Ollama calls or long playable smoke runs
  as a substitute for unit tests.