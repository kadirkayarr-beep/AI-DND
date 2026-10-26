# Oturum devri — B02 (2026-10-26)

Ürün kanıtı değildir; kısa devir kaydıdır. Özet tek başına uygulama talimatı değildir. B01 kaydı: `session-handoff-B01.md`.

- **Yetki:** "başla" VAR. Aday kökü `C:\Users\Kadir\Desktop\AI-DND-b01-isolated` (dal `task/b01-source-identity-20261026`, kaynak `78b380384e70832156d2d9aa2785192bbbbdb74b`). Yasak: commit/push/merge, main, kurulum, kişisel kayıt, sırlar, 8008, yayın.
- **Görev:** B02. Bağımlılık B01 (ACCEPTED). Kritik yol gibi ele alındı (risk belirsiz → kritik): tekil bağımsız inceleme.
- **Durum:** ACCEPTED. Bağımsız inceleme üç turda: KOŞULLU ONAY (kanıtsız REAL kabul, karışık kaynak SHA, harness'te sessiz hata kaybı, FAIL→SKIP kapanışı, şema–owner tip uyuşmazlığı) → KOŞULLU ONAY (BLOCKED kaydı yazılamıyordu; bozuk harness öğesi AttributeError) → ONAYLA. Her bulgu önce kırmızı testle sabitlendi, sonra düzeltildi.
- **Okunan bağlam:** plan 01 satır 1-40 ve 67-91; `01_Ortak_Sozlesmeler_ve_Kapilar.md` (QG-1, EvidenceRecord); tasarım §16.5, §16.7, §18.6, KAN 02/S40; `QG-1_5_Hibrit_Inceleme.md`; mevcut harness `ai-dnd/scripts/run_regression_evidence.py` ve `ai-dnd/docs/regression-evidence.md`. `integration-obligations.json` içinde B01/B02 kaydı yok.
- **Değişiklik (rollback = bu dosyaları silmek; tümü izlenmeyen, izlenen dosyada fark yok):**
  - `tools/acceptance/evidence.py` — `deduplicate_results`, `normalize_harness_run`, `record_evidence`, `validate_record`, `provenance`, `satisfies_real_acceptance`, `summarize_columns`. Mevcut harness değiştirilmedi; çıktısı normalize edilir.
  - `ai-dnd/api/tests/test_roadmap_b02.py` — 18 test.
  - `docs/acceptance/evidence.schema.json`
  - `docs/acceptance/session-handoff-B02.md` — bu kayıt.
- **Karar kuralları (bilinçli):** aynı qualified ID tek yöntem; yalnız sonraki PASS önceki FAIL/BLOCKED'ı kapatır, sonraki FAIL her zaman kazanır, diğer durumlarda en kötüsü korunur; `conflicts` ve `closed_failures` raporlanır. REAL PASS/FAIL gerçek bağımlılık adlandırmalı; bilinmeyen kanıt BLOCKED/NOT_RUN/SKIP/UNCONFIGURED olarak yazılabilir. `human_acceptance` reviewer, `model` model nesnesi olmadan "gerçek kabul" olmaz. FIXTURE/mock kayıt asla gerçek kabul sayılmaz. Tek `sourceSHA` ile özetlenir. `expected_failure`/`unexpected_success` sınıflanmamış sayılıp reddedilir.
- **Test kanıtı** (cwd `…\AI-DND-b01-isolated\ai-dnd`, Python 3.14.2, Windows; fixture=sentetik, mock yok):
  - FAIL: `python -m unittest api.tests.test_roadmap_b02 -v` önce `ModuleNotFoundError: evidence` (arayüz yokluğu). Sonraki tur testleri: 5 ve 2 hata, ürün karşı örneği.
  - PASS: B02 18 OK; `api.tests.test_roadmap_b02 api.tests.test_roadmap_b01 test_definition_preflight_checks test_definition_preflight` birlikte 63 OK.
  - Mutasyon: 11+3 owner mutasyonu testi kırdı, dosya hash'i her seferinde geri yüklendi. Bir mutasyon (boş fixtureOwner) önce hayatta kaldı → doğrudan assert eklendi.
  - Statik AST envanteri (import yok): `api/tests` 199 modül (197 + 2 yeni), 2710 yöntem kimliği, tekrar yok. Bu çalışma zamanı keşfi değildir ve 2825 ile eşit olması beklenmez.
  - Lint UNCONFIGURED. UI/Node NOT_RUN.
- **Test sayılarının sınırı:** 2882/2825/2811/11/2/1 sayıları SENTETİK bir defterden üretildi (`audit_shaped_results`); 26 Ekim audit'inin yeniden koşusu veya ham logu değildir.
- **Açık düşük sınırlar:**
  1. `[FAIL, PASS, SKIP]` → nihai SKIP, `closed_failures` boş (geçmiş yalnız `methods[id]["statuses"]` içinde).
  2. `closed_failures` yalnız raporlanır; hiçbir kapı her kapanış için gerekçe (ör. ağ-engelli koşu → HTTP koşusu) istemez.
  3. `record_evidence` varsayılan kökü `docs/acceptance/evidence-runs` .gitignore'da değil; yazım kilitsiz, tek yazar varsayımı.
  4. Gerçek bir `run.json` ile uçtan uca normalize denenmedi; yalnız harness koduna uygun sentetik şekiller.
  5. Şema doğrulayıcı olarak kullanılmıyor (bağımlılık yok); owner ile alan listesi, enum, pattern ve `additionalProperties` eşliği testle sabit.
  6. Test `sys.path.insert(0, tools/acceptance)` kalıcıdır; çıplak `import evidence` yalnız bu testte (`adventure.evidence` ile çakışma yok).
- **Geri dönüş:** RB-1; yalnız yukarıdaki dosyalar. Sentetik snapshot gerekmedi; geri dönüş provası NOT_RUN.
- **Açık yükümlülük:** P0 UNRESOLVED; P6, gerçek browser–API–kimlik–model zinciri, çalışan runtime SHA kapanmadı. Graphify grafı `78b38038`'den, yeni dosyaları içermiyor.
- **Sonraki hazır iş:** B03 (bağımlılık B02, kabul kanıtı yukarıda). Başlamadan önce B03'ün gerçek test koşusu gerektirip gerektirmediği ve izolasyonu (B06 harness'i henüz yok) ayrıca değerlendirilir.
- **Başarı iddiası sınırı:** Doğrulanan: B02 testi ve yakın regresyonlar. Yalnız planlanan: B03 ve sonrası, gerçek harness çıktısıyla uçtan uca defter, çalışan runtime kimliği.
