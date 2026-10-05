---
name: Ollama live verification
description: Replit proxy authentication and safe interpretation of Turkish game smoke runs.
---

When a live test uses the Replit Ollama proxy, the Python Ollama client must be configured with the host and an `Authorization: Bearer` header sourced from environment secrets. The module-level `ollama.chat` does not attach the project-specific proxy token by itself; route a test-local client through it rather than changing production behavior for a smoke run. Never print host/token values or raw headers.

Historical model traces can differ in generated prose and fallback count even when they use the same source hash. Treat them as evidence of past runs, not as verification of the current engine; record current-engine behavior separately and enforce the per-turn model-call ceiling.

**Why:** A live request succeeded only after supplying the proxy authorization header, and repeated nine-turn runs of the same model flow produced different fallback counts.

**How to apply:** For future live checks, make the authenticated client explicit, keep state in a disposable `GameSession`, and report only sanitized per-turn outcomes, call counts, and fallback totals.

A successful Ollama preflight from a user's Windows or other machine does not verify the Replit workspace's own bearer secret. The workspace smoke must authenticate successfully from the environment where it runs.

**Why:** A Windows preflight succeeded while the Replit workspace still received HTTP 401 until its `OLLAMA_PROXY_TOKEN` secret was refreshed.

**How to apply:** After external connectivity is restored, run the authenticated preflight from Replit. If it returns 401, refresh the Replit secret through the secure Secrets flow; never request or copy the token in chat.

For FastAPI workflow checks, custom INFO loggers need their own stream handler to make sanitized model-call counts visible in workflow output. A successful HTTP response alone does not prove the model was called.

**Why:** Uvicorn's workflow showed access logs but suppressed the adapter's model-call records until the API loggers wrote directly to the workflow stream.

**How to apply:** Record the configured model and per-turn call count server-side, then inspect workflow logs after the real HTTP smoke. Do not expose these diagnostics in client responses.

Schema compliance and HTTP success are not semantic acceptance. Require the
expected authoritative state change for each live intent, including populated
plan steps rather than an immersive clarification.

**Why:** Fixture packets accepted a complex plan while real Qwen returned empty
steps. Requiring its operation/envelope improved goals and promises, but prompt
and schema adjustments alone did not establish successful live plan handling.

**How to apply:** Report fixture coverage and native model coverage separately.
Keep failed source-span/dependency validation fail-closed; do not weaken checks,
substitute a fabricated plan or call a safe fallback a successful interpretation.

Check every economy operation's canonical movement and payment independently;
HTTP 200 plus unchanged replay can also describe an authoritative rejection.

**Why:** A live verifier initially reported passing merchant trading while both
sales had actually been rejected. Receipt correctness did not prove the first
operation succeeded. A normal custom character also exposed a hand-label
compatibility problem that the default-character flow had not revealed.

**How to apply:** Require same-instance source/destination ownership changes and
the expected wallet delta for each sale/purchase, alongside replay assertions.
Include the normal character-creation path in live acceptance. Preserve an
incorrect original verifier result, explicitly disqualify it, and retain the
new corrected run rather than silently rewriting the old report.