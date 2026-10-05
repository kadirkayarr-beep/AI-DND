---
name: Development HTTP certificate trust
description: Preserve TLS verification when Python httpx cannot trust the development proxy certificate.
---

Use the operating system trust store for development HTTP probes when the default httpx certificate bundle fails while urllib succeeds.

**Why:** The same development API was reachable through urllib but httpx raised CERTIFICATE_VERIFY_FAILED because its default bundle lacked the local issuer. Passing ssl.create_default_context() preserved verification and made the real HTTP probe work.

**How to apply:** Compare the two clients before diagnosing an application/network failure. Supply the system SSL context to a test-local client; do not disable TLS verification, change production client behavior, or expose secret values.