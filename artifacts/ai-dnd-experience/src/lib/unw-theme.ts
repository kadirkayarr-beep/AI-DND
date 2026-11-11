export type UnwThemeChoice = 'night' | 'day' | 'system';
export type UnwResolvedTheme = 'night' | 'day';

/*
 * Reading tokens. Night is the base; day is tuned so body text keeps 7:1 and soft text 4.5:1 even under the
 * lightest atmosphere veil (the fog veil is a light colour over dark text, tests/scene-atmosphere.test.mjs).
 * accentLight / dangerText / patinaText are text-capable colours; patina and danger are fills and rules.
 */
export const UNW_THEME_COLORS = {
  night: {
    page: '#11161B',
    surface: '#1A2128',
    surfaceSunken: '#0E1216',
    text: '#EEE7D5',
    textSoft: '#B8B1A0',
    accentLight: '#E8BA5C',
    patina: '#4F8F83',
    patinaText: '#8CC9BA',
    danger: '#A8332E',
    dangerText: '#F2B8B0',
    border: '#3A444B',
  },
  day: {
    page: '#E6E2D4',
    surface: '#EFEBDF',
    surfaceSunken: '#F6F3EA',
    text: '#0F0C08',
    textSoft: '#3A3228',
    accentLight: '#523004',
    patina: '#2E675C',
    patinaText: '#0C2F28',
    danger: '#8C2621',
    dangerText: '#5E1511',
    border: '#B5AD96',
  },
} as const satisfies Record<UnwResolvedTheme, Record<string, string>>;

/** The highContrast setting: same token names, stronger values (text >= 7:1 everywhere, full-strength rules). */
export const UNW_HIGH_CONTRAST_COLORS = {
  night: {
    page: '#000000',
    surface: '#0B0F12',
    surfaceSunken: '#000000',
    text: '#FFFFFF',
    textSoft: '#F2EBDA',
    accentLight: '#FFD36B',
    patina: '#7FD0BE',
    patinaText: '#9BE0D0',
    danger: '#FF6B5E',
    dangerText: '#FFB4AA',
    border: '#C9C2B0',
  },
  day: {
    page: '#F4F1E8',
    surface: '#FFFFFF',
    surfaceSunken: '#FFFFFF',
    text: '#000000',
    textSoft: '#0F0C08',
    accentLight: '#4A2C00',
    patina: '#0F3D34',
    patinaText: '#0F3D34',
    danger: '#6E1511',
    dangerText: '#6E1511',
    border: '#0F0C08',
  },
} as const satisfies Record<UnwResolvedTheme, Record<keyof (typeof UNW_THEME_COLORS)['night'], string>>;

export function resolveTheme(choice: UnwThemeChoice, systemPrefersDark: boolean): UnwResolvedTheme {
  if (choice === 'night' || choice === 'day') return choice;
  return systemPrefersDark ? 'night' : 'day';
}

export function applyTheme(
  root: { setAttribute(name: string, value: string): void },
  choice: UnwThemeChoice,
  systemPrefersDark: boolean,
): UnwResolvedTheme {
  const resolved = resolveTheme(choice, systemPrefersDark);
  root.setAttribute('data-unw-theme', resolved);
  return resolved;
}

/**
 * Everything the reading layer reads from <html>: theme, contrast level and the dyslexia-friendly face.
 * One call, so the provider and the tests agree on the attribute names.
 */
export function applyReadingAttributes(
  root: { setAttribute(name: string, value: string): void },
  settings: { theme: UnwThemeChoice; highContrast: boolean; dyslexiaFont: boolean },
  systemPrefersDark: boolean,
): UnwResolvedTheme {
  const resolved = applyTheme(root, settings.theme, systemPrefersDark);
  root.setAttribute('data-unw-contrast', settings.highContrast ? 'high' : 'normal');
  root.setAttribute('data-unw-font', settings.dyslexiaFont ? 'dyslexia' : 'normal');
  return resolved;
}
