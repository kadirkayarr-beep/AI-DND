---
name: Large source transport
description: Preserve complete file contents when generating source through programmatic shell calls.
---

Do not use large shell stdout as the authoritative contents for a whole-file write. Generate into a temporary file, then read it with an explicit byte budget and validate the complete contents.

**Why:** A programmatic shell call returned only the tail of generated source even though its truncation flag was false. The source was restored from the complete temporary copy.

**How to apply:** For large generated text, use file-backed transport, check parsing and preservation before writing, and do not treat a successful shell exit as proof that all stdout was delivered.
