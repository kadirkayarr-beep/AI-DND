# Yol haritası: Kapı 1'e

Amaç: Kapı 1'e kadar her işi tek sayfada görmek: ne, neden, oyunda ne değişir, tahmin, gerçek, Kadir ne zaman oynar, durum.
Tek kaynak: sıra ve durum için bu dosya esastır. Ayrıntı ana planda (`YENIDEN_TASARIM_PLANI_20261113.md`), bölme tasarımında ve dilim planlarında kalır. Çelişkide bu dosya güncellenir; motor yapısında bölme tasarımı (§11, §12) ve `docs/adr/0001-game-parts-merkez-kurali.md` kazanır.
Güncelleme: her dilim sonunda aynı PR'da; dilim başlarken tahmin sütunu dolar. Durum değerleri: `bekliyor / koşuyor / oynayış bekliyor / bitti`.
Önden planlama: bir dilim koşarken sonrakinin planı ayrı worktree'de yazılır ve incelenir; koşan dilimin dosyalarına dokunmaz.
Telefon sayfası: bu tablonun yalnız işler, tarihler ve durumlar içeren özel kopyası; her dilim sonunda aynı adreste yenilenir.
Son güncelleme: 2026-11-23 (belge PR'ı).

## Sıra

| # | İş | Neden (bir cümle) | Oyunda ne değişir | Tahmin (gün, token) | Gerçek (gün, token) | Kadir'in oynayışı | Durum |
|---|----|-------------------|-------------------|---------------------|---------------------|-------------------|-------|
| 1 | Plan 6 (game.py bölmenin kapanışı) | Bölmeyi bitirip motoru temiz zemine oturtmak. | Görünür değişiklik yok | verilmedi | 0,3 gün (PR #145, b76e7254); token: ölçülmedi | Kapanış oynayışı (al-sat, kaydet-yükle, Geri Al, dövüş, yolculuk) | oynayış bekliyor |
| 2 | Belge PR'ı: borç defteri, INDEX, bu yol haritası, ana plan ve HANDOFF repoya | Sıra ve kararlar tek yerde, depoda dursun. | Yok | ölçülmedi | sonraki dilim sonunda yazılır | — | koşuyor |
| 2b | Rastgele kırık taraması (yalnız test dosyaları, kendi worktree'si; belge PR'ından sonra, tur bölmeden önce, çünkü tur bölme koşarken test dosyalarına ikinci bir yazıcı girmemeli; ayrı planı var) | Kasabası sabit olmayan testler CI'ı rastgele kırmızı yapıyor. | Yok (CI daha az rastgele kırmızı) | dilimden önce verilecek | — | — | bekliyor |
| 3 | D-331/D-332 düzeltme dilimi; yanında: tur bölme tasarımı ve bedel tahmini, BS yeniden ölçümü, arayüz yazı dilimi ("sunucu" yazıları, Büyücü/Cleric cümlesi) | İki bilinen oyun hatasını kapatmak ve tur bölmenin bedelini önceden görmek. | Belirsiz yere yürüyüş çalışır; güvenlik denetiminden geçen NPC cevabı alakasız hazır cümleye dönmez; yaratma ekranındaki gereksiz yazılar kalkar | dilimden önce verilecek | — | 10 dakika | bekliyor |
| 4 | Tur bölmenin tamamı (Fable; planını Kadir onaylar); yanında: BS, sonra BA (tek ek yazıcı, ayrı dosyalar) | Donmuş büyük işlevleri bölmeden B2 ve sonrası temiz yazılamaz. | Tur bölme: yok. BS/BA: düşman canı sayı olarak, Türkçe tür/sınıf/özellik adları | dilimden önce verilecek (plan ve tahmin Kadir'in onayına gider) | — | Ortasında ve sonunda | bekliyor |
| 5 | Arayüz 1. tur (A2.2 A taslağıyla sürer; v0 B taslağı bırakıldı, Kadir 2026-11-22) | Hikâye önde, kitap sayfası görünümü. | Kitap sayfası arayüzü ilk ekranlar | dilimden önce verilecek | — | Tur sonunda | bekliyor |
| 6 | Kalan BM hataları; B1a/B1b/B3a testleri; motor ara kapısı | BM oynayışında çıkan kalan hataları ve ara kapıyı kapatmak. | BM oynayışındaki kalan hatalar | dilimden önce verilecek | — | 10 dakika (ara kapı) | bekliyor |
| 7 | B2 (anlatıcı), B3b, B3c; arayüz 2. tur | Varış, kimler var, arama ve savaş sonucu model tarafından anlatılsın. | Varış, kimler var, arama, savaş sonucu model anlatır | dilimden önce verilecek | — | Dilim sonları | bekliyor |
| 8 | Kapı 1 | Oyunun oynanabilir ve güzel olduğunu Kadir'in eliyle sınamak. | — | dilimden önce verilecek | — | 30 dakika | bekliyor |

## Geçmiş ölçüler

Tahmin bu tabloya bakılarak yapılır. Gün = ilk commit'in yazar tarihinden son merge'ün commit tarihine takvim süresi.

| Plan | ilk commit | son merge | gün | token | PR'lar |
|------|-----------|-----------|-----|-------|--------|
| Plan 3 | 2026-11-20 02:28 | 2026-11-20 21:16 | 0,8 | ölçülmedi | #135, #136 |
| Plan 4 | 2026-11-20 22:14 | 2026-11-22 03:30 | 1,2 | ölçülmedi | #137, #138 |
| Plan 5 | 2026-11-22 03:55 | 2026-11-22 19:02 | 0,6 | ölçülmedi | #139, #140, #141 |
| Plan 6 | 2026-11-22 19:36 | 2026-11-23 03:18 | 0,3 | ölçülmedi (yalnız devam koşusu 1,87 milyon, Plan 6 ledger'ında; toplam doğrulanmadı) | #145 |

Not: plan yazımı ve ölçüm süresi dahil değil; planlar üst üste bindi.

## Sonrası

Kapı 1'den sonra: ikinci kasaba, cinsiyet/portre sorusu Kadir'e, Hat C. Güvenlik okuması (D-320) ilk uzak oyuncudan önce.

## Geçerli eski kararlar

Kadir'in 2026-11-12 kararlarından geçerli kalanlar (`YOL_HARITASI_20261112.md` §5; kelimesi kelimesine; numaralar o dosyadaki numaralardır):

3. Depo özele çevrildi (2026-11-12, doğrulandı: girişsiz erişim kapalı).
4. İlk sürümde "kendi anahtarını getir" yok kararı (1 Kasım) sürer; hukuk incelemesi olmadan eklenmez.
5. Faz 4 yönü: kural verisi için yalnız SRD 5.2, dünya için kendi dünya. Hukuk incelemesi şart.
8. Ekran kartı alınmaz, kiralık GPU ve ikinci "yönetici model" kurulmaz.
9. İçerik sınırları belgesi yabancı oyunculardan önce (Faz 5) yazılır.
10. Kural içeriği (büyü, feat, geçmiş, tür) değişmez: Kadir lisans başvurusu yapacak; açık bir ret gelmeden SRD 5.2 dışı içerik oyundan çıkarılmaz. Son karardır. Sonuç: Faz 4'ün "lisanssız içerik kalmadı" kapısı, başvurunun cevabına bağlıdır. Fark listesi: proje belgesi `claude/SRD52_FARK_VE_API_ADAYLARI_2026-11-12.md` (52 büyü + 17 ad farkı, 58 feat, 12 geçmiş, 1 tür).
11. "SRD kapısı" testi yazılmaz (10. karar gereği).
12. Anadolu/Türk folkloru dünyası: hayır. Kadir ileride kendi özgün fantastik dünyasını kuracak.
13. Onaylandı (Faz 2 sonrası, derleme zamanında alınır, motorun tur yolundan dış çağrı yok): CC0 müze görselleri (Met Open Access), game-icons simgeleri, CC0 ortam sesi paketi. Her biri için önce lisans ve atıf şartı doğrulanır.
17. Varlık kaynakları (Kadir beyanı, 21:06): ana menü müziği `Nordisk Ritual.mp3` Suno ile, Premier abonelik sırasında üretildi (Suno'nun yardım sayfasına göre abonelik sırasında yapılan şarkılara ticari kullanım hakkı verilir). Logo ve animasyon Google Flow ile, Google AI Ultra planında üretildi. Google Flow yardım sayfası (12 Kasım 2026): "Google won't claim ownership over that content"; ticari kullanım için açık izin ya da yasak cümlesi yok, Hizmet Şartları'na yönlendiriyor; tüm çıktılarda görünmez SynthID filigranı var. Ticari kullanımın açık dayanağı ve kullanılan modelin ön izleme durumu doğrulanmadı; satıştan önce kapanacak madde.

## Kadir'in kuralları

Oynayış kapısı, push/merge/yayın ve model ile tahmin kuralları `CLAUDE.md`'de: "Oynayış kapısı", "Push/merge/yayın", "Model ve tahmin".
