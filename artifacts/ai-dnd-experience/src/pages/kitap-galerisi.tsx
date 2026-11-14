// A1 gallery: the book theme set on one page, for Kadir's approval from screenshots. Development only (see
// app-shell.tsx); the sample text is gallery data, not game text. Query string for screenshots:
// ?gorunum=gunduz|gece|karanlik|saat, ?saat=gunduz|gece.
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { toast } from 'sonner';
import { Clock, Moon, Plus, Sun } from 'lucide-react';
import { TabsContent } from '@/components/ui/tabs';
import { Ayraclar, KitapKabugu } from '@/components/kitap/kitap-kabugu';
import { ArayuzAyarlari, AyarCarki, type ArayuzDegeri } from '@/components/kitap/arayuz-ayarlari';
import {
  AcilirListe, Anahtar, BildirimAlani, BolumBasligi, BosSatirlar, Ipucu, KitapDugme, OnayKutusu, Pencere, Rozet,
  SayiKutusu, Sayac, SecimKartlari, SeciciGrup, Yukleniyor,
} from '@/components/kitap/kontroller';
import { Mikrofon, YazmaAlani, type YazmaKipi } from '@/components/kitap/yazma-alani';
import { useIsMobile } from '@/hooks/use-mobile';
import { GORUNUM_SECENEKLERI, VARSAYILAN_EL, VARSAYILAN_GORUNUM, hikayeTekAkista, kitapTemasi, type GorunumSecimi, type HikayeSaati } from '@/lib/kitap-tema';

const AYRACLAR = [
  { deger: 'hikaye', etiket: 'Hikâye' }, { deger: 'karakter', etiket: 'Karakter' }, { deger: 'canta', etiket: 'Çanta' },
  { deger: 'dunya', etiket: 'Dünya' }, { deger: 'gunluk', etiket: 'Günlük' },
];
const TURLER = [
  { deger: 'insan', baslik: 'İnsan', aciklama: 'Becerikli, her işe uyar.' },
  { deger: 'ejderhasoyu', baslik: 'Ejderhasoyu', aciklama: 'Kanında ejder ateşi var.', ayrinti: 'Nefes silahı, ateşe direnç' },
  { deger: 'cuce', baslik: 'Cüce', aciklama: 'Taşa ve zehre dayanıklı.' },
];
const ZARLAR = [{ deger: 'kemik', etiket: 'Kemik' }, { deger: 'obsidyen', etiket: 'Obsidyen' }];
const TURKCE = 'Çığlık, ağaç, öğüt; İzmir ılık, şiş yağlı. ÇĞIİÖŞÜ çğıiöşü 43 / 49';

function sorgu(ad: string): string | null {
  return typeof window === 'undefined' ? null : new URLSearchParams(window.location.search).get(ad);
}

function Ornek({ ad, children }: { ad: string; children: ReactNode }) {
  return (
    <div className="kitap-ornek">
      <p className="kitap-ornek-ad">{ad}</p>
      <div className="kitap-ornek-ic">{children}</div>
    </div>
  );
}

function Parca({ baslik, children }: { baslik: string; children: ReactNode }) {
  return (
    <section className="kitap-parca" aria-label={baslik}>
      <BolumBasligi duzey={3}>{baslik}</BolumBasligi>
      <div className="kitap-parca-ornekler">{children}</div>
    </section>
  );
}

export default function KitapGalerisi() {
  const ilkGorunum = GORUNUM_SECENEKLERI.some((s) => s.deger === sorgu('gorunum')) ? (sorgu('gorunum') as GorunumSecimi) : VARSAYILAN_GORUNUM;
  const [ayar, setAyar] = useState<ArayuzDegeri>({ gorunum: ilkGorunum, duzen: 'iki-sayfa', el: VARSAYILAN_EL, boy: 'normal' });
  const [saat, setSaat] = useState<HikayeSaati>(sorgu('saat') === 'gunduz' ? 'gunduz' : 'gece');
  const [efektKapali, setEfektKapali] = useState(false);
  const [ayrac, setAyrac] = useState('hikaye');
  const [kip, setKip] = useState<YazmaKipi>('yap');
  const [metin, setMetin] = useState('');
  const [liste, setListe] = useState<string | undefined>(undefined);
  const [tur, setTur] = useState('ejderhasoyu');
  const [onay, setOnay] = useState(true);
  const [anahtar, setAnahtar] = useState(false);
  const [sayac, setSayac] = useState(2);
  const [kuvvet, setKuvvet] = useState('15');
  const [pencere, setPencere] = useState(false);
  const [dinliyor, setDinliyor] = useState(false);
  const [lambaKaranlikta, setLambaKaranlikta] = useState(sorgu('lamba') === 'acik');
  const tema = kitapTemasi(ayar.gorunum, saat);
  const tekAkis = hikayeTekAkista(ayrac, useIsMobile());
  // T5: in one flow the left page opens on the last lines, right above the writing field.
  const solAkis = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (tekAkis && solAkis.current) solAkis.current.scrollTop = solAkis.current.scrollHeight;
  }, [tekAkis, ayrac]);

  // Portalled windows, lists and notices render under <body>, so the attributes go on <html> while the gallery is open.
  useEffect(() => {
    const kok = document.documentElement;
    const nitelikler = { 'data-kitap-tema': tema, 'data-kitap-el': ayar.el, 'data-kitap-boy': ayar.boy, 'data-kitap-efekt': efektKapali ? 'kapali' : 'acik' };
    for (const [ad, deger] of Object.entries(nitelikler)) kok.setAttribute(ad, deger);
    return () => { for (const ad of Object.keys(nitelikler)) kok.removeAttribute(ad); };
  }, [tema, ayar.el, ayar.boy, efektKapali]);

  // The fake story clock only drives the look while "Hikâyedeki saati izle" is chosen; a hand-picked look offers the
  // way back to the clock instead (review 15).
  const saatDugmesi = ayar.gorunum === 'saat' ? (
    <KitapDugme tur="masa" onClick={() => setSaat(saat === 'gece' ? 'gunduz' : 'gece')} aria-label={saat === 'gece' ? 'Gündüze çevir' : 'Geceye çevir'}>
      {saat === 'gece' ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
      <span className="kitap-dar-gizli">{saat === 'gece' ? 'Gündüze çevir' : 'Geceye çevir'}</span>
    </KitapDugme>
  ) : (
    <KitapDugme tur="masa" onClick={() => setAyar({ ...ayar, gorunum: 'saat' })} aria-label="Saate dön">
      <Clock aria-hidden="true" />
      <span className="kitap-dar-gizli">Saate dön</span>
    </KitapDugme>
  );

  // Story lines of the sample scene: the first part fills the left page, the rest continues on the right.
  const ilkBolum = (
    <>
      <div className="kitap-satir">
        <p className="kitap-p kitap-ilk">Yağmur damdan sızıyor; mum alevi her damlada eğiliyor. Masanın öbür ucundaki kadın, eldivenini çıkarmadan bıçağını bileğine sürüyor.</p>
        <p className="kitap-kenar-metin">Kesende 12 gümüş var.</p>
      </div>
      <p className="kitap-soz">Yanına oturup adını soruyorum.</p>
      <div className="kitap-satir">
        <p className="kitap-p">“Adımı soran ya borçludur ya ölü,” diyor, gözünü kapıdan ayırmadan. “Sen hangisisin?”</p>
        <p className="kitap-kenar-metin">Sezgi zarı 13, zorluk 12. Yalan söylemiyor.</p>
      </div>
      <div className="kitap-satir">
        <p className="kitap-soz kitap-soz-silik">Bıçağıma uzanıyorum.</p>
        <p className="kitap-kenar-metin">Geri alındı.</p>
      </div>
      <p className="kitap-soz">Ona bir kadeh şarap ısmarlıyorum.</p>
      <p className="kitap-p">Kadeh önüne gelince ilk kez gülümsüyor. Dişlerinden biri altın; öbürleri kırık. “Kuzey yolunda <span className="kitap-ad">Varka</span>’nın adamları bekliyor,” diye fısıldıyor.</p>
    </>
  );
  const sonBolum = (
    <>
      <p className="kitap-soz">“Kaç kişiler?”</p>
      <div className="kitap-satir">
        <p className="kitap-p">“Dört. Belki beş. Biri tazı besliyor; tazıdan kork, adamdan değil.” Kadehini dibine kadar içiyor ve kalkıyor.</p>
        <p className="kitap-kenar-metin">Yol tarifi günlüğe yazıldı.</p>
      </div>
    </>
  );
  const yazmaAlani = (
    <YazmaAlani kip={kip} kipDegisince={setKip} metin={metin} metinDegisince={setMetin} gonder={() => setMetin('')}
      mikrofonDestegi dinliyor={dinliyor} dinlemeDegisince={setDinliyor} />
  );

  const sol = (
    <>
      <BolumBasligi yan={`3 Mirtul 1501, ${saat === 'gece' ? 'gece yarısı' : 'öğle'}`}>Kırık Fener Meyhanesi</BolumBasligi>
      <div className="kitap-akis" ref={solAkis}>
        {ilkBolum}
        {tekAkis ? sonBolum : null}
      </div>
      {tekAkis ? yazmaAlani : null}
      <p className="kitap-sayfa-no">51</p>
    </>
  );

  const sag = (
    <>
      <TabsContent value="hikaye" className="kitap-ayrac-icerik">
        {tekAkis ? null : (
          <>
            <BolumBasligi yan={<Rozet tur="yeni">Yeni iş</Rozet>}><span className="kitap-kucuk-bas">Ilsa, 3. seviye</span></BolumBasligi>
            <div className="kitap-akis">{sonBolum}</div>
            {yazmaAlani}
          </>
        )}
      </TabsContent>
      {AYRACLAR.slice(1).map((a) => (
        <TabsContent key={a.deger} value={a.deger} className="kitap-ayrac-icerik">
          <BolumBasligi yan="A2'de yazılacak">{a.etiket}</BolumBasligi>
          <BosSatirlar satir={8} etiket="Henüz yazılmadı" />
        </TabsContent>
      ))}
      <p className="kitap-sayfa-no">52</p>
    </>
  );

  return (
    <div className="kitap-galeri" data-kitap-tema={tema} data-kitap-el={ayar.el} data-kitap-boy={ayar.boy} data-kitap-efekt={efektKapali ? 'kapali' : 'acik'}>
      <h1 className="kitap-gizli">Unwritten kitap teması: galeri</h1>
      <Ayraclar deger={ayrac} degisince={setAyrac} ayraclar={AYRACLAR}
        masa={<>{saatDugmesi}<span className="kitap-dar-yok"><AyarCarki deger={ayar} degisince={setAyar} /></span></>}>
        <KitapKabugu tema={tema} el={ayar.el} boy={ayar.boy} efektKapali={efektKapali} sol={sol} sag={sag} darEkranSayfasi={ayrac === 'hikaye' ? 'sol' : 'sag'} lambaKaranlikta={lambaKaranlikta} />
      </Ayraclar>

      <div className="kitap-galeri-set">
        <div className="kitap-tane" aria-hidden="true" />
        <BolumBasligi yan="Oturum 1: temel kontroller ve okuma lambası. Mühür, mum, zar ve kenar notu Oturum 2'de.">Kontrol seti</BolumBasligi>

        <Parca baslik="Arayüz ayarları (seçici düğme grupları)">
          <Ornek ad="dolu"><ArayuzAyarlari deger={ayar} degisince={setAyar} /></Ornek>
          <Ornek ad="devre dışı">
            <SeciciGrup etiket="Yazı boyu, devre dışı" deger="normal" degisince={() => {}} disabled secenekler={[{ deger: 'normal', etiket: 'Normal' }, { deger: 'buyuk', etiket: 'Büyük' }]} />
          </Ornek>
          <Ornek ad="odak">
            {/* Radix puts an inline outline: none on the group root, so the shown ring sits on a wrapper. */}
            <div className="kitap-odak-goster">
              <SeciciGrup etiket="Sayfa düzeni, odak örneği" deger="iki-sayfa" degisince={() => {}} secenekler={[{ deger: 'iki-sayfa', etiket: 'İki sayfa hikâye' }, { deger: 'karakter-acik', etiket: 'Karakter açık' }]} />
            </div>
          </Ornek>
          <Ornek ad="G10: karanlıkta lamba (karar senin)">
            <Anahtar etiket="Karanlık temada okuma lambası" acik={lambaKaranlikta} degisince={setLambaKaranlikta} />
          </Ornek>
          <Ornek ad="efekt">
            <Anahtar etiket="Kâğıt dokusu" acik={!efektKapali} degisince={(v) => setEfektKapali(!v)} />
          </Ornek>
        </Parca>

        <Parca baslik="Düğme">
          <Ornek ad="ana"><KitapDugme tur="ana">Gönder</KitapDugme></Ornek>
          <Ornek ad="ikinci"><KitapDugme>Rastgele seç</KitapDugme></Ornek>
          <Ornek ad="kare"><KitapDugme tur="kare" aria-label="Ekle"><Plus aria-hidden="true" /></KitapDugme></Ornek>
          <Ornek ad="devre dışı"><KitapDugme tur="ana" disabled>Gönder</KitapDugme> <KitapDugme disabled>Rastgele seç</KitapDugme></Ornek>
          <Ornek ad="odak"><KitapDugme tur="ana" className="kitap-odak-goster">Sınıfa geç</KitapDugme></Ornek>
        </Parca>

        <Parca baslik="Açılır liste">
          <Ornek ad="boş"><AcilirListe etiket="Zar takımı" deger={liste} degisince={setListe} secenekler={ZARLAR} /></Ornek>
          <Ornek ad="dolu"><AcilirListe etiket="Zar takımı" deger="kemik" degisince={() => {}} secenekler={ZARLAR} /></Ornek>
          <Ornek ad="devre dışı"><AcilirListe etiket="Zar takımı" deger="obsidyen" degisince={() => {}} secenekler={ZARLAR} disabled /></Ornek>
        </Parca>

        <Parca baslik="Onay kutusu ve anahtar">
          <Ornek ad="dolu"><OnayKutusu etiket="Zarları göster" isaretli={onay} degisince={setOnay} /></Ornek>
          <Ornek ad="boş"><OnayKutusu etiket="Savaş özetini aç" isaretli={false} degisince={() => {}} /></Ornek>
          <Ornek ad="devre dışı"><OnayKutusu etiket="Otomatik kayıt" isaretli disabled degisince={() => {}} /></Ornek>
          <Ornek ad="anahtar"><Anahtar etiket="Müzik" acik={anahtar} degisince={setAnahtar} /> <Anahtar etiket="Ses" acik degisince={() => {}} /></Ornek>
          <Ornek ad="anahtar, devre dışı"><Anahtar etiket="Anlatıcı sesi" acik={false} disabled degisince={() => {}} /></Ornek>
        </Parca>

        <Parca baslik="Seçim kartı">
          <Ornek ad="seçili ve boş"><SecimKartlari etiket="Tür" deger={tur} degisince={setTur} secenekler={TURLER} /></Ornek>
          <Ornek ad="devre dışı"><SecimKartlari etiket="Tür, devre dışı" deger={undefined} degisince={() => {}} disabled secenekler={TURLER.slice(0, 2)} /></Ornek>
        </Parca>

        <Parca baslik="Sayaç, rozet, bölüm başlığı">
          <Ornek ad="sayaç"><Sayac etiket="Şifa iksiri" deger={sayac} min={0} max={3} degisince={setSayac} /></Ornek>
          <Ornek ad="en az"><Sayac etiket="Meşale" deger={0} min={0} max={3} degisince={() => {}} /></Ornek>
          <Ornek ad="devre dışı"><Sayac etiket="Ok" deger={12} disabled degisince={() => {}} /></Ornek>
          <Ornek ad="rozet"><Rozet>Taşınıyor</Rozet> <Rozet tur="yeni">Yeni</Rozet> <Rozet tur="hakem">Kural</Rozet></Ornek>
          <Ornek ad="bölüm başlığı"><div className="kitap-ornek-sutun"><BolumBasligi yan="Taşıdığın her şey">Çanta</BolumBasligi><BolumBasligi duzey={3}>Üstünde</BolumBasligi></div></Ornek>
        </Parca>

        <Parca baslik="Sayı kutusu">
          <Ornek ad="boş"><SayiKutusu etiket="Zekâ" deger="" yerTutucu="—" degisince={() => {}} /></Ornek>
          <Ornek ad="dolu"><SayiKutusu etiket="Kuvvet" deger={kuvvet} degisince={setKuvvet} /></Ornek>
          <Ornek ad="hata"><SayiKutusu etiket="Çeviklik" deger="21" hata="3 ile 20 arası olmalı." degisince={() => {}} /></Ornek>
          <Ornek ad="devre dışı"><SayiKutusu etiket="Karizma" deger="9" disabled degisince={() => {}} /></Ornek>
        </Parca>

        <Parca baslik="Bildirim, pencere, ipucu">
          <Ornek ad="kendiliğinden kapanan bildirim"><KitapDugme onClick={() => toast('Macera kaydedildi.')}>Bildirim göster</KitapDugme></Ornek>
          <Ornek ad="pencere, yapışkan kapatma"><KitapDugme onClick={() => setPencere(true)}>Pencereyi aç</KitapDugme></Ornek>
          <Ornek ad="ipucu"><Ipucu metin="Kalan büyü yuvası: 2"><KitapDugme>Büyü yuvaları</KitapDugme></Ipucu></Ornek>
        </Parca>

        <Parca baslik="Mikrofon, boş durum, yükleniyor">
          <Ornek ad="kapalı"><Mikrofon destek dinliyor={false} degisince={() => {}} /></Ornek>
          <Ornek ad="dinliyor"><Mikrofon destek dinliyor degisince={() => {}} /></Ornek>
          <Ornek ad="devre dışı"><Mikrofon destek dinliyor={false} disabled degisince={() => {}} /></Ornek>
          <Ornek ad="desteklenmiyor"><Mikrofon destek={false} dinliyor={false} degisince={() => {}} /><p className="kitap-etiket">Düğme görünmez.</p></Ornek>
          <Ornek ad="boş durum"><BosSatirlar satir={3} etiket="Gerisi henüz yazılmadı" /></Ornek>
          <Ornek ad="yükleniyor"><Yukleniyor etiket="Sayfa yazılıyor" /></Ornek>
        </Parca>

        <Parca baslik="Yazma alanı">
          <Ornek ad="dolu"><YazmaAlani kip="soyle" kipDegisince={() => {}} metin="Kapıyı yavaşça aralıyorum." metinDegisince={() => {}} gonder={() => {}} mikrofonDestegi /></Ornek>
          <Ornek ad="devre dışı, mikrofon yok"><YazmaAlani kip="sor" kipDegisince={() => {}} metin="" metinDegisince={() => {}} gonder={() => {}} mikrofonDestegi={false} disabled /></Ornek>
        </Parca>

        <Parca baslik="Yazı tipleri ve Türkçe harfler">
          <Ornek ad="Literata"><p className="kitap-p">{TURKCE}</p><p className="kitap-kenar-metin">{TURKCE}</p></Ornek>
          <Ornek ad="A, Charm"><p className="kitap-el" data-kitap-el="a">{TURKCE}</p></Ornek>
          <Ornek ad="B, Kalam (varsayılan)"><p className="kitap-el" data-kitap-el="b">{TURKCE}</p></Ornek>
          <Ornek ad="C, Bad Script"><p className="kitap-el" data-kitap-el="c">{TURKCE}</p></Ornek>
        </Parca>
      </div>

      <Pencere acik={pencere} degisince={setPencere} baslik="Uzun pencere">
        {Array.from({ length: 14 }, (_, i) => (
          <p key={i} className="kitap-p">Satır {i + 1}: kaydırınca başlık ve Kapat düğmesi yerinde kalır.</p>
        ))}
      </Pencere>
      <BildirimAlani />
    </div>
  );
}
