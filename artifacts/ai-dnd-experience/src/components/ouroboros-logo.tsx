import { useEffect, useRef, useState } from 'react';
import { useAppearance } from '@/components/appearance-provider';

// Plan part D1 (simple path): a looped video per theme on a flat white (day, multiplied in) or black (night,
// screened in) ground, so no alpha channel is needed. The still frame is always shown; the video plays only
// while something is really loading, stays at least MIN_VISIBLE_MS once shown, never plays under reduced
// motion, pauses while the tab is hidden and unmounts with the home screen.
export const MIN_VISIBLE_MS = 600;

export function OuroborosLogo({ loading }: { loading: boolean }) {
  const { resolvedTheme, prefersReducedMotion, effectsLevel } = useAppearance();
  const base = import.meta.env.BASE_URL;
  const still = `${base}logo/ouroboros-${resolvedTheme}-still.jpg`;
  const video = useRef<HTMLVideoElement>(null);
  const shownAt = useRef(0);
  const [playing, setPlaying] = useState(false);
  const motion = !prefersReducedMotion && effectsLevel !== 'off';

  useEffect(() => {
    const el = video.current;
    if (!el || !motion) return undefined;
    if (loading) {
      shownAt.current = Date.now();
      setPlaying(true);
      void el.play().catch(() => setPlaying(false));
      return undefined;
    }
    if (!playing) return undefined;
    const rest = Math.max(0, MIN_VISIBLE_MS - (Date.now() - shownAt.current));
    const timer = setTimeout(() => { el.pause(); el.currentTime = 0; setPlaying(false); }, rest);
    return () => clearTimeout(timer);
  }, [loading, motion]);

  useEffect(() => {
    const el = video.current;
    const onVisibility = () => {
      if (!el) return;
      if (document.hidden) el.pause();
      else if (playing) void el.play().catch(() => {});
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [playing]);

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
