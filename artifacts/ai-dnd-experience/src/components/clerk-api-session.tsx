import { useAuth } from "@clerk/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useRef, type ReactNode } from "react";
import { rotateAuthEpoch, setAuthTokenGetter } from "@workspace/api-client-react/custom-fetch";
import {
  clerkSessionIdentity,
  clearAccountBrowserState,
  nextAccountClient,
  readClerkToken,
  type AccountBoundary,
} from "@/lib/account-session";

function GateWaiting() {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        background: "#100e0c",
        color: "#d9bd8b",
        fontFamily: "Georgia, serif",
      }}
    >
      <p>Kapılar açılıyor...</p>
    </main>
  );
}

export default function ClerkApiSession({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const identity = clerkSessionIdentity(auth);
  const tokenReader = useRef(auth.getToken);
  tokenReader.current = auth.getToken;
  const boundary = useRef<AccountBoundary | null>(null);
  const generation = useRef(0);

  if (!identity) {
    if (boundary.current) {
      rotateAuthEpoch();
      void boundary.current.client.cancelQueries();
      boundary.current.client.clear();
      boundary.current = null;
      clearAccountBrowserState();
      generation.current += 1;
    }
    setAuthTokenGetter(null);
  } else if (boundary.current?.identity !== identity) {
    boundary.current = nextAccountClient(boundary.current, identity);
    generation.current += 1;
  }

  if (identity && boundary.current) {
    const installedGeneration = generation.current;
    setAuthTokenGetter(() => readClerkToken(
      () => tokenReader.current(),
      () => generation.current === installedGeneration,
    ));
  }

  const activeIdentity = identity;
  const activeGeneration = generation.current;
  const activeClient = boundary.current?.client ?? null;

  useEffect(() => {
    return () => {
      if (!activeClient) return;
      void activeClient.cancelQueries();
      activeClient.clear();
      clearAccountBrowserState();
      if (generation.current === activeGeneration) {
        setAuthTokenGetter(null);
        rotateAuthEpoch();
        boundary.current = null;
      }
    };
  }, [activeIdentity, activeClient, activeGeneration]);

  if (!identity || !activeClient) return <GateWaiting />;

  return (
    <QueryClientProvider client={activeClient}>
      <div key={identity} style={{ display: "contents" }}>{children}</div>
    </QueryClientProvider>
  );
}
