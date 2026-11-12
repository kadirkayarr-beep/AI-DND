# Dilim 1 — J-013 (Jarvis incelemesi) kararları — 2026-11-04

Kaynak: J-013 (12 bulgu). Belge incelemesi; ürün kodu değişmedi. Her karar DILIM1_TASARIM/PLAN'a uygulanacak (Dilim 1 başlamadan önce, tek geçiş).

| # | Bulgu | Karar | Tasarım/plan değişikliği |
|---|-------|-------|--------------------------|
| 1 | Eksik cevap reddi siler; 8 kayıt sınırı ret ömrünü bozar | KABUL | Ret yalnız aynı NPC + ilgili teklif için açık `takes` ile kalkar; none/eksik/bozuk ret'i korur. Sınır 32; dolunca önce önceki günün kayıtları düşer, bugünküler asla sessizce düşmez. Görev 3 + 10 testleri. |
| 2 | Ret hangi ödemeye ait | KABUL | `declines` teklif/satır kimliğine (bahşiş, mal, oda) bağlanır. Kapsamı belirsiz genel ret = ödeme ilerlemez, doğal konuşma. Görev 3 + 10. |
| 3 | Hafıza 12 satırlık pencere | KISMEN | Kaynak ömrü görünümden ayrılır: NPC başına 40 `remember=true` kaynak, görünüm 3. 116 (uzun süreli) "Dilim 1: son 40 seçilmiş söz" olarak dürüst yazılır; tam arşiv sonraya. Test: 25 konuşma + 13+ remember. |
| 4 | NPC oyuncunun bilmediğini bilir | KABUL | NPC görünümü ayrı kurulur; kese toplamı yerine "uzattığı N bakır". Süzme seçim/bütçeden önce. Başka-NPC sızıntı testi. |
| 5 | Sıfır tutar/unclear çelişkisi | KABUL | Teklif açma ≠ para uzatma; yalnız "öneri hiç yok" eski yola düşer, `unclear` serbest yorum açmaz. Görev 4/8. |
| 6 | 200 karakter kırpma | KISMEN | Kabul edilen söz 600 karaktere kadar tam saklanır, görünüm 200; kırpılan parça "kanıt" sayılmaz. Düzeltme-bağı Dilim 1 dışı (not düşüldü). |
| 7 | İlgili satır ≠ destek | KABUL | `supports` yalnız gerçek örtüşme/kaynak sahipliğiyle; son-3 yedek bağlamdır, inkâr korumasını kaldırmaz. |
| 8 | Geri Al/atomiklik kanıtı | KABUL | Kayıt hatası, yanıt kaybı, bayt-aynı tekrar, gerçek resume, Geri Al sonrası sızıntı testleri eklenir. |
| 9 | 600 bayt ölçümü | KABUL | UTF-8 ölçüm, zorunlu alan taşma kuralı (öncelik: aktif işlem > bu turun sonucu > anı); son istem bütçesi ölçülür. |
| 10 | Panel "hayır" dalı | KABUL | Bahşiş, başarılı mal makbuzundan sonra teklif edilir; iki ayrı işlem olarak açıkça sınanır. |
| 11 | Gerçek zincir kapısı | KISMEN | Hafıza için 5 kanıt ayrı raporlanır; 04b gerçek adımı koşu listesine eklenir. Modelin ilk öğrenme alanını doldurması kontrollü bir gerçek örnekte denenir. |
| 12 | Tek yerde okunur sözleşme | KABUL | Tasarım başına bir sayfalık Türkçe güncel özet + güncel modül tablosu; D1–D24 değişiklik günlüğü olarak kalır. |

Maliyet/risk: tasarım belgesi uzlaştırma geçişi gerekir; kod yok. Yanlışsa geri alınır (belge).
