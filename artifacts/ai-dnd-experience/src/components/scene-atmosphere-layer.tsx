import { useEffect, useState, type CSSProperties } from 'react';
import {
  rgbaCss,
  themedAtmosphere,
  type AtmosphereTheme,
  type ResolvedAtmosphere,
} from '@/lib/scene-atmosphere';
import './scene-atmosphere-layer.css';

/** Deterministic pseudo-random in 0..1 so motes keep their place across renders. */
export function seeded(i: number, j: number): number {
  const x = Math.sin(i * 91.7 + j * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

type Var = CSSProperties & Record<`--${string}`, string | number>;

function moteStyle(i: number): Var {
  const t = 12 * (0.8 + 0.4 * seeded(i, 4));
  return {
    '--x': `${(6 + seeded(i, 1) * 88).toFixed(1)}%`,
    '--y': `${(12 + seeded(i, 2) * 78).toFixed(1)}%`,
    '--s': `${(2.5 * (0.8 + 0.6 * seeded(i, 5))).toFixed(1)}px`,
    '--vx': `${(3 * (0.7 + 0.6 * seeded(i, 6))).toFixed(1)}vw`,
    '--vy': `${(-10 * (0.7 + 0.6 * seeded(i, 7))).toFixed(1)}vh`,
    '--t': `${t.toFixed(1)}s`,
    '--d': `${(-seeded(i, 3) * t).toFixed(1)}s`,
  };
}

/**
 * Page-material atmosphere behind the story text. Paints only the resolved preset (engine facts
 * resolved by resolveAtmosphere); it never reads or produces story text. Mount inside a
 * position: relative container with the text layered above.
 */
export function SceneAtmosphereLayer({ atmosphere, theme }: { atmosphere: ResolvedAtmosphere; theme: AtmosphereTheme }) {
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    if (typeof document === 'undefined') return undefined;
    const sync = () => setHidden(document.hidden);
    sync();
    document.addEventListener('visibilitychange', sync);
    return () => document.removeEventListener('visibilitychange', sync);
  }, []);

  const colours = themedAtmosphere(atmosphere, theme);
  const motion = atmosphere.motion;
  const style: Var = {
    '--sc-tint': rgbaCss(colours.tint),
    '--sc-bloom': rgbaCss(colours.bloom),
    '--sc-win': rgbaCss(colours.win),
    '--sc-vig': rgbaCss(colours.vig),
    '--sc-fog': rgbaCss(colours.fog),
    '--sc-mote': rgbaCss(colours.mote),
    '--sc-bx': `${atmosphere.bloom.x}%`,
    '--sc-by': `${atmosphere.bloom.y}%`,
    '--sc-br': `${atmosphere.bloom.r}%`,
  };
  const fogY = ['18%', '56%'];
  const fogH = ['46%', '52%'];

  return (
    <div
      className="unw-atmo"
      aria-hidden="true"
      data-atmosphere={atmosphere.kind}
      data-period={atmosphere.period ?? undefined}
      data-motion={motion ? '1' : '0'}
      data-hidden={hidden ? '1' : '0'}
      style={style}
    >
      <i className="unw-atmo-tint" />
      <i className="unw-atmo-bloom" />
      <i className="unw-atmo-win" />
      {motion
        ? Array.from({ length: motion.fogBands }, (_, i) => (
            <i
              key={`fog-${i}`}
              className="unw-atmo-fog"
              style={{ '--y': fogY[i], '--h': fogH[i], '--t': `${18 + i * 7}s` } as Var}
            />
          ))
        : null}
      {motion
        ? Array.from({ length: motion.mote.n }, (_, i) => (
            <i key={`mote-${i}`} className="unw-atmo-mote" style={{ ...moteStyle(i), '--glow': `${motion.mote.glow}px` } as Var} />
          ))
        : null}
      <i className="unw-atmo-vig" />
    </div>
  );
}
