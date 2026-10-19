# Yerel kişi kabulü: aynı action_id replay incelemesi (2026-10-19)

Bu, sabit aday üzerinde bağımsız bir ürün testidir. **Canlı Qwen veya insan oynanış kabulü değildir.** Model deterministik bir test ikamesidir; FastAPI tur rotası, `SessionManager`, `CampaignStore` (geçici SQLite), receipt tablosu `campaign_turn_actions` ve sahiplik kontrolleri gerçek çalışır.

## Kaynak

- Depo: `kadirkayarr-beep/AI-DND`
- Aday: `b7a1d5f11974254085488dbf8ab3c1e574c80f3a` ("Archive local NPC persistence verification"), ebeveyn `65803c762f4f2423764e2e6898bbe73d24395b7f`
- `origin/feature/ai-freedom-first-slice-20261019` ucu = aday (fetch sonrası doğrulandı)
- Ortak checkpoint `96150a000e4eff5d65b0653359536e7eae82a624` adayın atası
- Görev dalı: `cursor/local-person-replay-review-20261019`, worktree `AI-DND-local-person-replay-review`
- Üretim kodu, `test_local_person_persistence.py` ve CI seçici yapılandırması değiştirilmedi.

## Komut

```powershell
cd ai-dnd
$env:PYTHONUTF8='1'
$env:REPLAY_REVIEW_EVIDENCE_DIR='<bu klasör>'   # isteğe bağlı; adım sayımlarını JSON olarak yazar
python -m unittest api.tests.test_local_person_replay_review -v
```

Sonuç: **6/6 OK** (`unittest-run.log`). Komşu testler `test_local_person_persistence` + `test_http_two_player_isolation`: **10/10 OK** (`neighbor-run.log`).

## Testler ve sayımlar

Sayımlar SQLite'tan okunur: `history` = `campaign_history` satırı, `receipt` = `campaign_turn_actions` satırı, kişi = kalıcı `engine_save.world_state.npcs` içindeki yerel kişi. Model çağrısı kümülatiftir.

| Test | Adım | HTTP | Model | History | Receipt | Kişi |
|---|---|---|---|---|---|---|
| `test_same_action_id_replay_returns_receipt_without_new_work` | ilk kabul | 200 created | 1 | 1 | 1 | Neris |
| | aynı action_id replay | 200 (aynı gövde) | 1 | 1 | 1 | Neris |
| | aynı action_id, farklı mesaj | 409 `action_id_conflict` | 1 | 1 | 1 | Neris |
| `test_same_action_id_replay_survives_http_resume_and_cold_restart` | ilk kabul | 200 | 1 | 1 | 1 | Neris |
| | HTTP save+resume sonrası replay (aynı süreç) | 200 | 1 | 1 | 1 | Neris |
| | soğuk yeniden başlatma + HTTP resume sonrası replay | 200 | 1 | 1 | 1 | Neris |
| `test_same_action_id_elsewhere_never_returns_first_campaign_person` | ilk kabul (A) | 200 | 1 | 1 | 1 | Neris |
| | B oyuncusu A'nın oturumuna aynı action_id | 404 (yok kayıtla aynı gövde) | 1 | 1 | 1 | Neris |
| | A'nın yeni kampanyasında aynı action_id | 200 yeni tur | 2 | 1 | 1 | Taren |
| | B'nin yeni kampanyasında aynı action_id | 200 yeni tur | 3 | 1 | 1 | Taren |
| `test_rejected_proposal_is_replayed_without_creating_a_person` | kanonik Neris ile çakışan öneri | 200 `proposal_rejected` | 1 | 1 | 1 | — |
| | aynı action_id replay | 200 (aynı gövde) | 1 | 1 | 1 | — |
| | yeni action_id ile tekrar | 200 `proposal_rejected` | 2 | 2 | 2 | — |
| `test_save_failure_leaves_no_person_and_retry_creates_exactly_one` | enjekte kayıt hatası | 503 | 1 | 0 | 0 | — |
| | aynı action_id ile tekrar | 200 created | 2 | 1 | 1 | Neris |
| | aynı action_id replay | 200 (aynı gövde) | 2 | 1 | 1 | Neris |
| | aynı mesaj, yeni action_id | 200 `reused_local_person` | 3 | 2 | 2 | Neris |
| `test_later_description_finds_same_person_after_cold_restart` | ilk kabul | 200 | 1 | 1 | 1 | Neris |
| | soğuk yeniden başlatma sonrası yalnız tarifle selam | 200 `resolved`, `last_npc_id` = aynı kişi | 3 | 2 | 2 | Neris |
| | aynı arama cümlesi tekrar | 200 `reused_local_person` | 4 | 3 | 3 | Neris |

Adım bazlı ham sayımlar: `test_*.json`.

## Hangi save/resume sınırı gerçekten sınandı

1. **HTTP `/save` + `/resume`, aynı süreç.** Kampanya hâlâ canlıyken `SessionManager.resume_campaign` aynı bellek içi oturumu döndürür (`session_manager.py` 420-456; test bunu `session_id` eşitliğiyle doğrular). Yani bu sınır SQLite'tan yeniden yükleme **değildir**. Mevcut `test_local_person_persistence.py` yalnız bu sınırı kullanır.
2. **Soğuk yeniden başlatma.** Aynı SQLite dosyası üzerinde yeni `CampaignStore` + yeni `SessionManager` + yeni uygulama, ardından HTTP `/resume` (yeni `session_id`). Kişi, `origin_request_key` ve receipt SQLite'tan geri gelir; aynı action_id replay'i model çağırmadan ilk yanıtla (yalnız `session_id` farklı) aynı gövdeyi döndürür. Gerçek süreç sonlandırma veya ayrı Python süreci kullanılmadı.

## Sözleşmeye dayalı beklentiler (uydurulmadı)

- Receipt anahtarı `(campaign_id, action_id)` ve kampanya sahibine bağlıdır (`campaign_store.get_turn_action`). Bu yüzden başka kampanyada aynı action_id yeni bir turdur; test ilk kampanyanın yanıtını, kişisini veya görünüşünü döndürmediğini doğrular.
- Yabancı oyuncunun oturum isteği "kayıt yok" ile aynı 404 cevabını alır (`test_http_two_player_isolation.py` ile aynı sözleşme).
- NPC kimlikleri kampanya içi sıradır (`npc_001` her kampanyada tekrar edebilir); kimlik ayrımı içerik ve kampanyaya bağlı `origin_request_key` ile doğrulanır.
- Kayıt hatası `store.save_campaign` üzerinde mevcut testlerdeki kalıpla (`CampaignStorageError`) enjekte edildi; tur yolu, geri alma ve receipt yazımı gerçek çalıştı.

## Testin hata yakalama gücü

Dosya değiştirmeden, yalnız bellek içinde iki ürün davranışı bozuldu:

- `SessionManager.get_turn_action` her zaman `None`: replay/receipt kullanan 4 test kırmızı (4/4).
- `api.main._rollback_session` etkisiz: kayıt hatası testi kırmızı (1/1).

## Bulgu

Ürün hatası bulunmadı. Kurulum sırasında iki test hatam düzeltildi (imzasız store'da `manager.get` için `principal` gerekir; NPC kimliğinin kampanyalar arasında benzersiz olacağını yanlış varsaymıştım). Bunlar ürün başarısızlığı sayılmadı.

## Kalan boşluklar

- Canlı Qwen, gerçek Ollama ve insan oynanışı yok.
- Ayrı işletim sistemi süreci veya gerçek sunucu yeniden başlatması yok; soğuk sınır aynı süreçte yeni nesnelerle kuruldu.
- Eşzamanlı aynı action_id yarışı (iki istek aynı anda, `CampaignStaleError` dalı) sınanmadı.
- Kayıt hatası yalnız `save_campaign` girişinde enjekte edildi; SQLite işlemi ortasında kısmi yazma sınanmadı.
- Undo ile yerel kişi oluşturmanın geri alınması sınanmadı.
- Farklı konumdaki aynı cümle (istek anahtarı konuma bağlı) ve 6 kişi / 60 NPC sınırları sınanmadı.
- Yeni dosya günlük seçicide (`scripts/development_checks.json`) yok; yalnız `.\dev.ps1 -ApiDiscover` ile çalışır. Seçici yapılandırması bilerek değiştirilmedi.

## Birleşik dalda çağrı bütçesi takibi

Claude AI-freedom test modülüne iki dar sağlayıcı-sınırı testi eklendi. Testlerde `game.ollama.chat` gerçek çağrı sınırında sayıldı; canlı Qwen çağrısı yapılmadı.

| Akış | İlk gözlem | Düzenleme ve beklenen kanıt |
|---|---|---|
| Tarifle seçilen kişiyle sıradan konuşma | 2 gerçek `chat` çağrısı, telemetride toplam 1 | Ön ayrıştırma intent çağrısı olarak korunur; anlatı çağrısıyla toplam 2. |
| Tarifle seçilen kişiye geçerli söz | Söz kaydedildi, fakat sonuç anlatımı üçüncü `chat` çağrısını başlatıyordu | Kaydedilmiş `promise`/`goal` doğrudan yanıtı kullanılır; eylem korunur, toplam çağrı sayısı 2'de kalır. |

Verilen birleşik cümlenin `ve` ile yazılan biçimi deterministik yönlendiricide `plan` olarak sınıflanıyor. Bu çağrı bütçesi incelemesinde yönlendirici değiştirilmedi; geçerli `promise` akışını aynı tarif ve selamı koruyan noktalı biçimle doğruladık: “Omzunda halat taşıyan kişiye selam veriyorum. Sana söz veriyorum.”

Bu iki test mevcut `test_ai_freedom_resolution_boundary` selector'ü içindedir; önceki selector ve replay kapsamı korunur. Canlı Qwen, insan kabulü ve GitHub Actions bu dar doğrulamada çalıştırılmaz.
