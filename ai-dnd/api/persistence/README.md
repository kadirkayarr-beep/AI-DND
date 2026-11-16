# Persistent Campaign

This file began as the V1 description. The sections below are updated to the
current code: `campaign_store.py` (registry), `api/main.py` (routes) and
`game.py` (engine save). Where this text and the code differ, the code wins.

Campaigns use the existing `ai-dnd-save` engine snapshot (`game.py` `_SUPPORTED_SAVE_VERSIONS` lists the
accepted versions) as their
canonical game state. SQLite wraps that snapshot with a campaign envelope that
stores the session-local Python RNG state. Campaign metadata and turn history
are stored separately; history contains only player messages, returned
narration, and server timestamps, not model prompts or `GameSession.messages`.

The API server opens its registry through `StartupCampaignStore`, which needs
`AI_DND_CAMPAIGN_DB` and fails closed when it is missing or empty (a relative
path resolves against the process working directory, because `CampaignStore`
resolves the path it is given). `ai-dnd/saves/campaigns.sqlite3` is only the
fallback of `default_campaign_db_path()` when a `CampaignStore` is built without
a path (only that function resolves a relative path next to `game.py`); the API does not use it. `start_local.ps1 -LocalPlay` sets the variable
to `%LOCALAPPDATA%\AI-DND\local-play.sqlite3` when it is unset. An older
registry schema is migrated only with `AI_DND_ALLOW_SCHEMA_MIGRATION=1`. SQLite transactions and WAL mode
protect updates; a turn's canonical save and history entry commit together.
If validation or the transaction fails, the API restores the in-memory turn
snapshot and keeps the last committed save.

Campaigns are owned. Each registry row stores an owner (issuer and subject)
from the authenticated principal, and every read, save and delete matches the
caller's owner. A request without a principal is rejected
(`AuthenticationError`). Campaign UUIDs are opaque locators and are also not
access controls on their own. Keep this deployment to one active API
instance for a campaign at a time; the live `GameSession` remains
process-local. Multi-instance coordination and sharing between owners
are out of scope.

`DELETE /api/game/campaigns/{campaign_id}` (also under `/api/campaigns/...`)
deletes one campaign owned by the caller; its history and receipts are removed
with it by foreign-key cascade, and it cannot be undone. The engine's supported save
version remains authoritative; unsupported campaign or engine versions are
rejected without loading partial state. No historical campaign migration was
needed for the initial V1 registry; later registry schema changes are
migrated only as described above.