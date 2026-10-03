---
name: Shared API routes across artifacts
description: Reuse sibling artifact services in one project without duplicating an API or engine process.
---

Within one Replit project, a web artifact can call a backend service route owned by a sibling artifact, and publishing the project includes its artifacts together. A frontend under a non-root preview path successfully reached the existing FastAPI service through its registered route. The API service's `paths` list must cover every frontend API route; an endpoint can work on FastAPI's port yet return 502 through the proxy when its path is unregistered.

**Why:** The frontend's base path can make a sibling API route look unreachable, while unregistered API paths fall through to another service. Duplicating the route or starting another engine process can split in-memory game sessions.

**How to apply:** Verify each frontend API route through the preview proxy, then confirm it is covered by the canonical backend service's `paths`. Update artifact TOML through its validation flow when needed. Do not prepend the frontend artifact base path to API routes or launch a second engine to create a new route.