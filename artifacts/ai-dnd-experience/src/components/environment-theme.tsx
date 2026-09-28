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
  source: 'canonical-location' | 'neutral-default';
};

const ThemeContext = createContext<EnvironmentTheme>({
  family: 'neutral',
  time: 'neutral',
  weather: 'neutral',
  source: 'neutral-default',
});

function familyForState(state?: GameState): EnvironmentFamily {
  const current = state?.locations?.[state.location];
  const text = `${state?.location ?? ''} ${current?.name ?? ''} ${current?.type ?? ''}`.toLocaleLowerCase('tr-TR');
  if (/taverna|han|meyhane|inn|tavern/.test(text)) return 'tavern';
  if (/orman|forest|koru|woods/.test(text)) return 'forest';
  if (/şehir|sehir|city|kent|başkent|capital/.test(text)) return 'city';
  if (/köy|koy|village|mezra|hamlet/.test(text)) return 'village';
  if (/yol|road|patika|travel|geçit|gecit/.test(text)) return 'road';
  if (/vahşi|vahsi|wilderness|kır|kir|bozkır|bozkir/.test(text)) return 'wilderness';
  if (/zindan|dungeon/.test(text)) return 'dungeon';
  if (/mağara|magara|cave|kovuk/.test(text)) return 'cave';
  if (/kale|castle|hisar|fortress/.test(text)) return 'castle';
  if (/tapınak|tapinak|temple|manastır|manastir/.test(text)) return 'temple';
  if (/harabe|ruins|yıkıntı|yikinti/.test(text)) return 'ruins';
  return 'neutral';
}

export function EnvironmentThemeProvider({ state, children }: { state?: GameState; children: ReactNode }) {
  const theme = useMemo<EnvironmentTheme>(() => ({
    family: familyForState(state),
    time: 'neutral',
    weather: 'neutral',
    source: state?.location ? 'canonical-location' : 'neutral-default',
  }), [state]);

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