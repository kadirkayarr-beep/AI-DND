# AI-DND kararlar ve yol haritası (2026-10-30)

Kaynak: Kadir'in Claude oturumundaki onayları. Bu dosya kabul kaydı değildir; ürün kabulünü yalnız Kadir verir.

## Güncel durum

- Altı sınıf (Sorcerer, Barbarian, Fighter, Rogue, Monk, Paladin) seviye 1-5, başlangıç 1-5.
- `dev/ai-dnd` = `33bdb6c`. Çalışma dalı `task/c-series-merge` = `587885b`, uzak yedekte. `main` değişmedi. Depo private.
- Test tabanı: 5038 test, 0 başarısız, 166 atlanan. Atlananlar guard altında koşamıyor; izole ortamda koşuluyor, sonuç henüz yok.
- Tarayıcı kabulü, gerçek Clerk, gerçek oyuncu testi yok. Altı sınıf "tam sınıf" değildir: DEX ASI eklenmekte; Weapon Mastery, diğer alt sınıflar, seviye 6+ ve büyü etkilerinin çoğu yok.

## Yol haritası sırası

"C serisi bitene kadar durma" kararının yerine geçer. Plan iptal edilmedi, yeniden sıralandı.

1. Altı sınıfı bitir ve birleştir: **tamam**.
2. Uzak yedek: **tamam**, sürüyor.
3. Test tabanı temizliği (özgün 22. iş): **büyük ölçüde tamam**, 166 atlanan test koşuluyor.
4. Model kapısı (özgün 13 ve 14): pilot 1 tamam, pilot 2 puanlanıyor, entegrasyon bekliyor.
5. Motor defteri + compact bellek: `narrative_memory` incelenip üstüne kurulacak.
6. Oyun testi ön koşulları: DEX ASI, yerel giriş (sürüyor), mikrofon.
7. Üç oturumluk oyun testi (P6).
8. İlk sürümü yaz.
9. Veri güdümlü büyü etki modeli, sonra özgün plana kalınan yerden dönüş: C05, kalan sınıflar, alt sınıflar, C07, X/L/U/D...

Oyun testi bulguları planın sıradaki maddesinin önüne geçer. DM tutarsızlığı, kural eksikliğinden önceliklidir.

## 18 varsayılan karar

Oyun kuralları
1. Başlangıç: DM birkaç seçenek sunar, oyuncu serbest de yazabilir.
2. Seviye: XP, DM ödül verebilir.
3. DEX ASI oyun testinden önce eklenir.
4. Zar: önemli atışlarda oyuncu tıklar.
5. Motorda karşılığı olmayan eylemlerde DM makul zorluk ve sonuç belirler; kalıcı değişikliği motor kaydeder.
6. Önemli NPC'ler ölebilir, koruma yok.
7. Dünya oyun içi zamanla ilerler, gerçek saatle değil.
8. Otomatik kayıt, geri alma yok.

DM ve model
9. Oyun testi İngilizce.
10. Tur başına en çok 30 saniye gecikme kabul; ikinci kontrol geçişi veya düşünme modu kullanılabilir.
11. Sansürsüz adaylar puanlamadan sonra denenir (TrevorJS Gemma indirildi, pilot 2'de).
12. Görsel ve müzik üretimi yerel; oyun içi harcama ayda en çok 25 USD.

Proje
13. `main` oyun testi geçince güncellenir.
14. Eski worktree'ler tek tek onayla temizlenir.
15. Haftalık git bundle D diskine (ilki `D:\AI-DND-yedek`).
16. Linear kullanılmıyor; takip Jarvis'in sayfası, teknik durum HANDOFF.md.
17. Mekanik kabulü test ve bağımsız inceleme; ürün kabulü yalnız Kadir.
18. Donanım yükseltme planı yok; 8 GB VRAM'e göre tasarım. Depo private kalır.

## İlk sürüm kararları

- Forgotten Realms, Neverwinter çevresinde küçük ama yoğun açık dünya; kendi dünya sonra.
- Altı sınıf, seviye 1-5; solo + geçici yoldaş NPC.
- Anlatımlı savaş; harita sonra.
- Gerçek ölüm, D&D kurallarıyla diriliş olası; tanrı kurtarışı nadir ve garantisiz. Varsayılan mod gerçek ölüm olacak; mevcut "Normal" (çatışma başına dönüş) buna uymuyor.
- Kalıcı tek kampanya, 1-2 saatlik oturumlar.
- İki katmanlı bellek: motor defteri kesin gerçekler, compact özet ton ve ilişki. Çelişkide defter kazanır, özet durum yazmaz.
- DM anlatım tarzı kampanya başında seçilir. Sesli anlatım sonra.
- Mikrofon ilk sürümde, büyük iş değilse. Öneri yerel Whisper.
- Çekirdek İngilizce, oyuncu dili TR/EN yönü; geçiş oyun testinden sonra, aşamalı.
- PC önce, telefon ileride.
- Müzik, ses, özgün portre, mekân görseli şart, ilk sürümden sonra.
- Yerel giriş modu; Clerk herkese açılırken. Şimdilik kullanıcı yalnız Kadir, tamamlanınca herkes.
- Lisans ileride; şimdi engel değil, kural verisi `content/` altında ayrı tutulur.
- İçerik: karanlık fantezi serbest. NSFW ayarı yetişkin içerik için, varsayılan kapalı. Reşit olmayanlarla ilgili cinsel içerik motor düzeyinde imkânsız; cinsel şiddet özelliği ve açık cinsel test metni yazılmaz.

## Pilot 1 sonucu

Bu fixture ve ayarlar için geçerlidir (8K bağlam, düşünme kapalı). Kadir 19 tam tur, ikinci puanlayıcı Claude 30 tur; korelasyon 0,67.

| | Gemma 4 E4B | Qwen 3.5 9B Q4 |
|---|---|---|
| Kadir ortalama | 96,7 | 75,7 |
| İkinci puanlayıcı | 86,2 | 66,1 |
| Sert hata (Kadir / ikinci) | 1 / 1 | 3 / 5 |
| Tercih | 15 | 4 (1 eşit) |
| Ortanca süre | 1,6 sn | 5,3 sn |

Formel kapı geçilmedi: Gemma T03-2'de oyuncunun yanlış iddiasını kabul etti. Gemma yanıtları daha kısa (119 / 190 token). Kazanan ilan edilmedi; önde giden aday Gemma 4 E4B.

## Jarvis'ten istenenler

Sıra: 1 takip sayfası, 2 özgürlük testi, 3 üç oturumluk bellek testi, 4 DM tarzı ön ayarları, 5 büyü etki modeli araştırması, 6 yerel ses ve medya araştırması, 7 Neverwinter içerik taslağı. Ayrıntı önceki mesajdadır. Sırrı anlatıcıya hiç göndermemek tasarım kararı olarak not edilsin: pilotta sır sızması model seçimiyle tam çözülmez.
