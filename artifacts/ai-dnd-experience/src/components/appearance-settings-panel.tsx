import { useAppearance } from '@/components/appearance-provider';
import type { EffectsLevel, InkRevealSpeed } from '@/lib/appearance-settings';
import type { UnwThemeChoice } from '@/lib/unw-theme';
import './appearance-settings-panel.css';

const LEVELS: ReadonlyArray<{ value: EffectsLevel; label: string }> = [
  { value: 'off', label: 'Kapalı' },
  { value: 'low', label: 'Az' },
  { value: 'full', label: 'Tam' },
];

const THEMES: ReadonlyArray<{ value: UnwThemeChoice; label: string }> = [
  { value: 'night', label: 'Gece' },
  { value: 'day', label: 'Gündüz' },
  { value: 'system', label: 'Sistem' },
];

const INK_SPEEDS: ReadonlyArray<{ value: InkRevealSpeed; label: string }> = [
  { value: 'slow', label: 'Yavaş' },
  { value: 'normal', label: 'Normal' },
  { value: 'fast', label: 'Hızlı' },
  { value: 'instant', label: 'Anında' },
];

/*
 * Only settings that something reads are shown. Dice set, health gauge, spell-slot style and font scale
 * live in the settings store but have no consumer yet, so they have no control here (font size is the
 * Aa control beside the story; see the S3 report Ruling).
 */
export function AppearanceSettingsPanel() {
  const { settings, setSetting } = useAppearance();
  return (
    <div className="appearance-settings" data-testid="appearance-settings-panel">
      <fieldset role="radiogroup">
        <legend>Okuma teması</legend>
        {THEMES.map(({ value, label }) => (
          <label key={value} className="appearance-option">
            <input
              type="radio"
              name="appearance-theme"
              value={value}
              checked={settings.theme === value}
              onChange={() => setSetting('theme', value)}
              data-testid={`radio-theme-${value}`}
            />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>
      <fieldset role="radiogroup">
        <legend>Efekt seviyesi</legend>
        {LEVELS.map(({ value, label }) => (
          <label key={value} className="appearance-option">
            <input
              type="radio"
              name="appearance-effects-level"
              value={value}
              checked={settings.effectsLevel === value}
              onChange={() => setSetting('effectsLevel', value)}
              data-testid={`radio-effects-${value}`}
            />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>
      <p className="appearance-note">Hareketi azalt ayarı sistemden okunur; açıksa efektleri sınırlar.</p>
      <fieldset role="radiogroup">
        <legend>Mürekkep belirme hızı</legend>
        {INK_SPEEDS.map(({ value, label }) => (
          <label key={value} className="appearance-option">
            <input
              type="radio"
              name="appearance-ink-speed"
              value={value}
              checked={settings.inkRevealSpeed === value}
              onChange={() => setSetting('inkRevealSpeed', value)}
              data-testid={`radio-ink-${value}`}
            />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>
      <p className="appearance-note">Yeni anlatı satırları bu hızda belirir. Efekt seviyesi Kapalı ya da hareketi azalt açıkken metin hemen görünür.</p>
      <fieldset>
        <legend>Ses</legend>
        <label className="appearance-option">
          <input
            type="checkbox"
            checked={settings.menuMusic}
            onChange={(event) => setSetting('menuMusic', event.currentTarget.checked)}
            data-testid="checkbox-menu-music"
          />
          <span>Ana menü müziği</span>
        </label>
      </fieldset>
      <fieldset>
        <legend>Okunabilirlik</legend>
        <label className="appearance-option">
          <input
            type="checkbox"
            checked={settings.highContrast}
            onChange={(event) => setSetting('highContrast', event.currentTarget.checked)}
            data-testid="checkbox-high-contrast"
          />
          <span>Yüksek kontrast</span>
        </label>
        <label className="appearance-option">
          <input
            type="checkbox"
            checked={settings.dyslexiaFont}
            onChange={(event) => setSetting('dyslexiaFont', event.currentTarget.checked)}
            data-testid="checkbox-dyslexia-font"
          />
          <span>Disleksi dostu yazı tipi</span>
        </label>
      </fieldset>
    </div>
  );
}
