---
name: SSR context identity
description: Dependency identity across Vite SSR tests and externalized workspace hooks.
---

An SSR test provider and its consumers must use the same dependency instance.
Do not assume that a mounted provider proves this when mixing Vite-loaded modules
with externalized workspace libraries.

**Why:** A campaign-library SSR test reported a missing QueryClient despite a
mounted provider. Loading the provider through Vite while the generated workspace
hooks used the native package created distinct contexts; matching their module
loading fixed the test without changing application behavior.

**How to apply:** Check module/context identity before changing working app hooks
or adding another provider to resolve an SSR-only context error.