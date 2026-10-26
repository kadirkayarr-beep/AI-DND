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
