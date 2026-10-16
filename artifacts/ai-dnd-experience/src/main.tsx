import { ClerkProvider } from "@clerk/react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { ErrorBoundary } from "@/components/error-boundary";
import { clerkReturnUrl } from "@/lib/clerk-return-url";

import "./index.css";

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
const clerkReturn = clerkReturnUrl(import.meta.env.BASE_URL, window.location.href);

createRoot(document.getElementById("root")!, {
  // Keeps caught errors off reportError(), which would raise the dev overlay.
  onCaughtError: (error, errorInfo) => {
    console.error(error, errorInfo.componentStack);
  },
}).render(
  <ErrorBoundary>
    {clerkPublishableKey ? (
      <ClerkProvider
        publishableKey={clerkPublishableKey}
        signInFallbackRedirectUrl={clerkReturn}
        signUpFallbackRedirectUrl={clerkReturn}
        signInForceRedirectUrl={clerkReturn}
        signUpForceRedirectUrl={clerkReturn}
        afterSignOutUrl={clerkReturn}
      >
        <App />
      </ClerkProvider>
    ) : (
      <main
        role="alert"
        style={{
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          background: "#100e0c",
          color: "#e7d5b6",
          fontFamily: "Georgia, serif",
        }}
      >
        Giriş şu anda kullanılamıyor.
      </main>
    )}
  </ErrorBoundary>,
);
