import type { ReactNode } from 'react';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Kurdele } from '@/components/kitap/cizimler/kurdele';
import type { ElYazisi, KitapTemasi, YaziBoyu } from '@/lib/kitap-tema';
import './kitap.css';

export interface KitapKabuguProps {
  tema: KitapTemasi;
  el?: ElYazisi;
  boy?: YaziBoyu;
  efektKapali?: boolean;
  /** Desk row above the book: theme and settings buttons on the left. */
  masa?: ReactNode;
  sol: ReactNode;
  sag: ReactNode;
  /** Below 760px only one page fits (decision G6); this one stays, the other hides. */
  darEkranSayfasi?: 'sol' | 'sag';
  kurdeleEtiketi?: string;
}

/** Open book: cloth cover, two pages with a spine curve and a page stack, the ribbon down the middle (T1). */
export function KitapKabugu({ tema, el = 'b', boy = 'normal', efektKapali = false, masa, sol, sag, darEkranSayfasi = 'sol', kurdeleEtiketi }: KitapKabuguProps) {
  const gizli = (taraf: 'sol' | 'sag') => (darEkranSayfasi === taraf ? '' : ' kitap-darda-gizli');
  return (
    <div className="kitap-masa" data-kitap-tema={tema} data-kitap-el={el} data-kitap-boy={boy} data-kitap-efekt={efektKapali ? 'kapali' : 'acik'}>
      {masa ? <div className="kitap-masa-ust">{masa}</div> : null}
      <div className="kitap-cilt">
        <div className="kitap-sayfalar">
          <section className={`kitap-sayfa kitap-sayfa-sol${gizli('sol')}`}>
            <div className="kitap-tane" aria-hidden="true" />
            <div className="kitap-sayfa-ic">{sol}</div>
          </section>
          <Kurdele etiket={kurdeleEtiketi} />
          <section className={`kitap-sayfa kitap-sayfa-sag${gizli('sag')}`}>
            <div className="kitap-tane" aria-hidden="true" />
            <div className="kitap-sayfa-ic">{sag}</div>
          </section>
        </div>
      </div>
    </div>
  );
}

export interface Ayrac { deger: string; etiket: string }

/**
 * Bookmark tabs sticking out over the top edge of the page (T2), on tabs.tsx: arrow keys move between them
 * (Radix roving focus) and the open one is announced as selected. The book goes in as children so the
 * matching TabsContent can sit on its page. With tabs, the desk row goes in here (masa) so focus order follows the eye.
 */
export function Ayraclar({ deger, degisince, ayraclar, masa, children }: { deger: string; degisince: (deger: string) => void; ayraclar: ReadonlyArray<Ayrac>; masa?: ReactNode; children?: ReactNode }) {
  return (
    <Tabs value={deger} onValueChange={degisince} className="kitap-ayrac-kok" activationMode="automatic">
      {/* The desk buttons sit top left, before the tabs in reading and focus order. */}
      {masa ? <div className="kitap-masa-ust">{masa}</div> : null}
      <TabsList className="kitap-ayraclar" aria-label="Defter ayraçları">
        {ayraclar.map((a) => (
          <TabsTrigger key={a.deger} value={a.deger} className="kitap-ayrac">{a.etiket}</TabsTrigger>
        ))}
      </TabsList>
      {children}
    </Tabs>
  );
}
