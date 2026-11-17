# Onay listesi (Kadir kararları, 2026-11-15)

Kaynak: Kadir'in 2026-11-15 kararları, madde 16-21. Defter: `docs/agents/debt-register.md`.

## 1. PR #70 (para, D-096) içinde yeniden yazılan testler

PR #70 = `task/yuk-para-20261115`, birleşme `3576eeaf`. Dört dosyada var olan testler değişti (`ai-dnd/api/tests/` altında). Ortak neden D-096: oyuncunun verdiği hediye ya da bahşişi NPC "alırım" demediyse kart açılırsa kart yalnızca onayda reddedilebilirdi (ölü kart). Artık kart hiç açılmaz, neden o turda söylenir ("alacağını söylemedi"). Beklenti gevşemedi, yön değişti: "kart açılır, onayda reddedilir" yerine "kart açılmaz, ret nedeni söylenir, kese ve defter değişmez".

Sayı notu: Kadir'in yazdığı "13+6" sayısını depoda ve PR #70'te bulamadım. Aşağıda yardımcı işlev yoluyla etkilenenler dahil 15 test sayıyorum. "altına/altında/altından" ve "6 soyut özne" değişiklikleri PR #70'te değil, PR #80'te (D-209, D-210; bkz. bölüm 2).

Onay durumu: Bu 15 test için Kadir'in ayrı bir onay cümlesi yok. Onay bekliyor.

| Dosya | Test | Eski beklenti | Yeni beklenti | Kadir onayı |
|---|---|---|---|---|
| test_compound_line.py | `test_walk_then_pay_opens_one_card_for_the_coin` | han turunda 5 gümüş bahşiş için bir "prepared" kart açılır, `max_total_cp` 50 | kart açılmaz (`economic_offer` yok), "alacağını söylemedi" bir kez söylenir, "prepared" sayısı 0, kese aynı, barmenin `coin_responses` değeri `offer:50: unknown` | onaylandı (Kadir, 2026-11-16) |
| test_compound_line.py | `test_walk_then_pay_by_name_opens_the_same_card` | isimle verilen bahşiş de bir kart açar (50 cp, kese aynı) | aynı yeni beklenti (ortak denetim `assert_tip_answered_without_a_dead_card`) | onaylandı (Kadir, 2026-11-16) |
| test_compound_line.py | `test_walk_then_pay_by_name_after_a_comma_and_sonra` | yukarıdakiyle aynı eski beklenti | aynı yeni beklenti | onaylandı (Kadir, 2026-11-16) |
| test_dilim3d_money.py | `test_a_tip_named_twice_is_given_once` (`tips_once` yardımcısı) | okumada NPC sözü yok, bahşiş kartı açılır (5 cp, kese 100) | okumaya "NPC alır" (`coin_answer: takes`) eklendi; kart yine açılır, ardından onay adımı eklendi: kese 95, kart yok | onaylandı (Kadir, 2026-11-16) |
| test_dilim3d_money.py | `test_a_turkish_tip_named_twice_is_given_once` (`tips_once` yardımcısı) | aynı | aynı yeni beklenti | onaylandı (Kadir, 2026-11-16) |
| test_economic_spoken_consent.py | `test_validated_offer_without_semantic_reply_cannot_debit` | defterde bir işlem, `net_debit_cp` 0, `npc_consent_required` | defterde işlem yok, "prepared" kart yok, `coin_responses` `offer:5: unknown` | onaylandı (Kadir, 2026-11-16) |
| test_economic_spoken_consent.py | `test_unknown_response_cannot_authorize_debit` (`run_consent` yardımcısı) | kart açılır, onayda reddedilir | senaryo 2 adımda biter: kart yok, kese 100, metinde "alacağını söylemedi" | onaylandı (Kadir, 2026-11-16) |
| test_economic_spoken_consent.py | `test_model_injected_speaker_cannot_authorize_debit` (`run_consent`, `malformed`) | aynı eski beklenti | aynı yeni beklenti | onaylandı (Kadir, 2026-11-16) |
| test_economic_spoken_consent.py | `test_unknown_reply_opens_no_card_and_says_why` (eski ad `test_unknown_reply_card_cannot_apply_and_warns_may_refuse`) | durum "prepared", `may_refuse` doğru, çözümde `refused`/`npc_consent_required`/0 | hazırlıkta hemen `refused`/`npc_consent_required`, `offer` yok, mesajda "alacağını söylemedi", dünya durumu değişmez | onaylandı (Kadir, 2026-11-16) |
| test_economic_spoken_consent.py | `test_unclear_reply_still_holds_after_turn_advance` (eski ad `test_consuming_refusal_cannot_be_retried_after_turn_advance`) | iki turda kart onaylanır, ikisi de `refused`, borç 0 | iki turda da hazırlık `refused`, kart yok, kese değişmez, defterde `operations` yok | onaylandı (Kadir, 2026-11-16) |
| test_economic_spoken_consent.py | `test_saved_reply_survives_reload` | yeniden yüklemeden sonra kart çözülür ve reddedilir | yeniden yüklemeden sonra hazırlık doğrudan `refused`, kart yok | onaylandı (Kadir, 2026-11-16) |
| test_economic_spoken_consent.py | `test_deterministic_reply_cannot_silently_drop_pending_gift` | bekleyen hediye için bir kart açılır, çözümde reddedilir | kart açılmaz; sonuç `refused`/`npc_consent_required`; anlatıda "alacağını söylemedi"; bekleyen öneri temizlenir | onaylandı (Kadir, 2026-11-16) |
| test_room_purpose_routing.py | `test_compound_gift_mentions_room_but_stays_gift` | kişi sözü yok, hediye kartı açılır | okumaya "NPC alır" (`TAKES`) eklendi, kart yine açılır (5 cp, "Hediye") | onaylandı (Kadir, 2026-11-16) |
| test_room_purpose_routing.py | `test_tip_amount_comes_from_words_not_model_figure` | kişi sözü yok, bahşiş kartı 5 cp | `TAKES` eklendi, kart yine 5 cp "Bahşiş"; tutar yine sözcüklerden gelir | onaylandı (Kadir, 2026-11-16) |
| test_room_purpose_routing.py | `test_disabled_turn_does_not_skip_next_enabled_economic_read` | hediye okuması sözsüz | okumaya `TAKES` eklendi; denetimler aynı | onaylandı (Kadir, 2026-11-16) |

Not: `run_purpose` yardımcısına yalnız isteğe bağlı `speech` bağımsız değişkeni eklendi; kendi başına beklenti değişmedi.

## 2. PR #80 (D-209, D-210) süzgeç değişiklikleri (gevşetme olabilir)

| Madde | Ne değişti | Kadir onayı |
|---|---|---|
| D-209 | para iddia süzgecinde "altına/altında/altından" artık para sayılmaz ("altın", "altını", "altınlar" sayılır). Gevşetme: "Kesenden altından üçü düşüyor" gibi nadir bir yalan cümle kalabilir; para kaydı etkilenmez. | onaylandı (2026-11-15) |
| D-210 | anlatı büyüsü iddia geçidi 6 soyut özne (seçim, karar, zafer, tercih, sıra, söz) ve "doğru" yönünde artık iddia görmez. Gevşetme: listede olmayan soyut özne yine Python satırına düşer, eşya etkilenmez. | onaylandı (2026-11-15) |

## 3. Öteki onay maddeleri

| Madde | Konu | Defter satırı | Durum |
|---|---|---|---|
| 17 | Geri Al testinde `wrong_turn` yerine `wrong_time` (`test_skill_result_pipeline_regression.py`, Geri Al durum bozma durumlarından biri; D-139 kaydı) | D-139 | onaylandı (Kadir, 2026-11-15) |
| 18 | D-094 gizlenme testleri | D-094 (kural D-171) | onaylandı (Kadir, 2026-11-15) |
| 19 | D-194: izinsiz yolda telemetri kaynağı tutulmaz | D-194 | onaylandı (Kadir, 2026-11-15) |
| 20 | D-214: "henüz motorda yok", yuva harcanmaz | D-214 | onaylandı (Kadir, 2026-11-15) |
| 21 | D-203: görev kabul edilmeden toplanan delil | D-203 | onaylanmadı. Karar: delil silinmez, saklanır, görev kabul edilince sayılır; test bu davranışa göre yazılır |
| 2 | D-166: C5 testleri eşit sıkılıkla yeniden yazılacak | D-166 | yeniden yazım yapılınca bu listeye eklenir |
| CI 2026-11-17 | `test_clerk_http.test_concurrent_requests_share_one_jwks_fetch_without_blocking_the_loop`: saat sınırı (0.25 sn, CI'da 0.67 sn ile kırıldı) yerine kapı: anahtar getirme test kapıyı açana kadar bekler; sağlık cevabı geldiğinde istekler bitmemiş olmalı ve kapı zaman aşımına düşmemeli. Döngüyü kilitleyen kod hâlâ kırmızı (denendi). Ayrıca `test_front_carries_more` yeni ad testi kasabasını sabitler | - | onay bekliyor (gevşetme yok; sıkılaştırma) |

Doğrulamadım: testlerin dosyalardaki şu anki hâli yerine PR #70 birleşme farkına (`git diff 3576eeaf^1 3576eeaf`) baktım; "13+6" sayısının kaynağı bulunamadı.

## 4. Kadir onayı 2026-11-16 (oynayıştan sonra)

Kadir 2026-11-16'da 10 dakika oynadı (main 221e6d98) ve "Onaylıyorum" dedi. Oynayış kapısı geçti. Bölüm 1'deki 15 test ve aşağıdakiler onaylandı.

| PR | Değişiklik (gevşetme olabilir) | Durum |
|---|---|---|
| #111 | `test_explicit_shop_creation` (2 test), f04 D05, `test_step0_ledger_play` keseye göre yeniden yazıldı; d229 gösterilen eşya 2'den 1'e; 53g tohumu 116'dan 163'e; 54c yakalanma cümleleri ('Elini çek' yerine 'Hırsız mısın', 'Hırsız mısın' yerine 'O kadar kolay mı sandın') | onaylandı |
| #110 | `test_a_coin_deal_to_nobody_listed_still_asks_who` yeniden yazıldı | onaylandı |
| #109 | ön okuma tavanı 400'den 700'e; usage.jsonl `causes` alanı | onaylandı |
| #107 | kaçak döngü tavanı 240'tan 480'e | onaylandı |
| #114 | D-267 söylenen tutar metinde kalır; 'İşte bu yüzden sana para vermem.' silinir; D-266 kapsamı: para ya da kese adı geçen al/tut/işte/buyur cümleleri silinir | onaylandı |
| #113 | D-120 Türkçe 'Toplu Şifa Sözü' testi hata yerine 'henüz motorda yok' bekler (aynı sıkılık) | onaylandı |
| D-109, D-166, kalan-sayaç, D-231, #84 | önceki dalgalarda yeniden yazılan testler (KOD 2 devir notu listesi) | onaylandı |

## 5. D-249 + D-250 dilimi (dal `task/d249-tasarim-20261116`, onay bekliyor)

Yeniden yazılan testler; "gevşetme olabilir" işaretlileri sınırı yeniden tanımlar. Kadir oynayıştan sonra onaylar.

| Test | Değişiklik | İşaret |
|---|---|---|
| `test_experimental_npc_dialogue`, `test_default_npc_targeting`, `test_npc_p2_continuity` | konuşma şemasının anahtar kümesine `mentions` girdi; şerit açıkken `required` listesine `mentions`, `kind` seçeneklerine `none` eklendi | gevşetme olabilir |
| `test_meaning_boundary_acceptance` (satır 33), `test_spoken_promises` (`TheField`), `test_default_focus_acceptance` (bayrak kapalı), `test_query_request_acceptance` (yer bilgisi) | `required` listesi `[..., "threat", "mentions"]` oldu (aynı sıkılık) | gevşetme olabilir |
| `test_story_links.test_a_person_carries_one_at_most` | üst sınır 5 yerine `town_knowledge.MAX_ITEMS` (10) | gevşetme olabilir |
| `test_arrival_narration` | uzun anlatım durumu 8 cümle (tavan 6); son anlatım 400 yerine 1200 harf | gevşetme olabilir |
| `test_local_gemma_12b` | bulut mesajları testi bulut üslup bloğunu bekler | gevşetme olabilir |
| `test_game_name.ProtectedIdsTests.test_env_variable_name_set_is_unchanged` | `AI_DND_*` ad sayısı 36'dan 37'ye (`AI_DND_RUMOUR_LANE`) | gevşetme olabilir |
| `test_journey_schema` beklenti anahtarı kümesi | `duyulan` eklendi (yalnız ekleme) | - |

## 6. Logo sürekli dönsün (dal `task/logo-donsun-20261117`, sahibin kararı, davranış değişimi)

Kaynak: Kadir, 2026-11-17: "logonun otomatik dönmesi gerekiyor, dönmüyor". Bulgu: `OYNAYIS_NOTLARI_20261117.md` B8.

| Test | Eski beklenti | Yeni beklenti | Not |
|---|---|---|---|
| `artifacts/ai-dnd-experience/tests/menu-logo-music.test.mjs`: "the logo plays only while something is loading..." yerine "with motion on the logo loops on its own, whatever is loading; a hidden tab pauses it and showing the tab resumes it" | video yalnız yükleme sürerken oynar, bekleme bitince en az 600 ms kalır (`loading` prop, `MIN_VISIBLE_MS`) | hareket açıkken video yüklemeden bağımsız döngüde oynar; gizli sekmede durur, sekme görününce yeniden başlar; tema değişince yeniden başlar; `autoPlay` yok. Azaltılmış hareket / efekt kapalı: video yok, yalnız durağan görsel (komşu test aynen duruyor) | sahibin kararı, davranış değişimi; aynı sıkılık; onay bekliyor |

## 16. Yuva kırmızıları (dal task/sekiz-kirmizi-20261117)

Sekiz test yuvada kırmızıydı, CI'da yeşildi. Eski testlerde yapılan değişiklikler (hiçbir iddia gevşetilmedi; işaretli olanlar "gevşetme olabilir" sınıfında):

- `ai-dnd/test_spells_v1.py` `test_cure_wounds_heals_during_combat_and_refuses_to_open_combat`: ilk yarı eski sözleşmeyi sabitliyordu (savaş dışında Cure Wounds `ValueError`). Kadir'in 2026-11-15 D-056 kararı (f4c96d86) bunu tersine çevirdi. Yeni ilk yarı: savaş dışında iyileştirir, bir yuva harcar, savaş açmaz (`combat.active` False). İkinci yarı aynı. Gevşetme olabilir: eski "reddeder" iddiası kalktı, yerine kararın tersi iddia geldi.
- `ai-dnd/api/tests/test_journey_real_run.py` TheNetworkGuard: yuva koruması (B06) varken biri atlanır (`skipIf(GUARDED)`, TCP geri dönüş soketi koruma altında yapılamaz), öteki AF_UNIX soketle koşar; ikisi de CI'da (koruma yok) eskisi gibi koşar. Gevşetme olabilir: yalnız yuvada, atlama ve soket türü.
- `ai-dnd/api/tests/test_model_chain.py` `test_two_processes_on_one_file_never_lose_an_add`: koruma varken atlanır; aynı kilidi sınayan yeni iş parçacıklı eş test hep koşar. CI'da süreç testi aynen koşar. Gevşetme olabilir: yalnız yuvada atlama.
- Yeni (ek): `api/tests/test_pocket_keeps_paragraphs.py`, `api/tests/slot_guard.py`. Ürün kodu: `ai-dnd/pocket.py` paragraf boşluğunu korur (test_ai_pipeline_port'taki test dokunulmadı).
