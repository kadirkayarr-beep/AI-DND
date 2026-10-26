# Oturum devri — B03 (2026-10-26)

Ürün kanıtı değildir; kısa devir kaydıdır. Özet tek başına uygulama talimatı değildir. Önceki kayıtlar: `session-handoff-B01.md`, `session-handoff-B02.md`.

- **Yetki:** "başla" VAR. Aday kökü `C:\Users\Kadir\Desktop\AI-DND-b01-isolated` (dal `task/b01-source-identity-20261026`, kaynak `78b380384e70832156d2d9aa2785192bbbbdb74b`). Yasak: commit/push/merge, main, kurulum, kişisel kayıt, sırlar, 8008, yayın; toplu silme, `git clean`/`reset`, paket kaldırma yok. Kullanıcı ek olarak izole testleri onaysız koşmaya izin verdi.
- **Görev:** B03. Bağımlılık B02 (ACCEPTED). Kritik yol: tekil bağımsız inceleme.
- **Durum:** ACCEPTED. Bağımsız inceleme iki turda: KOŞULLU ONAY (M1-M5) → ONAYLA. Kalan düşük notlar aşağıda.
- **Okunan bağlam:** plan 01 satır 1-40 ve 93-117; `01_Ortak_Sozlesmeler_ve_Kapilar.md`; tasarım §16.5, §16.7, §18.6, ANL 01/02, BIL 01/02, S12, S15, A17; `QG-1_5_Hibrit_Inceleme.md`. `integration-obligations.json` içinde B01-B03 kaydı yok.

## Ölçülen sonuç (eski rapordaki sayı varsayım olarak kullanılmadı)
- Koşu: `python ai-dnd/scripts/run_regression_evidence.py api.tests.test_campaign_api api.tests.test_default_npc_targeting api.tests.test_stability_repairs` (cwd = çalışma kopyası kökü, `run_isolated.py` ile). Python 3.14.2, Windows. İki bağımsız koşu: 186 yöntem seçildi/çalıştı, 175 PASS, 11 FAIL, 13 başarısız olay, aynı 11 yöntem ve aynı imzalar.
- Yedi profil testinin kimliği (hepsi `api.tests.test_campaign_api.CampaignApiTests`): `test_conversation_proposal_rejection_and_valid_unknown_are_distinct` (3 olay), `test_free_http_profile_purpose_is_owned_by_personal_topic`, `test_free_npc_profile_statement_uses_shared_resolution_without_forced_target`, `test_missing_conversation_fields_reject_without_retry_or_focus_change`, `test_model_owned_personal_purpose_phrasings_do_not_need_lexical_gate`, `test_npc_occupation_and_origin_share_validated_profile_resolution`, `test_profile_why_does_not_bypass_unverified_lore_safety`. Diğer dört: D4 (`test_default_npc_targeting`), iki hükümdar ve Bardak yöntemi (`test_stability_repairs`).
- Ebeveyn commit `83c6ebd^` = `cb40a59a6cbb6f331f41732dfb88c28e98a37c1c`: aynı üç modülde 35 yöntem başarısız (taban temiz değil); 26'sı 83c6ebd ile onarılmış; HEAD'de yeni olan 2 yöntem.
- Ayırıcı deney (bellekte, repo/beklenti DEĞİŞMEDEN): HEAD ürünü + HEAD testleri + double'ın ebeveyn sürümü → 7 profil yönteminde 9 olay 4'e indi. 3 yöntem tamamen düzeldi (`CONFIRMED_BY_DIAGNOSTIC`, `test_fixture_double`, W02): rejection_and_valid_unknown (2 yeni kırılandan biri), missing_conversation_fields (diğer yeni kırılan), free_http_profile_purpose. 4 yöntem eski double ile de aynı imzayla düşüyor (`PREEXISTING_NOT_DOUBLE`, `unresolved`): free_npc_profile_statement, model_owned_personal_purpose, occupation_and_origin, profile_why. D4, iki hükümdar, Bardak: yeniden üretildi, neden bağımsız doğrulanmadı (`REPRODUCED_CAUSE_NOT_VERIFIED`, `unresolved`, planın hipotezi `plan_cause_class`'ta).
- **Plan iddiası:** "7 profil yöntemi/9 assertion ortak schema-double nedeni" ölçümle yalnız 3 yöntem/5 olay için doğrulandı. `triage_status = PLAN_CLASS_PARTIALLY_CONFIRMED`; yöntem dağılımı 3 CONFIRMED / 4 PREEXISTING_NOT_DOUBLE / 4 REPRODUCED_CAUSE_NOT_VERIFIED. Plan assertion'ları (11/13/7/9) `plan_cause_class` gruplaması üzerinden sınanıyor; ölçülen kanıt durumu ayrıca sabit.
- Yan bulgu (W03'e): D4 fixture'ı rastgele han adı üretiyor (üç koşuda Nuri, Tamsin, Lidda); imza karşılaştırmasında `<Ad> Hanı` maskelenir.
- Mekanizma izi: ortak double (`CapturingConversationContextClient`, test_campaign_api.py) `spoken_text` rotasında `last_profile_field` güncellemiyor, kuyruktaki sınıflandırıcı cevaplarını tüketmiyor. Double'ın `spoken_text` rotası 83c6ebd'de eklenmiş (aynı commit `ai-dnd/game.py` +128 satır da değiştirmiş).

## Yalıtım kanıtı
- `run_isolated.py`: izin listesinden temiz ortam (jeton yok, kullanıcı kabuğundaki `AI_DND_*` taşınmadı), yeni koşu dizininde ayrı DB/ev/TEMP, `AI_DND_DISABLE_DEFAULT_APP=1`. Koruma v1: dış ağ, 127.0.0.1:8008, ana checkout, diğer worktree'ler, `.env`. Koruma v2: ayrıca 11434, `sqlite3.connect`, `os.listdir/scandir`; `subprocess.Popen` yalnız kayıt. Sonda (probe2) 8/8 engel doğrulandı.
- Tüm gerçek koşularda `guard_blocked_events=[]`, `campaign_db_created=false`, `tracked_diff_empty=true`, `worktree_status_new_lines=[]`. Kanıt: `docs/acceptance/evidence/b03-diagnostics/proofs/*.proof.json`.

## Değişiklik (rollback = bu yeni dosyaları silmek; tümü izlenmeyen, izlenen dosyada fark yok)
`tools/acceptance/failure_contract.py`, `ai-dnd/api/tests/test_roadmap_b03.py` (10 test), `docs/acceptance/failure-contracts.json`, `docs/acceptance/evidence/` (b03-anchors-78b3803, b03-anchors-78b3803-v2, b03-parent-cb40a59, b03-diagnostics, b03-triage-history; toplam yaklaşık 4 MB), bu kayıt.

## Test kanıtı
- FAIL: `python -m unittest api.tests.test_roadmap_b03` önce `ModuleNotFoundError: failure_contract`, ikinci sürümde retained v2 kanıtı yok (`FileNotFoundError`) ve eksik arayüzler; ürün karşı örneği değil.
- PASS: B03 10 test OK. B01+B02+B03+preflight (`test_definition_preflight_checks test_definition_preflight`) izole ortamda 73 test OK.
- Mutasyon: B03 owner'ında 13 mutasyon testi kırdı (biri ilk turda hayatta kaldı → atıfsız `approved_behavior` ve "bilinmeyen ama metinde geçen atıf" durumları eklendi), her seferinde hash geri yüklendi.
- Lint UNCONFIGURED. UI/Node NOT_RUN.

## Açık sınırlar
1. **Denetim ledger'ı yoktu.** "Denetim ledger'ı ile birebir ID eşliği" taze koşulara göre kuruldu; plan maddesi harfiyen karşılanmadı, ölçümle ikame edildi.
2. D4, iki hükümdar ve Bardak yöntemlerinin nedeni bağımsız doğrulanmadı; dört profil yöntemi (`PREEXISTING_NOT_DOUBLE`) için gerçek neden (ürün mü sözleşme mi) çözülmedi — sahipler W02-W05.
3. `test_fixture_double` yalnız "ebeveynin double'ı ile geçiyor" demektir; yeni double'ın daha sadık olup bir ürün kusurunu açığa çıkarmadığı kanıtlanmadı (`double_change_sufficient` alanı bunu doğru söyler; N4).
4. N1: `<Sözcük> Hanı` maskesi her han adını gizler (şu an yalnız D4'te etkili). N2: imza 120 karakterde kesiliyor (mevcut veride sonucu değiştirmiyor). N3: `verify_retained_files` yol normalizasyonu yok ve dizindeki fazladan dosyayı yakalamaz. Düzeltmek onaylı sürümü değiştireceğinden yapılmadı.
5. Tutulan kanıtta `C:\Users\Kadir\...` ve oturum kimliği içeren yollar var (sır/jeton/e-posta yok). Dosyalar izlenmeyen ve commit edilmedi; paylaşılan dala girmeden önce kullanıcı kararı gerekir (normalize etmek hash'leri değiştirir).
6. Koruma v2 `subprocess.Popen` içeriğini yakalamıyor (10 kayıt, koşucunun kendi `git` çağrılarıyla tutarlı, kanıtlanmadı). Koruma "ağ (loopback hariç) + 8008 + 11434 + `.env` + kişisel yol okuma" kapsar; `ctypes`/`subprocess` içeriği kapsam dışı.
7. Retained kaynak ağacı: HEAD + yalnız izlenmeyen B01-B03 dosyaları; çalışan runtime SHA UNKNOWN.
8. Ebeveyn karşılaştırması `cb40a59`'da koruma v1 ile yapıldı (v2 değil).

## Geri dönüş / temizlik
Ebeveyn karşılaştırması için geçici ayrı worktree `C:\Users\Kadir\Desktop\AI-DND-b03-parent` açıldı; yalnız o worktree `git worktree remove` ile kaldırılacak (başka worktree, dal ve stash'lere dokunulmaz). Scratchpad araçları (`b03_iso\`) repo dışı; betik kopyaları ve digest'leri retained kanıtta.

## Sonraki hazır iş
B04 (bağımlılık B03). B04 tam PHB kaynak ve kabiliyet manifestini ister; PHB kaynak metnine/haklarına erişim ve izin gerektirir. Başlamadan önce kaynak erişimi ve haklar kullanıcıyla doğrulanır.

## Başarı iddiası sınırı
Doğrulanan: B03 testi, taze iki izole koşu, ebeveyn karşılaştırması, double değiş-tokuş deneyi, yakın regresyonlar. Yalnız planlanan: W02-W05 düzeltmeleri, kalan sekiz yöntemin gerçek nedeni, tam suite, P0/P6, gerçek browser–API–kimlik–model zinciri.
