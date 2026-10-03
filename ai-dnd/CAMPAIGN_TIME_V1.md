# Campaign Time V1 conventions

- Python owns a Harptos calendar anchored once at the first registered scene.
  Canonical `canonical_start_time` (year/month/day/hour/minute) is preserved if
  supplied by server world metadata. Otherwise: **1 Mirtul 1501 DR, 09:00,
  Neverwinter local**. Festivals and four-year Shieldmeet are calendar days.
  This local-world convention has no UTC offset or connection to computer time.
- `world_state` contains the clock, scheduled events, bounded active task, and
  journey. Existing campaign transactions and action receipts persist all of them;
  there is no separate clock store, timer, migration system, or advance-time API.
- Windows are half-open: `[start, end)`, in seconds relative to campaign start.
  A public, explicit local look/arrival can establish occurrence inside a window.
  Otherwise a pending event commits fixed world effects at window close. Failed
  prerequisites expire it. Long actions are never cut retroactively. Aftermath
  is learned only through a later local observation, not merely by elapsed time.
- Scheduled definitions are server-owned and the production queue starts empty.
  Supports registered NPC relocation, namespaced boolean world flags, and the
  fixed edge-case effects `npc_hostility` and `route_block` (registered endpoints,
  boolean blocked state). Hostility never automatically starts combat.
  No Qwen-authored event scripts, NPC simulation, damage, or quest scheduling.
- Bounded research is a finite examination of a registered feature/current scene:
  default six minutes per pass, overridden only by server `search_duration_seconds`.
  This is not a general per-message cost or a DC-to-minutes formula. A player
  duration is a budget; unfinished passes persist. A server `search_dc` enables
  the existing Investigation resolver; otherwise there is no unnecessary roll.
  Results come from server `search_result` or explicit no-new-finding text.
  Optional DCs use the current public core tiers (10/15/20/25/30), independently
  of duration. A paused journey does not permit searching its remote origin scene.
- Server `travel_routes[destination]` defines a list of stage durations in seconds.
  Registered places in the same local anchor/region use a five-minute pedestrian
  stage. Unknown cross-region routes are refused rather than assigned fictional
  distances. V1 is not a continental travel simulation.
- Each stage checks travel dice once at its midpoint: d6 occurrence (1–2 event,
  3–6 no event), d6 catalog type, d6 disposition (paired calm/cautious/difficult).
  Only occurrence is rolled for no-event. Consecutive pattern repetition is
  reduced with the last pattern excluded when alternatives exist, never blacklisted
  permanently. The finite catalog contains noncombat traveler/wagon/crossing
  encounters. Encounter pauses remaining travel; continue/stop/return/new
  registered destination are explicit player choices. No automatic damage/combat.
  Return and reroute retrace already traveled duration to the last registered
  anchor; V1 never invents unregistered mid-route shortcuts.
- Short/long rest defaults are one/eight hours. Explicit valid rest durations are
  preserved; sleeping until morning uses next 07:00, and an eight-hour-or-longer
  sleep can complete the existing long rest. No postcombat rest or Stable skip.
- A completed initiative wrap adds six seconds. Partial rounds keep existing
  scheduler behavior. Normal death restores the world checkpoint (clock, queue,
  tasks, journey), **not RNG or action receipts**. Technical API failure restores
  the entire pre-request snapshot, including RNG.
- New current-format saves are validated; missing clock fields in old fixtures
  are not migrated during loading. The next real registered scene initializes once.

## Edge-case hardening

- Existing event/receipt architecture remains authoritative. Optional event fields
  preserve the original V1 save shape; there is no parallel scheduler or ledger.
- Bulk resolution uses causal readiness first. Within ready candidates it uses
  chronological boundary, explicit priority (higher first), causal group, location,
  and stable event ID. Each consequence is evaluated against preceding consequences.
  Dependency-delayed events cannot resolve before their dependencies.
- `dependencies` refer to canonical event IDs. `followups` are at most 16 fixed
  server-owned definitions per parent, without recursively nested followups; the
  full queue is at most 256 events. Spawned definitions automatically depend on the
  parent. Cycles/missing dependencies and their descendants remain unchanged,
  receive a private `scheduled_event_diagnostics` record, and produce a bounded
  warning. Hidden event IDs are not sent to the client or model.
- `decision_status` distinguishes no interaction, pending choice, combat handoff,
  and resolved player choice from world occurrence and knowledge. Pending choices
  survive window close and save/resume. Learning aftermath preserves a missed
  encounter; it does not retroactively turn it into an on-time encounter.
- Ordinary `INTERRUPTIVE` events do not split long actions. Only a public,
  directly relevant `requires_decision` interaction or `FORCED` obstacle may stop
  actual progress. A stationary location is not assumed to be the player's travel
  position: in-route relevance requires explicit `route_destination`. The start
  of an active window is the deterministic availability checkpoint, not a randomly
  invented occurrence minute. Events elsewhere still resolve without forced choices.
- Stops retain actual task/travel/retrace progress and requested/remaining seconds.
  Independent consequences at the stop timestamp still resolve; later consequences
  wait for future gameplay. Rest resources/healing apply only after completed rest.
  Calendar-based weeks/months mean 7/30 Harptos days, not Gregorian dates.
- A pending choice never advances time by itself. Avoidable continue/talk/stop and
  valid return/reroute are explicit player intents. Forced obstacles cannot simply
  be ignored. Multiple known pending encounters can be selected by their displayed
  summary; UI command context is separated from the actual player decision.
- An optional registered `combat_npc_id` only hands an explicit fight choice to
  existing combat initialization. Initiative, damage, death and escape remain combat
  owned. Combat exit restores the pending decision, not automatic action continuation.
- Hidden aftermath requires explicit server `aftermath_visible` permission and a
  real local observation. Clock passage alone never expands player knowledge.