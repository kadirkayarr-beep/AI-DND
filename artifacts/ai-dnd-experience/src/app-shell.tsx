import { lazy, Suspense, type ReactNode } from "react";
import { ErrorBoundary } from "@/components/error-boundary";
import { Toaster } from "@/components/ui/toaster";
import { AppearanceProvider } from "@/components/appearance-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/not-found";
import GameBrowser from "@/pages/game-browser";
import { Route, Switch, useLocation, Router as WouterRouter } from "wouter";

// Book UI gallery (A1): development only, never part of the game flow; the import is dropped from production builds.
const KitapGalerisi = import.meta.env.DEV ? lazy(() => import("./pages/kitap-galerisi")) : null;

function Router() {
  return (
    // Keep a shared shell (sidebar, navbar) outside the boundary so it
    // survives a page crash.
    <RoutedErrorBoundary>
      <Switch>
        <Route path="/" component={GameBrowser} />
        {KitapGalerisi ? (
          <Route path="/galeri">
            <Suspense fallback={null}><KitapGalerisi /></Suspense>
          </Route>
        ) : null}
        <Route component={NotFound} />
      </Switch>
    </RoutedErrorBoundary>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function routerBase(baseUrl: string): string {
  return baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
}

export default function AppShell() {
  return (
    <AppearanceProvider>
    <TooltipProvider>
      <WouterRouter base={routerBase(import.meta.env.BASE_URL)}>
        <Router />
      </WouterRouter>
      <Toaster />
    </TooltipProvider>
    </AppearanceProvider>
  );
}
