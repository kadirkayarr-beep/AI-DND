import { ChevronDown, RotateCcw, Type } from 'lucide-react';
import {
  DEFAULT_READING_PREFERENCES,
  type ReadingPreferences,
} from '@/lib/reading-preferences';
import './reading-settings.css';

export function ReadingSettings({
  value,
  onChange,
}: {
  value: ReadingPreferences;
  onChange: (next: ReadingPreferences) => void;
}) {
  const isDefault = value.fontSizePx === null && value.lineHeight === null;

  return (
    <details className="reading-settings" data-testid="reading-settings">
      <summary aria-label="Okuma ayarları">
        <Type size={15} aria-hidden="true" />
        <span>Aa</span>
        <ChevronDown size={13} aria-hidden="true" />
      </summary>
      <div className="reading-settings__panel" role="group" aria-label="Anlatı görünümü">
        <label className="reading-settings__control" htmlFor="reading-font-size">
          <span className="reading-settings__label">Anlatı yazı boyutu</span>
          <output htmlFor="reading-font-size">
            {value.fontSizePx === null ? 'Varsayılan' : `${value.fontSizePx} px`}
          </output>
          <input
            id="reading-font-size"
            type="range"
            min="18"
            max="32"
            step="1"
            value={value.fontSizePx ?? 24}
            aria-label="Anlatı yazı boyutu"
            onChange={(event) => onChange({ ...value, fontSizePx: Number(event.currentTarget.value) })}
          />
        </label>
        <label className="reading-settings__control" htmlFor="reading-line-height">
          <span className="reading-settings__label">Satır aralığı</span>
          <output htmlFor="reading-line-height">
            {value.lineHeight === null ? 'Varsayılan' : value.lineHeight.toFixed(2)}
          </output>
          <input
            id="reading-line-height"
            type="range"
            min="1.3"
            max="2"
            step="0.02"
            value={value.lineHeight ?? 1.68}
            aria-label="Anlatı satır aralığı"
            onChange={(event) => onChange({ ...value, lineHeight: Number(event.currentTarget.value) })}
          />
        </label>
        <button
          className="reading-settings__reset"
          type="button"
          disabled={isDefault}
          onClick={() => onChange({ ...DEFAULT_READING_PREFERENCES })}
        >
          <RotateCcw size={13} aria-hidden="true" />
          Varsayılana dön
        </button>
      </div>
    </details>
  );
}
