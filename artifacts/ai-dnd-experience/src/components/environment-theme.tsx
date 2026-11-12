import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { CSSProperties } from 'react';
import type { GameState } from '@workspace/api-client-react';
import { ATMOSPHERE_FAMILY_DATA, NEUTRAL_LINE, rgbaCss } from '@/lib/scene-atmosphere';

type EnvironmentFamily =
  | 'neutral'
  | 'tavern'
  | 'forest'
  | 'city'
  | 'village'
  | 'road'
  | 'wilderness'
  | 'dungeon'
  | 'cave'
  | 'castle'
  | 'temple'
  | 'ruins';

type ThemeTime = 'neutral' | 'dawn' | 'day' | 'evening' | 'night';
type ThemeWeather = 'neutral' | 'clear' | 'rain' | 'fog' | 'snow' | 'storm';

type EnvironmentTheme = {
  family: EnvironmentFamily;
  time: ThemeTime;
  weather: ThemeWeather;
  /** In-game clock; the atmosphere uses it only to split 'day' into morning and afternoon. */
  clock: { hour: number; minute: number } | null;
  source: 'canonical-world' | 'neutral-default';
};

const ThemeContext = createContext<EnvironmentTheme>({
  family: 'neutral',
  time: 'neutral',
  weather: 'neutral',
  clock: null,
  source: 'neutral-default',
});

function familyForEnvironment(environment?: string): EnvironmentFamily {
  switch (environment) {
    case 'tavern':
    case 'forest':
    case 'city':
    case 'village':
    case 'road':
    case 'wilderness':
    case 'dungeon':
    case 'cave':
    case 'castle':
    case 'temple':
    case 'ruins':
      return environment;
    default:
      return 'neutral';
  }
}

export function EnvironmentThemeProvider({ state, children }: { state?: GameState; children: ReactNode }) {
  const theme = useMemo<EnvironmentTheme>(() => {
    const world = state?.world;
    const time = state?.campaign_time;
    return {
      family: familyForEnvironment(world?.environment),
      time: world?.time_of_day ?? 'neutral',
      weather: world?.weather === 'unknown' ? 'neutral' : world?.weather ?? 'neutral',
      clock: time ? { hour: time.hour, minute: time.minute } : null,
      source: world ? 'canonical-world' : 'neutral-default',
    };
  }, [state]);

  return (
    <ThemeContext.Provider value={theme}>
      <div
        className="environment-theme"
        data-environment={theme.family}
        data-time={theme.time}
        data-weather={theme.weather}
        data-theme-source={theme.source}
        style={{ '--theme-line': rgbaCss(theme.family === 'neutral' ? NEUTRAL_LINE : ATMOSPHERE_FAMILY_DATA[theme.family].line) } as CSSProperties}
      >
        {children}
      </div>
    </ThemeContext.Provider>
  );
}

export function useEnvironmentTheme() {
  return useContext(ThemeContext);
}