# AI-DND — Stage 10B Lore Integrity Repair / Final Acceptance

Tarih: 2026-10-09. Kapsam, owner’ın onayladığı Castle Ward bayt geri yüklemesi ve `OwnerContinuityRecord` onarımıdır. Dondurulmuş Stage 10B v2 kabul metni değiştirilmedi. Bu belge bütün repository, production, merge veya şehir aktivasyonu onayı değildir.

HEAD: `f63d952506064cd59e960f1e3efa6627d4e52053`. Branch: `phase8/emergent-storytelling-expansion`. Checkout: `C:\Users\Kadir\Desktop\AI-DND-phase8-expansion`. Commit, push, merge, reset, clean veya stash yapılmadı. Eski handoff’lar ve eski kanıt kökleri duruyor.

Yeni kanıt kökü: `.local/evidence/stage10b-lore-integrity-20261009-1805/`.
Önceki FAIL kökü: `.local/evidence/stage10b-acceptance-v1-20261009/`.
Önceki onarım kökü: `.local/evidence/stage10b-repair-v2-20261009-085201/`.

## Belge geri yükleme

Aday, mevcut dosyanın yalnız LF satır sonlarını CRLF yaparak bellek içinde üretildi. BOM yoktu. Başka bayt değişmedi. Aday SHA-256 pinle birebir eşleşince yazıldı.

| Sürüm | SHA-256 | Bayt |
| --- | --- | --- |
| LF yedek | `d8accdf67802838b6e019cd8b05a75c781fc5a4837c14bbeb0d15c29c2d420da` | 2500 |
| Geri yüklenen CRLF | `be4b2f8a399103537f93fc33cfebe47524bd811a6fb232b577b480a087895d8a` | 2544 |

Yedek: `Owner_Decision_Castle_Ward_1501.lf-backup.md`. Admission pinleri ve test digest’leri değiştirilmedi. `load_freeze_evidence()` integrity hatası vermiyor; public küme 95. Sahte pin testi `test_hash_pin_mismatch_admits_nothing` hâlâ hiçbir kayıt kabul etmiyor.

Onay cümlesi aynı kaldı: Castle Ward, 1501 DR’de Waterdeep’in bir bölgesi olarak var olmaya devam eder. Bu cümle 2025 kaynak fact’i değildir, pakete yüklenmez ve oyuncuya verilmez.

## pack_index satır sonu

Integration testi, Neverwinter `pack_index.json` için korunan `3ba99717976aa25f154fdd97cc4ce6e5e7d5bf59bd175bc037cd7c537ebcacd5` özetini bekliyordu. Diskteki LF kopya `db3ee679accc0d219a4aa34104cf6e2b351612ba6f9bab34fc31d0574dbd00b4` (637 bayt) idi. CRLF adayı pinle eşleşti; JSON metni değişmedi. LF yedek `pack_index.lf-backup.json`. Diğer üç Neverwinter dosyası zaten pinli CRLF baytlarındaydı ve değiştirilmedi. Şehirler DISABLED kaldı.

## OwnerContinuityRecord

`api/lore_authority/models.py` içinde gerçek bir frozen kayıt. Alanlar: `decision_id`, `provenance_kind`, `approved_statement`, `subject`, `predicate`, `year`, `scope`, `decision_document_digest`.

- `provenance_kind` yalnız `OWNER_APPROVED_CONTINUITY` olabilir.
- Yıl tamsayı ve 0–9999 aralığındadır. Digest 64 küçük harf hex olmak zorundadır.
- `runtime_enabled` ve `official_source_fact` alan değil, her zaman `False` dönen property’dir.
- `SourceTier.OWNER_APPROVED_CONTINUITY.rank` ValueError vermeye devam eder.
- `SourceManifest.from_mapping` ve pack ingestion bu tier’ı reddetmeye devam eder.
- Kayıt oluşturmak kampanya canon’u, oyuncu bilgisi veya anlatı izni yazmaz.

## Retrieval sınırı

Kirli `registry.py` içinde `_freeze_scope_required` çağrılıyor, fonksiyon yoktu ve `fact_is_current` çöküyordu. Fonksiyon eklendi: temporal scope boşsa ve fact id pinli V2.2 kümesinin tam üyesiyse kayıt current sayılmaz. Küme dışındaki kayıtlara önek kuralı uygulanmaz. Evidence yüklenemezse küme boş kalır.

Ayrıca public paket yolu, restricted id’yi `COMMON_KNOWLEDGE` diye saklasa da düşürür. `WD22-F-015` değeri, hariç tutulan Castle Ward çıkarım cümlesini içeriyorsa pakete girmez. İzinli ward listesi bu cümleyi içermediği için durur. Yeni fact veya pack içeriği yazılmadı.

## Kaynak özetleri

| Dosya | SHA-256 |
| --- | --- |
| `models.py` | `3da765cb319d48b863b3645bce3c3f1f51f45e4e618f463e22fdda06315c63d6` |
| `registry.py` | `fc9a47e681c01e1ecc945265d7f85522a19e8685720b4812a36607cde3adc384` |
| `freeze_admission.py` | `a83a70c7faca62ca6cabd8da41ca380c7c2c05e9339ac232468b74b9bbacd53a` |
| Castle Ward belgesi | `be4b2f8a399103537f93fc33cfebe47524bd811a6fb232b577b480a087895d8a` |
| `pack_index.json` | `3ba99717976aa25f154fdd97cc4ce6e5e7d5bf59bd175bc037cd7c537ebcacd5` |

Git durumu: `models.py` ve `registry.py` modified. `freeze_admission.py` ve Castle Ward belgesi önceden untracked. Commit yok.

## Koşular

Eski 165 komutunun kendisi kanıt klasöründe yoktu. Eski logun çalıştırdığı lore, API, persistence ve exploration modüllerinin tamamı yeni süitte koştu. Sayı 165 değil, çünkü import hatası kalkınca integration testleri gerçekten çalıştı ve süit tam modülleri aldı.

| Kayıt | Sonuç |
| --- | --- |
| lore-boundary-persistence-weather | 296 test, 147.870 s, exit 0 |
| regressions-required | 634 test, 243.298 s, exit 0 |

634 komutu, önceki `regressions-final-command.json` seçicilerinin aynısıdır. Save sürümleri testte duruyor: lore payload 2, campaign format 1, SQLite şema 5, game save 3. Waterdeep ve Baldur’s Gate DISABLED. `production_authorized` false.

## Kabul

AC-001–AC-026 ve AC-028, önceki repair-v2 tarayıcı, birleşik kampanya ve canlı Qwen kanıtıyla duruyor. Bu onarım o yüzeylerin kodunu değiştirmedi. Neverwinter hükümdar sorgusu yeni integration testinde aynı fact id ile geçti. AC-027, yeni 296 ve 634 koşuları yeşil olduğu için PASS. S10B-INV-001 tarihsel HTTP 500 olarak UNCONFIRMED kalır.

Stage 10B yerel kabulü bu kanıtla PASS’tir. Bütün repository sertifikası, production, merge veya şehir açılışı değildir.

## Kalan risk

- `pack_index.json` Git blob’u LF olabilir; çalışma kopyası pinli CRLF’dir. Autocrlf yeniden yazarsa pin yine kayar. Ham bayt yedeği kanıt kökündedir.
- Canlı tarayıcı ve 20 turluk smoke bu turda yeniden koşulmadı. Önceki kanıt, bu diff’in değmediği yüzeyler içindir.
- Freeze adayı hâlâ `FREEZE_CANDIDATE_NOT_APPROVED` ve yüklenmez.
