# Cursor integration handoff — Stage 10A shop repair, 9 Ekim 2026

## Durum ve çalışma yeri

Dükkân oluşturma hatası düzeltildi. **Stage 10A FAIL; Stage 10B BLOCKED; production NO-GO.** Tam canlı tanı senaryosu 20 tur ve API restart çalıştırdı; iki bağımsız kabul hatası kaldı. Production onayı verilmedi.

Tek çalışma yeri: `C:\Users\Kadir\Desktop\AI-DND-phase8-expansion`.

Branch: `phase8/emergent-storytelling-expansion`.

HEAD: `f63d952506064cd59e960f1e3efa6627d4e52053`. Commit/push/merge/reset/clean yapılmadı. Cursor aynı mevcut worktree üzerinde devam etmelidir. Başka checkout'a taşıma, kopyalama veya cherry-pick istenmiyor.

## Kök neden ve uygulama

Eski açık shop isteği `shop_setup/requested` üretip `verified_world_updates` olmadan anlatı aşamasına gidiyordu. Anlatıcı `narration_only=True` çalışıyordu. Sonraki aşama boş `create_shops` için `proposal_rejected` üretiyordu; shop validator ve creation owner hiç çağrılmıyordu. Qwen'in geçersiz bir shop alanı oluşturduğu kanıtlanmış değildi.

`game.py` içinde mevcut explicit-request, interaction-mode/target ve kapasite/duplicate kapılarından sonra dokuz satırlık routing eklendi. `shop_creation.resolve_explicit_request(session)` yalnızca bu kapılardan geçen istekte çağrılır. Python sabit yerel shop açıklamasını ve mevcut `living_world.stable_local_name` ile shopkeeper adını belirler. Model metni hiçbir alanda kullanılmaz.

Yeni owner, mevcut session-bound `create_shop_from_proposal` fonksiyonunu kullanır. Bu fonksiyon mevcut shop validator, NPC validator/creator, kayıtlı konum, kapasite, kimlik sayaçları, karşılıklı shop/NPC bağlantıları, tag'ler ve `PROCEDURAL_LOCAL_FICTION` katmanını korur. Başarılı kayıt anlatım çağrısından önce oluşturulur; Qwen yalnızca `created` sonucunu görür. Oluşturma başarısızsa deterministik cevap döner.

Yeni kayıt aynı mevcut API candidate-turn snapshot/autosave/rollback/receipt transaction içinde kalır. Yeni veritabanı, transaction, persist alanı veya session sahibi eklenmedi. Save/schema sürümleri değişmedi. Aynı action ID'nin replay'i Python oluşturmayı ve modeli tekrar çalıştırmaz; ikinci farklı istek mevcut duplicate kapısına takılır.

Hiçbir stok, fiyat, eşya, para, reward, quest veya resmî lore eklenmez. `/item market` çağrılmaz. Mevcut narrator-only schema, model world-proposal reddi, lore/Reality Gate ve fallback korunur. Yeni shop isteğinde bir narration çağrısı vardır; reddedilen narration yeniden denenmez.

## Bu çalışmada değişen dosyalar

| Dosya | Değişiklik |
|---|---|
| `ai-dnd/game.py` | Kapılardan sonra yeni Python shop owner'a routing; yalnızca 9 yeni satır. Dosyada önceden bulunan freeze-claim ve work-answer değişiklikleri ayrıca korundu. |
| `ai-dnd/shop_creation.py` | Yeni küçük Python owner; statik yerel kayıt, mevcut creator'a delegasyon, resolved outcome. |
| `ai-dnd/api/tests/test_explicit_shop_creation.py` | Yeni odaklı unit ve gerçek HTTP/SQLite transaction testleri. |
| `ai-dnd/test_shops.py` | Eski model-owned creation/schema beklentileri güncel Python-owned davranışa uyarlandı; owner reddi testi tutuldu. |
| `ai-dnd/api/tests/live_neverwinter_canon_smoke.py` | Yalnızca travel-away ve disclosure-ack kabul hataları ertelenerek kalan tanı/restart adımları çalıştırılır. İkisi de `scenario_failures` olarak saklanır; en sonda FAIL/exit 1 zorunludur. Önceden bulunan tanı/UTF-8/log koruma değişiklikleri korunmuştur. |
| `ai-dnd/docs/STAGE10A_SHOP_REPAIR_HANDOFF_2026-10-09.md` | Bu handoff. |

`api/tests/test_live_neverwinter_smoke_diagnostics.py` önceki çalışmadan mevcut olup bu uygulama turunda değiştirilmedi.

## Git ve SHA-256

Checkout başlangıçta dirty idi. Önceden bulunan lore staging/freeze dosyaları ve evidence klasörleri korundu; bu shop işi onları yeniden uygulamadı.

Son tam `git status --short`: `.local/evidence/stage10a-shop-repair-20261009/git-status.txt`. Tracked değişiklikler: lore authority `campaign_state.py`, `ingestion.py`, `models.py`, `player_knowledge.py`, `registry.py`; `api/main.py`; smoke; `game.py`; `test_shops.py`. Untracked dosyalar arasında önceki freeze/admission/claim modülleri, lore testleri/evidence klasörleri ve yeni shop owner/test/handoff vardır. Tam liste snapshot dosyasında bulunur. Evidence snapshot'ındaki tracked diff **önceden bulunan değişiklikleri de içerir**; topluca ters patch veya restore için kullanılmamalıdır.

Final kaynak hash'leri:

| Dosya | SHA-256 |
|---|---|
| `ai-dnd/game.py` | `842F3C1522F1E0D37ED66E72A76BD55AE023E079D25AFC17E2D12B0413A398DC` |
| `ai-dnd/shop_creation.py` | `3F86AF37ECC79BC870C2D8C3F0E6188C8EEA404CFB6F61A31F2D94B8C3779C6D` |
| `ai-dnd/test_shops.py` | `97889D8C42AC7CE28F02292B73EDE14FD9CF30AC598E39D5BA71D4BF4110C4AC` |
| `ai-dnd/api/tests/test_explicit_shop_creation.py` | `6E38DD5080726BC026E9FA2C6B790134454ED5A093E7E4DB4AE0B4B025679C25` |
| `ai-dnd/api/tests/live_neverwinter_canon_smoke.py` | `ADCBF42F1820DC31566AB929000BCFE8C83A0A6FD714ACD96645E5E134FA63C9` |

Makine tarafından okunabilir manifest: aynı evidence klasöründe `source-hashes.json`. `git diff --check` exit 0; yalnızca Windows LF/CRLF uyarıları çıktı.

## Test komutları ve gerçek sonuçlar

Komutların çalışma dizini checkout içindeki `ai-dnd`; Python process environment `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`.

İlk focused test grubu:

```text
python -m unittest api.tests.test_explicit_shop_creation api.tests.test_live_neverwinter_smoke_diagnostics -q
```

**9 test OK**, exit 0. İlk fixture denemesinde default session konumu kayıtlı olmayan bir yerdi; positive fixture kayıtlı `tavern` konumuna düzeltildi. Unknown-location negatif testi ayrıca tutuldu.

İlgili regresyonlar:

```text
python -m unittest test_shops api.tests.test_explicit_shop_creation api.tests.test_live_neverwinter_smoke_diagnostics api.tests.test_lore_authority api.tests.test_lore_engine_integration api.tests.test_campaign_lore_persistence api.tests.test_lore_1501_freeze_contract api.tests.test_lore_1501_freeze_admission api.tests.test_lore_1501_admission_boundary api.tests.test_lore_1501_integration test_narrative_safety_calibration test_checkpoint_blockers api.tests.test_equipment_economy api.tests.test_equipment_economy_http api.tests.test_campaign_persistence api.tests.test_persistence_idempotency -q
```

**262 test OK**, 94.888 saniye, exit 0. Beklenen negative-path ERROR logları suite failure değildir. Önceki daha dar 142-test taramada eski shop beklentileri nedeniyle 3 failure vardı; `ai-dnd-shop-regressions-initial-20261009.log` korundu. Test beklentileri yukarıda açıklanan yeni sahipliğe uyarlandıktan sonra 262-test grup geçti.

Son focused kontrol, restart sonrası gerçek HTTP replay ve RNG/history rollback assertion'ları eklendikten sonra:

```text
python -m unittest api.tests.test_explicit_shop_creation api.tests.test_live_neverwinter_smoke_diagnostics test_shops -q
```

**18 test OK**, 0.788 saniye, exit 0. Bir ara fixture kontrolünde `recent_narrations` yerine mevcut `recent_dm_narrations` alanı gerekti; düzeltildi. 262-test grubundan sonra gameplay kaynakları değişmedi; yalnızca test assertion'ları ve smoke'un başarısızlıkları erteleyerek tanıya devam etmesi değişti.

Kapsanan davranışlar: açık oluşturma; ordinary inquiry ve açık ret; duplicate ve same-ID replay; shop/NPC global ve local kapasite sınırları; bilinmeyen konum; karşılıklı ID link'i; save/resume ve resume sonrası HTTP receipt replay; autosave failure'da engine save/RNG/history/journal/narrative-memory/lore ve persistent payload rollback; kaydedilmemiş receipt yokluğu; ayrı kampanyanın değişmemesi; max 2 model-call; bozuk model world proposal sonrası tek çağrı ve fallback; inventory/currency/quest/economy alanlarının değişmemesi.

## İzole gerçek Qwen smoke

Komut:

```text
python -m api.tests.live_neverwinter_canon_smoke
```

Process-local `OLLAMA_HOST=http://127.0.0.1:11434`, model `qwen3:8b`. Her çalıştırma yeni geçici SQLite ve ayrı port kullandı. Bunlar yeni bağımsız smoke kampanyalarıdır; narration retry değildir.

| Çalıştırma | Gerçek sonuç |
|---|---|
| `ai-dnd-shop-live-20261009.json` | FAIL, exit 1; 15 tur, shop creation/duplicate/economy geçti; travel-away assertion'da durdu. |
| `ai-dnd-shop-live-complete-20261009.json` | FAIL, exit 1; travel failure korunarak 18. tura ilerledi; disclosure acknowledgement assertion'da durdu. |
| `ai-dnd-shop-live-full-20261009.json` | FAIL, exit 1; **20 tur**, gerçek API restart/resume, shop/NPC link persistence ve same-NPC name recall tamamlandı; iki önceki kabul hatası sonunda FAIL üretti. |

Son çalıştırmada turn 12: `created`, 1 model çağrısı, `shop_001` ↔ `npc_001`, current location Neverwinter. Turn 13 duplicate: `limit_reached`, 0 çağrı. Turn 14 economy: `unsupported`, 0 çağrı. En yüksek çağrı sayısı **2**; rebuilding check resolved oldu, HTTP 500 tekrarlanmadı. Tam smoke hiçbir turda yeni model retry yapmadı.

Turn 18'de player-name disclosure `npc_001` için canonical memory'ye kaydedildi. Turn 20'de restart sonrası aynı NPC: **“Evet, adının Arven olduğunu hatırlıyorum”**, 0 model çağrısı. Shop/NPC stable ID, reciprocal link, lore binding ve saved state restart kontrolleri geçti. Bu, travel/revisit başarısını kanıtlamaz.

## Kalan hatalar — bu kapsamda düzeltilmedi

1. **Travel/revisit FAIL:** `tavernaya gidiyorum` → `unverified`, “Bu yolun süresi henüz belirlenmiş değil; yolculuk başlamadı.” Oyuncu Neverwinter'dan ayrılmadı. Return turu “Zaten buradasın” dedi. Doğrulanmış rota süresi uydurulmadı; travel sahibi değiştirilmedi; smoke geçerli revisit kapsamı olarak sertifikalanamaz.
2. **Disclosure acknowledgement FAIL:** Exact smoke mesajında “lütfen bunu hatırla” bulunuyor. NPC turn 18'de yanlış “adını bilmiyorum” cevabı verdi (`answered_from_npc_memory`); aynı tur sonrası disclosure kaydedildi ve restart sonrası recall geçti. Memory/intent routing düzeltmesi shop repair kapsamında yapılmadı. Bu cevabın hedeflenenden farklı olduğu doğrudan transcript kanıtıdır; routing kök nedeni ayrı incelenmelidir.
3. **Manuel narration gözlemi:** Turn 19, empty production quest catalog'a rağmen meyhanede görevler duyulduğunu söyleyen model metni içeriyor. State'e quest/offer eklenmedi ve mekanik assertion geçti; bu prose source-grounding açısından ayrıca incelenmeli. Manuel narration PASS verilmedi.

Önceki oturumda gözlenen geniş `test_sessions`, `test_ai_pipeline_port` ve eski `test_smoke_turn_diagnostics` hatalarının tamamı bu çalışmada yeniden test edilmedi veya düzeltilmedi. 262 OK sonucu tüm repository testlerinin geçtiği iddiası değildir.

## Kanıtların konumu ve recovery

Dayanıklı kanıt klasörü: `.local/evidence/stage10a-shop-repair-20261009/`. Focused/regression logları, üç canlı JSON transcript, final stderr, tüm başarısız smoke'ların API logları, source hash manifest ve git status/diff burada saklandı. Tam run'ın `api-first.log` ve `api-after-restart.log` dosyaları `ai-dnd-shop-live-full-20261009/` altındadır. Geçici kampanya DB'leri kopyalanmadı; production save/DB kullanılmadı.

Devam etmeden önce aynı worktree'nin branch/HEAD/status ve beş kaynak hash'ini kontrol et. Yeni bir tanı denemesi yaparsan önce mevcut evidence'ı koru, yeni çıktı adı kullan. Testler için geçici CampaignStore kullan; `AI_DND_CAMPAIGN_DB` ile production dosyası seçme. Live smoke zaten kendi temporary DB'sini seçer. Başarısız API logları harness tarafından temp dışında saklanır; onları aynı evidence klasöründe yeni run adıyla muhafaza et.

Recovery gerekiyorsa toplu reset/clean/checkout/restore yapma. `game.py` ve smoke dosyalarında daha önceki kullanıcı değişiklikleri var. Yalnızca bu handoff'ta tanımlanan kendi routing/owner/test kapsamını mevcut diff ile incele; baseline HEAD'e döndürmek eski lore/tanı işlerini kaybettirir. DB recovery veya migration gerekli değildir.

## Cursor yeniden uygulamamalı

- Python shop owner ve dokuz satırlık route zaten uygulanmış durumda; ikinci creator veya paralel persistence ekleme.
- Qwen world_updates/prose'u shop/NPC/item/campaign canon kaynağına geri bağlama.
- `/item market` ile bu dükkânı oluşturma veya stock/cash provision etme.
- Mevcut UTF-8 subprocess, traceback loglama, grounded shop inquiry ve failure-log retention işlerini tekrar yazma.
- Neverwinter pack, city profile/activation, save/schema sürümleri, model budget veya no-retry kurallarını değiştirme.
- Deferred smoke failures'ı silerek, assertion'ı kaldırarak veya fixture rota/state enjekte ederek Stage 10A PASS üretme.
- Commit/push/merge/reset/clean, başka worktree'ye taşıma veya Phase 9 başlatma.

Stage 10B ancak gerçek tam Stage 10A kabulünden sonra açılabilir. Production için ayrıca owner onayı gerekir.
