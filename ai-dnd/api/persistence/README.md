# Persistent Campaign V1

Campaigns use the existing `ai-dnd-save` version 1 engine snapshot as their
canonical game state. SQLite wraps that snapshot with a campaign envelope that
stores the session-local Python RNG state. Campaign metadata and turn history
are stored separately; history contains only player messages, returned
narration, and server timestamps, not model prompts or `GameSession.messages`.

The default registry is `ai-dnd/saves/campaigns.sqlite3`. Set
`AI_DND_CAMPAIGN_DB` to use another path. SQLite transactions and WAL mode
protect updates; a turn's canonical save and history entry commit together.
If validation or the transaction fails, the API restores the in-memory turn
snapshot and keeps the last committed save.

V1 is a single-user development feature, not an account or authorization
system. Campaign UUIDs are opaque locators, not access controls. Anyone who can
reach the API can access campaigns. Keep this deployment to one active API
instance for a campaign at a time; the live `GameSession` remains
process-local. Account ownership, multi-instance coordination, and sharing
are out of scope.

There is no campaign-delete endpoint in V1. The engine's supported save
version remains authoritative; unsupported campaign or engine versions are
rejected without loading partial state. No historical campaign migration was
needed for the initial V1 registry.