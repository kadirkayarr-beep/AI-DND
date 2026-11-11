import { useAppearance } from '@/components/appearance-provider';
import { useEnvironmentTheme } from '@/components/environment-theme';
import { SceneAtmosphereLayer } from '@/components/scene-atmosphere-layer';
import { shouldPlayEffects } from '@/lib/effect-registry';
import { resolveAtmosphere } from '@/lib/scene-atmosphere';

/**
 * The one atmosphere layer of the play screen: engine world facts from EnvironmentThemeProvider plus
 * the effects level from AppearanceProvider (which already folds in reduced motion). Mount it as the
 * first child of the isolated .dnd-app container.
 */
export function EnvironmentAtmosphere() {
  const { family, time, weather, clock } = useEnvironmentTheme();
  const { effectsLevel } = useAppearance();
  const atmosphere = resolveAtmosphere({ environment: family, timeOfDay: time, weather, clock }, effectsLevel);
  return <SceneAtmosphereLayer atmosphere={atmosphere} theme="night" fade={shouldPlayEffects(effectsLevel)} />;
}
