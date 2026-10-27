// One unresolved action per owner+campaign. A technical retry resumes the stored id; a deliberate new
// action mints a new id only after the previous one was confirmed or explicitly cancelled. Text is never
// consulted, and the auth epoch is recorded on the resumed action but is not part of the key.

export type ActionKey = { ownerId: string; campaignId: string; actionId: string };
export type PendingAction = { key: ActionKey; epoch: number };
export type CloseReason = "confirmed" | "cancelled";

const PENDING_PREFIX = "ai-dnd-pending-turns:action:";
const CLOSE_REASONS: readonly string[] = ["confirmed", "cancelled"];

// Used only when browser storage throws; storage stays the source of truth otherwise.
const memoryFallback = new Map<string, string>();

export class PendingActionError extends Error {}

function slot(ownerId: string, campaignId: string): string {
  if (!ownerId || !campaignId) throw new PendingActionError("pending action needs an owner and a campaign");
  return `${PENDING_PREFIX}${JSON.stringify([ownerId, campaignId])}`;
}

/** Sign-out and owner changes must not leave an old owner's pending move in memory either. */
export function clearPendingFallback(): void {
  memoryFallback.clear();
}

// Both sources are consulted, so a write that only reached memory (quota, blocked setItem) is still seen.
function read(storageKey: string): string | null {
  try {
    const stored = window.sessionStorage.getItem(storageKey);
    if (stored !== null) return stored;
  } catch {
    // Fall through to the in-memory copy.
  }
  return memoryFallback.get(storageKey) ?? null;
}

function write(storageKey: string, value: string): void {
  try {
    window.sessionStorage.setItem(storageKey, value);
    memoryFallback.delete(storageKey);
  } catch {
    memoryFallback.set(storageKey, value);
  }
}

function remove(storageKey: string): void {
  memoryFallback.delete(storageKey);
  try {
    window.sessionStorage.removeItem(storageKey);
  } catch {
    // The memory copy is already gone.
  }
}

function storedActionId(ownerId: string, campaignId: string): string | null {
  if (!ownerId || !campaignId) return null;
  const raw = read(slot(ownerId, campaignId));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as { actionId?: unknown };
    return typeof parsed.actionId === "string" ? parsed.actionId : null;
  } catch {
    return null;
  }
}

// The kind is bookkeeping about which flow owns the move; it is never part of the request body.
export type PendingKind = "play" | "death_wait";
export type StoredPending = { key: ActionKey; request: Record<string, unknown>; kind: PendingKind };

function storedPending(ownerId: string, campaignId: string): StoredPending | null {
  // Before a campaign or session exists (opening screen) there is nothing to read; only writes need both.
  if (!ownerId || !campaignId) return null;
  const raw = read(slot(ownerId, campaignId));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as { actionId?: unknown; request?: unknown; kind?: unknown };
    if (typeof parsed.actionId !== "string") return null;
    const request = parsed.request && typeof parsed.request === "object" ? parsed.request as Record<string, unknown> : {};
    const kind: PendingKind = parsed.kind === "death_wait" ? "death_wait" : "play";
    return { key: { ownerId, campaignId, actionId: parsed.actionId }, request, kind };
  } catch {
    return null;
  }
}

/** The unresolved action for this owner+campaign with its original request body, or null. */
export function readPending(ownerId: string, campaignId: string): StoredPending | null {
  return storedPending(ownerId, campaignId);
}

/** `request` is the original body (without the action id); a retry must send exactly this. */
// A species action keeps its own retry input here until the server result is reconciled (see
// species-trait-controls.tsx). It is a second pending owner, so other mutations must see it.
const SPECIES_RETRY_PREFIX = "ai-dnd-turn-context:species:";

/** True while a species action for this campaign was sent but not yet confirmed. */
export function speciesActionUnresolved(campaignScope: string): boolean {
  if (!campaignScope) return false;
  return read(`${SPECIES_RETRY_PREFIX}${campaignScope}:retry`) !== null;
}

/**
 * Which unresolved mutation of this campaign should stop another one. Children that cannot see GameBrowser
 * state (death-wait, quest commands) use this; the ambient action lives only in GameBrowser state.
 */
export function unresolvedElsewhere(ownerId: string, campaignScope: string): "play" | "species" | null {
  if (storedActionId(ownerId, campaignScope)) return "play";
  return speciesActionUnresolved(campaignScope) ? "species" : null;
}

export function createIntentKey(
  ownerId: string,
  campaignId: string,
  request: Record<string, unknown> = {},
  kind: PendingKind = "play",
): ActionKey {
  if (storedActionId(ownerId, campaignId)) {
    throw new PendingActionError("an earlier action is still pending; retry it or cancel it first");
  }
  if (!window.crypto?.randomUUID) throw new PendingActionError("Secure UUID generation is unavailable.");
  const key = { ownerId, campaignId, actionId: window.crypto.randomUUID() };
  write(slot(ownerId, campaignId), JSON.stringify({ actionId: key.actionId, request, kind }));
  return key;
}

export function resumePending(key: ActionKey, epoch: number): PendingAction {
  if (storedActionId(key.ownerId, key.campaignId) !== key.actionId) {
    throw new PendingActionError("no pending action for this owner, campaign and id");
  }
  return { key: { ownerId: key.ownerId, campaignId: key.campaignId, actionId: key.actionId }, epoch };
}

// Only an answer that proves nothing was committed may cancel: the server refused the request before
// processing it. A timeout, a lost connection or a closed waiting screen prove nothing.
// Two proofs only: the server's own "not_applied" contract (a refusal it remembers under the turn lock, so
// the action can never be applied later), or a body the schema rejects (422 happens before the handler and
// the same body is invalid forever). A bare 400/404/409/500 proves nothing.
const HTTP_UNPROCESSABLE = 422;
export type CancelEvidence =
  | { kind: "server_not_applied"; code: string }
  | { kind: "server_rejected"; status: number };

function provesNothingWasCommitted(evidence: CancelEvidence | undefined): boolean {
  if (evidence?.kind === "server_not_applied") return Boolean(evidence.code);
  return evidence?.kind === "server_rejected" && evidence.status === HTTP_UNPROCESSABLE;
}

export function closePending(
  key: ActionKey,
  reason: CloseReason | undefined,
  evidence?: CancelEvidence,
): void {
  if (!reason || !CLOSE_REASONS.includes(reason)) {
    throw new PendingActionError("pending closes only on a confirmed result or a proven cancel");
  }
  if (reason === "cancelled" && !provesNothingWasCommitted(evidence)) {
    throw new PendingActionError("cancelling needs proof that the server did not commit the action");
  }
  if (storedActionId(key.ownerId, key.campaignId) !== key.actionId) return;
  remove(slot(key.ownerId, key.campaignId));
}
