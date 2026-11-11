import { useAppearance } from '@/components/appearance-provider';
import type { EffectsLevel } from '@/lib/appearance-settings';
import './appearance-settings-panel.css';

const LEVELS: ReadonlyArray<{ value: EffectsLevel; label: string }> = [
  { value: 'off', label: 'Kapalı' },
  { value: 'low', label: 'Az' },
  { value: 'full', label: 'Tam' },
];

export function AppearanceSettingsPanel() {
  const { settings, setSetting } = useAppearance();
  return (
    <div className="appearance-settings" data-testid="appearance-settings-panel">
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
    </div>
  );
}
