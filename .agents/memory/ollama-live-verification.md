---
name: Ollama live verification
description: Replit proxy authentication and safe interpretation of Turkish game smoke runs.
---

When a live test uses the Replit Ollama proxy, the Python Ollama client must be configured with the host and an `Authorization: Bearer` header sourced from environment secrets. The module-level `ollama.chat` does not attach the project-specific proxy token by itself; route a test-local client through it rather than changing production behavior for a smoke run. Never print host/token values or raw headers.

Historical model traces can differ in generated prose and fallback count even when they use the same source hash. Treat them as evidence of past runs, not as verification of the current engine; record current-engine behavior separately and enforce the per-turn model-call ceiling.

**Why:** A live request succeeded only after supplying the proxy authorization header, and repeated nine-turn runs of the same model flow produced different fallback counts.

**How to apply:** For future live checks, make the authenticated client explicit, keep state in a disposable `GameSession`, and report only sanitized per-turn outcomes, call counts, and fallback totals.