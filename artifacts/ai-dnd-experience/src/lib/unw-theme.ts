export type UnwThemeChoice = 'night' | 'day' | 'system';
export type UnwResolvedTheme = 'night' | 'day';

export const UNW_THEME_COLORS = {
  night: {
    page: '#11161B',
    surface: '#1A2128',
    text: '#E6DFCE',
    textSoft: '#B8B1A0',
    accentLight: '#D9A441',
    patina: '#4F8F83',
    danger: '#A8332E',
  },
  day: {
    page: '#DCD8C8',
    surface: '#EAE6D8',
    text: '#26211A',
    textSoft: '#4A4336',
    accentLight: '#7A4F0A',
    patina: '#2E675C',
    danger: '#8C2621',
  },
} as const satisfies Record<UnwResolvedTheme, Record<string, string>>;

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
