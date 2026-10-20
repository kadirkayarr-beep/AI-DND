# AI-DND — Geliştirme Belgeleri

Bu dizin, **mimari ve geliştirme** belgeleri içindir. Oyuncu arayüzü veya oyun gerçeği kaynağı değildir. Başlıklar tarihsel durumları değiştirmez.

## Aktif çalışma alanı

- Birincil Windows geliştirme alanı: `C:\Users\Kadir\Desktop\AI - DND`
- Cursor ve Replit için ortak aktif geliştirme dalı: `dev/ai-dnd` (upstream `origin/dev/ai-dnd`; GitHub `kadirkayarr-beep/AI-DND`)
- Kararlı entegrasyon dalı: `main`. Terfi doğrulama ve açık owner onayı ister.
- `recovery/a1-freeze-288f5de` ile önceki Phase 8 worktree'leri (`AI-DND-phase8`, `AI-DND-phase8-expansion`) tarihseldir; aktif geliştirme tabanı değildir.
- Değişim aynı doğrulanmış `dev/ai-dnd` commit'inden yapılır. GitHub eşitlemesi kontrollüdür; zorlayıcı veya yıkıcı eşitleme yapılmaz. Cursor ve Replit birbirinin kaydedilmemiş işinin üzerine yazmaz.

## Araştırma ve aşamalı planlama

- [Yedi depo incelemesi ve fırsat haritası — 20 Ekim 2026](research/2026-10-20/README.md): tam raporlar, sabit kaynak commit'leri ve ajan okuma sınırları. Kayıt/planlama onayıdır; uygulama, merge veya yayın izni değildir.

## Aktif başvuru noktaları

| Konu | Belge |
|---|---|
| Onaylı gelecek yol haritası | [Future Project Bible v2.3.2](AI-DND_Future_Project_Bible_v2_3_2_PROPOSED.md) |
| Yol haritası için ayrı owner onayı | [v2.3.2 Owner Approval](AI-DND_Future_Project_Bible_v2_3_2_OWNER_APPROVAL_2026-10-09.md) |
| Phase 8 yerel mühendislik checkpoint'i | [Phase 8 Local Checkpoint Closeout](PHASE8_LOCAL_CHECKPOINT_CLOSEOUT_2026-10-09.md) |
| Stage 10A geçmiş kapanış kayıtları | `STAGE10A_*.md` (yerlerinde korundu) |
| Stage 10B yerel kabul ve inceleme kayıtları | `STAGE10B_*.md` (yerlerinde korundu) |
| Test ve lore inceleme kayıtları | [evidence/](evidence/) |
| Eski Project Bible sürümleri | [archive/future-project-bible/](archive/future-project-bible/) |

### Kaynak önceliği ve sınırlar

- Python mekanik ve kalıcı oyun durumunun otoritesidir; lore otoritesi Forgotten Realms bilgisi, kabul edilmiş campaign olayları ise campaign canon oluşturur. Qwen bu gerçekleri değiştiremez.
- **Onaylanan v2.3.2 dosyasının baytları değiştirilmemiştir.** `PROPOSED` başlığı tarihsel olarak korunur, geçerli owner onayı ayrı belgedir.
- Stage 10A kapalıdır. Stage 10B yerel kabul kanıtı vardır; genel canlı yayın/release sertifikası değildir.
- Phase 8 **yerel geliştirme checkpoint'i CLOSED**, fakat **live-release NO-GO** olmaya devam eder.
- Waterdeep ve Baldur's Gate taslakları onaylanmış/aktif şehir değildir. Phase 9 açılmaz.
- Tarihsel belgelerde eski Project Bible dosya yolları görünebilir: **orijinal metinlere dokunulmadan** sürümler [arşive taşınmıştır](archive/future-project-bible/README.md). Eski yolları aktif kaynak gibi kullanmayın.

### İlgili ayrı dosyalar

Master Handoff v3 ve v2'nin masaüstündeki bağımsız referans kopyaları `Desktop/Belgeler/Proje_Notlari/AI-DND_Handoff/` altında tutulur. Arşivleme sırasında Git çalışma ağacı `AI-DND-phase8-expansion` klasöründeydi. Ayrı worktree'ler veya yedekler arşivleme sırasında taşınmamıştır.

**Not:** Bu düzenleme dokümantasyon gezinimini kolaylaştırır; testlerin tekrar geçtiği, yeni uygulama izni verildiği veya bir şehrin aktive edildiği anlamına gelmez.
