# Onay listesi: "gevşetme olabilir" satırlarına geriye dönük bakış (2026-11-22)

Kod zaten main'de; bu geriye dönük bir bakış. 'Hayır' dediğin satır için sıkılaştırma işi açılır.

Kaynak: `docs/agents/onay-listesi-20261115.md` bölüm 1-24 (bölüm 19 hariç: 2026-11-19'da onaylandı, yeniden sorulmaz). Sahibin kararı Q5 (2026-11-22). Satır numaraları bu dosyanın 2026-11-22 hâline göredir; her satırda testin adı da yazılı. Okuyan: Opus (Plan 6 Görev 5 Adım 8).

Sayılar: okunan satır 125 (Plan 6'dan önce 120, Plan 6'nın kendi bölüm 24 satırları 5); tek tek 74; mekanik 51; PR #121'in kayıtsız yeniden yazımı 5.

Nasıl ayrıldı:
- **Tek tek:** sınırı gerçekten oynatan her satır (test önce reddettiği bir şeyi artık kabul ediyor ya da daha az şeye bakıyor) ve testi, modülü ya da metni para, kayıt, Geri Al, makbuz ya da deneyim puanına (XP) dokunan her satır.
- **Anahtar sözcük yedeği:** metninde `bakır`, `gümüş`, `altın`, `makbuz`, `receipt`, `kayıt`, `save`, `Geri Al`, `undo`, `deneyim` ile başlayan bir sözcük, `XP` ya da `para` (ekleriyle) geçen satır ne olursa olsun tek tek listededir. Yalnız bu yüzden giren satırın yanında "(anahtar sözcük)" yazar; bu yedek bilerek biraz fazla yakalar (ör. "koruma altında").
- **Mekanik:** geri kalanlar (sayı listesi bir ad büyüdü, test yalnız yeni çağrıyı da sayıyor, sınır daha sıkı oldu). Bunlar bölüm başına tek satırla sayılır.

Öneri sütunu: "onayla" = olduğu gibi kalsın; "onayla, borç açık" = bilinen boşluk borç defterinde satırıyla duruyor; "sıkılaştır" = yeni bir sıkılaştırma işi öneriyorum.

## 1. PR #121, daha önce kaydedilmemiş beş yeniden yazım

PR #121 (dal `task/d249-duzeltme-20261116`, birleşme `e94d81a3`). Kaynak: `D249_DUZELTME_RAPORU_20261116.md` "Açık kalanlar" 1-5 ve birleşmenin test farkı (`git diff e94d81a3^1 e94d81a3`). Bu beş madde onay listesine hiç yazılmamıştı.

1. `test_arrival_narration.Narrate.test_first_visit_keeps_six_sentences_return_keeps_four`. Önce: ilk varış metninin ilk altı cümlesi modelin ilk altı cümlesiydi ("Bir." ... "Altı."). Şimdi: yalnız ilk dört cümle modelden; bütün metin en çok 6 cümle; "Yedi." ve "Sekiz." yok. Neden: varış metnine adsız bir kişinin satırı girdi ve beşinci, altıncı cümlenin yerini alabilir. Kaçabilecek: modelin 5. ve 6. cümlesinin düşmesi artık hata sayılmaz. Öneri: onayla.
2. Kervan durağı (yol durağı) varışı. Önce: şehir dışından şehre girerken metin "Dışarı, ..." diye başlıyordu. Şimdi: "Kent kapısından geçip ..." diye başlar; yeni test `test_arrival_wiring.ArrivalWiring.test_the_whole_shown_arrival_from_a_waystation_is_capped_and_leads_with_the_lead` bunu ve en çok 6 cümleyi denetler. Birleşme farkında eski bir test değişmedi; değişen ürün metni, yeni testle sabitlendi. Kaçabilecek: yok (metin değişikliği). Öneri: onayla.
3. Söylenti iddiasında tam kelime süzgeci (ürün kuralı). Önce: "altın", "zar", "öldü" gibi oyun sözcükleri sözcüğün içinde geçse bile ("altında", "zarar", "öldürdü") söylenti iddiasını siliyordu. Şimdi: yalnız söylenti iddiasında tam kelime aranır, "Kuyunun altında bir kapı var" kalır. Modelin önerdiği yer tanımı eski sıkı süzgeçte kalır (`test_a_model_place_proposal_keeps_the_old_substring_filter`). Kaçabilecek: söylentide "altınlık" gibi bir türev artık süzgece takılmaz; arkasından desteksiz para süzgeci (`without_unbacked_money`) yine çalışır. Para kaydı etkilenmez. Öneri: onayla. (Para sözcüğüne dokunduğu için tek tek.)
4. `test_story_links.HalfTruths.test_it_comes_after_news_and_before_places`. Önce: kişinin bildiklerinin sırası `iş, haber, söylenti, yer`. Şimdi: başa `kasaba` satırı eklendi (`kasaba, iş, haber, söylenti, yer`). Kaçabilecek: yok; sıra yine tam denetlenir, yalnız yeni tür başa girdi. Öneri: onayla.
5. `test_heard_rumours.RumourLane.test_mechanical_words_match_whole_words_only` (yeni test). 3. maddedeki tam kelime kuralını sabitler: beş cümle kalır, altı cümle silinir. Eski bir test değişmedi. Öneri: onayla.

## 2. Tek tek bakılacak satırlar (74)

### Bölüm 2 (PR #80, 2026-11-15'te onaylandı)
- **Satır 37, D-209 para iddia süzgeci.** Önce: "altına/altında/altından" para sayılıyordu. Şimdi: sayılmıyor; "altın", "altını" sayılır. Kaçabilecek: "Kesenden altından üçü düşüyor" gibi nadir bir yalan cümle ekranda kalabilir; kese değişmez. Öneri: onayla.
- **Satır 38, D-210 anlatı büyüsü iddia geçidi.** Önce: altı soyut özne (seçim, karar, zafer, tercih, sıra, söz) iddia sayılıyordu. Şimdi: sayılmıyor. Kaçabilecek: bu sözcüklerle kurulmuş bir büyü iddiası Python satırına düşmeden geçebilir; eşya değişmez. Öneri: onayla.

### Bölüm 4 (2026-11-16'da onaylandı)
- **Satır 60, PR #111.** Dükkân açma (2 test), f04 D05, `test_step0_ledger_play` keseye göre yeniden yazıldı; d229 gösterilen eşya 2'den 1'e; bir tohum 116'dan 163'e; iki yakalanma cümlesi değişti. Kaçabilecek: gösterilen eşya sayısı inince ikinci eşyanın gösterimi artık denetlenmiyor. Öneri: onayla.
- **Satır 61, PR #110** `test_integ_review_fixes...test_a_coin_deal_to_nobody_listed_still_asks_who` yeniden yazıldı (para, D-097). Kaynak: birleşme `9dd001cd` test farkı. Önce: kişisiz okunan para satırı (`person_id: none`) bir konuşma sürerken de (`speaking_with` npc_a) "kime?" diye sorardı (geçersiz yol). Şimdi: aynı soru yalnız kimseyle konuşulmuyorken sorulur; konuşma sürerken kişisiz para satırı konuşulan kişiye bağlanır (yeni test `test_a_coin_deal_with_no_person_in_a_talk_is_for_the_one_talked_to`: geçerli, `purchase`, npc_a). Kaçabilecek: konuşma sürerken oyuncu parayı başka birine demek istediyse ve model kişiyi okuyamadıysa, para önerisi "kime?" sormadan konuşulan kişiye açılır. Öneri: onayla (oynayışta bak).
- **Satır 62, PR #109.** Ön okuma tavanı 400'den 700'e. Kaçabilecek: 400-700 arası uzun bir okuma artık hata sayılmaz (daha çok yerel model süresi). Öneri: onayla.
- **Satır 63, PR #107.** Kaçak döngü tavanı 240'tan 480'e. Kaçabilecek: döngü iki kat uzun sürünce yakalanır. Öneri: onayla.
- **Satır 64, PR #114** (para). Söylenen tutar metinde kalır; "İşte bu yüzden sana para vermem." silinir; para ya da kese adı geçen al/tut/işte/buyur cümleleri silinir. Kaçabilecek: kesenin değiştiğini söyleyen ama tutar vermeyen bir cümle. Öneri: onayla.
- **Satır 66, önceki dalgalar (D-109, D-166, kalan sayaç, D-231, #84).** Ayrıntı bu listede değil, KOD 2 devir notunda; D-231 kese ve eşya aramasıdır (para). Kaçabilecek: doğrulamadım; bu satırların test farkını okumadım. Öneri: onayla (zaten onaylı); ayrıntı istersen ayrı bakılır.

### Bölüm 5 (D-249 + D-250 tasarım dalı)
- **Satır 76, `test_story_links.test_a_person_carries_one_at_most`.** Önce: bir kişinin bildiği en çok 5. Şimdi: `town_knowledge.MAX_ITEMS` = 10. Kaçabilecek: 6-10 madde taşıyan kişi artık hata değil (bilerek). Öneri: onayla.
- **Satır 77, `test_arrival_narration` uzun anlatım.** Önce: son anlatım 400 harf. Şimdi: 8 cümlelik anlatım 6'ya kesilir, son anlatım 1 200 harfe kadar. Kaçabilecek: 400-1 200 harf arası metin artık uzun sayılmaz. Öneri: onayla.

### Bölüm 7 (yuva kırmızıları)
- **Satır 94, `test_spells_v1.test_cure_wounds_heals_during_combat_and_refuses_to_open_combat`.** Önce: savaş dışında Cure Wounds reddedilirdi. Şimdi: savaş dışında iyileştirir, bir büyü yuvası harcar, savaş açmaz (senin D-056 kararın). Kaçabilecek: yok; eski iddianın tersi bilerek. Öneri: onayla.
- **Satır 95, `test_journey_real_run` TheNetworkGuard** (anahtar sözcük). Yuvada biri atlanır, öteki başka soket türüyle koşar; CI'da ikisi eskisi gibi. Kaçabilecek: yalnız yerel yuvada bir ağ hatası görünmez; CI görür. Öneri: onayla.

### Bölüm 8 (BM görev 1)
- **Satır 105, `test_front_money...test_say_mode_reads_every_line_and_coin_stays_the_owners`.** Önce: parasız söz satırı okunmazdı. Şimdi: her satır okunur; parasız satırda para 0, para satırı yine 50. Kaçabilecek: yok; para iddiası aynı sıkı. Öneri: onayla.
- **Satır 106, `...test_a_coin_line_asked_of_the_dm_is_read_but_its_coin_is_never_taken`.** Önce: anlatıcıya sorulan satır okunmazdı. Şimdi: okunur ama okunan para alınmaz (`_front_coin == 0`). Kaçabilecek: yok. Öneri: onayla.
- **Satır 107, `...test_a_say_line_without_coin_is_read_once_and_asks_no_second_call`.** Önce: öneri adımı kendi çağrısını yapardı. Şimdi: ön okuma o çağrı, en çok 2 çağrı. Kaçabilecek: yok (para modülü olduğu için tek tek). Öneri: onayla.
- **Satır 110, davranış sınırı BM T1.** Kişi seçili düz `say` satırında eski kelime yolları oda kartını artık hazırlamaz; kararı modelin okuması verir. Kaçabilecek: model okumayı kaçırırsa "oda istiyorum" satırı oda kartı açmaz (para hareketi yok, güvenli yön). Öneri: onayla.

### Bölüm 10 (BM görev 3)
- **Satır 129, davranış sınırı BM T3.** Anlatıcıya sorulan satırda model listedeki bir kişiyi adlandırırsa o kişi konuşur; bilgi kapısı ve rol listesi o yolda çalışmaz. Kaçabilecek: model yanlış kişiyi adlandırırsa bilgi kapısının hazır cevabı gelmez. Öneri: onayla (oynayışta bak).

### Bölüm 11 (BM görev 4)
- **Satır 139, davranış sınırı BM T4** (para, iş ücreti). Okuma "iş" demiyorsa kelimeyle iş yakalama çalışmaz: "Paramı ver" ücret ödetmez; paket alma ve sözle teslim okuma olmadan yakalanmaz. Kaçabilecek: model `take` ya da `hand_over` okumazsa paket yerinde kalır, ücret ödenmez (güvenli yön; para yanlış yöne akmaz). Öneri: onayla (oynayışta bak).

### Bölüm 12 (BM görev 6)
- **Satır 147, `test_arrival_narration.Narrate.test_world_is_identical_with_and_without_the_call`.** Önce: iki yolda dünya tamamen aynı. Şimdi: `scene_state.arrival_text` dışında aynı (kayıtlı varış metni; Geri Al geri alır). Kaçabilecek: o tek anahtarda iki yolun farkı karşılaştırmadan çıktı; anahtar dönen metne eşit diye ayrıca denetleniyor. Öneri: onayla.

### Bölüm 13 (BM görev 7)
- **Satır 161, yolculuk 41 `is_haberi_sokakta`.** Önce: sokaktaki kişi işi kendi sözüyle anınca iş "duyuldu" olurdu. Şimdi: işin kendi cümlesini söylemesi gerekir. Kaçabilecek: başka sözlerle anlatılan bir iş günlüğe düşmez. Öneri: onayla (oynayışta bak).

### Bölüm 14 (BM görev 8)
- **Satır 177, `test_world_keeps_its_word.LeavingTown` üç test.** Önce: ilk "yola devam" uyarır ve hiçbir şey kıpırdamazdı. Şimdi: uyarır ve bir sonraki yola yürür: konum değişir, saat tam +1 saat; gün süren yolculuk ya da uzak şehre varış yok. Kaçabilecek: yok; yeni davranış tam sayıyla denetleniyor. Öneri: onayla.

### Bölüm 16 (BM görev 9)
- **Satır 189, `test_carius_fifth_play.TheRoadOnIsNoWall`.** Önce: ilk "yola devam" durakta kalırdı. Şimdi: uyarır ve yürür; ikinci yürüyüş uyarısız. Kaçabilecek: ilk "yola devam" artık durdurmaz; yanlışlıkla söylenen satır oyuncuyu uyarıyla birlikte yürütür. Öneri: onayla.

### Bölüm 17 (BM son düzeltme)
- **Satır 195, `test_ready_line_share.ReadyLineShare`.** Önce: hazır satır payı yalnız kaynağı bilinen satırlardan. Şimdi: payda bütün oyuncu satırları; kaynaksız satır `unknown` sayılır. Kaçabilecek: bir ölçüm tanımı değişti; eski ve yeni pay birbiriyle karşılaştırılamaz. Öneri: onayla.
- **Satır 196, `test_narration_source_record...test_no_other_engine_module_reports_a_source`.** Önce: anlatı kaynağı bildirebilen modül kümesi daha dardı. Şimdi: `front_proposal.py` (rota günlüğü) izinli; küme yine tam eşitlikle denetlenir. Kaçabilecek: o modül yanlış kaynak yazarsa bu test yakalamaz. Öneri: onayla.

### Bölüm 18 (game.py bölme T0)
- **Satır 204, `test_refusal_census.RefusalCensus`.** Yasaklayan taramalar artık bütün motor dosyalarına bakar (daha sıkı); ama "`combat_refusal_turn` `note` çağırır" olumlu iddiası artık herhangi bir parçada sağlanabilir. Kaçabilecek: olumlu iddia daha kolay geçer. Öneri: onayla.
- **Satır 207, `test_game_name`** (kayıt biçimi kimliği). Afiş yasakları bütün dosyalarda (daha sıkı); `UNWRITTEN` afişi ve `"format": "ai-dnd-save"` kayıt kimliği herhangi bir parçada bulunursa geçer. Kaçabilecek: kimlik yanlış dosyada dursa da test geçer; kayıt biçimi aynı. Öneri: onayla.
- **Satır 208, `test_tr_names...test_game_prompt_carries_the_narrator_note`.** `_dm_prompt_note(` en az 2 kez: tanım ve çağrı ayrı dosyalarda da sayılır. Kaçabilecek: çağrı kaybolup iki tanım kalsa test geçer (bugün böyle değil). Öneri: onayla.
- **Satır 210, `test_narration_source_record.TheListIsTheEngines` (iki test).** Kaynak bildiren parça `ENGINE_PART_REPORTERS` listesine adıyla yazılırsa kabul edilir. Kaçabilecek: liste adla genişler; her genişleme diff'te görünür. Öneri: onayla.
- **Satır 221, `size_budget.json` `long_functions["run"] = 184`.** Terminal döngüsü `game_parts/terminal.py` içine taşındı, yeni uzun işlev izni. Kaçabilecek: yok (büyüme yok). Öneri: onayla.
- **Satır 232, `test_engine_routing.RoutingAuditTests` R1-R7.** Yardımcı R8 bulgularını süzer; eski "yalnız kendi kuralı" testleri R8'i görmez. Kaçabilecek: yok; R8'in kendi testleri ve bütün ağaç testi on üç kuralı koşar. Öneri: onayla.
- **Satır 242, N7 kapı kuralı "DOWN boş".** İşlev başına sayı artışı kapıyı durdurmaz, defterde açıklanır. Not: N7 Plan 6 sonunda zorunlu adım olmaktan çıktı (bölüm 24 satır 484). Kaçabilecek: bir işlevde çalışan satır sayısının artması kapıyı durdurmaz; defterdeki açıklama yanlışsa artış gözden kaçabilir. Azalma (DOWN) yine durdurur. Öneri: onayla.
- **Satır 243, `F_fon` geçme kuralı** (para D-370, kayıt D-371). 304 bilinen bayrak açık kırığı kapıda kırmızı saymıyordu. Kaçabilecek: o 304 içinde yeni bir kırık gizlenebilirdi. Durum: bayrak açık kırıklar `task/fon-a` ile düzeldi; Plan 5 ve Plan 6 kapıları `failing_ids 0` istiyor. Öneri: onayla.

### Bölüm 20 (bayrak açık düzeltmeleri)
Bölümün ortak anlamı: test artık ön okumayı da tam sayıyla sayıyor (0 çağrı yerine tam `['front']`) ya da başka bir yolu koşuyor.
- **Satır 290, `test_front_proposal.FrontTable...` (yaklaşık 31 sınıf).** Önce: okuma kesintisinde tur 200 ile oynardı. Şimdi: 503 "tekrar dene", sonra satır yeni kimlikle oynar (senin G6 kararın). Kaçabilecek: okuma kesintisinde tur artık oynamaz; "kesintide tur yine oynar" güvencesi bu sınıflarda denetlenmiyor, oyuncu satırı yeniden yazar. Öneri: onayla.
- **Satır 291, `test_front_failed_fallback` (13 yer, "evet" testi, kayıt testi).** Kesinti yerine "kullanılamaz okuma"; D-240 kurtarması `fallback:failed:<kind>` altında artık denetlenmiyor. Kaçabilecek: o kurtarma yolu bozulursa bu dosya görmez. Öneri: onayla, borç açık (D-406).
- **Satır 292, `test_d109_timing` hırsızlık ve `test_everyday_gate`.** Başarısız okuma yerine kullanılamaz cevap. Kaçabilecek: başarısız okumada hırsızlık sorusu bu testte denetlenmiyor. Öneri: onayla, borç açık (D-407 belge dizesi).
- **Satır 297, `test_stage10b...test_before_resolution_failure_restores_state_rng_and_has_no_receipt`** (makbuz, Geri Al). Hata türü değişti; iki bayrakta da 503, durum ve zar geri döner, makbuz yok. Kaçabilecek: yok; geri alma ve makbuzsuzluk aynı sıkı. Öneri: onayla.
- **Satır 298, `test_stage10b...transport_failure_persists_and_replays_without_retry`** (kayıt, yeniden oynatma). Okuma `{}` döner, öteki çağrılar düşer. Kaçabilecek: okuma kesintisi bu testte değil, satır 290'da. Öneri: onayla.
- **Satır 299, `...creation_replay_duplicate_resume_and_session_isolation` (iki dosya, dükkân işlemi).** Yinelenen satır 0 yerine tam bir ön okuma çağrısı. Kaçabilecek: yok; işlem ve oturum ayrımı aynı. Öneri: onayla.
- **Satır 300, `test_model_failure_never_locks...low_token_cap`.** Döngü koruması bayrak açıkken denetlenmiyor. Kaçabilecek: bayrak açık yolda döngü koruması bozulursa bu test görmez. Öneri: onayla, borç açık (D-407).
- **Satır 305, `test_coin_writers` ve `test_economic_room.CoinWithTheLine` 4 test** (para). Bayrak açık: ekilmiş para yerine betikli amaç okuması; bayrak kapalı değişmedi. Kaçabilecek: bayrak açık bu satırlarda başarısız okuma denetlenmiyor (G11 testleri denetliyor). Öneri: onayla.
- **Satır 308, `test_d231_person_gear...takes_its_purse_and_its_gear`** (kese). 0 çağrı yerine bayrak açık tam `['front']`. Kaçabilecek: yok; kese ve eşya iddiaları aynı. Öneri: onayla.
- **Satır 313, `test_intent_response_consistency` (on iki test)** (anahtar sözcük: `save_resume`). `calls == 0` yerine `['front'] * n`. Kaçabilecek: yok; çağrı sayısı yine tam (okunan satır kadar ön okuma, başka çağrı yok); satır yalnız çağrı beklentisini değiştirdi. Öneri: onayla.
- **Satır 324, `test_narration_receipt_contract` `enter()` (8 test)** (makbuz). `calls == 0` yerine `read_first()`; gizli sahne denetimi ön okuma isteğini de tarar (daha geniş). Kaçabilecek: yok; çağrı türleri tam denetleniyor, makbuz iddialarını satır değiştirmedi. Öneri: onayla.
- **Satır 326, `test_f04_creation_authority` 7 test** (kayıt hatası). `read_first()`; kayıt hatası yeniden denemesi iki okuma. Kaçabilecek: kayıt hatasından sonraki yeniden deneme bir ön okuma daha yapar; bu fazla çağrı artık hata değil (tam iki, fazlası yine kırmızı). Öneri: onayla.
- **Satır 327, `test_campaign_api...invalid_conditional_conversation_rejects_before_interaction_effects`.** Bayrak açık tür listesi; geçersiz önerinin bayrak açık okunup reddedildiği gösterilmedi. Kaçabilecek: bayrak açık yolda geçersiz koşullu konuşma. Öneri: onayla, borç açık (D-415).
- **Satır 328, `test_campaign_api.test_free_npc_profile_statement`.** Yalnız bayrak kapalı koşar. Kaçabilecek: bayrak açık konuşma zarfı bu testte hiç sorulmuyor. Öneri: onayla, borç açık (D-413).
- **Satır 331, `test_campaign_api...unpunctuated_locked_followup_reaches_same_npc_door_context`** (kayıt hatası geri alma). Python'un "kilitli" cevabı ve iki odak denetimi yalnız bayrak kapalı; bayrak açıkta kayıt hatası geri alma, yeniden deneme, bellek geri alma ve yeniden oynatma denetleniyor. Kaçabilecek: bayrak açıkta kilitli kapı cevabının Python'dan geldiği. Öneri: onayla, borç açık (D-414).
- **Satır 335, `test_npc_initiative...exploration_can_include_one_contextual_initiative_and_replay`.** `<= 2` çağrı yerine tam türler; tur sınırı inisiyatifte 2'den 3'e. Kaçabilecek: bayrak açık inisiyatifli turda model çağrısı 2'den 3'e çıktı; bu fazla çağrının süresi hata sayılmaz. Türler tam denetlendiği için başka bir çağrı yine yakalanır. Öneri: onayla.
- **Satır 346, `test_campaign_api...reopened_verified_city_ruler_answer_preserves_lore_and_history`** (yeniden açılan kayıt). Model yalnız ön okumayı yanıtlar; satır başına tür listesi. Kaçabilecek: doğrulamadım (test gövdesini okumadım); satır yalnız sahte modelin cevabını ve çağrı türlerini değiştirdi, bilgi ve geçmiş iddiaları satırda değişmedi. Öneri: onayla.
- **Satır 347, `test_npc_player_address` `introduce` yardımcısı (6 test, ad kayıttan sonra da kalır).** 0 çağrı yerine bayrak açık tam `['front']`. Kaçabilecek: yok; tam bir ön okuma bekleniyor, bayrak kapalı yine 0. Öneri: onayla.
- **Satır 362, `test_smoke_turn_diagnostics...captures_checkpoint_before_native_turn`** (Geri Al anlık görüntüsü, kayıt 1). Bayrak açık tam bir ön okuma. Kaçabilecek: yok; tam bir ön okuma bekleniyor, bayrak kapalı yine 0; Geri Al anlık görüntüsü (kayıt 1) iddiasını satır değiştirmedi. Öneri: onayla.
- **Satır 375, `test_companion_wait_regressions.FreeDialogueWaitApiTests` (4 test, kayıt hatası geri alma).** Satır başına `with_reading()`; kayıt hatası iki okuma; yeniden oynatmanın çağrı yapmadığı denetimi eklendi (daha sıkı). Kaçabilecek: kayıt hatası testinde başarısız denemenin okuması yeniden denemede bir kez daha yapılır (tam iki okuma, fazlası kırmızı); kayıt geri alma iddiasını satır değiştirmedi. Öneri: onayla.
- **Satır 380, `test_front_failed_fallback` şehir dışına yürüme ve yolda soygun** (soygun = para). Kesinti yerine kullanılamaz okuma; D-377 durumları kesintide değil kullanılamaz okumada koşuyor. Kaçabilecek: okuma kesintisinde soygun yolu bu testte yok (G6: kesinti artık 503). Öneri: onayla.
- **Satır 384, `test_step4_branches.Branches.line` (6 test, ücret dahil).** `chat_calls <= 1` yerine tam türler (daha sıkı). Ücret testi içerdiği için tek tek. Kaçabilecek: yok (daha sıkı). Öneri: onayla.
- **Satır 385, `size_budget.json` game.py 22 670 -> 22 727** (onaylandı 2026-11-19). Bugün game.py 1 400 satır; bu sınır geçmişte kaldı. Kaçabilecek: yok; sınır bugün 1 450 (satır 479). Öneri: onayla.
- **Satır 386, `_front_step` 231 -> 235** (onaylandı 2026-11-19). Kaçabilecek: işlev 4 satır daha uzun olabildi; yalnız boyut sınırı, davranış değil. Öneri: onayla.
- **Satır 387, `_run_player_turn_internal` 2 743 -> 2 756** (onaylandı 2026-11-19). Kaçabilecek: işlev 13 satır daha uzun olabildi; yalnız boyut sınırı, davranış değil. Öneri: onayla.

### Bölüm 21 (bölme Plan 3)
- **Satır 396, `test_engine_probe_tools`** (anahtar sözcük: "kayıt testi"). Karışık ağaçta çıkış 2 "ret" yerine 1 "kırık"; ikisi de sıfır değil, dosya yine yazılmaz. Kaçabilecek: çıkış kodunu "2 = ret" diye ayıran bir betik karışık ağacı artık "kırık" (1) görür; dosya yine yazılmaz. Öneri: onayla.
- **Satır 398, `test_engine_routing` R11.** Yamalanan yerleşik ada yalnız `builtins.`/`io.` üzerinden ulaşım bulgu sayılır. Satırdaki kör nokta (`from builtins import open` yapan modül) Plan 4 Görev 2'de kapandı (D-440 kapalı). Kaçabilecek: `from io import open` gibi dar biçimler (bugün motorda yok). Öneri: onayla.
- **Satır 411, parça zaman aşımı 3 000 s -> 4 500 s**. Kaçabilecek: gerçek bir takılma 25 dakika geç yakalanır. Öneri: onayla.
- **Satır 412, paket hızı duvar saatiyle.** En uzun parçayla ölçülse bayrak açık paket sınırı %0.4 aşardı. Kaçabilecek: en uzun parça ölçüsündeki %0.4'lük aşım (1.104) duvar saatinde görünmez. Öneri: onayla.

### Bölüm 22 (bölme Plan 4)
- **Satır 419, `test_engine_patch_census` `DYNAMIC_REASONS`.** Sayım, `test_engine_module_alias.py` içinde hesaplanan yama adını hedefe çözmeden kabul eder. Kaçabilecek: o dosyada yeni bir dinamik yama adı. Öneri: onayla.
- **Satır 422, `_batches_are_movable` T5.** Hassas adlar (para/kayıt/ölüm) taşınabilir; karşılığında güçlü inceleme ve `move_check --tier strong`. Kaçabilecek: para/kayıt/ölüm adı T5 partisinde taşınırken bu test kırmızı vermez; koruma güçlü incelemeye ve `move_check --tier strong`'a kaldı. Öneri: onayla.
- **Satır 423, `test_every_re_export_is_the_parts_own_object`.** Anlatı adaptörü takılıyken sarmalayıcı, yakaladığı özgün nesne aynı denetimden geçerse kabul. Koruma testi yanlış nesneyi yine reddeder. Kaçabilecek: adaptör takılıyken sarmalayıcının kendisi değil, yakaladığı özgün nesne denetlenir; sarmalayıcının kendi davranışı bu testte görülmez (test yalnız kimliğe bakar). Öneri: onayla.
- **Satır 425, M12 yazıcı taraması.** `held=0` yerine: tutulan yazıcı yolları Görev 4'te kaydedilen kümeye tam eşit ve her biri adlı bir testle kapalı. Kaçabilecek: kayıtlı kümede olan bir yol tek başına taşımayı durdurmaz. Öneri: onayla.

### Bölüm 23 (bölme Plan 5)
- **Satır 450, M12 yazıcı taraması (Plan 4'ten taşındı).** Satır 425 ile aynı kural. Kaçabilecek: kayıtlı kümede olan bir yol tek başına taşımayı durdurmaz. Öneri: onayla.
- **Satır 451, `move_block` N3 kural 6.** Bir işlevin içindeki `locals(` ya da `sys.modules`, `identity_allowlist.json` satırı adlandırırsa taşınır; öteki her kullanım yine reddedilir. Kaçabilecek: izin listesinde satırı olan bir `locals(`/`sys.modules` kullanımı kendiliğinden geçer; satırın doğruluğu incelemeye kalır. Öneri: onayla.
- **Satır 452, `_batches_are_movable` T6 (Geri Al koruması).** Altı tur partisinde hassas adlar taşınabilir; yeni koruma Geri Al geri yüklemesinin `game.py`'de kaldığını denetler. Kaçabilecek: Geri Al geri yüklemesi dışındaki hassas adlar (67 adın 31'i) taşınırken bu test kırmızı vermez; koruma güçlü incelemeye ve `move_check --tier strong`'a kaldı. Öneri: onayla.
- **Satır 455, `identity_allowlist.json` ilk satır** (`turn_front.py` `_local_place_turn` `sys.modules`). Kaçabilecek: o işleve sonradan eklenen ikinci bir `sys.modules` kullanımı da muhtemelen geçer (doğrulamadım: satır dosyayı, işlevi ve adı anar, yeri anmaz). Öneri: onayla.
- **Satır 462, `identity_allowlist.json` iki satır** (`turn.py` `_run_player_turn_internal` `sys.modules` ve `locals`). Kaçabilecek: o işleve sonradan eklenen ikinci bir `sys.modules` ya da `locals(` kullanımı da muhtemelen geçer (doğrulamadım, satır 455 ile aynı). Öneri: onayla.
- **Satır 463, `size_budget.json` `turn.py` 3 667** (2 500 parça sınırının üstünde; bundan sonra yalnız küçülebilir). Kaçabilecek: `turn.py` 2 500 sınırının 1 167 satır üstünde kalabilir; büyüyemez. Öneri: onayla; tur bölme dilimi küçültecek.

### Bölüm 24 (bölme Plan 6, bu dal)
- **Satır 479, `size_budget.json` game.py 1 450 ve `test_game_py_is_within_the_spec_cap`**. Bütçe gerçek boyut + 50 satır pay; tavan testi (< 1 500) sıkılaştırma. Kaçabilecek: game.py 50 satıra kadar büyüyebilir, her kullanım bir Ruling ve onay satırı ister. Öneri: onayla.
- **Satır 484, N4, N5, N7, N8 zorunlu kapı adımı olmaktan çıktı**. Betikler ve testleri CI'da kalır; para ya da kayıt işlevi için `sensitive.json` satırı, güçlü inceleme ve onay satırı yine şart. Kaçabilecek: bölme dışı işlerde bu araçlar artık kendiliğinden koşmuyor. Öneri: onayla.
- **Satır 8 (Görev 5 ile yazılır), ölü kod koşul 1.** Bölmenin kendi defter dosyaları (kilitler, parti dosyaları, plan belgeleri) "kullanım" sayılmaz; bölme sabitleme testleri ayrı sütunda gösterilir. Kaçabilecek: yalnız defterde adı geçen bir işlev "kullanılmıyor" görünür; silmek yine dört koşulu ve senin satır satır "evet"ini ister. Öneri: onayla.

## 3. Mekanik satırlar (51)

- Bölüm 4: 1 satır (PR #113: hata yerine "henüz motorda yok", aynı sıkılık).
- Bölüm 5: 4 satır (konuşma şemasına `mentions` eklendi; yerel model bulut üslup bloğu; `AI_DND_*` ad sayısı 36'dan 37'ye).
- Bölüm 7: 1 satır (`test_model_chain` iki süreç testi yalnız yerel yuvada atlanır; iş parçacıklı eşi hep koşar).
- Bölüm 9: 1 satır (okuma ömrü kısaldı, aynı değerler aynı sıklıkta).
- Bölüm 13: 5 satır (şemaya `voiced` eklendi; iki sınır daha sıkı oldu).
- Bölüm 15: 1 satır (kendi söylentisi tehditten önce; iki yuva yine dolu).
- Bölüm 18: 6 satır (yasaklayan taramalar `game_parts` dosyalarına genişledi: daha sıkı).
- Bölüm 20: 28 satır (test ön okumayı da tam sayıyla sayıyor; bayrak kapalı ikizi olan bayrak kapalıya sabitleme).
- Bölüm 21: 1 satır (`move_check` aralığa dayalı karşılaştırma; eski testler değişmedi).
- Bölüm 22: 1 satır (beklenen çağrı yeri `game.py` yerine `game_parts/combat_flow.py`, tam eşitlik).
- Bölüm 24: 2 satır (boş satır silme, `ast.dump` eşit; `_narrate_resolved_turn` game.py'de kaldı, boyut hedefi tutuyor).

Toplam: 51 mekanik satır.
