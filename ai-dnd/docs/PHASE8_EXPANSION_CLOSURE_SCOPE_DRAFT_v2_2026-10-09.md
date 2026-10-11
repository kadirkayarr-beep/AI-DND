# AI-DND — Phase 8 Expansion Closure Scope Draft v2

**Belge kodu:** `AI-DND-P8-CLOSURE-SCOPE-DRAFT-v2`  
**Tarih:** 2026-10-09, Europe/Istanbul  
**Durum:** **DRAFT. KAPANIŞ DEĞİLDİR. PASS DEĞİLDİR. OWNER ONAYI DEĞİLDİR.**  
**Öncel:** `ai-dnd/docs/PHASE8_EXPANSION_CLOSURE_SCOPE_DRAFT_v1_2026-10-09.md` yerinde durur. Bu sürüm onu değiştirmez.

v2, v1’deki dört düzeltmeyi işler: AC-027 kanıt haritası, HTTP 500 politika ayrımı, kapanış kapılarının sözleşme kaynağı, Waterdeep öncelikli salt okuma araştırması. Oyun kodu, lore, pin, save, aktivasyon, `.gitattributes` ve Git bu belgeyle değişmez. Onaylı Bible v2.3.2 ve owner onay kaydı bayt olarak durur.

İncelenen ağaç: `C:\Users\Kadir\Desktop\AI-DND-phase8-expansion`  
Dal: `phase8/emergent-storytelling-expansion`  
HEAD: `0c7b24cd7ec9e32f0a54412769f85851b30d11a2`  
Bu turda test koşulmadı.

## 1. Phase 8 zorunlu kapanış kapsamı

Zorunluluk, bir maddenin hangi sözleşmede kapanış engeli diye yazıldığına bağlıdır. F01 ve production maddeleri bu listeye otomatik girmez. Daha önce zorunlu sayılan FAIL silinmez.

| Madde | Sözleşme kaynağı | Phase 8 kapanışındaki yeri |
|---|---|---|
| S10B-AC-001 … AC-026 ve AC-028 | `STAGE10B_MASTER_IMPLEMENTATION_PLAN_v2.md` satırları. Repair-v2 `summary.json` bunları PASS yazar. | Tarihsel PASS. Bu belge taze PASS yazmaz. |
| S10B-AC-027 | Aynı plan: ilgili regresyon grubu yeni kanıt kökünde exit 0. Repair-v2 kabul kaydı, 165’lik lore koşusu kırmızı kaldığı için maddeyi **FAIL** ve kapanış engeli yapar. | Zorunlu ve açık. 165 FAIL silinmez. 296/634 ile eşdeğerlik bu belgede **UNVERIFIED**. |
| Repair-v2 final kabulü | `STAGE10B_REPAIR_FINAL_ACCEPTANCE_CURSOR_HANDOFF_v2_2026-10-09.md`: “Final kabul: FAIL; kapanış yazılmadı.” | Tarihsel belge durumu. Sonraki lore-integrity PASS cümlesi bu FAIL’i yok etmez. |
| `regressions-final` 633 / exit 1 | Repair-v2 `summary.json`. Neden CP1254. Aynı seçici listesinin sonraki `regressions-final-02` kaydı exit 0. | Tarihsel kırmızı koşu korunur. AC-027’nin plan metnindeki seçici yarısı için komut kimliği aşağıda doğrulanır. Bu, 165 lore FAIL’ini kapatmaz. |
| S10B-INV-001 | Plan v2 satırı: doğrulanmamış durur; çıkmaması düzeltildiği anlamına gelmez; kök neden uydurulmaz. | Kayıt zorunlu. **Kök nedenin bulunması bu sözleşmede kapanış önkoşulu değildir.** UNCONFIRMED, PASS değildir. |
| Stage 10A CLOSED | `STAGE10A_FINAL_CLOSURE_CURSOR_HANDOFF_v2_2026-10-09.md` | Tarihsel girdi. Bu belge onu yeniden açmaz ve taze PASS saymaz. Özgün tam sözleşme bulunamadı. |

Bu listenin dışında kalan ve Phase 8 kapanışına **ithal edilmeyen** kapılar bölüm 4’tedir. Live-release NO-GO, F01-AC-004, F01-AC-005 ve şehir aktivasyonu Phase 8 kapanış engeli diye bu listeye yazılmaz. Onların kendi kapıları durur.

AC-027 açık kaldığı sürece Phase 8 Expansion kapanış kaydı yazılmaz.

## 2. S10B-AC-027 kanıt haritası

Eşdeğerlik test sayısından kurulmaz. Sonuç: **UNVERIFIED**.

### 2.1 İki koşunun kimliği

| | Kırmızı 165 | Sonraki 296 | Sonraki 634 |
|---|---|---|---|
| Kanıt kökü | `.local/evidence/stage10b-repair-v2-20261009-085201/` | `.local/evidence/stage10b-lore-integrity-20261009-1805/` | Aynı lore-integrity kökü |
| Log | `boundary-persistence-weather-final.log` | `lore-boundary-persistence-weather.log` | `regressions-required.log` |
| Sonuç | 165 test, 4 failure, 14 error, 113.739 s, exit 1 | 296 test, 147.870 s, exit 0 | 634 test, 243.298 s, exit 0 |
| Komut dosyası | **Yok.** `lore-boundary-command.json` bu kökte yoktur. Handoff da eski 165 komutunun klasörde olmadığını yazar. | `lore-boundary-command.json` duruyor. | `regressions-required-command.json`, repair-v2 `regressions-final-command.json` ile aynı modül listesidir. |
| Kayıtlı HEAD | `git-head-final.txt`: `f63d952506064cd59e960f1e3efa6627d4e52053` | `summary.json`: aynı `f63d952` | Aynı |
| Kaynak | `protected-lore-blockers.json`: `models.py` gözlenen SHA-256 `f75bbafe95be7f9ea00500fab1065de6c1918e1de8d01705b30a2a5512948aa6`. Castle Ward gözlenen `d8accdf6…`, beklenen pin `be4b2f8a…`. | Handoff: `models.py` `3da765cb319d48b863b3645bce3c3f1f51f45e4e618f463e22fdda06315c63d6`. Castle Ward geri yüklenen `be4b2f8a…`. `registry.py` de değişmiş. | 634 komutu lore_1501 modüllerini içermez. |

İki yeşil koşu, kırmızı koşunun aynı kaynak snapshot’ı değildir. `models.py` özeti değişmiştir. Castle Ward baytı değişmiştir. Bu, onarımın kendisidir. Aynı komutun tekrarı değildir.

634 listesi, kırmızı 18 testi barındıran dört lore modülünü içermez. 634 exit 0, o 18 testin geçtiğini göstermez.

### 2.2 Kayıp kanıt

- 165 koşusunun argv’si yok. Hangi modüllerin seçildiği komut dosyasından doğrulanamaz.
- 165 logu `-q` çıktısıdır. Geçen testlerin kimlik listesi logda yoktur. Yalnız unittest’in yazdığı 18 kırmızı kimlik vardır.
- 296 logu da `-q` çıktısıdır. `Ran 296 tests` ve `OK` vardır. Test başına PASS satırı yoktur.
- 296 anındaki test dosyalarının SHA-256’sı kanıt köküne yazılmamıştır.
- Komut eşdeğerliğini bağımsız inceleyen ayrı bir kişi kaydı yoktur. Lore-integrity handoff’un kendi AC-027 PASS cümlesi bu boşluğu kapatmaz.

Bu dört boşluk dururken eşdeğerlik **UNVERIFIED** kalır. Tarihsel FAIL satırı durur.

### 2.3 Kırmızı 18 test

Logdaki erken `ERROR: Campaign autosave` ve `ERROR: Engine turn failed` satırları uygulama günlüğüdür. Unittest sonucu değildir. Unittest 14 error ve 4 failure, logun 4128. satırından sonradır ve toplam 18’dir.

Hepsinin ortak gözlenen nedeni, pin uyuşmazlığı yüzünden public kümenin boş kalması veya `OwnerContinuityRecord` import’unun düşmesidir. Assertion’lar gevşetilerek geçirilmemiştir. Aşağıdaki satır numaraları, bugünkü dosyada traceback ile aynı metni taşır. Bu, 296 anındaki dosya özetinin saklandığı anlamına gelmez.

| Test | Sonuç | Traceback’te ulaşılan ifade | 296 komutunda modül | Test başına yeşil satır |
|---|---|---|---|---|
| `Lore1501FreezeContractTests` setUpClass | ERROR | `load_freeze_view()` → `freeze input changed: Owner_Decision_Castle_Ward_1501.md sha256 d8accdf6…` | `test_lore_1501_freeze_contract` var | Yok |
| `test_altered_claim_text_is_rejected` | ERROR | `KeyError: WD22-F-001` (`canonical_proposal` satır 501). Hedef assertion’a gelinmedi. | `test_lore_1501_freeze_admission` var | Yok |
| `test_f015_printed_ward_list_is_admitted` | ERROR | `KeyError: WD22-F-015` | aynı modül | Yok |
| `test_f015_rejects_reintroduced_castle_ward_inference` | ERROR | `KeyError: WD22-F-015` | aynı modül | Yok |
| `test_historical_record_is_not_promoted_by_a_current_label` | ERROR | `KeyError: WD22-F-004` | aynı modül | Yok |
| `test_missing_source_applicability_is_not_replaced_by_runtime_scope` | ERROR | `KeyError: WD22-F-001` | aynı modül | Yok |
| `test_missing_sources_and_wrong_hash_fail_closed` | ERROR | `KeyError: BG22-F-001` | aynı modül | Yok |
| `test_owner_existence_sentence_is_not_admitted_as_the_2025_claim` | ERROR | `KeyError: WD22-F-015` | aynı modül | Yok |
| `test_restricted_record_is_rejected_when_relabeled_current_and_common` | ERROR | `KeyError: WD22-F-067` | aynı modül | Yok |
| `test_runtime_visibility_does_not_decide_a_verified_public_record` | ERROR | `KeyError: WD22-F-001` | aynı modül | Yok |
| `test_supplemental_record_is_rejected_when_relabeled_current` | ERROR | `KeyError: WD22-F-002-1` | aynı modül | Yok |
| `test_tampered_runtime_metadata_cannot_enter_the_projection` | ERROR | `KeyError: WD22-F-001` | aynı modül | Yok |
| `test_structure_comes_from_the_pinned_record` | ERROR | `KeyError: WD22-F-015` | `test_lore_1501_admission_boundary` var | Yok |
| `test_lore_1501_integration` | ERROR | `ImportError: cannot import name OwnerContinuityRecord`. Gövde çalışmadı. | `test_lore_1501_integration` var | Yok. Hangi gövdelerin geçtiği logda yok. |
| `test_pinned_evidence_loads_and_admits_every_public_record` | FAIL | `assertEqual(evidence.integrity_errors, ())`. Gözlenen: `sha256 mismatch Owner_Decision_Castle_Ward_1501.md` | admission modülü var | Yok |
| `test_unknown_id_is_rejected` | FAIL | `assertIn("not_in_public_freeze_manifest", decision.reasons)`. Gözlenen neden: `freeze_integrity` ve aynı mismatch. | aynı | Yok |
| `test_pinned_snapshot_is_deeply_immutable_and_covers_every_pin` | FAIL | `assertEqual(snapshot.evidence.integrity_errors, ())`. Aynı mismatch. | boundary modülü var | Yok |
| `test_public_batch_rejects_a_forged_projection` | FAIL | `assertEqual(batch.integrity_errors, ())`. Aynı mismatch. | aynı | Yok |

296 komutunun tam listesi: `test_lore_1501_freeze_contract`, `test_lore_1501_integration`, `test_lore_1501_freeze_admission`, `test_lore_1501_admission_boundary`, `test_api`, `test_campaign_api`, `test_persistence_idempotency`, `test_campaign_persistence`, `test_campaign_lore_persistence`, `test_exploration_package`, `test_exploration_boundaries`, `test_exploration_closeout`.

Bu liste, kırmızı modülleri içerir ve süit exit 0’dır. Modülün süite girmesi, o modüldeki her eski test kimliğinin aynı assertion ile geçtiğini göstermez. Integration gövdeleri 165’te hiç çalışmadığı için onların ilk geçişi 296’dadır ve kimlik dökümü yoktur.

Yerine konmuş veya gevşetilmiş bir assertion bu incelemede bulunmadı. Dört FAIL’in bugünkü satırları traceback ile aynıdır: admission dosyası 27 ve 124, boundary dosyası 23 ve 41, freeze view 150. Import hâlâ `OwnerContinuityRecord` adını ister. Sahte sınıf veya skip eklenmiş değildir.

### 2.4 Bu haritanın kapatmadığı şey

Lore-integrity handoff AC-027’yi PASS yazar. Bu belge o cümleyi tarihsel iddia olarak bırakır ve taze PASS saymaz. Owner, kayıp argv ve test başına döküm varken eşdeğerliği kabul edebilir. Kabul bu belgede yoktur. Kabul edilmezse AC-027 FAIL durur.

## 3. HTTP 500 araştırma politikası

Bu politika koşu başlatmaz. S10B-INV-001 fixed değildir ve bu turda yeniden üretildiği iddia edilmez.

Beş hüküm ayrıdır:

| Hüküm | Anlamı | Bu belgedeki durum |
|---|---|---|
| Yeni beklenmeyen HTTP 500 | İleride bir koşuda traceback’i saklanan yeni bir olay açılır. | Gözlenmedi. Bu belge olay açmaz. |
| O olayın yeniden üretilebilirliği | Aynı disposable ortamda aynı istek kimliğiyle tekrar çıkması. Bir kez çıkmak, tekrar üretildi demek değildir. | Yok. |
| Tarihsel S10B-INV-001 ile bağ | Yeni traceback, saklanmış tarihsel istekle aynı kampanya, aynı tur ve aynı yığın ise bağ kurulur. | Tarihsel olayın özgün istek ve traceback’i tek vakaya bağlı değildir. Yeni 500 otomatik olarak INV-001 sayılmaz. |
| Doğrulanmış kök neden | Tekrarlanabilir traceback ve sahip modül. CP1254, kasıtlı save-failure ve proxy drop bu bağın yerine geçmez. | Yok. |
| Doğrulanmış onarım | Kök neden kaydından sonra, aynı reprodüksiyonun artık o hatayı vermemesi ve regresyonun ayrı kanıtı. Üç yeşil deneme, onarım kanıtı değildir. | Yok. |

Korunan prova sınırları, onaydan sonra da şunlardır: boş disposable SQLite, mevcut kampanya save’ine dokunmama, Qwen kapalı ve açık kolların ayrı günlüğü, istek kimliği, tam traceback, kaynak snapshot özeti. Tarihsel logun üzerine yazılmaz. Üç temiz deneme INV-001’i kapatmaz. Bir yeni 500, tarihsel olayı kanıtlamaz. Kabul senaryosunda beklenmeyen 500 çıkarsa ilgili AC, plan v2’ye göre FAIL veya BLOCKED olur.

CP1254 500’ü `regressions-final.log` içindedir ve ayrı olay olarak durur.

## 4. Kapı ayrımı

| Kapı | Zorunlu kaynak | Phase 8 kapanışına etkisi | Kendi kapısı |
|---|---|---|---|
| Phase 8 Expansion kapanışı | Plan v2 AC-001…AC-028 ve repair-v2 FAIL kaydı | AC-027 açık. Kapanış yazılmaz. | Bu belgenin kapsamı |
| F01 bütünlük | Bible v2.3.2 F01-AC-004 manifestosu ve F01-AC-005 üç Neverwinter öznitelik karar kaydı | İthal edilmez. Yoklukları Phase 8 maddesini PASS yapmaz ve kapanış listesine eklenmez. | F01 faz PASS ve F15 başlangıcı |
| F13 araştırma | Bu belgenin bölüm 5 önerisi. Henüz owner onayı yok. | Kapanışın yerine geçmez. | Salt okuma |
| F13 admission / aktivasyon | Ayrı owner imzası. Şu an yok. | Kapanışa ithal edilmez. | Şehirler DISABLED kalır |
| Production release | `gate-ledger.json` `release: NO-GO`. Closeout live-release NO-GO. | Kapanışa ithal edilmez. Yerel kapanış yayını açmaz. | Yayın kapısı |

F15, Bible’da Phase 8 kapanış kaydı ile F01, F03 ve F04 faz PASS’ini ve F12-P01 / F12-P04 manifestolarını birlikte ister. Bir kapının ilerlemesi diğerini tamamlamış sayılmaz.

## 5. Şehir yönü

Owner hedefi, oynanabilir Forgotten Realms şehirlerini güvenli biçimde açmaktır. Bu hedef activasyon izni değildir.

Önerilen salt okuma sırası, owner onayına bağlı olarak **önce Waterdeep, sonra Baldur’s Gate**’tir. İkisi de bugün `INCOMPLETE` ve runtime `DISABLED` (`waterdeep.v1`, `baldurs_gate.v1`) kalır. Kurulu katalog yalnız Neverwinter `VERIFIED_PARTIAL` paketini taşır. `production_authorized` false durur.

F13-RESEARCH, Phase 8 kapanış çalışmasıyla aynı takvimde okunabilir. Okuma extraction ve review boşluğunu tarif eder. Yeni claim, pin, admission, aktivasyon, save göçü veya kampanya canon yazılmaz. Boş claim kümesi admission değildir.

## 6. Owner kararları

1. Bölüm 1’deki zorunlu listenin Phase 8 kapanış kapsamı olarak kabulü. AC-027 FAIL’i listeden çıkarılamaz.
2. Kayıp 165 argv ve test başına döküm varken 296/634 eşdeğerliğinin reddi veya açık kabulü. Bu belge reddeder ve UNVERIFIED bırakır.
3. Bölüm 7’deki disposable AC-027 tekrarının ayrıca yetkilendirilmesi. Yetki, tarihsel FAIL’i silmez.
4. S10B-INV-001’in kapanış önkoşulu olmadığı hükmünün kabulü. Kök neden zorunlu kılınırsa bu, plan v2’nin yeni bir değişikliğidir ve ayrıca yazılır.
5. Waterdeep-önce F13-RESEARCH salt okumasının paralel başlaması. Admission ve aktivasyon bu karara dahil değildir.
6. F01 ve production kapılarının kendi onaylarında kalması.

## 7. Sonraki çalıştırılabilir paket

Paket adı: `P8-AC027-DISPOSABLE-REPLAY`.

Bu belge onu başlatmaz. Önkoşullar:

- Bölüm 6’nın 1, 2 ve 3 numaralı kararları yazılmış olur.
- Komut, saklanmış `lore-boundary-command.json` listesinin aynısıdır. 634 komutu bu paketin yerine geçmez.
- Veritabanı boş disposable SQLite’dır. `ai-dnd/saves/campaigns.sqlite3` açılmaz.
- Lore pinleri, save şeması, şehir bayrakları ve tarihsel loglar yazılmaz.
- Kaynak snapshot ve test dosyası SHA-256’sı yeni kanıt köküne yazılır.
- Çıktı `-q` değildir. Her test kimliği dökülür.
- Tarihi 165 FAIL dosyaları yerinde kalır. Yeni yeşil log, eski FAIL’in silinmesi değildir.
- İnceleyen, komutu yazan kişiden ayrıdır. Aynı kişinin notu bağımsız kabul sayılmaz.
- Exit 0 olsa bile Phase 8 kapanışı bu paketin içinde ilan edilmez. Kapanış ayrı owner kaydıdır.

Paralel ve ayrı paket: `F13-RESEARCH-WATERDEEP`. Yalnız bölüm 6 karar 5’ten sonra, salt okuma. Aktivasyon paketi değildir.

**SON DURUM:** `DRAFT v2 — OWNER REVIEW PENDING`. v1 durur. Kapanış yoktur. PASS yoktur. Eşdeğerlik UNVERIFIED’dır.
