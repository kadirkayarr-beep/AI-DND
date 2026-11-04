# ADIM 2 TASARIMI: ölçüm (yolculuk senaryoları, gecikme, harcama kaydı)

Durum: taslak, Kadir incelemesini bekliyor. Kod YOK, commit YOK, push YOK. Tarih 2026-11-04. Brainstorming sonucu (Kadir ile bölüm bölüm onaylandı: 1–4).
Kaynaklar: `CANLI_OYUN_NOTLARI_20261103.md` (1–33 ilk oynayış, 34–56 EK 4, düzeltmeler EK 4 sonunda), `HANDOFF.md` üst 4 bölüm, `YOL_HARITASI_ONERI_20261031.md` (Adım 2 satırı), salt-okuma kod araştırması (workflow wf_0fb2d8b0-6f0; kesinlik düzeyleri aşağıda). Madde numaraları (1–56) notlar dosyasındandır.

## 1. Amaç ve anlayış
- Amaç: 3b (tur çekirdeği) başlamadan, oynayışta görülen hataların makineyle tekrarlanabilir bir listesini ve ölçülebilir bir ilerleme sayısını çıkarmak; 30 sn gecikmenin kaynağını ölçmek; günlük harcamayı kaydedip uyarmak.
- Kadir'in kararları: (a) testler OLMASI GEREKEN davranışa göre yazılır, bugün kırık olanlar "bilinen kırık" işaretli; (b) çoğu senaryo sahte modelle, 3–4 anahtar senaryo gerçek zincirle ve yalnız Kadir "yap" deyince; (c) kapsam DAR: yolculuk senaryoları + gecikme + harcama; (d) yaklaşım 1 (senaryo dosyaları + tek çalıştırıcı); (e) "üstü kalsın" bahşiş sayılır (bira + 1 bakır bahşiş); (f) oda "anahtarı" eşya değil, oda kaydı + anlatıcıya "oda tutuldu"; (g) harcama: engel yok, 3 USD/gün uyarı.
- Başarı ölçüsü: 3b'ye girerken "şu kadar senaryo bilinen kırık" sayısı var, 3b bitince düşer, yeni kırık 0. Ürünü yalnız Kadir kabul eder.
- Kısıtlar: para, kayıt, Geri Al hatalarında sıfır tolerans. Harcama, push, birleştirme "yap" ister. Anahtarlar asla yazdırılmaz.

## 2. Parçalar
1. Senaryo dosyaları: `ai-dnd/api/tests/journeys/*.json`.
2. Çalıştırıcı (depoda, pytest içinde): HTTP üzerinden oyunu sürer, sahte modelle, her adımdan sonra durumu kontrol eder.
3. Gerçek zincir komutu (`C:\Users\Kadir\Desktop\AI-DND-TOOLS` içinde, depo dışı): aynı dosyaları, aynı süreç içinde (in-process) gerçek zincirle koşar. Çalışan sunucuya dışarıdan bağlanmaz (sahte modeli/durumu okumak için süreç içi gerekir).
4. Gözlem ve harcama kaydı (ürün koduna, davranışı DEĞİŞTİRMEYEN eklemeler).

Dal: `origin/task/ui-labels-20261103` (e4439bab, Haiku sınırı kalkmış) üstüne yeni dal `task/step2-measure-20261104`. `AI-DND-ui-labels` klasörü başka bir dalda olabilir; dal adıyla çalışılır. Birleştirme yok.

## 3. Senaryo dosyası biçimi
Her dosya bir yolculuk. Alanlar:
- `id`, `title`, `source_items` (not madde numaraları).
- `setup`: karakter (sınıf, seviye), mekân, kişiler (id, ad, rol), kese (kuruş), envanter, can, `seed` (zar tohumu, `session.rng.seed(N)`).
- `steps[]`: her adım `say` (oyuncu cümlesi) VEYA `command` (`/item shop_buy ...`) VEYA `economic_action` (prepare/confirm/cancel) VEYA `combat_action`; `expect`; `known_broken` (madde numaraları); `real_chain` (true/false).
- `expect` alanları: `kese` (cp), `envanter` (ad ve adet, kuruş), `oda` (flags.inn_room var mı), `kip` (konuşma kipi: aktif mi, kimle), `savas` (aktif mi), `konum`, `hp`, `kart` (açık mı, max_total_cp, karşı taraf), `olu` (ölüm durumu), `yasak_metin` (gerçek zincirde, `not_contains`), `anlatici_gerekli_metin` (isteğe bağlı).
- Not: oklar (`world.ammunition`) ve oda kaydı yanıtta yok; canlı dünyadan okunur. Eşyalar yığın değil, ayrı kayıt; adet sayarak doğrulanır.

## 4. Senaryolar (motor, sahte modelle; "olması gereken" beklenti)
Her biri şu an geçiyor mu / bilinen kırık mı: koddan tahmin; çalıştırmayla doğrulanacak.
1. Bira, sohbetle: "bir bira alayım" ve "bir bira alabilir miyim" teklif kartı açar; onay → kese −4, envanterde Bira. (35; "alabilir miyim" bugün kırık: `?` ve fiil listesi; yüksek)
2. "5 bakır, üstü kalsın" (4 bakırlık bira): bira envanterde, kese −5, barmene 1 bakır bahşiş. (35; bugün bahşiş ayrıştırıcı yok → kırık, 3b'ye girer; yüksek)
3. Oda ve uyku: pazarlık başarılı → indirim ya da açık ret nedeni; öde → `inn_room` kaydı + anlatıcıya "oda tutuldu"; "odama gidip uyuyorum" kayıt varken çalışır. (37, 38; bugün kırık; orta)
4. Tüketim: yemek ye, bira iç → envanterden azalır; ok at → ok sayacı azalır ve sayaç paketten tohumlanır. (54, 56; bugün kırık; orta)
5. Silah: Greatsword'lu Fighter saldırır → "uygun silahın yok" çıkmaz. (39; bugün kırık: kuşanma yok; orta)
6. Savaş eylemleri: Ready tetik ve karşılıkla çalışır (eksik tetikte Türkçe, anlaşılır mesaj); "rakibe yaklaşıyorum" savaş hareketi sayılır; Dash, Second Wind, Action Surge bozulmadan kalır (yeşil, korunur). (40; yüksek)
7. Çıkış: odadan çıkış → konum sokak (üst mekân); başka mekâna girmez. Motor testi çıkış kodunu doğrular (doğru çalışıyor, yeşil); sahne atlaması gerçek zincir senaryosudur. (42; düşük)
8. Konuşma kipi: uyku, mekân değişikliği, "konuşmayı bitir", ölüm sonrası kip kapanır; "satıcıya soruyorum" eski kişiyle cevaplanmaz. (4, 15, 41; kısmen kırık; orta)
9. Kaçış: 8a çıkışlı sahnede kaçış çalışır; 8b çıkışsız sahnede tur kaybedilir (BİLİNÇLİ, yeşil olmalı); 8c başlangıç ve sokak sahnelerinde çıkış tanımlıdır (bilinen kırık, 3c veri işi). (21; yüksek)
10. Ölüm: 0 HP → ölüm zarları → ölünce savaş düğmeleri ve konuşma kipi kapanır, ekran tutarlı (mod fark etmez; ölüm modları sonra). (25–27)
11. Geri Al ve yenileme: kese, envanter, oda tam geri gelir; yenileme sonrası durum aynı. SIFIR TOLERANS, yeşil olmalı. (29, 31)
12. Yetersiz bakiye: kesenden fazla teklif reddedilir, kese değişmez (bugün yeşil, korunur; `purse_below_base`).
13. Ham komut sızıntısı: tezgâh ve kartla alışverişte sohbete `/__direct_shop_buy__...` düşmez. (52; ui-labels dalında düzelmiş olmalı)
14. Başlangıç kesesi: yaratma ekranında gösterilen kese = oyun başındaki kese (sınıf altını metinde kalmaz). (34; bugün kırık; orta)
15. Cinayetin sonucu: Ferumel'i öldürmenin dünyada karşılığı var. `known_broken` + `xfail` (3c). (47)
16. Geçmiş zaman: "az önce 5 bakır verdim" yeni teklif açmaz. Motorda tek başına tekrarlanamaz: sahte "ön okuma" para verdi derse kart açar. Bu yüzden önce sahte-ön-okumalı motor testi (bugün kırık: hiçbir yerde geçmiş zaman kontrolü yok), sonra gerçek zincirde modelin ne okuduğu. (3; yüksek)

## 5. Gerçek zincir senaryoları
Çekirdek 4 (varsayılan): fiyat hatırlama (barmen 3 tur sonra hâlâ 4 bakır, "öyle demedim" demez; 36), ödeme sonrası tutarlılık (barmen "parayı bırakmadın" demez), motor reddi sonrası anlatıcı uyumu (motor "uygun silah yok" derken anlatıcı saldırı anlatmaz; 39), savaş başlatma ve gecikme ("kafa atıyorum" net başlar; 8, 19).
Elle istenince (ek 2): boş cümle ve parantezli replik (43, 45), evren dili (46, "Aleykümselam"), çıkış sahne atlaması (42).
Kurallar: her senaryo 3 kez koşar; sonuç "3 üzerinden kaç" olarak yazılır; kontroller durumda (kese, envanter, kip), metin kontrolü kısa ve sade (`yasak_metin`); koşu yalnız Kadir "yap" deyince, her koşunun harcaması kayda yazılır.

## 6. Gecikme ölçümü (gözlem, davranış değişmez)
- `ModelChain`'e isteğe bağlı gözlemci: her sağlayıcı denemesinde `sağlayıcı, sonuç, atlama nedeni, saniye`. Bugün bu yalnız log satırı (`Model chain skipped/answered`). Dönüş değeri `(cevap, sağlayıcı)` çifti DEĞİŞMEZ (iki çağıran var).
- Adaptörde (`ollama_adapter.py`) zincir çağrısının toplam süresi ölçülür: Gemma da buradan ölçülür (zincir dışında).
- Gerçek zincir koşucusu adım başına `sağlayıcı, saniye` tablosu yazar (3 koşunun ortancası ve en kötüsü).
- Bilinen: 20 sn çağrı sınırı + 25 sn bulut yürüyüşü + Gemma ≈ 30 sn olası (orta; loglar okunmadı). Kaynak ölçümle bulunacak, bulunamazsa raporda "bulunamadı" yazılır.

## 7. Harcama kaydı (davranış değişmez; engel yok)
- Ayrı, yalnızca yazan günlük kayıt: sağlayıcı başına çağrı, girdi, çıktı, Gemini düşünme tokenı; Gemma da sayılır. Dosya `%LOCALAPPDATA%\AI-DND\` altında. Yeni dosya, `model-chain-spend.json` (Haiku aylık) olduğu gibi kalır; `HaikuSpend` kapı görevini sürdürür, ona ek görev verilmez.
- Fiyat tablosu ayar dosyasında: Haiku başlangıç değeri girdi 0,10 ve çıktı 0,50 USD/milyon token (eski kod sabitleri, GÜNCELLİĞİ DOĞRULANMADI); Gemini "bilinmiyor". Uyarı yalnız bilinen fiyatları toplar.
- Uyarı: günlük bilinen toplam 3 USD'ye gelince log satırı + sağlık uç noktasında `harcama_uyarisi` alanı. Durdurmaz.
- Kayıt yazılamazsa çağrı yine yapılır (Haiku defterinin tersi, bilinçli): yalnız uyarı.
- Bugünkü durum (okuma): bu ay Haiku ≈ 6,14 M girdi, 198 bin çıktı token; eski sabitlerle ≈ 0,71 USD (yaklaşık).

## 8. Testler (yeni parçalar için)
Gözlemci davranışı değiştirmiyor (dönüş ve sıra aynı); günlük kayıt gün değişince sıfırlanır; okunamayan dosya oyunu durdurmaz; Gemini düşünme tokenı sayılır; uyarı yalnız bilinen fiyatla 3 USD'de çıkar; kayıt yazılamazsa çağrı yapılır. Çalıştırıcı için: bilinen kırık işareti `xfail(strict)`; düzelen test "işareti kaldır" diye uyarır; tam test paketi 0 kırık kalır.

## 9. Rapor ve geçme ölçüsü
Rapor `ADIM2_RAPOR_<tarih>.md` (Türkçe): senaryo tablosu (geçti / bilinen kırık [madde] / YENİ KIRIK; N, M, Z satırı; türe göre gruplu), gerçek zincir "3 üzerinden kaç", gecikme tablosu, harcama özeti, 3 senaryonun ham adım kaydı (Kadir örnekle denetler).
Sıfır tolerans: senaryo 11, 12 ve para/kayıt adımları `known_broken` olamaz; kırılırsa adım geçmez.
Geçer: (1) motor senaryoları depoda koşar, tam test 0 kırık; (2) her bilinen kırığın madde numarası var, ayrı sayılır; (3) gerçek zincir 4 × 3 koşuldu (Kadir "yap") ve rapor çıktı; (4) 30 sn kaynağı rapora yazıldı (veya "bulunamadı"); (5) harcama kaydı ve uyarı testleri geçer; (6) Kadir raporu okudu. "Kabul" yalnız Kadir'dir.
3b'ye devir: bilinen kırık listesi 3b'nin kontrol listesidir; her 3b görevi ilgili işareti kaldırır.

## 10. Kapsam dışı
Makine kırık sayacı, davranış sınamaları, okunan oyun (ayrı adım). Kadir'in elle 11–19 testleri. Bahşiş ve oda kaydının GERÇEK uygulaması (3b). Arayüz düzeltmeleri. Ölüm modları (sonra).

## 11. Açık noktalar / riskler
- Ön okuma ayarı (`AI_DND_FRONT_PROPOSAL=1`) oynayışta açık mı bilinmiyor; senaryolar ayarın iki hâlinde de yazılır, kontrol plan aşamasında.
- Gerçek modelin bazı hataları (geçmiş zaman, sahne atlaması) yalnız gerçek zincirde görülür; motor testi modelin okuduğunu taklit eder.
- Kesinlik: durum alanları yüksek; Greatsword, oda, tüketim, kese orta; sahne atlaması ve 30 sn düşük/orta. Hiçbiri çalıştırılarak doğrulanmadı.
- `HaikuSpend` fail-closed; günlük kayıt ayrı olduğu için Gemini'yi kapatmaz.
- Çalışan bir API şu an `c-merge` sürümünde (Haiku 4 USD sınırı hâlâ var); yeni dal ayrı bir sürüm olacak.

## 12. Uygulamada eklenenler (yürütme sırasında, denetleyici kararıyla; Kadir uykudayken, geri alınabilir)
- Adım eylemleri (§3): `undo` (ürünün kendi geri alma yolu) ve `reload` (taze yönetici, kayıttan okuma; yeniden başlatma gibi); ikisi yalnız `true` alır.
- `expect` anahtarları (§3): `tezgah` (tezgâh teklifi: kişi, ürün, birim fiyat), `kisi_kese` (kişi kesesi), `anlaticiya_giden` (anlatıcıya giden bağlam), `cephane` (ok sayacı), `hareket` (savaş hareketi).
- `setup` anahtarları: `character`, `campaign_start`, `place`, `npcs`, `currency`, `inventory`, `ammunition`, `current_hp`, `seed`, `front_proposal`, `death_mode`.
- Sohbetle alışveriş motorda ekonomik karttan değil TEZGÂH teklifinden geçer (`/item shop_buy` ile onaylanır); senaryo 01 bunu gözler (`kart` null, `tezgah` dolu). Kadir'in istediği "sohbetle bira" bu yolla tamamlanıyorsa değişiklik gerekmez; değilse 3b tasarım kararıdır.
- Madde 38 ("anahtarı alıp odaya gidiyorum") motor yolunda BUGÜN GEÇİYOR; oynanışta görülen "eline geçen bir şey yok" modelin anlatısına/okumasına bağlı görünüyor. Gerçek zincir adımı gerekebilir, bu adımda kurulmadı.
- Tam test paketi: görevler boyunca bilinen sıra bağımlı `test_town_knowledge … test_a_failed_model_still_points_at_a_real_lead` kararsızlığı bir kez görüldü (tek başına geçer); Adım 2 ile ilgisi yok.
