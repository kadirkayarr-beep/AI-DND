import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { GameState } from '@workspace/api-client-react';

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
  source: 'canonical-world' | 'neutral-default';
};

const ThemeContext = createContext<EnvironmentTheme>({
  family: 'neutral',
  time: 'neutral',
  weather: 'neutral',
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
    return {
      family: familyForEnvironment(world?.environment),
      time: world?.time_of_day ?? 'neutral',
      weather: world?.weather === 'unknown' ? 'neutral' : world?.weather ?? 'neutral',
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
      >
        {children}
      </div>
    </ThemeContext.Provider>
  );
}

export function useEnvironmentTheme() {
  return useContext(ThemeContext);
}