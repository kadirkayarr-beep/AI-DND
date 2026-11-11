import { createContext, useCallback, useContext, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react';
import {
  DEFAULT_APPEARANCE_SETTINGS,
  readAppearanceSettings,
  resolveEffectsLevel,
  writeAppearanceSettings,
  type AppearanceSettings,
  type EffectsLevel,
} from '@/lib/appearance-settings';
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
const serverReducedMotion = () => false;

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppearanceSettings>(() => readAppearanceSettings());
  const prefersReducedMotion = useSyncExternalStore(subscribeReducedMotion, snapshotReducedMotion, serverReducedMotion);
  const setSetting = useCallback(<K extends keyof AppearanceSettings>(key: K, value: AppearanceSettings[K]) => {
    setSettings((current) => {
      const next = { ...current, [key]: value };
      writeAppearanceSettings(next);
      return next;
    });
  }, []);
  const value = useMemo<AppearanceContextValue>(() => ({
    settings,
    setSetting,
    effectsLevel: resolveEffectsLevel(settings, prefersReducedMotion),
    prefersReducedMotion,
  }), [settings, setSetting, prefersReducedMotion]);
  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>;
}

export function useAppearance(): AppearanceContextValue {
  return useContext(AppearanceContext);
}
