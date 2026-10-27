// Binds the freshness gate to the page's own identity: signed-in owner, session and auth epoch.
// Every component that wants to change the visible game state calls applyGameState instead of writing the cache.
import type { QueryClient } from "@tanstack/react-query";
import { getGetGameSessionStateQueryKey } from "@workspace/api-client-react";
import { currentAuthEpoch } from "@workspace/api-client-react/custom-fetch";
import { currentAccountOwner } from "@/lib/account-session";
import { applyState, nextRevision } from "@/lib/state-envelope";

// Same fallback the pending-action slots use when no Clerk owner is resolved (local fixture).
const LOCAL_OWNER = "local";

// A session id belongs to exactly one campaign, and callers do not all know the campaign id, so the session names the view.
export function gameStateScope(sessionId: string) {
  return { ownerId: currentAccountOwner() ?? LOCAL_OWNER, campaignId: sessionId, epoch: currentAuthEpoch() };
}

export { nextRevision };

/**
 * `revision` is the marker taken before the read was issued; omit it for a mutation reply, which is as old as its arrival.
 */
export function applyGameState<T>(
  client: QueryClient,
  sessionId: string,
  state: T,
  options: { revision?: number; isCurrent?: () => boolean } = {},
): boolean {
  return applyState(
    client,
    getGetGameSessionStateQueryKey(sessionId),
    gameStateScope(sessionId),
    options.revision ?? nextRevision(),
    state,
    { isCurrent: options.isCurrent },
  );
}
