import { QueryClient } from "@tanstack/react-query";
import {
  ApiRequestError,
  currentAuthEpoch,
  rotateAuthEpoch,
} from "@workspace/api-client-react/custom-fetch";

const ACCOUNT_OWNER_KEY = "ai-dnd-account-owner";
const ACCOUNT_STORAGE_KEYS = ["ai-dnd-last-selected-campaign-id"];
const ACCOUNT_STORAGE_PREFIXES = [
  "ai-dnd-transcript-",
  "ai-dnd-pending-turns:",
  "ai-dnd-turn-context:",
];

type KeyedStorage = {
  readonly length: number;
  key(index: number): string | null;
  removeItem(key: string): void;
};

export type ClerkSessionSnapshot = {
  isLoaded: boolean;
  isSignedIn?: boolean;
  userId?: string | null;
  sessionId?: string | null;
};

export type AccountBoundary = {
  identity: string;
  client: QueryClient;
};

export function clerkSessionIdentity(auth: ClerkSessionSnapshot): string {
  if (!auth.isLoaded || auth.isSignedIn !== true) return "";
  if (!auth.userId || !auth.sessionId) return "";
  return `${auth.userId}:${auth.sessionId}`;
}

export function isAccountScopedStorageKey(key: string): boolean {
  return ACCOUNT_STORAGE_KEYS.includes(key)
    || ACCOUNT_STORAGE_PREFIXES.some((prefix) => key.startsWith(prefix));
}

export function clearAccountStorage(storage: KeyedStorage): void {
  const keys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key && isAccountScopedStorageKey(key)) keys.push(key);
  }
  for (const key of keys) storage.removeItem(key);
}

export function clearAccountBrowserState(): void {
  if (typeof window === "undefined") return;
  try {
    clearAccountStorage(window.localStorage);
    clearAccountStorage(window.sessionStorage);
    window.localStorage.removeItem(ACCOUNT_OWNER_KEY);
  } catch {
    // Storage can be unavailable. The signed-in screen still uses a fresh cache.
  }
}

export type OwnerTransition = "unresolved" | "same" | "changed";

/** Stored data with no recorded owner (previous null) is never "same": it cannot be verified. */
export function classifyOwnerTransition(
  previous: string | null,
  resolved: string | null,
): OwnerTransition {
  if (!resolved) return "unresolved";
  return previous === resolved ? "same" : "changed";
}

/** The account owner is the Clerk user; a new session of the same user is not a new owner. */
function ownerOfIdentity(identity: string): string | null {
  const owner = identity.split(":")[0];
  return owner ? owner : null;
}

function readStoredOwner(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(ACCOUNT_OWNER_KEY);
  } catch {
    return null;
  }
}

function writeStoredOwner(owner: string): void {
  try {
    window.localStorage.setItem(ACCOUNT_OWNER_KEY, owner);
  } catch {
    // Without a record the next mount cannot verify the owner and clears instead of recovering.
  }
}

function isAuthenticationFailure(error: unknown): boolean {
  if (error instanceof ApiRequestError) return true;
  if (!error || typeof error !== "object") return false;
  return (error as { status?: unknown }).status === 401;
}

export function createAccountQueryClient(): QueryClient {
  const epoch = currentAuthEpoch();
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => !isAuthenticationFailure(error) && failureCount < 3,
      },
      mutations: {
        retry: false,
      },
    },
  });
  const write = client.setQueryData.bind(client);
  client.setQueryData = ((...args: Parameters<QueryClient["setQueryData"]>) => {
    if (currentAuthEpoch() !== epoch) return undefined;
    return write(...args);
  }) as QueryClient["setQueryData"];
  return client;
}

export function nextAccountClient(
  previous: AccountBoundary | null,
  identity: string,
): AccountBoundary {
  if (previous?.identity === identity) return previous;
  if (previous) {
    rotateAuthEpoch();
    void previous.client.cancelQueries();
    previous.client.clear();
  }
  const resolved = ownerOfIdentity(identity);
  const before = previous ? ownerOfIdentity(previous.identity) : readStoredOwner();
  // An unresolved identity neither clears nor claims stored data; the gate keeps it hidden.
  if (classifyOwnerTransition(before, resolved) === "changed" && resolved) {
    clearAccountBrowserState();
    writeStoredOwner(resolved);
  }
  return { identity, client: createAccountQueryClient() };
}

export function accountWriteAllowed(epoch: number): boolean {
  return epoch === currentAuthEpoch();
}

export async function readClerkToken(
  getToken: () => Promise<string | null>,
  stillCurrent: () => boolean,
): Promise<string | null> {
  if (!stillCurrent()) return null;
  try {
    const token = await getToken();
    if (!stillCurrent()) return null;
    if (typeof token !== "string") return null;
    if (token.length < 1 || token.length > 8192 || /\s/.test(token)) return null;
    return token;
  } catch {
    return null;
  }
}
