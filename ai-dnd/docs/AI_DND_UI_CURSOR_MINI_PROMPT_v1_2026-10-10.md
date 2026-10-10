# AI-DND — Cursor Mini Prompt: Ouroboros Ana Menü ve Karakter Yaratma

**MODE: CURSOR AGENT | LANGUAGE: TURKISH**

Proje sahibinin onayladığı görsel yönü uygula. Önce şu belgeyi oku:
`ai-dnd/docs/AI_DND_UI_STYLE_DIRECTION_v1_2026-10-10.md`

**Amaç:** AI-DND oyuncuya gerçek bir Forgotten Realms RPG'si gibi hissettirsin; teknik dashboard/AI-chat görünümü olmasın.

**Kapsam (yalnız oyuncu frontend'i):**
1. Ana menü: ouroboros amblemli, sisli/kadim/sinematik ama sade; kömür + sıcak altın + derin zümrüt. Yeni Macera, Maceraya Devam Et, Karakterler ve Ayarlar mevcut gerçek akışlara bağlı olsun. Yeni sahte rota/işlev ekleme.
2. Karakter yaratma: aynı görsel dil. Kompakt adım göstergesi; solda seçim kartları, sağda seçilenin doğrulanmış detayı; altta sabit Önceki/Sonraki. Kartlar ayırt edilebilir, kontrast güçlü, oyuncu dili tutarlı Türkçe.
3. **1920×1080'de ana akışlar sayfa düzeyinde dikey scroll gerektirmesin.** 1366×768 ve küçük pencerelerde kırpma yerine responsive düzen ve gerekirse sadece panel içi scroll. Metni küçülterek gizleme.
4. Ortak renk/spacing/button/panel token'ları; görünür keyboard focus, erişilebilir kontrast, reduced-motion desteği. Aşırı animasyon veya neon kullanma.

**Uygulama:** Önce gerçek menü/karakter oluşturma bileşenlerini ve mevcut route'ları bul. Minimum dosyayla kademeli UI düzenlemesi yap. Kullanılabilecek mevcut varlıkları tercih et; dışarıdan telifli FR görseli dahil etme. Mevcut ana işlevleri koru.

**Değiştirme:** Python mekaniği, canonical state, D&D/lore doğruları, Qwen (tur başına maks. 2 çağrı ve deterministic fallback), save/SQLite, oturum izolasyonu, şehir kapıları, lore pinleri, `.gitattributes`, F01, yayın/production/deploy ayarları. Git commit/push/merge/reset yok. Frontend yalnız sunar, gerçeklik üretmez.

**Faz yönetimi:** F01 PASS/CLOSED durumunu yeniden tartışma; Production NO-GO sıradan UI tasarımını durdurmaz. Uygulama için henüz açılmamış bağlayıcı faz koşulları varsa bunları sessizce geçersiz sayma: kod değiştirmeden tasarım/izole prototip hazırlayıp tek somut engeli raporla.

**Sonuç:** Değişen dosyalar, kısa uygulama notu, gerçekten çalıştırılan testler, 1920×1080 her ekranda scroll gözlemi, 1366×768 uyumu ve kalan sorunları Türkçe bildir. Uygulanmayan veya gözlenmeyen şeyi PASS diye yazma.

**İşlemi şimdi başlat; gereksiz genel plan döngüsüne girme.**
