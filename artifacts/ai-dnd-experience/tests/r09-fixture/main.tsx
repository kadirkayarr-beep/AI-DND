/**
 * Disposable page for the R09 chain check. It mounts the REAL GameBrowser inside the real account-boundary helpers
 * (nextAccountClient / createAccountQueryClient, the same ones ClerkApiSession uses) and does NOT replace fetch: every
 * request goes through the Vite proxy to the temporary Python backend started by tests/roadmap-r09.test.mjs.
 * The identity here is a FIXTURE identity (the backend runs FixedAuthenticator); it is NOT Clerk and never claims to be.
 */
import { useState } from "react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { getGetGameSessionStateQueryKey } from "@workspace/api-client-react";
import { setAuthTokenGetter } from "@workspace/api-client-react/custom-fetch";
import GameBrowser from "@/pages/game-browser";
import { nextAccountClient, type AccountBoundary } from "@/lib/account-session";
import "@/index.css";

const params = new URLSearchParams(window.location.search);
const campaignId = params.get("campaign") ?? "";
const sessionOf = () => (window as unknown as { __r09Session?: string }).__r09Session ?? "";

let boundary: AccountBoundary | null = null;
let rerender: (identity: string) => void = () => {};

function View() {
  const [identity, setIdentity] = useState("owner-a:session-1");
  rerender = setIdentity;
  if (boundary?.identity !== identity) boundary = nextAccountClient(boundary, identity);
  return (
    <QueryClientProvider client={boundary!.client}>
      <div key={identity} style={{ display: "contents" }}><GameBrowser /></div>
    </QueryClientProvider>
  );
}

async function openPlay() {
  const clickWhen = async (selector: string) => {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const node = document.querySelector<HTMLButtonElement>(selector);
      if (node && !node.disabled) { node.click(); return; }
      await new Promise((resolve) => window.setTimeout(resolve, 100));
    }
    throw new Error(`R09 fixture could not find ${selector}`);
  };
  await clickWhen('[data-testid="button-continue-session"]');
  await clickWhen(`[data-testid="button-resume-${campaignId}"]`);
}

const cached = () => {
  const client = boundary?.client as QueryClient | undefined;
  const sessionId = sessionOf();
  if (!client || !sessionId) return null;
  const data = client.getQueryData(getGetGameSessionStateQueryKey(sessionId)) as { turn_index?: number } | undefined;
  return data ? { turnIndex: data.turn_index ?? null } : null;
};

(window as unknown as Record<string, unknown>).__r09 = {
  switchIdentity: (identity: string) => rerender(identity),
  openPlay,
  cacheTurnIndex: () => cached()?.turnIndex ?? null,
  identity: () => boundary?.identity ?? null,
  setSession: (sessionId: string) => { (window as unknown as { __r09Session?: string }).__r09Session = sessionId; },
};

setAuthTokenGetter(() => "r09-fixture-token");
createRoot(document.getElementById("root")!).render(<View />);
if (campaignId) void openPlay();
