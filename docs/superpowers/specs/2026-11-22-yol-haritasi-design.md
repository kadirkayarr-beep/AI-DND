# Kapı 1'e yol haritası: planlı, güvenli, hızlı (tasarım)

Tarih: 22 Kasım 2026. Durum: Kadir yazılmasını onayladı (brainstorming); grill-me turlarıyla sınanacak, sonra uygulama planı yazılacak.

## 1. Niyet ve neden

Kadir'in sözleri: oyunun "bir an önce oynanabilir ve güzel olması", "gereksiz zaman kaybetmemek için daha planlı olmak", "gelecekte ne yapacağımızın belli olması".

Bugün sorun şu: iş sırası beş-altı belgeye dağılmış (ana plan `YENIDEN_TASARIM_PLANI_20261113.md`, bölme tasarımı `2026-11-17-game-py-bolme-design.md`, Fable kararları `KARARLAR_SON.md`, borç defteri, INDEX, HANDOFF). Kadir neyin ne zaman geleceğini, neye mal olacağını ve ne zaman oynayacağını tek yerde göremiyor. Plan 3-6 yaklaşık altı gün sürdü ve oyunda görünür bir şey değiştirmedi; bu bilinerek seçilmiş bir yoldu ama Kadir'e önceden gün ve token olarak gösterilmedi.

## 2. Hedefler, hedef olmayanlar, kaçınılacaklar

Hedefler:
- Kapı 1'e kadar her işin tek sayfada görünmesi: ne, neden, oyunda ne değişir, tahmini gün ve token, Kadir ne zaman oynar, durum.
- Her dilimden önce Kadir'e gün ve token tahmini; dilim sonunda gerçek sayı yanına yazılır (tahmin ile gerçek karşılaştırılır).
- Dilimler arasında boşluk olmaması: bir dilim koşarken sonrakinin planı yazılır ve incelenir.
- Rastgele kırıkların (flake) dilim ortasında işi durdurmaması.

Hedef olmayanlar:
- Sırayı değiştirmek. Kadir 1. yolu seçti (aşağıda §4): önce tur bölmenin tamamı, sonra görünür işler.
- Yeni oyun özelliği eklemek. Bu belge yalnız işin nasıl planlanıp yürütüleceğini düzenler.

Kaçınılacaklar (çalışsa bile başarısızlık sayılır):
- Hız için güvenlik ya da kalite kaybı: para/kayıt/Geri Al bağımsız incelemesi, yeşil CI, oynayış kapıları, sıfır tolerans yolculukları gevşemez (CLAUDE.md "Dokunulmaz").
- Kadir'in göremediği ya da anlayamadığı bir yol haritası (İngilizce, uzun, dağınık).
- Güncellenmeyen, eskiyen bir yol haritası.

## 3. Kısıtlar

- CLAUDE.md kuralları: worktree başına tek yazıcı; main'e merge yalnız yeşil CI ile; push/merge sonrası CI kontrolü; anahtar dosyalarına dokunulmaz; force push ve dal silme yok.
- Otomatik izin (Kadir, 22 Kasım): Plan 6 ve tur bölmede yeşil CI sonrası push/PR/merge serbest; oynayış kapıları kalır. Plan 6 Görev 8 (ölü kod silme) dışarıda: push/PR/merge her biri Kadir'e sorulur.
- Model: tur bölme Fable (Kadir, 22 Kasım); diğer güçlü işler Opus. Haftalık token limiti dar; Fable Opus'tan pahalıdır.
- Bilgisayar: tam test paketi aynı anda yalnız bir tane; test yuvaları 3 ve 5 kullanılmaz; tarayıcı testlerini yalnız Kod-1 koşar.
- Eski kayıtlar önemsizdir (Kadir); uyumluluk işi yapılmaz.

## 4. Yaklaşımlar (Kadir seçti: 1)

1. **Bugünkü sıra (seçilen).** Önce tur bölmenin tamamı, sonra görünür işler. En düzenli yol; donmuş koda dokunan B2 ve sonrası temiz zemine oturur. Bedeli: tur bölme bitene kadar oyunda görünür değişiklik azdır (yalnız yan yoldaki BS/BA ve arayüz yazı dilimi).
2. Daraltılmış tur bölme ve yanında arayüz: yalnız B2'nin gerektirdiği parça (`finish_turn` ve ana tur işlevi) bölünür, arayüz 1. tur yanda yürür. Daha erken görünür ilerleme; iki yazıcı koordinasyonu gerekir. Seçilmedi.
3. Önce görünür işler, sonra tur bölme. B2 donmuş koda dokunduğu için CI kırmızı olur ya da her adım bütçe onayı ister. Seçilmedi.

## 5. Sıra (Kadir'in kararıyla)

| # | İş | Yanında yürüyen | Oyunda ne değişir | Kadir'in oynayışı |
|---|----|-----------------|-------------------|-------------------|
| 1 | Plan 6 (game.py bölmenin kapanışı) | — | Görünür değişiklik yok | Kapanış oynayışı (al-sat, kaydet-yükle, Geri Al, dövüş, yolculuk) |
| 2 | Belge PR'ı: borç defteri, INDEX, bu yol haritası, ana plan ve HANDOFF repoya | — | Yok | — |
| 2b | Rastgele kırık taraması (§6.4; yalnız test dosyaları, kendi worktree'si; uygulayıcının kararı: belge PR'ından sonra, tur bölmeden önce, çünkü tur bölme koşarken test dosyalarına ikinci bir yazıcı girmemeli) | — | Yok (CI daha az rastgele kırmızı) | — |
| 3 | D-331/D-332 düzeltme dilimi | Tur bölme tasarımı ve bedel tahmini; BS yeniden ölçümü; arayüz yazı dilimi ("sunucu" yazıları, Büyücü/Cleric cümlesi) | Belirsiz yere yürüyüş çalışır; güvenlik denetiminden geçen NPC cevabı alakasız hazır cümleye dönmez; yaratma ekranındaki gereksiz yazılar kalkar | 10 dakika |
| 4 | Tur bölmenin tamamı (Fable; planını Kadir onaylar) | BS, sonra BA (tek ek yazıcı, ayrı dosyalar) | Tur bölme: yok. BS/BA: düşman canı sayı olarak, Türkçe tür/sınıf/özellik adları | Ortasında ve sonunda |
| 5 | Arayüz 1. tur | — | Kitap sayfası arayüzü ilk ekranlar | Tur sonunda |
| 6 | Kalan BM hataları; B1a/B1b/B3a testleri; motor ara kapısı | — | BM oynayışındaki kalan hatalar | 10 dakika (ara kapı) |
| 7 | B2 (anlatıcı), B3b, B3c; arayüz 2. tur | — | Varış, kimler var, arama, savaş sonucu model anlatır | Dilim sonları |
| 8 | Kapı 1 | — | — | 30 dakika |

Sonrası (Kapı 1'den sonra): ikinci kasaba, cinsiyet/portre sorusu Kadir'e, Hat C. Güvenlik okuması (D-320) ilk uzak oyuncudan önce.

## 6. Tasarım

### 6.1 Tek sayfalık yol haritası
- Dosya: `docs/design/YOL_HARITASI.md`, Türkçe, sade. INDEX'in en üstünde bağlantı.
- Satır başına sütunlar: iş, neden (bir cümle), oyunda ne değişir, tahmin (gün, token), gerçek (gün, token), Kadir'in oynayışı, durum (bekliyor / koşuyor / oynayış bekliyor / bitti).
- Güncelleme: her dilimin bitişinde aynı PR'da (dilim sonu adımının parçası); ayrıca her yeni dilim başlarken tahmin satırı dolar.
- Tek kaynak kuralı: sıra ve durum için bu dosya esastır; ayrıntı ana planda, bölme tasarımında ve dilim planlarında kalır. Çelişkide bu dosya güncellenir, diğerleri ona bağlanır.

### 6.2 Dilim öncesi tahmin
- Her dilim başlamadan Kadir'e: tahmini gün, tahmini token (model başına), tam test sayısı, Kadir'in kaç kez oynayacağı. Tahmin geçmiş dilimlerin ledger'larındaki gerçek sürelerden çıkarılır (Plan 3-6 ölçüleri).
- Tur bölme için bu tahmin, bölmenin planı onaya gitmeden önce verilir (Plan 6 Görev 7 Adım 1b).

### 6.3 Önden planlama (boşluksuz geçiş)
- Bir dilim koşarken, sonraki dilimin planı ayrı bir worktree'de yazılır ve incelenir; dilim bitince bekleme olmaz.
- Kural: önden yazılan plan, koşan dilimin dosyalarına dokunmaz; koşan dilim bitince plan bir kez "değişen ne?" diye yeniden okunur.

### 6.4 Rastgele kırık taraması
- 22 Kasım'daki kırık, kampanya başlatıp kasabası sabit olmayan bir testten çıktı (D-483). Kampanya başlatan ve `fixed_town` / `campaign_seed` kullanmayan bütün testler bir kerede taranır; her biri sabitlenir (yalnız tohum; doğrulama gevşemez).
- Paylaşılan bir test yardımcısı değişince onu ödünç alan bütün modüller koşulur (22 Kasım dersi: PR #142'nin ilk CI'ı).

### 6.5 Test yükü
- Tam paket yalnız kapılarda (dilim sonu, plan ara kapısı); görev içinde hedefli set + sabit komşu set.
- Yan yolda yürüyen iş ayrı test yuvası kullanır (bugün: SLOT 2 ve 4 ana iş, SLOT 9 yan iş).

### 6.6 Değişmeyenler
- Para/kayıt/Geri Al bağımsız incelemesi, yeşil CI, oynayış kapıları, sıfır tolerans yolculukları, dilim sonu tam paket ve bütün dal incelemesi.

## 7. Uygulayıcıya kalanlar
- Yol haritası tablosunun ilk doldurulması: ana plandan, `KARARLAR_SON.md`'den ve borç defterinden.
- Tahmin yöntemi: Plan 3-6 ledger'larından gerçek süre ve token okuma betiği. Uygulayıcının kararı: token kaynağı iş akışı (workflow) günlüklerindeki ajan başına token sayılarıdır (`subagent_tokens`); ledger'da token yoksa o satır "ölçülmedi" yazar, uydurulmaz. Kadir'in haftalık limit yüzdesi yalnız onun panelinde görünür; dilim sonunda ondan istenmez, tahminde "yaklaşık" olarak geçer.
- Rastgele kırık taramasının yöntemi (AST ya da metin taraması) ve kaç test çıktığı.

## 8. Kadir'in kararları (grill-me, 22 Kasım 2026)

Kadir: "hepsi evet Otomatik izin ben aksini söyleyinceye kadar hep açık."

- **S1 Oynayış kapısı:** oynayış bekliyorken sonraki dilim kendi worktree'sinde başlayabilir; Kadir oynamadan main'e birleşmez. (CLAUDE.md "Oynayış kapısı" satırındaki "sonraki dilim başlamaz" bu anlamla güncellenir.)
- **S2 Tahmin:** dilim öncesi gün/token tahmini bilgi olarak verilir, iş beklemez; yalnız tur bölmenin planı ve tahmini Kadir'in onayını bekler.
- **S3 Aşım:** tahmini aşan dilim durmaz; aşım yol haritasına yazılır ve dilim sonunda nedeniyle söylenir. Tur bölmede Fable haftalık limiti biterse kalan parça Opus ile sürer (Ruling yazılır).
- **S4 Otomatik izin:** Kadir aksini söyleyene kadar her iş için açık: yeşil CI sonrası push, PR ve main'e merge serbest. Kalanlar: oynayış kapıları (S1 biçimiyle), force push ve dal silme yasağı, her push/merge sonrası CI kontrolü, para/kayıt/Geri Al bağımsız incelemesi, anahtar dosyaları, Plan 6 Görev 8 (ölü kod silme: push/PR/merge Kadir'e sorulur).
- **S5 Bekleyen dilim sınırı:** Kadir: "s5 3 dilim". Main'e girmemiş, Kadir'in oynayışını bekleyen en çok üç dilim olur (üst üste dallar, her biri bir öncekinin üstünde). Dördüncü dilim başlamaz; iş Kadir'in oynayışını bekler ve ona haber verilir.
- **S6 Telefon sayfası:** yol haritası ayrıca özel (yalnız Kadir'in gördüğü) bir sayfa olarak yayınlanır, her dilim sonunda aynı adreste güncellenir; içinde yalnız işler, tarihler, durumlar; kod ve anahtar yok.
- **S7 CLAUDE.md:** oynayış kapısı (S1, S5), kalıcı otomatik izin (S4), tahmin ve aşım (S2, S3) satırları belge PR'ında CLAUDE.md'ye yazılır.
- **S8 Tek oynayış:** bekleyen dilimler en üstteki sürümde tek oynayışla oynanır; her dilim kendi kontrol maddelerini birleşik listeye ekler. İyiyse hepsi main'e girer; bir dilimde sorun çıkarsa yalnız o dilim ve üstündekiler bekler.
- **S9 Oyunu değiştirmeyen işler:** yalnız test, belge ya da CI dosyalarına dokunan işler oynayış beklemez, yeşil CI sonrası main'e girer ve S5 sınırına sayılmaz. Oyun koduna (motor, API, arayüz, içerik JSON'ları) dokunan her iş oynayış kapısından geçer.
