# AI-DND — Replit Integration and API Security Handoff (2026-10-12)

## Authority and release constraints

This is an implementation handoff, **not** production certification. Python alone owns canonical game state and mechanics; lore sources own setting reality; accepted campaign events own campaign canon. Qwen may only narrate verified results (max two model calls per player turn, deterministic rejection fallback). The browser is a presentation client. Preserve all legacy saves and session isolation. No force push, branch merge, or production publish.

## API client contract: local fix verified

- Source: `lib/api-spec/openapi.yaml` (31 HTTP method/path pairs, paths relative to `/api`).
- Generator: `lib/api-spec/orval.config.ts`, Orval 8.30.0.
- Outputs: `lib/api-client-react/src/generated` and `lib/api-zod/src/generated`.
- Build dependency: frontend TypeScript references `lib/api-client-react` composite project and its `dist` declarations. **Regenerating `src` alone is not enough; rebuild the library declarations.**
- Before: frontend TypeScript reported 157 error lines (missing API fields/operations and downstream type errors).
- After: Orval regenerated successfully; `tsc --build` for workspace libraries succeeded; frontend `tsc -p tsconfig.json --noEmit` returned 0 errors / exit 0.
- The 31 source contract routes were compared with an isolated FastAPI `create_app(..., ollama_adapter=None)`: 31/31 method/path pairs matched after applying the intended `/api` prefix.
- Frontend Node test suite: 72/72 passed; Vite build succeeded (bundle-size warning only).
- Focused isolated Python API/model-boundary regression: 88/88 passed (exit code 0).
- Guard: `artifacts/ai-dnd-experience/tests/api-contract-freshness.test.mjs` checks key generated API projections and campaign delete hook.
- Generated files changed in bulk (122 tracked paths in client and Zod sources). This is expected generator output; review before commit. Never hand-edit generated output.
- Windows note: `pnpm run typecheck:libs` emitted a dependency preinstall warning because `sh` was not available, but its underlying `tsc --build` step succeeded. Replit/Linux should run the declared pipeline directly and verify exit status.

## P0: current anonymous campaign API exposure

`ai-dnd/scripts/security_gate.py` constructs a fresh, temporary SQLite store and an isolated ASGI app. It does not read production databases or call a live network endpoint. Its result:

- Anonymous `GET /api/game/campaigns`: HTTP 200.
- Anonymous `GET /api/game/campaigns/{campaign_id}`: HTTP 200.
- Anonymous `DELETE /api/game/campaigns/{campaign_id}`: HTTP 200.
- Exit code: **1 (FAIL / release_ready=false)**.

Replit app lookup succeeded; publish status returned `found=false`. This does **not** prove development previews are protected.

### Safe implementation requirements for Replit runtime authority

1. Verify which Replit identity/auth mechanism is actually enabled and trusted at the server boundary. Do not assume client-supplied headers are authenticated. Do not embed a shared API secret in browser JavaScript.
2. Implement verified server-side principal identity and an owner/ACL mapping for campaigns and active sessions. Protect create/list/read/resume/save/delete and all state-mutating session endpoints, including both `/api` and `/api/game` aliases. Public health and static catalogs can remain anonymous if explicitly intended.
3. For cookie sessions, enforce appropriate CSRF protection, `HttpOnly`, `Secure`, and `SameSite` settings; reject forged or missing credentials. For token auth, verify signature, issuer, audience, expiry and intended scope server-side.
4. **Legacy campaigns with no owner must not be silently claimed by the first visitor.** Design a restricted administrative claim/migration path and validate that old SQLite records remain loadable. Avoid destructive schema rewrites or broad migration until tested on a copy.
5. Return a consistent authorization failure that does not reveal whether another user's campaign exists. Do not leak campaign IDs, world state, history, or session secrets.
6. Add isolated two-user tests: unauthenticated requests denied; user A cannot list/read/resume/save/delete or mutate user B's campaigns/sessions; authorized owner succeeds; session restart and old-save compatibility pass.
7. Re-run `scripts/security_gate.py` in the secured configuration and require exit 0. Keep this as a release blocker, not a cosmetic warning. Verify the real Replit preview/proxy identity boundary separately, without using live save records as test fixtures.

## Next integration gate

After security and schema are verified in the Replit runtime, use **temporary test campaigns only** to exercise actual Qwen + FastAPI + SQLite + browser flows, then the 24-turn GOLD-SYSTEM/GOLD-EXPERIENCE acceptance matrix. No production publication until security gate, frontend build, relevant regression suites, session isolation, save compatibility, and real model call-budget checks all have explicit evidence.
