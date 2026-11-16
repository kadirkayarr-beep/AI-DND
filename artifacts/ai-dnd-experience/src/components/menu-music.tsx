import { Volume2, VolumeX } from 'lucide-react';
import { useEffect } from 'react';
import { useAppearance } from '@/components/appearance-provider';
import { startMenuMusic, stopMenuMusic } from '@/lib/menu-music';

/** Plays the main-menu track while the home screen is mounted; the one visible control is a small icon button. */
export function MenuMusicButton() {
  const { settings, setSetting } = useAppearance();
  const on = settings.menuMusic;
  useEffect(() => {
    if (!on) return undefined;
    void startMenuMusic(import.meta.env.BASE_URL);
    return () => stopMenuMusic();
  }, [on]);
  const label = on ? 'Müziği kapat' : 'Müziği aç';
  return (
    <button
      type="button"
      className="menu-music-button"
      aria-label={label}
      aria-pressed={on}
      title={label}
      data-testid="button-menu-music"
      onClick={() => setSetting('menuMusic', !on)}
    >
      {on ? <Volume2 size={18} aria-hidden="true" /> : <VolumeX size={18} aria-hidden="true" />}
    </button>
  );
}
