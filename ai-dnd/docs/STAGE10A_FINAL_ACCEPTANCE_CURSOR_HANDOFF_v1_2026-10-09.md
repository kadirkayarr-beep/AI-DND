# Stage 10A final local acceptance — Cursor handoff v1

9 Ekim 2026, Europe/Istanbul. Kullanıcının bu görevde verdiği açık, sınırlı uygulama onayıyla çalışıldı.

## Karar ve sınır

**Doğrulanan Stage 10A yerel senaryoları PASS. Özgün Stage 10A sözleşmesinin tüm maddeleri için sertifika VERİLMEDİ. Stage 10B BLOCKED; Replit/production NO-GO.**

Belgesel engel: özgün Stage 10A kabul listesinin tam metni erişilebilir kaynaklarda bulunamadı. Referans sohbet `6ac7fef2-d5d4-83ed-8fd7-15520e9c8e48` içindeki assistant cevapları yalnızca `chatgpt-content-reference` placeholder'ları olarak döndü. Önceki Codex sohbetindeki shop repair kullanıcı sözleşmesi, dört kronolojik handoff, mevcut smoke assertion'ları ve bu görevin açık kabul kapsamı incelendi. Bunlar yerel kontrol listesini destekler; görünmeyen özgün listenin tamamını temsil ettiği varsayılmadı. Tam özgün listeyle madde eşleştirmesi yapılmadan genel Stage 10A sertifikası veya Stage 10B açılışı çıkarılmamalı.

Bu engel Qwen combat prose eksikliği değildir. `.agents/memory/combat-lifecycle-boundaries.md` mevcut Python result renderer'ının korunmasını açıkça ister. `game.py::_combat_narration` model çağrısı yapmadan resolved sonuçları anlatır; attack yolu final sonuç verir ve narration safety exact Python metninden sapmayı reddeder. Qwen anlatıcısı eklemek yeni committed narration fazı gerektirir ve mevcut görevin dışında kalır. Kabul için sırf model çağrısı üretmek gerekmez; combat'ta 0 çağrı geçerlidir. Kampanyaya yalnızca açık oyuncu seçimiyle giren mevcut authored courtyard kabul senaryosudur; küresel Neverwinter düşmanı veya resmî lore olayı değildir.

## İş çakışması ve checkout

Başlangıçta `list_threads`, önceki sohbetler ve yerel Python süreçleri okundu. `Napraw Stage 10A AI-DND` (`01a11dae-6258-7aa3-a943-4a472ef24864`) completed/idle idi. Görünür Codex listesinde bu görev dışında örtüşen aktif Codex işi yoktu; çalışan Python test/API süreci görülmedi. Önceki combat gate çıktısı ve handoff'u tamamlanmıştı. Bu gözlem görünmeyen harici Cursor oturumlarını kanıtlamaz.

Checkout: `C:\Users\Kadir\Desktop\AI-DND-phase8-expansion`.
Branch: `phase8/emergent-storytelling-expansion`.
Başlangıç ve son HEAD: `f63d952506064cd59e960f1e3efa6627d4e52053`.
Dirty tree korundu. Commit/push/merge/force push/reset/clean/stash/checkout yapılmadı. Production DB/save/deploy, schema, şehir aktivasyonu veya Phase9 işlemi yapılmadı. Synced `sources/` salt okunur tutuldu.

Kronolojik geçmiş: shop repair → gameplay repair → narration intent repair v1 → live combat gate. Hiçbir eski handoff, transcript veya test sonucu yeniden yazılmadı. Önceki combat gate'deki Qwen prose engeli bu raporda mimari gerekçeyle değerlendirilir; eski rapor tarihsel kanıt olarak korunur.

## Dar değişiklikler

- `bounded_encounter.py`: giriş cümlesi canonical gizli adı yerine mevcut `public_npc_name` etiketini kullanır. Kaydedilen NPC kimliği/rolü değişmez. Başlangıçtaki “Python tarafından” ifadesi oyuncuya uygun inisiyatif cümlesine çevrildi.
- Aynı owner'da `visible_dash_narration`: yalnızca gerçek resolved `dash`, aynı görünür NPC ID'si ve public projection'daki integer mesafe için cümle üretir. Gizli/görünmeyen veya farklı actor için sessizdir. Yön, yol, ek saldırı veya hasar uydurmaz; state/RNG değiştirmez. Enemy-first initiative durumunda başlangıç cümlesi de aynı yardımcıyı kullanır.
- `game.py`: mevcut combat renderer yalnızca resolved Dash cümlesini owner yardımcısından ekler. Attack exact narration gate, no retry, model call budget ve deterministic ownership korunur.
- `test_bounded_encounter.py`: gerçek authored encounter ve gerçek movement/action budget testine görünür mesafe anlatımı kontrolü eklendi; yanlış actor/non-Dash/gizli NPC ve rendering sırasında state/RNG değişmeme kontrolü eklendi. Önceki assertion'lar kaldırılmadı.

| Dosya | Son SHA-256 |
|---|---|
| `ai-dnd/game.py` | `5bdd827d4299ea4f829f1b80cf3315be7ff758e94b56c184c29746cc3dafdb32` |
| `ai-dnd/bounded_encounter.py` | `74cbfb10c8c1d3a85dca1abe0a5b73027ead7845573b3fb067b4bb4371bd9ae2` |
| `ai-dnd/api/tests/test_bounded_encounter.py` | `248056273d03a90be92a2d7cd490900b6658545339b100ddd74827480bd3e58f` |
| `ai-dnd/shop_creation.py` — değişmedi | `3f86af37ecc79bc870c2d8c3f0e6188c8eea404cfb6f61a31f2d94b8c3779c6d` |
| `live_neverwinter_canon_smoke.py` — değişmedi | `62eadaaa18ceb1ec01fd52860cf25b95b157ad2bac200623a0f447f2235304b7` |
| `live_neverwinter_combat_gate.py` — değişmedi | `c6cd854bbe798a7eefb3a29a1aebe4a280d58e98bb8eee81d09df53a8f5fda54` |

365 mevcut kaynak dosyasının başlangıç/son hash karşılaştırmasında yalnızca yukarıdaki üç existing source değişti; 362 aynı kaldı. Tarama `.py/.json/.md` ve belirtilen dışlamalarla sınırlıdır; bütün disk/repository byte audit değildir. Pack/profile hash snapshot'ı ayrıca saklandı. Shop owner, lore packs, smoke harness ve önceki lore/persistence değişikliklerine müdahale edilmedi.

## Kabul matrisi

| Kontrol | Sonuç | Kanıt / sınır |
|---|---|---|
| 20 tur + gerçek FastAPI restart | PASS yerel | `live-smoke.json`, exit 0; full saved state equality assertion korundu |
| Manuel 20 tur anlatım | PASS senaryo | `manual-review-and-verification.json`; her tur için cümle/not |
| Investigation | PASS | Gerçek 19/DC15 success; başarıya uygun grounded fallback |
| Shop creation/search/refusal/economy | PASS | Stable shop/keeper; Find existing; ürün/fiyat/quest icadı yok |
| Unknown Elara / Arven | PASS | Elara reddi; aynı stable keeper restart sonrası Arven recall; isolation assertions |
| Lore grounding | PASS bounded | Turns1–5 mevcut facts; turns6/8 unknown refusal; önceki handoff source review korunur, kitaplar bu işte yeniden bağımsız doğrulanmadı |
| Atmosfer | PASS bounded | Turns15/17 spill/ring search public Python BLUE events/referents; model kampanya olayı yaratmadı |
| Authored live combat | PASS yerel | Opt-in Commoner, `mm2024.commoner`, printed p.77/PDF p.80; injected hostile/seed/route yok |
| Initiative / Dash / action economy | PASS | Order player→npc_001; gerçek 60→5ft; movement_used55, dash_count1, round2 player turn |
| Gerçek zar / hasar / HP | PASS | Tek player roll9, 7 hasar, NPC4→0, player12; alias tekrarları ikinci saldırı değildir |
| Combat restart | PASS bu run | NPC0, player12, combat inactive resume ile aynı; active resume önceki run'da kanıtlı, yeni run için iddia edilmez |
| Combat isolation/rewards | PASS | İkinci kampanya courtyard/combat almadı; XP/inventory/currency/quest değişmedi |
| Max2 calls / no narration retry | PASS | Smoke toplam4/max2; combat bütün turlar0; trace/count ve post-gate kontrolleri |
| İlgili regresyon | PASS | 401 tests, 8.919s, exit0; bütün repository değildir |
| Özgün Stage10A tam liste eşleştirmesi | BLOCKED belge | Tam özgün sözleşme metni erişilemedi |
| Replit runtime / production | NOT RUN / NO-GO | Local Windows/Ollama kanıtı yerine geçmez |
| Stage10B | BLOCKED | Otomatik açılmadı; final original-contract certification yok |

Yeni combat ID `302305dd-8ae6-40b3-9cd4-49d679d0be21`. Dört cümle public state ile elle eşleştirildi. Attack runner aynı roll'u recursive compatibility alias'lardan iki kez topluyor; bu raporda iki zar veya iki saldırı sayılmadı. Bu observation defect değiştirilmedi, assertion gevşetilmedi.

## Komutlar ve gerçek sonuçlar

Working directory `ai-dnd`; process-local `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`. Live için `OLLAMA_HOST=http://127.0.0.1:11434`, model `qwen3:8b`; API ayrı port/geçici SQLite kullandı. Smoke evidence env yeni dizine yönlendirildi. Reddedilen narration içinde tekrar çağrı yapılmadı.

```text
python -m unittest api.tests.test_bounded_encounter api.tests.test_combat_lifecycle api.tests.test_monster_combat api.tests.test_monster_hardening api.tests.test_stage10a_narration_intent api.tests.test_stage10a_gameplay_repairs api.tests.test_explicit_shop_creation api.tests.test_live_neverwinter_smoke_diagnostics test_shops api.tests.test_lore_engine_integration test_narrative_safety_calibration test_checkpoint_blockers test_playable_living_world test_narrative_rebalance api.tests.test_living_world_v2_foundation api.tests.test_narrative_memory api.tests.test_narrative_director -q
python -m api.tests.live_neverwinter_canon_smoke
python -c "from pathlib import Path; from api.tests import live_neverwinter_combat_gate as gate; gate.EVIDENCE=Path('../.local/evidence/stage10a-final-acceptance-v1-20261009/combat'); raise SystemExit(gate.main())"
```

Üç komut exit0. `regressions.log`, `live-smoke.json`/stderr, `combat.stdout.json`/stderr ve ayrı `.exit.txt` dosyaları saklandı. Regresyonlarda intentional autosave-failure negatif test ERROR logları vardır; suite sonucu OK. `git diff --check` exit0; satırsonu uyarıları logda korundu. `verify_evidence.py` exit0: call traces, resume HP/active match, BLUE texture, exact changed-file set, unchanged HEAD; bu transcript doğrulamasıdır, ikinci bir gameplay test suite değildir.

## Kanıt ve Cursor devamı

Yeni evidence root: `C:\Users\Kadir\Desktop\AI-DND-phase8-expansion\.local\evidence\stage10a-final-acceptance-v1-20261009`.

Başlangıç dirty patch/status/hash'leri, üç source before kopyası, final status/hash'leri, fresh raw transcripts, API logları, exit codes, manuel JSON review ve source-only patch burada. Evidence hashes ayrı manifestte. Raw smoke/combat status hâlâ `MECHANICAL_PASS_NEEDS_MANUAL_NARRATION_REVIEW`; manuel kararı ayrı dosyada, raw transcript değiştirilmedi.

Cursor aynı expansion checkout'ta review yapmalı. Shop creation/routing, lore admission, save/schema veya engine sahipliğini yeniden uygulama. Yeni combat narrator/model call fazı ekleme. Existing dirty-before/final whole diff önceden var olan işleri de içerir: ters patch/reset/restore olarak kullanma. Recovery gerekirse yalnızca `before` dosyaları ve session-only patch ile bu üç dar farkı incele; daha yeni başka işleri ezme. Önceki handoff/evidence dizinlerini koru.

Tek kalan sertifikasyon engeli özgün Stage10A listesinin tam metniyle kapsam eşleştirmesidir. Yerel PASS, Replit doğrulaması, production onayı veya whole-repository PASS anlamına gelmez. Önceden raporlanan kapsam dışı eski test sorunları bu işte çözüldü diye sunulmamalı.
