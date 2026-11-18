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

## 7. Yuva kırmızıları (dal task/sekiz-kirmizi-20261117)

Sekiz test yuvada kırmızıydı, CI'da yeşildi. Eski testlerde yapılan değişiklikler (hiçbir iddia gevşetilmedi; işaretli olanlar "gevşetme olabilir" sınıfında):

- `ai-dnd/test_spells_v1.py` `test_cure_wounds_heals_during_combat_and_refuses_to_open_combat`: ilk yarı eski sözleşmeyi sabitliyordu (savaş dışında Cure Wounds `ValueError`). Kadir'in 2026-11-15 D-056 kararı (f4c96d86) bunu tersine çevirdi. Yeni ilk yarı: savaş dışında iyileştirir, bir yuva harcar, savaş açmaz (`combat.active` False). İkinci yarı aynı. Gevşetme olabilir: eski "reddeder" iddiası kalktı, yerine kararın tersi iddia geldi.
- `ai-dnd/api/tests/test_journey_real_run.py` TheNetworkGuard: yuva koruması (B06) varken biri atlanır (`skipIf(GUARDED)`, TCP geri dönüş soketi koruma altında yapılamaz), öteki AF_UNIX soketle koşar; ikisi de CI'da (koruma yok) eskisi gibi koşar. Gevşetme olabilir: yalnız yuvada, atlama ve soket türü.
- `ai-dnd/api/tests/test_model_chain.py` `test_two_processes_on_one_file_never_lose_an_add`: koruma varken atlanır; aynı kilidi sınayan yeni iş parçacıklı eş test hep koşar. CI'da süreç testi aynen koşar. Gevşetme olabilir: yalnız yuvada atlama.
- Yeni (ek): `api/tests/test_pocket_keeps_paragraphs.py`, `api/tests/slot_guard.py`. Ürün kodu: `ai-dnd/pocket.py` paragraf boşluğunu korur (test_ai_pipeline_port'taki test dokunulmadı).

## 8. BM görev 1 (dal `task/bm-t1-20261117`, onay bekliyor)

Konuşma satırı artık ön okumadan geçer (`say`/`ask_dm`, kişi seçili olsun olmasın); eski kelime yolları yedek. Yeniden yazılan testler; "gevşetme olabilir" işaretlileri sınırı yeniden tanımlar.

| Test | Değişiklik | İşaret |
|---|---|---|
| `test_front_money.SayModeCoin.test_say_mode_reads_only_a_line_that_names_coin` (yeni ad `test_say_mode_reads_every_line_and_coin_stays_the_owners`) | parasız söz satırı artık okunur (eskiden okunmazdı, `skipped:typed`); aynı sıkılık: o satırda para 0, para satırı yine 50 okur | gevşetme olabilir |
| `test_front_money.SayModeCoin.test_a_coin_line_to_nobody_typed_is_not_a_say_mode_reading` (yeni ad `test_a_coin_line_asked_of_the_dm_is_read_but_its_coin_is_never_taken`) | `ask_dm` satırı artık okunur; aynı sıkılık: okunan para alınmaz (`_front_coin == 0`), rota `typed:talk_read` | gevşetme olabilir |
| `test_front_money.SayModeCoinKeepsTheTalk.test_a_say_line_without_coin_keeps_its_own_proposal_call` (yeni ad `test_a_say_line_without_coin_is_read_once_and_asks_no_second_call`) | eski öneri adımı kendi sınıflandırıcı çağrısını yapardı; şimdi ön okuma o çağrı (en çok 2 çağrı) | gevşetme olabilir |
| `test_front_tip_pipeline.TipPipeline.test_say_mode_keeps_the_same_true_for_the_chosen_vendor` (süit düzeltmesi) | sahte model yanıtına `asks` ve `about_person_id` ('none') eklendi; "yanıt = sahibe giden girdi" karşılaştırması aynen tam eşitlik kaldı (para alanları dahil) | gevşetme yok (fikstür yeni okuma alanlarını bilmiyordu) |

Davranış sınırı (BM T1, Opus incelemesi 2026-11-17): kişi seçili düz `say` satırında `_front_economic_none` kurulur; eski kelime yolları (`bold_acts.take_room`, `_room_asked`) oda kartını artık hazırlamaz, kararı modelin `economic_intent` okuması verir. Para hareketi ve satın alma yolları değişmedi. Gevşetme olabilir; onay bekliyor.

## 9. BM görev 2 (dal `task/bm-once-model-20261117`, onay bekliyor)

Dükkân varlığı, bilinmeyen ad, yer adı ve ad söyleme: model okuması düz konuşma derse konuşma yanıtlar; eski satır yedek. Yeniden yazılan testler "gevşetme olabilir" işaretlidir.

| Test | Değişiklik | İşaret |
|---|---|---|
| `test_talk_front.SayLineIsRead.test_bad_about_person_is_none`, `test_unknown_asks_is_none` | okuma artık tur bitince temizlendiği için `session._front_talk` turdan sonra değil tur içinde (`_run_player_turn` dönerken) okunur; aynı değerler aynı sıklıkta denetlenir | gevşetme olabilir (okuma ömrü kısaldı) |
| Yeni test `test_talk_front.SayOwnersAreFallback.test_shop_word_question_to_vendor_is_spoken` | satır "Satıcı esnafı arasında ne dönüyor?" (görev metnindeki "Satıcılar" çoğulu `_SHOP_ENTITY_QUERY_PATTERN` ile eşleşmez, dolayısıyla eski yolu hiç tetiklemezdi) | yeni, gevşetme değil |

## 10. BM görev 3 (dal `task/bm-once-model-20261117`, onay bekliyor)

Kişisel soru, küçük konuşma, bilgi kapısı, iş sorusu ve rol + kişi sorusu: model okuması düz konuşma derse kişi konuşmayla yanıtlar; eski satır yedek. Bu görevde eski bir test yeniden yazılmadı ve gevşetilmedi; yalnız yeni test eklendi.

| Test | Değişiklik | İşaret |
|---|---|---|
| Yeni `test_talk_front.RemainingSayOwnersAreFallback` (kişisel, küçük konuşma, iş, bilgi kapısı, rol + kişi, D-325) ve `SayOwnersAreFallback.test_name_disclosure_pool_when_the_speech_failed` | yeni; eski satır yalnız okuma başarısızken kalır | gevşetme yok |

Davranış sınırı (BM T3): `ask_dm` satırında model düz konuşma okuyup listedeki bir kişiyi adlandırırsa o kişi konuşmayla yanıtlar (eskiden bilgi kapısı satırı, sahne listesi ya da iş satırı çıkardı). Bilgi kapısının ve rol listesinin `ask_dm` yolu bu yüzden okuma varken çalışmaz; "gevşetme olabilir" olarak işaretlendi: Kadir oynayışta bakmalı.

## 11. BM görev 4 (dal `task/bm-once-model-20261117`, onay bekliyor)

İş kapısı model okumasıyla karar verir (B1): başka bir kişiyi adlandıran soru iş konuşması sayılmaz; sahibin şart satırı da okuma "iş" demedikçe eklenmez. Bu görevde eski bir test yeniden yazılmadı ve gevşetilmedi; yalnız yeni test dosyası eklendi (`test_bm_thread_reading.py`).

| Test | Değişiklik | İşaret |
|---|---|---|
| Yeni `test_bm_thread_reading.ThreadReading` (15 test: B1, şart satırı, kabul + soru, Geri Al, okuma yok, ücret, ücret + iş okuması yok, başka kişi hakkında iş sorusu) | yeni; eski kelime kapısı yalnız okuma yokken kalır | gevşetme yok |

Davranış sınırı (BM T4): okuma `speak_to` ya da bir iş türüyse (`work`, `offer_answer`, `hand_over`) ve iş adlandırmıyorsa (`job_id`, `offer_id`, `asks == "work"`), kelimeyle iş yakalama (kısa soru, "ücret", sahip terimleri) artık çalışmaz. "Paramı ver" gibi bir satır, okuma "iş" demiyorsa ücret ödetmez (kişiye konuşmayla söylenir). `matter`, `take_up` ve `lapsed` kararları okumadan geri getirildi (okuma iş diyorsa aynı Python doğrulayıcıları çalışır: `raises_the_matter`, `offers_to_help`, `lapsed_yes`; testleri var). Okuma kipi `take` (kabul edilmiş işte paketi sahibinden alma) ve `speak_to` okumasıyla sözle yapılan teslim (`give`/`give_late`, iş ücreti) okuma varken artık kelimeyle yakalanmaz: paket yerinde kalır, ücret ödenmez (güvenli yönde kapanır); model `take` ve `hand_over` okumazsa bu iki yol çalışmaz. Düzeltme: ilk sürümdeki "`_front_take`/`_front_offer_gate` karşılar" cümlesi `matter`, `take_up`, `lapsed` için yanlıştı. "gevşetme olabilir" olarak işaretlendi: Kadir oynayışta bakmalı.

## 12. BM görev 6 (dal `task/bm-once-model-20261117`, onay bekliyor)

Kişi konuşması saati, oyuncuya gösterilen varış metnini (en çok 600 karakter), kişinin kendi sözlerini, kendi işini ve son sözlerini bilir (B4, B5, B6). Varış metni kayıtlı durumdadır (`scene_state.arrival_text`); Geri Al onu geri alır.

| Test | Değişiklik | İşaret |
|---|---|---|
| `test_arrival_narration.Narrate.test_world_is_identical_with_and_without_the_call` | dünya eskiden her yerde aynıydı; şimdi `scene_state.arrival_text` hariç aynı (iki yolun kendi gösterilen metni bu anahtarda ve dönen metne eşit), geri kalan dünya aynı sıklıkta karşılaştırılır | gevşetme olabilir (karşılaştırmadan bir anahtar çıktı) |
| Yeni `test_npc_scene_time` (saat, sahne, kendi iş, kendi söz, son sözler, Geri Al, kayıt-yükleme) | yeni | gevşetme yok |
| `test_economic_spoken_consent.PendingCoinPrompt.test_bound_pending_offer_tells_only_recipient_coin_is_not_transferred` (süit düzeltmesi) | fikstürün `{elapsed_seconds}` taslak saati geçerli saatle değiştirildi (konuşma notu artık saati okuyor); para iddiaları (5 bakır, "henüz sende değil", para değişmedi) aynen duruyor | gevşetme yok (para kodu değişmedi) |
| `test_haggle_review.ReviewedPrices` (2 test, süit düzeltmesi) | `{elapsed_seconds}` taslak saati yerine geçerli saat kuruldu (`a_valid_clock`); fiyat iddiaları (bira 3/4 bakır) aynen duruyor | gevşetme yok (fiyat kodu değişmedi) |

## 13. BM görev 7 (dal `task/bm-once-model-20261117`, onay bekliyor)

Günlük yalnız gerçekten söylenen şeyi tutar (B3). Bir iş ya da söylenti "duyuldu" sayılması için cevabın o işin kendi sözcüklerinin en az yarısını taşıması gerekir (`town_rumours.was_voiced`, işlere de uygulandı) ve model `voiced` ile anahtarı (`k1..k10`) verdiyse o anahtar listede olmalıdır; yalnız yer ya da kişi adı hiçbir şeyi işaretlemez. "Söylediklerin konuşmada duyuldu." satırı günlüğe yazılmaz (K-BM-4). Duyulan söylenti günlükte "Ad: iddia" ve söyleyenin adıyla görünür.

| Test | Değişiklik | İşaret |
|---|---|---|
| `test_town_knowledge.WhatWasSaidIsTiedToTheRecord.test_a_place_named_with_a_case_ending_is_that_place` | yer adı eskiden işi "duyuldu" yapıyordu; şimdi yer bağı kalır (`last_said_place`), iş "duyuldu" olmaz | gevşetme olabilir (sınır yeniden tanımlandı, ama daha sıkı) |
| `test_experimental_npc_dialogue` (3 yer: `required` listeleri, `properties` kümesi) | şemaya `voiced` eklendi: `required` sonuna (mentions'tan önce), `properties` kümesine | gevşetme olabilir (tam liste sabitleyen test genişledi) |
| `test_heard_rumours_turn.MentionOverHttp.test_lane_off_schema_has_no_mentions_in_required` | `required` listesine `voiced` eklendi; `mentions` hâlâ yok | gevşetme olabilir |
| Yolculuk 41 `is_haberi_sokakta` (adım 1 ve 2) | sokakta geçen kişinin cümlesi eskiden işi serbest bir cümleyle anıyordu (iş sahibinin adı yeterdi); şimdi işin kendi cümlesini söyler (`$is_satiri:potter`, koşucu canlı dünyadan okur). Beklenen sonuç ve sıfır tolerans aynı | gevşetme olabilir: yeniden anlatılan (aynı sözcükleri taşımayan) bir iş artık günlüğe düşmez; Kadir oynayışta bakmalı |
| Yeni `test_journal_heard` (yer adı, sahip adı, voiced, söylenti izi, genel satır, şema, Geri Al) | yeni | gevşetme yok |

Düzeltme turu 1 (inceleme bulguları): (1) `was_voiced` artık yalnız bir işi diğer işlerden ve söylentilerden ayıran sözcükleri sayar (ortak şablon sözcükleri sayılmaz; hiç ayırt edici sözcüğü olmayan iş tam söylenmelidir); hiçbir satır başka bir işi "duyuldu" yapmaz. (2) Duyulan katalog söylentisi tehlikeli işi "duyuldu" yapmaz, `heard_rumours` içine söylenen sözleriyle yazılır; yanlış söylentide gizli gerçek günlüğe sızmaz.

| Test | Değişiklik | İşaret |
|---|---|---|
| `test_story_links.HalfTruths.test_saying_it_in_your_own_way_is` | yanlış söylenti söylenince tehlike işi eskiden "heard" oluyordu (günlük gerçek satırı gösterirdi); şimdi iş "open" kalır, söylenti kendi sözleriyle `heard_rumours`ta | gevşetme olabilir (sınır yeniden tanımlandı; daha sıkı) |
| Yeni `test_journal_heard.OneJobIsNeverAnother`, `FalseRumourKeepsItsOwnWords` | yeni (60 sabit kasaba, tüm sıralı çiftler: 0 çapraz eşleşme; yanlış söylenti) | gevşetme yok |
| `test_default_focus_acceptance` (flag kapalı, tüm kipler), `test_meaning_boundary_acceptance`, `test_query_request_acceptance`, `test_default_npc_targeting` (yer önerisi), `test_npc_p2_continuity` (3 test), `test_spoken_promises.TheField` (süit düzeltmesi) | `required` ve `properties` beklentilerine `voiced` eklendi (üstteki `test_experimental_npc_dialogue` satırıyla aynı şema değişikliği) | gevşetme olabilir (tam liste sabitleyen testler genişledi) |
| `test_npc_p2_continuity.test_live3_short_followup_drops_rumor_and_names_the_referent` | test değişmedi; ürün düzeltildi: `voiced` kuralı istemin sonundan alan kuralları bloğuna alındı, son satır yine oyuncunun mesajı | gevşetme yok |

## 14. BM görev 8 (dal `task/bm-once-model-20261117`, onay bekliyor)

| Test | Değişiklik | İşaret |
|---|---|---|
| `test_world_keeps_its_word.LeavingTown.test_the_road_on_is_a_person_saying_why_not_now_and_nothing_moves` (şimdi `..._saying_why_not_and_the_walk_is_one_hour`), `test_the_road_on_read_as_an_attempt_is_still_no_journey` (şimdi `..._still_no_day_long_journey`), `test_a_far_city_read_as_the_street_stays_on_the_road` | BM T9 (K-BM-2) sonrası kırıktı (T9 bu üç testi güncellememişti): ilk "yola devam" artık uyarır VE bir sonraki yola yürür. Eski "hiçbir şey kıpırdamaz" yerine: konum değişir, saat tam +3600 sn (bir saatlik yol; günlük yolculuk ya da uzak şehre varış yok), kişi aynı turda tırnaklı söz söyler. Niyet aynı: gün sürecek yolculuk yok | gevşetme olabilir |

## 15. BM görev 5 (dal `task/bm-once-model-20261117`, onay bekliyor)

| Test | Değişiklik | İşaret |
|---|---|---|
| `test_town_knowledge.WiderKnowledge.test_speaker_keeps_own_rumour_when_the_cap_bites` | BM T5: konuşanın kendi söylediği söylenti artık tehdit maddesinden ÖNCE gelir (sıra `[tehdit, kendi]` yerine `[kendi, tehdit]`); iki yuva yine dolu | gevşetme olabilir |

## 16. BM görev 9 (dal `task/bm-once-model-20261117`, onay bekliyor)

| Test | Değişiklik | İşaret |
|---|---|---|
| `test_carius_fifth_play.TheRoadOnIsNoWall.test_told_why_not_once_...` | BM T9 (K-BM-2): ilk "yola devam" artık uyarır VE yürür (eskiden durakta kalırdı); ikinci yürüyüş uyarısız | gevşetme olabilir |

## 17. BM son düzeltme (dal `task/bm-once-model-20261117`, onay bekliyor)

| Test | Değişiklik | İşaret |
|---|---|---|
| `test_ready_line_share.ReadyLineShare` (paylaşım, kaynaksız satırlar, boş kayıt; yeni: telemetrisiz tur, tezgâh varlık satırı) | tasarım 5.9'a uyar: payda TÜM oyuncu satırları (eskiden yalnız kaynağı bilinen, motor sahibi olmayan satırlar); kaynaksız satırlar atılmaz, `unknown` olarak sayılır; `shop_inquiry` motor sahibi değil (tezgâh varlık satırı hazır satırdır) | sınırı yeniden tanımlar, gevşetme olabilir |
| `test_narration_source_record.TheListIsTheEngines.test_no_other_engine_module_reports_a_source` (T11, süit düzeltmesi) | izinli modül kümesine rota günlüğü yazıcısı `front_proposal.py` eklendi (`ROUTE_LOG_WRITERS`); küme hâlâ tam eşitlik; yeni: `python_direct` mağaza listesinde olmamalı | gevşetme olabilir (izinli modül kümesi genişledi) |

## 18. game.py bölme T0 (dal `task/game-py-bolme-t0`, onay bekliyor)

| Test | Değişiklik | İşaret |
|---|---|---|
| `test_exits.OnlyExitsReadsTests.test_only_exits_reads_the_exit_fields` (T0.3) | üst düzey `*.py` taramasına `game_parts` dosyaları eklendi; `exits.py` ve `test_*` atlaması yalnız kök dizindeki dosyalar için (`game_parts/exits.py` atlanmaz); bulgu göreli yolla yazılır; tohumlu ihlal: `game_parts/x.py` ve `game_parts/exits.py` içindeki `get("exit_location_id") or` yakalandı | gevşetme olabilir (taranan küme değişti, genişledi) |
| `test_refusals.RefusalTexts.test_the_old_vague_line_is_gone` (T0.3) | `assertNotIn` artık `engine_source_text()` üzerinde; taranan küme game.py -> game.py + game_parts/*.py (helper engine_source_files); aynı sıkılık, yeni dosya da taranır; tohumlu ihlal kanıtı geçti | gevşetme olabilir (taranan küme değişti, genişledi) |
| `test_refusal_census.RefusalCensus` (kod taraması + `combat_refusal_turn` AST'si) (T0.3) | iki AST taraması `engine_source_files()` üzerinde. Yasaklayan iki tarama (bilinmeyen `fail` kodu; `text_for` var `note` yok): tohumlu ihlal kanıtı geçti. Olumlu iddia `combat_refusal_turn` işlevi `note` çağırır: kanıt yok, herhangi bir parça sağlayabilir (küme genişleyince daha kolay sağlanır) | gevşetme olabilir (taranan küme değişti, genişledi) |
| `test_roadmap_k02 ...test_every_npc_damage_caller_mitigates_first` (T0.3) | 40 satırlık pencere araması her motor dosyasında; taranan küme game.py -> game.py + game_parts/*.py (helper engine_source_files); aynı sıkılık, yeni dosya da taranır; tohumlu ihlal kanıtı geçti | gevşetme olabilir (taranan küme değişti, genişledi) |
| `test_roadmap_w01 ...test_no_mind_reading_mechanic_discloses_thoughts_today` (T0.3) | `assertNotIn` her motor dosyasında; taranan küme game.py -> game.py + game_parts/*.py (helper engine_source_files); aynı sıkılık, yeni dosya da taranır; tohumlu ihlal kanıtı geçti | gevşetme olabilir (taranan küme değişti, genişledi) |
| `test_game_name` (afiş `assertNotIn`/`assertIn`, kayıt biçimi kimliği) (T0.3) | `inspect.getsource(game)` ve `ai-dnd/game.py` yerine `engine_source_text()`. Yasaklayan: afiş `assertNotIn` (AI DUNGEON MASTER yok): tohumlu ihlal kanıtı geçti. Olumlu: afiş `assertIn` (`UNWRITTEN`) ve kayıt biçimi kimliği `"format": "ai-dnd-save"`: kanıt yok, herhangi bir parça sağlayabilir (küme genişleyince daha kolay sağlanır) | gevşetme olabilir (taranan küme değişti, genişledi) |
| `test_tr_names.TrNamesTests.test_game_prompt_carries_the_narrator_note` (`_dm_prompt_note(` sayısı >= 2) (T0.3) | sayım `engine_source_text()` üzerinde; tanım ve çağrı ayrı dosyada olsa da sayılır | gevşetme olabilir (taranan küme değişti, genişledi) |
| `test_combat_v2_authoritative.test_W_single_end_combat_definition` (T0.3) | tam bir `end_combat` tanımı kuralı tüm motor dosyalarında; tohumlu ihlal: parçada ikinci tanım `2 != 1` | gevşetme olabilir (taranan küme değişti, genişledi) |
| `test_narration_source_record.TheListIsTheEngines` (iki test) (T0.3) | kaynak değerleri `engine_source_text()` + `dialogue_runtime.py`'den okunur (yeni değer mağaza listesi testinde yakalanır). Modül kümesi testi dosya adıyla kalır: `narration_source` anan her `game_parts` dosyası, sabitlenmiş `ENGINE_PART_REPORTERS = ()` içinde adıyla yazılmadıkça testi bozar (taşıma görevi adı ekler); kök dizindeki başıboş modül hâlâ yakalanır | gevşetme olabilir (izinli küme `ENGINE_PART_REPORTERS` ile genişleyebilir, adla) |
| `test_d053_product_no_test_imports` (T0.3) | tarama `game_parts` dosyalarını `__init__.py` olmasa da kapsar; taranan küme game.py -> game.py + game_parts/*.py (helper engine_source_files); aynı sıkılık, yeni dosya da taranır; tohumlu ihlal kanıtı geçti | gevşetme olabilir (taranan küme değişti, genişledi) |
| `test_engine_sensitivity` ve kilit `engine_split_locks/sensitive.json` (T0.7, hassas liste) | Hassas liste spec §5'teki kuraldan geniş. Spec §5: para sözcükleri `currency\|coin\|gold\|money_owner\|pay(` ile yaklaşık 45 işlev öngörüyordu. Kilitte şimdi 87 işlev var. Para sözcüklerine `money\|shop\|merchant\|price` eklendi. `SAVE_NAMES` ve `SNAPSHOT_NAMES` içindeki işlevler artık kendi adlarıyla da işaretleniyor (eskiden yalnız onları çağıranlar). Geri Al komşuları eklendi (`_capture_combat_death_checkpoint`, `_restore_combat_death_checkpoint`, `_restore_in_place`). Ölçüm (2026-11-18): 20 işlev listeye yalnız `shop` sözcüğü yüzünden giriyor; bir kısmı yanlış alarm olabilir. Listeden ad yalnız güçlü inceleyenin yazdığı `removed` satırıyla çıkar; implementer çıkaramaz. Bedeli: T3-T5'te daha çok güçlü inceleme. | sıkılaştırma (spec §5 kuralı değişti) |

### 18.1 game.py bölme T1 (dal `task/game-py-bolme-t1`, onay bekliyor)

| Test | Değişiklik | İşaret |
|---|---|---|
| `test_regression.test_terminal_skill_command` (T1.2) | `runpy.run_path(game.py, run_name="__main__")` artık `SystemExit(0)` ile biter (assert edilir) ve motor tek modül olarak çalışır (`sys.modules["game"] is engine` assert edilir); karakter `mod["_session"]()` yerine `engine._session().character` üzerinden okunur ve varsayılan oturum sonda geri konur; aynı girdiler, aynı üç çıktı iddiası (SKILL CHECK başlığı, `Skill: Stealth`, `Ability Modifier`); eşit sıkılık. Not: bu bir betik testi, unittest bulmaz; betik olarak kırmızı (`mod` bağlanmamış) sonra yeşil koştu | tek modüle karşı yeniden yazıldı; eşit sıkılık |
| `test_sessions.CompatibilityTests.test_exec_namespace_scalars_are_not_a_state_input` -> `test_module_scalars_are_not_a_state_input_for_another_session` (T1.2) | `exec` ile ikinci motor kopyası kuran sözleşme kaldırıldı: motor artık hiç ikinci kopya olarak çalıştırılmaz (`exec`, `runpy`). Yerine içe aktarılmış modülde modül skalerlerinin (`current_hp`, `character_name`) başka bir oturumun durumuna girdi olmadığı sınanır (oturum durumu değişmez, oturumun kendi hp'si serileşir, `serialize_game_state(session=...)` eşit, `current_hp` `vars(game)` içinde yok: ölçüm 2026-11-18 False). Varsayılan oturumun hp ve adı sonda geri konur. Kaldırılan: ikinci kopyanın (`exec` ad alanı) varsayılan oturumunun bu skalerlerle etkilenmemesi iddiası, çünkü ikinci kopya artık yok | sözleşme kaldırıldı, gevşetme |
| `ai-dnd/game.py`, `_GameModule` üstündeki yorum (T1.2) | KADIR BEKLİYOR, dosyaya dokunulmadı. Önerilen yeni metin (satır sayısı aynı, 2 satır): `# Imported modules retain live character aliases. The engine file is never` / `# run as a second copy (exec, runpy); the terminal entry delegates here.` Eski metin: `# Imported modules retain live character aliases. Plain exec dictionaries` / `# must use create_session() and explicit session-owned state instead.` | Kadir'in evetini bekliyor |
| `api/tests/engine_split_locks/size_budget.json`, `long_functions["run"] = 184` (T1.1) | `__main__` terminal döngüsü olduğu gibi `game_parts/terminal.py` içinde `terminal.run` oldu; büyüme yok, yalnız yeni bir yerde uzun işlev girdisi | gevşetme olabilir (yeni uzun işlev izni) |

### 18.2 game.py bölme T2 (dal `task/game-py-bolme-t2`, onay bekliyor)

| Test | Değişiklik | İşaret |
|---|---|---|
| `test_engine_surface.SurfaceTests.test_only_the_module_of_a_moved_name_may_change` (T2.4, Task 18) | Test, `roll_d20`'nin yeni modülünü `"game_parts.character_rules"` olarak elle yazıyordu; Task 18 bu adı altın dosyaya (`surface.json`) koyunca "değişiklik yok" oldu ve `assertNotEqual(..., [])` kırıldı. Yeni değer `"game_parts.another_part"`; ayrıca bu değerin altın dosyadakinden farklı olduğu assert edilir (altın yine değişirse test sessizce anlamsızlaşmaz). Üç iddia aynı: taşınan adın yalnız modülü değişebilir, taşınmayan adın modülü değişemez, imza değişemez | eşit sıkılık (bir iddia eklendi) |
| `test_engine_parts_pilot.WrapperFilter.test_the_wrapper_filter_reads_an_explicit_part_list` (T2.4, Task 18) | beklenen `_PART_MODULES` değeri `()` -> `("game_parts.character_rules",)`; plan bunu Task 14'te önceden yazmıştı | eşit sıkılık |
| `test_engine_move_check.MoveCheckTests.test_a_manual_line_in_game_py_is_exempt_and_echoed` (T2.4 hazırlık, Task 19) | `--manual` biçimi değişti: game.py satırı artık tarafını söyler. Tek `game.py:1:test` yerine `game.py:base:1:test` ve `game.py:new:1:test` verilir (aynı elle düzeltilmiş satır, iki taraftan). İki iddia aynı: el satırı muaf olur ve MANUAL olarak geri yazılır | eşit sıkılık (eski tek giriş artık iki tarafı birden muaf tutmuyor; yeni test `test_a_game_py_manual_line_exempts_only_its_own_side` bunu ayrıca kilitler) |
| `test_engine_move_check.MoveCheckTests.test_a_hand_written_part_line_is_reported_unless_manual` (T2.4 hazırlık, Task 19) | parça girdisi çıplak ad yerine ai-dnd köküne göre yolla verilir: `dice.py:2:...` -> `game_parts/dice.py:2:...`. İki iddia aynı: el satırı bildirilir, el girdisiyle muaf olur | eşit sıkılık (çıplak ad artık hata; `test_a_manual_line_naming_a_file_outside_the_check_is_refused`) |
| `test_engine_parts_pilot.WrapperFilter.test_the_wrapper_filter_reads_an_explicit_part_list` (T2.4, Task 19) | beklenen `_PART_MODULES` değeri `("game_parts.character_rules",)` -> `("game_parts.character_rules", "game_parts.text_rules_a")`; pilot (b) parçası listeye girer (Task 19 Step 3) | eşit sıkılık |
