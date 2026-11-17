import { useEffect, useRef, useState } from 'react';
import { useAppearance } from '@/components/appearance-provider';

// Plan part D1 (simple path): a looped video per theme on a flat white (day, multiplied in) or black (night,
// screened in) ground, so no alpha channel is needed. The still frame is always shown; while motion is on the
// video loops all the time (owner decision 2026-11-17), never plays under reduced motion, pauses while the tab
// is hidden and unmounts with the home screen.
export function OuroborosLogo() {
  const { resolvedTheme, prefersReducedMotion, effectsLevel } = useAppearance();
  const base = import.meta.env.BASE_URL;
  const still = `${base}logo/ouroboros-${resolvedTheme}-still.jpg`;
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const motion = !prefersReducedMotion && effectsLevel !== 'off';

  // A theme change swaps the src, which reloads and stops the video, so the theme restarts it too.
  useEffect(() => {
    const el = video.current;
    if (!el || !motion) return undefined;
    const start = () => { if (!document.hidden) void el.play().then(() => setPlaying(true), () => setPlaying(false)); };
    const onVisibility = () => {
      if (document.hidden) el.pause();
      else start();
    };
    start();
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [motion, resolvedTheme]);

  return (
    <div className={`ouroboros-art${playing ? ' is-playing' : ''}`}>
      <img
        className="ouroboros-still"
        src={still}
        alt="UNWRITTEN amblemi: kendi kuyruğunu ısıran kömür çizimi yılan"
        data-testid="image-approved-ouroboros"
      />
      {motion && (
        <video
          ref={video}
          className="ouroboros-video"
          src={`${base}logo/ouroboros-${resolvedTheme}.mp4`}
          poster={still}
          muted
          loop
          playsInline
          preload="auto"
          aria-hidden="true"
          tabIndex={-1}
          data-testid="video-ouroboros"
        />
      )}
    </div>
  );
}
