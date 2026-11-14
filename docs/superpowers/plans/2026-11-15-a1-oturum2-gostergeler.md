# A1 Oturum 2: göstergeler, zar, kenar notu, kayıt bildirimi ve galerinin son kanıtı (plan ve ledger)

İstem: `AI-DND-b01-isolated/A1_ISTEMI_20261113.md` ("Kapsam: Oturum 2") ve Kadir'in 14 Kasım güncellemeleri. Dal: `task/ui-a1-oturum2-20261114` (bütünleştirme dalı `0c0eb85f`'ten, PR #52 içinde). Worktree: `AI-DND-a1-o2`. Oturum 1 ledger'ı: `2026-11-14-a1-oturum1-tema-seti.md` (kurdele "Oldu", Varka çizgisi kalır).

## Tasarım (kısa)

- **Yeni dosyalar:** `src/components/kitap/gostergeler.tsx` (can mührü, büyü yuvaları, zar, kenar notu, kayıt bildirimi). Çizimler `cizimler/` altında: `mum.tsx` (yanan, sönük), `can-muhuru.tsx` (dolu, basılmamış, çatlaklar), `kenar-simgeleri.tsx` (para, zar, iş, geri al, kural). Zar kodla çizilir ve renkleri değişkenden gelir, bu yüzden çizim klasöründe değil `gostergeler.tsx`'te.
- **Veri biçimi:** mühür ve mum sayıyı yalnız kendisine verilen değerden gösterir; zar asla kendisi atmaz (`Math.random` yok). Geçersiz değer (eksi, en çoktan büyük, tam sayı değil) "okunamadı" hâlidir: sayı uydurulmaz.
- **Çatlak sayısı:** can tam ise 0; yoksa kayıp oranının üçte biri yukarı yuvarlanır, en çok 3 (43/49 → 1, taslaktaki gibi).
- **Mum (T12, Çelişki 25):** seviye başına ayrı kısa sıra, altında yalnız "1. seviye"; kalan yuva sayısı ekran okuyucu adında ve ipucunda (`1. seviye: kalan yuva 2 / 4`). Sıra klavyeyle odaklanır, ipucu odakta açılır.
- **Kayıt bildirimi (Çelişki 24):** iki biçim yan yana: küçük mühür ve küçük kurdele; sağ üstte, kendiliğinden solar; `role="status"`. Hata ("Kaydedilemedi") kendiliğinden kapanmaz.
- **G6 (telefon):** iki seçenek, `?telefon=a|b`. A: sağ üstte tek Ayarlar düğmesi (görünüm ayarın içinde), lamba yok. B: kitap 48 piksel aşağı iner, üst şeritte saat ve Ayarlar, lamba kitabın sol üst köşesinde.
- **G10:** Oturum 1'deki ayar anahtarı kalır; kanıtta iki görüntü yan yana.
- **Kısayol kapatma (Kadir, madde 2):** `kitap.css`'teki 66 piksel üst boşluk, sayfa yığını gölgeleri ve sırt kavisi yarıçapları `src/index.css` değişkenlerine taşınır.

## Adımlar (her biri: önce kırmızı test, sonra kod)

1. Sabit pikseller değişkene — test: `kitap.css`'te `66px`, `110px`, `90px` ve sayfa yığını listesi yok; değişkenler `index.css`'te aynı değerle.
2. Çizimler ve göstergeler — test: adlar, durumlar, çatlak sayısı, zar sayısı yalnız verilen değerden, renk kuralı.
3. Kayıt bildirimi ve G6 — test: `role="status"`, iki biçim, telefon düzeni niteliği.
4. Galeri — test: her parçanın hâlleri galeride.
5. Kanıt: 375/768/1024/1440/1911 üç tema, klavye, gerçek piksellerden kontrast, yolculuk komşu seti, build, `typecheck`, `test`, `test:ui`.

## Rulings (uygulama sırasında)

- Ruling: telefonda varsayılan düzen G6-a (sağ üstte yalnız Ayarlar, saat düğmesi gizli, lamba yok); G6-b galeride `?telefon=b` ile — istem iki seçeneği yan yana istiyor, oyuna hangisinin gireceğini Kadir seçer — yanlışsa maliyeti: varsayılanı `kitap-kabugu.tsx`'te tek harf değiştirmek.
- Ruling: G6-b'de odak sırası görsel sırayla uyuşmuyor (masa düğmeleri telefonda kitaptan sonra odaklanıyor, b'de ise üst şeritte görünüyor); `masaSonra={darEkran}` ve onu sabitleyen test olduğu gibi kaldı — b seçilmeden sırayı değiştirmek seçilmemiş düzen için testi yeniden yazmak olurdu — yanlışsa maliyeti: b seçilirse bir prop ve bir test satırı.
- Ruling: zar yalnız galeride (göstergeler bölümü) gösterildi, hikâye sayfasına konmadı; zar atma akışı A1'in işi değil — yanlışsa maliyeti: zarı kenar notunun yanına koymak.
- Ruling: kayıt bildirimi küçük bir kâğıt fiş: mühür biçiminde 22 piksellik balmumu, kurdele biçiminde V kesikli kurdele ucu; 2600 ms sonra kendiliğinden kapanır; hata kapanmaz ve mühür/kurdele yerine uyarı simgesi taşır (hata "kaydedildi" mührüyle karışmasın) — yanlışsa maliyeti: tek bileşen.
- Ruling: telefonda kayıt bildirimi sol altta (`bottom: 170px`), çünkü sağ üst ayraçlar ve Ayarlar ile dolu — yanlışsa maliyeti: bir CSS kuralı.
- Ruling: galerideki sağ sayfa başlığında "Yeni iş" rozeti yerine durum şeridi (küçük mumlar, 38 piksellik mühür, sayı) kondu, hedef resim 01 gibi; "Yeni iş" altın kenar notu olarak hikâyeye geçti, bunun için galeriye bir hikâye satırı eklendi (galerinin kendi metni, hedeften kopya değil) — yanlışsa maliyeti: galeri metni.
- Ruling: mühürdeki 2. ve 3. çatlak taslaktaki tek çatlağın merkez etrafında döndürülmüş kopyası; formül her kaybedilen üçte bir için bir çatlak (43/49 → 1) — taslak tek çatlak çiziyor, hasar ölçeği tanımlı değil — yanlışsa maliyeti: `catlakSayisi`.
- Onay listesi (gevşetme olabilir, işaretli): `tests/kitap-a1.test.mjs` "round 3, finding 1" lamba testi yeniden yazıldı: lamba üst konumu artık `calc(var(--masa-ust-bosluk) - var(--lamba-en) * k)` ile okunuyor ve `--masa-ust-bosluk: 66px` ayrıca doğrulanıyor (eski test `top` içinde 66 sayısını arıyordu; sıkılık eşit: aynı oran ve aynı 66 px).
- Park: G6-b seçilirse odak sırası (yukarıdaki Ruling).
- Bulgu (ölçümde, kendi işim): G6-a telefonda Ayarlar düğmesini görünür yapınca 44 piksellik simge düğmesinden "Ayarlar" sözcüğü taştı; 375'te sayfa 383, 390'da 398 piksel genişledi (yatay kaydırma). Önce kırmızı test (`o2 G6: on the phone the settings button is a 44px icon key ...`), sonra sözcük `kitap-dar-gizli` içine alındı (`arayuz-ayarlari.tsx`); 375 ve 390'da a ve b için `scrollWidth = clientWidth`. Masaüstünde sözcük görünür kalıyor.
- Ruling: ölçüm aracı galeri parçalarını belgeyi kaydırarak görünür alana getiriyor; kitabın kendi kutularını kaydırmak görüntüde masayı yanlış çizdiği için kullanılmadı — yanlışsa maliyeti: yalnız ölçüm aracı.
- Bağımsız inceleme (Sonnet, kapsamlı kod incelemesi; para/kayıt/Geri Al mantığı yok, kayıt bildirimi yalnız gösterge): 9 risk, 1 soru. Düzeltilenler (önce kırmızı test, sonra kod): ikinci kayıtta solma süresi yeniden başlamıyordu (`kimlik`; tarayıcıda ölçüldü: ikinci tıktan 1,5 s sonra fiş duruyor, 3 s sonra gitmiş); hata "polite" duyuruluyordu (artık `assertive`); durum şeridi okunamayan seviyeyi ve canı sessizce atlıyordu (artık "okunamadı" yazıyor); şerit dokuz seviyede telefonda taşabilirdi (`flex-wrap`); mum satırı adını iki kez okutuyordu (ipucunun `aria-describedby`'ı satırdan kaldırıldı; tarayıcıda `aria-describedby` yok, ipucu açık); devre dışı zar adında "devre dışı" yoktu. Çatlak sınır testleri eklendi (tam üçte birler, NaN, Infinity), zaten yeşildi.
- Ruling: yuva sayısına üst sınır konmadı (inceleme bulgusu 5) — motor sınırlı değer gönderir, CLAUDE.md imkânsız durum için kod istemiyor — yanlışsa maliyeti: tek satır sınır.
- Ruling: zamanlayıcı testi kaynak düzeyinde (etki bağımlılıkları `[durum, kimlik]`) ve tarayıcıda bir kez ölçüldü; pakette DOM test ortamı yok, tarayıcı paketine yeni test eklenmiyor (sahip kuralı) — yanlışsa maliyeti: zamanlayıcı gerilemesi geç fark edilir.
- Ruling: `catlakSayisi` formülü değiştirilmedi (inceleme bulgusu 7: 3e9 üstü can uç durumu) — D&D'de imkânsız, sınır testleri yeşil.
