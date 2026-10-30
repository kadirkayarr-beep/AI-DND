import { useRef, useState } from 'react';
import type { CombatActionInput, GameState } from '@workspace/api-client-react';

type Casting = GameState['spellcasting'];
type Option = { slot_level: number; points_gained: number; available: boolean; reason: string | null };
function conversionOptions(spellcasting: Casting): Option[] | null {
  const projection = spellcasting?.convert_spell_slot;
  if (!spellcasting?.sorcery_points || !Array.isArray(projection?.options)) return null;
  const options = projection.options;
  if (!options.every((item: Option) => item && [1, 2, 3].includes(item.slot_level)
    && Number.isSafeInteger(item.points_gained) && item.points_gained > 0 && typeof item.available === 'boolean'
    && (item.reason === null || typeof item.reason === 'string'))
    || new Set(options.map((item: Option) => item.slot_level)).size !== options.length) return null;
  return options;
}

export function SpellSlotConversionChoice({ spellcasting, slot, onSlotChange, blocked, onCommand }: {
  spellcasting: Casting; slot: string; onSlotChange: (slot: string) => void; blocked: boolean;
  onCommand: (message: string, command: CombatActionInput) => void;
}) {
  const options = conversionOptions(spellcasting);
  if (!options) return null;
  const offered = options.filter(option => Object.hasOwn(spellcasting!.slots, String(option.slot_level)));
  const selected = offered.find(option => String(option.slot_level) === slot);
  const enabled = !blocked && selected?.available === true && (spellcasting!.slots[slot] ?? 0) > 0;
  return <div className="mt-3" data-testid="spell-slot-conversion">
    <h3 className="dnd-kicker">Font of Magic · yuva → puan</h3>
    <label>Büyü yuvası <select data-testid="select-convert-spell-slot" value={slot} disabled={blocked} onChange={event => {
      if (!blocked && (event.target.value === '' || offered.some(option => String(option.slot_level) === event.target.value))) onSlotChange(event.target.value);
    }}><option value="">Yuva seç</option>{offered.map(option => <option key={option.slot_level} value={String(option.slot_level)}>
      {option.slot_level}. seviye · kalan {spellcasting!.slots[String(option.slot_level)]} · +{option.points_gained} puan
    </option>)}</select></label>
    {selected?.reason && <p role="status">Dönüştürme kullanılamıyor: {selected.reason}</p>}
    <button type="button" className="action-suggestion" data-testid="button-convert-spell-slot" disabled={!enabled} onClick={() => {
      if (!enabled || !selected) return;
      onCommand('Büyü yuvasını Sorcery Points puanına dönüştürüyorum.', { steps: [{ kind: 'convert_spell_slot', slot_level: selected.slot_level }] });
    }}>Seçili yuvayı puana dönüştür · Action gerektirmez</button>
    <p className="subtle-text">Bir büyü yuvası harcanır; Action veya Bonus Action harcanmaz. Yalnızca puan sınırını aşmayan yuva → puan dönüşümü desteklenir. Puanlardan yeni yuva oluşturma desteklenmiyor.</p>
  </div>;
}

/** Draft selection only. The existing turn owner holds identity, pending requests and retries. */
export function createConversionDraft() {
  let key = ''; let slot = '';
  return { get slot() { return slot; }, sync(next: string) { if (key !== next) slot = ''; key = next; }, choose(value: string) { slot = value; } };
}

export function SpellSlotConversionControl({ spellcasting, decisionScope, blocked, onCommand }: {
  spellcasting: Casting; decisionScope: string; blocked: boolean; onCommand: (message: string, command: CombatActionInput) => void;
}) {
  const ref = useRef<ReturnType<typeof createConversionDraft> | null>(null);
  if (!ref.current) ref.current = createConversionDraft();
  const draft = ref.current;
  const [, redraw] = useState(0);
  draft.sync(JSON.stringify([decisionScope, blocked, spellcasting?.slots, spellcasting?.sorcery_points, conversionOptions(spellcasting)]));
  return <SpellSlotConversionChoice spellcasting={spellcasting} slot={draft.slot} blocked={blocked}
    onSlotChange={value => { draft.choose(value); redraw(n => n + 1); }} onCommand={(message, command) => {
      draft.choose(''); redraw(n => n + 1); onCommand(message, command);
    }} />;
}
