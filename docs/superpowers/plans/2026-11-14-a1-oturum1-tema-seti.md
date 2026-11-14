# A1 Oturum 1: tema kontrol seti ve galeri (plan)

İstem: `AI-DND-b01-isolated/A1_ISTEMI_20261113.md` (Kadir onaylı) ve 14 Kasım güncellemeleri. Hedef resim: `kitap-taslagi-20261113/hedef-resimler/`. Dal: `task/ui-a1-tema-20261114` (bütünleştirme dalı 44de21fe'den).

## Tasarım (kısa)

- **Amaç:** A2 ekranlarının kuracağı kitap görünümünün ortak parçaları: üç tema, yazı tipleri, kitap kabuğu, temel kontroller; tek galeri sayfasında Kadir'in onayı için.
- **Kapsam dışı:** oyun ekranı yeniden tasarımı, sayfalama, mühür/mum/zar/lamba/kenar notu (Oturum 2), motor kodu.
- **Yaklaşımlar:**
  1. *(seçilen)* Yeni değişkenler `src/index.css`'te yalnız `[data-kitap-tema="gunduz|gece|karanlik"]` seçicisinin altında. Eski ekranlar bu niteliği taşımaz; eski `--unw-*` ve `data-unw-theme` olduğu gibi kalır.
  2. Eski `--unw-*` değerlerini yeni renklere çevirmek: bütün eski ekranlar bir anda renk değiştirir, A2'den önce bozulur, eski kontrast testleri kırılır. Reddedildi.
  3. Ayrı bir CSS dosyasında tema: istemin "renk yalnız `src/index.css`" kuralına aykırı. Reddedildi.
- **Ruling: yeni set `[data-kitap-tema]` altında, eski ekranlar dokunulmadan kalır — eski ekranlar A2'ye kadar bugünkü görünümünde kalmalı, galeri tek başına doğrulanabilmeli — yanlışsa maliyeti: A2'de niteliği `<html>`'e taşımak (tek satır) ve eski `--unw-*` tanımlarını silmek; kod çöpe gitmez.**
- **Değişken adları** taslağın adlarıdır (`--sayfa`, `--murekkep`, `--soluk`, `--hakem`, `--mum`, `--mum-cizgi`, `--cizgi`, `--bez` ...); Kadir'in istemi üçünü bu adla istiyor. Depoda bu adlar başka yerde kullanılmıyor (arandı).
- **Görünüm:** `src/lib/kitap-tema.ts` saf işlev: seçim (`saat|gunduz|gece|karanlik`) + hikâye saati (`gunduz|gece`) → tema. Galeri sahte saat düğmesiyle besler; oyunun gerçek saati A2.6/A2.8.
- **Çizim klasörü:** `src/components/kitap/cizimler/` (taslaktan alınan SVG çizimleri ve iki doku resmi). Renk kodu araması bu klasörü kapsamaz.
- **Bileşenler:** `src/components/kitap/` altında, `src/components/ui` üstüne ince sarmalayıcılar; stil `kitap.css`'te yalnız `var(--...)` ile.
- **Galeri:** `/galeri` yolu yalnız geliştirmede (`import.meta.env.DEV`, tembel yükleme); oyun akışına bağlı değil.

## Adımlar (her biri: önce kırmızı test, sonra kod; doğrulaması yanında)

1. Yazı tipleri (bitti, 33567081) — `tests/unw-theme.test.mjs` yeşil.
2. `kitap-tema.ts` + `index.css` kitap değişkenleri (üç tema, el yazısı, yazı boyu, efekt kapalı) — yeni test `tests/kitap-a1.test.mjs`: değerler karar belgesi 5. bölümle aynı; eski `--unw-*` blokları değişmedi.
3. Çizim klasörü: kalem ucu, kurdele, seçim damgası, iki doku — test: dosyalar var, `--mum`, `--mum-cizgi`, `--soluk` kullanılıyor; kaynak notu.
4. Kitap kabuğu + ayraç — test: `role=tablist`, `aria-selected`, tek sayfa sınıfı; doku döşeme, tam sayfa `filter` yok.
5. Temel kontroller (düğme, açılır liste, onay kutusu, anahtar, seçim kartı, sayaç, rozet, bölüm başlığı, sayı kutusu, bildirim, pencere, ayar çarkı, seçici grup, mikrofon, ipucu, boş satır, yükleniyor) — test: ARIA adları, devre dışı, hata iletisi, 44 piksel değişkeni; ham `select/checkbox/alert` yok.
6. Yazma alanı (kalem ucu, altın çizgi, el yazısı, üç kip, mikrofon solda) — test: kip seçici radyo grubu, mikrofon desteklenmezse görünmez.
7. Galeri sayfası — test: yol yalnız DEV'de; her parçanın boş/dolu/hata/devre dışı/odak hâli.
8. Kanıt: 6 görüntü, yan yana, kontrast ölçümü, ağ, kayma, arama sonuçları; `typecheck`, `test`, `test:ui`.

## Rulings (uygulama sırasında)

- Ruling: galeri `data-kitap-*` niteliklerini açıkken `<html>`'e de koyar — pencere, açılır liste ve bildirim `<body>` altına taşınıyor, tema onlara da geçmeli — yanlışsa maliyeti: yalnız galeri etkilenir, kapanınca nitelikler silinir.
- Ruling: dört yeni yazı tipi `font-display: optional` — yazı tipi geç gelince hikâye 30,6 piksel kayıyordu (ölçüldü), hedef 0 — yanlışsa maliyeti: yavaş ağda ilk açılışta yedek yazı tipi; A2.6'da `preload` eklenerek giderilir.
- Ruling: el yazısı düğmeleri hedef resimdeki gibi A, B, C sırasıyla, varsayılan B — T10'daki "B, A, C" tercih sırasıdır, hedef resim A B C gösteriyor — yanlışsa maliyeti: dizi sırası, tek satır.
- Ruling: telefonda masada yalnız saat düğmesi, Ayarlar gizli — beş ayraç ve iki düğme 390'a sığmıyor, yer kararı G6 (Oturum 2'de Kadir'e iki seçenek) — yanlışsa maliyeti: bir CSS kuralı.
- Ruling: telefonda galeri sağ sayfayı (yazma alanıyla) gösterir — tek sayfa düzeninin hangi sayfayı göstereceği A2.6'nın işi — yanlışsa maliyeti: `darEkranSayfasi` değeri.
- Ruling: ekran görüntüleri commit edilmedi (27 MB); worktree'de `UI_EKRAN_GORUNTULERI_20261113/` — yanlışsa maliyeti: istenirse ayrıca eklenir.
- Kısayol: kitabın konum ölçüleri (üst boşluk 66 px, sayfa yığını gölgesi, sırt kavisi yarıçapı) `kitap.css`'te sabit piksel; renk ve yazı tipi tümüyle değişkenden, boşlukların çoğu `--bosluk-*`'tan.
- Park: WSL yuva 9 yoktu; ilk deneme `/root/aidnd-env-9` altında yarım bir klasör bıraktı (silinmedi, sahibi bu oturum).

### Üçüncü ayrı göz (Opus, Fable; `72a51bab`) — Kadir: "Hepsini düzelt"
- Ruling: lamba boynu alçaltıldı ve lamba 84'ten 96 piksele büyütüldü (geniş ekranda en çok 108) — 1911'de tepesi pencereden taşıyordu, iki inceleme de "küçük" dedi; tepe her genişlikte pencerenin en az 4 piksel içinde (testle hesaplanıyor) — yanlışsa maliyeti: tek sayı.
- Ruling: telefonda kurdele ucu sayfanın altından çıkıp cilt kenarını aşıyor (yaklaşık 14 piksel görünür) — masada 5 piksel boşluk var, daha uzun sarkamaz; gizlemek yerine bu seçildi — yanlışsa maliyeti: tek CSS kuralıyla gizlenir.
- Ruling: 800 genişlikte "Ne yapıyorsun?" iki satıra iniyor (kelime bölünmeden) — Gönder simgeye döndü, seçenekler tek satır — yanlışsa maliyeti: küçük.
- Test yeniden yazımı (onay listesi, gevşetme olabilir diye işaretli): `--lamba-en` 84→96 (büyüme); hale tepe formülü 0.573→0.725 (ampul aşağı kaydı); kurdele kutusu 100%+40→100%+44 ve `SARKMA = 42` (daha uzun sarkma, sıkılaştırma).
- Kadir onayı (14 Kasım 2026): kurdele "Oldu" (commit `cc1597e4`, Fable düzeltmesi).
