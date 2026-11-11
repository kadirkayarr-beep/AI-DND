# YOL HARİTASI REVİZYONU (Adım 2'den sonrası)

Durum: taslak, Kadir incelemesini bekliyor. Kod YOK, commit YOK, push YOK. Tarih 2026-11-04. Brainstorming sonucu (Kadir bölüm bölüm onayladı; karar listesi A1–D onaylandı: "hepsi önerinde").
Kaynaklar: `YOL_HARITASI_ONERI_20261031.md` (eski sıra), `OYUN_TARIFI_KADIR_20261031.md` (istenen oyun), `CANLI_OYUN_NOTLARI_20261103.md` (EK 4, 5, 6: oynanış bulguları), `ADIM2_TASARIM_20261104.md` ve `ADIM2_PLAN_20261104.md` (ölçüm adımı), `HANDOFF.md`.

## 1. Amaç
Adım 2'den sonraki yolu, Kadir'in başarı ölçüsüne ("30 dakika oyna, en az 2 gerçek iz bul, birinin peşine düş, seçiminin sonucunu gör, 'şimdi ne olacak?' de") en kısa yoldan ve güveni kırmadan ulaşacak biçimde sıralamak. Ürünü yalnız Kadir kabul eder.

## 2. Verilen kararlar (Kadir, 2026-11-04)
1. Öncelik: DÖNÜŞÜMLÜ (C). Her dilimde bir güvenilirlik işi ve bir oyun hissi işi birlikte gider.
2. Oyun hissi sırası: önce kişisel hafıza (1) ve görevler ve izler (2); sonra ilk 10 dakika (3) ve ilerleme (4: XP, seviye, büyü).
3. Yaklaşım 1: dilim dilim çekirdek, tek yazar. Her dilimde `game.py`'den yalnızca o parça yeni bir modüle çıkar; bir alanın tek sahibi olur, anlatıcı yalnız okur.
4. 3a (küçük gerçek sahnede kanıt; okuma ve kayıt ayrımı; haberci zinciri) DİLİM 3'ün içine girer. Bu, 2026-11-02 kararını ("3a geçmezse 3b başlamaz") bilinçli gevşetir: Dilim 1–2'nin kanıtı kendi oynayışlarıyla gelir, 3a'nın zinciri en çok dünya davranışlarında gerekir. Jarvis posta kutusu Dilim 3 başında yeniden açılır.
5. "Yama döngüsü yok" kuralı genişler: çekirdek gelene kadar yalnız sıfır tolerans hataları VE o dilimin kontrol listesi düzeltilir.
6. R7: sohbetle alışveriş tezgâh teklifinden (`/item shop_buy` ile onay) geçer; kart oda, bahşiş, hediye içindir.
7. R8: oda anahtarı eşya değil, oda kaydıdır; gerçek zincir koşusuna bir oda senaryosu eklenir.
8. `ui-labels` dalı Adım 2 bitince birleşir (Dilim 0). Gerçek zincir koşusu Adım 2 bitince, tahmini tutar görülüp onaylanarak. `task/step2-measure-20261104` dalı push'lanır (özel depo).
9. Önceki teyitler geçerli: testler olması gereken davranışa göre, bahşiş "üstü kalsın", savaşta satın alma reddedilir (R11), 3 USD/gün harcama uyarısı, ölüm modları 3b'den sonra, HANDOFF arşivi 3a'dan önce.

## 3. Sıra
0. Adım 2'yi kapat (Görev 14, 15, 16, sabah raporu, dal yedeği, HANDOFF arşivi).
1. Dilim 0: küçük arayüz turu + `ui-labels` birleşmesi.
2. Dilim 1: para ve kart tek sahip + kişisel hafıza.
3. Dilim 2: görev eşyası ve teslim, konuşma kipi, ret mesajları, savaş eylem yorumu + görevler ve izler.
4. Dilim 3: dünya davranışları (çıkışlar, "Etkileşime geç", anlatı kalitesi) + ilk 10 dakika + 3a kanıtı.
5. Dilim 4: ölüm modları + ilerleme (XP, seviye, büyüler, sınıf özellikleri).
6. Adım 4: Kadir tekrar oynar ve kabul eder (en fazla 3 kırık ve "devam ederdim").
7. Sonrası (eski adım 5–11): eski yönlendirmeyi silme, kendi dünya, defter, üç oturum, ayrı okuma modeli, yabancı oyuncular, lisans. Dilimler oturunca ikinci bir brainstorming ile yeniden ele alınır.

## 4. Her dilimin kuralı
- Girdi: Adım 2'nin o dilime ait `known_broken` işaretleri (madde numaralarıyla) kontrol listesidir.
- Tasarım: her dilim kendi brainstorming, tasarım belgesi ve planıyla gelir; her biri Kadir onayından geçer.
- İçerik: bir güvenilirlik işi + bir oyun hissi işi. Modül adayları dilim tasarımında kesinleşir.
- Bitiş kapısı (hepsi birlikte): (1) ilgili işaretler kalkar ve yeni kırık 0; (2) tam test paketi 0 kırık; (3) bağımsız inceleme (en güçlü model); (4) gerçek zincirde kısa kontrol (Kadir "yap"; harcama günlük kayıtta); (5) Kadir 30 dakika oynar, notlar sonraki dilimin girdisi olur (GEVŞETİLDİ 2026-11-04: şimdilik beklenmez; deftere "oynayış bekliyor" yazılır, Kadir sonra oynar).
- Güvenlik: para ve kayıtta sıfır tolerans; birleşme Kadir onayıyla; push ve yedek ayrı "yap"; anahtarlar yazdırılmaz.
- Süre tahmini yazılmaz.

## 5. Dilimlerin içeriği (taslak; dilim tasarımında kesinleşir)
Madde numaraları `CANLI_OYUN_NOTLARI_20261103.md` içindedir (1–56 ilk bölüm ve EK 4; 100+T EK 5; EK 6 arayüz).
- **Dilim 0 (arayüz):** 34 (kese özeti: sınıf + geçmiş = toplam), 51 (panel biçimi), 52 (ham komut; `ui-labels`), 53 (İngilizce metin), 20 (savaş etiketleri), geri alınan metin, "Görevler 0" sayacı, tezgâh panelinin savaşta gizlenmesi (R11 arayüz kısmı), savaş başlangıç bildirimi ve düşman canı (19).
- **Dilim 1:** Güvenilirlik: 35, 36 (fiyatı motor sahiplenir), 37 (pazarlık), 38 (oda kaydı), 103 (reddedilen para kesilmez), 110 (oda cümlesi sayım işini bitirmez, saat atlamaz), 54, 56, 107 (tüketim ve cephane), 3 (geçmiş zaman), bahşiş ayrıştırıcı. Oyun hissi: kişisel hafıza (116: iki karakterde kaybolan kişisel bilgi; kaydetten sonra bile).
- **Dilim 2:** Güvenilirlik: 115 (görev eşyası çoğalması, doğru alıcı), 4, 15, 41 (konuşma kipi), 39, 40 (silah kuşanma, ret mesajları, Ready, yaklaşma), 113 (çift karşı saldırı), 114 (savaşta satın alma). Oyun hissi: görevler ve izler (görev günlüğü tek kaynak, olaylar birbirine bağlanır).
- **Dilim 3:** Güvenilirlik: 21/105 (çıkışlar), 7/16/18 ("Etkileşime geç"), 42 (çıkış sahne atlaması), 47 (cinayetin sonucu), 43–46 (anlatı kalitesi: boş cümle, parantezli replik, selam kalıbı), 50 (bayat ipucu). Oyun hissi: 49 (ilk 10 dakika), 48 (iş bulma döngüsü). 3a kanıtı: küçük gerçek durumda okuma/kayıt ayrımı, makbuz, geri alma, haberci zinciri.
- **Dilim 4:** Güvenilirlik: ölüm modları ve ölü ekranı (25–27, 6), Stunned/Incapacitated kaçamaz kuralı. Oyun hissi: 111 (XP, seviye), 112 (büyü hedefi, yuva, desteklenmeyen kullanım), sınıf özellikleri (Hunter's Mark, Hex, Sneak Attack).

## 6. Riskler ve açık noktalar
- Dilim içerikleri taslak: her dilimin brainstorming'i kapsamı değiştirebilir.
- "Dönüşümlü" ritim koordinasyon ister; tek yazar kuralı paralel çalışmayı sınırlar.
- 3a'nın gevşetilmesi ürün riski taşır: Dilim 3'te kanıt gelmezse Dilim 4'e geçilmez.
- Kişisel hafıza (116) tasarım olarak belirsiz: mevcut anlatı hafızası ile kayıt arasındaki bağ doğrulanmadı.
- Gerçek zincir koşularının toplam maliyeti ölçülmedi.
