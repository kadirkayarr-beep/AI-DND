# Sekiz kırmızı test: neden yuvada kırmızı, CI'da yeşildi

Dal: `task/sekiz-kirmizi-20261117` (origin/main a43fb2af üstünde). Yuva 5'te koşuldu.

Kısa sonuç: sekiz testin sebebi dört ayrı şey çıktı. Üçü gerçekten yuva ortamının farkı, ikisi gerçek hata (biri ürün kodunda, biri eski test), biri de yuvanın eski dosya kopyası. CI'da yeşil görünmelerinin iki sebebi var: CI'da yuva koruması yok, ve CI yalnız `api/tests` dosyalarını koşuyor, `ai-dnd/test_*.py` dosyalarını koşmuyor (bkz. D-327).

## Test başına

1. `test_d041_wizard_skills ... test_offline_ui_fallback_carries_the_source_list`
   - Sebep: test, depodaki `artifacts/.../character-catalog-defaults.ts` dosyasını okuyor. Yuvadaki `src/artifacts` klasörü 29 Ekim'den kalma eski kopya (Nature'sız Wizard listesi). `slot.sh` bu klasörü yuvaya göndermiyor.
   - Düzeltme: yuva aracı (yama aşağıda, `slot.sh` ve `slot_sync.sh`). Test aynen kaldı.
   - Kanıt: yamalı kopya (`slot_x.sh`) ile yuvada geçti.

2. `test_full_python_suite` x2 (`..._ci_shard_count...`, `test_ci_runs_six_shards...`)
   - Sebep: test `.github/workflows/ai-dnd-ci.yml` okuyor. Yuvadaki `src/.github` 29 Ekim'den kalma eski kopya ("shard: [...]" satırı yok), `slot.sh` göndermiyor.
   - Düzeltme: aynı yama. Test aynen kaldı.
   - Kanıt: yamalı kopya ile geçti.

3. `test_journey_real_run TheNetworkGuard` x2
   - Sebep: yuva koruması (B06) TCP soketi açmayı yasaklıyor. Biri Python'un TCP geri dönüş soket çiftini zorla kullanıyor, öteki `socket.socket()` (AF_INET) açıyor; ikisi de koruma tarafından `PermissionError` ile kesiliyor, test beklediği `AssertionError`a hiç ulaşmıyor.
   - Düzeltme (test): koruma varken (`AI_DND_GUARD_EXPECTED_SHA256` ortam değişkeni, yeni `api/tests/slot_guard.py`) birincisi atlanır, ikincisi AF_UNIX soketle koşar; "dış bağlantı yasak" iddiası aynı. CI'da ikisi eskisi gibi koşar. Onay listesi 16'ya yazıldı.
   - Kanıt: yuvada geçti/atlandı; korumasız WSL koşusunda ikisi de geçti.

4. `test_model_chain TheSpendCap.test_two_processes_on_one_file_never_lose_an_add`
   - Sebep: test alt süreç açıyor, yuva koruması alt süreci yasaklıyor.
   - Düzeltme (test): koruma varken süreç testi atlanır. Aynı kilidi (`one_writer`, tutamak başına kilit) iki iş parçacığı ve ayrı `HaikuSpend` ile sınayan yeni test eklendi, her yerde koşar. CI'da süreç testi aynen koşar. D-294 kapandı.
   - Kanıt: yeni test yuvada ve Windows'ta geçti; korumasız WSL'de süreç testi geçti.

5. `test_ai_pipeline_port ... multi_paragraph_temporary_texture...` (GERÇEK ÜRÜN HATASI)
   - Sebep: `pocket.without_false_purse` (D-142, 2e351a37) cümleleri yeniden tek boşlukla birleştiriyordu; para taşımayan her turda çok paragraflı anlatı tek bloğa dönüyordu. Windows'ta da kırmızıydı, yani yuva farkı değil. `without_the_taking` aynı kusura sahipti.
   - Düzeltme: `ai-dnd/pocket.py`: cümleler arası boşluk korunuyor, düşen cümlenin yanındaki en uzun boşluk (paragraf kesmesi) kalıyor. Yeni `test_pocket_keeps_paragraphs.py` (4 test).
   - Kanıt: asıl test kırmızı iken yeşil oldu; yeni testler geçti.

6. `test_spells_v1 ... test_cure_wounds_heals_during_combat_and_refuses_to_open_combat` (ESKİ TEST)
   - Sebep: Kadir'in D-056 kararı (f4c96d86, 2026-11-15) Cure Wounds'u savaş dışına açtı; test hâlâ "savaş dışında reddeder" diyordu. Test CI'da koşmadığı için kimse görmedi.
   - Düzeltme: testin ilk yarısı yeni sözleşmeye yazıldı (iyileştirir, yuva harcar, savaş açmaz). Onay listesi 16'da "gevşetme olabilir" diye işaretli.
   - Kanıt: yuvada ve Windows'ta geçti.

## Yuva aracı için bekleyen yama (ben yazmadım: bu dört dosya başka işte)

Dosya: `C:\Users\Kadir\Desktop\AI-DND-TOOLS\slot_yama_20261117.diff` (özet). Yamalı çalışan kopyalar: `slot_x.sh` ve `slot_sync_x.sh` (aynı klasörde, deneme için). Üç satırlık değişiklik:

- `slot.sh`, `git add` satırı: `git add -A -- ai-dnd content lib artifacts start_local.ps1` yerine `git add -A -- ai-dnd content lib artifacts .github start_local.ps1`
- `slot.sh`, `git ... archive` satırı: `... "$T" ai-dnd content tools lib start_local.ps1` yerine `... "$T" ai-dnd content tools lib .github artifacts start_local.ps1`
- `slot_sync.sh`, döngü: `for d in ai-dnd content tools lib; do` yerine `for d in ai-dnd content tools lib .github artifacts; do`

`slot_test.sh` ve `slot_par.sh` değişmiyor. Yama uygulanınca D-304 (4. madde) kapanır. Not: `slot_x.sh` ve `slot_sync_x.sh` yalnız deneme kopyası, yama uygulanınca silinebilir.

## Son koşu

`slot_x.sh 5 ... fin`: altı modül + `test_pocket_keeps_paragraphs` + komşu set (`test_journey_runner`, `test_journey_report`, `test_journey_schema`, `test_journeys`): 378 test, exit 0. Yamasız `slot.sh` ile 1 ve 2 numaralı testler (toplam 3 test) hâlâ kırmızı olur.

## Yeni defter satırları

- D-294 kapalı, D-304 kısmen kapalı (yama bekliyor).
- D-329: `ai-dnd/test_*.py` (36 dosya) CI'da koşmuyor; kalan 34 dosyanın durumu ölçülmedi.
- D-330: paragraf yutan öbür süzgeçler (doğrulanmadı, `town_knowledge.without_unbacked_money` vb.).
