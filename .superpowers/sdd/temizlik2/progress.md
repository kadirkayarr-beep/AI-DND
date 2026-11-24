# Temizlik 2 (2026-11-24) — ledger

Branch task/temizlik-2-20261124, stacked on 5f3fb391. Input: 51 rows round 1 skipped (skipped-round1.json).

## Triage (re-read scan entry + grep evidence, 2026-11-24)

| id | karar | grup | gerekce / kanit |
|---|---|---|---|
| D-499 | LEAVE | - | game.py split slice; tur anlatimi/kayit yolu, bolme isi temizlik degil |
| D-500 | LEAVE | - | yeni olcum kilidi eklemek temizlik degil; game.py split / lock isiyle |
| D-501 | LEAVE | - | para/envanter yazan dev islevleri bolmek tasarim isi |
| D-502 | DO | G4 | authored_dungeon._reply ve bounded_encounter._reply birebir (grep ile goruldu); diger 5 kopya disarida |
| D-504 | LEAVE | - | legacy_sword_move eski kayit degil, yeni oyunda canli dil yolu (places.py:792); genel drop/take esdegerligi kanitlanmali, tasarim isi |
| D-505 | LEAVE | - | 'legacy' eski kayit degil, varsayilan (free_v1 olmayan) kip adi; '' bos env degerinde cokme yaratir; kazanc yok |
| D-507 | DO | G5 | islevler yalniz testlerden cagriliyor (grep); kismen tutulanlar Ruling'de |
| D-508 | DO (kismi) | G1 | yalniz grounded_action F841 x3 (ruff.json:900-902); except daraltma LEAVE: davranis degisir, para yollarinda tek tek analiz ister |
| D-509 | DO (kismi) | G2 | memory_archive yalniz test_roadmap_w08; intent_contract YENIDEN_TASARIM_PLANI B3b'de planli -> tutulur |
| D-510 | DO | G2 | save_migration yalniz ai-dnd/test_save_migration.py import ediyor; eski kayit araci |
| D-514 | DO (kismi) | G5 | yalniz testlerden cagriliyor (grep); tutulanlar Ruling'de |
| D-515 | LEAVE | - | 12 dosyada farkli katlama algoritmalari; ad/iddia eslesmesi davranis riski; karsilastirma korpusu isteyen ayri is |
| D-516 | LEAVE | - | dev islev bolme; living_world (D-517 bolgesi) ve dunya kaydi |
| D-518 | LEAVE | - | initiative legacy_preserved canli uretiliyor (initiative.py:368); monster legacy_* canli; item_transfers:286 plain string D-526 ground_items tasarimina bagli; interaction _defeated status dali icin uretim kanitlanmadi |
| D-519 | DO | G3 | legacy_quests (quest_log.py:112, serializers.py:800), legacy_entry_supports (npc_statements.py:929, dialogue.py:549, turn.py:2601) canli; yalniz ad |
| D-521 | DO | G1 | _SHOP_CREATION_ACTION_PATTERN okuyucusuz (coin.py, game.py:175, whitelist, surface.json, ruff.json:250) |
| D-522 | DO | G1 | analyze_player_action/update_world_state_from_player yalniz test_engine_parts_pilot |
| D-523 | DO (kismi) | G1 | is_dialogue_or_emotion yalniz pilot test; digerleri Ruling ile tutulur |
| D-524 | LEAVE | - | savefile v1/v2'yi kabul ettikce yol canli; D-525 ile birlikte ayri kayit-surumu PR'i (Opus) |
| D-525 | LEAVE | - | 367 satirlik kayit dogrulayicisi; ayri dilim, bagimsiz Opus incelemesi |
| D-526 | LEAVE | - | ground_items alanini kaldirmak 8 okuyucu + kayit; tasarim degisikligi |
| D-527 | DO | G3 | text_rules_a dize dali, dialogue.py dize dali; once kirmizi test (yeni oyun dize yazmiyor) |
| D-532 | LEAVE | - | 10 rota takma adi, 36 test dosyasi, dis cagiricilar dogrulanmadi; genis API isi |
| D-533 | DO | G2 | freeze_* / live_gate / OwnerContinuityRecord yalniz test_lore_1501_integration; aktif plan referansi yok |
| D-536 | LEAVE | - | Ruling: tut (asagida) |
| D-538 | LEAVE | - | D-039 (YUKSEK) yolu; sunucu+istemci birlikte, UI turu ile |
| D-539 | LEAVE | - | 5 dogrulayici farkli (None, strip) ; ortak yardimci bayrak ister, net sadelesme ~10 satir; hata metni riski |
| D-540 | LEAVE | - | baslangic parasi/gunluk dev islevleri bolme; tasarim isi |
| D-541 | DO | G1 | trace_ai_pipeline.py cagiransiz; ruff.json:930-931; pilot test yorumlari D-522 ile giden testlerde |
| D-542 | DO | G2 | director_v2 yalniz test_incident_wave8_9 |
| D-543 | DO | G2 | world_identity yalniz test_roadmap_w10 |
| D-546 | DO | G4 | fighter/monk _apply_three birebir (diff bos); rogue ek satirli |
| D-547 | DO | G4 | world_threads.py:306 yeni thread her zaman pay_basis yaziyor; pay_basis() fallback (199-206) yalniz eski kayit |
| D-548 | LEAVE | - | performans; lru_cache paylasilan sozluk mutasyon denetimi ister, temizlik degil |
| D-549 | LEAVE | - | zar/hasar dev islevleri; kilit ekleme ve bolme ayri dilim |
| D-552 | LEAVE | - | yalniz plan satiri, kod yok |
| D-553 | LEAVE | - | CI adimi; ayri yapilmali |
| D-554 | LEAVE | - | D-387 duzeltmesine ait |
| D-555 | DO (kismi) | G1 | Bolum B (4 test degiskeni + acceptance_test expected_failure) ve _SHOP satiri; Bolum A'nin kalani D-490 kararina |
| D-556 | LEAVE | - | per-file-ignore game.py'de yeni F401'i gizler: ratchet gevsetme |
| D-561 | LEAVE | - | UI turu; bu kosuda TS test yolu yok |
| D-563 | LEAVE | - | UI (level-up-controls) + D-039 ile birlikte; UI turu |
| D-564 | LEAVE | - | UI + openapi tipi; UI turu |
| D-566 | LEAVE | - | kodda is yok; knip/fallow ignore eklemek gelecekteki bulgulari gizler |
| D-567 | LEAVE | - | bilgi bulgusu, kal |
| D-568 | LEAVE | - | paket silme pnpm kilit dosyasi yeniden uretimi ister; bu kosuda kilit dosyasina dokunulmaz |
| D-569 | LEAVE | - | ayni (kilit dosyasi) |
| D-571 | LEAVE | - | UI turu |
| D-575 | LEAVE | - | ayni (kilit dosyasi) |
| D-576 | LEAVE | - | D-039 yolu, D-538 ile birlikte UI turunda |
| D-578 | LEAVE | - | urun karari + yeni karsilastirma testi; UI turu |

## Rulings

- Ruling: D-509 intent_contract.py ve test_roadmap_w09 tutulur, yalniz memory_archive.py silinir — intent_contract YENIDEN_TASARIM_PLANI B3b'de dosya listesinde — yanlissa maliyeti: 136 satir olu kod bir dilim daha kalir.
- Ruling: D-533 dondurma hatti (freeze_review/transform/mapping, live_gate, OwnerContinuityRecord) silinir; test_lore_1501_integration'da yalniz bu modulleri cagiran durumlar silinir, claim_authorization/freeze_eligibility durumlari kalir — aktif plan/ADR'de referans yok — yanlissa maliyeti: git gecmisinden geri getirilir. ruff.json'daki freeze_mapping F841 satiri G1 ile cakismasin diye G2 dokunmaz; G1/G2 birlesince sondaki tek supurmede silinir (ratchet eski satira hata vermez).
- Ruling: D-502/D-546/D-547 done per scan recommendation (merge the two identical _reply copies, use one shared apply_subclass_step, delete the old-save pay_basis fallback) — identical code / owner rule old saves do not matter — cost if wrong: an old save's job without terms.pay_basis shows the per-delivery pay line and a total-split day wage. D-502 only partly closed: the other 5 turn_index/messages copies tracked as D-581.
- Ruling: D-542 director_v2 silinir, test_incident_wave8_9'da yalniz director_v2 durumlari silinir — uretimde baglanti yok, plan yok — yanlissa maliyeti: 75 satir geri getirilir.
- Ruling: D-543 world_identity silinir, test_roadmap_w10'da yalniz world_identity durumlari silinir — uretimde cagri yok — yanlissa maliyeti: 43 satir geri getirilir.
- Ruling: D-541 trace_ai_pipeline.py silinir — cagiran yok, elle arac; sahip kurali olu kodu "sil" — yanlissa maliyeti: git gecmisinden geri getirilir.
- Ruling: D-523 _narration_is_unsafe tutulur (12 test cagrisi canli _narration_safety_decision'i onun uzerinden sinar); register_attack_hook/register_initiative_hook tutulur (tarama onerisi, savas genisletme noktasi) — yanlissa maliyeti: ~10 satir olu kod kalir.
- Ruling: D-507/D-514 tutulanlar: capabilities.register_resolver ve monster_capabilities.register_executor (canli dagitim yolunu sinayan test dikisi), spell_concentration.bless_max_targets (rule-oracles manifestinde engine_resolver), monster_combat.restore_resources (savas kaynagi; dilim sahibi karari olmadan savas testi silinmez). front_proposal.ready_line_share (ve ENGINE_OWNERS) tutulur: bm-once-model tasarimi 5.9/K-BM-5 ve plan Adim 12.4 sonraki oynayisi bununla olcer (G5 fix round 1'de geri getirildi). Diger islevler yalniz testi sadece o islevi sabitliyorsa silinir; test canli bir yolu da kapsiyorsa islev tutulur ve ledger'a yazilir — yanlissa maliyeti: kucuk olu kod kalir ya da geri getirilir.
- Ruling: D-536 compact_receipts/get_turn_action_receipt tutulur — tarama net oneri vermiyor; silmek makbuz testlerini azaltir (yasak), baglamak yeni davranis (temizlik degil) — yanlissa maliyeti: ~130 satir olu kod kalir.
- Ruling: D-524/D-525 eski kayit surumu ve savas gocu silinecek (sahip kurali: eski kayit onemsiz) ama ayri kayit-surumu PR'inda, bagimsiz Opus incelemesiyle — kayit dogrulayicisi en hassas yuzey — yanlissa maliyeti: bir dilim gecikme.
- Ruling: D-568/D-569/D-575 paketler (mockup-sandbox, ai-dnd-web, api-server) kaldirilacak, ama pnpm kilit dosyasini yeniden ureten ayri PR'da — bu kosu kilit dosyasina dokunamaz — yanlissa maliyeti: paketler bir PR daha derlenir.
- Ruling: D-538/D-576 D-039 eski format-3 Wizard yolu kaldirilabilir (eski kayit onemsiz), sunucu ve istemci birlikte UI turunda — D-039 YUKSEK satir, bu kosuda TS test yolu yok — yanlissa maliyeti: dal bir dilim daha kalir.
- Ruling: D-555 Bolum A'dan yalniz _SHOP_CREATION_ACTION_PATTERN (D-521) kalkar; adventure_director, _existing_local_tavern, _filter_unsupported_lore_paragraphs D-490'a, roll_initiative_npc kalir (dinamik yama hedefi) — tarama onerisi — yanlissa maliyeti: 3 whitelist satiri kalir.
- Ruling: D-522/D-523 analyze_player_action, update_world_state_from_player, is_dialogue_or_emotion silinir (yalniz sabitleme testleriyle) — olu-kod-kaniti onerisi "sil", uretimde cagiran yok, sahip onay sorusu istemiyor — yanlissa maliyeti: ~20 satir ve 2 test git gecmisinden geri getirilir.

## Gruplar

- G1 game.py yuzeyi: D-508(F841), D-521, D-522, D-523, D-541, D-555(B) — money_save_undo true (coin.py, test_persistence_idempotency).
- G2 olu moduller: D-509(memory_archive), D-510, D-533, D-542, D-543 — money_save_undo true (save_migration).
- G3 NPC bellek eski dali + adlar: D-519, D-527 — false.
- G4 kopya birlestirme + pay_basis: D-502, D-546, D-547 — true (turn_index/Undo, karakter durumu, ucret).
- G5 yalniz-test olu islevler: D-507, D-514 — true (action_economy, shop_trade).
- Ortak belgeler (debt-register durum hucreleri, onay-listesi bolum 27, bu ledger) gruplar degil orkestrator tarafindan yazilir.
- G1 RESULT: slot 9 label g1fix: exit=0, Ran 359 tests (test_engine_parts_pilot, 4 engine locks, 4 journey modules); ruff ratchet=0; vulture=0.
- G1 fix round 1: the two deleted is_dialogue_or_emotion asserts rewritten against live is_npc_dialogue_input; onay-listesi section 27 added (3 test changes, gevsetme olabilir).
- G2 RESULT: slot 9 label g2fix: exit=0, Ran 192 tests (lore_1501_integration, admission_boundary, roadmap_w08/w10, incident_wave8_9, 4 journey modules); independent g2rev exit=0, 188 tests; ruff ratchet=0; vulture=0.
- G2 fix round 1: onay-listesi section 27 has 16 G2 rows (gevsetme olabilir); tautological assert removed from test_staged_fact_cannot_become_player_knowledge; D-580 park row for orphaned admit_public_batch/projection_is_transform_ready.
- G2 fix round 2: freeze_mapping F841 satiri ruff.json'dan silindi (G1+G2 bu dalda birlesik; supurme yapildi). Ratchet + vulture exit 0.

## G3 fix 1
Fixed: campaign_validation no longer accepts plain-string NPC memory entries (red test SaveValidationRejectsStringMemory in test_npc_memory_dict_only; stricter, no check reduced). Ran 382 tests green + ruff ratchet + vulture exit 0.
Ruling: no new debt row - branch removed instead - new games write dicts only, old saves do not matter - cost if wrong: an old save with string memory is rejected at load.
- G4 RESULT: slot 9 label g4fix: exit=0, Ran 379 tests (test_temizlik2_dedupe, test_world_threads, test_thread_hiring, test_thread_errand, 4 journey modules, 4 engine locks); ruff ratchet=0; vulture=0. Reviewer proofs g4rev (145 tests) and g4rev2 (178 tests) exit=0.
- G4 fix round 1: onay-listesi section 27 row added for test_pay_basis_of_an_old_save_comes_from_its_kind -> test_pay_basis_is_only_the_stored_one (gevsetme olabilir).
- G5 fix round 1: ready_line_share, ENGINE_OWNERS and the 5 ReadyLineShare tests restored (Ruling above rewritten: kept for the pending K-BM-5 play measurement; cost if wrong: about 15 dead lines). onay-listesi section 27 has the G5 rows (gevsetme olabilir). Park D-582 (action_economy 'magic' Ready validator and spell_mechanic_unavailable branch now unreachable).
- G5 RESULT: slot 9 label g5fix2: exit=0, Ran 472 tests (touched modules, front_proposal, interaction_adventure, 4 journey modules, 4 engine locks); ruff ratchet=0; vulture=0.

## Closing gate (round 2)
- RESULT slot 4 label t2-off (default flag, 3 shards, tree 59c98aba): tests 11298 skipped 183 failing_ids 1 PAR_EXIT=1; failing: api.tests.test_game_name.ProtectedIdsTests.test_env_variable_name_set_is_unchanged (36 != 37; AI_DND_PHASE8_LIVE_AUTHORIZED left with live_gate.py in G2).
- Fix: PROTECTED_ENV_NAME_COUNT 37 -> 36, onay-listesi section 27 row (gevsetme olabilir). Slot 9 t2envfix exit=0, Ran 182 tests (test_game_name + 4 journey modules).
- RESULT slot 4 label t2-fon (fon flag, 3 shards, after fix): tests 11298 skipped 181 failing_ids 0 PAR_EXIT=0.
- Quality gate: ruff ratchet exit 0; vulture exit 0.
- Ruling: default-flag full suite not rerun after the one-line count fix — only failure was that pin, targeted run green, fon full run on the fixed tree green — cost if wrong: a flag-off-only failure shows in CI.
