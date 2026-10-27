/**
 * Disposable page for the R02 live-browser check. It mounts the REAL GameBrowser and does NOT replace fetch: requests go
 * through the Vite proxy to the temporary backend started by tests/r02-live-browser.test.mjs. Not the signed-in app.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { setAuthTokenGetter } from "@workspace/api-client-react/custom-fetch";
import GameBrowser from "@/pages/game-browser";
import "@/index.css";

const campaignId = new URLSearchParams(window.location.search).get("campaign") ?? "";

setAuthTokenGetter(() => "live-fixture-token");

createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <GameBrowser />
  </QueryClientProvider>,
);

async function openPlayScreen() {
  const clickWhen = async (selector: string) => {
    for (let attempt = 0; attempt < 80; attempt += 1) {
      const node = document.querySelector<HTMLButtonElement>(selector);
      if (node && !node.disabled) {
        node.click();
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 100));
    }
    throw new Error(`live fixture could not find ${selector}`);
  };
  await clickWhen('[data-testid="button-continue-session"]');
  await clickWhen(`[data-testid="button-resume-${campaignId}"]`);
}

if (campaignId) void openPlayScreen();
