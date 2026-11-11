import { createContext, useContext, useLayoutEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react';
import {
  DEFAULT_APPEARANCE_SETTINGS,
  resolveEffectsLevel,
  type AppearanceSettings,
  type EffectsLevel,
} from '@/lib/appearance-settings';
import { createAppearanceStore } from '@/lib/appearance-store';
import { readPrefersReducedMotion, subscribePrefersReducedMotion } from '@/lib/reduced-motion';
import { readPrefersDark, subscribePrefersDark } from '@/lib/system-theme';
import { applyReadingAttributes, resolveTheme, type UnwResolvedTheme } from '@/lib/unw-theme';

type AppearanceContextValue = {
  settings: AppearanceSettings;
  setSetting: <K extends keyof AppearanceSettings>(key: K, value: AppearanceSettings[K]) => void;
  /** The chosen level after the system reduced-motion preference has capped it. */
  effectsLevel: EffectsLevel;
  prefersReducedMotion: boolean;
  /** The reading theme after 'system' has been resolved from the colour-scheme preference. */
  resolvedTheme: UnwResolvedTheme;
};

const AppearanceContext = createContext<AppearanceContextValue>({
  settings: DEFAULT_APPEARANCE_SETTINGS,
  setSetting: () => {},
  effectsLevel: resolveEffectsLevel(DEFAULT_APPEARANCE_SETTINGS, false),
  prefersReducedMotion: false,
  resolvedTheme: 'night',
});

const browserWindow = () => (typeof window === 'undefined' ? null : window);
const subscribeReducedMotion = (onChange: () => void) => subscribePrefersReducedMotion(browserWindow(), onChange);
const snapshotReducedMotion = () => readPrefersReducedMotion(browserWindow());
const subscribeDark = (onChange: () => void) => subscribePrefersDark(browserWindow(), onChange);
const snapshotDark = () => readPrefersDark(browserWindow());

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [store] = useState(() => createAppearanceStore());
  const settings = useSyncExternalStore(store.subscribe, store.get, store.get);
  const prefersReducedMotion = useSyncExternalStore(subscribeReducedMotion, snapshotReducedMotion, snapshotReducedMotion);
  const systemPrefersDark = useSyncExternalStore(subscribeDark, snapshotDark, snapshotDark);
  const resolvedTheme = resolveTheme(settings.theme, systemPrefersDark);
  // Before paint, so a returning day reader never sees a night frame. The attributes live on <html>.
  useLayoutEffect(() => {
    applyReadingAttributes(document.documentElement, settings, systemPrefersDark);
  }, [settings.theme, settings.highContrast, settings.dyslexiaFont, systemPrefersDark]);
  const value = useMemo<AppearanceContextValue>(() => ({
    settings,
    setSetting: store.set,
    effectsLevel: resolveEffectsLevel(settings, prefersReducedMotion),
    prefersReducedMotion,
    resolvedTheme,
  }), [settings, store, prefersReducedMotion, resolvedTheme]);
  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>;
}

export function useAppearance(): AppearanceContextValue {
  return useContext(AppearanceContext);
}
