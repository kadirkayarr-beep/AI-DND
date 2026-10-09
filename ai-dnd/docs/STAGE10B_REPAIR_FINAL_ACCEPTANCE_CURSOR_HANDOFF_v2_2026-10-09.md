# AI-DND Stage 10B — Repair / Final Acceptance / Cursor Handoff v2

Tarih: 2026-10-09. **Final kabul: FAIL; kapanış yazılmadı.** Kapsam içi oyun onarımları uygulandı. Son zorunlu seçiciler + 10A + API/save/weather koşusu **634 test / 632 farklı test kimliği, 200.728 saniye, exit 0**. Ek lore doğrulaması **165 testte 4 failure + 14 error, exit 1**; korunan kaynak/pin ve lore model sözleşmesi engelleri açık. PASS belgesi değildir.

## Çalışma alanı ve sınırlar

Checkout: `C:/Users/Kadir/Desktop/AI-DND-phase8-expansion`; branch `phase8/emergent-storytelling-expansion`; HEAD `f63d952506064cd59e960f1e3efa6627d4e52053`. Başlangıçta çok kirliydi ve hâlâ kirli. `git-status-before.txt` / `git-status-final.txt` içerir. Tüm Git diff bu oturuma mal edilmemelidir. Başka aktif yazar görülmedi; alt ajan çalıştırılmadı. Commit/push/merge/reset/clean/stash/restore yapılmadı. Replit veya production DB kullanılmadı. Frontend kaynakları bu onarımda değiştirilmedi.

Dondurulmuş v2 sözleşmesi SHA256: `4c0ebe1d023c249af941e637c221e67ee827595796f5bca09cb563bef2819286`. Asıl 28 madde değiştirilmedi; summary.json özgün satırları da içerir. Stage10A tarihsel kapanışı ve eski 10B FAIL kanıtları korunur; eski kapanış bugünkü dirty source ile eşdeğer sayılmaz.

Yeni kanıt kökü: `.local/evidence/stage10b-repair-v2-20261009-085201/`. Eski kırmızı kök: `.local/evidence/stage10b-acceptance-v1-20261009/`. Eski 401/8.919s kaydı geçerli tarihsel kayıttır, tüm suite değildir. Yeni kayıtlardaki yollar aksi yazılmadıkça yeni köke göredir.

## Uygulanan değişiklikler

- `game.py`: `_explicit_campaign_shop_request` arama ile açık yaratımı ayırır; `resolve_npc_reference` ve `_run_player_turn_internal` bilinmeyen ad hitabını existing `unresolved_named_address` ile çözer; `_scene_presence_text`, `_scene_look_text`, `plan_living_world_turn` mevcut public NPC sunumunu kullanır. Saklanan NPC adı/rolü değiştirilmez.
- `living_world.py`: public descriptor/name ve `public_scene_people`; appearance ad olarak yükseltilmez, görünür kişiler Türkçe ve tekrarsız sunulur.
- `game.py`: `_supported_lore_question_response`, `finalize_narration` / bounded fallback, `_narrate_resolved_turn` ve ilgili shop refusal yolları mevcut `resolved_presentation` bağlantılarını yeniden kullanır. Investigation başarı/başarısızlığı gerçek sonuçtan anlatılır. Explicit shop'ta uydurulmuş kalabalık/silah/birinci şahıs reddedilir. High Road bilgisi yalnız yüklü fact varsa; The North/Sword Coast metni kitapta bölgesel gruplama niteliğini korur. Yeni lore fact veya pack yok.
- `game.py` `_combat_narration`: existing `visible_dash_narration` ile gerçek 5 feet mesafe sunulur. `bounded_encounter.py` başlangıç hash'i ile aynı; hareket/initiative/economy değişmedi. `shop_creation.py` değiştirilmedi.
- `game.py`: eski `_agent_debug_log` ve çağrıları, eşleşen tarihsel küçük hunks üzerinden kaldırıldı. Önceki source snapshot saklandı. Toplu eski dosya geri yükleme yapılmadı; `targeted-restoration.json` eşleşme kayıtlarıdır.
- Yeni `api/model_phase.py`, `api/ollama_adapter.py` ve `api/main.py`: AC019 için request-local faz kanıtı. Aşağıdaki sınır açıklamasına bakın.
- `game.py` `_print_skill_result` ve model transport exception tanı satırı: CP1254 konsoluna yazılamayan emojiler kaldırıldı. Bu yalnız tanı çıktısıdır; oynanış/zar veya oyuncu anlatısı değişmez.
- Yeni `api/tests/test_stage10b_model_boundary.py`: pre/post transport, malformed, save failure, receipt replay/resume/isolation, unknown/mixed phase fail-closed ve strict CP1254 konsol testi. Eski assertion'lar gevşetilmedi. İçe aktarılan base class nedeniyle toplam test yürütmesinde iki tekrar vardır; 634/632 ayrımı bu yüzden açık verilir.
- `api/tests/live_neverwinter_canon_smoke.py`: önceki faz/gate/bellek trace bağlantıları dar hunks ile onarıldı; her gerçek çağrı öncesi/sonrası canonical state+RNG digest gözlemcisi eklendi. `live_stage10b_unified.py` ve `stage10b_boundaries.py` yalnız yeni evidence path için `AI_DND_STAGE10B_EVIDENCE_DIR` kabul eder. Bu harness'leri eski varsayılan evidence köküne yönlendirmeyin.

Tam başlangıç/son SHA256: `source-hashes-before.json`, `source-hashes-final.json`. İnceleme farkı: `repair-only-review.patch` ve kapsam notu. Bu patch dirty checkout'a kör uygulanmamalıdır. İki evidence-path harness'inin başlangıç snapshot'ı yoktur; bunlar için tam önce-byte kanıtı uydurulmadı. Diğer önceden var olan dirty değişiklikler korunur.

## AC019 — transaction ve anlatı sınırı

Python `_narrate_resolved_turn` içinde, çözülmemiş entity/update izinleri kalmadığında existing narration-only sınırını request-local ContextVar ile işaretler. Adapter exception'ı typed `ModelFailure` içine bu fazı koyar. Faz model metninden, HTTP cevabından veya bir dükkân bulunması gibi heuristikten türetilmez; DB'ye/persisted schema'ya eklenmez ve scope finally ile sıfırlanır.

API ancak bütün failure'lar bu kanıtlı resolved narration sınıfındaysa normal sonuç/save/receipt yoluna devam eder. Bilinmeyen/plain/mixed failure aynı rollback+503 yolundadır. Sonraki save failure hâlâ aynı mevcut rollback sahibindedir. Call budget ve diğer hata kontrolleri kalır.

Fault harness: çözüm öncesi exception → 503, state aynı, shop0; iki çağrı gözlendi, retry iddiası değildir. Çözüm sonrası shop narrator exception → 200, shop1, tek çağrı. Malformed → 200, shop1, tek çağrı. Son iki halde metin: “Burada küçük bir yerel dükkân var; başında bir dükkâncı duruyor.” Replay/resume/isolation ve save rollback son suite içinde doğrulandı. Fault testleri gerçek Qwen kanıtı diye sayılmadı.

## Gerçek runtime, hava ve anlatı

`unified-02/unified-campaign.json`: tek izole kampanyada shop/tavern/name/empty quest, action replay/conflict/concurrency, aktif combat restart ve gerçek devam turu; failures=[]; ikinci kampanya temiz. Gerçek Qwen trace: 19 audit satırı, 7 çağrı, tur başına max2; her çağrıda canonical digest aynı, finalization sonrası çağrı yok. Gerçek browser audit: 17 satır, 1 model çağrısı; digest aynı. Canonical kampanya gerçekliği model çağrısından bağımsızdır.

`browser-session.md` görünür UI/API karşılaştırmaları, tam iki envanter satırı, kayıp yanıtın aynı action_id ile gerçek UI tekrarı, gecikmiş A cevabının B'ye sızmaması ve combat restart kanıtlarını açıklar. Shop görünümü mevcut transcript ve keeper panelidir; ayrı shop ekranı iddiası yoktur. `browser-replay-proof.json` aynı istek ve tam state eşitliğini doğrular.

AC004: gerçek mevcut authored exploration yolculuğu, RNG değiştirilmeden stone_trail_fork'a ulaştı; mevcut catalog weather=fog → API fog → görünür “Sisli”. Bu veri Neverwinter default clear varsayımından türetilmedi. Eksik/unknown alanlar yalnız response-level **sentetik sunum fixture** olarak işlendi; ikisinde “Belirsiz” göründü ve raw canonical fog korundu. Fixture kaldırılınca normal fog tekrar görüldü. Üç AX/PNG ve ağ raw/presented çiftleri saklıdır.

`narration-review.md`: Codex manuel metin okuması; yeni insan/owner imzası değildir. Türkçe kabul akışı çözülmüş sonuçları anlatır, oyuncu anlatısında teknik motor dili yoktur. Story smoke'un ilk beş İngilizce lore sorusu ayrıca belirtilir; bütün dosyaya Türkçe denmez. Gerçek zarlar, sonuçlar ve NPC'ler değiştirilmedi.

## Koşular ve kırmızı geçmiş

| Kayıt | Sonuç |
| --- | --- |
| focused-01 | 77 test, exit0 |
| model-boundary-01 | 9 test, fixture key error, exit1; korundu |
| model-boundary-02 | 9 test, exit0 |
| regressions-01 | 488 test, 98.040s, exit0 |
| boundaries-01 | pre/post/malformed + negatif yollar, exit0 |
| unified-01 ve unified-02 | gerçek Qwen, restart, combat, isolation; exit0 |
| story-smoke-01 | 20 gerçek runtime turu, exit0; manuel okuma ayrı notta |
| boundary-persistence-weather-final | 165 test, 4failure14error, 113.739s, exit1; lore engelleri açık |
| regressions-final | 633 test, 3failure2error, 230.889s, exit1; CP1254 tanı çıktısı hatası |
| regressions-final-02 | 634 yürütme / 632 farklı test, 200.728s, exit0; aynı seçiciler + CP1254 testi |
| regression-script-final | 29/29, exit0; unittest içinde sıfır test veren standalone betik ayrıca çalıştırıldı |
| frontend-test | 67/67, exit0 |
| frontend-libraries / typecheck / build | hepsi exit0 |

Son tam komut `regressions-final-command.json`; seçilen her test `regressions-final-test-ids.json`. development_checks.json seçicileri ve önceki 10A grubu kapsandı. Önceki 491 koşusunun bire bir komutu bulunamadı; sayıyı zorla eşitlemek için test ekleme/çıkarma yapılmadı. Yeni sayılar gerçek runner çıktısıdır.

Frontend loglarında paket yöneticisinin script öncesi doğrulama/install uyarısı, sourcemap uyarısı ve >500kB bundle uyarısı vardır. İstenen dört scriptin kendi çıkışı 0'dır; lockfile/package.json değiştirilmedi. Uyarılar silinmedi; production deploy yapılmadı.

## Açık engeller ve kesin sonraki kapsam

1. `Owner_Decision_Castle_Ward_1501.md` için beklenen pin `be4b2f8a399103537f93fc33cfebe47524bd811a6fb232b577b480a087895d8a`; mevcut hash `d8accdf67802838b6e019cd8b05a75c781fc5a4837c14bbeb0d15c29c2d420da`. Freeze admission fail-closed davranıyor; boş kabul kümesi takip eden WD22/BG22 hatalarını doğuruyor. Kaynağı veya pini keyfi değiştirerek PASS yapılamaz. Owner tarafından kabul edilmiş exact belge/pin ayrı lore kapsamı içinde uzlaştırılmalı.
2. `test_lore_1501_integration` import aşamasında `OwnerContinuityRecord` bulamıyor. Test gövdesi çalışmadı; import giderilince başka assertion'lar çıkabilir. Sahte class veya skip eklenmedi. Staged 1501 lore model/integration sözleşmesi ayrı kapsamda incelenmeli; city activation veya save schema'ya sessiz müdahale yapılmamalı.

`protected-lore-blockers.json` tam kanıtı içerir. models.py başlangıçta dirty idi; bu görev korunan dosyaları değiştirmedi. Exact eski byte/hash başlangıçta yakalanmadığı için kesin eski hash iddiası yoktur. Bu engeller kullanıcının source/lore/schema kapsam dışı sınırına girer; sıradan 10B değişiklikleri için yeniden onay istenmedi.

INV001: tarihsel aralıklı HTTP500 **UNCONFIRMED** kalır. Bu çalışmada ayrıca CP1254 tanı çıktısı kaynaklı 500 gerçekten üretildi; traceback `regressions-final.log` içinde, dar düzeltme ve strict encoding testi son yeşil koşuda doğrulandı. Tarihsel 500'ün aynı kök neden olduğu iddia edilmez. Kasıtlı save-failure testleri ve proxy drop hataları ayrı kayıtlardır.

## 28 maddelik final değerlendirme

AC027'nin zorunlu seçici kısmı yeşildir. Ek ilişkili lore doğrulaması hâlâ kırmızı olduğundan regresyon kapanışı ihtiyatlı biçimde FAIL tutuldu. Böylece 27 PASS / 1 FAIL; Stage10B kapanışı yok. Bu, sözleşme metninde değişiklik değildir.

| Madde | Durum | Bulgu | Kanıt (yeni köke göre) |
| --- | --- | --- | --- |
| S10B-AC-001 | PASS | HP 12/12 aynı kampanyanın API state ve görünür UI kaydında eşleşti. | `browser-inventory.ax.txt`, `browser-network/`, `browser-resume-state.json` |
| S10B-AC-002 | PASS | Tavern location_001, parent Neverwinter; giriş/çıkış/yeniden giriş aynı kimlik. | `browser-tavern.ax.txt`, `browser-tavern-reentry.ax.txt`, `unified-02/unified-campaign.json` |
| S10B-AC-003 | PASS | 1 Mirtul 1501 DR 09:00; combat sonrası 09:00:06 API kaynaklı. | `browser-inventory.ax.txt`, `browser-resume-state.json` |
| S10B-AC-004 | PASS | Gerçek authored fog görünür Sisli; eksik ve unknown yalnız açıkça etiketli sentetik UI fixture, Belirsiz. Raw API fog korunur. | `weather-live-travel-04.json`, `browser-weather-*.ax.txt`, `browser-and-trace-verification.json` |
| S10B-AC-005 | PASS | Combat id, round2, HP12/NPC4 ve sıra eşleşti. | `browser-resume-combat-panel.ax.txt`, `browser-resume-state.json` |
| S10B-AC-006 | PASS | İki API envanter string kimliği de karakter panelinde görünür; eksik satır yok. | `browser-inventory.ax.txt`, `browser-and-trace-verification.json` |
| S10B-AC-007 | PASS | Boş quest listesi ve sunulmuş etkin görev yok anlatısı; kayıt uydurulmadı. | `unified-02/unified-campaign.json`, `story-smoke-01.json` |
| S10B-AC-008 | PASS | Arven keeper belleğinde; başka NPC adı bilmiyor; restart sonrası hatırlıyor. | `unified-02/unified-campaign.json`, `unified-02/unified-audit.jsonl` |
| S10B-AC-009 | PASS | Açık yaratım bir shop; lookup ve tekrar keeper çoğaltmaz; shop owner değişmedi. | `regressions-final-02.log`, `unified-02/unified-campaign.json` |
| S10B-AC-010 | PASS | API narration gerçek AX metninde bire bir bulunuyor. | `browser-and-trace-verification.json` |
| S10B-AC-011 | PASS | A cevabı 15sn gecikirken B açıldı; B tur0/HP12, A hasar metni sızmadı. | `browser-B-before-delayed.ax.txt`, `browser-B-after-delayed.ax.txt`, `browser-network/` |
| S10B-AC-012 | PASS | Combat bitmeden API restart+UI refresh/resume: combat ve shop tam eşit. Shop mevcut transcript/keeper görünümünde; ayrı shop paneli yok. | `browser-resume-state.json`, `browser-resume.ax.txt`, `browser-resume-world.ax.txt` |
| S10B-AC-013 | PASS | Birleşik izole kampanya meşru komutlarla sıralı akışı tamamladı; failures boş. | `unified-02/unified-campaign.json`, `unified-02/unified-audit.jsonl` |
| S10B-AC-014 | PASS | Replay, çatışan gövde409, eşzamanlı çift gönderim, kesinti sonrası gerçek UI tekrarı; ikinci state/RNG etkisi yok. | `unified-02/unified-campaign.json`, `browser-replay-proof.json`, `regressions-final-02.log` |
| S10B-AC-015 | PASS | Mevcut failed-save rollback ve yeni post-resolution model error + save failure kombinasyonu geçti. | `regressions-final-02.log` |
| S10B-AC-016 | PASS | İkinci kampanya NPC/shop/avlu/isim kaydını devralmadı. | `unified-02/unified-campaign.json`, `browser-B-after-delayed.ax.txt` |
| S10B-AC-017 | PASS | Aktif combat kimliği, konum, HP, inisiyatif ve economy restartta korunur; sonraki gerçek tur ilerler. | `unified-02/unified-campaign.json`, `browser-resume-state.json` |
| S10B-AC-018 | PASS | Birleşik trace max2; gerçek UI max1; gate finalization sonrası çağrı yok. | `browser-and-trace-verification.json`, `story-smoke-01.json`, `regressions-final-02.log` |
| S10B-AC-019 | PASS | Çözüm öncesi503 rollback/no receipt; kanıtlı çözüm sonrası200 grounded fallback + kayıt/replay; malformed1call. CP1254 konsol arızası da onarıldı. | `boundaries-01/model-failure.json`, `regressions-final-02.log` |
| S10B-AC-020 | PASS | Desteksiz lore/ödül/envanter/fiyat talepleri yeni gerçek yazmaz. | `boundaries-01/negative-paths.json`, `story-smoke-01.json`, `regressions-final-02.log` |
| S10B-AC-021 | PASS | Gerçek 5feet dash, ıska/hasar Python sonucu; combat model çağrısı0. | `browser-combat.ax.txt`, `browser-resume-combat-panel.ax.txt`, `regressions-final-02.log` |
| S10B-AC-022 | PASS | Aktif combat seyahati400; konum değişmedi. | `unified-02/unified-campaign.json`, `regressions-final-02.log` |
| S10B-AC-023 | PASS | test_wrong_actor_and_no_weapon_do_not_roll ve current_actor/participant negatifleri geçti. | `regressions-final-02.log`, `api.tests.test_combat_lifecycle` |
| S10B-AC-024 | PASS | Olmayan hedef reddedilir; relocation stale turn reddi ve bilinmeyen Elara NPC belleği izolasyonu geçti. | `boundaries-01/negative-paths.json`, `story-smoke-01.json`, `regressions-final-02.log` |
| S10B-AC-025 | PASS | Hiç yaşanmamış konuşma unverified; events değişmedi. | `boundaries-01/negative-paths.json`, `story-smoke-01.json` |
| S10B-AC-026 | PASS | Codex manuel metin incelemesi; Türkçe kabul akışı çözülmüş sonuçları anlatır. İngilizce lore soruları ayrıca etiketlendi. | `narration-review.md`, `browser-session.md` |
| S10B-AC-027 | FAIL | Zorunlu seçiciler+10A+API/save/weather grubu onarım sonrası kontrol edilir; genişletilmiş lore koşusu165 testte4 failure14 error ve exit1 olarak açık. Kapanış engeli. | `regressions-final-02.log`, `regression-script-final.log`, `boundary-persistence-weather-final.log`, `protected-lore-blockers.json` |
| S10B-AC-028 | PASS | Yerel gerçek qwen3:8b çağrıları; intent/narration fazları ve her çağrıda eşit canonical_before/after digest. | `unified-02/unified-audit.jsonl`, `browser-audit.jsonl`, `browser-and-trace-verification.json` |

## Cursor'a devralma notu

Bu yeni sürümü ve `summary.json` dosyasını kullanın; önceki Stage10A/10B raporlarını değiştirmeyin. Güncel hashleri doğrulamadan eski patch uygulamayın. Önce korunan lore belge/pin ve model sözleşmesi farkını sahibinin kabul ettiği ayrı kapsamda çözün; ardından kırmızı 165 koşusunu ve son seçici koşuyu yeni bir evidence kökünde çalıştırın. Eski kırmızı loglar kalmalı. Ancak tüm gereken kanıtlar yeşil olduğunda yeni versioned final acceptance yazılabilir. Mevcut rapor merge/deploy/production veya bütün repository onayı değildir.
