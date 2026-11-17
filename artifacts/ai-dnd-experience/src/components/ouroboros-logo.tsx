import { useEffect, useRef, useState } from 'react';
import { useAppearance } from '@/components/appearance-provider';
import { createOuroborosRenderer, type OuroborosRenderer } from '@/components/ouroboros-renderer';

// v0 graphite ouroboros (owner-approved 2026-11-17), drawn live in WebGL. The renderer loops while motion is
// on (owner decision 2026-11-17), and stops itself while the tab is hidden, the logo is off screen or the OS
// asks for reduced motion. Without WebGL (or when the context is lost) the static emblem stays: the same
// drawing as a mask, so it never needs a second image per theme. Day uses the ink as drawn; night is the same
// logo with filter: invert(1) (CSS, see .unwritten-ouroboros in unwritten-play.css).
// variant="mark" is the small 24-40 px mark: a static silhouette, no WebGL at all.
export function OuroborosLogo({ size, variant = 'full' }: { size?: number; variant?: 'full' | 'mark' }) {
  const { prefersReducedMotion, effectsLevel } = useAppearance();
  const motion = !prefersReducedMotion && effectsLevel !== 'off';
  const mark = variant === 'mark';
  const canvas = useRef<HTMLCanvasElement>(null);
  const dust = useRef<HTMLCanvasElement>(null);
  const renderer = useRef<OuroborosRenderer | null>(null);
  const motionNow = useRef(motion);
  const [live, setLive] = useState(false);

  useEffect(() => {
    motionNow.current = motion;
    renderer.current?.setRunning(motion);
  }, [motion]);

  useEffect(() => {
    if (mark || !canvas.current || !dust.current) return undefined;
    let disposed = false;
    const element = canvas.current;
    const onFailed = () => setLive(false);
    element.addEventListener('ouroboros-renderer-failed', onFailed);
    createOuroborosRenderer(element, dust.current).then(engine => {
      if (disposed) { engine.destroy(); return; }
      renderer.current = engine;
      engine.setRunning(motionNow.current);
      setLive(true);
    }).catch(() => { if (!disposed) setLive(false); });
    return () => {
      disposed = true;
      element.removeEventListener('ouroboros-renderer-failed', onFailed);
      renderer.current?.destroy();
      renderer.current = null;
    };
  }, [mark]);

  const mask = `url("${import.meta.env.BASE_URL}logo/ouroboros-${mark ? 'mark' : 'emblem'}.png")`;
  return (
    <span
      className="unwritten-ouroboros"
      style={size ? { width: size, height: size } : undefined}
      data-renderer={live ? 'webgl' : 'static'}
      data-variant={variant}
      role="img"
      aria-label="UNWRITTEN amblemi: kendi kuyruğunu ısıran kömür çizimi yılan"
      data-testid={mark ? 'image-ouroboros-mark' : 'image-approved-ouroboros'}
    >
      <span className="unwritten-ouroboros-fallback" aria-hidden="true" style={{ maskImage: mask, WebkitMaskImage: mask }} />
      {!mark && (
        <>
          <canvas ref={canvas} aria-hidden="true" />
          <canvas ref={dust} aria-hidden="true" />
        </>
      )}
    </span>
  );
}
