import {
  readAppearanceSettings,
  writeAppearanceSettings,
  type AppearanceSettings,
  type AppearanceStorage,
} from './appearance-settings.ts';

/**
 * Settings held in memory and mirrored to storage after each change.
 * Ruling: the in-memory value is the base for a change (storage is read once at start), so a blocked
 * store never loses the choice; another tab's changes to other keys are overwritten (last writer wins).
 */
export function createAppearanceStore(storage?: AppearanceStorage | null) {
  let settings = readAppearanceSettings(storage);
  const listeners = new Set<() => void>();
  return {
    get: () => settings,
    set<K extends keyof AppearanceSettings>(key: K, value: AppearanceSettings[K]) {
      if (settings[key] === value) return;
      settings = { ...settings, [key]: value };
      writeAppearanceSettings(settings, storage);
      for (const listener of [...listeners]) listener();
    },
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
  };
}
