import { QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";

import AppShell from "@/app-shell";
import { ErrorBoundary } from "@/components/error-boundary";
import { startLocalPlaySession } from "@/lib/local-play-session";

import "./index.css";

// Served only by the Vite dev server with VITE_AI_DND_LOCAL_PLAY=1 (see local-play-vite.ts).
const session = startLocalPlaySession();

createRoot(document.getElementById("root")!, {
  onCaughtError: (error, errorInfo) => {
    console.error(error, errorInfo.componentStack);
  },
}).render(
  <ErrorBoundary>
    <QueryClientProvider client={session.client}>
      <AppShell />
    </QueryClientProvider>
  </ErrorBoundary>,
);
