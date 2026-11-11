import { createContext, useContext, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react';
import {
  DEFAULT_APPEARANCE_SETTINGS,
  resolveEffectsLevel,
  type AppearanceSettings,
  type EffectsLevel,
} from '@/lib/appearance-settings';
import { createAppearanceStore } from '@/lib/appearance-store';
import { readPrefersReducedMotion, subscribePrefersReducedMotion } from '@/lib/reduced-motion';

type AppearanceContextValue = {
  settings: AppearanceSettings;
  setSetting: <K extends keyof AppearanceSettings>(key: K, value: AppearanceSettings[K]) => void;
  /** The chosen level after the system reduced-motion preference has capped it. */
  effectsLevel: EffectsLevel;
  prefersReducedMotion: boolean;
};

const AppearanceContext = createContext<AppearanceContextValue>({
  settings: DEFAULT_APPEARANCE_SETTINGS,
  setSetting: () => {},
  effectsLevel: resolveEffectsLevel(DEFAULT_APPEARANCE_SETTINGS, false),
  prefersReducedMotion: false,
});

const browserWindow = () => (typeof window === 'undefined' ? null : window);
const subscribeReducedMotion = (onChange: () => void) => subscribePrefersReducedMotion(browserWindow(), onChange);
const snapshotReducedMotion = () => readPrefersReducedMotion(browserWindow());

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [store] = useState(() => createAppearanceStore());
  const settings = useSyncExternalStore(store.subscribe, store.get, store.get);
  const prefersReducedMotion = useSyncExternalStore(subscribeReducedMotion, snapshotReducedMotion, snapshotReducedMotion);
  const value = useMemo<AppearanceContextValue>(() => ({
    settings,
    setSetting: store.set,
    effectsLevel: resolveEffectsLevel(settings, prefersReducedMotion),
    prefersReducedMotion,
  }), [settings, store, prefersReducedMotion]);
  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>;
}

export function useAppearance(): AppearanceContextValue {
  return useContext(AppearanceContext);
}
