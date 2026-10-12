# AI-DND — Incremental Repair Audit (2026-10-12)

**Scope:** local working tree on `dev/ai-dnd` at `8aa19fa`; no commit, merge, push, live Replit deployment, or production save mutation. The fixes below are proposed working-tree changes, not production certification.

## Architectural invariants

- Python alone resolves mechanics, campaign state, rewards, and persistence.
- Official 2024 D&D rulebooks and current Forgotten Realms sources retain their separate reference authorities; no setting canon is created by tests.
- Qwen may understand intent and narrate verified results, but does not author game truth.
- Maximum two model calls per player turn; rejected narration falls back deterministically.
- Existing save shapes and isolated sessions are preserved.

## Applied and locally verified

1. **Adventure objectives:** `interaction_adventure.py` now reads the existing equipment owner's item labels and Python-resolved combat status/HP. A newly acquired instance item or newly defeated NPC can progress an eligible objective. Already-defeated targets do not count again. Legacy string inventories remain readable. New test: `api/tests/test_adventure_objective_evidence_regression.py`.
2. **Sword drop routing:** `game.py` resolves four explicit present-tense sword-drop paraphrases before abstract adventure-abandon proposals. This is deliberately narrow, not a general-purpose natural-language item engine. Resolved inventory transfers bypass model narration to prevent a contradictory reversal. New test: `api/tests/test_inventory_intent_regression.py`.
3. **XP receipts:** `xp.py` hashes overlong server-authored combat reward IDs using SHA-256, preserving short legacy IDs; receipt capacity is now bounded at 10,000 rather than 500. New test: `api/tests/test_xp_receipt_regression.py`. **Limitation:** the 10,000 receipt bound still needs a long-horizon storage/retention design; this is not infinite replay protection.
4. **Combat presentation:** `game-browser.tsx` retains a selected living combat target across turns and clears stale/ended targets. Known Python combat error codes map to specific Turkish player guidance, without displaying arbitrary server error strings. New `src/lib/combat-ui-contract.ts` and `tests/combat-ui-contract.test.mjs`.
5. **Local development exposure:** `vite.config.ts` and package scripts bind local Vite/preview to `127.0.0.1`, no longer use `allowedHosts: true`, and preserve Replit's required public listener with explicit hostnames. New `tests/vite-exposure.test.mjs`. **Limitation:** this does NOT authenticate a publicly reachable campaign API.
6. **Compound NPC introduction:** `local_dialogue.py` recognizes a clearly delimited, capitalized `Ben Astrid.` introduction followed by a question. `game.py` acknowledges that disclosure and answers the NPC identity question in the same turn using verified Python fields, without leaking memory to another NPC. New `api/tests/test_npc_compound_dialogue_regression.py`.
7. **Offline audit harness:** `scripts/gameplay_audit.py` runs five isolated item-action paraphrase cases and compares action routing, before/after inventory, ground items, narration, and model-call budget. JSON output only; no real Qwen or SQLite. New `api/tests/test_gameplay_audit_harness.py`.

## Test interpretation

- Focused Python regressions passed during implementation, including tests first observed failing before their fixes.
- Frontend Node tests passed; a standalone TypeScript check for the new combat UI helper passed.
- Initial frontend TypeScript check had 157 error lines from stale generated API declarations. The subsequent local Orval regeneration and library rebuild fixed them: **0 TypeScript errors**, and the Vite build passed. Replit runtime validation remains outstanding.
- No real-Qwen 24-turn GOLD-EXPERIENCE acceptance test has been performed.

## Unresolved priorities (do not mark complete)

**P0 — Public API authorization.** A reachable FastAPI instance still exposes campaign list/read/delete without account/session authorization. Local loopback containment is not a substitute for deployed access control. Before any public Replit deployment, design and test real user ownership, protected routes, and migration-safe session access. Do not expose live saves.

**P1 — Replit integration of regenerated client.** Local Orval regeneration, declaration rebuild, and TypeScript checks now pass. Validate the same source and generation pipeline in Replit; do not hand-edit generated client files.

**P1 — Travel encounters.** Text-only travel encounters may not produce targetable persistent NPC entities. Resolve through existing living-world/incident ownership and source authority, with replay and save tests. Do not fabricate NPC identities in narration or frontend.

**P1 — Broader multi-intent NPC conversation.** Only a narrow combined introduction/identity path is repaired. Questions involving several independently grounded facts, offers, promises, or lore require wider acceptance tests and appropriate authority separation.

**P1 — Long-campaign XP storage.** The 10,000 receipt cap is bounded and preserves old saves, but needs a deliberate long-term deduplication/persistence policy.

**P1 — Narrative audit expansion.** Extend the offline harness beyond five item actions to combat, travel, NPC memory, quest objectives, reload/replay, and cross-session isolation; then run a real-Qwen, 24-turn GOLD-SYSTEM and GOLD-EXPERIENCE acceptance plan. Never add model calls to gameplay turns.

**P2 — Living world and atmosphere.** Expand only after mechanics/intent/security contracts are reliable. UI must present verified environment/time/weather/combat facts without creating game state.

## Integration update — API client regeneration

The OpenAPI source contract in `lib/api-spec/openapi.yaml` was already newer than the generated TypeScript client. Regenerated client and Zod types with Orval and rebuilt library declarations. Frontend TypeScript changed from 157 error lines to **0** (exit code 0). Source contract and isolated FastAPI routes match **31/31** method/path pairs. Node frontend tests passed **72/72**; Vite build passed with a bundle-size warning. The earlier TypeScript-drift finding is now fixed **locally**, pending Replit verification.

New regression: `artifacts/ai-dnd-experience/tests/api-contract-freshness.test.mjs`. Generated client/Zod changes affect 122 tracked files; review generator output before any commit.

Security remains **P0 and blocked**: `ai-dnd/scripts/security_gate.py` confirmed HTTP 200 for anonymous list/read/delete in an isolated temporary database, and exits 1 to prevent accidental release certification. The Replit app was found but its publish status is `found=false`. No deployment was performed. See `docs/REPLIT_AUTH_AND_API_CONTRACT_HANDOFF_2026-10-12.md` for the implementation and migration requirements.

## Integration handoff

1. Review the local diff and untracked regression files; no changes have been committed.
2. Replit integration should verify current FastAPI, SQLite, real Qwen, generated API client, and browser with temporary campaigns before touching any historical saves.
3. Run focused tests, full relevant suites, and 24-turn acceptance with explicit pass/fail evidence.
4. Do not merge, force-push, or certify production without a separate explicit deployment/release decision.
