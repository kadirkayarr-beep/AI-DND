import type { KeyboardEvent } from 'react';
import { Mic } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';
import { Toggle } from '@/components/ui/toggle';
import { KalemUcu } from '@/components/kitap/cizimler/kalem-ucu';
import { KitapDugme, SeciciGrup } from '@/components/kitap/kontroller';
import './kitap.css';

export type YazmaKipi = 'yap' | 'soyle' | 'sor';
const KIPLER: ReadonlyArray<{ deger: YazmaKipi; etiket: string }> = [
  { deger: 'yap', etiket: 'yap' },
  { deger: 'soyle', etiket: 'söyle' },
  { deger: 'sor', etiket: 'anlatıcıya sor' },
];

/** Microphone toggle (toggle.tsx); not rendered when the browser cannot listen. */
export function Mikrofon({ destek, dinliyor, degisince, disabled }: { destek: boolean; dinliyor: boolean; degisince: (v: boolean) => void; disabled?: boolean }) {
  if (!destek) return null;
  return (
    <Toggle pressed={dinliyor} onPressedChange={degisince} disabled={disabled} aria-label="Sesle yaz" className="kitap-dugme kitap-dugme-kare kitap-mikrofon">
      <Mic aria-hidden="true" />
    </Toggle>
  );
}

/** Writing line: pen nib, gold rule, the player's hand; three modes below; microphone left of Gönder. */
export function YazmaAlani({ kip, kipDegisince, metin, metinDegisince, gonder, mikrofonDestegi, dinliyor = false, dinlemeDegisince = () => {}, disabled }: {
  kip: YazmaKipi; kipDegisince: (k: YazmaKipi) => void; metin: string; metinDegisince: (v: string) => void; gonder: () => void;
  mikrofonDestegi: boolean; dinliyor?: boolean; dinlemeDegisince?: (v: boolean) => void; disabled?: boolean;
}) {
  const yolla = (e?: { preventDefault(): void }) => { e?.preventDefault(); if (metin.trim() && !disabled) gonder(); };
  const tus = (e: KeyboardEvent<HTMLTextAreaElement>) => { if (e.key === 'Enter' && !e.shiftKey) yolla(e); };
  return (
    <form className="kitap-yaz" onSubmit={yolla}>
      <div className="kitap-yaz-sira">
        <KalemUcu />
        <Textarea rows={1} value={metin} onChange={(e) => metinDegisince(e.target.value)} onKeyDown={tus} disabled={disabled}
          aria-label="Ne yapıyorsun?" placeholder="Ne yapıyorsun?" className="kitap-yaz-girdi" />
        <Mikrofon destek={mikrofonDestegi} dinliyor={dinliyor} degisince={dinlemeDegisince} disabled={disabled} />
        <KitapDugme tur="ana" type="submit" disabled={disabled}>Gönder</KitapDugme>
      </div>
      <SeciciGrup etiket="Söyleyiş biçimi" tur="cizgi" deger={kip} degisince={kipDegisince} secenekler={KIPLER} className="kitap-kipler" />
    </form>
  );
}
