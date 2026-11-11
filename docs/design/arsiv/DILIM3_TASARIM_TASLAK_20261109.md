# DİLİM 3 TASARIM TASLAĞI: dünya davranışları + ilk 10 dakika + 3a kanıtı

Durum: TASLAK, Kadir'in kararlarını bekliyor (§3). Kod yok, test koşulmadı, model çağrılmadı, commit/push yok. Tarih 2026-11-09.
Kod gerçekleri `AI-DND-c-merge` (`task/c-series-merge`, HEAD 827ffd60, Dilim 1 içinde) üzerinden, önce `graphify query` ile, sonra yalnız gösterilen satırlar okunarak alındı. Dilim 2 kodu `task/dilim2-quests-refusals-20261104` dalındadır (c-merge'den 8 commit ileride); ondan beklenenler §4'te ayrı yazılı. Satır numaraları 827ffd60'tandır, Dilim 2 birleşince kayar; plan işlev adıyla arar.
Madde numaraları `CANLI_OYUN_NOTLARI_20261103.md`'den. **Numara notu:** yol haritasındaki "Etkileşime geç 7/16/18" üç ayrı listeden gelir: 7 = `HANDOFF_ARSIV_20261104.md` önem listesi, 16 = notlar madde 16 (ve aynı şikâyet madde 11), 18 = EK 5 T18 (yani 118). Bu belgede üçü birlikte "Etkileşime geç (11/16/118)" diye anılır.

## 0. Tek sayfa özet (Kadir için)

**Bu dilim ne yapıyor?**
- **Çıkışlar (21/105):** Sokakta kaçış "çıkış göremiyorsun" demez. Bugün şehrin kendisi hiçbir yere bağlı değil. Öneri: her şehre bir kez "yan sokak" açılır (K1).
- **"Etkileşime geç" (11/16/118):** Düğme yalnız tıklanabilirken görünür. Bugün ekran süresi dolmuş olayı gösteriyor, motor reddediyor.
- **Dışarı çıkınca başka yere geçme (42):** Motor yolu doğru; büyük ihtimalle modelin seçimi. Önce gerçek zincirde ölçülür.
- **Cinayetin sonucu (47):** Tanık her durumda o turda tepki verir. Bugün sokakta (çıkış yok) hiçbir şey yazılmıyor.
- **Anlatı (43–46):** "Barmen (başını kaldırır): …" kalkar; iskeleye "içeri adım atıyorsun" denmez; boş kalıpların kaynağı ölçülüp kesilir; "Aleykümselam" istemden çözülür (yasak listesi yok).
- **Bayat ipucu (50):** Han içinde sokak olayı görünmez (katalog verisi).
- **İlk 10 dakika (49):** Açılışta motorun kaydettiği gerçek bir olay görünür; oyuncu boşta kalırsa dünya bir kez daha gelir (K2). Hazır görev, sabit açılış yok.
- **3a kanıtı:** Küçük gerçek sahnede fırsat → seçim → tepki → kayıt → sonraki konuşma → kaydet/aç zinciri; haberci bu zincirde. Geçmezse Dilim 4 yok.

**Motorun kesin sözleri (önerilen):** (1) Çıkış kararını tek yer verir; kaçış, tanığın kaçışı, Dünya paneli ve "dışarı" seçeneği aynı kaydı okur. (2) Ekranda görünen bir düğme, motorun o anda kabul edeceği bir eylemdir. (3) Reddedilen bir tıklama Türkçe ve nedenli söylenir. (4) İlk dakikadaki olay motorun kaydıdır, yapay zekâ uydurmaz. (5) Para, kayıt, Geri Al senaryoları her görevde yeşil kalır.

**Doğrulanmayanlar:** 42'nin kökü, 46'nın kaynağı (hangi model), 43'ün gerçek oyundaki yolu, 118'in kesin nedeni (ayrıntı §6).

---

## 1. Amaç, başarı ölçüsü, kapsam

**Amaç (tek cümle):** Oyuncunun dünyada hareket ettiği, bir olaya karıştığı ya da bir suç işlediği anlarda dünya kayda dayalı ve tutarlı karşılık versin; oyunun ilk dakikalarında peşine düşülecek gerçek bir şey olsun; ve "okuma/kayıt ayrı, makbuz, geri al, haberci zinciri" küçük gerçek bir sahnede kanıtlansın.

**Başarı ölçüsü (Kadir'in):** 30 dakika oyna, en az 2 gerçek iz bul, birinin peşine düş, seçiminin sonucunu gör, "şimdi ne olacak?" de. Dilim 2 izleri görünür kılar; Dilim 3 izlerin oyunun başında da var olmasını (49) ve oyuncunun yaptığının dünyada karşılık bulmasını (47, 118) sağlar. Ölçü ancak Kadir'in oynayışında görülür; dilim kapısı oynayışı beklemez (2026-11-04 gevşetmesi), deftere "oynayış bekliyor" yazılır.

**Kapsam (yol haritası §5):** Güvenilirlik: 21/105, 11/16/118, 42, 47, 43–46, 50. Oyun hissi: 49 (ilk 10 dakika); 48 (iş bulma döngüsü) yol haritasında var ama bu taslağın istenen listesinde yok: karar K7. 3a kanıtı kapıya eklenir.

**Kapsam dışı:** ölüm modları, XP/seviye, büyüler, sınıf özellikleri (Dilim 4); Dilim 2'nin işleri (görev günlüğü, izler, konuşma kipi, ret metinleri, silah); yeni şehir/kendi dünya (eski Adım 6); yoldaş (T14); para yolunun kendisi (Dilim 1); savaşta dikkat şeridinin gizlenmesi (24) yalnız §2.2'deki tek kuraldan bedava gelir, ayrı iş açılmaz; arayüz cilası.

**Kurallar:** model önerir, Python doğrular ve kaydeder; yeni kelime listesi / regex doğrulayıcı YOK; reddetmek yerine onar; para/kayıt/Geri Al sıfır tolerans; her dilim `game.py`'den yalnız kendi parçasını çıkarır.

## 2. Maddeler

Her madde: **Bugün** (kodda doğrulanmış) · **Öneri** · **Sahip** · **Test işareti** · **Risk**.

### 2.1 Çıkışlar ve kaçış (21, 105)
**Bugün.** Kaçış `combat_lifecycle.flee` (`combat_lifecycle.py:211-246`): çıkış = bulunduğun yerin `exit_location_id` ya da `parent_location_id`'si; yoksa "Buradan sıyrılabileceğin bir çıkış göremiyorsun; kavga seni bırakmıyor." ve tur kaybı. Aynı kural ikinci kez `bold_acts._way_out` (`bold_acts.py:150-153`) içinde yazılı (tanığın kaçışı). Bu iki alanı yazan yerler binalar ve alt mekânlardır (`local_places.py:417-418`, `grounded_action.py:1277-1306`, `game.py:16280-16281`, `incidents/sublocations.py:80-81`); şehrin kendisi (sokak, başlangıç sahnesi) bir üst mekâna bağlı değil, yani orada çıkış yok. Senaryo 09c bilinen kırık [21]; 09d (handan kaçış) geçiyor: Turgut'un "Kaçacak bir açık bulamıyorsun"u tutmayan Acrobatics zarıydı (105 çözüldü sayılır, işaret yok). T5 ek bulgusu: Dünya paneli "geçit yok" yazan yerden kaçış mümkün oldu; panelin hangi alanı okuduğu DOĞRULANMADI.
**Öneri.** Tek sahip `exits.py` (yeni, `game.py` dışı): `way_out(world, location_id) -> str | None`. Bina/alt mekân: bugünkü kural aynen. Şehir (yerleşim) için: K1 kararına göre (önerim A) yerleşimin "yan sokak" yeri ilk gerektiğinde bir kez açılır (`local_places` düzeniyle, yerleşimin çocuğu, kendi çıkışı sokağa), sonra hep aynısı kullanılır. `flee`, `bold_acts._way_out`, Dünya panelinin geçit satırı ve ön okumanın `outside` satırı `exits.way_out`'u okur. Kaçışın zarı ve tur kaybı bugünkü gibi kalır (D&D'ye uygun; Kadir'in "sınırsız deneme, garantisiz başarı"sı). Çıkışsızlık gerçekten varsa (kilitli mahzen, 09b) metin ne yapabileceğini de söyler: "Çıkış yok; dövüşmeye devam edebilir ya da teslim olabilirsin." (metin Dilim 2 `refusals` üzerinden, K6).
**Sahip.** `exits.py` (karar), `local_places` (yerin kaydı), `combat_lifecycle` ve `bold_acts` yalnız okur.
**Test.** 09c işareti kalkar; 15'in [21] yarısı kalkar; yeni birim: `exits.way_out` her mekân türü için; kaynak sayımı testi: ürün kodunda `exit_location_id or parent_location_id` ifadesi `exits.py` dışında yok. Yeni senaryo "yan sokaktan geri dönüş" (kaçtıktan sonra sokağa dönülür, kayıt/yenileme aynı).
**Risk.** Yeni yer açmak kayıt biçimine dokunur (eski kayıtlarda yan sokak yok: ilk ihtiyaçta açılır, onarım gerekmez). Yer sayısı sınırı (`local_places`: yerleşim başına en çok yer, toplam 80) dolu bir kampanyada yan sokak açılamazsa? Öneri: sınır yan sokak için bir yer ayırır. Bağımsız inceleme ister (yer değişimi savaşı bitirir, kayıt).

### 2.2 "Etkileşime geç" (11, 16, 118)
**Bugün.** Arayüz `ambient-event-actions.tsx`: düğme, sahnedeki olayın göndergesi `lifecycle == "presented"` ise görünür (`isActiveBlueAmbientEvent`, :16-29). Motor `GameSession.resolve_ambient_event_action` (`game.py:22762-22871`) ayrıca süreye bakar: gönderge `expires_after_turn` geçtiyse `REJECTED/event_expired` (:22826-22834). Süre 12 tur (`living_world.create_scene_referent`, :1591). Süre dolunca göndergeyi `expired` yapan `living_world.expire_referents` yalnız "çevreye bak" metinleri kurulurken çağrılıyor (`game.py:16677`, `16766`); API görünümü (`living_world.public_scene_projection`, :2015-2103) süreye bakmadan `presented` göndergeyi yolluyor. Sonuç: ekran süresi dolmuş olayı gösterir, tıklama reddedilir. Arayüz bütün `REJECTED` nedenlerini tek cümleye indiriyor (:83-88, "Şu anda buna müdahale edemiyorsun."). `promotion_unavailable` ise `NO_EFFECT` → "Bir süre duruyorsun." (yanlış: oyuncu yanlarına gitmek istedi). Başarılı tıklama (`APPLIED`) kişiyi gerçek NPC yapar, konuşmayı açar, tur olarak mesajlara yazılır (:22842-22871), sonra arayüz "Yanlarına gidip ne olduğunu soruyorum." hamlesini gönderir (`ambientFollowUpMove`, :74-81).
T18'deki nöbet değişimi ve haberci reddinin nedeni büyük ihtimalle süre dolması; DOĞRULANMADI (kayıt okunmadı; `event_not_interactive` ve `event_referent_missing` de olası).
**Öneri.** Tek kural tek yerde: `ambient_actions.py` (yeni; `resolve_ambient_event_action` gövdesi `game.py`'den buraya taşınır, `game` ince sarmalayıcı kalır) içinde `actionable(world) -> {event_id, can_interact, reason}`; aynı işlev hem API görünümüne `actionable` alanını yazar hem tıklamayı denetler. Arayüz düğmeyi yalnız `can_interact` doğruyken gösterir. Savaş, ölüm, süre dolması, yer değişimi düğmeyi kaldırır (24 bedava çözülür). Ret nedeni Türkçe ve nedenli (`refusals.text_for`, Dilim 2): ör. "Onlar çoktan dağıldı." Tıklama oyuncunun yazdığı "yanlarına gidiyorum" ile aynı sonucu verir (K3).
**Sahip.** `ambient_actions.py` (karar ve göndergenin yaşam döngüsü yazımı `living_world`'de kalır), `api/serializers` ve arayüz yalnız okur.
**Test.** Yeni senaryo "etkileşim düğmesi": (a) taze olay → `APPLIED`, kişi sahnede, konuşma açık; (b) 13 tur sonra görünümde `can_interact: false`, düğme yok; (c) süresi dolmuş olaya doğrudan istek → Türkçe nedenli ret, durum değişmez; (d) savaşta `can_interact: false`. Arayüz: SSR çizim testi (düğme var/yok). Geri Al: `APPLIED` tıklama geri alınınca kişi ve gönderge eski hâline döner (bugün sınandığı DOĞRULANMADI).
**Risk.** Uç noktanın kendi makbuz/tekrar düzeni var (`api/main.py:2348-2520`, `action_id` ile); taşıma bunu bozmamalı: para yok ama kayıt ve makbuz var, bağımsız inceleme ister.

### 2.3 Dışarı çıkınca sahne atlaması (42)
**Bugün.** Motor yolu doğru: senaryo 07 (odadan "dışarı çıkıyorum" → sokak) sahte modelle geçiyor. Ön okumanın yer listesinde `outside` türü ve `WAY_OUT` var (`front_proposal.py:22-35`); Kadir'in oynayışında Tahılcı'ya geçiş büyük ihtimalle modelin listeden başka bir yeri seçmesi (EK 4 düzeltmeleri, kesinlik "düşük"). "Gece/akşam ifadesi tutarsız" kısmı DOĞRULANMADI.
**Öneri.** Önce ölç: gerçek zincirde "odadan dışarı çık" ve "handan dışarı çık" ×3 (rc5), rota günlüğü (`AI_DND_ROUTE_LOG`) modelin seçtiği satırı gösterir. Kök model seçimiyse düzeltme liste tarafında: `outside` satırının etiketi gerçek hedefin adını taşır ("dışarı: Neverwinter sokağı", `exits.way_out`'tan), böylece model "dışarı"yı başka yerle karıştırmaz. Model yine başka bir yeri seçerse ve o yer bir çıkış komşusu değilse motor onarır: önce çıkışa geçirir, sonra yürüyüşü bugünkü yolculuk kuralıyla yapar ve anlatı ara durağı söyler ("Sokağa çıkıp Tahılcı'ya yürüyorsun"). Kelime listesi yok.
**Sahip.** `exits.py` (etiket), `front_proposal` (liste), yürüyüş bugünkü sahibinde.
**Test.** rc5 (gerçek zincir, 3 koşu, hedef 3'te 3). Sahte modelle: model `go_to` başka yer önerdiğinde ara durak anlatısı ve doğru konum.
**Risk.** Kök başka çıkarsa (ör. oda çıkışının hana değil sokağa bağlı olması: `local_places.py:485` odanın çıkışını han kaydına yazıyor, yani odadan "dışarı" bir adımda sokağa mı hana mı gitmeli?) K4'te karar.

### 2.4 Cinayetin sonucu (47)
**Bugün.** `bold_acts.killed` cinayeti deftere yazar ve `fresh_killing` bayrağını koyar; tur sonunda `bold_acts.answer_to_killing` (`bold_acts.py:354-377`): silahlı biri varsa saldırır; silahsız tanıklar yalnız `_way_out` bir yer verirse oraya taşınır ve "bağırarak kapıya koşuyor" yazılır. Çıkış yoksa silahsız tanık için HİÇBİR satır yazılmaz. Ayrıca savaş tur sonunda hâlâ sürüyorsa hiç çalışmaz (:358). Sonradan gelen karşılık çalışıyor (ceset 8 saat sonra kaldırılır, muhafız sorguya gelir; senaryo 15'in korunan adımları). Senaryo 15 bilinen kırık [21, 47].
**Öneri.** Tanık her durumda o turda adıyla tepki verir: çıkış varsa kaçar (yer değişir), yoksa geri çekilip bağırır ve sahnede "korkmuş" kalır (tek yeni bayrak, kişi kaydında). "Kapıya" sabit sözü açık havada yanlış; satır yerin türünden kurulur ("kalabalığın içine koşuyor"). Savaş içinde öldürülen kişi için tepki savaş bittiği turda verilir (bayrak savaş bitene kadar tutulur). Tanık bir sonraki konuşmada gördüğünü bilir (bugün `bold_acts.remembers` deftere bakıyor; Dilim 1 `truth_card.npc_view` bunu taşıyorsa ek iş yok, DOĞRULANMADI).
**Sahip.** `bold_acts` (tepki ve defter), çıkış `exits`.
**Test.** 15 işareti kalkar; yeni: savaş içinde cinayet → savaş biten turda tepki; çıkışsız yerde tanık sahnede, adıyla tepki; kayıt/yenileme sonrası tanık "korkmuş".
**Risk.** Silahlı tanığın savaş başlatması mevcut; savaş ve konuşma kipinin birlikte kapanması Dilim 2 `talk_mode`'a bağlı. Kayıt alanı eklenir: bağımsız inceleme.

### 2.5 Anlatı kalitesi (43, 44, 45, 46)
**45 parantezli replik — Bugün:** NPC sözü `game._render_experimental_npc_speech` (`game.py:8181-8190`) ile `"{ad} ({sahne yönergesi}): “{söz}”"` biçiminde kuruluyor; parantez motorun kendi biçimi. **Öneri:** `"{Ad} {yönerge}. “{söz}”"` (yönerge yoksa `"{Ad}: “{söz}”"`); Türkçe ilk harf Dilim 2 `tr_case.upper_first`. Saf biçim değişikliği. **Test:** birim + Adım 2 yolculuk senaryolarının anlatı kayıtlarında `(` ile başlayan yönerge yok (senaryo beklentisi, ürün doğrulayıcısı değil). **Risk:** düşük; çok sayıda test eski biçimi sabitliyor olabilir (`test_experimental_npc_dialogue.py`), eski davranışı sabitleyen testler aynı sıkılıkta yeniden yazılır (izinli, listesi Kadir'e).
**44 "içeri adım atıyorsun" — Bugün:** `local_places.arrival_text` (`local_places.py:553-583`) ilk ziyarette `outdoors` değilse "{ad} karşına çıkıyor ve içeri adım atıyorsun" diyor; `outdoors` yalnız sur dışı yerler için (`:176`, `:194`); iskele (`:69`) şehir içinde açık hava olduğu hâlde bina sayılıyor. **Öneri:** yer türlerine ikinci bir alan `open_air` (iskele, pazar, meydan gibi türlerde doğru) ve ona göre "…'na varıyorsun" satırı; "Yeniden … içindesin" satırları da aynı alana bakar. **Test:** iskele ilk/ikinci ziyaret satırı. **Risk:** düşük; tür tablosu veri işi.
**43 boş cümleler — Bugün:** "Bu sorunun peşini bırakmamaya karar veriyorsun." `interaction_adventure.resolve` içinde `goal` işlemi kaydedilince tek başına anlatı oluyor (`interaction_adventure.py:1233-1244`); bira siparişinde bunun çıkması modelin `goal` önerdiği anlamına gelir. "Çevrede şimdilik belirgin bir değişiklik olmuyor." motorun genel yedek cümlesi (`game._generic_no_change_response`, `game.py:10050-10066`); senaryo 01'in 3. adımında tanınmayan satın almada çıkıyor. Gerçek oyunda hangi yoldan geldiği DOĞRULANMADI. **Öneri:** (a) `goal` kaydı kendi başına anlatı cümlesi üretmez; kayıt günlükte görünür (Dilim 2 `quest_log`), anlatıyı anlatıcı yazar. (b) Genel yedek cümle yalnız model hiç cevap vermediğinde kalır; motorun söyleyecek bir şeyi yokken ve model çalışıyorken anlatıcı doğruluk kartından kısa bir sahne satırı yazar (K5: model çağrısı artar). (c) Önce ölç: rota günlüğünde bu iki cümlenin kaç turda ve hangi daldan çıktığı. **Test:** 01 adım 3 Dilim 1'de çözülmüş olmalı (DOĞRULANMADI); yeni sahte model senaryosu: alışveriş satırına `goal` önerisi gelirse anlatıda "peşini bırakmamaya" yok. **Risk:** (b) gecikme ve maliyet.
**46 "Aleykümselam" — Bugün:** motor metinlerinde yok (arama boş); model çıktısı. Hangi modelin (Gemini/Haiku/Gemma) yazdığı DOĞRULANMADI. **Öneri:** NPC ve anlatıcı istemine dünya bilgisinden tek satır: "Faerûn'dasın; selam ve yemin bu dünyanın inançlarıyla söylenir." Doğrulayıcı/yasak listesi yok. **Test:** yalnız gerçek zincir (rc6: üç farklı NPC'ye selam, 3 koşu); senaryo beklentisinde bu kelime "yasak_metin" olarak durabilir (test gözlemi, ürün kuralı değil). **Risk:** istem bütçesi; Gemma küçük model, istemi dinlemeyebilir.

### 2.6 Bayat ipucu (50)
**Bugün.** Şerit, bulunduğun yerin sahne kaydındaki olayı gösterir (`living_world.public_scene_projection` `world["location"]`'u okur), yani "başka sahneden kalma" değil. Olay seçimi sahne türüne göre (`select_and_record_ambient_event`, `living_world.py:1373-1417`), ama ortam süzgeci (`environments`) kampanya düzeyinde tek değer (`set_ambient_context`, :1329-1370). Örnek: `city_beggar_dispute` ("İki yolcu, bir bankın yanında…") sahne türü olarak `city|temple|tavern` alıyor (`ambient_event_catalog.py:93`); şehir kampanyasında han sahnesi bu olayı seçebilir. Kadir'in gördüğü örnekle birebir uyuyor; o kampanyanın kaydı okunmadı, kesin kök DOĞRULANMADI.
**Öneri.** Katalogda metni açık hava anlatan olaylar `tavern` sahne türünden çıkar (veri düzeltmesi; Python kuralı eklenmez). Kalan katalog bir kez taranır (yazarken, oyunda değil).
**Sahip.** `ambient_event_catalog.py` (veri).
**Test.** Katalog testi: `tavern` türü alan her olay için insan onaylı küçük bir tablo; senaryo: han sahnesinde seçilen olaylar tavern olayları. **Risk:** düşük.

### 2.7 İlk 10 dakika (49)
**Bugün.** Açılış `api/opening_narrative.initialize_campaign_opening`: yer adı, hava, saat ve yalnız `GREEN` (tıklanamaz, süs) bir olay (`allowed_types={"GREEN"}`); model çağrılmaz. `campaign_opening.build_opening` bilerek ana görev koymaz (`main_quest: None`). Yani oyunun başında motorun kaydettiği, peşine düşülebilecek hiçbir şey görünmüyor; kasaba işleri (`world_threads.ensure`, `_seed_settlement`) var ama oyuncu ancak konuşarak rastlıyor. Haberci (`world_happenings.caller_comes`) ancak bir bağ (link) varsa gelir.
**Öneri.** Hazır görev değil, "dünyanın kapısı aralık": (1) Açılışta süs olayına ek olarak başlangıç sahnesinde bir `BLUE` olay (tıklanabilir, §2.2) ve yerleşimin açık işlerinden biri oyuncunun gördüğü bir olay satırı olarak (`world_happenings`, `known_to_player`) yazılır; ikisi de tohumdan, mevcut kataloglardan, her kampanyada farklı. Dilim 2 bunu "İzler"de gösterir. (2) Oyuncu ilk 8 turda hiçbir kayda dokunmadıysa dünya bir kez gelir: bir kişi yaklaşır ya da sokakta bir haber konuşulur (`world_threads.street_talk`); reddederse ısrar yok. (3) Ölçü tur sayısıdır, dakika değil. Model yeni olay yaratmaz.
**Sahip.** `opening_hook` işlevi `api/opening_narrative` içinde (açılış tek yazar); dünyanın ikinci gelişi `world_happenings` (bugünkü bağ sahibi). Hangi işin seçildiği `world_threads`.
**Test.** Yeni senaryo "ilk on tur": yeni kampanya, oyuncu yalnız "etrafa bakıyorum" der; 1. turda `quest_log.trails` en az 1 satır ya da tıklanabilir olay; 8. turda boşta kalmışsa ikinci geliş; oyuncu ilk turda bir işe girdiyse ikinci geliş YOK. Üç farklı tohumda üç farklı açılış (Kadir'in "aynı Marek" şikâyeti).
**Risk.** Kadir'in tarifi "ne boş bekleme ne her tur kriz" ve "hikâye zorla oynatılmaz": itme dozu ürün kararı (K2). Açılış kaydı değişir: yeni kampanyalar etkilenir, eski kayıtlar etkilenmez (onarım yok). Yeni kampanya yaratmanın para/kese yoluna dokunmamalı (14_start_purse yeşil kalmalı).

### 2.8 3a kanıtı
**Bugün.** Parçalar var ama birlikte kanıtlanmadı: ön okuma açık/kapalı (`front_proposal.enabled`, yerel oyunda açık); makbuz/tekrar (`action_id`, `manager.get_turn_action`); Geri Al ve yenileme (senaryo 11, 10/10 geçiyor); haberci düzeni (`world_happenings.caller_comes`, `callers_leave`, `_message`, `_summoning_room`: ulak gelir, defterdeki olaydan kurulu mesajı söyler, gerekiyorsa evin iç odasına çağırır, sonra geri döner).
**Öneri.** Tek küçük gerçek sahne, iki çatışan amaç, sonuç dayatılmadan; bugünkü düzenle, yeni içerik yok: oyuncu sokakta bir kasaba işini öğrenir → kabul eder ya da başka yol seçer (ör. işi verenin rakibine söyler) → teslim/ihanet deftere yazılır → kayıttan bir bağ açılır, ulak gelir ve mesajı defterdeki olaydan söyler (`_why_sent`) → oyuncu çağrıyı kabul eder ya da reddeder → çağıran kişi olanı bilir → kaydet/aç sonrası ulak, bağ ve iz aynı. Her adım: (a) sahte modelle senaryo (kapı), (b) ön okuma açık/kapalı karşılaştırması, (c) gerçek zincir 3 koşu (K8). Beş parça: okuma ve kayıt ayrı, makbuz (aynı `action_id` iki kez işlemez), Geri Al, yenileme eşitliği, anlatıcı yalnız olandan yazar. Yanında bir serbest ajan oyunu (30 tur) okunur; zincir test için kurulmuş sahneye dönüşmesin.
**Sahip.** Kanıt düzeneği `api/tests/journeys`; ürün kodu değişmez, yalnız bulunan kırıklar o dilimin kontrol listesine girer.
**Test.** Senaryo "haberci zinciri" (sıfır tolerans sınıfında) + gerçek zincir rc7.
**Risk.** Zincirdeki kırıklar Dilim 3 kapsamını büyütebilir (yama döngüsü yasağı: yalnız sıfır tolerans hataları ve kontrol listesi düzeltilir, gerisi kayda geçer). Gerçek zincir maliyeti ölçülmedi.

## 3. KADİR'E SORULACAK KARARLAR

Her birinde önerim ilk seçenektir. Cevap gelmezse taslak önerilerle okunur; plan cevapsız kararları "öneriyle" işaretler.

**K1. Şehir sokağında kaçınca nereye gidilir?**
A) Şehrin "yan sokak" yeri bir kez açılır, sokağın çıkışı olur; kaçan ve tanık oraya gider, geri dönülebilir. B) Yer değişmez: "kalabalığa karışırsın", zar tutarsa düşman seni kaybeder, savaş biter. C) Şehir kapısına/surların dışına çıkar.
Öneri A. Gerekçe: bugünkü kod "kaçış = yer değişimi" üstüne kurulu (`commit_location_change` savaşı ve konuşmayı kapatıyor); B yeni bir "gözden kaybolma" kuralı ister, C bir kaçış için fazla büyük sıçrama ve yolculuk saatini işletir.

**K2. İlk dakikalarda dünya ne kadar ittirsin?**
A) Açılışta bir görünür olay + oyuncu ilk 8 turda hiçbir şeye dokunmazsa bir kez daha gelen bir kişi/haber; sonra ısrar yok. B) Yalnız açılıştaki görünür olay. C) Oyun bir olayın ortasında başlar (in medias res).
Öneri A. Gerekçe: Kadir'in tarifi "ne boş bekleme ne her tur kriz", 49 "oyuncu boşta"; B boşta kalmayı çözmeyebilir, C "hikâye zorla oynatılmaz" ile çatışır ve her açılışı benzetir.

**K3. "Etkileşime geç" düğmesi kalsın mı?**
A) Kalsın, ama yalnız tıklanabilirken görünsün; tıklama yazmakla aynı sonucu versin. B) Kaldırılsın; oyuncu yazarak etkileşir, şerit yalnız bilgi verir. C) Bugünkü gibi her zaman görünsün, yalnız ret metni iyileşsin.
Öneri A. Gerekçe: düğme bugün ekranın en belirgin turuncu düğmesi ve sorun düğmenin kendisi değil yalan söylemesi; B kolay ama Kadir'in "duruma göre değişen doğal seçenekler" isteğinden geri adım; C asıl hatayı bırakır.

**K4. Han odasından "dışarı çıkıyorum" nereye götürür?**
A) Bir adımda sokağa (oyuncunun "dışarı"sı binadan dışarıdır). B) Önce han salonuna, ikinci "dışarı" ile sokağa. 
Öneri A. Gerekçe: senaryo 07 bugün sokağa çıkarıyor ve geçiyor; oyuncu "salona iniyorum" derse zaten salona gider. (Bugünkü kodda odanın çıkışı han kaydı (`local_places.py:485`); A seçilirse `exits` odada "dışarı"yı sokak sayar, kayıt değişmez.)

**K5. Motorun söyleyecek bir şeyi yokken boş kalıp cümle mi, anlatıcı mı?**
A) Model çalışıyorsa anlatıcı kısa bir sahne satırı yazar; kalıp yalnız model yokken. B) Kalıp kalsın, yalnız sıklığı azaltılsın (farklı kalıplar). 
Öneri A, ama önce ölçüm: rota günlüğü bu cümlenin kaç turda çıktığını gösterir; çok seyrekse B yeter. Gerekçe: Kadir "mekanik cevap olmasın" diyor; bedeli her böyle turda bir model çağrısı.

**K6. Çıkışı gerçekten olmayan yerde (kilitli mahzen) kaçış metni ne söylesin?**
A) Neden + ne yapılabilir ("Çıkış yok; dövüşebilir ya da teslim olabilirsin"). B) Yalnız neden. Öneri A. Gerekçe: madde 21'in asıl şikâyeti "ne yapabileceğini söylemiyor". Not: "teslim ol" bugün bir eylem olarak var mı DOĞRULANMADI; yoksa metin yalnız "dövüşmeye devam" der.

**K7. İş bulma döngüsü (48) bu dilimde mi?**
A) Bu dilimde, yalnız K2'nin parçası olarak: ilk dakikalardaki görünür iş, "nerede iş bulurum" sorusunun cevabı olur; NPC'nin oyuncuyu paslaması ayrı düzeltilmez. B) Ayrı madde olarak bu dilimde (NPC'lerin bildiği işler konuşmaya bağlanır). C) Dilim 4 sonrasına.
Öneri A. Gerekçe: Dilim 2 izler ve görev günlüğü getirdi; asıl kırık "ilk 10 dakikada somut bir şey yok"; B NPC bilgi sahipliğine (Dilim 1 D28) dokunur ve dilimi büyütür.

**K8. Gerçek zincir koşuları (rc5 dışarı, rc6 selam, rc7 haberci zinciri, 3'er koşu).**
A) Plan tahmini sunulup tek "yap" ile hepsi. B) Her biri ayrı "yap". Öneri A. Gerekçe: Adım 2'de 48 çağrı ≈ 1,3 sent; Gemini ücretsiz, Haiku yedek. Tahmin plan aşamasında hesaplanır.

## 4. Dilim 2 varsayımları ve bağımlılık

Dilim 3 şu adların birleşmiş tabanda olduğunu varsayar; plan Görev 1 bunları arar, biri yoksa DURUR. Dalda gördüklerim (`task/dilim2-quests-refusals-20261104`, uç 545475ec): `quest_log.py`, `talk_mode.py`, `tr_case.py` VAR; `refusals.py`, `gear.py` dal ağacında YOK (henüz yazılmamış ya da başka adla; DOĞRULANMADI).
- `quest_log.view(world)` ve `quest_log.trails(world)`; günlükte "İzler" bölümü ve "Henüz bir iz yok." boş durumu. Dilim 3'ün §2.7 ve §2.8 kanıtı izleri buradan okur.
- `world_happenings`: `KINDS` içinde `"delivered"`, `FOLLOW_ON["delivered"]` (dal commit a49b9e81 bunu anlatıyor). Haberci zinciri bu satırlardan bağ açar.
- `talk_mode`: tek yazar; `close(world, reason)`; `REASONS` içinde en az `moved`, `combat`, `death`, `rest`, `addressed_absent`; dalda `callers_leave` artık `talk_mode.close(world, "target_gone")` çağırıyor (doğrulandı). Dilim 3'ün yeni kapanış nedenleri (tanık kaçtı, ulak gitti) buraya eklenir; `test_talk_mode_writers` yeşil kalmalı.
- `refusals.text_for(code, **facts)` ve `refusals.note(session, code, ...)`: §2.1 (çıkışsız kaçış) ve §2.2 (tıklama reddi) metinleri buradan. Dal birleşmezse Dilim 3 metinleri geçici olarak kendi modülünde tutar ve Dilim 2 gelince taşır (iş tekrarı riski).
- `tr_case.upper_first`: §2.5 (45) ve tanık satırları.
- `truth_card.narrator_view` / `npc_view` (Dilim 1, c-merge'de var) ve Dilim 2'nin `görevlerin:`/`izler:` satırları: tanığın ve ulağın "bildiği" buradan anlatıcıya gider.
- Yolculuk düzeneği: `gunluk.iz`, `gunluk.iz_sayisi`, `sifir_tolerans` adım anahtarı, gerçek koşu raporunda "Sıfır tolerans ihlalleri" (Dilim 2 karar 56, 63).
Bağımlılık sonucu: Dilim 3 planı Dilim 2 `task/c-series-merge`'e birleşmeden kod görevine başlamaz. Bekleme süresince yapılabilecekler: K kararları, katalog taraması (§2.6, salt okuma), gerçek zincir ölçümü (§2.3, §2.5) için senaryo yazımı.

## 5. Görevlere bölünme taslağı (sıra önerisi)

"İnceleme" = bağımsız inceleme (en güçlü model) gerekir: para, kayıt ya da Geri Al'a dokunur.
1. **Taban denetimi:** Dilim 2 adları (§4) var mı; yolculuk senaryoları ve tam test yeşil; işaretler listesi. (salt okuma)
2. **Ölçüm (gerçek zincir, K8 "yap"):** rc5 (dışarı), rc6 (selam), rota günlüğünden 43 kalıplarının dalı. Sonuç 2.3 ve 2.5'in kapsamını kesinleştirir.
3. **`exits.py` çıkarımı ve yan sokak (21):** `flee`, `bold_acts._way_out`, Dünya paneli, `outside` etiketi tek kaynağa bağlanır; 09c işareti kalkar. **İnceleme** (yer değişimi, savaş sonu, kayıt).
4. **Cinayetin sonucu (47):** tanık her durumda tepki, savaş içi cinayet; 15 işareti kalkar. **İnceleme** (kayıt alanı, savaş başlatma).
5. **`ambient_actions.py` çıkarımı ve düğme (11/16/118, 24):** `actionable` tek kural, görünüm alanı, arayüz, nedenli ret. **İnceleme** (makbuz, kayıt, Geri Al).
6. **Dışarı/sahne atlaması onarımı (42):** ölçüm sonucuna göre; ara durak anlatısı. Kayıt: yer değişimi; **inceleme** yalnız onarım yolu yer yazıyorsa.
7. **Anlatı biçimi (44, 45, 46, 43a):** konuşma biçimi, `open_air`, selam istemi, `goal` cümlesi. Para/kayıt yok.
8. **Bayat ipucu (50):** katalog verisi ve katalog testi. Para/kayıt yok.
9. **Boş cümle (43b, K5):** yalnız ölçüm "gerekli" derse. Para/kayıt yok; maliyet notu.
10. **İlk 10 dakika (49, K2, K7):** açılış kancası + ikinci geliş + "ilk on tur" senaryosu. **İnceleme** (kampanya yaratma kaydı; 14_start_purse yeşil).
11. **3a kanıtı:** haberci zinciri senaryosu (sıfır tolerans), ön okuma açık/kapalı karşılaştırması, rc7 (K8 "yap"), serbest oyun okuması. **İnceleme** (Geri Al ve yenileme eşitliği bütün zincirde).
12. **Kapı:** işaretler kalkmış, yeni kırık 0, zero_tolerance yeşil, tam test 0 kırık, bütün dal bağımsız incelemesi, `graphify update .`, 3a kanıtı geçti; deftere "oynayış bekliyor". Kanıt geçmezse Dilim 4 başlamaz.
Sıra gerekçesi: çıkış (3) cinayet (4) ve dışarı (6) için temeldir; düğme (5) ilk 10 dakikanın (10) tıklanabilir olayını taşır; 3a (11) en sona, çünkü zincir öncekilerin hepsini kullanır.

## 6. Açık riskler ve bilmediklerim

- **Dilim 2 birleşmedi:** `refusals` ve `gear` dalda yok; ret metinleri Dilim 2'nin sözleşmesine bağlı. Dilim 2 planı değişirse §4 yeniden yazılır.
- **42'nin kökü bilinmiyor:** model seçimi olduğu tahmin; gerçek zincir ölçümü olmadan düzeltme tasarlanamaz. Ölçüm kökün başka olduğunu gösterirse §2.3 değişir.
- **118'in kesin nedeni:** süre dolması en olası (kod yolu bunu gösteriyor) ama o kampanyanın kaydı okunmadı.
- **50'nin kesin kökü:** katalog/sahne türü uyumsuzluğu en olası; Kadir'in kampanya kaydı okunmadı.
- **46 hangi modelden:** Gemini, Haiku ya da yerel Gemma; istem satırının küçük modelde tutup tutmadığı bilinmiyor.
- **43 gerçek oyunda hangi yoldan:** sahte modelde görülen yol ile Kadir'in oynayışındaki yol aynı mı, bilinmiyor.
- **Ambient tıklamanın Geri Al'ı:** `APPLIED` tıklamanın geri alındığını sınayan bir test görmedim; DOĞRULANMADI. Sıfır tolerans alanı olduğu için Görev 5'in ilk adımı bu.
- **Dünya paneli (T5) hangi alanı okuyor:** "geçit yok" metninin kaynağı okunmadı.
- **"Teslim ol" eylemi var mı (K6):** bilinmiyor.
- **Yer sınırı:** `local_places` en çok yer sınırı dolu kampanyada yan sokak açılamayabilir.
- **Gerçek zincir maliyeti:** Dilim 3 için ölçülmedi; Adım 2 ölçeğinde düşük görünüyor.
- **3a kapsam riski:** zincir yeni kırık çıkarırsa "yama döngüsü yok" kuralıyla çatışır; bulgular plan aşamasında Kadir'e listelenir.
- **Eski testler:** 44 ve 45 metin değişiklikleri eski biçimi sabitleyen testleri kırar; yeniden yazılanlar listelenip Kadir'e sunulur.
- **Jarvis:** YOL_PLAN Task 5 Step 1 posta kutusunun Dilim 3 başında açılmasını istiyor. J-008 (dünya ve konuşma) okundu; "kilitli kapı ≠ çıkış yok" ve "veri eksiği anlatıcıya kapı uydurtularak kapatılmaz" ilkeleri bu taslakla uyumlu. Bu taslak Jarvis'e gönderilmedi.
