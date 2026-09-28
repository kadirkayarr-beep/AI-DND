---
name: Shared API routes across artifacts
description: Reuse sibling artifact services in one project without duplicating an API or engine process.
---

Within one Replit project, a web artifact can call a backend service route owned by a sibling artifact, and publishing the project includes its artifacts together. A frontend under a non-root preview path successfully reached the existing FastAPI service through its registered route.

**Why:** The frontend's base path can make a sibling API route look unreachable, but duplicating the route or starting another engine process can split in-memory game sessions.

**How to apply:** Verify the existing service route from the new artifact before changing routing. Reuse the canonical service; do not launch a second engine merely to create a frontend-prefixed route.