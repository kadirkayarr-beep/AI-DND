---
name: Private preview and Clerk transport
description: Keep Replit private-preview access separate from the AI-DND Python API's Clerk Bearer identity.
---

For the isolated AI-DND Experience preview, the Replit private-preview session and the app's Clerk identity are separate authentication layers. Same-origin protected browser requests need to carry the Replit session to the preview gateway, while Python continues to authenticate only the Clerk Bearer token. The Experience Vite proxy must remove cookies before forwarding requests to Python.

**Why:** Private development URLs are gated before Vite; omitting browser credentials causes Replit to redirect to its login flow, and a Clerk JWT is not a Replit external-access token. Forwarding preview cookies to the API is unnecessary and increases credential exposure.

**How to apply:** Keep the shared API client's protected-request credential mode defaulting to `omit`; opt in only from the isolated Experience auth boundary, strip cookies in that artifact's `/api` proxy, and leave Python's issuer+subject verification unchanged. Do not use a Clerk JWT as Replit preview authorization.
