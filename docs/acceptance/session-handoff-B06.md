# B06 devir kaydı — platform çalıştırıcısı (2026-10-27)

Kısa kayıttır; ürün kanıtı veya bütün oyunun başarısı değildir. Sır, jeton, kitap metni yoktur.

## Kaynak kimliği
- Dal `task/b01-source-identity-20261026`, HEAD `78b380384e70832156d2d9aa2785192bbbbdb74b`; B01-B06 işi izlenmeyen dosyalar, commit yok.

## Yapılan
- Önce `ai-dnd/api/tests/test_roadmap_b06.py` yazıldı (9 test), uygulama yokken kırmızı doğrulandı (`ModuleNotFoundError`).
- Sonra `tools/acceptance/platform_runner.py`: `run_gate(command: list[str], cwd, timeout_s, env, *, column="unit", test_id=None, platform_name=None) -> EvidenceRecord`.
  - Kabuk string'i çalıştırmaz (`TypeError`; boş liste `ValueError`); `shell=False`.
  - Windows: iş nesnesi (job object, kill-on-close). POSIX: kendi oturumu + süreç grubu (`killpg`). Timeout ve gate sonu yalnız bu ağacı kapatır; lider çıksa da torunlar temizlenir.
  - Ortam tam olarak çağıranın verdiği `env`; çıktı geçici dosyaya (UTF-8 olmayan bayt güvenli), kayıtta yalnız SHA256.
  - Durumlar: çıkış 0 → PASS; ≠0 → FAIL; timeout → FAIL (exitCode null); komut bulunamadı, desteklenmeyen platform veya lider öldürülemedi → BLOCKED. `evidence.validate_record` ile geçerli.

## Test
- Windows 11, Python 3.14.2: `python -m unittest api.tests.test_roadmap_b06 -v` (cwd `ai-dnd`) 9 test OK, 8,1 sn. Test yalnız küçük python çocuk süreçleri açar; oyun/model/sunucu yok.
- POSIX yolu bu oturumda DOĞRULANMADI: WSL (Ubuntu 24.04, Python 3.12.3) altında 9 testin 9'u `git status` hatasıyla (çıkış 128, worktree .git yolu Windows biçiminde) düştü; çalıştırıcı kodu değil kaynak kimliği okuması. POSIX kanıtı için ana (non-worktree) bir klon veya WSL'de erişilebilir bir git gerekir.

## Açık
- "Gerçek ürün çalıştırma sayısı" EvidenceRecord şemasında alan değil; kaydedilmedi (şema B02'nin; değiştirilmedi).
- Windows'ta süreç, iş nesnesine atanmadan önce torun açarsa (milisaniyelik yarış) o torun ağaçta olmayabilir.
- `ai-dnd/run_tests.py` ve `dev.ps1` bu çalıştırıcıya bağlanmadı; "33 kapıyı toptan yeniden yazma" yapılmadı.
- Bağımsız inceleme yapılmadı. Tam suite, B01-B05 yeniden koşusu, lint, UI testleri koşulmadı.

## Sonraki
- R01 (bağımlılıklar B03, B06). B06 POSIX doğrulaması ve isteğe bağlı run_tests.py adaptörü ayrı karar.

## Replit POSIX sentetik doğrulaması — 2026-10-28

- Aday SHA: `a963f0a3cc01b2ead30697aa79afa9a560db4dc8`. Komut `python -m unittest api.tests.test_roadmap_b06 -v`, `cwd=ai-dnd`; yalnız testteki küçük Python çocukları çalıştı. Dış ortam temiz bir allowlist'ten kuruldu; HOME/TMP ve `AI_DND_CAMPAIGN_DB` sentetik geçici dizine yönlendirildi, `AI_DND_DISABLE_DEFAULT_APP=1`; kullanıcı sırları ve model ayarları taşınmadı.
- Sonuç: 9 test, 10.402s, `OK`, süreç exit code 0. Kapsam: POSIX süreç grubu timeout temizliği, lider çıktıktan sonra torun temizliği, runner dışı sentetik bystander'ı yaşamda bırakma, gerçek exit/status, exact env, shell-string reddi, eksik executable ve UTF-8 dışı çıktı.
- Bu ilk koşu yalnız B06 runner sözleşmesinin sentetik POSIX doğrulamasıdır. Ürün importu/regresyonu, HTTP, model veya servis çalıştırılmadı. O sırada B03 guard entegrasyonu yoktu; sonraki bölümde eklenen fail-closed launcher bu açığı kapatır.
- İlk koşuda B06 kod değişikliği yapılmadı. B03 köken düzeltmesi dışında özgün plan/ZIP değişmedi.

## Fail-closed guarded launcher — 2026-10-28

- `tools/acceptance/guarded_runner.py` yalnız güvenli `unittest` selector'larını kabul eder; run root'u yeni/boş `/tmp` diziniyle sınırlar. Çalıştırıcı ortamı allowlist'ten kurar; HOME/TMP/DB sentetik alana yönelir, varsayılan uygulama kapalıdır, çağıranın sırları/kişisel ortamı kopyalanmaz. Git kaynak kimliği çağrıları da `PATH` ve Git yapılandırmasını filtreler.
- Mevcut `platform_runner.run_gate` süreç sahibini kullanır; yeni katman ikinci bir process manager kurmaz. Önceki çocuk pinned guard SHA/ID, sentetik yasak yol, socket ve subprocess audit engellerini ispatlar. Hedef bootstrap bunları tekrar doğrular ve ancak sonra test selector'larını import eder. Yanlış/eksik/değişmiş guard veya eksik kaynak SHA'da hedef modül başlamaz. Exit code ve timeout aynı B06 kaydından ileri taşınır; gerçek test metot sayısı fonksiyon sonucunda ayrı `testMethodsRun` alanıdır, B02 EvidenceRecord şeması değiştirilmedi.
- Guard dosya açma/listeleme, DB erişimi, mutasyon, socket, Python subprocess/fork ve native `ctypes` yükleme API'lerini audit hook ile sınırlar. Bu çekirdek düzeyinde OS sandbox değildir; doğrudan native sistem çağrısı için mutlak engel iddiası değildir. Sistem kurulumu/izin değişikliği yapılmadı.
- TDD: guarded test modülü ilk olarak `ModuleNotFoundError` ile kırmızı görüldü; ardından mevcut B06 ve yeni guarded-runner sentetik testleri birlikte geçti: `Ran 18 tests in 16.764s`, `OK`, exit code 0. Kapsam: sır sentinel'ının dışlanması, yanlış/eksik/değişen guard, hedefin başlamaması, sentetik yasak yol/mutasyon, socket/subprocess engeli, kaynak SHA yokluğu, scratch dışı ret, timeout ve exit-code aktarımı.
- Ürün/K07 testleri, HTTP, model veya servis bu koşuda çalıştırılmadı. K07 kaynak eki referans kapsamındadır; Git/yayına eklenmedi. Bağımsız architect incelemesi bu ortamda devre dışıydı; son kontrol elle yapıldı ve bu, bağımsız incelemenin yerine geçmez.

## Human Temporary HP düzeltmesi — 2026-10-28

- **Aday:** `/home/runner/workspace/.worktrees/ai-dnd-b01-source-identity-a963f0a3-20261101`; taban `HEAD`/SHA `a963f0a3cc01b2ead30697aa79afa9a560db4dc8`. Worktree kirli ve commit yok; değişikliklerin tümü bu düzeltmeye ait değildir.
- **Düzeltme kapsamı:** Human gibi tür-özellik durumu kalıcı tutulmayan karakterlerde Temporary HP kök karakter durumuna yazılır; sonraki mekanik okumada, engine save ve karakter izdüşümünde korunur. Hasar tüketimi aynı kalıcı değeri günceller. Orc’un tür durumu yolu değişmedi.
- **Mevcut dar doğrulama:** doğrulanmış guard `ai-dnd-b06-linux-guard-v1`, SHA256 `adc0c55e7051049185b3f3bcf001a2ed19ea48152e0f841fd8060992b89fea1c`; exit 0, 5 test, 0 fail/error/skip. Seçiciler: `test_external_temporary_hit_points_persist_for_non_trait_species`, `test_external_temporary_hit_points_at_zero_do_not_revive_or_change_death_saves`, `test_orc_adrenaline_rush_and_short_rest_recharge`, `test_orc_temporary_hit_points_absorb_damage_before_hit_points`, `test_zero_hp_temporary_hit_points_oracle_matches_source`.
- **Bu son koşunun kanıtı:** `/tmp/ai-dnd-human-thp-fix-final-zpsflbp1/run-evidence.json`; ham hedef çıktısı `/tmp/ai-dnd-human-thp-fix-final-zpsflbp1/child-1.raw.log`, SHA256 `4bdd78e80dc2a824c4030885bb683fb35a7b1dadb0236d4c725364c577c8c59d`. Başarısız ara koşular nihai başarı sayımına dahil değildir.
- **Önceki geniş koşu:** 58 test exit 0 idi ancak Human düzeltmesinden önce, `/tmp/ai-dnd-death-thp-k07-regressions-baqx4_9y/run-evidence.json` ve `child-1.raw.log` altında kaydedildi. Bu sonuç yeni düzeltmeyi doğrulamaz.
- **Aday worktree durum özeti (HANDOFF güncellemesinden önce):** izlenen değişiklikler: `ai-dnd/api/serializers.py`, `ai-dnd/api/tests/test_death_system.py`, `ai-dnd/api/tests/test_roadmap_b06.py`, `ai-dnd/api/tests/test_roadmap_k07.py`, `ai-dnd/game.py`, `ai-dnd/rule_oracles.py`, `content/manifest/rule-oracles.json`, `docs/acceptance/session-handoff-B03.md`, `docs/acceptance/session-handoff-B06.md`, `tools/acceptance/platform_runner.py`, `tools/acceptance/source_identity.py`. Bu liste adayın mevcut kirli diff'idir; tümünü Human düzeltmesine atfetme.
- **Aday worktree izlenmeyen dosyaları:** `ai-dnd/api/tests/fixtures/b06_guard_target.py`, `ai-dnd/api/tests/fixtures/b06_import_exit_zero.py`, `ai-dnd/api/tests/test_roadmap_b06_guarded_runner.py`, `ai-dnd/docs/evidence/suite-runs/20261028T124131Z-844997a5d8e149c284abe8792230c522/output.log`, aynı dizindeki `run.json`, `tools/acceptance/guarded_runner.py`, `tools/acceptance/linux_guard/sitecustomize.py`. Değiştirilmedi veya temizlenmedi.
- **İnceleme/açık işler:** bağımsız yeniden inceleme bekliyor; eski ZIP `.local/review-packages/death-stabilization-review.zip` SHA256 `2c02f75c5aaaec6fa61e790c5723c71916f54f5a3c6a516de37ba0b01e6cd431` Human düzeltmesinden önce hazırlandı ve güncel düzeltme için inceleme kanıtı değildir. Kalıcı yaprağın `K07.death_saves_and_stable` durumu hâlâ `OPEN`; `ACCEPTED` değildir. Save/restore round-trip için ayrı Human hedef testi henüz koşulmadı.
- **Kesin sonraki adım:** bağımsız inceleyici, taban SHA'ya göre mevcut tüm diff'i ve beş testin kanıtını incelemeli; özellikle Human Temporary HP save/restore round-trip'ini ve Orc/0 HP sınırlarını doğrulamalı. İnceleme tamamlanana kadar kabul/kapama yok. Commit, push, merge ve yayın yapılmadı; bu HANDOFF dışında kod/test/kanıt/kaynak dosyası değiştirilmedi.
