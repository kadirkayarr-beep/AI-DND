import { SlidersHorizontal } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Anahtar, KitapDugme, SeciciGrup } from '@/components/kitap/kontroller';
import {
  EL_YAZISI_SECENEKLERI, GORUNUM_SECENEKLERI, SAYFA_DUZENI_SECENEKLERI, YAZI_BOYU_SECENEKLERI,
  type ElYazisi, type GorunumSecimi, type SayfaDuzeni, type YaziBoyu,
} from '@/lib/kitap-tema';
import './kitap.css';

/** lambaKaranlikta: G10, the reading lamp in the dark theme too; efektKapali: paper and cloth texture off. */
export interface ArayuzDegeri { gorunum: GorunumSecimi; duzen: SayfaDuzeni; el: ElYazisi; boy: YaziBoyu; lambaKaranlikta: boolean; efektKapali: boolean }

/** The "Arayüz" section of the settings (T3): appearance, page layout, hand, text size, lamp and texture (ui-polish 9). */
export function ArayuzAyarlari({ deger, degisince }: { deger: ArayuzDegeri; degisince: (d: ArayuzDegeri) => void }) {
  const el = EL_YAZISI_SECENEKLERI.map((s) => ({ ...s, etiket: <span className="kitap-el-ornek" data-kitap-el={s.deger}>{s.etiket}</span>, ad: `${s.etiket}, ${s.ad}` }));
  return (
    <section className="kitap-arayuz" aria-labelledby="kitap-arayuz-baslik">
      <h2 id="kitap-arayuz-baslik" className="kitap-arayuz-baslik">Arayüz</h2>
      <p className="kitap-etiket">Görünüm</p>
      <SeciciGrup etiket="Görünüm" deger={deger.gorunum} degisince={(gorunum) => degisince({ ...deger, gorunum })} secenekler={GORUNUM_SECENEKLERI} className="kitap-secici-gorunum" />
      <p className="kitap-etiket">Sayfa düzeni</p>
      <SeciciGrup etiket="Sayfa düzeni" deger={deger.duzen} degisince={(duzen) => degisince({ ...deger, duzen })} secenekler={SAYFA_DUZENI_SECENEKLERI} />
      <p className="kitap-etiket">El yazısı</p>
      <SeciciGrup etiket="El yazısı" deger={deger.el} degisince={(e) => degisince({ ...deger, el: e })} secenekler={el} />
      <p className="kitap-etiket">Yazı boyu</p>
      <SeciciGrup etiket="Yazı boyu" deger={deger.boy} degisince={(boy) => degisince({ ...deger, boy })} secenekler={YAZI_BOYU_SECENEKLERI} />
      <Anahtar etiket="Karanlık temada okuma lambası" acik={deger.lambaKaranlikta} degisince={(lambaKaranlikta) => degisince({ ...deger, lambaKaranlikta })} />
      <Anahtar etiket="Kâğıt dokusu" acik={!deger.efektKapali} degisince={(v) => degisince({ ...deger, efektKapali: !v })} />
    </section>
  );
}

/** Settings wheel on the desk: a small window under the button (popover.tsx; A0-5). */
export function AyarCarki({ deger, degisince }: { deger: ArayuzDegeri; degisince: (d: ArayuzDegeri) => void }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <KitapDugme tur="masa"><SlidersHorizontal aria-hidden="true" />Ayarlar</KitapDugme>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className="kitap-pusula">
        <ArayuzAyarlari deger={deger} degisince={degisince} />
      </PopoverContent>
    </Popover>
  );
}
