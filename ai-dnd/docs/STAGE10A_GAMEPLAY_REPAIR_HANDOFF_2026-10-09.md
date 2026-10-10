# Cursor integration handoff — Stage 10A gameplay repair, 9 Ekim 2026

## Durum ve çalışma yeri

Stage 10A **PASS değildir**. İzole gerçek Qwen smoke mekanik sonucu `MECHANICAL_PASS_NEEDS_MANUAL_NARRATION_REVIEW` oldu. Manuel anlatı incelemesi yapılmadı. **Stage 10B BLOCKED. Production NO-GO.**

Tek çalışma yeri: `C:\Users\Kadir\Desktop\AI-DND-phase8-expansion`.

Branch: `phase8/emergent-storytelling-expansion`.

HEAD: `f63d952506064cd59e960f1e3efa6627d4e52053`. Commit, push, merge, reset veya clean yapılmadı. Waterdeep ve Baldur's Gate açılmadı. Shop owner, Neverwinter lore paketi, production save ve veritabanı şeması değiştirilmedi.

## Üretim onarımı ile test düzeltmesi

Üretim onarımı `ai-dnd/game.py` içindeki `_unsupported_available_quest_claim`. `yok` artık cümlenin herhangi bir yerinde geçtiği için olumlu görev iddiasını aklamaz. Olumsuzluk, görev kelimesinin bulunduğu cümlecikte aranır. Kabul edilmiş görev veya aktif oturumun `quest_offers()` kaydı yoksa olumlu uygunluk iddiası reddedilir. Teklif varken kayıtlı başlığı söyleyen cümle reddedilmez.

Aynı dosyada daha önce eklenen yerel taverna çıkışı ve açık isim kaydı bu turda davranış olarak değiştirilmedi. Dönüş zaten mevcut çıkış sahibiyle `fr:city:neverwinter` konumuna yazılıyordu; `start_travel` çağrılmıyordu. Kayıt hatası, testin `game.serialize_game_state()` ile varsayılan oturumu yazmasıydı.

Test düzeltmeleri:

- Dönüşten hemen sonra konum `fr:city:neverwinter`, yeniden girişten sonra aynı yerel taverna. Son konum tek başına ölçülmez.
- İsim kaydı `session.serialize_game_state()` ile aynı oturumdan alınır. `npc_002` Arven öğrenmez.
- İkinci NPC'nin bellek listesinin boş olması gerekmez; Arven kaydı ve yanlış hatırlama olmamalıdır.
- Çatışma testi `start_combat` ile gerçek kayıt kurar. `tavernaya gidiyorum` `combat_travel` ile reddedilir.
- Görev denetimi test oturumu üzerinden çağrılır.
- Smoke, Elara cümlesinden sonra NPC sayısının 1 olmasını istemez. Taverna girişinin oluşturduğu NPC kimlikleri aynı kalmalı, Elara adlı kayıt ve oyuncu adı açıklaması oluşmamalıdır.

`ai-dnd/shop_creation.py` hash'i shop handoff ile aynıdır.

## Geçici tanı logları

`game.py` içinde Stage 10A tanı logları duruyor. Her ilgili tur `C:\Users\Kadir\Desktop\AI-DND-phase8\debug-6a7cc6.log` dosyasına NDJSON yazar. Bunlar ürün davranışı değildir. Sahip log kanıtını kabul ettikten sonra kaldırılmalıdır. Bu haliyle production'a alınmamalıdır.

## Kaynak SHA-256

| Dosya | SHA-256 |
|---|---|
| `ai-dnd/game.py` | `BF9DA3F5BA6482657739389CC0BB78CFE3ECC7D12AC0E2E2CFE58FD180DD3100` |
| `ai-dnd/living_world.py` | `0035E34356D026159015A694F37FEA5FD27B38CA73643E800CD6C59DBC8E1CD3` |
| `ai-dnd/local_dialogue.py` | `6E4E01E9311A8F38769DC00EF23D7C7AD9B0CB55B51EF64723643D598BC77102` |
| `ai-dnd/api/tests/test_stage10a_gameplay_repairs.py` | `FE1604E6EFE6A3493019FD4AE348F31A5676ABEFB400D71C0141F76DA1676D06` |
| `ai-dnd/api/tests/live_neverwinter_canon_smoke.py` | `A4629E9DC19EB872E957890BC55E811B576ED3EBE6DCBF84668B9108C9951109` |
| `ai-dnd/shop_creation.py` | `3F86AF37ECC79BC870C2D8C3F0E6188C8EEA404CFB6F61A31F2D94B8C3779C6D` |

## Test komutları

Çalışma dizini `ai-dnd`. `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`.

```text
python -m unittest api.tests.test_stage10a_gameplay_repairs -q
```

**8 test OK**, 0.116 saniye, exit 0.

```text
python -m unittest test_shops api.tests.test_explicit_shop_creation api.tests.test_live_neverwinter_smoke_diagnostics api.tests.test_lore_authority api.tests.test_lore_engine_integration api.tests.test_campaign_lore_persistence api.tests.test_lore_1501_freeze_contract api.tests.test_lore_1501_freeze_admission api.tests.test_lore_1501_admission_boundary api.tests.test_lore_1501_integration test_narrative_safety_calibration test_checkpoint_blockers api.tests.test_equipment_economy api.tests.test_equipment_economy_http api.tests.test_campaign_persistence api.tests.test_persistence_idempotency api.tests.test_stage10a_gameplay_repairs -q
```

**270 test OK**, 114.111 saniye, exit 0. Bu grup tüm depo değildir.

## İzole gerçek Qwen smoke

Komut: `python -m api.tests.live_neverwinter_canon_smoke`. Model `qwen3:8b`. `OLLAMA_HOST=http://127.0.0.1:11434`. Geçici SQLite. Eski shop evidence klasörü değiştirilmedi.

| Çalıştırma | Sonuç |
|---|---|
| `live-smoke-turn16-elara-count-fail.txt` | FAIL, exit 1, 16 tur. Taverna girişi `location_001` oldu. Elara turu yeni NPC veya isim açıklaması eklemedi; assertion hâlâ toplam NPC sayısının 1 olmasını istiyordu. |
| `live-smoke-rerun.json` | exit 0. `MECHANICAL_PASS_NEEDS_MANUAL_NARRATION_REVIEW`. 20 tur. En yüksek model çağrısı 2. |

İkinci çalıştırmanın ölçülen turları: 15 `location_001`, 0 çağrı, tamamlanmış giriş. 16 Elara reddi, açıklama listesi boş. 17 dönüş `fr:city:neverwinter`, 0 çağrı. 18 Arven, `NPC_MEMORY_EXPLICIT_PLAYER_NAME`, `npc_001`, 0 çağrı. 19 `etkin bir görev yok`, görev listesi boş, 0 çağrı. 20 restart sonrası aynı shopkeeper Arven'i hatırlıyor, 0 çağrı. Shop `shop_001` ↔ `npc_001` restart sonrası duruyor. Başlangıç ve resume konumu `fr:city:neverwinter`. Lore bağları `fr:world:forgotten_realms`, `fr:epoch:1501_dr`, `fr:region:the_north`.

## Kanıt

`.local/evidence/stage10a-gameplay-repair-20261009/`

Korunan shop klasörü: `.local/evidence/stage10a-shop-repair-20261009/`.

Git durumu: aynı yeni klasörde `git-status.txt`. Önceki lore ve shop dosyaları duruyor.

## Kalan engeller

- Manuel anlatı incelemesi yok. Stage 10A PASS yazılamaz.
- Tanı logları `game.py` içinde duruyor.
- Stage 10B açılmadı. Production onayı yok. Phase 9 başlamadı.
