# Borç sıfırlama planı (Debt Zero) — 2026-11-26

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Her görev kendi dalında, kulvarının worktree'sinde ve kulvarının test yuvasında koşar. Adımlar onay kutusu (`- [ ]`) biçimindedir.

**Goal:** Borç defterindeki 285 satırın (classify.json'daki 281 + classify'ın kaçırdığı 4 açık satır: D-012, D-023, D-076, D-279) her biri kapanır (düzelten commit sha'sı ya da Kadir'in "wontfix" cevabı) ve bu iş yeni borç ya da yeni sorun açmaz.

**Architecture:** Satırlar 55 göreve dağıtıldı (53'ü satır taşır; G0.5 ve G4.4 satırsız araç/kapı görevidir). Görevler 5 dalgada koşar: Dalga 0 (sorular, kapanış kanıtı, araç), Dalga 1 (KRİTİK/YÜKSEK), Dalga 2 (ORTA), Dalga 3 (DÜŞÜK), Dalga 4 (kapıları sıkılaştırma, desloppify kalanı ve son ölçüm). Her dalgada iki kulvar paralel çalışır (A: yuva 9, B: yuva 2); aynı anda koşan iki görevin dosya listesi kesişmez. Her dalga "dalga kapısı" ile biter: ölçüm `baseline.json` ile karşılaştırılır; herhangi bir aracın toplam sayısı büyürse aynı dalgada düzeltilir.

**Tech Stack:** Python 3.13 (CI) motoru ve FastAPI (`ai-dnd/`), React/TypeScript arayüz (`artifacts/ai-dnd-experience`), pnpm, GitHub Actions; ölçüm araçları `AI-DND-TOOLS/gate-venv-20261125` içinde (ruff 0.17.5, vulture 2.14, pyright 1.1.414, radon 6.0.1, import-linter 2.17, deptry 0.25.1, bandit 1.9.4, pip-audit 2.10.1, skylos 5.8.0, knip 6.48.0, fallow 3.45.0, gitleaks 8.30.1).

**Spec (girdiler):** `C:\Users\Kadir\Desktop\AI-DND-TOOLS\gate-20261125\classify.json` (281 satırın türü, önceliği, dosyaları, kırmızı test önerisi, bağımlılığı, sahip sorusu); `docs/agents/debt-register.md` (satır metni ve kapanma kuralı); `docs/agents/kalite-taramasi-20261125.md` ve `kalite-taramasi-20261125/baseline.json` + `make_baseline.py` (`COMMANDS`: başlangıç ölçümü); `CLAUDE.md`; `docs/agents/implementer-preamble.md`; `docs/agents/hiz-kurallari.md`.

## Kadir için kısa özet (Türkçe)

- Defterde 285 açık ya da yarım kalmış borç var (sınıflandırma dosyasının 281'i + onun kaçırdığı 4 satır). Plan her birini tek bir göreve bağlar; Ek A'da satır satır liste var (285 satır, eksik yok, iki kez yazılan yok).
- **Senden bir kez cevap istiyoruz:** tek liste (Bölüm "Kadir'e soru paketi"). Yalnız senin zevkine kalan ya da "wontfix/ertele" kararı gereken sorular var; ajanların karar verebileceği 14 soru (ör. kullanılmayan paketleri silmek) soru olmaktan çıkıp Ruling oldu. Her sorunun seçenekleri ve önerimiz var. Bir kez cevaplarsın, bir daha sorulmaz.
- **Önce en tehlikeliler:** Dalga 1'de 2 KRİTİK ve 7 YÜKSEK satır var (zar atılmaması, yanlış okunan sözün kalıcı değişiklik yapması, belirsiz yere gidememe, dev işlevler, npm güvenlik açıkları).
- Her düzeltmede önce hatayı gösteren test yazılır, sonra kod değişir. Para, kayıt ve Geri Al'a dokunan her iş Opus ile ayrıca incelenir.
- **Yeni borç açılmaz:** her dalga sonunda ölçüm araçları yeniden koşulur; herhangi bir aracın toplam sayısı büyüdüyse aynı dalgada düzeltilir.
- Haftalık kullanım şu an %61. Dalga 0 ve Dalga 1'in KRİTİK/güvenlik kısmı 29 Kasım sıfırlanmasından önce sığar; G1.6-G1.8 sığmazsa sıfırlamaya kalır (tahmin, ölçülmedi). Dalga 2-4 sıfırlamadan sonra, yaklaşık iki hafta.
- Oyunu değiştiren dalgalar senin en az 10 dakikalık oynayışından önce "bitti" sayılmaz.

## Sayım kontrolü

| Tür (classify.json) | Sayı | Nereye gider |
|---|---|---|
| code_fix | 90 | düzeltme görevleri (kırmızı test + sha) |
| test_only | 45 | test görevleri (kırmızı test ya da bozma kanıtı + sha); 5 tarayıcı/ekran satırı G3.11 Kod-1 listesine |
| refactor | 40 | bölme/ölü kod görevleri (karakterizasyon testi + sha) |
| owner_decision | 26 | 8'i G0.1'de yalnız cevapla kapanır; D-221 G3.12'de D-279 ile kapanır (Kadir zaten seçti); 17'si cevaba ya da Ruling'e göre kod görevinde (G1.3, G1.5, G2.2, G2.3, G2.9, G2.24, G2.25, G2.26, G3.5, G3.6) |
| tooling_ci | 25 | araç/CI görevleri |
| blocked_on_feature | 19 | 18'i G0.1 kapanış listesi (S10, S11, S12); D-584 G1.8'de düzeltilir (engeli olan D-592 aynı görevde kalkar) |
| docs | 13 | G3.9, G2.15 (D-552), G2.22 (D-567) |
| dependency | 10 | G1.5, G2.22, G2.23 |
| external_tool | 8 | G0.3 (4), G0.4 (1), G2.19 (D-359), G3.9 (D-455), G0.1 (D-168) |
| already_fixed | 4 | G0.2 (3), G3.9 (D-469: defterde zaten "kapandı"; yalnız D-481 işaretçisi doğrulanır) |
| false_alarm | 1 | G0.2 |
| classify.json dışında kalan açık satır | 4 | D-012 → G2.4 (S-sorusu, ürün tercihi); D-023 → G0.1 erteleme listesi; D-076 → G3.8; D-279 → G3.12 (yeni görev) |
| **Toplam** | **285** | 53 görevde satır var + G0.5 ve G4.4 satırsız = 55 görev |

Kaynak: defter durum sütunu büyük/küçük harf duyarsız `açık`/`kısmen` ile başlayan 280 satır + başka biçimde açık 4 satır (D-012 "AÇIK, kabul edilen davranış", D-023 "PR bekliyor", D-076 "kökeni bilinmiyor", D-279 metin içinde "durum: açık") + defterde kapalı ama classify'da açık D-469 = 285. Öncelik: KRİTİK 2 ve YÜKSEK 7 satırın hepsi Dalga 0/1'de. ORTA satırlar Dalga 2'de; istisnalar: G0.1'de yalnız cevapla kapanan 13 ORTA satır, G1.x paketlerine katılan ORTA satırlar ve Dalga 4'teki D-588, D-598, D-599 (bütün kodun durulmasını bekler; Ruling aşağıda). Para/kayıt/Geri Al satırı 66 (D-023 dahil).

## Global Constraints (her görev bunlara bağlıdır)

- **Kapalı sayma:** bir satırın açık sayılması = durum hücresi büyük/küçük harf duyarsız `açık` ya da `kısmen` ile başlar, ya da satır elle tutulan tuhaf biçim listesindedir (D-012, D-023, D-076, D-279; yeni bulunursa eklenir). Diğer biçimler (`kapandı`, `kapalı`, `düzeltildi`, `düzeldi`, `tamamlandı`, `uygulandı`, `yapıldı`, `yanlış bulgu`, `kasıtlı / wontfix`, `PR #NN'te düzeltildi` vb.) kapalıdır.
- **Kapanma kuralı (defterin kendi kuralı):** bir satır yalnız düzelten commit sha'sı ile ya da Kadir'in "wontfix" cevabıyla kapanır. Durum sütununa `kapandı (<sha>)` ya da `wontfix (Kadir, S<no>, <tarih>)` yazılır. already_fixed ve false_alarm satırları kanıt satırı (commit sha, test adı, komut çıktısı) ve ikinci bir doğrulayıcı ajanın "çürütemedim" notuyla kapanır.
- **Yeni borç yok:** görev sırasında bulunan yeni bir hata sessizce düzeltilmez ve göz ardı edilmez. Görevin kendi dosyasında ve görevin yol açtığı bir hataysa aynı görevde düzeltilir. Önceden var olan bir hataysa deftere yeni satır olarak yazılır ve aynı dalganın bir görevine eklenir; plan bu satır da kapanmadan bitmez.
- **Davranış:** yalnız satırın istediği davranış değişir. HTTP kodları, hata gövdeleri, oyuncu metni, kayıt/commit/rollback sırası, makbuzlar, Geri Al noktaları ve kilitler başka türlü aynen kalır.
- **Önce kırmızı:** her code_fix/test_only/refactor satırı için önce kırmızı test (ya da refactor için karakterizasyon testi) yazılır ve kırmızı koşusu deftere yazılır. Karakterizasyon testi bozma denemesiyle kanıtlanır: korunan satırı değiştir, koş, kırmızıyı gör, `git restore` ile geri al.
- **Eski kayıt önemsizdir (Kadir kuralı):** eski kayıt uyumu için iş yapılmaz. Eski kayıt dalı kaldırılırken yeni kampanyanın kaydet/yükle/Geri Al turu testle korunur.
- **Boyut kilitleri yalnız küçülür:** `ai-dnd/scripts/quality_gate/size_lock.json` ve `ai-dnd/api/tests/engine_split_locks/size_budget.json`. Sınırı yeniden tanımlayan her değişiklik `docs/agents/onay-listesi.md`'ye "gevşetme olabilir" diye yazılır.
- **Testler yalnız yuvada:** `bash /c/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh <YUVA> <WORKTREE> test <etiket> 540 <modüller>` (çalışma klasörü /c/Users/Kadir/Desktop). Arayüz testleri `slot_web.sh` ile aynı yuvada. Kulvar A yalnız yuva 9, kulvar B yalnız yuva 2. Yuva 3, 4, 5 asla. İnceleyici testlerini kendi kulvarının yuvasında, implementer durduktan sonra koşar (yuva 3 yasak olduğu için çakışan inceleme yok).
- **Her hedefli koşuya girer:** komşu set `api.tests.test_journey_runner`, `test_journey_report`, `test_journey_schema`, `test_journeys`; `api.tests.test_town_seed`; motor kilitleri `test_engine_surface`, `test_engine_patch_census`, `test_engine_routing`, `test_engine_sources`, `test_engine_size_budget`, `test_engine_layout`, `test_quality_size_budget`, `test_main_route_table`; `api.tests.test_refusal_census`. `game.py` ya da `game_parts/` değişirse ayrıca `test_engine_sensitivity` (önsöz madde i).
- **İki bayrak:** her hedefli koşu `AI_DND_FRONT_PROPOSAL` kapalı ve `=1` (ilk modül `api.tests.gate_boot`) ile koşar. Beklenen: `failing_ids 0`. RESULT satırı `tests N skipped N failing_ids N PAR_EXIT=N` biçiminde deftere yazılır.
- `test_contract_parity` kendi parçasında koşar (yaklaşık 500 sn). Para testleri listesi: `docs/superpowers/plans/2026-11-23-tur-bolme-measure/money_tests.txt`; para/kayıt/Geri Al görevlerinde bu liste de koşar.
- **Sabit kasaba:** kampanya kuran her yeni test `api/tests/town_seed.py` `fixed_town` (yolculukta `campaign_seed`) kullanır.
- **Tarayıcı testi yok:** implementer ve inceleyici tarayıcı testi koşmaz (yalnız Kod-1 koşar). Arayüz görevleri `pnpm run typecheck` ve tarayıcısız node/vitest testleriyle (follow harness) doğrulanır. Ekran görüntüsü isteyen kontrol G3.11 Kod-1 listesine gider. Kırılgan tarayıcı paketine (`play-screen-ui-regression.test.mjs`, `play-viewport.test.mjs`) yeni test eklenmez.
- **Yerel geçiş CI değildir:** CI ayrıca knip, gitleaks, project_health_check/final_gate ve tam parçalı paketi koşar (`.github/workflows/ai-dnd-ci.yml`, `ai-dnd-quality.yml`). Modül seçmeden önce değişen dosya yolu ve modül adı tüm repoda aranır (tools/, content/, docs/acceptance/, api/tests, .github/); dosya metnini ya da yolunu okuyan testler içe aktarıcı olarak görünmez.
- **Modeller:** implementer Sonnet. İnceleme: para/kayıt/Geri Al satırı taşıyan görev Opus, diğerleri Sonnet. Bütün dal incelemesi Opus. Fable kullanılmaz.
- **Süreç:** her görev için `superpowers:test-driven-development` ve `superpowers:verification-before-completion` yüklenir; implementer istemine `docs/agents/implementer-preamble.md` konur ve her maddesi cevaplanır. Koda `graphify query` ile girilir (graphify-out varsa). İngilizce commit mesajı, satır grubu başına bir commit. `rm -r`, `Remove-Item`, `git clean`, `git reset --hard`, `git worktree remove` asla. Anahtar dosyaları (.env, apikeys*, *.pem) açılmaz. Force push yok, dal silinmez. Bekleme döngüsü en çok 9 dakika.
- **Worktree'ler:** denetleyici `C:/Users/Kadir/Desktop/AI-DND-borc-kontrol` (dalga dalı `borc/dalga-<N>-20261126`; birleştirme, defter güncellemesi, dalga kapısı burada); kulvar A `C:/Users/Kadir/Desktop/AI-DND-borc-A`, kulvar B `C:/Users/Kadir/Desktop/AI-DND-borc-B` (görev dalları). Üçü ayrı; aynı worktree'de tek yazıcı.
- **Tek yazıcı kuralları:** `docs/agents/debt-register.md` yalnız denetleyici tarafından kendi worktree'sinde, dalga dalında güncellenir; görev dalları deftere dokunmaz. Paylaşılan kilit/taban dosyaları (`size_lock.json`, `size_budget.json`, ruff/knip/vulture/gitleaks tabanları, fallow tabanı) yalnız küçültülür; iki görev aynı dosyayı küçültürse birleştirmede küçük değer alınır.
- **Push/PR/birleştirme:** CLAUDE.md "Sahibin kuralları" ve Kadir'in geçerli yazılı iznine göre. Oyun davranışını değiştiren dalga, Kadir en az 10 dakika oynamadan main'e birleşmez; birleşmemiş dalganın üstüne sonraki dalga yığılır (stacked).
- **Defter (ledger):** `.superpowers/sdd/borc-sifirlama/progress.md` (denetleyici), `progress-A.md` ve `progress-B.md` (kulvarlar). Rulings, RESULT satırları, bozma kanıtları, parklar, önsöz cevapları ve görev başına süre/düzeltme turu burada.

### Rulings (plan yazılırken verilen kararlar)

- Ruling: kulvar başına bir worktree, görev başına yeni dal — `git worktree remove` yasak; 53 worktree birikirdi — yanlışsa maliyeti: kulvar içinde görevler sıralı, izolasyon kaybı yok.
- Ruling: D-588, D-598, D-599 (ORTA) Dalga 4'te — kapı sıkılaştırma ve desloppify kalanı bütün kod değişikliklerinden sonra ölçülmeli, yoksa iki kez yapılır — yanlışsa maliyeti: ORTA satırlar birkaç gün geç kapanır.
- Ruling: bir paket en yüksek öncelikli satırının dalgasında koşar (ör. G1.2 içinde DÜŞÜK D-335) — aynı dosyaya iki kez dönmemek için — yanlışsa maliyeti: düşük.
- Ruling: D-169 G0.1 kapanış listesinde, bağımlısı D-094 G1.1'de — kapanış bir karar, kod değil; G1.1 D-169'u gerektirmez — yanlışsa maliyeti: Kadir "yap" derse D-169 Dalga 2'ye yeni görev olarak girer.
- Ruling (R-S52): G0.3 ve G0.4'teki repo dışı araç/canlı ölçüm satırları (D-078, D-079, D-304, D-306, D-302) commit sha'sı yerine araç dosyasının sha256 değeri ve koşu çıktısıyla kapanır — repo dışında commit olamaz, defter kuralının amacı (düzeltmenin kanıtı) böyle karşılanır — yanlışsa maliyeti: Kadir itiraz ederse araçlar repoya alınır, beş DÜŞÜK satır yeniden açılır.
- Ruling: G0.1'deki para/kayıt/Geri Al satırları (D-009, D-023, D-048, D-050, D-271, D-312, D-320) kod değişikliği olmadan yalnız Kadir cevabıyla kapanır; bu yüzden inceleme Sonnet (metin ve seçenek doğruluğu) — Opus incelemesi kod değişikliği içindir — yanlışsa maliyeti: düşük; satır "yap" cevabı alırsa kod görevine geçer ve orada Opus incelenir.
- Ruling (R-S18): D-532 eski /api/sessions takma adları kaldırılır; önce repo geneli arama (arayüz, `lib/api-*` istemcileri, testler, docs/acceptance) kullanan olmadığını gösterir; kullanan varsa o takma ad kalır ve gerekçesi satıra yazılır — ölü yol, Kadir kuralı "ölü kod sil" (2026-11-22) — yanlışsa maliyeti: istemci kırılır; codegen farkı ve CI yakalar.
- Ruling (R-S19..S17): `artifacts/api-server`, `artifacts/mockup-sandbox`, `artifacts/ai-dnd-web` silinir (D-575, D-585, D-311, D-568, D-569) — kullanılmıyorlar, güvenlik açığı ve açık Vite sunucusu taşıyorlar, git geçmişinde kalırlar; Kadir kuralı "ölü kod sil" — yanlışsa maliyeti: geçmişten geri alınır.
- Ruling (R-S33): kullanılmayan shadcn dosyaları ve bağlı paketleri aynı PR'da çıkar (D-557) — ayrı tutmak knip tabanını kirletir — yanlışsa maliyeti: düşük.
- Ruling (R-S37, R-S39): `bind_deadline` (D-512) ve iki ölü kabul işlevi ile yalnız onları sınayan testleri (D-580) silinir — Kadir "ölü kod sil" — yanlışsa maliyeti: geçmişten geri alınır; silinen testler onay listesine.
- Ruling (R-S40): `ai-dnd/docs/evidence/**` betikleri üretim bölgesinden arşiv klasörüne `git mv` ile taşınır (D-595) — yalnız dışlamak bozuk kodu bırakır — yanlışsa maliyeti: düşük.
- Ruling (R-S45): kayıt doğrulayıcısındaki ulaşılmaz `spell_mechanic_unavailable` dalı silinir (D-582) — `prepare_ready` zaten reddediyor; ölü kod — yanlışsa maliyeti: gelecekteki büyü motoru dalı yeniden yazar.
- Ruling (R-S2): D-221 Kadir'in 2026-11-15 (a) kararıyla D-279'a bağlıdır; ikisi G3.12'de birlikte kapanır — karar zaten verilmiş, yeniden sorulmaz — yanlışsa maliyeti: yok.
- Ruling (R-S30): D-583 bütün 20 motor→api kenarı kaldırılarak kapanır: önce `api.dnd_2024_rules` motora iner (14 kenar), kalan 6 kenar tek tek taşınır ya da çağrı yerinde değer geçirilir; davranış değiştirmeden kaldırılamayan kenar onay listesine "gevşetme olabilir" diye yazılır ve satır `kısmen` kalır — tam port katmanı gereksiz büyük — yanlışsa maliyeti: satır Dalga 4'e kadar kısmen kalır.
- Ruling: D-592 (109 F-rank işlev) bu planda tamamen sıfırlanamaz; G1.8 üç işlevi böler ve radon cc ratchet kapısını kurar. Satır ancak S18'de Kadir (b) derse `wontfix (kalan F işlevleri ratchet ile yalnız küçülür)` olur ve bu sınır onay listesine "gevşetme olabilir" diye girer; (a) derse ayrı bir plan gerekir ve satır o plana kadar `kısmen` kalır — kapanışı sessizce yeniden tanımlamamak için — yanlışsa maliyeti: borç sıfır hedefi bu satırda Kadir'in kararına bağlı kalır.
- Ruling: D-279 kayıp kişi kaçıranı yeni görev G3.12 olarak yapılır; eski kayıtlı görevler için göç yapılmaz (Kadir kuralı: eski kayıt önemsiz) — Kadir 2026-11-15 (a) seçti — yanlışsa maliyeti: içerik işi bir dilim sürer.
- Ruling: eski G4.2 bölündü: D-599 (72 öznel bulgu) G4.2, D-598 (mekanik kümeler, defterde D-599'a bağlı) G4.3; son kapı G4.4 — tek görev inceleme yüzeyi için çok büyük — yanlışsa maliyeti: bir ek inceleme turu.

## Review Focus (hiçbir mevcut testin kesin yakalamadığı, en olası beş arıza)

1. **Eski kayıt dalı kaldırılırken yeni kayıt da o şekli yazıyorsa** (G2.6, G2.7, G2.21 D-563): ör. tohumsuz `POST /api/sessions` dünyası. Beklenen: yeni kampanya kaydet/yükle/Geri Al turu aynı kalır. G2.6 ve G2.7'de "yeni kampanya tam tur" testi bu yüzden zorunlu.
2. **Ölü sanılan ama dinamik ulaşılan kod siliniyor** (G1.5, G2.22, G2.25, G2.26): `game.X` yama hedefleri, string `getattr`, içerik JSON'u, workflow ve betik yolları. Beklenen: silmeden önce repo geneli arama, `test_engine_patch_census` ve `test_engine_surface` yeşil, knip/fallow/vulture tabanı yalnız küçülür.
3. **Para metni okuyucuları genişletilince yanlış pozitif** (G3.1, G3.2, G3.3): meşru anlatı silinir ya da para kartsız hareket eder. Beklenen: her kalıp için olumlu ve olumsuz tablo testi; kese yalnız doğrulanmış kart ya da açık `/item buy|sell` ile değişir (önsöz madde g).
4. **Bayrak açık/kapalı ayrışması** (G1.3, G2.1, G2.2, G2.3): bir yol yalnız bir bayrakta düzelir. Beklenen: her görev iki bayrakta `failing_ids 0`; G2.1'de sahte model okuma öncesi çağrıda yüksek sesle hata verir.
5. **turn_index ve Geri Al tutarlılığı** (G1.4, G2.8, G1.8): tur bitiren yol birleştirilince bir yol iki kez artırır ya da Geri Al eski indekse dönmez. Beklenen: her tur bitiren yol tam bir kez artırır, Geri Al önceki indeks ve mesajları geri getirir (G2.8 kırmızı testi; G1.4 ve G1.8 bunu kendi koşularına ekler).

---

## Standart görev adımları (her görevde, görev bloğundaki değerlerle)

- [ ] **A1 Hazırlık:** kulvar worktree'sinde dalga dalından yeni dal `task/borc-<görev>-20261126` aç. Bağımlı soru cevapları (S no) deftere yazılı mı bak; cevap yoksa görev başlamaz, kulvar sıradaki göreve geçer.
- [ ] **A2 Dosya çakışması:** görevin Dosyalar listesini öteki kulvarda o an koşan görevin listesiyle karşılaştır; kesişirse bekle.
- [ ] **A3 Keşif:** `graphify query "<satırın konusu>"`; her satırın `debt-register.md` metnini ve classify.json `red_test` alanını oku.
- [ ] **A4 Kırmızı test:** görev bloğundaki testleri yaz. Koş: `slot.sh <yuva> <wt> test <görev>-red 540 <yeni modül> <komşu set>`. Beklenen: yeni testler FAIL, diğerleri PASS.
- [ ] **A5 Düzeltme:** görev bloğundaki yaklaşımla en az kod. Önsöz madde h (yeniden kullanım) cevabını deftere yaz.
- [ ] **A6 Yeşil (hızlı set):** aynı komut, iki bayrakta. Beklenen: `failing_ids 0`.
- [ ] **A7 Bozma kanıtı:** karakterizasyon testleri için bozma denemesi; RESULT deftere.
- [ ] **A8 Uzun set (görev sonunda bir kez):** dokunulan dosyaları okuyan bütün test modülleri (repo geneli aramayla bulunan) + para listesi (para görevi ise) + `test_contract_parity` (API değiştiyse, ayrı parça).
- [ ] **A9 Yerel kapı:** ruff ratchet, ruff check-shrink, vulture names-shrink, size_lock_shrink, vulture 80; arayüz görevinde `pnpm run typecheck` ve knip. Hepsi exit 0.
- [ ] **A10 Commit:** yalnız görevin dosyaları; İngilizce mesaj; `graphify update .` (commit etme).
- [ ] **A11 İnceleme:** görev bloğundaki model; inceleyici diff'i, kırmızı/yeşil RESULT satırlarını ve önsöz cevaplarını okur, testleri aynı yuvada yeniden koşar. Bulgu varsa düzeltme turu aynı implementer'a.
- [ ] **A12 Teslim:** dalga dalına birleştir; denetleyici defter satırlarını `kapandı (<sha>)` yapar.

---

## Dalga 0 — sorular, kapanış kanıtı, araçlar (Dalga 1 ile paralel; kod yok ya da yalnız araç)

### G0.1 Kadir'e soru paketi ve cevapla kapanan satırlar
- **Satırlar (28):** D-024, D-320, D-021, D-343, D-404, D-424, D-327, D-246, D-168, D-149, D-307 (S1-S11, satır başına bir soru) ve erteleme listesi (S12): D-312, D-315, D-029, D-022, D-025, D-026, D-009, D-169, D-271, D-042, D-048, D-050, D-058, D-358, D-066, D-014, D-023.
- **Kulvar:** denetleyici (yuva gerekmez). **İnceleme:** Sonnet (soru metni sade mi, seçenekler satırla uyumlu mu; para satırları için Ruling yukarıda).
- **Dosyalar:** yeni `docs/agents/borc-sorulari-20261126.md` (aşağıdaki "Kadir'e soru paketi" bölümü aynen).
- **Adımlar:** soru dosyasını yaz, Kadir'e tek mesajla gönder. Cevapları dosyaya ve deftere yaz. Cevap bir satırı "yap" yönüne çevirirse satır yeni bir göreve (G2.x/G3.x sonuna) eklenir, plan onu da kapatmadan bitmez. Cevap "erteleme/wontfix" ise satır `ertelendi: <özellik> (Kadir, S<no>)` olur; tetikleyici sütunu korunur, özellik gelince satır yeniden açılır. Bu biçim kapalı sayılır.
- **Kural:** her soru bir kez sorulur. Cevapsız soru yeniden sorulmaz; dalga raporunda "cevap bekleyen: S<no>" diye yalnız listelenir.

### G0.2 Kapanış kanıtı (already_fixed / false_alarm)
- **Satırlar:** D-344, D-517, D-086, D-478.
- **Kulvar:** B (yuva 2), Dalga 1'in başında. **İnceleme:** D-517 kayıt satırı olduğu için Opus doğrulayıcı; diğerleri Sonnet.
- **Kanıt:** D-344 `api.tests.test_turn_core_route` içindeki `test_the_speech_debug_trail_patch_still_reaches_the_turn` yuvada yeşil (01cc6f84). D-517 b53d4a0c + tohumsuz dalların canlı olduğu (`POST /api/sessions`) kod okuması. D-086 PR #42 geri alma + `handleStoryScroll` okuması (tarayıcı koşusu yok). D-478 `git log -S "from __future__ import annotations" -- ai-dnd/game.py` boş.
- **Kapanış:** doğrulayıcı ajan satırı çürütmeye çalışır; çürütemezse denetleyici `kapandı (kanıt: <sha/test>)` yazar.

### G0.3 Repo dışı test araçları
- **Satırlar:** D-078, D-079, D-304, D-306. **Ruling:** R-S52.
- **Kulvar:** denetleyici, yalnız yuva 9 ve yuva 2 boşken (hiçbir `slot.sh` koşusu açık değilken; bash betiği koşu sırasında satır satır okur). **İnceleme:** Sonnet.
- **Dosyalar:** `C:/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh`, `slot_web.sh`, `slot_sync.sh` (repo dışı). Önce yedek kopya `*.bak-20261126`; değişiklik `*.new` dosyasına yazılır, `bash -n` ile denetlenir, sonra `mv` ile yerine konur (yarım dosya hiç koşmaz).
- **Kırmızı kontrol:** `slot.sh x /yok test l 1 m` ve `slot.sh 9 '../kötü' ...` bugün devam ediyor (D-079) → sonra exit 2. `slot_web.sh` ile altı arayüz testi bugün `spawnSync python ENOENT` (D-078) → `PYTHON` dışa aktarılınca geçer. `slot_web.sh` kopyasında `content/names` yok (D-306) → var.
- **Düzeltme:** `[[ "$N" =~ ^[0-9]+$ ]] || exit 2` ve WT adı denetimi (Kadir 2026-11-16 onaylı); `slot_web.sh` `PYTHON` dışa aktarır ve `content/names` kopyalar; D-304 için paket koşusu bir kez çalıştırılıp çıktısı deftere.
- **Kapanış:** araç dosyalarının sha256 değeri + koşu çıktısı (R-S52).

### G0.4 Yerel modelle canlı ölçüm (harcama yok)
- **Satırlar:** D-302. Ayrıca S13-S15 "yerel ölçüm" seçilirse D-177, D-262, D-263 için ölçüm verisini üretir (bu satırlar G1.3'te kapanır). **G1.1'in ön koşuludur** (D-094 kalan dünya önkoşullu denemeler D-177 ölçümüne bağlı).
- **Kulvar:** denetleyici, yerel `gemma4-12b-dm` ile. **İnceleme:** Sonnet.
- **Adım:** `_REPLY_TOKEN_CAPS` bugün yalnız `{"gemma4-12b-dm": 300}` (yanıt); varış çağrısının tavanı ayrıca kodda okunur, varsayılmaz. 20 turda `mentions` JSON'unun kesilip kesilmediğini say; `timing` alanının doğru dolma oranını ve "evet" sonrası yeniden okumanın değişme oranını say. Sonuç `.superpowers/sdd/borc-sifirlama/olcum-g04.md`.
- **Kapanış:** kesilme 0 ise D-302 kanıtla kapanır (R-S52); kesilme varsa tavan yükseltme düzeltmesi aynı görevde kırmızı testle (`test_reply_cap_fits_mentions`: tavan, en uzun örnek `mentions` cevabını kesmez) yapılır.

### G0.5 Taban karşılaştırma aracı
- **Satırlar:** yok (dalga kapısının aracı). **Kulvar:** A (yuva 9), Dalga 1'den önce. **İnceleme:** Sonnet.
- **Dosyalar:** yeni `docs/agents/kalite-taramasi-20261125/compare_baseline.py`; test `ai-dnd/api/tests/test_compare_baseline.py` (modülü dosya yolundan `importlib` ile yükler).
- **Arayüz:** `compare(base: dict, new: dict, touched: set[str]) -> list[str]`; komut satırı `python compare_baseline.py BASE.json NEW.json --touched <dosya listesi>`; herhangi bir toplam büyürse satırları basar ve exit 1.
- **Kırmızı test:** `test_total_growth_fails`: `ruff_extra` toplamı 10'dan 11'e çıkınca hata; `test_growth_in_untouched_file_fails` (ölü kod silme ya da imza değişikliği dokunulmayan çağıranda vulture60/pyright bulgusu doğurursa yakalanır; `touched` yalnız raporda "kimin yüzünden" sütunu için); `test_deptry_growth_fails` (modül anahtarlı); `test_skylos_total_growth_fails` (yalnız toplamlar); `test_new_engine_api_edge_fails`; `test_new_vuln_id_fails` (pip/pnpm audit'te yeni kimlik); `test_shrink_passes`.
- **Kural:** her araç için toplam (sözlükte değerler toplamı, listede uzunluk, skylos'ta kategori toplamları) yeni ≤ eski; ayrıca liste araçlarında (`engine_api_edges`, `import_linter_broken_pairs`, audit kimlikleri) yeni girdi her zaman hata. Çıktı büyüyen anahtarları `touched` içinde mi diye işaretler.

---

## Dalga 1 — KRİTİK ve YÜKSEK

Kulvar A (yuva 9): G0.5 → (G0.4 bitince) G1.1 → G1.2 → G1.3 → G1.8. G0.4 ölçümü gecikirse kulvar A önce G1.2'yi alır. Kulvar B (yuva 2): G0.2 → G0.3 → G1.4 → G1.5 → G1.6 → G1.7.

### G1.1 Riskli denemede her zaman zar (KRİTİK)
- **Satırlar:** D-094, D-173. **Kulvar:** A. **İnceleme:** Opus (para). **Önce:** G0.5 ve G0.4 (D-177 ölçümü).
- **Dosyalar:** `ai-dnd/game_parts/turn_front.py`, `ai-dnd/bold_acts.py`, `ai-dnd/api/model_chain.py`; yeni test `ai-dnd/api/tests/test_d094_world_rolls.py`.
- **Kırmızı test:** `test_sneak_past_guard_rolls_stealth`: "Muhafızın yanından gizlice geçiyorum" turunda motor Stealth zarını atar ve sonucu anlatı değil motor belirler (Athletics ve Perception için aynı şekil, alt test); `test_theft_with_trailing_words_rolls`: `bold_acts.is_theft("kesesini çalmak için zar atıyorum, kimse görmesin")` ve yazım hatalı "zar atıyorm" True, olumsuz cümle ("çalmayacağım") False.
- **Düzeltme:** ön okumanın riskli deneme becerilerine dünya önkoşullu becerileri ekle, motor doğrular ve atar (PR #55 yolu); `_STEAL_TRY` kapısı cümle sonundaki ek sözü kabul eder.
- **Kapanış:** sha; oynayış listesi O1.

### G1.2 Belirsiz yere ve birinin peşine gitme (YÜKSEK)
- **Satırlar:** D-331, D-335, D-333, D-299, D-297. **Kulvar:** A. **İnceleme:** Sonnet. **Önce:** G1.1 (aynı `turn_front.py`).
- **Dosyalar:** `ai-dnd/game_parts/turn_front.py`, `ai-dnd/grounded_places.py`, `ai-dnd/exits.py`, `ai-dnd/talk_front.py`, `ai-dnd/heard_rumours.py`, `ai-dnd/game_parts/travel.py`; yeni test `ai-dnd/api/tests/test_d331_vague_places.py`.
- **Kırmızı test:** `test_listed_place_not_named_by_reading_walks_or_asks`: "Bakkala gidiyorum" yürür ya da "Hangisine gidiyorsun?" sorar, sahne anlatısı vermez; `test_npc_named_inn_is_an_option` (D-335); `test_misrouted_lines` (D-333: "4 bakırım var mı" kese sorgusuna, ikinci "tavernaya gidiyorum" yolculuğa, "teşekkür edip handan çıkıyorum" çıkışa); `test_generic_alias_only_with_one_match` (D-299); `test_heard_inn_name_routes_to_inn` (D-297: "Kara Kuzgun Hanı" duyulduktan sonra "Hana gidiyorum" handa biter, "giremiyorsun" yok).
- **Düzeltme:** yer çözümü önce görünen/duyulan yer listesine, sonra türe bakar; birden çok eşleşmede soru sorar. D-297 tek kasaba haritası içinde çözülür (ikinci yerleşim S11'e bağlı değil).
- **Kapanış:** sha; oynayış listesi O2.

### G1.3 Eylem başına zamanlama (timing) (KRİTİK)
- **Satırlar:** D-109, D-260, D-261, D-262, D-263, D-177, D-420, D-245. **Bağımlı soru:** S13, S14, S15, S16 (ölçüm G0.4'te). **Kulvar:** A. **İnceleme:** Opus (para). **Önce:** G1.2.
- **Dosyalar:** `ai-dnd/front_proposal.py`, `ai-dnd/game_parts/turn_front.py`, `ai-dnd/bold_acts.py`, `ai-dnd/api/main.py` (yalnız D-245 günlük etiketi); testler `ai-dnd/api/tests/test_d109_timing.py`, `test_front_proposal.py`.
- **Kırmızı test:** `test_mixed_timing_line_changes_only_now_actions`: "yarın ona vuracağım ama şimdi biramı içiyorum" sahte okumayla vuruş ertelenir, içki şimdi; envanter/ilişki yalnız "now" eylemle değişir (D-109, D-260); `test_later_go_to_does_not_move_or_pass_time` (D-261); `test_missing_timing_is_not_now` (D-262: alan yoksa kalıcı değişiklik yok); `test_yes_replays_stored_reading` (D-263: "evet" ilk okumayı yeniden kullanır, ikinci okuma çağrısı yok); `test_unclear_persuasion_reading_asks` (D-177, S13'e göre); `test_front_reply_called_set_once` (D-420); `test_dash_command_logged_as_command_not_empty` (D-245: etiket `skipped:empty` değil).
- **Düzeltme:** okuma şemasında `timing` eylem başına alan olur ve zorunludur; eksikse güvenli varsayılan "later/ask"; "evet" saklı okumayı oynatır.
- **Kapanış:** sha; oynayış listesi O3.

### G1.4 create_app kalan bölme ve yinelenen rotalar (YÜKSEK)
- **Satırlar:** D-531, D-532. **Ruling:** R-S18 (D-532). **Kulvar:** B. **İnceleme:** Opus (Geri Al). **Önce:** G0.3.
- **Dosyalar:** `ai-dnd/api/main.py`, `ai-dnd/api/routes_turn.py`, `routes_undo.py`, `routes_quests.py`, `routes_species.py`, `routes_level_up.py`; yeni test `ai-dnd/api/tests/test_main_route_aliases.py`; `size_lock.json`.
- **Kırmızı test:** `test_ambient_event_route_exits` (ortam olayı rotasının çıkışları, bugün testsiz); `test_journal_not_written_on_death_rollback` (ölüm geri sarmasında günlük yazılmaz; defter satırı D-531); `test_no_duplicate_method_path_pairs` (D-532: her takma ad kümesi için yöntem+yol çifti tek). Mevcut rota tablosu ve OpenAPI öncesi/sonrası birebir aynı (`route_dump.py`, `main_openapi_golden.json`).
- **Düzeltme:** kalan yazma yollarını `register_*_routes(application, *, api_main, ...)` kalıbıyla taşı (aşama 1-3 ile aynı); R-S18 ile eski takma adları sil ve TS/Python istemcilerini yeniden üret.
- **Kapanış:** sha.

### G1.5 Kullanılmayan npm paketleri ve açıklar (YÜKSEK)
- **Satırlar:** D-575, D-585, D-586, D-311, D-568, D-569. **Ruling:** R-S19..S17. **Kulvar:** B. **İnceleme:** Sonnet. **Önce:** G1.4.
- **Dosyalar:** `artifacts/api-server/`, `artifacts/mockup-sandbox/`, `artifacts/ai-dnd-web/`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`, `package.json`, `lib/api-zod/package.json`, `lib/db/package.json`, `lib/api-spec/package.json`, `artifacts/ai-dnd-experience/package.json`, `artifacts/ai-dnd-experience/vite.config.ts`.
- **Kırmızı kontrol:** `pnpm audit --prod --json` bugün 1 kritik, 2 yüksek; `pnpm audit` toplam 23. Silmeden önce repo geneli arama paketin adını hiçbir yerde göstermemeli (workflow, `start_local.ps1`, docs/acceptance dahil).
- **Düzeltme:** üç paketi `git rm` ile dosya dosya kaldır (`git rm -r` ve diğer yasak komutlar yok); zod'u `>=4.6.6`'ya yükselt; kalan dev açıkları yükselt; `artifacts/ai-dnd-experience/vite.config.ts` Vite sunucusu `127.0.0.1` ve adlı `allowedHosts` (D-311'in kalan kısmı).
- **Doğrulama:** `pnpm install --frozen-lockfile`, `pnpm run typecheck`, orval codegen farksız, `pnpm audit --prod` kritik/yüksek 0, knip ve fallow tabanı büyümez.
- **Kapanış:** sha.

### G1.6 Karakter yaratma ekranını bölme (YÜKSEK)
- **Satırlar:** D-561, D-571, D-560, D-578, D-564, D-559, D-573. **Kulvar:** B. **İnceleme:** Opus (başlangıç parası). **Önce:** G1.5.
- **Dosyalar:** `artifacts/ai-dnd-experience/src/components/character-creation-screen.tsx`, `src/components/*-starting-creation.tsx` (6 sınıf), `src/lib/*-starting-creation.ts` (6 sınıf), `src/lib/starting-purse.ts`, `tests/character-creation.test.mjs`.
- **Kırmızı test (tarayıcısız):** `startingCreationPayload.<sınıf>` tablo testi: her sınıf için başlangıç eşyası/altın/yük bölmeden önce ve sonra aynı (D-561, D-571, D-560); `defaultCatalogMatchesServer` (D-578: istemci kataloğu sunucu kataloğundan farklıysa kırmızı); sunucu sözleşme testi `test_creation_without_race_key_is_identical` (`ai-dnd/api/tests`, D-564); gizli eski test bloğu silinmeden önce iki test görünür arayüz durumundan sınıf kimliğini okur (D-559, D-573; eşit sıkılıkta, onay listesine).
- **Düzeltme:** altı kopya bileşeni ve altı lib kopyasını tek veri güdümlü bileşen ve tek tabloya indir; ekranı adım bileşenlerine böl; `race` anahtarını yükten çıkar.
- **Kapanış:** sha; Kod-1 görsel kontrol K1.

### G1.7 Oyun ekranını bölme ve kaydırma (YÜKSEK)
- **Satırlar:** D-090, D-088, D-089, D-574, D-180. **Kulvar:** B. **İnceleme:** Opus (Geri Al). **Önce:** G1.6.
- **Dosyalar:** `artifacts/ai-dnd-experience/src/pages/game-browser.tsx`, `src/pages/game/*.tsx`, `src/components/campaign-transcript.tsx`, `src/lib/action-recovery.ts`; follow harness test dosyası (tarayıcısız).
- **Kırmızı test (follow harness):** `resizeBeforeScrollKeepsReader` (D-090 1), `layoutScrollAfterReaderInputKeepsPosition` (D-090 2), `programmaticScrollDoesNotForceBottom` (D-088), `observersReattachToNewStoryNode` (D-089), `unresolved409ShowsRecovery` (D-180: Geri Al, görev, tür yeteneği, büyü hazırlama ve ortam olayı rotalarında 409 `unresolved_action` kurtarma mesajı); bölmeden önce tur gönder, Geri Al, dükkân, kayıt akışları için karakterizasyon (D-574).
- **Düzeltme:** kaydırma mantığını callback ref'li bir kancaya taşı; `GameBrowser`'ı akış bileşenlerine böl; tüm hata eşlemesi `action-recovery.ts`'den.
- **Kapanış:** sha; Kod-1 görsel kontrol K2.

### G1.8 Uzun tur işlevleri ve karmaşıklık (YÜKSEK)
- **Satırlar:** D-530, D-592, D-584. **Bağımlı soru:** S17, S18. **Kulvar:** A. **İnceleme:** Opus (Geri Al/para yolu). **Önce:** G1.3.
- **Dosyalar:** `ai-dnd/game_parts/turn.py`, `turn_front_steps.py`, `living_world_steps.py`, `intent_steps.py`, `narration_steps.py`, `narration_safety.py`, `narration.py`, `ai-dnd/model_phase.py`, `ai-dnd/game.py` (yalnız kilit), `size_lock.json`, `size_budget.json`; yeni test `ai-dnd/api/tests/test_turn_long_functions_pin.py`.
- **Kırmızı test:** sabit tohumla `_run_player_turn_internal`, `_dispatch_player_turn`, `_narration_safety_decision` için karakterizasyon (çıktı durumu, mesajlar, makbuz, Geri Al noktası), bozma kanıtıyla; `test_fallbacks_log_when_forced` (D-584: paket doğrulama ve yalnız-anlatı model çağrısı yedekleri hata fırlatınca `model_phase.log_fallback` çağrılır).
- **Düzeltme:** tur-bölme aracıyla (`cut_block`/`cut_check`, CHANGED 0) üç işlevi böl; böldükten sonra D-584'ün üç geniş `except`'i daraltılır ya da loglanır. radon cc ratchet (F/E sayısı yalnız küçülür) bu görevde `ai-dnd/scripts/quality_gate/` altına kurulur ve G4.1'de CI'a girer.
- **Kapanış:** D-530 ve D-584 sha ile. D-592 yalnız S18 cevabına göre: (b) ise `wontfix (kalan F işlevleri ratchet ile)` + onay listesinde "gevşetme olabilir"; (a) ise `kısmen (<sha>; kalan N F işlevi ayrı planda)` — sessizce "kapandı" yazılmaz.

### Dalga 1 kapısı (DK1)
Aşağıdaki "Dalga kapısı" bölümündeki adımlar. Ayrıca `pnpm audit --prod` ve `pnpm audit` (G1.5 değişti). Oynayış: O1-O3.

---

## Dalga 2 — ORTA

Kulvar A (yuva 9): G2.1 → G2.2 → G2.4 → G2.5 → G2.6 → G2.7 → G2.9 → G2.21 → G2.8 → G2.14 → G2.13 → G2.15.
Kulvar B (yuva 2): G2.3 → G2.10 → G2.11 → G2.24 → G2.12 → G2.17 → G2.18 → G2.19 → G2.20 → G2.22 → G2.23 → G2.25 → G2.26.
G2.16 (18 dosyaya dokunur) dalganın sonunda tek başına, iki kulvar boşken koşar (yuva 9).

### G2.1 Bayrak açık test düzeni
- **Satırlar:** D-410, D-415, D-421, D-423, D-428, D-411, D-390, D-389. **Kulvar:** A. **İnceleme:** Opus (para testleri).
- **Dosyalar:** `ai-dnd/api/tests/test_campaign_api.py`, `test_intent_response_consistency.py`, `test_experimental_npc_dialogue.py`, `test_f04_n08_npc_memory.py`, `test_economic_bribe.py`, `test_step0_ledger_play.py`, `test_real_death.py`, `test_step4_branches.py`, `api/tests/journeys/runner.py`; yeni yardımcı `ai-dnd/api/tests/front_reading.py`.
- **Kırmızı test:** sahte istemciler okuma öncesi çağrıda yüksek sesle hata verir, her kayıt hatası/Geri Al/makbuz tekrar testine kullanılabilir okuma ikizi (D-410); `UsableReadingTwins.asyncTearDown` `fallback:failed|invalid|no_list` görürse kırmızı (D-421); ilk turdan sonra `client.conversation_replies == []` (D-415); iş/teklif ücreti tam 12 bakır ve cüzdan değişmez (D-423); ikinci `_press` rüşvet kartını açar (D-411); gece nöbeti 21:00 sonrası `days_worked==1, paid_cp==12` (D-390); yeniden kurulan günlük iş kaydında `fires_at/status_lines/item_noun` yok (D-389).
- **Düzeltme:** `read_first/with_reading/call_kinds` tek yardımcı modüle (D-428). Testler eşit sıkılıkta yeniden yazılır; sınır değişikliği onay listesine.
- **Kapanış:** sha.

### G2.2 Bayrak açık konuşma okuması
- **Satırlar:** D-413, D-414, D-425. **Bağımlı soru:** S19. **Kulvar:** A. **İnceleme:** Sonnet. **Önce:** G2.1.
- **Dosyalar:** `ai-dnd/game_parts/turn_front.py`; testler `test_campaign_api.py`, `test_experimental_npc_dialogue.py`.
- **Kırmızı test:** `test_free_person_line_answers_purpose` (D-413: "Marek, seni bu şehre getiren şeyi anlat" cevabı amaca değinir, `conversation_focus` nedeni yazılır); `test_inn_question_gives_locked_inn_answer` (D-414: `owner_verified` odak `venue-door:<han>`); `test_room_deal_in_talk_mode_has_speech_call` (D-425: çağrı türlerinde konuşma çağrısı var; S19 (b) ise satır kod değişmeden Kadir cevabıyla kapanır).
- **Düzeltme:** düz konuşma okumasında Python'un doğrulanmış odağı yazılır; oda kartı açılırken hancı konuşur (S19 a).
- **Kapanış:** sha; oynayış O4.

### G2.3 Model çağrı tavanı ve kullanım defteri
- **Satırlar:** D-150, D-416, D-418, D-419, D-417, D-405, D-408, D-494, D-496. **Bağımlı soru:** S20. **Kulvar:** B. **İnceleme:** Opus (D-150 harcama).
- **Dosyalar:** `ai-dnd/api/model_chain.py`, `ai-dnd/api/ollama_adapter.py`, `ai-dnd/api/usage_ledger.py`, `ai-dnd/api/main.py` (yalnız health ve 503 günlüğü), `ai-dnd/dialogue_runtime.py`, `ai-dnd/game_parts/turn_front.py` (yalnız `model_calls_left` çağrıları), `api/tests/live_*_smoke.py` (4 dosya); testler `test_model_chain.py`, `test_ollama_adapter.py`, `test_front_failed_fallback.py`.
- **Kırmızı test:** sonucu bilinmeyen ya da zaman aşımına uğrayan Haiku çağrısı aylık sayaca en yüksek olası maliyetle yazılır (D-150, Kadir 2026-11-16 a); açık 4xx reddi fazla faturalanmaz (sayaç değişmez, ayrı alt test); `[front, initiative]` sonrası düz çağrı reddedilir (D-416); 3 çağrılı tur `total_model_calls=3` (D-418); "satırın kalanı" ve stok cevabı 3. çağrı istisnasını alır (D-419, S20 a); canlı betikler `turn_call_cap` içe aktarır, yerel `MAX_MODEL_CALLS_PER_TURN = 2` yok (D-417, statik test); tur içi `ConnectionError` 503 ve durum/zar değişmez (D-405); 503 tur rota günlüğüne ve kullanım satırına `refused` yazar (D-408); kilitli `_LOCAL_CALL_LOCK` ikinci çağrıyı zaman aşımıyla yedeğe düşürür (D-494); art arda iki `/api/health` defter dosyasını bir kez okur (D-496).
- **Düzeltme:** `turn_call_cap` listeyi çağrı başına sayar; kilit `acquire(timeout=...)`; health uyarısı kısa süreli önbellek.
- **Kapanış:** sha.

### G2.4 Zar ve anlatı çelişkisi
- **Satırlar:** D-226, D-241, D-242, D-251, D-012. **Bağımlı soru:** S21 (D-012). **Kulvar:** A. **İnceleme:** Sonnet. **Önce:** G2.2.
- **Dosyalar:** `ai-dnd/game_parts/turn_front.py`, `ai-dnd/game_parts/narration.py`, `ai-dnd/game.py` (yalnız çağrı), `ai-dnd/town_knowledge.py`, `ai-dnd/bold_acts.py`, `ai-dnd/api/journey_messages/`; yeni test `ai-dnd/api/tests/test_d226_roll_before_speech.py`.
- **Kırmızı test:** düz korkutma cümlesi konuşma çağrısından önce zar atar ve cevap sonucu yansıtır (D-226); başarısız zar + listede olmayan akıcı başarı anlatısı reddedilir ya da yeniden yazılır (D-241); iş şartını reddeden NPC cevabına `terms_to_add` eklenmez (D-242); yolculuk sistem satırı N çekişte art arda tekrarlanmaz (D-251); S21 (a) ise modelin gerçek ödülü kendi sözleriyle söylemesi ("25 deneyim puanı kazandın", tutar gerçek ödülle aynı) `CANONICAL_XP_CONTRADICTION` ile reddedilmez, farklı tutar hâlâ reddedilir (D-012; (b) ise satır Kadir cevabıyla kapanır).
- **Düzeltme:** zar konuşmadan önce; `_states_the_failed_check` anlam denetimi genişler; şablon satırları `bold_lines_said` gibi döner.
- **Kapanış:** sha; oynayış O5.

### G2.5 Yolculuk ve varış anlatısı
- **Satırlar:** D-301, D-338, D-309, D-296, D-498, D-303. **Bağımlı soru:** S22. **Kulvar:** A. **İnceleme:** Opus (D-303 kayıt alanı). **Önce:** G2.4.
- **Dosyalar:** `ai-dnd/game_parts/travel.py`, `resolved_narration.py`, `narration.py`, `ai-dnd/arrival_narration.py`, `ai-dnd/grounded_action.py`, `ai-dnd/heard_rumours.py`, `ai-dnd/api/lore_authority/campaign_state.py`.
- **Kırmızı test:** "X'a gidiyorum" anlatıcıya gider, "X konumuna vardın." yok (D-301, Kadir K29); art arda iki "yürümeye devam" farklı metin (D-338); Python yedeğine düşen varışın nedeni kaydet/yükle sonrası okunur (D-309); ekli hedef adı `base_name` ile temizlenir (D-296); aynı kasabada üç binadan çıkışta "Dışarı, <kent> sokaklarına çıkıyorsun." en çok bir kez (D-498, S22); başlangıç kentine dönüş kasaba portresi yazmaz (D-303: başlangıç yerleşimi `world_state`'e yazılır).
- **Kapanış:** sha; oynayış O6.

### G2.6 Eski kayıt dalları A (kayıt, savaş, büyü, diyalog)
- **Satırlar:** D-525, D-524, D-576, D-538, D-505, D-028. **Kulvar:** A. **İnceleme:** Opus. **Önce:** G2.5.
- **Dosyalar:** `ai-dnd/game_parts/savefile.py`, `combat_flow.py`, `turn_front.py` (D-028), `ai-dnd/game.py` (yalnız kaldırılan ad), `ai-dnd/api/session_manager.py`, `ai-dnd/api/routes_spells_write.py`, `ai-dnd/dialogue_runtime.py`, `scripts/engine_split/inventory.py` (ad listesi), `api/tests/test_engine_sensitivity.py`, `test_dilim4a_shield.py`.
- **Kırmızı test:** v1-v3 kayıt açık hatayla reddedilir, v4+ kayıt bayt bayt aynı döner (D-525); yeni kampanyanın savaş durumu `schema_version 3`, eski şekil reddedilir (D-524); büyü hazırlığı göç yolu olmadan çalışır (D-576); yeni şekil büyü kitabı olmayan Wizard reddedilir ya da temiz kurulur (D-538); `AI_DND_DIALOGUE_MODE=legacy` reddedilir (D-505); `no_action` reddi `turn_resources` yazmaz (D-028). Zorunlu: `test_new_campaign_full_round_trip` (yeni kampanya: tur, kaydet, yükle, Geri Al, aynı durum).
- **Düzeltme:** eski dal ve göç kodu silinir; silinen göç testleri onay listesine "eski kayıt kuralı (Kadir)" gerekçesiyle.
- **Kapanış:** sha.

### G2.7 Eski kayıt dalları B (envanter)
- **Satırlar:** D-504, D-526, D-518. **Kulvar:** A. **İnceleme:** Opus. **Önce:** G2.6.
- **Dosyalar:** `ai-dnd/equipment_economy.py`, `ai-dnd/item_transfers.py`, `ai-dnd/initiative.py`, `ai-dnd/game_parts/places.py`, `intent.py`, `narration.py`, `savefile.py`, `text_rules_b.py`, `turn_front.py` (yalnız `ground_items` okuyucuları), `ai-dnd/game.py`.
- **Kırmızı test:** yeni kampanyada "Kılıç" bırakma `legacy_sword_move`'dan geçmez, eşya kimliği ve altın korunur (D-504); bırakılan eşya yalnız yeni yer-eşyası modelinde, al/bırak/Geri Al/kaydet turunda sayılar eşit (D-526); yeni inisiyatif sonucunda `legacy_preserved` yok, eski şekilli transfer altına/eşyaya dokunmaz (D-518). Zorunlu: G2.6'daki tam tur testi bu görevin koşusuna da girer.
- **Kapanış:** sha.

### G2.8 Tur cevabı kopyaları (turn_index)
- **Satırlar:** D-581, D-502. **Kulvar:** A. **İnceleme:** Opus. **Önce:** G2.21; öteki kulvarda `api/main.py`'ye dokunan görev koşmuyor olmalı (A2).
- **Dosyalar:** `ai-dnd/game_parts/turn.py`, `turn_front.py`, `places.py`, `living_world_turn.py`, `ai-dnd/api/routes_turn.py`, `routes_undo.py`, `routes_economic.py`, `ai-dnd/api/main.py`; test `api/tests/test_turn_rollback_sites.py`.
- **Kırmızı test:** `test_every_turn_end_increments_once`: her tur bitiren yol `turn_index`'i tam bir kez artırır ve tek geçmiş girdisi ekler; Geri Al önceki indeks ve mesajları geri getirir (D-581, D-502).
- **Düzeltme:** tek yardımcı (`_reply` + `messages.extend` + artış); bilinen 10 artış yeri onu çağırır (`turn_front.py` içinde 7, `turn.py` ~852, `places.py` ~1625, `routes_economic.py` ~93; satır numaraları bayatlayabilir, implementer `turn_index` aramasıyla yeniden sayar ve sayıyı deftere yazar).
- **Kapanış:** sha.

### G2.9 Ekonomi çekirdeği
- **Satırlar:** D-317, D-403, D-501. **Bağımlı soru:** S23. **Kulvar:** A. **İnceleme:** Opus. **Önce:** G2.7.
- **Dosyalar:** `ai-dnd/equipment_economy.py`, `ai-dnd/bold_acts.py`, `ai-dnd/game.py`, `ai-dnd/api/narrative_director.py`, `ai-dnd/game_parts/turn.py`; testler `test_front_failed_fallback.py`, yeni `test_d317_shopkeeper_purse.py`, `test_equipment_apply_pin.py`.
- **Kırmızı test:** dükkânsız "Shopkeeper" NPC 5-40 bakır taşır, üstü aranınca en çok o kadar (D-317); sayısız "biraz para" teklifi yapısal kurala göre karara bağlanır, sessiz kalmaz (D-403, S23: tutar sorulur); `_apply` her işlem için altın/eşya/makbuz/Geri Al karakterizasyonu, bölmeden önce yeşil (D-501).
- **Düzeltme:** `person_purse` rol eşleşmesi dükkân kaydına bağlanır; `_apply` işlem başına işlevlere bölünür, kilit küçülür.
- **Kapanış:** sha.

### G2.10 Karakter oluşturma API'si ve küçük API güvenliği
- **Satırlar:** D-540, D-319, D-313, D-539, D-314, D-385, D-316. **Kulvar:** B. **İnceleme:** Opus (başlangıç parası). **Önce:** G2.3.
- **Dosyalar:** `ai-dnd/api/character_creation.py`, `ai-dnd/api/dnd_2024_rules.py`, `ai-dnd/api/schemas.py`, `ai-dnd/api/main.py`, `ai-dnd/api/persistence/campaign_store.py` (yalnız hata sınıfı), `ai-dnd/api/identity_suggestion.py`.
- **Kırmızı test:** sınıf/geçmiş çiftleri için sabit tohumla başlangıç altını ve eşyası bölmeden önceki değerle aynı (D-540); -1 bonus ya da izinsiz yeteneğe bonus `CharacterCreationError`, 3-20 dışı skor hata (D-319); 5000 öğeli liste 422, fazla anahtarlı sözlük 422, sınır üstü gövde 413 (D-313); ortak boş-değil doğrulayıcı '', boşluk ve None'ı aynı metinle reddeder (D-539); barındırma kipinde `/docs`, `/redoc`, `/openapi.json` 404 ve health gövdesinde model zinciri/PID yok (D-314); var olan kimlikle kampanya 409 ve özel kod (D-385); bir sahibin 40 reddi başka sahibi `storage_full` yapmaz (D-316).
- **Kapanış:** sha.

### G2.11 Katman döngüsü ve motor→api kenarları
- **Satırlar:** D-590, D-583. **Ruling:** R-S30. **Kulvar:** B. **İnceleme:** Sonnet. **Önce:** G2.10.
- **Dosyalar:** `ai-dnd/api/persistence/campaign_store.py`, `ai-dnd/api/auth.py`, `ai-dnd/api/local_play.py`, `ai-dnd/api/main.py`, yeni `ai-dnd/api/deps.py`, `ai-dnd/dnd_2024_rules.py` (taşınan), `ai-dnd/api/dnd_2024_rules.py` (ince yeniden dışa aktarma), `docs/agents/kalite-taramasi-20261125/importlinter.ini`.
- **Kırmızı test:** import-linter sözleşmeleri (`routes_*` bağımsızlığı ve "motor api'yi içe aktarmaz") bugün kırık; görev sonunda geçer ya da yok sayma listesi yalnız küçülür; `engine_api_edges` 20'den 0'a iner (R-S30; kaldırılamayan kenar onay listesine ve satır `kısmen`).
- **Düzeltme:** `api.main`'deki paylaşılan yardımcılar `api/deps.py`'ye; `dnd_2024_rules` motor katmanına iner, eski yol yama hedefi olarak kalır (`test_engine_patch_census`).
- **Kapanış:** sha.

### G2.12 Büyü satırları
- **Satırlar:** D-057, D-040, D-280. **Kulvar:** B. **İnceleme:** Opus (D-040 başlangıç paketi). **Önce:** G2.24.
- **Dosyalar:** `ai-dnd/game_parts/narration.py` (yalnız prompt bağlamı), `ai-dnd/api/model_chain.py`, `ai-dnd/spell_effects.py`, `content/` yaratım kataloğu, `ai-dnd/api/character_creation.py`, `artifacts/ai-dnd-experience/src/components/character-creation-screen.tsx` (G1.6 sonrası parçası).
- **Kırmızı test:** N. turda Light atılınca N+1. tur sahne istemi etkin `spell_effects_v1` olgusunu taşır (D-057); Wizard/Cleric 2-5 seviye başlangıç paketiyle POST geçerli karakter döner (D-040); 8 çözücüsüz büyünün Türkçe adı `spell_effects.named` ile okunur (D-280).
- **Kapanış:** sha; Kod-1 görsel kontrol K3 (yaratım ekranında seviye seçimi).

### G2.13 İz ve iş defteri
- **Satırlar:** D-336, D-337. **Kulvar:** A. **İnceleme:** Sonnet. **Önce:** G2.14.
- **Dosyalar:** `ai-dnd/quest_log.py`, `ai-dnd/world_threads.py`.
- **Kırmızı test:** sahibinin ağzından duyulan izde `who` o sahip, aynı içerik iz listesinde iki kez yok, hazır yedek satır iz yazmaz (D-336); `offered` durumundaki iş `quest_log.view` içinde ücret ve gün ile görünür (D-337).
- **Kapanış:** sha.

### G2.14 Günlük eylemler
- **Satırlar:** D-243, D-244, D-308. **Kulvar:** A. **İnceleme:** Sonnet. **Önce:** G2.8.
- **Dosyalar:** `ai-dnd/everyday_actions.py`, `ai-dnd/exploration.py`, `ai-dnd/game.py`, `ai-dnd/game_parts/turn.py`, `turn_exits.py`; test `test_lr00_everyday_actions.py`.
- **Kırmızı test:** kişi bulunamayan "Takip ediyorum" sabit "izini kaybediyorsun" satırına değil okumaya/anlatıya gider (D-243; eski iddia eşit sıkılıkta yeniden yazılır); tek görünen adlı kapıda "İçeri giriyorum" o kapıya gider (D-244); açılıştaki ulak (`promoted_npc_id: null`) sorulunca terfi eder ve cevaplar (D-308).
- **Kapanış:** sha; oynayış O7.

### G2.15 Yaşayan dünya ve saldırı uzun işlevleri
- **Satırlar:** D-516, D-549, D-552. **Kulvar:** A. **İnceleme:** Opus (D-516 kayıt). **Önce:** G2.13.
- **Dosyalar:** `ai-dnd/living_world.py`, `ai-dnd/game_parts/` (ensure_scene_state parçası), `ai-dnd/action_economy.py`, `ai-dnd/adventure/play.py`, `ai-dnd/bounded_encounter.py`, `ai-dnd/weapon_attack.py`, `size_budget.json`, `size_lock.json`, `docs/agents/kalite-taramasi-20261124.md`.
- **Kırmızı test:** sabit kasabayla `ensure_scene_state` çıktı durumu bölmeden önce/sonra aynı (D-516); `weapon_attack` hazırla/çöz isabet, ıska, kritik, ikinci el, cephane çıktıları aynı (D-549); `test_every_long_function_has_shrink_row` (D-552: `size_budget.json` her `long_functions` girdisinin belgede küçültme satırı var).
- **Kapanış:** sha.

### G2.16 Türkçe metin katlama ve içerik okuma (tek başına)
- **Satırlar:** D-515, D-520, D-548. **Kulvar:** yuva 9, iki kulvar boşken. **İnceleme:** Sonnet.
- **Dosyalar:** `ai-dnd/living_world.py`, `local_dialogue.py`, `game_parts/text_rules_b.py`, `bound_text.py`, `name_catalog.py`, `thread_catalog.py`, `town_knowledge.py`, `vouching.py`, `world_threads.py`, `api/opening_narrative.py` ve katlama kopyası olan diğer dosyalar (graphify ile listelenir, toplam 18).
- **Kırmızı test:** `test_every_fold_copy_matches_canonical`: İ, I, ı, i, ş girdileri her kopyada aynı sonuç (D-515, D-520); `test_mapping_loaded_once`: ortak yükleyici 7 çağrı yerine aynı veriyi verir, `mapping.json` süreç başına bir kez okunur (D-548).
- **Kapanış:** sha.

### G2.17 CI keşfi ve kilit korumaları
- **Satırlar:** D-329, D-341, D-342, D-340, D-218, D-500, D-553, D-467, D-346. **Kulvar:** B. **İnceleme:** Opus (D-467 kayıt koruma testleri). **Önce:** G2.12.
- **Dosyalar:** `ai-dnd/scripts/full_python_suite.py`, `ai-dnd/scripts/development_checks.json`, `.github/workflows/ai-dnd-ci.yml`, `ai-dnd-quality.yml`, `ai-dnd/test_regression.py`, `ai-dnd/test_sessions.py`, `scripts/engine_split/outside_probe.py`, `size_lock.json`, `size_lock_shrink.py`, `size_budget.json`, `ai-dnd/live_narration_smoke.py`, `live_phase_c_narrative_smoke.py`, `ai-dnd/acceptance_test.py`, `ai-dnd/api/live_smoke.py`.
- **Kırmızı test:** `modules()` kök `ai-dnd/test_*.py` 36 dosyayı da bulur (D-218, D-329); CI `python game.py` alt süreci ve iki içe aktarma sırasını taze yorumlayıcıda koşar (D-341); `test_regression.py` betik olarak koşar, 30'dan az geçişte kırmızı, `create_session(seed=11)` (D-342), `sys.modules['ollama']` yaması kalkar (D-340); büyüyen dört dosyanın `size_lock` girdisi kapıyı kırmızı yapar (D-500); yükseltilmiş `size_budget.json` değeri CI'da kırmızı (D-553); bir `game_parts` değişikliği basılan özeti değiştirir (D-346, `_engine_digest` yeniden kullanılır); D-467 için CI koşu günlüğünde 9 korumalı kayıt/taşıma testinin atlanmadan koştuğu `gh run view` çıktısıyla gösterilir.
- **Not:** kök testler ilk kez CI'da koşunca kırık çıkarsa kökeni izlenir (CLAUDE.md "Bilinen kırıklar"); düzeltilir ya da deftere yeni satır olarak bu dalgaya eklenir.
- **Kapanış:** sha.

### G2.18 inventory ve probe araçları
- **Satırlar:** D-451, D-461, D-452, D-437, D-438, D-362, D-365. **Bağımlı soru:** S24. **Kulvar:** B. **İnceleme:** Opus (D-452 oturum takibi). **Önce:** G2.17.
- **Dosyalar:** `ai-dnd/scripts/engine_split/inventory.py`, `outside_probe.py`, `ai-dnd/api/tests/engine_probe.py`, `test_engine_split_inventory.py`, `test_talk_mode_writers.py`.
- **Kırmızı test (fikstür):** başka sınıf yöntemi tarafından okunan ad listelenmez (D-451, S24 b ise; a ise Kadir cevabıyla kapanır); `"game.py"` yol dizesiyle tarayan test listelenir (D-461); yardımcıdan dönen üç oturum biçimi takip edilir (D-452); 3 adımlı zincir listelenir (D-437); üst düzey `from game import X` yardımcısı `run=True` (D-438); yeniden kurulan araç kimliği 4 eski satırları yeniden tetikler (D-362); asılı alt süreç `PROBE FAIL <adım>` verir (D-365).
- **Kapanış:** sha.

### G2.19 move/coverage/ledger/census araçları
- **Satırlar:** D-349, D-468, D-431, D-432, D-433, D-436, D-435, D-363, D-427, D-475, D-434, D-359. **Bağımlı soru:** S25. **Kulvar:** B. **İnceleme:** Sonnet. **Önce:** G2.18.
- **Dosyalar:** `ai-dnd/scripts/engine_split/routing_audit.py`, `coverage_by_function.py`, `move_check.py`, `ledger_diff.py`, `patch_census.py`, `move_block.py`, `ai-dnd/docs/engine-split/patch-census.md`, `ai-dnd/api/tests/gate_boot.py`, testler `test_engine_surface.py`, `test_engine_move_check.py`, `test_engine_probe_tools.py`, `test_engine_move_block.py`, `test_engine_gate_boot.py`.
- **Kırmızı test:** classify.json `red_test` alanlarındaki fikstürler (örnek: `game_parts/<diğer>.py:999:neden` "manual entry exempts nothing" verir, D-432; `import_module('game')` ve `builtins.__import__('game')` görülür, D-434/D-359; bozuk `--identity-allowlist` satırı exit 2 REFUSED, D-475; rapor sayıları taze taramaya eşit, D-427). D-349 için S25 (a) önerisi kabul edilirse kalan kör noktalar belgeye yazılır ve satır Kadir cevabıyla kapanır.
- **Kapanış:** sha.

### G2.20 Kasaba tohumu ve yolculuk testleri
- **Satırlar:** D-383, D-386, D-393, D-384, D-554, D-085, D-480, D-292. **Kulvar:** B. **İnceleme:** Sonnet. **Önce:** G2.19.
- **Dosyalar:** `ai-dnd/api/tests/test_journeys.py`, `journey_runner.py`, `journeys/runner.py`, `town_seed.py`, `test_journey_runner.py`, `test_local_person_replay_review.py`, `test_three_plays.py`, `ai-dnd/game_parts/places.py` (yalnız D-085 kökeni ürün kodundaysa), yeni `ai-dnd/api/tests/test_no_real_ollama.py`.
- **Kırmızı test:** 36_messenger_chain tohum 10, kasaba 11, okuma kapalı: adım 3 `iz_sayisi` 0 (D-383); tekrar tohumu kardeş senaryonun tohumuyla çakışmaz (D-384); tohumsuz `create_session()` çağıran testler taranır, ortak yardımcı zarı sabitler, her biri onay listesine (D-393); `fixed_town` özel runner işlevi olmadan çalışır (D-554); iki kişili sahnede doğru kişi seçilir (D-085); `FightBackTests` zarı sabit (D-480); gerçek Ollama çağrısı testte hata verir (D-292). D-386: 12 rc zincir senaryosu yerel `gemma4-12b-dm` ile yeni tohumlarda koşulur, sonuç deftere (harcama yok).
- **Kapanış:** sha.

### G2.21 Arayüz küçükleri
- **Satırlar:** D-153, D-235, D-563, D-282. **Kulvar:** A. **İnceleme:** Opus (D-563 seviye atlama). **Önce:** G2.9 (aynı `equipment_economy.py`).
- **Dosyalar:** `artifacts/ai-dnd-experience/src/components/character-creation-screen.tsx` (G1.6 sonrası parçaları), `character-panel.tsx`, `level-up-controls.tsx`, `skill-check-result.tsx`, `ai-dnd/equipment_economy.py` (yalnız el yuvası çıktısı).
- **Kırmızı test (tarayıcısız):** her seçim kutusu ve +/- düğmesinin boş olmayan erişilebilir adı var (D-153); karakter paneli ana el ve ikinci eli gösterir, başlangıç kalkanı takılı (D-235); `class_name == null` önizlemesi Sorcerer denetimi çizmez, eski dal silinir (D-563); zorluk kartı "Zor, DC 18" (D-282, Kadir 2026-11-16).
- **Kapanış:** sha; Kod-1 görsel kontrol K4.

### G2.22 shadcn/toast temizliği
- **Satırlar:** D-557, D-570, D-558, D-572, D-567, D-566, D-579. **Ruling:** R-S33. **Kulvar:** B. **İnceleme:** Opus (D-566 dükkân). **Önce:** G2.20.
- **Dosyalar:** `artifacts/ai-dnd-experience/src/components/ui/` (kullanılmayan dosyalar), `ui/toast.tsx`, `toaster.tsx`, `sonner.tsx`, `src/components/kitap/`, `shop-panel.tsx`, `artifacts/ai-dnd-experience/package.json`, `pnpm-lock.yaml`, fallow/knip tabanları.
- **Kırmızı kontrol:** önce iddia doğrulanır: `useToast`/`Toaster` `app-shell.tsx` ve `kitap/kontroller.tsx`'te hâlâ kullanılıyor mu (D-558). Silme sonrası fallow ve knip tabanı küçülür; derleme ve vitest geçer (D-557, D-570); kitap galerisi `import.meta.env.DEV` koruması altında (D-567); `shop-panel` testleri bileşen üzerinden içe aktarır, test-only export kalkar (D-566); D-579 G1.5 ve bu görevle birlikte çözülür (üç kopyadan biri kalır).
- **Kapanış:** sha.

### G2.23 Python bağımlılık bildirimi
- **Satırlar:** D-587, D-593. **Kulvar:** B. **İnceleme:** Sonnet. **Önce:** G2.22.
- **Dosyalar:** `uv.lock`, `pyproject.toml`, `.github/workflows/ai-dnd-ci.yml`, `ai-dnd/api/tests/test_roadmap_b04.py`.
- **Kırmızı kontrol:** `pip-audit` uv.lock'ta certifi PYSEC-2026-4320 buluyor → yok (certifi >= 2026.10.18); `deptry` pypdf, pydantic, starlette için DEP002/DEP003 → yok (pypdf geliştirme/test bağımlılığı olarak bildirilir).
- **Kapanış:** sha.

### G2.24 campaign_store
- **Satırlar:** D-495, D-536, D-305. **Bağımlı soru:** S26. **Kulvar:** B. **İnceleme:** Opus. **Önce:** G2.11 (aynı dosya).
- **Dosyalar:** `ai-dnd/api/persistence/campaign_store.py`, `ai-dnd/api/tests/test_persistence_idempotency.py`, `compact_receipts` testleri.
- **Kırmızı test:** 10 000 satırlık geçmiş sayfalı okunur ve eski `fetchall` ile aynı veri (D-495); S26 (b) ise `compact_receipts` ve yalnız onu çağıran test kullanımları silinir, Geri Al derinliği testi yeşil kalır (D-536, onay listesine); eşzamanlı iki farklı eylem `threading.Barrier` ile aynı anda başlar ve zaman kaybı olmadan sıralanır (D-305).
- **Kapanış:** sha.

### G2.25 game.py başlığı ve ölü kod tablosu
- **Satırlar:** D-445, D-490, D-492, D-555, D-507, D-523. **Bağımlı soru:** S27, S28. **Kulvar:** B. **İnceleme:** Sonnet. **Önce:** G2.23.
- **Dosyalar:** `ai-dnd/game.py`, `ai-dnd/game_parts/__init__.py`, `text_rules_a.py`, `lore.py`, `places.py`, `turn_front.py` (yalnız içe aktarma), `docs/engine-split/olu-kod-kaniti.md`, `ai-dnd/scripts/quality_gate/vulture_whitelist.py`, ilgili testler.
- **Kırmızı test:** `test_game_header_f401_gate`: izin listesi dışındaki kullanılmayan içe aktarma kırmızı (D-445; 643 yeniden dışa aktarma S4 b ile izinli); `SECURITY LLM01/LLM07` yorumu `_untrusted_player_block`'un hemen üstünde, `ast.dump` aynı (D-492). Silmeler: S34 tablosundaki satırlar, vulture beyaz liste B'deki 7 girdi (D-555), yalnız testlerin çağırdığı 7 + 4 işlev ve testleri (D-507, D-523). Her silme sonrası motor kilitleri ve komşu set yeşil.
- **Kapanış:** sha.

### G2.26 Diğer ölü kod
- **Satırlar:** D-512, D-544, D-509, D-513, D-514, D-580, D-594, D-601, D-595. **Bağımlı soru:** S29 (D-544); Ruling R-S37, R-S39, R-S40. **Kulvar:** B. **İnceleme:** Sonnet. **Önce:** G2.25.
- **Dosyalar:** `ai-dnd/incidents/categories.py`, `incidents/gate.py`, `ai-dnd/intent_contract.py`, `ai-dnd/local_exploration.py`, `ai-dnd/api/lore_authority/freeze_admission.py`, `api/lore_authority/__init__.py`, `ai-dnd/interaction_adventure.py`, `ai-dnd/spells/legality.py`, `ai-dnd/adventure/dialogue_jobs.py`, `ai-dnd/docs/evidence/` (R-S40: arşiv klasörüne `git mv`), `docs/agents/kalite-taramasi-20261125/pyrightconfig.json`, ilgili testler.
- **Kırmızı kontrol:** her aday için repo geneli arama ve dinamik çağrı denetimi; silinemeyen aday beyaz listeye gerekçeyle (D-594, D-601). D-544 S29 (a) ise `threat_band 'none'` ile savaş bağı reddi testi, (b) ise işlev ve testi silinir. Silinen test onay listesine.
- **Kapanış:** sha; vulture 60 ve skylos sayıları düşer.

### Dalga 2 kapısı (DK2)
"Dalga kapısı" adımları; ayrıca `pip-audit` (G2.23) ve `pnpm audit` (G2.22), skylos (G2.26). Oynayış: O4-O7.

---

## Dalga 3 — DÜŞÜK

Kulvar A (yuva 9): G3.1 → G3.2 → G3.3 → G3.4 → G3.5 → G3.6 → G3.7. Kulvar B (yuva 2): G3.8 → G3.9 → G3.10 → G3.12. G3.11 Kod-1'de, kulvarlardan bağımsız.

### G3.1 Kese cümlesi okuması
- **Satırlar:** D-285, D-286, D-287, D-288, D-289, D-291. **Bağımlı soru:** S30, S31. **Kulvar:** A. **İnceleme:** Opus.
- **Dosyalar:** `ai-dnd/pocket.py`, `ai-dnd/front_proposal.py`; test `ai-dnd/api/tests/test_pocket_coin_lines.py`.
- **Kırmızı test (tablo, olumlu ve olumsuz):** "Kesene 5 bakır bırakıyor." para hareketsiz turda silinir (D-285); "Kesene beş gümüş ekli." silinir, "ekli" metal sıfatı değil (D-288); "Kesenin altından on bakır çıkıyor", "Yirmi altın senin", "bir buçuk bakır", "0 bakır" (D-289); ilk sözcük olmayan veriş ve "birkaç gold" (D-291); S30 (a) ise İngilizce olumsuz kese cümlesi (D-286), (b) ise satır `ertelendi: İngilizce dil desteği`; S31 (a) ise kazanılan zarda anlatı ödenen 5'e göre yeniden yazılır (D-287). Her durumda: kese yalnız kartla değişir.
- **Kapanış:** sha.

### G3.2 Ekonomi satırları
- **Satırlar:** D-334, D-253, D-275, D-278, D-265, D-412, D-318. **Bağımlı soru:** S32. **Kulvar:** A. **İnceleme:** Opus. **Önce:** G3.1.
- **Dosyalar:** `ai-dnd/economic_actions.py`, `ai-dnd/equipment_economy.py`, `ai-dnd/game_parts/coin.py`, `ai-dnd/bold_acts.py`, `ai-dnd/local_dialogue.py`, `ai-dnd/game_parts/turn_front.py`, içerik kataloğu (S32 a: "20 Ok" fiyatı); testler `test_economic_bribe.py`, yeni `test_d334_room_price.py`.
- **Kırmızı test:** oda fiyatı tek cümlede bir kez; açık 4 bakır teklife "barmene 4 bakır veriyorum" satın almayı tamamlar, tek harcama, tek makbuz (D-334); "Kısa Yay & 20 Ok" parça toplamıyla fiyatlanır (D-253); NPC kaldırılınca kesesi de taşınır/düşer, `validate_world` temiz (D-275); `|` içeren yer kimliği `rpartition` ile bölünür, olumsuz anlatılar ("mızrak çalınmış") eşya göstermez (D-278); aynı turdaki para isteği kendi Persuasion zarını atar, kart sonucu parayla tutar (D-265); 500 bakırlı kesede bahşiş cevabı "altın yok" demez (D-412); 4000 karakterlik düşmanca girdi zaman sınırında biter (D-318: `_NOT_NOW` sınırlı).
- **Kapanış:** sha.

### G3.3 İz teslim okuması
- **Satırlar:** D-277, D-284, D-293, D-596. **Kulvar:** A. **İnceleme:** Opus. **Önce:** G3.2.
- **Dosyalar:** `ai-dnd/world_threads.py`, `ai-dnd/game_parts/turn_front.py`; test `ai-dnd/api/tests/test_world_threads.py`.
- **Kırmızı test:** "paket servis yok mu, neyse bahşiş veriyorum" teslim saymaz, gerçek teslim ("bahşişin") sayar (D-277); "takımı götürmedim", "sunmuyorum", "hayır", "henüz değil", "teslim ediyorum, para istemiyorum" tablosu (D-284); "Şimdi değil, kabul ederim" ret (D-293, Kadir 2026-11-16); `days_worked`/`accepted_turn` None olan kayıtta iş günü TypeError vermez (D-596).
- **Kapanış:** sha.

### G3.4 Söylenti kaydı
- **Satırlar:** D-295, D-298, D-321, D-322, D-323. **Kulvar:** A. **İnceleme:** Opus (D-323 Geri Al). **Önce:** G3.3.
- **Dosyalar:** `ai-dnd/heard_rumours.py`; test `ai-dnd/api/tests/test_heard_rumours_turn.py`.
- **Kırmızı test:** aynı adlı iz ve yer ikisi de saklanır (tür + ad) (D-295); `base_name` "'lerinde", "'ndakiler" eklerini keser, "Ba'al" kalır (D-298); tekrar söylemedeki iddia yer kaydına da yazılır (D-321); tekrar söyleme `turn`'ü yeniler, sınırda eski yer atılmaz (D-322); iddiasız kayıt + iddialı tekrar + Geri Al → çıplak ad (D-323).
- **Kapanış:** sha.

### G3.5 grounded_action ve metin süzgeçleri
- **Satırlar:** D-381, D-382, D-392, D-222, D-508, D-330. **Bağımlı soru:** S33. **Kulvar:** A. **İnceleme:** Sonnet. **Önce:** G3.4.
- **Dosyalar:** `ai-dnd/grounded_action.py`, `ai-dnd/game.py`, `ai-dnd/town_knowledge.py`; testler `test_front_failed_fallback.py`, yeni `test_d381_rob_outside.py`.
- **Kırmızı test:** tohum 12/27/32 kasabasında okuma kapalı "şehrin dışına gidiyorum ve X'i soyuyorum" oyuncuyu kasabadaki X'e yürütmez, "X kasabada mı?" sorar (D-381, S33); "Zivanel'i soyuyorum." tek başına adım üretir (D-382); `PLACE_KINDS` dış mekân bayrağı bozulunca son iddia tek başına kırmızı (D-392); "birine" yer/kişi adıyla eşleşmez, geçerse satır yanlış alarm olarak kanıtla kapanır (D-222); geniş `except` yerleri loglar ya da daralır, beklenmeyen hata yutulmaz (D-508); çok paragraflı metin süzgeçten paragraf boşluğuyla çıkar (D-330).
- **Kapanış:** sha.

### G3.6 Küçük motor satırları
- **Satırlar:** D-582, D-290, D-165, D-406, D-407, D-409, D-310. **Bağımlı soru:** S34 (D-310); Ruling R-S45 (D-582). **Kulvar:** A. **İnceleme:** Sonnet. **Önce:** G3.5.
- **Dosyalar:** `ai-dnd/action_economy.py`, `ai-dnd/refusals.py`, `ai-dnd/adventure/director.py`, `ai-dnd/followup.py`, `ai-dnd/incidents/bridge.py`, `ai-dnd/game_parts/turn_front.py`, `ai-dnd/api/main.py` (yalnız kaynak etiketi), yerel oyun başlatıcısı (`start_local.ps1`, D-310); testler `test_action_economy.py`, `test_front_failed_fallback.py`, `test_d109_timing.py`, `test_model_failure_never_locks.py`, `test_talk_front.py`.
- **Kırmızı test:** `magic` türünde Ready + `spell_metadata` kaydı yüklemede reddedilir, sonra ulaşılmaz dal silinir (D-582, R-S45); hedef ölünce takip görevi açılır, düşmüş ikinci NPC yerine sıradaki seçilir (D-290); kaynaksız tur `campaign_history_sources`'a None değil tanımlı etiket yazar (D-165); açık teklifte okuma RuntimeError → `fallback:failed:offer_answer` ve teklif kabul (D-406); okuma şemasında sınırsız kanıt dizisi yok, bozma kanıtıyla (D-407); "provider gone" testleri `ConnectionError` ile 503 bekler (D-409); başlatıcı `-LocalPlay` ile `AI_DND_SPEECH_DEBUG=1` kurar (D-310, S34 a; kapanış bir sonraki oynayışta `speech-debug.jsonl` okunmasıyla, O8).
- **Kapanış:** sha.

### G3.7 TypedDict artıkları
- **Satırlar:** D-597. **Kulvar:** A. **İnceleme:** Sonnet. **Önce:** G3.6 (aynı `world_threads.py`, `front_proposal.py`).
- **Dosyalar:** `ai-dnd/world_happenings.py`, `world_threads.py`, `front_proposal.py`, `town_knowledge.py`, `ThreadKeysUsedByCallers` testi.
- **Kırmızı test:** `ThreadKeysUsedByCallers` düzenli ifadesi iş kaydı tutan bütün değişken adlarını kapsar; TypedDict'te olmayan anahtar okunursa kırmızı; `_make_room(state: Mapping)` iç içe `links` listesine yazmıyor (tip daraltılır).
- **Kapanış:** sha.

### G3.8 Motor testi sertleştirme
- **Satırlar:** D-453, D-454, D-462, D-463, D-476, D-477, D-380, D-356, D-388, D-391, D-076. **Kulvar:** B. **İnceleme:** Sonnet.
- **Dosyalar:** `ai-dnd/api/tests/test_engine_patch_census.py`, `test_engine_module_alias.py`, `patch_census.json`, `test_engine_surface.py`, `test_engine_parts_pilot.py`, `test_engine_schemas_part.py`, `test_front_proposal.py`, `test_front_carries_more.py`, yeni `test_no_tests_dir_on_sys_path.py`.
- **Kırmızı test:** izin listesinde olmayan hesaplanmış yama adı sayımı kırmızı yapar (D-453); uygun olmayan kapanış `_assert_part_ob...` kırmızı (D-454); D-462 (a)-(e), D-476 ve D-477 maddelerinin her biri bozma kanıtıyla; `SchemasPart` `assertIs` (D-380 madde 2; 5-8 ölçüm notu, kanıtla kapanır); `api/tests`'i `sys.path`'e koyan modül AST taramasında kırmızı (D-356); `test_front_carries_more` kurulumu mixin'e taşınır, 243 yinelenen koşu düşer (D-388); `holders` karakter adını içerir, `['text']`'ten önce `assertIsNotNone` (D-391); D-076: `test_roadmap_c06_dex_asi` modülü yuvada 10 kez koşulur, süreler deftere; tek test 60 sn'yi geçmezse satır "yeniden üretilemedi" kanıtı + doğrulayıcı ile kapanır (flake kuralı: bisect yok, tohum zaten sabit), geçerse kök neden aranır ve düzeltilir.
- **Kapanış:** sha.

### G3.9 Belgeler ve süreç kuralları
- **Satırlar:** D-357, D-442, D-457, D-460, D-482, D-493, D-479, D-481, D-491, D-439, D-441, D-455, D-469. **Kulvar:** B. **İnceleme:** Sonnet. **Önce:** G3.8.
- **Dosyalar:** `docs/design/borc-defteri.md`, `docs/agents/hiz-kurallari.md`, `docs/agents/implementer-preamble.md`, `docs/agents/common.md`, `docs/agents/onay-listesi-20261115.md`, `docs/engine-split/olu-kod-kaniti.md`, `docs/design/INDEX.md`, `ai-dnd/docs/engine-split/claims.md`, `ai-dnd/scripts/engine_split/blank_runs.py`, `ai-dnd/api/tests/test_engine_layout.py`, `test_engine_surface.py` (bir yorum satırı), `.superpowers/sdd/tur-bolme/progress.md` (repo içindeyse).
- **Kırmızı test (yalnız kod maddeleri):** `blank_runs.verify('x = 1\n','x = 1')` bulgu döner (D-493 d); def içinde silinen boş satır bulgusu tam metinle (D-493 e). Diğerleri metin: 8 dikey çizgi düzeltmesi (D-357), "sekiz yeni parça" (D-442), claims.md "Plan 2 anlık görüntüsü" notu (D-439), progress.md'ye RED/GREEN işaretçileri (D-441), D-481 koşu kuralları bir kez `common.md`'ye; D-455 D-481'e bağlanıp kanıtla kapanır; D-469 defterde zaten `kapandı (açık kalanlar D-481'de)`, yalnız işaretçinin doğru olduğu doğrulanır, durum değişmez; biten planlara ait D-457, D-460, D-479, D-482, D-491 "plan bitti, kural `common.md`'de" kanıtıyla kapanır.
- **Kapanış:** sha.

### G3.10 Eski arayüz kodu
- **Satırlar:** D-164. **Kulvar:** B. **İnceleme:** Sonnet. **Önce:** G3.9.
- **Dosyalar:** `artifacts/ai-dnd-experience/src/` (ham `<select>` ve eski CSS sınıfları), yeni tarayıcısız node testi `tests/no-legacy-ui.test.mjs`.
- **Kırmızı test:** `noRawSelectOrLegacyClass`: `src` içinde ham `<select>` ya da eski sınıf adı kalmaz (bugünkü sayı önce ölçülür, 59 doğrulanmadı).
- **Kapanış:** sha; Kod-1 görsel kontrol K5.

### G3.11 Kod-1 ve Kadir listesi (tarayıcı ve ekran görüntüsü)
- **Satırlar:** D-083, D-087, D-091, D-273, D-236. **Sahip:** Kod-1 (tarayıcı testleri yalnız onda). **İnceleme:** Sonnet (kanıtı okur).
- **İş:** D-083 giriş resmi `img.complete/decode` beklenir; D-273 ve D-091 yerleşim/kaydırma durulmasını bekleyen tek çağrı; D-087 son N (öneri 10) yeşil main CI koşusu kanıtıyla kapanır; D-236 dar ve geniş genişlikte üç kurtarma düğmesinin üst üste binmediği ekran görüntüsü. Kırılgan pakete yeni test eklenmez; yalnız var olan bekleme düzeltilir.
- **Kapanış:** sha (D-083, D-091, D-273) ya da kanıt (D-087 CI koşu kimlikleri, D-236 ekran görüntüsü yolu) + Kod-1 notu.

### G3.12 Kayıp Kişi: kaçıran ayrı düşman
- **Satırlar:** D-279, D-221. **Ruling:** R-S2. **Kulvar:** B. **İnceleme:** Sonnet. **Önce:** G3.10.
- **Dosyalar:** `ai-dnd/adventure/templates.py` (`_missing_person` bağları: `captor_npc_ids`), `ai-dnd/adventure/evidence.py`, `ai-dnd/adventure/dungeon.py`, `ai-dnd/adventure/projection.py`; yeni test `ai-dnd/api/tests/test_d279_captor.py` (sabit kasaba).
- **Kırmızı test:** `test_defeating_captor_closes_threat_step`: kaçıran yenilince "Tehdidi dağıt" adımı kapanır; `test_defeating_rescuee_does_not_close`; `test_captor_placed_in_dungeon`; etiket "Karşılaş"; ikna/sindirme yolu D-183 istisnasıyla çalışmaya devam eder (uçtan uca `apply_evidence` testi).
- **Düzeltme:** kaçıran şablona ayrı NPC olarak eklenir, `resolution_kinds`'a combat geri döner; eski kayıtlı görev göçü yok (Kadir kuralı).
- **Kapanış:** sha (iki satır birlikte); oynayış O10.

### Dalga 3 kapısı (DK3)
"Dalga kapısı" adımları. Oynayış: O8, O9 (para satırları G3.1-G3.3) ve O10.

---

## Dalga 4 — kapıları sıkılaştırma, desloppify kalanı, son ölçüm

Sıralı, yuva 9: G4.1 → G4.2 → G4.3 → G4.4.

### G4.1 Kalite kapısı sıkılaştırma
- **Satırlar:** D-588, D-589, D-591, D-556, D-600. **Bağımlı soru:** S35, S36, S37. **İnceleme:** Opus (D-588 para yolu).
- **Dosyalar:** `ai-dnd/equipment_economy.py`, `economic_actions.py`, `game.py`, `api/main.py`, `api/routes_level_up.py`, `game_parts/turn.py`, `turn_front.py`, `combat_flow.py`, `resolved_narration.py` (yalnız "possibly unbound" yerleri), `ai-dnd/bound_text.py`, `npc_speech_boundary.py`, `pyproject.toml`, `ai-dnd/scripts/quality_gate/` (ratchet, tabanlar), `.github/workflows/ai-dnd-quality.yml`, `docs/agents/kalite-taramasi-20261125.md`.
- **Kırmızı test:** "possibly unbound" her yer için değişkeni atanmamış bırakan dalı süren test UnboundLocalError vermez (D-588; pyright yanılıyorsa yerleşim değişir); döngüdeki kapanış döngüden sonra çağrılınca kendi değerini görür (D-591 B023); pyright ratchet tabanı 1804'ten büyüyemez, yeni Optional hatası kapıyı kırmızı yapar (D-589, S35 a); ruff tabanı yalnız gerçek borcu tutar, bilinçli yeniden dışa aktarmalar `__all__` ya da gerekçeli `noqa` (D-556); S37'te seçilen her araç ratchet adımı olarak eklenir ve tohumlanmış yeni bulguyla kırmızı olduğu gösterilir (D-600).
- **Kapanış:** sha; CI süresi önce/sonra deftere.

### G4.2 desloppify öznel bulgular (72 bulgu)
- **Satırlar:** D-599. **Bağımlı soru:** S39. **İnceleme:** Opus (session_manager, main).
- **Dosyalar:** bulgu başına (`game.py`, `game_parts/`, `api/main.py`, `api/session_manager.py`, `api/auth.py`, `api/emergence`, `character_progression.py`, `class_progression.py`).
- **İş bölümü:** 72 bulgu 20 boyuta göre en çok 4 alt partiye bölünür; her parti ayrı commit ve ayrı inceleme turu.
- **Kırmızı test:** alt bulgu başına (ör. `SessionManager.get` durum değiştirmez); docs/openapi rotası G2.10 D-314 ile kapandıysa kanıt; S39 (2) "hayır" ise `ValueError` → `GameError` göçü alt bulgusu Kadir cevabıyla kapanır.
- **Kapanış:** sha.

### G4.3 desloppify mekanik kümeler
- **Satırlar:** D-598. **Bağımlı soru:** S38. **İnceleme:** Opus (para koruyan assert'ler). **Önce:** G4.2 (defterde D-598, D-599'a bağlı).
- **Dosyalar:** küme başına belirlenir (`ai-dnd` üretim bölgesi; `api/` içindeki `assert`'ler).
- **Kırmızı test:** küme başına desloppify sayısı düşer; para veya girdi koruyan `assert`'ler (bandit B101) açık `raise` olur, her biri için test. S38 (a) ile "gerekçeli yanlış alarm" kümeleri (ör. 988 bölümler arası özel içe aktarma) satır notuna gerekçesiyle yazılır.
- **Kapanış:** sha.

### G4.4 Son kapı (satır yok)
- [ ] `make_baseline.py` `COMMANDS` içindeki 17 komutun hepsini `AI-DND-TOOLS/gate-<tarih>-son/raw` içine koş (skylos gerçek `rg` ile, pip-audit iki dosya, pnpm audit iki koşu).
- [ ] `python docs/agents/kalite-taramasi-20261125/make_baseline.py <raw> <...>/baseline-son.json`.
- [ ] `compare_baseline.py baseline.json baseline-son.json --touched <bütün dosyalar>` → exit 0 (her araç toplamı ≤ başlangıç). Yeni yayımlanmış açık (2026-11-25 sonrası) varsa aynı görevde yükseltilir.
- [ ] Tam CI: `gh run list --repo kadirkayarr-beep/AI-DND` 'AI-DND bounded verification' ve 'AI-DND quality gate' yeşil.
- [ ] desloppify taraması: objective ≥ 74.9, açık kümeler başlangıçtan büyük değil.
- [ ] Bütün dal incelemesi: Opus, `superpowers:requesting-code-review`, dalga dallarının main'e göre farkı.
- [ ] Defter sayımı: Python ile her `| D-NNN |` satırının son hücresini al; açık = `casefold()` sonrası `açık`/`acik`/`kısmen`/`kismen` ile başlar ya da satır elle tutulan tuhaf biçim listesindedir (D-012, D-023, D-076, D-279 ve plan sırasında eklenenler; bunlar için durum hücresi yeniden yazıldı mı bakılır) ya da metinde `durum: açık` geçer. Beklenen: 0. `ertelendi:` ve `wontfix` Kadir cevabıyla kapalıdır. Sayımın kendisi bir kez elle denetlenir: rastgele 10 kapalı satırın durumunu oku.
- [ ] Kadir oynayışı (en az 10 dakika) ve sabah özeti.

---

## Dalga kapısı (DK1-DK3; DK4 = G4.4)

- [ ] **K1:** dalganın bütün görevleri dalga dalında; denetleyici defteri güncelledi.
- [ ] **K2 CI kapıları yerelde:** `.github/workflows/ai-dnd-quality.yml` içindeki adımlar aynen (ruff F,E9 taban, ruff/knip/vulture/gitleaks/size_lock yalnız küçülür, vulture 80, gitleaks tam geçmiş, knip, `pnpm run typecheck`). Hepsi exit 0.
- [ ] **K3 ucuz taban komutları:** `ruff_extra`, `vulture60`, `bandit`, `pyright`, `radon_cc`, `import_linter`, `engine_api_edges`, `deptry`, `fallow` → `AI-DND-TOOLS/gate-<tarih>-dalgaN/raw`; `make_baseline.py` ile `baseline-dalgaN.json`.
- [ ] **K4 karşılaştırma:** `compare_baseline.py baseline.json baseline-dalgaN.json --touched "$(git diff --name-only origin/main...HEAD)"` → exit 0. Herhangi bir aracın toplamı büyürse (dokunulmayan dosyada olsa da) aynı dalgada, büyümeye yol açan görevin kulvarında küçük düzeltme görevi (aynı kurallar). Yeni satır açılmaz. deptry ve skylos da karşılaştırılır (skylos yalnız DK2 ve G4.4'te, 289 sn).
- [ ] **K5 dalga hedef seti:** dalgada dokunulan dosyaları okuyan test modüllerinin birleşimi + komşu set + motor kilitleri + para listesi, iki bayrakta, yuva 9 ve 2'ye bölünmüş. `failing_ids 0`.
- [ ] **K6 PR ve CI:** dalga dalı → main PR; `gh run list` ile iki iş akışı yeşil. Kırmızı hemen bildirilir; tekrar koşmadan önce kırmızı denemenin kanıtı indirilir.
- [ ] **K7 oynayış ve özet:** oyun davranışı değiştiyse Kadir en az 10 dakika oynar (oynayış listesi); oynamadıysa defterde "oynayış bekliyor" ve main'e birleştirme yok. Sabah özeti (en çok beş satır).
- [ ] **K8 açık süreç denetimi:** açık `bash`/`sleep` süreçleri kontrol edilir (hız kuralı 6).

---

## Bütçe

Haftalık kullanım %61; sıfırlanma 2026-11-29 17:00; %90'da yeni aşama başlamaz. Fable kullanılmaz; Opus yalnız para/kayıt/Geri Al incelemesi ve bütün dal incelemesi; implementer ve diğer incelemeler Sonnet. Sayılar tahmindir, ölçülmedi.

**Oran:** Dalga 1 görev başına ~%2,5 (implementer + inceleme + ortalama 0,4 düzeltme turu; 6/8 Opus inceleme) tahmin edilir. Sonraki dalgalar bu oranla hesaplanır; yalnız Opus incelemesi olmayan küçük (S) paketler için ~%1,5 kullanılır, çünkü Sonnet inceleme ve kısa diff. Dalga 1 bittiğinde gerçek oran defterden okunur ve tablo yeniden hesaplanır.

| Dalga | Görev | Ajan (impl + inceleme + düzeltme turu) | Opus inceleme | Tahmini pay | Hesap |
|---|---|---|---|---|---|
| 0 | 5 | 5 + 5 + 1 = 11 | 1 | %4 | küçük görevler, ~%0,8 |
| 1 | 8 | 8 + 8 + 3 = 19 | 6 | %20 | 8 × 2,5 |
| 2 | 26 | 26 + 26 + 8 = 60 | 15 | %55 | 15 × 2,5 + 11 × 1,5 |
| 3 | 12 | 12 + 12 + 4 = 28 | 4 | %22 | 4 × 2,5 + 8 × 1,5 |
| 4 | 4 | 4 + 7 (G4.2 dört parti) + 2 + bütün dal = 14 | 4 | %18 | G4.1 2,5 + G4.2 6 + G4.3 3 + G4.4 (tam ölçüm + bütün dal) 6 |

**Sıfırlamadan önce (61 → 90):** 29 puan var. Dalga 0 (%4) + Dalga 1 (%20) = %24 → ~%85; düzeltme turları fazla çıkarsa sınır aşılır. Sıra ve kesme kuralı: G0.1, G0.2, G0.5, G0.4, G0.3 → G1.1, G1.3 (KRİTİK) → G1.5 (güvenlik açığı) → G1.2, G1.4 → G1.6, G1.7, G1.8. Bir görev başlarken kullanım %82'yi geçmişse o görev ve kalan Dalga 1 görevleri (önce G1.8, G1.7, G1.6) sıfırlamaya kalır; yarım görev bırakılmaz.

**Sıfırlamadan sonra:** Dalga 2 (%55) ilk haftaya sığar; Dalga 3 (%22) ve Dalga 4 (%18) ikinci haftaya (6 Aralık sıfırlamasından sonra) kalır. Toplam yaklaşık iki hafta. Para/kayıt/Geri Al incelemesi ve bütün dal incelemesi bütçe için atlanmaz (Dokunulmaz).

## Kadir oynayış listesi (O) ve Kod-1 görsel listesi (K)

| No | Ne denenir | Hangi görev |
|---|---|---|
| O1 | Gizlice geçme, tırmanma, çalma denemelerinde zar görülür | G1.1 |
| O2 | "Tavernaya gidiyorum", birinin peşine gitme, NPC'nin söylediği hana gitme | G1.2 |
| O3 | "Yarın vuracağım ama şimdi içiyorum" gibi karışık satır; "evet" cevabı | G1.3 |
| O4 | Konuşma kipinde oda isteme, NPC'ye geçmişini sorma | G2.2 |
| O5 | Korkutma/ikna: zar sonucu ile anlatı tutarlı | G2.4 |
| O6 | Kasabada yürüme, binalardan çıkma, başlangıç kentine dönme | G2.5 |
| O7 | Takip etme, kapıya girme, açılıştaki ulağa soru | G2.14 |
| O8 | `-LocalPlay` oyunu sonrası `speech-debug.jsonl` okunur | G3.6 |
| O9 | Bahşiş, oda fiyatı, paket satışı, iş teslimi | G3.1-G3.3 |
| O10 | Kayıp Kişi görevi: kaçıranla karşılaşma | G3.12 |
| K1 | Karakter yaratma ekranı, altı sınıf | G1.6 |
| K2 | Oyun ekranı kaydırma, Geri Al, kurtarma mesajı | G1.7 |
| K3 | Wizard/Cleric 2-5 seviye başlangıcı | G2.12 |
| K4 | Erişilebilir adlar, el yuvaları, zorluk kartı | G2.21 |
| K5 | Eski select/CSS temizliği sonrası ekranlar | G3.10 |

---

## Kadir'e soru paketi (tek seferlik; cevaplar `docs/agents/borc-sorulari-20261126.md`'ye)

Her soruya harf ile cevap yeterli (ör. "S1 a"). "Öneri" bizim seçimimiz; cevapsız soru yeniden sorulmaz, yalnız dalga raporunda "cevap bekliyor" diye görünür ve ona bağlı görev başlamaz. Yalnız senin zevkine kalan ya da "wontfix/ertele" gerektiren sorular burada; classify.json'un 13 sorusu ve planın S52'si (eski numaralarıyla S2, S18-S23, S30, S33, S37, S39, S40, S45, S52; toplam 14) ajan kararına çevrildi, Rulings bölümünde "R-S<eski no>" adıyla duruyor.

| No | Satır | Görev | Soru | Seçenekler | Öneri |
|---|---|---|---|---|---|
| S1 | D-024 | G0.1 | Bilinçsiz (Unconscious) kuralı PHB s.376'dan doğrulanmadı. Sen ya da Jarvis PDF'e bakabilir misin? | a) bak, doğrula, kapat · b) doğrulanmamış diye kabul et, kapat | a (Jarvis bakar) |
| S2 | D-320 | G0.1 | Para, kayıt ve Geri Al uç noktalarının (tekrar oynatma, eşzamanlı istek, iade) güvenlik incelemesi ne zaman? | a) şimdi, Opus ile · b) oyun internete açılmadan önce | b (bugün tek kullanıcı, yerel; satır 'internete açılana kadar wontfix') |
| S3 | D-021 | G0.1 | Gerçek model İngilizce 'I shove the guard' cümlesinde kavga sorusunu her zaman açmıyor. Motor güvenli. | a) motor yedek kural eklesin · b) olduğu gibi kalsın · c) ön model değişince bakılsın | b |
| S4 | D-343 | G0.1 | Parçalar motor adlarını game.X önekiyle okuyor; game.py'de 643 yeniden dışa aktarma satırı var. Bunlar kaldırılsın mı? | a) evet, ayrı bir dilimde · b) hayır, merkez kuralı kalıcı | b (kırılma riski büyük, oyuna faydası yok) |
| S5 | D-404 | G0.1 | Bayrak açıkken kullanılamayan okumadan sonra 2 çağrı sınırı yüzünden sonuç biraz kötüleşiyor. | a) kabul et · b) okumadan sonra ek çağrıya yer bırak | a |
| S6 | D-424 | G0.1 | Küçük model oda cümlesini 'belirsiz' okursa Python'un kelime yolu oda kartını yedek olarak açsın mı? | a) evet · b) hayır, tasarım kalsın | b |
| S7 | D-327 | G0.1 | Konuşma kipindeki eski kelime yedek yolları ne olsun? | a) sonraki oynayış ve ölçümden sonra kaldır · b) kalıcı yedek olarak kalsın | b (zararsız; model düşünce oyunu ayakta tutar) |
| S8 | D-246 | G0.1 | İlan panosu ya da iş listesi olduğunda söylenti sorusu oraya yönlendirsin mi? | a) evet · b) hayır, 'söylentiler belirsiz' kalsın | b (bugün pano olup olmadığını doğrulamadım) |
| S9 | D-168 | G0.1 | Uygulama içi araç sayaç dosyasının eski kopyasını gösteriyor. Bu yalnız geliştirici aracı. | a) wontfix · b) okuyucuyu düzelt | a |
| S10 | D-149 | G0.1 | Oyuncu başına maliyet kotası gerekli mi? | a) şimdi yap · b) gerek yok · c) çok kullanıcılı yayına kadar ertele | c |
| S11 | D-307 | G0.1 | Yolda ikinci yerleşim (ör. Phandalin) ve kentler arası yolculuk yapılsın mı? | a) dilim olarak yap · b) ertele, bugünkü çıkmaz mesajı kalsın | b |
| S12 | 17 satır | G0.1 | Bu satırlar bir özellik gelmeden düzeltilemez. Her biri 'ertelendi: <özellik>' diye kapansın mı? Tetikleyici sütunu kalır; özellik gelince satır yeniden açılır. Para/kayıt/Geri Al satırları **kalın**. D-312: çok kullanıcılı barındırmada oturum sahipliği yok (özellik: çok kullanıcılı barındırma) · D-315: internete açık sürümde istek sınırı ve CORS eksik (özellik: internete açık sürüm) · D-029: yakın/uzak ayrımı konumsuz tahmin ediliyor (özellik: konum modeli) · D-022, D-025, D-026, D-014: İngilizce cümlelerde niyet/hedef okuması eksik (özellik: İngilizce dil desteği) · **D-009**: XP tablosunda olmayan CR'lı ilk canavar ödülsüz kalır (özellik: o canavarın eklenmesi) · D-169: NPC isteklilik/Influence modeli yok (özellik: Influence) · **D-271**: kalıcı ödül işareti kayıtta yok, ödül iki kez verilebilir (özellik: kalıcı ödül işareti) · D-042: Wizard/Cleric özellikleri sayfalı kaynak ve çözücü olmadan eksik (özellik: o sınıf çözücüleri) · **D-048**: müttefik NPC iyileştirme yolu yok, büyü/iksir harcanmadan sonuç çıkabilir (özellik: müttefik iyileştirme) · **D-050**: odak/malzeme bileşeni harcaması kayda yazılmıyor (özellik: bileşen kaydı) · D-058: savaşta anlatı büyüsü eylem ekonomisini atlıyor (özellik: savaş büyü eylemleri) · D-358: CI Python 3.14'e geçince yerel ile CI farkı (özellik: CI 3.14) · D-066: yoğunlaşma çözücüsü D-048'i bekliyor (özellik: yoğunlaşma çözücüsü) · **D-023**: Healer's Kit kodu oyuna bağlı değil, Geri Al sarmalı gerekiyor (özellik: stabilize eylemi + NPC müttefik ölüm kurtarışları) | a) hepsi ertelensin · b) satır satır yaz (ör. 'D-029 yap') | a (yapılan iş özelliği yarım getirir; para satırlarında bugün oyuncu o yola giremiyor — doğrulamadım, G0.1 doğrulayıcısı her biri için bunu kod okumasıyla kanıtlar) |
| S13 | D-177 | G1.3 | Motorun ayıramadığı model yanlış okumaları için yeniden tasarımdan önce küçük bir gerçek model ölçümü yapılsın mı? | a) evet, yerel gemma4-12b-dm ile (para harcanmaz) · b) evet, bulut modelle (bütçe rakamını sen ver) · c) ölçme, kurala göre düzelt | a |
| S14 | D-262 | G1.3 | 'timing' alanı gelmezse bugün 'şimdi' sayılıyor (güvensiz). Alanın gerçek modelde ne sıklıkla doğru dolduğu ölçülsün mü? (S13 ile aynı ölçüm) | a) yerel ölçüm · b) bulut ölçüm, bütçe sen · c) ölçme, alanı zorunlu yap ve eksikse sor | a |
| S15 | D-263 | G1.3 | 'evet' sonrası okuma yeniden yapılıyor ve ikinci okuma farklı çıkabilir. Ölçülsün mü? (S13 ile aynı ölçüm) | a) yerel ölçüm · b) bulut ölçüm, bütçe sen · c) ölçme, ilk okumayı sakla ve yeniden oynat | a (ölçüm ne derse desin ilk okumayı saklamayı da öneriyoruz) |
| S16 | D-260 | G1.3 | Bir satırda iki eylem ayrı zamanda olabilir ('yarın vuracağım ama şimdi içiyorum'). Okumaya eylem başına zaman alanı eklensin mi? | a) evet, eylem başına · b) hayır, karışık satırda oyuncuya kısa soru sorulsun | a |
| S17 | D-530 | G1.8 | Tur kodundaki kalan üç uzun işlev (_run_player_turn_internal, _dispatch_player_turn, _narration_safety_decision) şimdi bölünsün mü? Satır 'oynayıştan sonra' diyordu. | a) evet, bu planda, önce davranışı sabitleyen testlerle · b) bir sonraki oynayışından sonra | a |
| S18 | D-592 | G1.8 | 109 işlev F karmaşıklıkta. Bu planda üç tur işlevi bölünür ve 'yalnız küçülür' kapısı (ratchet) kurulur. Kalan işlevler için ne olsun? | a) ayrı bir planla hepsi küçültülsün (satır o plana kadar 'kısmen' kalır) · b) kalanlar wontfix: kapı onları yalnız küçültür, büyütmez (onay listesine 'gevşetme olabilir' diye girer) | b (109 işlevi bölmek haftalar sürer; oyuna faydası düşük) |
| S19 | D-425 | G2.2 | Konuşma kipinde oyuncu oda isteyince hancı konuşsun mu (bir ek model çağrısı) yoksa yalnız kart mı açılsın? | a) hancı konuşur · b) yalnız kart | a (sinematik anlatı kuralın) |
| S20 | D-419 | G2.3 | 'Satırın kalanı' ve yeniden sorulan stok cevabı için ek çağrılar NPC inisiyatifi gibi 3. çağrı istisnası alsın mı? | a) evet, bunlar için de sınır 3 · b) hayır, 2 kalsın, kaybolan cümleyi kabul et · c) oynayış kaybı gösterince karar ver | a |
| S21 | D-012 | G2.4 | Model gerçek deneyim ödülünü kendi cümlesiyle söylerse ('25 deneyim puanı kazandın') bugün reddediliyor. Tutar gerçek ödülle aynıysa izin verilsin mi? | a) aynı tutarsa izin ver, farklı tutar yine reddedilir · b) bugünkü gibi kalsın (sayıyı yalnız Python yazar) | a (sinematik anlatı; para/XP doğruluğu korunur) |
| S22 | D-498 | G2.5 | 'Dışarı, <kent> sokaklarına çıkıyorsun.' aynı oyunda tekrar tekrar yazılıyor. | a) çıkış satırını her sahnede model yazsın; Python satırı yalnız yedek ve ziyaret başına bir kez · b) yalnız ziyaret başına bir kez göster, sonra kısa çeşit | a |
| S23 | D-403 | G2.9 | Oyuncuya sayı söylenmeden 'biraz para' uzatılınca oyun ne yapsın? | a) reddet · b) tutarı sor · c) varsayılan bir tutar seç | b |
| S24 | D-451 | G2.18 | Test bulma aracı (inventory.touching_tests) içe aktarılan sınıfı yönteme göre değil ada göre çözüyor; güvenli yönde, yalnız yavaş. | a) gerekçeyle kabul et, kapat · b) şimdi düzelt | a |
| S25 | D-349 | G2.19 | Yönlendirme denetiminin (routing_audit) bilinen kör noktaları (eval/exec, string getattr, iki adımlı zincir) kapatılsın mı? | a) belgele ve kabul et (çalışma anı kimlik testi asıl riski kapsıyor) · b) kapat | a |
| S26 | D-536 | G2.24 | Makbuz sıkıştırma (compact_receipts) gerçek oyunda hiç çağrılmıyor, yalnız testler çağırıyor. | a) gerçek oyunda aç (kayıt küçülür, Geri Al'ın ulaştığı derinliği sınırlayabilir) · b) sil | b |
| S27 | D-445 | G2.25 | game.py başındaki 45 kullanılmayan içe aktarma için öneri: 44'ü kalsın (yama hedefi ya da yüzey), __main__ bloğundaki 1 'import game' silinsin (text_rules_a.py'deki eşiyle). | a) öneri kabul · b) satır satır yaz | a |
| S28 | D-490 | G2.25 | Ölü kod tablosu (docs/engine-split/olu-kod-kaniti.md) satır başına evet/hayır bekliyor. Tablodaki önerileri toplu kabul ediyor musun? | a) öneriler toplu kabul · b) tabloyu sen satır satır doldur | a |
| S29 | D-544 | G2.26 | combat_bind_allowed işlevi ölü. threat_band 'none' iken savaş bağı reddedilsin mi? | a) evet, kuralı gate.py'ye ekle ve işlevi tut · b) işlev ölü, sil | b |
| S30 | D-286 | G3.1 | İngilizce olumsuz kese cümlesi ('Not a single copper leaves your purse.') ele alınsın mı? | a) İngilizce olumsuzluğu şimdi ekle · b) İngilizce kip gelene kadar bekle (wontfix) | b |
| S31 | D-287 | G3.1 | Kazanılan zarda anlatı 10 bakır diyor, 5 bakır ödeniyor. | a) anlatıyı ödenen tutara göre yeniden yaz · b) nadir, olduğu gibi kabul et | a (para doğruluğu) |
| S32 | D-253 | G3.2 | 'Kısa Yay & 20 Ok' paketinde okların repoda fiyatı yok. | a) 20 ok için katalog fiyatı ekle (2024 kuralları: 1 GP) · b) paket satışını reddet | a |
| S33 | D-381 | G3.5 | Oyuncu 'şehrin dışına gidiyorum ve <kasabadaki biri>'ni soyuyorum' derse oyun ne yapsın? | a) o kişiye yürüsün · b) 'o kişi kasabada mı?' diye sorsun | b |
| S34 | D-310 | G3.6 | Güvenlik denetiminin değiştirdiği NPC sözlerinin model ham metni görünmüyor. Yerel oyun başlatıcısı konuşma hata ayıklama kaydını (AI_DND_SPEECH_DEBUG) varsayılan açsın mı? | a) evet, -LocalPlay'de açık · b) hayır, sonraki oyunda elle açarsın | a |
| S35 | D-589 | G4.1 | pyright (tip denetimi) kapıya girsin mi? | a) evet, yalnız küçülen taban (ratchet) olarak · b) kapı olmadan yalnız en kötü dosyaları düzelt | a |
| S36 | D-591 | G4.1 | ruff hata kalıbı kuralları B023/B904/B905 kapıya girsin mi? | a) bugünkü sayıyla taban yapıp kapıya ekle · b) yalnız kaynak koddakileri düzelt | a |
| S37 | D-600 | G4.1 | Yedi yeni araçtan hangileri CI kapısına girsin? CI süresi artabilir. | a) pip-audit, pnpm audit --prod, import-linter, pyright ratchet · b) yalnız iki audit · c) hiçbiri | a |
| S38 | D-598 | G4.3 | desloppify bazı kümeleri bilinçli tasarım yüzünden 'sorun' sayıyor (ör. game_parts tek paket olduğu için 988 bölümler arası özel içe aktarma). Bunlar 'gerekçeli yanlış alarm' diye kapansın mı? | a) evet, gerekçe satır notuna yazılır · b) hayır, hepsi düzeltilsin | a |
| S39 | D-599 | G4.2 | İki soru: (1) /docs ve /openapi rotaları barındırma kipinde kapansın mı? (2) Koddaki yaklaşık 935 'raise ValueError' GameError'a taşınsın mı? | (1) a) barındırma kipinde kapalı, yerelde açık · b) her yerde açık. (2) a) taşı · b) taşıma, yalnız yeni kod GameError kullansın | (1) a (G2.10 D-314 ile aynı iş) · (2) b (davranış ve hata metni riski) |

Kaynak sayımı: 39 soru. 36'sı classify.json'daki 49 sahip sorusundan kalanlar; 13'ü (eski S2, S18-S23, S30, S33, S37, S39, S40, S45) ve planın eski S52'si ajan kararına (Ruling) çevrildi. S12 erteleme listesi, S16 (D-260) ve S21 (D-012) plan tarafından eklendi. D-382 S33'ün cevabını izler.


---

## Ek B — Görev özet tablosu

| Görev | Satır sayısı | Satırlar | P/K/G | İnceleme |
|---|---|---|---|---|
| G0.1 | 28 | D-024, D-320, D-021, D-343, D-404, D-424, D-327, D-246, D-168, D-149, D-307, D-312, D-315, D-029, D-022, D-025, D-026, D-009, D-169, D-271, D-042, D-048, D-050, D-058, D-358, D-066, D-014, D-023 | evet | Sonnet (kod yok; cevapla kapanış) |
| G0.2 | 4 | D-344, D-517, D-086, D-478 | evet | Opus (D-517), Sonnet (diğerleri) |
| G0.3 | 4 | D-078, D-079, D-304, D-306 | - | Sonnet |
| G0.4 | 1 | D-302 | - | Sonnet |
| G1.1 | 2 | D-094, D-173 | evet | Opus |
| G1.2 | 5 | D-331, D-335, D-333, D-299, D-297 | - | Sonnet |
| G1.3 | 8 | D-109, D-260, D-261, D-262, D-263, D-177, D-420, D-245 | evet | Opus |
| G1.4 | 2 | D-531, D-532 | evet | Opus |
| G1.5 | 6 | D-575, D-585, D-586, D-311, D-568, D-569 | - | Sonnet |
| G1.6 | 7 | D-561, D-571, D-560, D-578, D-564, D-559, D-573 | evet | Opus |
| G1.7 | 5 | D-090, D-088, D-089, D-574, D-180 | evet | Opus |
| G1.8 | 3 | D-530, D-592, D-584 | evet | Opus |
| G2.1 | 8 | D-410, D-415, D-421, D-423, D-428, D-411, D-390, D-389 | evet | Opus |
| G2.2 | 3 | D-413, D-414, D-425 | - | Sonnet |
| G2.3 | 9 | D-150, D-416, D-418, D-419, D-417, D-405, D-408, D-494, D-496 | evet | Opus |
| G2.4 | 5 | D-226, D-241, D-242, D-251, D-012 | - | Sonnet |
| G2.5 | 6 | D-301, D-338, D-309, D-296, D-498, D-303 | evet | Opus |
| G2.6 | 6 | D-525, D-524, D-576, D-538, D-505, D-028 | evet | Opus |
| G2.7 | 3 | D-504, D-526, D-518 | evet | Opus |
| G2.8 | 2 | D-581, D-502 | evet | Opus |
| G2.9 | 3 | D-317, D-403, D-501 | evet | Opus |
| G2.10 | 7 | D-540, D-319, D-313, D-539, D-314, D-385, D-316 | evet | Opus |
| G2.11 | 2 | D-590, D-583 | - | Sonnet |
| G2.12 | 3 | D-057, D-040, D-280 | evet | Opus |
| G2.13 | 2 | D-336, D-337 | - | Sonnet |
| G2.14 | 3 | D-243, D-244, D-308 | - | Sonnet |
| G2.15 | 3 | D-516, D-549, D-552 | evet | Opus |
| G2.16 | 3 | D-515, D-520, D-548 | - | Sonnet |
| G2.17 | 9 | D-329, D-341, D-342, D-340, D-218, D-500, D-553, D-467, D-346 | evet | Opus |
| G2.18 | 7 | D-451, D-461, D-452, D-437, D-438, D-362, D-365 | evet | Opus |
| G2.19 | 12 | D-349, D-468, D-431, D-432, D-433, D-436, D-435, D-363, D-427, D-475, D-434, D-359 | - | Sonnet |
| G2.20 | 8 | D-383, D-386, D-393, D-384, D-554, D-085, D-480, D-292 | - | Sonnet |
| G2.21 | 4 | D-153, D-235, D-563, D-282 | evet | Opus |
| G2.22 | 7 | D-557, D-570, D-558, D-572, D-567, D-566, D-579 | evet | Opus |
| G2.23 | 2 | D-587, D-593 | - | Sonnet |
| G2.24 | 3 | D-495, D-536, D-305 | evet | Opus |
| G2.25 | 6 | D-445, D-490, D-492, D-555, D-507, D-523 | - | Sonnet |
| G2.26 | 9 | D-512, D-544, D-509, D-513, D-514, D-580, D-594, D-601, D-595 | - | Sonnet |
| G3.1 | 6 | D-285, D-286, D-287, D-288, D-289, D-291 | evet | Opus |
| G3.2 | 7 | D-334, D-253, D-275, D-278, D-265, D-412, D-318 | evet | Opus |
| G3.3 | 4 | D-277, D-284, D-293, D-596 | evet | Opus |
| G3.4 | 5 | D-295, D-298, D-321, D-322, D-323 | evet | Opus |
| G3.5 | 6 | D-381, D-382, D-392, D-222, D-508, D-330 | - | Sonnet |
| G3.6 | 7 | D-582, D-290, D-165, D-406, D-407, D-409, D-310 | - | Sonnet |
| G3.7 | 1 | D-597 | - | Sonnet |
| G3.8 | 11 | D-453, D-454, D-462, D-463, D-476, D-477, D-380, D-356, D-388, D-391, D-076 | - | Sonnet |
| G3.9 | 13 | D-357, D-442, D-457, D-460, D-482, D-493, D-479, D-481, D-491, D-439, D-441, D-455, D-469 | - | Sonnet |
| G3.10 | 1 | D-164 | - | Sonnet |
| G3.11 | 5 | D-083, D-087, D-091, D-273, D-236 | - | Sonnet |
| G3.12 | 2 | D-279, D-221 | - | Sonnet |
| G4.1 | 5 | D-588, D-589, D-591, D-556, D-600 | evet | Opus |
| G4.2 | 1 | D-599 | evet | Opus |
| G4.3 | 1 | D-598 | evet | Opus |
| G0.5 | 0 | — | - | Sonnet |
| G4.4 | 0 | — | - | Opus (bütün dal) |


## Ek A — Satır → görev eşlemesi (285 satır)

Sayım: 285 satır (classify.json 281 + classify dışı açık 4), 285 eşleme, tekrar yok, eksik yok (betikle denetlendi; yürütücü Dalga 0'da aynı denetimi defterin o günkü hâliyle, "Kapalı sayma" tanımıyla yeniden yapar). "P/K/G" para/kayıt/Geri Al demektir. "Soru" sütunu bağlı soru numarası (S) ya da ajan kararı (R-S<eski no>) gösterir. Classify dışı 4 satırın tür/öncelik değerleri defter metninden plan tarafından atandı.

| Satır | Öncelik | Tür | P/K/G | Görev | Soru/Ruling |
|---|---|---|---|---|---|
| D-009 | ORTA | blocked_on_feature | evet | G0.1 | S12 |
| D-012 | ORTA | owner_decision | - | G2.4 | S21 |
| D-014 | ORTA | blocked_on_feature | - | G0.1 | S12 |
| D-021 | ORTA | owner_decision | - | G0.1 | S3 |
| D-022 | DÜŞÜK | blocked_on_feature | - | G0.1 | S12 |
| D-023 | ORTA | blocked_on_feature | evet | G0.1 | S12 |
| D-024 | DÜŞÜK | owner_decision | - | G0.1 | S1 |
| D-025 | DÜŞÜK | blocked_on_feature | - | G0.1 | S12 |
| D-026 | DÜŞÜK | blocked_on_feature | - | G0.1 | S12 |
| D-028 | DÜŞÜK | code_fix | evet | G2.6 | - |
| D-029 | ORTA | blocked_on_feature | - | G0.1 | S12 |
| D-040 | ORTA | code_fix | evet | G2.12 | - |
| D-042 | ORTA | blocked_on_feature | - | G0.1 | S12 |
| D-048 | ORTA | blocked_on_feature | evet | G0.1 | S12 |
| D-050 | ORTA | blocked_on_feature | evet | G0.1 | S12 |
| D-057 | ORTA | code_fix | - | G2.12 | - |
| D-058 | ORTA | blocked_on_feature | - | G0.1 | S12 |
| D-066 | DÜŞÜK | blocked_on_feature | - | G0.1 | S12 |
| D-076 | DÜŞÜK | test_only | - | G3.8 | - |
| D-078 | DÜŞÜK | external_tool | - | G0.3 | R-S52 |
| D-079 | DÜŞÜK | external_tool | - | G0.3 | R-S52 |
| D-083 | DÜŞÜK | test_only | - | G3.11 | - |
| D-085 | DÜŞÜK | test_only | - | G2.20 | - |
| D-086 | DÜŞÜK | already_fixed | - | G0.2 | - |
| D-087 | DÜŞÜK | test_only | - | G3.11 | - |
| D-088 | ORTA | code_fix | - | G1.7 | - |
| D-089 | ORTA | code_fix | - | G1.7 | - |
| D-090 | ORTA | code_fix | - | G1.7 | - |
| D-091 | DÜŞÜK | test_only | - | G3.11 | - |
| D-094 | KRİTİK | code_fix | evet | G1.1 | - |
| D-109 | KRİTİK | code_fix | evet | G1.3 | - |
| D-149 | ORTA | blocked_on_feature | - | G0.1 | S10 |
| D-150 | ORTA | code_fix | evet | G2.3 | - |
| D-153 | ORTA | code_fix | - | G2.21 | - |
| D-164 | DÜŞÜK | refactor | - | G3.10 | - |
| D-165 | DÜŞÜK | code_fix | - | G3.6 | - |
| D-168 | DÜŞÜK | external_tool | - | G0.1 | S9 |
| D-169 | ORTA | blocked_on_feature | - | G0.1 | S12 |
| D-173 | ORTA | code_fix | evet | G1.1 | - |
| D-177 | DÜŞÜK | owner_decision | evet | G1.3 | S13 |
| D-180 | DÜŞÜK | code_fix | - | G1.7 | - |
| D-218 | ORTA | tooling_ci | - | G2.17 | - |
| D-221 | DÜŞÜK | owner_decision | - | G3.12 | R-S2 |
| D-222 | DÜŞÜK | code_fix | - | G3.5 | - |
| D-226 | ORTA | code_fix | - | G2.4 | - |
| D-235 | ORTA | code_fix | - | G2.21 | - |
| D-236 | DÜŞÜK | test_only | - | G3.11 | - |
| D-241 | ORTA | code_fix | - | G2.4 | - |
| D-242 | ORTA | code_fix | - | G2.4 | - |
| D-243 | ORTA | code_fix | - | G2.14 | - |
| D-244 | ORTA | code_fix | - | G2.14 | - |
| D-245 | DÜŞÜK | code_fix | - | G1.3 | - |
| D-246 | DÜŞÜK | owner_decision | - | G0.1 | S8 |
| D-251 | ORTA | code_fix | - | G2.4 | - |
| D-253 | DÜŞÜK | code_fix | evet | G3.2 | S32 |
| D-260 | DÜŞÜK | owner_decision | - | G1.3 | S16 |
| D-261 | DÜŞÜK | code_fix | - | G1.3 | - |
| D-262 | DÜŞÜK | owner_decision | - | G1.3 | S14 |
| D-263 | DÜŞÜK | owner_decision | - | G1.3 | S15 |
| D-265 | DÜŞÜK | code_fix | evet | G3.2 | - |
| D-271 | DÜŞÜK | blocked_on_feature | evet | G0.1 | S12 |
| D-273 | DÜŞÜK | test_only | - | G3.11 | - |
| D-275 | DÜŞÜK | code_fix | evet | G3.2 | - |
| D-277 | DÜŞÜK | code_fix | evet | G3.3 | - |
| D-278 | DÜŞÜK | code_fix | evet | G3.2 | - |
| D-279 | DÜŞÜK | code_fix | - | G3.12 | - |
| D-280 | DÜŞÜK | code_fix | - | G2.12 | - |
| D-282 | DÜŞÜK | code_fix | - | G2.21 | - |
| D-284 | DÜŞÜK | code_fix | evet | G3.3 | - |
| D-285 | DÜŞÜK | code_fix | - | G3.1 | - |
| D-286 | DÜŞÜK | code_fix | - | G3.1 | S30 |
| D-287 | DÜŞÜK | code_fix | - | G3.1 | S31 |
| D-288 | DÜŞÜK | code_fix | - | G3.1 | - |
| D-289 | DÜŞÜK | code_fix | evet | G3.1 | - |
| D-290 | DÜŞÜK | code_fix | - | G3.6 | - |
| D-291 | DÜŞÜK | code_fix | - | G3.1 | - |
| D-292 | ORTA | tooling_ci | - | G2.20 | - |
| D-293 | DÜŞÜK | code_fix | - | G3.3 | - |
| D-295 | DÜŞÜK | code_fix | - | G3.4 | - |
| D-296 | DÜŞÜK | code_fix | - | G2.5 | - |
| D-297 | ORTA | code_fix | - | G1.2 | - |
| D-298 | DÜŞÜK | code_fix | - | G3.4 | - |
| D-299 | DÜŞÜK | code_fix | - | G1.2 | - |
| D-301 | ORTA | code_fix | - | G2.5 | - |
| D-302 | DÜŞÜK | external_tool | - | G0.4 | R-S52 |
| D-303 | DÜŞÜK | code_fix | evet | G2.5 | - |
| D-304 | DÜŞÜK | external_tool | - | G0.3 | R-S52 |
| D-305 | DÜŞÜK | test_only | evet | G2.24 | - |
| D-306 | DÜŞÜK | external_tool | - | G0.3 | R-S52 |
| D-307 | ORTA | blocked_on_feature | - | G0.1 | S11 |
| D-308 | ORTA | code_fix | - | G2.14 | - |
| D-309 | DÜŞÜK | code_fix | - | G2.5 | - |
| D-310 | DÜŞÜK | owner_decision | - | G3.6 | S34 |
| D-311 | DÜŞÜK | owner_decision | - | G1.5 | R-S21 |
| D-312 | DÜŞÜK | blocked_on_feature | evet | G0.1 | S12 |
| D-313 | DÜŞÜK | code_fix | - | G2.10 | - |
| D-314 | DÜŞÜK | code_fix | - | G2.10 | - |
| D-315 | DÜŞÜK | blocked_on_feature | - | G0.1 | S12 |
| D-316 | DÜŞÜK | code_fix | - | G2.10 | - |
| D-317 | ORTA | code_fix | evet | G2.9 | - |
| D-318 | DÜŞÜK | code_fix | - | G3.2 | - |
| D-319 | DÜŞÜK | code_fix | - | G2.10 | - |
| D-320 | ORTA | owner_decision | evet | G0.1 | S2 |
| D-321 | DÜŞÜK | code_fix | - | G3.4 | - |
| D-322 | DÜŞÜK | code_fix | - | G3.4 | - |
| D-323 | DÜŞÜK | test_only | evet | G3.4 | - |
| D-327 | DÜŞÜK | owner_decision | - | G0.1 | S7 |
| D-329 | ORTA | tooling_ci | - | G2.17 | - |
| D-330 | DÜŞÜK | test_only | - | G3.5 | - |
| D-331 | YÜKSEK | code_fix | - | G1.2 | - |
| D-333 | ORTA | code_fix | - | G1.2 | - |
| D-334 | DÜŞÜK | code_fix | evet | G3.2 | - |
| D-335 | DÜŞÜK | code_fix | - | G1.2 | - |
| D-336 | ORTA | code_fix | - | G2.13 | - |
| D-337 | ORTA | code_fix | - | G2.13 | - |
| D-338 | DÜŞÜK | code_fix | - | G2.5 | - |
| D-340 | DÜŞÜK | refactor | - | G2.17 | - |
| D-341 | ORTA | tooling_ci | - | G2.17 | - |
| D-342 | ORTA | tooling_ci | - | G2.17 | - |
| D-343 | DÜŞÜK | owner_decision | - | G0.1 | S4 |
| D-344 | DÜŞÜK | already_fixed | - | G0.2 | - |
| D-346 | DÜŞÜK | tooling_ci | - | G2.17 | - |
| D-349 | ORTA | tooling_ci | - | G2.19 | S25 |
| D-356 | DÜŞÜK | test_only | - | G3.8 | - |
| D-357 | DÜŞÜK | docs | - | G3.9 | - |
| D-358 | DÜŞÜK | blocked_on_feature | - | G0.1 | S12 |
| D-359 | ORTA | external_tool | - | G2.19 | - |
| D-362 | DÜŞÜK | test_only | - | G2.18 | - |
| D-363 | DÜŞÜK | test_only | - | G2.19 | - |
| D-365 | DÜŞÜK | test_only | - | G2.18 | - |
| D-380 | DÜŞÜK | test_only | - | G3.8 | - |
| D-381 | DÜŞÜK | owner_decision | - | G3.5 | S33 |
| D-382 | DÜŞÜK | owner_decision | - | G3.5 | - |
| D-383 | ORTA | test_only | - | G2.20 | - |
| D-384 | DÜŞÜK | test_only | - | G2.20 | - |
| D-385 | DÜŞÜK | code_fix | - | G2.10 | - |
| D-386 | ORTA | test_only | - | G2.20 | - |
| D-388 | DÜŞÜK | refactor | - | G3.8 | - |
| D-389 | DÜŞÜK | test_only | - | G2.1 | - |
| D-390 | DÜŞÜK | test_only | evet | G2.1 | - |
| D-391 | DÜŞÜK | test_only | - | G3.8 | - |
| D-392 | DÜŞÜK | test_only | - | G3.5 | - |
| D-393 | ORTA | test_only | - | G2.20 | - |
| D-403 | ORTA | owner_decision | evet | G2.9 | S23 |
| D-404 | ORTA | owner_decision | - | G0.1 | S5 |
| D-405 | DÜŞÜK | test_only | - | G2.3 | - |
| D-406 | DÜŞÜK | test_only | - | G3.6 | - |
| D-407 | DÜŞÜK | test_only | - | G3.6 | - |
| D-408 | DÜŞÜK | code_fix | - | G2.3 | - |
| D-409 | DÜŞÜK | test_only | - | G3.6 | - |
| D-410 | ORTA | test_only | evet | G2.1 | - |
| D-411 | DÜŞÜK | test_only | evet | G2.1 | - |
| D-412 | DÜŞÜK | code_fix | evet | G3.2 | - |
| D-413 | ORTA | code_fix | - | G2.2 | - |
| D-414 | ORTA | code_fix | - | G2.2 | - |
| D-415 | DÜŞÜK | test_only | - | G2.1 | - |
| D-416 | DÜŞÜK | code_fix | - | G2.3 | - |
| D-417 | DÜŞÜK | test_only | - | G2.3 | - |
| D-418 | DÜŞÜK | refactor | - | G2.3 | - |
| D-419 | ORTA | owner_decision | - | G2.3 | S20 |
| D-420 | DÜŞÜK | code_fix | - | G1.3 | - |
| D-421 | DÜŞÜK | test_only | - | G2.1 | - |
| D-423 | DÜŞÜK | test_only | evet | G2.1 | - |
| D-424 | DÜŞÜK | owner_decision | - | G0.1 | S6 |
| D-425 | DÜŞÜK | owner_decision | - | G2.2 | S19 |
| D-427 | DÜŞÜK | tooling_ci | - | G2.19 | - |
| D-428 | DÜŞÜK | refactor | - | G2.1 | - |
| D-431 | DÜŞÜK | tooling_ci | - | G2.19 | - |
| D-432 | DÜŞÜK | tooling_ci | - | G2.19 | - |
| D-433 | DÜŞÜK | tooling_ci | - | G2.19 | - |
| D-434 | DÜŞÜK | tooling_ci | - | G2.19 | - |
| D-435 | DÜŞÜK | test_only | - | G2.19 | - |
| D-436 | DÜŞÜK | tooling_ci | - | G2.19 | - |
| D-437 | DÜŞÜK | test_only | - | G2.18 | - |
| D-438 | DÜŞÜK | tooling_ci | - | G2.18 | - |
| D-439 | DÜŞÜK | docs | - | G3.9 | - |
| D-441 | DÜŞÜK | docs | - | G3.9 | - |
| D-442 | DÜŞÜK | docs | - | G3.9 | - |
| D-445 | DÜŞÜK | owner_decision | - | G2.25 | S27 |
| D-451 | ORTA | tooling_ci | - | G2.18 | S24 |
| D-452 | DÜŞÜK | tooling_ci | evet | G2.18 | - |
| D-453 | DÜŞÜK | test_only | - | G3.8 | - |
| D-454 | DÜŞÜK | test_only | - | G3.8 | - |
| D-455 | DÜŞÜK | external_tool | - | G3.9 | - |
| D-457 | DÜŞÜK | docs | - | G3.9 | - |
| D-460 | DÜŞÜK | docs | - | G3.9 | - |
| D-461 | ORTA | tooling_ci | - | G2.18 | - |
| D-462 | DÜŞÜK | test_only | - | G3.8 | - |
| D-463 | DÜŞÜK | test_only | - | G3.8 | - |
| D-467 | ORTA | tooling_ci | evet | G2.17 | - |
| D-468 | ORTA | tooling_ci | - | G2.19 | - |
| D-469 | DÜŞÜK | already_fixed | - | G3.9 | - |
| D-475 | DÜŞÜK | tooling_ci | - | G2.19 | - |
| D-476 | DÜŞÜK | test_only | - | G3.8 | - |
| D-477 | DÜŞÜK | test_only | - | G3.8 | - |
| D-478 | DÜŞÜK | false_alarm | - | G0.2 | - |
| D-479 | DÜŞÜK | docs | - | G3.9 | - |
| D-480 | DÜŞÜK | test_only | - | G2.20 | - |
| D-481 | DÜŞÜK | docs | - | G3.9 | - |
| D-482 | DÜŞÜK | docs | - | G3.9 | - |
| D-490 | DÜŞÜK | owner_decision | - | G2.25 | S28 |
| D-491 | DÜŞÜK | docs | - | G3.9 | - |
| D-492 | DÜŞÜK | refactor | - | G2.25 | - |
| D-493 | DÜŞÜK | docs | - | G3.9 | - |
| D-494 | ORTA | code_fix | - | G2.3 | - |
| D-495 | DÜŞÜK | code_fix | evet | G2.24 | - |
| D-496 | ORTA | code_fix | - | G2.3 | - |
| D-498 | DÜŞÜK | code_fix | - | G2.5 | S22 |
| D-500 | ORTA | tooling_ci | - | G2.17 | - |
| D-501 | ORTA | refactor | evet | G2.9 | - |
| D-502 | ORTA | refactor | evet | G2.8 | - |
| D-504 | ORTA | code_fix | evet | G2.7 | - |
| D-505 | DÜŞÜK | refactor | - | G2.6 | - |
| D-507 | DÜŞÜK | refactor | - | G2.25 | - |
| D-508 | DÜŞÜK | code_fix | - | G3.5 | - |
| D-509 | ORTA | refactor | - | G2.26 | - |
| D-512 | DÜŞÜK | owner_decision | - | G2.26 | R-S37 |
| D-513 | DÜŞÜK | refactor | - | G2.26 | - |
| D-514 | DÜŞÜK | refactor | - | G2.26 | - |
| D-515 | ORTA | refactor | - | G2.16 | - |
| D-516 | ORTA | refactor | evet | G2.15 | - |
| D-517 | YÜKSEK | already_fixed | evet | G0.2 | - |
| D-518 | ORTA | code_fix | evet | G2.7 | - |
| D-520 | DÜŞÜK | refactor | - | G2.16 | - |
| D-523 | DÜŞÜK | refactor | - | G2.25 | - |
| D-524 | ORTA | code_fix | evet | G2.6 | - |
| D-525 | ORTA | code_fix | evet | G2.6 | - |
| D-526 | ORTA | refactor | evet | G2.7 | - |
| D-530 | YÜKSEK | refactor | evet | G1.8 | S17 |
| D-531 | YÜKSEK | refactor | evet | G1.4 | - |
| D-532 | ORTA | refactor | evet | G1.4 | R-S18 |
| D-536 | ORTA | owner_decision | evet | G2.24 | S26 |
| D-538 | DÜŞÜK | code_fix | evet | G2.6 | - |
| D-539 | DÜŞÜK | refactor | - | G2.10 | - |
| D-540 | ORTA | refactor | evet | G2.10 | - |
| D-544 | DÜŞÜK | owner_decision | - | G2.26 | S29 |
| D-548 | DÜŞÜK | refactor | - | G2.16 | - |
| D-549 | ORTA | refactor | - | G2.15 | - |
| D-552 | ORTA | docs | - | G2.15 | - |
| D-553 | DÜŞÜK | tooling_ci | - | G2.17 | - |
| D-554 | DÜŞÜK | test_only | - | G2.20 | - |
| D-555 | ORTA | refactor | - | G2.25 | - |
| D-556 | DÜŞÜK | tooling_ci | - | G4.1 | - |
| D-557 | ORTA | dependency | - | G2.22 | R-S33 |
| D-558 | DÜŞÜK | code_fix | - | G2.22 | - |
| D-559 | DÜŞÜK | test_only | evet | G1.6 | - |
| D-560 | YÜKSEK | refactor | evet | G1.6 | - |
| D-561 | ORTA | refactor | evet | G1.6 | - |
| D-563 | DÜŞÜK | code_fix | evet | G2.21 | - |
| D-564 | DÜŞÜK | code_fix | evet | G1.6 | - |
| D-566 | DÜŞÜK | refactor | evet | G2.22 | - |
| D-567 | DÜŞÜK | docs | - | G2.22 | - |
| D-568 | ORTA | dependency | - | G1.5 | R-S22 |
| D-569 | ORTA | dependency | - | G1.5 | R-S23 |
| D-570 | ORTA | dependency | - | G2.22 | - |
| D-571 | ORTA | refactor | evet | G1.6 | - |
| D-572 | DÜŞÜK | code_fix | - | G2.22 | - |
| D-573 | DÜŞÜK | test_only | evet | G1.6 | - |
| D-574 | YÜKSEK | refactor | evet | G1.7 | - |
| D-575 | DÜŞÜK | dependency | - | G1.5 | R-S20 |
| D-576 | ORTA | code_fix | evet | G2.6 | - |
| D-578 | DÜŞÜK | refactor | - | G1.6 | - |
| D-579 | DÜŞÜK | dependency | - | G2.22 | - |
| D-580 | DÜŞÜK | refactor | - | G2.26 | R-S39 |
| D-581 | ORTA | code_fix | evet | G2.8 | - |
| D-582 | DÜŞÜK | code_fix | - | G3.6 | R-S45 |
| D-583 | DÜŞÜK | refactor | - | G2.11 | R-S30 |
| D-584 | DÜŞÜK | blocked_on_feature | - | G1.8 | - |
| D-585 | YÜKSEK | dependency | - | G1.5 | R-S19 |
| D-586 | ORTA | dependency | - | G1.5 | - |
| D-587 | ORTA | dependency | - | G2.23 | - |
| D-588 | ORTA | code_fix | evet | G4.1 | - |
| D-589 | DÜŞÜK | tooling_ci | - | G4.1 | S35 |
| D-590 | ORTA | refactor | - | G2.11 | - |
| D-591 | DÜŞÜK | code_fix | - | G4.1 | S36 |
| D-592 | DÜŞÜK | refactor | evet | G1.8 | S18 |
| D-593 | DÜŞÜK | dependency | - | G2.23 | - |
| D-594 | DÜŞÜK | refactor | - | G2.26 | - |
| D-595 | DÜŞÜK | owner_decision | - | G2.26 | R-S40 |
| D-596 | DÜŞÜK | code_fix | evet | G3.3 | - |
| D-597 | DÜŞÜK | test_only | - | G3.7 | - |
| D-598 | ORTA | refactor | evet | G4.3 | S38 |
| D-599 | ORTA | refactor | evet | G4.2 | S39 |
| D-600 | DÜŞÜK | tooling_ci | - | G4.1 | S37 |
| D-601 | DÜŞÜK | refactor | - | G2.26 | - |

