import { type ReactNode } from "react";
import { ErrorBoundary } from "@/components/error-boundary";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/not-found";
import GameBrowser from "@/pages/game-browser";
import { Route, Switch, useLocation, Router as WouterRouter } from "wouter";

function Router() {
  return (
    // Keep a shared shell (sidebar, navbar) outside the boundary so it
    // survives a page crash.
    <RoutedErrorBoundary>
      <Switch>
        <Route path="/" component={GameBrowser} />
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
    <TooltipProvider>
      <WouterRouter base={routerBase(import.meta.env.BASE_URL)}>
        <Router />
      </WouterRouter>
      <Toaster />
    </TooltipProvider>
  );
}
