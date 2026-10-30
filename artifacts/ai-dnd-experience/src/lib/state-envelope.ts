// One freshness gate for every response that wants to write the visible game state (R03).
//
// The server sends no state revision, so order is the order the page observed: a read is as old as the moment
// it was issued, a mutation reply as old as the moment it arrived. A response older than what the view already
// shows, or addressed to another owner, campaign or auth epoch, is refused and an authoritative refetch starts
// instead of trusting the stale copy. Abort alone is not the guard; a late callback is checked here too.
import { replaceEqualDeep } from "@tanstack/react-query";
import type { QueryClient, QueryKey } from "@tanstack/react-query";

export type ViewIdentity = { ownerId: string; campaignId: string; epoch: number; revision: number };
export type StateEnvelope<T> = ViewIdentity & { state: T };
type ViewScope = Omit<ViewIdentity, "revision">;

let clock = 0;
/** Order marker; take it before issuing a read, or when a mutation reply arrives. */
export function nextRevision(): number {
  clock += 1;
  return clock;
}

export function mayApplyState(current: ViewIdentity, incoming: ViewIdentity): boolean {
  return incoming.ownerId === current.ownerId
    && incoming.campaignId === current.campaignId
    && incoming.epoch === current.epoch
    && incoming.revision >= current.revision;
}

const views = new WeakMap<QueryClient, Map<string, ViewIdentity>>();
const readStamps = new WeakMap<object, ViewIdentity>();

function viewsOf(client: QueryClient): Map<string, ViewIdentity> {
  let known = views.get(client);
  if (!known) {
    known = new Map();
    views.set(client, known);
  }
  return known;
}

function refetch(client: QueryClient, key: QueryKey): void {
  void client.invalidateQueries({ queryKey: key });
}

/** The only writer of a game-state cache entry. Returns whether the state was applied. */
export function applyState<T>(
  client: QueryClient,
  key: QueryKey,
  scope: ViewScope,
  revision: number,
  state: T,
  options: { isCurrent?: () => boolean } = {},
): boolean {
  if (options.isCurrent && !options.isCurrent()) return false;
  const known = viewsOf(client);
  const slot = JSON.stringify(key);
  const incoming = { ...scope, revision };
  const current = known.get(slot);
  if (current && !mayApplyState(current, incoming)) {
    refetch(client, key);
    return false;
  }
  const before = client.getQueryState(key)?.dataUpdateCount;
  client.setQueryData(key, state);
  // The account client drops a write from an old auth epoch; the view must not claim a state that never landed.
  if (client.getQueryState(key)?.dataUpdateCount === before) return false;
  known.set(slot, incoming);
  return true;
}

/** Wraps a query fetch so its result carries the moment it was issued (read by the structural-sharing guard). */
export function gatedStateRead(scope: ViewScope) {
  return async <T extends object>(fetcher: () => Promise<T>): Promise<T> => {
    const revision = nextRevision();
    const state = await fetcher();
    readStamps.set(state, { ...scope, revision });
    return state;
  };
}

/** react-query's own fetches land through this hook; an older result keeps the newer cached state. */
export function stateStructuralSharing(client: QueryClient, key: QueryKey) {
  return <T>(oldData: T | undefined, newData: T): T => {
    const stamp = typeof newData === "object" && newData !== null ? readStamps.get(newData) : undefined;
    if (!stamp) return replaceEqualDeep(oldData, newData) as T;
    const known = viewsOf(client);
    const slot = JSON.stringify(key);
    const current = known.get(slot);
    // A different owner/session/epoch is an identity change, not an old reply: the page's own fresh read reseats the view
    // (refusing it would loop refetch -> refuse), but only when it is not older than what the view already shows: a fresh
    // read always carries a higher revision, so an older foreign-identity read can never reseat the view.
    const sameView = current && current.ownerId === stamp.ownerId && current.campaignId === stamp.campaignId && current.epoch === stamp.epoch;
    if (oldData !== undefined && current && (sameView ? !mayApplyState(current, stamp) : stamp.revision < current.revision)) {
      queueMicrotask(() => refetch(client, key));
      return oldData;
    }
    known.set(slot, stamp);
    return replaceEqualDeep(oldData, newData) as T;
  };
}
