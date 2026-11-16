// A1 Oturum 2: the book's indicators. Each one shows only the values it is given: nothing here rolls, counts or
// guesses. A value that cannot be true (below zero, above the maximum, not a whole number) is shown as unreadable,
// never as a made-up number.
import { useEffect, useRef, type ReactNode } from 'react';
import { CircleAlert, X } from 'lucide-react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { BosSatirlar, Ipucu } from '@/components/kitap/kontroller';
import { CanMuhuruCizimi } from '@/components/kitap/cizimler/can-muhuru';
import { KenarSimge, type KenarSimgesi } from '@/components/kitap/cizimler/kenar-simgeleri';
import { Mum } from '@/components/kitap/cizimler/mum';
import './kitap.css';

const tamSayi = (n: unknown): n is number => typeof n === 'number' && Number.isInteger(n);

/** Health is valid only as whole numbers with 0 <= can <= enCok and enCok > 0. */
export function canGecerli(can: unknown, enCok: unknown): boolean {
  return tamSayi(can) && tamSayi(enCok) && enCok > 0 && can >= 0 && can <= enCok;
}

/** Cracks on the seal: none at full health, then one per third of the health lost, at most three (43/49 → 1). */
export function catlakSayisi(can: number, enCok: number): number {
  if (can >= enCok) return 0;
  return Math.min(3, Math.ceil((1 - can / enCok) * 3 - 1e-9));
}

export interface CanMuhruProps {
  can?: number;
  enCok?: number;
  basHarf: string;
  /** buyuk: the character page seal (84px); kucuk: the status strip seal (38px). */
  boy?: 'buyuk' | 'kucuk';
}

/** Health seal (draft principle 3): the seal is health, cracks show damage, the number stays written beside it. */
export function CanMuhru({ can, enCok, basHarf, boy = 'buyuk' }: CanMuhruProps) {
  const en = boy === 'buyuk' ? 84 : 38;
  const kutu = `kitap-muhur-kutu kitap-muhur-${boy}`;
  if (can === undefined && enCok === undefined) {
    return <div className={kutu}><CanMuhuruCizimi en={en} basHarf={basHarf} basilmamis etiket="Can mührü, henüz basılmadı" /></div>;
  }
  if (!canGecerli(can, enCok)) {
    return (
      <div className={kutu}>
        <CanMuhuruCizimi en={en} basHarf={basHarf} basilmamis etiket="Can mührü: can bilgisi okunamadı" />
        <span className="kitap-etiket" aria-hidden="true">okunamadı</span>
      </div>
    );
  }
  const catlak = catlakSayisi(can as number, enCok as number);
  const etiket = `Can mührü: ${can} / ${enCok} can, ${catlak ? `${catlak} çatlak` : 'çatlak yok'}`;
  return (
    <div className={kutu}>
      <CanMuhuruCizimi en={en} basHarf={basHarf} catlak={catlak} etiket={etiket} />
      <span className="kitap-muhur-yazi" aria-hidden="true">
        <span className="kitap-muhur-sayi">{can} / {enCok}</span>
        {boy === 'buyuk' ? <span className="kitap-etiket">can</span> : null}
      </span>
    </div>
  );
}

export interface YuvaSeviyesi { seviye: number; toplam: number; dolu: number }

const yuvaGecerli = (s: YuvaSeviyesi) => tamSayi(s.toplam) && tamSayi(s.dolu) && s.toplam > 0 && s.dolu >= 0 && s.dolu <= s.toplam;

/** What a screen reader and the hint say for one level (conflict 25): the slots left, never shown as text on the page. */
export function yuvaOzeti(s: YuvaSeviyesi): string {
  return yuvaGecerli(s) ? `${s.seviye}. seviye: kalan yuva ${s.dolu} / ${s.toplam}` : `${s.seviye}. seviye: yuva bilgisi okunamadı`;
}

function Mumlar({ s, en }: { s: YuvaSeviyesi; en: number }) {
  return (
    <>
      {Array.from({ length: s.toplam }, (_, i) => <Mum key={i} yanan={i < s.dolu} en={en} />)}
    </>
  );
}

/**
 * Spell slots as candles (draft principle 3): lit is a slot left, out is a spent one. One short row per level with
 * only the level name under it (T12); each row takes focus and shows the slots left in a hint. The hint repeats the
 * name for sight only: the row drops the tooltip's aria-describedby so a screen reader says it once.
 */
export function BuyuYuvalari({ seviyeler }: { seviyeler: ReadonlyArray<YuvaSeviyesi> }) {
  if (seviyeler.length === 0) return <BosSatirlar satir={1} etiket="Büyü yuvası yok" />;
  return (
    <TooltipProvider delayDuration={150}>
      <div className="kitap-yuvalar" role="group" aria-label="Büyü yuvaları">
        {seviyeler.map((s) => (
          <Ipucu key={s.seviye} metin={yuvaOzeti(s)}>
            <div className="kitap-yuva" role="img" tabIndex={0} aria-label={yuvaOzeti(s)} aria-describedby={undefined}>
              <div className={`kitap-raf${yuvaGecerli(s) ? '' : ' kitap-raf-bos'}`}>{yuvaGecerli(s) ? <Mumlar s={s} en={24} /> : <span className="kitap-etiket">okunamadı</span>}</div>
              <span className="kitap-etiket">{s.seviye}. seviye</span>
            </div>
          </Ipucu>
        ))}
      </div>
    </TooltipProvider>
  );
}

/** The status strip over the right page (target picture 01): small candles per level, the small seal, the number. */
export function DurumSeridi({ seviyeler, can, enCok, basHarf }: { seviyeler: ReadonlyArray<YuvaSeviyesi>; can: number; enCok: number; basHarf: string }) {
  const gecerli = canGecerli(can, enCok);
  const ad = ['Durum: ' + (gecerli ? `can ${can} / ${enCok}` : 'can bilgisi okunamadı'), ...seviyeler.map(yuvaOzeti)].join('; ');
  return (
    <div className="kitap-durum" role="img" aria-label={ad}>
      {seviyeler.map((s) => (yuvaGecerli(s)
        ? <div key={s.seviye} className="kitap-durum-mumlar"><Mumlar s={s} en={11} /></div>
        : <span key={s.seviye} className="kitap-etiket">okunamadı</span>))}
      <CanMuhuruCizimi en={38} basHarf={basHarf} basilmamis={!gecerli} catlak={gecerli ? catlakSayisi(can, enCok) : 0} />
      {gecerli ? <span className="kitap-muhur-sayi">{can} / {enCok}</span> : <span className="kitap-etiket">okunamadı</span>}
    </div>
  );
}

export type ZarYuzu = 4 | 6 | 8 | 10 | 12 | 20;

// Die outlines in a 48-unit box, drawn here in code (the draft has no die drawing); colours come from kitap.css tokens.
// Facet lines only where they clear the number: the d20 face triangle holds it (its base on the lower corners), the d10
// has the V of its lower faces under the number, so it no longer reads as the d8 diamond (review 3).
const ZAR_BICIMI: Record<ZarYuzu, { dis: ReactNode; ic?: string; y: number }> = {
  4: { dis: <path d="M24 5L44.5 40.5H3.5Z" />, y: 31 },
  6: { dis: <rect x="6" y="6" width="36" height="36" rx="5" />, y: 24 },
  8: { dis: <path d="M24 3L44 24L24 45L4 24Z" />, y: 24 },
  10: { dis: <path d="M24 3L44.5 20L24 45L3.5 20Z" />, ic: 'M3.5 20L24 30L44.5 20M24 30V45', y: 18 },
  12: { dis: <path d="M24 3.5L44.5 18.4L36.7 42.5H11.3L3.5 18.4Z" />, y: 25 },
  20: { dis: <path d="M24 2.5L42.6 13.2V34.8L24 45.5L5.4 34.8V13.2Z" />, ic: 'M24 5L42.6 34.8H5.4Z', y: 27.5 },
};

/** A die (A1): drawn in SVG; it shows the value it is given and nothing else. It never rolls. */
export function Zar({ yuz, deger, disabled, en = 48 }: { yuz: ZarYuzu; deger?: number; disabled?: boolean; en?: number }) {
  const bicim = ZAR_BICIMI[yuz];
  const gecerli = deger !== undefined && tamSayi(deger) && deger >= 1 && deger <= yuz;
  const ad = (deger === undefined ? `d${yuz} zarı, atılmadı` : gecerli ? `d${yuz} zarı: ${deger}` : `d${yuz} zarı: değer okunamadı`) + (disabled ? ', devre dışı' : '');
  const durum = deger === undefined ? ' kitap-zar-bos' : gecerli ? '' : ' kitap-zar-hata';
  return (
    <svg width={en} height={en} viewBox="0 0 48 48" role="img" aria-label={ad} className={`kitap-zar${durum}${disabled ? ' kitap-zar-devre-disi' : ''}`}>
      <g className="kitap-zar-yuz">{bicim.dis}</g>
      {bicim.ic ? <path className="kitap-zar-ic" d={bicim.ic} /> : null}
      {deger !== undefined && !gecerli ? (
        <g className="kitap-zar-uyari"><circle cx="24" cy="24" r="8" /><path d="M24 19.6V25M24 28.2V28.4" /></g>
      ) : null}
      {gecerli ? <text className="kitap-zar-sayi" x="24" y={bicim.y} textAnchor="middle" dominantBaseline="central">{deger}</text> : null}
    </svg>
  );
}

/** Margin note (draft principle 1): what the rules say, green and italic with a small icon; gold when new. */
export function KenarNotu({ simge, yeni, silik, children }: { simge: KenarSimgesi; yeni?: boolean; silik?: boolean; children: ReactNode }) {
  return (
    <p className={`kitap-kenar-metin kitap-kenar${yeni ? ' kitap-kenar-yeni' : ''}${silik ? ' kitap-kenar-silik' : ''}`}>
      <KenarSimge ad={simge} />
      <span>{children}</span>
    </p>
  );
}

export const KAYIT_SURESI = 2600;
export type KayitDurumu = 'kaydedildi' | 'hata';

/**
 * Save notice in the desk row (A0-7), with the ribbon mark (Kadir picked it over the seal, conflict 24: the seal read as
 * health). A save fades by itself after KAYIT_SURESI; an error stays, is announced at once and offers a way out:
 * "Tekrar dene" when the caller can retry, and always a close button. `kimlik` changes with every save, so a second
 * save restarts the fade and is read again.
 */
export function KayitBildirimi({ durum, kimlik = 0, kapat, tekrar }: { durum?: KayitDurumu; kimlik?: number; kapat: () => void; tekrar?: () => void }) {
  const kapatRef = useRef(kapat);
  kapatRef.current = kapat;
  const kutu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (durum !== 'kaydedildi') return undefined;
    const zaman = setTimeout(() => kapatRef.current(), KAYIT_SURESI);
    return () => clearTimeout(zaman);
  }, [durum, kimlik]);
  // A pressed button leaves the page (close empties the notice, a retry turns it into a save), so focus moves to the
  // notice itself, which stays; otherwise it would fall back to the top of the page.
  const basinca = (f: () => void) => () => {
    kutu.current?.focus();
    f();
  };
  return (
    <div ref={kutu} tabIndex={-1} className="kitap-kayit" data-durum={durum ?? 'bos'}>
      {/* Only the words are live; the buttons sit beside the live region so it reads "Kaydedilemedi" alone. */}
      <div role="status" aria-live={durum === 'hata' ? 'assertive' : 'polite'} className="kitap-kayit-canli">
        {durum ? (
          <span key={kimlik} className="kitap-kayit-fis">
            {durum === 'hata' ? <CircleAlert className="kitap-kayit-hata-simge" aria-hidden="true" /> : <span className="kitap-kayit-kurdele-isaret" aria-hidden="true" />}
            <span>{durum === 'hata' ? 'Kaydedilemedi' : 'Kaydedildi'}</span>
          </span>
        ) : null}
      </div>
      {durum === 'hata' ? (
        <span className="kitap-kayit-eylem">
          {tekrar ? <button type="button" className="kitap-kayit-dugme" onClick={basinca(tekrar)}>Tekrar dene</button> : null}
          <button type="button" className="kitap-kayit-kapat" aria-label="Kapat" onClick={basinca(kapat)}><X aria-hidden="true" /></button>
        </span>
      ) : null}
    </div>
  );
}
