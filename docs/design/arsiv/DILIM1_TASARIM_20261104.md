# DİLİM 1 TASARIMI: para ve kart tek sahip + kişisel hafıza

Durum: taslak, Kadir onayını bekliyor. Kod YOK, test koşulmadı, model çağrılmadı, commit/push YOK. Tarih 2026-11-04.

## 0. Güncel özet (tek sayfa; J-013 kararlarından sonra)

Bu sayfa bugünkü sözleşmedir. Aşağıdaki bölümlerle çelişirse bu sayfa, §13 ve §12 geçerlidir. Henüz kod yok; aşağıdaki hiçbir madde şu an testle kanıtlanmış değildir.

**Oyuncu ne yapar, motor neyi kesin garanti eder?**
- Oyuncu her zamanki gibi yazar: "bir bira, 5 bakır, üstü kalsın", "bu gece kalacak oda", "biramı içiyorum", "babam değirmenci". Yeni komut öğrenmez.
- Yapay zekâ cümlenin ne demek olduğunu önerir: alışveriş mi, oda mı, bahşiş mi, hediye mi, daha önce ödenmiş bir şey mi. Motor bunu denetler ve kaydeder. Rakamı her zaman motor hesaplar, yapay zekâ rakam vermez.
- Motorun kesin sözleri: (1) Sen onaylamadan para gitmez. (2) Ekranda gösterilen toplamdan fazla para asla kesilmez. (3) Para sessizce "hediye"ye dönmez. (4) Para uzatılan bir cümle iş/vardiya başlatmaz, ücret ödetmez, saati ilerletmez. (5) Fiyatı motor bilir; anlatıcı ve NPC fiyatı motordan okur. (6) Yenen/içilen şey çantadan düşer; ok atınca ok sayısı azalır.

**Para ne zaman gider; NPC'nin reddi hangi işe uygulanır?**
- Teklif istemek para vermek değildir. "Bir bira alabilir miyim" yalnız tezgâhta bir teklif açar. Para ancak sen kartı ya da tezgâhı onaylayınca gider.
- Cümlenin ne için olduğu anlaşılamazsa kart açılmaz, para kesende kalır, NPC doğal olarak sorar. Eski "kelimeden tahmin" yoluna yalnız yapay zekâ hiçbir öneri vermediyse dönülür; anlaşılamayan bir öneri başka bir karta dönüşmez.
- NPC parayı geri çevirirse ret, hangi kalem içinse ona uygulanır. Yalnız bahşişi istemezse bira yine satılır, bahşiş sıfır olur. Odanın parasını açıkça almazsa oda kartı kapanır; onaylansa da para kesilmez. Neyi reddettiği belli değilse o NPC'ye hiçbir ödeme ilerlemez; konuşarak netleşir.
- Ret, NPC aynı kalem için açıkça "alırım" diyene ya da oyun günü değişene kadar sürer. Yapay zekâ cevap vermezse ya da cevabı bozuksa ret sürer, kalkmaz. Aynı anda en çok 32 kişinin reddi tutulur; yer gerekirse önce önceki günlerin kayıtları silinir, bugünkü bir ret sessizce silinmez.

**NPC neyi hatırlar, ne kadar süre, neyi bilmez?**
- Yapay zekâ "bu hatırlamaya değer mi" diye evet/hayır der. Motor oyuncunun kendi cümlesini 600 karaktere kadar aynen saklar. Özet ya da uydurma yazılmaz.
- Her NPC kendisine söylenmiş son 40 seçilmiş sözü tutar; 41. gelince en eskisi gider. Kaydet/yükle ve Geri Al bunu taşır. Bu "uzun süreli tam hafıza" değildir: Dilim 1'in sözü "son 40 seçilmiş söz"dür. Tam arşiv sonraki iştir.
- Konuşurken NPC'ye en çok 3 ilgili söz gösterilir. Her biri en çok 200 karakterdir; daha uzunsa "kısaltıldı" diye işaretlenir ve kısaltılmış parça kanıt sayılmaz.
- NPC şunları bilmez: kesendeki toplam para, çantan, başka NPC'lerle konuştukların ve onlara ödediklerin. NPC yalnız kendisine uzatılan parayı ("uzattığın 5 bakır"), kendisiyle olan teklif ve ödemeleri ve kendi fiyatlarını görür.
- Kayıt "oyuncu bunu söyledi" demektir, "bu doğru" demek değildir. "Sen bana söz vermiştin" gibi NPC'ye söz yükleyen uydurmalar kayıttan destek alamaz, bugünkü gibi reddedilir. Hiç ilgili söz bulunmazsa NPC "hatırlamıyorum" der; bu bilinçli bir karardır ve oynayışta bakılacaktır.

**Tek onay mı, iki onay mı; Geri Al neyi döndürür?**
- Panel bahşişi gösterirse (Kadir "evet" derse): bira + bahşiş tek onaydır, tek makbuzdur. Tek Geri Al keseni, barmenin kesesini, birayı ve teklifi birlikte eski hâline getirir.
- Panel değişmezse (Kadir "hayır" derse): önce bira onaylanır (4 bakır). Bira gerçekten alındıktan sonra 1 bakırlık Bahşiş kartı açılır; ikinci onay bahşişi öder. İki ayrı makbuz olur. Bira alınamazsa bahşiş kartı hiç açılmaz.
- **Geri Al tek adımdır (§13 D37).** Motor yalnız en son oynanan turu geri alır; geri aldıktan sonra yeni bir tur oynanmadan ikinci kez Geri Al çalışmaz ("Geri alınabilecek bir son tur yok."). Bu kural Dilim 1'de değişmez. İki onaylı durumda bunun anlamı şudur:
  - Bahşişi onayladıktan sonra Geri Al'a basarsan **yalnız bahşiş** geri gelir (kese 95 → 96, barmen 5 → 4). Bira sende kalır, 4 bakırlık bira ödemesi durur. Bahşiş kartı yeniden onay bekler; istersen yine onaylarsın, istersen bırakırsın.
  - Ondan sonra birayı Geri Al ile geri almanın yolu **yoktur**: ikinci Geri Al reddedilir, yeni bir tur oynamak da işe yaramaz (Geri Al o zaman yalnız o yeni turu geri alır).
  - Birayı geri almak istiyorsan Geri Al'a **bahşişi onaylamadan önce**, bira alınır alınmaz basarsın: bira, 4 bakır ve tezgâh teklifi geri gelir, o sırada açılan Bahşiş kartı kapanır.
  - Oyuncunun göreceği sonuç: "üstü kalsın" B yolunda tek tuşla "hiç olmamış" yapılamaz; bahşişten sonra yalnız bahşiş geri alınır. Panel "evet" yolunda bu sorun yoktur (tek makbuz, tek Geri Al hepsini döndürür).

**Hangisi ne durumda?**
- Belge kararı (Kadir'in onayına açık): bu sayfadaki her kural ve sayılar (40 söz, 3 gösterim, 600/200 karakter, 32 ret, 600 baytlık kart, %10 indirim); panel sorusu.
- Testle kanıtlanacak (kod yazılınca; şu an hiçbiri kanıtlı değil): para kuralları, ret kapsamı ve süresi, NPC'ler arası bilgi sızmaması, kayıt hatası / yanıt kaybı / aynı işlemin yeniden gönderilmesi / oyunu yeniden açma / Geri Al, 600 bayt sınırı.
- Gerçek yapay zekâyla kısa ücretli koşuda denenecek: fiyat hatırlama, ödeme sonrası tutarlılık, yapay zekânın ilk anlatımda kendi başına "hatırla" demesi ve sonra doğru ayrıntıyı söylemesi, ok atışının doğru yola gitmesi.
- Oynayış bekliyor: ürün kabulü yalnız Kadir'in 30 dakikalık oynayışıyla; "hatırlamıyorum" cevabının doğal durup durmadığı; pazarlık zarının oyunda gerçekten atılıp atılmadığı.

Terimler (ilk kullanım): `deal` = işlem önerisi; tender = uzatılan para; replay = aynı işlemin yeniden gönderilmesi; görünüm = modele giden kısa metin; kaynak = motorun sakladığı tam kayıt.

---

**Not (iki eleştiriden, J-013'ten ve Dilim 0 incelemesinden sonra):** §11 "Eleştiri sonrası düzeltmeler" (D1–D24), §12 "J-013 sonrası düzeltmeler" (D25–D36) ve §13 "Dilim 0 incelemesi sonrası düzeltme" (D37) değişiklik günlüğüdür. §3a, §3b, §3d, §3e, §4 ve §5 J-013 ile güncellendi; §0, §3b, §5 ve §6'nın Geri Al cümleleri D37 ile güncellendi; §3c için §11 D6/D24 geçerlidir. Bir çelişki olursa sıra şudur: §0 > §13 > §12 > §11 > öteki bölümler. §9'daki kararlar silinmedi; değişenler yeni numarayla yazıldı ("karar N'nin yerine geçer"). Uygulama planı: `DILIM1_PLAN_20261104.md`.
Kaynaklar: `YOL_HARITASI_REVIZYON_20261104.md` (§2–5), `YOL_PLAN_20261104.md` (Task 3), `ADIM2_TASARIM_20261104.md` (§3, §4, §12), `CANLI_OYUN_NOTLARI_20261103.md` (34–56, EK 4–6), `OYUN_TARIFI_KADIR_20261031.md`, `HANDOFF.md`, `DILIM1_HAFIZA_ARASTIRMA_20261104.md` ve iki salt-okuma araştırma çıktısı (para: 4 ajan; hafıza: 3 ajan). Kod gerçekleri `AI-DND-c-merge` (3c733c57) ve Adım 2 düzeneği `AI-DND-step2` (`task/step2-measure-20261104`) üzerinden okundu. Madde numaraları notlar dosyasındandır (100+T = EK 5).

## 1. Amaç ve anlayış

**Amaç (tek cümle):** Oyuncunun parayla ilgili söylediği her cümlenin ne anlama geldiğine TEK bir yer karar versin, ödenen ve reddedilen para hiç şaşmasın, anlatıcı her turda motorun gerçeğini okusun; ve oyuncunun bir NPC'ye anlattığı kişisel şey o NPC'de kalsın.

**Kadir'in açıkça söyledikleri (kesin):**
- Dilim 1 = bir güvenilirlik işi (para ve kart tek sahip) + bir oyun hissi işi (kişisel hafıza). Kontrol listesi: 35, 36, 37, 38, 54, 56, 107, 3, 103, 110 ve 116.
- "Üstü kalsın" = satın alma + bahşiş (Adım 2 kararı e). Sohbetle alışveriş tezgâh teklifinden geçer ve `/item shop_buy` ile onaylanır (R7). Oda anahtarı eşya değil, oda kaydıdır (R8). Savaşta satın alma reddedilir (R11).
- Fiyatı motor sahiplenir, anlatıcı yalnız okur (karar g). Anlatıcıya her turda kısa doğruluk kartı (karar c). Kartlar yalnız onaydır, metin esastır (karar h).
- Az motor kuralı; yeni kelime listesi / regex doğrulayıcı YOK (K2: dayanaksız para/eşya sonucu durdurulabilir, yaratıcı deneme engellenmez). "Model önerir, Python doğrular, kaydeder." Para, kayıt ve geri alda sıfır tolerans. Reddetmek yerine onarmak.
- Her dilim `game.py`'den yalnız kendi parçasını yeni modüle çıkarır; bir alanın tek sahibi olur, anlatıcı yalnız okur.
- Bitiş kapısında Kadir'in 30 dakikalık oynayışı şimdilik beklenmez: deftere "oynayış bekliyor" yazılır.

**Benim varsaydıklarım (Kadir onaylamadı; hepsi §9'da karar olarak yazılı):**
- Oyuncunun oynadığı yol ön okumanın açık olduğu yoldur (`api/local_play.py:216` yerel oyunda `AI_DND_FRONT_PROPOSAL=1` yapar). Para anlamını bu okumaya bağlıyorum; ön okuma kapalıyken eski yol olduğu gibi kalır.
- "Kişisel hafıza" = "oyuncu bunu bana söyledi" bilgisidir, "bu doğrudur" bilgisi değildir. NPC bunu bilir; doğru olup olmadığını bilmez.
- Pazarlıkta başarılı zar küçük, sabit bir indirim verir (37). Kadir "zar etkisiz" diye şikâyet etti; indirim miktarını ben seçtim.
- Yemek ve içmenin oyun etkisi yok (açlık, sarhoşluk yok); yalnız eşya düşer.

## 2. Kanıtlı kök nedenler

Kesinlik parantezde; "doğrulanmadı" yazanlar çalıştırılarak görülmedi.

1. **Para cümlesinin anlamına kimse tek başına karar vermiyor (yüksek).** Uzatılan para önce ön okumadan `session._front_coin` olarak gelir (`game.py:18326`), `_hand_over_coin` (`game.py:18394-18420`) onu `session._coin_paid` yapar; açık tezgâh teklifi varsa tezgâha bağlanır (`18415`). Kimse sahiplenmezse `_tell_the_coin` (`game.py:17815-17846`) cevaptan SONRA çalışır ve parayı sessizce **Hediye** kartına çevirir (`turn_proposal('gift', ...)`). Ön okumanın paranın NE İÇİN olduğunu söyleyen bir alanı yok (`front_proposal.py:113-134`, yalnız `coin_cp`). Madde 35 (üstü kalsın → hediye), 3 (geçmiş zaman → yeni teklif) ve T10'daki Hediye kartı buradan.
2. **Oda cümlesi sayım işini bitiriyor ve 8 saat geçiriyor (yüksek; saf fonksiyonla doğrulandı).** Ön okuma `offer_answer/hand_over/work` değilse `_thread_gate` (`game.py:8392`, zincir `~18805-18808`) eski kelime listesiyle iş okur: `world_threads.turn_gate` (`world_threads.py:1421`, iş dalı `1451-1455`) → `does_the_work_now`; `_names_the_work` (`1044-1049`) para kelimelerini (`town_threads.json ~424`: gümüş, bakır...) "işin adı" sayar, "ödüyorum" birinci şahıs/şimdi ekine uyar (`json:296, 569`). Sonuç `work_turn` → `_one_shift` → `advance_campaign_time` 8 saat (`town_threads.json:912`) + 26 bakır. Oda sahibi `bold_acts.take_room` "ödüyorum"u tanımadığı için (`bold_acts.py:598-601, 666, 720`) satırı almamış; para da 1. maddedeki yoldan Hediye olmuş. Madde 110.
3. **NPC'nin sözle reddi motorda hiçbir yere yazılmıyor (yüksek).** Konuşma şemasında (`game.py:7942-7960`) "parayı alırım/almam" alanı yok; `_tell_the_coin` cevabı hiç okumaz. Hazır bir "satır reddedildi" mekanizması var ama üretimde onu besleyen yok (`economic_actions.py:390-411, 735-748`). Madde 103 (T3: reddedilen 5 bakır kartla kesildi).
4. **Konuşmadan bahşiş çıkmıyor (yüksek).** Bahşiş yalnız panelden (`economic_actions.py:1113, 1369-1374` `tip_cp=0`; `counter_purchase_offer` `1457` tek eşya satırı). Tezgâhta fazla para "para üstü" sayılır (`shop_trade.py:230-232`), yani "üstü kalsın"ın tersi. Satın alma + bahşiş satırı veri yapısında zaten mümkün (`economic_actions.py:258-331`), yalnız onu kuran yok.
5. **Fiyat konuşma istemine yalnız kelime tutunca gidiyor, anlatıcıya hiç gitmiyor (yüksek).** `price_note`/`room_note` (`bold_acts.py:605-625`) oyuncunun sözü kelime listesine uyarsa yazılır; anlatıcı bağlamında (`build_world_context`, `game.py:7160-7303`) fiyat, kese, oda kaydı, açık teklif, makbuz, çıkış yok. Fiyatın tek kaynağı zaten motor (`shop_trade.py:19` PRICES, `bold_acts.py:602` `_ROOM_PRICE=50`). Madde 36, 2, 38 (anlatıcıya "oda tutuldu" gitmiyor). "Öyle bir şey demedim" cümlesinin model mi yoksa hazır inkâr satırı mı olduğu **doğrulanmadı**; tezgâhın hazır teklif satırının (`bold_acts.py:808-819`) NPC sözü olarak kaydedilip kaydedilmediği de doğrulanmadı.
6. **Pazarlıkta indirim yazan kod yok (yüksek).** `npc['price_cut_cp_v1']` okunuyor (`shop_trade.py:70-74`) ama yazan yok; oda fiyatı sabit. İkna zarının hangi yolda atıldığı **doğrulanmadı**. Madde 37.
7. **Yemek/içmek hiçbir şeyi düşürmüyor; ok sayacı hiç dolmuyor (yüksek).** Ön okuma türlerinde "tüket" yok (`front_proposal.py:22`); eski sınıflandırıcının `use_item` dalı bilerek hiçbir şey değiştirmez (`game.py:15806-15809`). Eşyalarda tür alanı yok (`equipment_economy.py:571-597` yalnız `item_id`, `name`). Ok sayacı `world_state['ammunition']` ayrı ve hiçbir yerde tohumlanmıyor (yalnız `weapon_attack.py:594` okur, `1015` azaltır); boşken yay saldırısı `no_ammunition` ile reddedilir. "Ağır/Hafif Tatar Yayı & 20 Ok" paketleri kataloğa göre `bolt` ister (`weapon_catalog.py:40-66`). Madde 54, 56, 107 (T7).
8. **Kişisel bilgi hiçbir kalıcı kayda yazılmıyor; hatırlama sorusu Python inkârına düşüyor (orta-yüksek).** Olağan konuşma yolunda `record_npc_interaction` bilerek atlanır (`game.py:14704-14713`); oyuncunun satırı yalnız 4'lük `npc_speech_log`'da (`local_dialogue.py:26-43`) ve kimsenin geri okumadığı `npc_statements[].player` alanında kalır. "hatırlıyor musun / söylemiştim" `is_npc_historical_claim` (`game.py:1143-1164`) ile iddia sayılır; `claim_support` yalnız NPC'nin kendi sözlerine bakar (`npc_statements.py:678-727`); dayanak yoksa Python `_CLAIM_DENIAL_LINES[0]`'ı yazar (`game.py:7006-7008, 21265-21287, 21720-21746`). Kaydet-yenile ayrı neden DEĞİL. Oyuncunun ADI kalır, çünkü ayrı kod onu `npc["memory"]`'ye yazar (`local_dialogue.py:769-785`). Madde 116. Kadir'in oyununda inkârı hangi dalın (doğrudan Python dalı mı, konuşma yedeği mi) ürettiği **doğrulanmadı**.

## 3. Tasarım

### 3a. Tek para sahibi (anlam kararı)
**Kural:** Bir turda paranın ne anlama geldiğine yalnız `money_owner.decide` karar verir. Parayı hareket ettiren yer değişmez: kese ve defter yine yalnız `economic_actions` ve `shop_trade` tarafından yazılır. Diğer okuyucular (tezgâh, oda, iş kapısı, kart açma) kelimeye bakmaz, bu kararı okur.

**Model önerir:** ön okuma şemasına `kind`'in hemen arkasına bir `deal` alanı eklenir (küçük modeller sondaki alanları boş bırakıyor, şema notu):
`deal = {kind: goods | room | tip | gift | paid_before | none, goods_key: <listelenen mal anahtarlarından biri veya "">, keep_change: bool}`.
Kelime listesi yok: anlamı model okur.

**Python doğrular (yapısal kurallar, kelimesiz):**
- `goods`: konuşulan kişi satıcı (`shop_trade.is_vendor`), `goods_key` onun mallarında, savaş yok (R11) → tezgâh teklifi açılır; para varsa ve fiyat ≤ para ≤ kese ise teklife "uzatılan para" olarak bağlanır.
- `room`: kişi hancı/sunucu, oyuncunun o gece odası yok, para varsa oda fiyatı ≤ para ≤ kese → Oda kartı.
- `tip`: §3b.
- `gift`: kişi orada, tutar ≤ kese, tutuklama/rüşvet durumu değil (o yol aynen kalır) → Hediye kartı.
- `paid_before`: kart açılmaz; doğruluk kartı makbuzları gösterir ("ödendi: bira 4 bakır, Marek'e" ya da "kayıtta ödeme yok"); NPC buna göre doğal konuşur. Madde 3.
- **J-013 (§12 D29) ile güncel:** teklif açmak para uzatmak değildir. `goods` ve `room` sıfır tutarla da geçerlidir: teklif/kart açılır, para bağlanmaz; pozitif tutar koşulu (fiyat ≤ para ≤ kese) yalnız uzatılan para içindir. `gift` ve `tip` en az 1 bakır ister. Geçerli bir model önerisi doğrulamada düşerse karar `unclear` olur (kaynak `model`); yapısal tahmine de kelime yoluna da inilmez. Eski kelime yolu yalnız karar hiç yoksa çalışır: para yok ve `deal` yok/`none`.
- `none` ya da alan yok/bozuk ama para uzatıldı → **onarım, sessiz hediye yok:** yalnız iki yapısal anlam denenir: (1) bu kişinin açık tezgâh teklifi var ve para yetiyor → o teklifin parası (bugünkü `18415` dalı); (2) kişi sunucu, oda yok, oda fiyatı ≤ para ≤ kese → Oda kartı (oyuncu kartta görür, iptal edebilir). İkisi de değilse kart açılmaz; doğruluk kartına "oyuncu para gösterdi, ne için olduğu belli değil, para el değiştirmedi" yazılır ve NPC doğal olarak sorar. Senaryo 16 ve 18 bu yolla da geçer.
- ~~Doğrulama düşerse `deal` yapısal onarıma iner~~ (D29 ile kalktı): doğrulama düşerse (satıcı değil, kese yetmiyor) karar `unclear` olur; hiçbir durumda reddedilen bir öneri para hareket ettirmez ya da başka bir kart açtırmaz. Bir turdaki tek tutarı yalnız tek işlem sahiplenir (`money_owner.claim`, D5).

**İş kapısı (110; güncel kural §11 D4 ve karar 57):** "Oyuncunun elinden para çıkan satır asla iş yapmak değildir": `money_owner.blocks_money_moves(session)` bu turda para kararı varsa ve tutarı 0'dan büyükse doğrudur. Kural tek yerdedir, `_carry_out_thread_turn` girişi: bu doğruysa iş kapısının para hareket ettiren iki kararı (`work` ve `pay`) uygulanmaz, satır kişiye söylenmiş sayılır; `_thread_gate`, `_front_work` ve onlara düşen yollar aynı kuralı buradan okur. ~~Ayrıca ön okuma VARKEN eski kelime listesi `_thread_gate` artık `work` kararı veremez~~ (D4(a) ile kaldırıldı: para uzatılmayan satırda eski liste ön okuma olsa da olmasa da aynen çalışır). Böylece oda cümlesi ne işi bitirir ne saati ilerletir.

**Kaldırılan:** `_tell_the_coin`'in "kimse sahiplenmediyse hediye" varsayılanı. Kart açma `money_owner.open_card_after_reply` içine taşınır ve yalnız kararın söylediği kartı açar.

**Pazarlık (37):** Açık bir teklifin (oda kartı ya da tezgâh teklifi) karşı tarafına karşı aynı turda başarılı bir İkna/Gözdağı/Aldatma zarı → motor o teklife sabit indirim yazar: fiyatın %10'u, aşağı yuvarlanır, en az 1 bakır (oda 50 → 45). Kişi başına oyun günü başına bir kez. Kart yeni fiyatla yeniden hazırlanır; doğruluk kartı "indirim: oda 45 bakır (ikna başarılı)" der. Başarısız zar fiyatı değiştirmez, kart "fiyat aynı" der. Oda fiyatı `bold_acts._ROOM_PRICE` sabitinden `room_price(world, npc)` fonksiyonuna geçer (indirim dahil). Zarın atıldığı yer §11 D13'te bulundu (`deterministic_check_for_action`, zar `game.py:15507-15540`); senaryo 03'te o bloğa gerçekten ulaşılıp ulaşılmadığı doğrulanmadı ve plan işe bunu sınayan bir testle başlar (D13).

### 3b. Reddedilen para ve bahşiş
**Bahşiş ("üstü kalsın"):** `deal.keep_change=true` ve para fiyattan fazlaysa Python bahşişi kendisi hesaplar: `bahşiş = uzatılan − fiyat`. Model hiçbir zaman rakam vermez. Bahşiş tezgâh teklifine (`flags.counter_offer_v1.tip_cp`) yazılır; onayda `counter_purchase_offer` bir "Bahşiş" satırı (alıcı satıcı) ekler; mevcut çözümleyici, makbuz ve geri al bu satırı zaten taşır. Teklif ve anlatı toplamı açık söyler: "bira 4 + bahşiş 1 = 5 bakır"; onaylanan toplam 5'tir (bu yalnız panel "evet" yolunda; onay kuralı §11 D1). Açık teklif yokken `deal.kind=tip` → ayrı "Bahşiş" kartı (Hediye değil). Onay adımı kalır (R7).
**Panel "hayır" yolu (§12 D34):** bahşiş tezgâh teklifine yazılmaz; tezgâh teklifinin tender'ı fiyata eşittir ve Python'un bahşiş rakamı teklifte `tip_after_cp` olarak bekler. Bahşiş kartı ancak mal satışı başarıyla makbuzlandıktan sonra açılır. Bu iki ayrı işlemdir: iki onay, iki makbuz. Geri Al tek adımdır (§13 D37): yalnız son onayı geri alır; bahşiş onaylandıktan sonra mal Geri Al ile geri alınamaz. Mal satılmazsa (ret, iptal, fiyat değişti, kese yetmedi) bahşiş kartı açılmaz ve `tip_after_cp` silinir.

**Ret (103) — güncel kural (§11 D3, D14 ve §12 D25, D26):** Konuşma şemasında iki isteğe bağlı alan vardır: `coin_answer: takes | declines | none` ve `coin_answer_for: <bu tur bu NPC için listelenen kalem kimlikleri> | unclear`. Kalem kimliklerini motor kurar, model yalnız listeden seçer: `tip`, `gift`, `room`, `goods:<mal anahtarı>`. Liste o NPC'ye bu turdaki para kararından ve o NPC'ye açık kart/tekliflerden çıkar.
1. `declines` + listelenen kalem → yalnız o kalem reddedilir. `tip`: tezgâh bahşişi (`tip_cp`/`tip_after_cp`) silinir, açık Bahşiş kartları iptal edilir; mal teklifi sürer. `gift`: açık Hediye kartları iptal edilir. `room`: o NPC'ye açık oda kartı iptal edilir. `goods:<k>`: o malın tezgâh teklifi kapanır.
2. `declines` + `unclear` (ya da kalem eksik/bozuk/listede yok) → **kapsamı belirsiz genel ret**: o NPC'ye açık bütün para kartları ve tezgâh teklifi iptal edilir, hiçbir kart açılmaz, ödeme ilerlemez; NPC doğal konuşmayla netleştirir.
3. Ret sürerken reddedilen kalem için o NPC'ye yeni kart açılmaz ve onay para kesmez: panel hazırlığı `refused`/`npc_declined` döner ("<ad> az önce parayı geri çevirdi."), tezgâh onayı `npc_declined` ile reddedilir ve hiçbir şey değişmez.
4. Ret yalnız iki yolla kalkar: aynı NPC aynı kalem için **açık** `takes` verir (genel retten yalnız o kalem çıkar), ya da oyun günü değişir. `none`, eksik, bozuk ya da listede olmayan cevap reddi korur. Ret anında iptal edilen kartlar gün değişince geri gelmez; yeni kart yeniden hazırlanmalıdır.
5. Kayıt sınırı 32 NPC'dir. Yer gerekirse önce önceki günlerin (zaten süresi bitmiş) kayıtları düşer. 32 kaydın hepsi bugünkü ise yeni ret yazılamaz; bu durum sessiz değildir, `decline_cap_full` olarak loga yazılır ve o turda yine kart açılmaz.
Model önerisi hiçbir zaman para YARATAMAZ ya da hareket ettiremez; yalnız kart/satırı durdurabilir. Kaydı `economic_actions` tutar (D17).

### 3c. Tüketim ve mühimmat
**Güncellik notu:** bu bölümün eşya türü ve tohumlama kısımları §11 D6 (tohum yalnız saldırı anında, eşya üstündeki `ammo_seeded_v1` işaretiyle), D18 (tek kaldırıcı `equipment_economy.remove_item`) ve D24 (eşyaya `kind` yazılmaz, tür yalnız tablodan) ile değişti; aşağıdaki metin tarihçedir, güncel arayüz §4'tedir.
**Eşya türü veri ile:** eşya kaydına isteğe bağlı `kind` alanı (`food` | `drink`). Tek tablo: `content/items/item_use.json` → `kinds` (tam etiket → tür: "Bira", "Şarap", "Tabak yemek"...) ve `ammunition` (paket etiketi → adet: "Kısa Yay & 20 Ok": 20, ...). Tezgâh satışında `grant_named_item` türü o an yazar; eski kayıtlar için okuma anında tablodan bakılır (kayıt yeniden yazılmaz). `resource_type` kullanılmaz (günlük erzak düşümüne karışmasın).

**Tüketme:** ön okumaya yeni tür `consume` + `item_id` (çantadaki kimliklerden; `hand_over` ile aynı doğrulama). Python: eşya çantada, kuşanılmış değil, türü `food`/`drink`, savaş yok, oyuncu ayakta → tek yardımcı `item_use.consume(world, item_id)` eşyayı düşürür ve dünyayı doğrular. Tür uymazsa (ör. kılıç) → onarım: sıradan deneme anlatısı, hiçbir şey düşmez. Mekanik etki ve ek süre yok. Doğruluk kartı "bu tur: Bira içildi" der. Ön okuma kapalıyken bugünkü durum sürer.

**Mühimmat:** `item_use.ensure_ammunition(world)`: çantada etiketi tabloda olan her eşya için, o eşya daha önce sayılmadıysa (`ammunition_seeded_items` listesinde kimliği yoksa) sayacı artırır; tür `weapon_catalog.lookup(etiket)['ammunition_type']`'dan (tatar yayları `bolt`, yaylar `arrow`). Çağrıldığı yerler: karakter yaratma sonu, kayıt yükleme, menzilli saldırının hazırlığı. Etiket ("& 20 Ok") değişmez (testler sabitliyor); kalan sayı doğruluk kartında ve envanter cevabında "(ok: 19)" diye görünür. Atılan okların geri toplanması yok.

### 3d. Doğruluk kartı
**İki ayrı görünüm, tek modül (§12 D28):** `truth_card.narrator_view(world, *, npc, this_turn, max_bytes=600)` anlatıcı içindir ve oyuncunun görebildiği her şeyi taşır (aşağıdaki içerik). `truth_card.npc_view(world, *, npc, held_out_cp, this_turn, max_bytes=600)` konuşulan NPC içindir ve ayrı kurulur: yalnız o NPC'nin kendi gördüğü/duyduğu ya da kendi işlemine ait bilgiyi taşır. NPC görünümünde **kese toplamı, çanta, başka NPC'lere ödemeler/teklifler, başka NPC'lere söylenenler, çıkışlar yoktur**. Kese yerine "oyuncunun sana uzattığı: N bakır; para henüz el değiştirmedi" yazılır. Ödemeler yalnız `payee_id == npc` olanlardır; açık teklif yalnız o NPC'ninkidir; oda satırı yalnız oda o NPC'nin yerindeyse; fiyatlar yalnız o NPC'nin malları (sunucuysa oda); "bu tur" yalnız o NPC'ye bağlı notlardır (`_turn_notes` satırları NPC kimliği taşır). Süzme, satır seçiminden ve bütçelemeden ÖNCE yapılır. İkisi de düz Türkçe metindir, yalnız motor durumundan okur, hiçbir şey yazmaz; gizli NPC adı, gizli stok, özel geçmiş YOKTUR. Konuşma başlığı: "SENİNLE OYUNCU ARASINDAKİ İŞLER (motor; salt okunur):" (D18'deki konuşma başlığının yerine). Anlatıcı başlığı D18'deki gibidir.

**Ekleme noktaları (hepsi aynı fonksiyonu çağırır):**
1. Konuşma yolu: `_experimental_speech_note` içinde (`game.py:8555-8623`), `bold_acts.speech_note` eklenmeden hemen önce (`~8621`); oyuncu mesajından önceki son not.
2. Anlatıcı yolu: `ask_dungeon_master` istem metninde `_bag_note` satırının arkasında, `NARRATION FACTS`'ten önce (`game.py:13626-13629`), "MOTOR GERÇEĞİ (salt okunur)" başlıklı ayrı bölüm. `KOMPAKT WORLD CONTEXT…VERIFIED LORE` ve `CURRENT LOCAL SCENE STATE…RECENT NARRATION` dilimlerinin DIŞINDA (4 test bu dilimleri kesip JSON okuyor).
3. `interaction` dalının JSON yükü (`13376-13379`). (`exploration_resolved` dalı §11 D16 ile çıkarıldı.) Konuşma yolu (1) `npc_view`, anlatıcı yolları (2, 3) `narrator_view` kullanır.
`build_world_context` içine KONMAZ (4800 baytlık süreklilik paketini ve defteri iter; konuşma yolu onu hiç çağırmaz).

**İçerik (sırayla):** konuşulan kişi (görünen adı/rolü) · kese (panelle aynı biçimde: altın/gümüş/bakır) · çanta (ilk 8 ad + "ve N eşya daha", mühimmat sayısı) · oda (tutuldu: yer, ne zamana kadar / yok) · açık teklif veya kart + "para henüz el değiştirmedi" · son ödemeler (en çok 3: ne, kaç bakır, kime, kaç tur önce) · bu tur değişenler (tüketilen, reddedilen para) · fiyatlar (konuşulan satıcının malları ve sunucuysa oda fiyatı, indirim dahil, "başka fiyat söyleme") · çıkışlar (motorda kayıtlı olanlar; yoksa "kayıtlı çıkış yok").
**Bayt bütçesi (güncel, §12 D33):** her görünüm en çok 600 bayttır; ölçüm başlık dahil **tamamlanmış UTF-8 metin** üzerinde yapılır (Türkçe harfler 2 bayt sayılır). Önce isteğe bağlı satırlar şu sırayla düşer: çıkışlar → eski ödemeler (1 kalır) → çanta kuyruğu → fiyatlar (açık teklifin malı ve oda kalır, D19). Hâlâ aşıyorsa zorunlu alanlar için taşma kuralı: (1) uzun ad/yer/etiket değerleri kelime sınırında kısaltılır ve "…" alır; (2) yine aşıyorsa zorunlu satırlar öncelik sırasının tersinden düşer: kişi/kese/oda → bu turun sonucu → aktif işlem (açık teklif/kart, uzatılan para) en son ve hiçbir zaman bütünüyle düşmez, gerekirse karakter sınırında kesilir. Düşen her zorunlu satır son satırdaki "(kısaltıldı: …)" işaretinde adıyla yazılır ve loga gider; kritik sonuç sessizce düşmez. Öncelik: aktif işlem > bu turun sonucu > anı (hafıza görünümü, §3e). Belirlenimci: aynı durum aynı metni verir. Son istemin gerçek boyu (bayt ve, sunucu bildiriyorsa, token) ölçüm koşusunda kaydedilir; 600 bir hedeftir, bütçenin yettiği ancak ölçümle gösterilir.
**Makbuz etiketi:** `economic_ledger.operations[op]` yeni kayıtlarda kısa `label` ("oda (bir gece)", "bahşiş") ve `payee_id` taşır (motor yazar). Eski kayıtlar "ödeme N bakır" diye gösterilir. Tezgâh defteri zaten kişi ve mal taşıyor.
**Bırakılan:** `price_note` ve `room_note` olduğu gibi kalır (testleri var); kart onların yanına gelir. Panel onayı anlatıcı çağırmaz; bir sonraki tur kartın "son ödemeler" satırı bunu taşır.
**Hazır satırlar:** tezgâhın hazır teklif satırı ("Bira 4 bakır…") NPC'nin kendi sözü olarak `npc_statements`'e kaydedilir (bugün kaydediliyorsa değişiklik yok; plan doğrular), böylece "4 bakır demiştin" hatırlaması dayanak bulur.

### 3e. Kişisel hafıza
**Güncel kural (§11 D10 ve §12 D27, D30, D31 ile).** Kaynak ile görünüm ayrıdır: **kaynak** motorun sakladığı tam söz kaydıdır; **görünüm** modele giden kısa metindir. Dilim 1'in dürüst sözü: "NPC başına son 40 seçilmiş söz"; tam arşiv sonraki iştir, 116'nın uzun süreli hafıza kabulü bu dilimle tamamen kapanmış sayılmaz.
**Kayıt (motor sahipli):** yeni modül `npc_told`, `world_state["npc_told_v1"] = {npc_id: [{"turn": int, "text": str, "cut": true?}]}`. Anlamı: "oyuncu bu NPC'ye bunu söyledi". Doğru olduğu iddia edilmez. Kampanya ve karakter kapsamı dış kapsayıcıdan (o kampanyanın `world_state`'i) gelir; satırda tekrarlanmaz. Kaynak action/revizyon bağı ve "düzeltme ↔ eski söz" bağı Dilim 1 dışıdır (§10).
**Doldurma (model önerir, Python doğrular, kaydeder):** NPC konuşma şemasına erken bir alan: `remember_player_line: bool` ("oyuncu bu satırda sana kendisi hakkında hatırlamaya değer bir şey anlattı mı?"). Model yalnız evet/hayır der; kayda **oyuncunun kendi sözü** yazılır, model özeti değil; böylece model içerik uyduramaz. Kabul edilen söz **600 karaktere kadar tam** saklanır. 600'ü aşan söz kelime sınırında 600'e kesilir ve `cut: true` taşır; kesilmiş satır görünümde bağlam olabilir ama hiçbir zaman destek/kanıt sayılmaz.
**Sınırlar (güncel):** NPC başına en çok **40** `remember=true` kaynak; 41. gelince o NPC'nin en eski satırı düşer. En çok 32 NPC; 33. NPC yazılınca en uzun süredir yazılmayan NPC'nin kaydı düşer ve bu loga yazılır. Önem sıralaması yok. Görünüm: en çok **3** satır, her satır en çok **200** karakter (daha uzunsa kelime sınırında kesilir ve "… (kısaltıldı; tamamı kayıtta)" işareti alır), başlık ve tırnaklar dahil toplam en çok 600 bayt (UTF-8). (Aşağıdaki "12 satır / 200 karakter" sözleri tarihçedir.)
**Getirme ve destek ayrıdır (D31):** `relevant` ve `context_rows` yalnız görünüm seçer; `supports` iddia kapısının tek dayanağıdır. `supports` yalnız gerçek örtüşmesi olan (en az bir ortak kök), kesilmemiş, o NPC'ye ait satırları döner; örtüşme yoksa boş döner. "En yeni 3 satır" yalnız `context_rows` ile bağlam olarak verilir ve inkâr korumasını (Python inkârı, `experimental_unverified_claim`, yankı süzgeci) hiçbir zaman kaldırmaz. Destek kararı satırın tam kaynak metnine bakar, görünüm parçasına değil.
**İddia kapısı (güncel):** `claim_about` önce NPC sözü/vaadi kalıplarına bakar: cümlede bunlardan biri varsa (aynı cümlede "ben söylemiştim" de olsa) `npc_words` olur ve kayıt destek sayılmaz. Bilinçli ürün kararı: örtüşmesiz bir "geçen sefer ne demiştim?" sorusunda inkâr korumasının hazır cevabı kalır; NPC hatırlamadığını söyler (oynayışta bakılacak).
**Koruma (değişmedi):** Python yazmaz eğer: NPC konuşulan kişi değil ya da orada değil, savaş var, NPC ölü, satır soru, satır mevcut `is_npc_historical_claim` ile geçmiş iddiası (bunu iddia kapısı yargılar), satır NPC'nin gizli profil değerlerini içeriyor (bugün `recent_player_utterances` için yapılan kontrolün aynısı). Yazma noktası: `_remember_experimental_npc_speech` (`game.py:8029-8046`).
**Kayıt, Geri Al ve atomiklik (D32):** anahtar `world_state` içindedir; ayrı bir kayıt sahibi yaratılmaz. "Mevcut yol taşır" bir varsayım olarak kalmaz, testle gösterilir: kayıttan önce hata → eski dünya ve eski hafıza; commit sonrası yanıt kaybı → aynı işlemin yeniden gönderilmesi makbuzla aynı sonucu ve tek öğrenmeyi verir; aynı action → bayt bayt aynı yanıt ve tek satır; yeni oturum/yönetici ile gerçek yeniden açma → hatırlama sorusu orada sorulur; Geri Al sonrası → hem kaynakta hem bütün konuşma girdisinde geri alınmış söz yoktur.
*(Aşağıdaki metin tarihçedir; çelişirse yukarıdaki güncel kural geçerlidir.)*
**Sınırlar (eski):** NPC başına 12 satır, en çok 32 NPC; dolunca en eski satır / en uzun süredir yazılmayan NPC düşer. Önem sıralaması yok.
**Getirme (en çok 3 satır):** `npc_told.relevant(world, npc_id, text, limit=3)`: oyuncunun şimdiki satırı ile kayıt satırları arasındaki ortak kelime kökleri (en az 4 harfli kelimelerin, katlanmış, ilk 5 harfi) sayılır; puanı 0'dan büyük en iyi 3 satır konuşma bağlamına "oyuncunun sana daha önce söyledikleri (söylendi; doğruluğunu bilmezsin)" diye girer. Bu bir liste değil, genel bir benzerlik ölçüsüdür. Toplam ≤ 600 bayt.
**İddia kapısı:** `game.py:21188-21287` dalında inkârdan önce `npc_told.supports(world, npc_id, claim)` çağrılır:
- Hatırlama oyuncunun KENDİ sözleri hakkındaysa (bugün `claim_support` → `absent`) ve kayıtta örtüşen satır varsa → destekli: Python inkârı yazılmaz, `experimental_unverified_claim` kurulmaz, model satırlarla cevap verir. Örtüşme yoksa ama kayıt boş değilse en yeni 3 satır verilir; model "bana X'ten bahsetmiştin ama bundan değil" diyebilir.
- İddia NPC'nin kendi sözleri ya da başkası hakkındaysa (`unsupported`) kayıt yalnız örtüşme varsa sayılır; yoksa bugünkü inkâr aynen kalır. `narrative_memory` test_5'teki uydurma ("Elaris bana ejderha hazinesinden bahsetmişti") hâlâ inkâr edilir.
**Kayıt ve geri al (eski):** anahtar `world_state` içinde → kaydet, yenile ve geri al mevcut yolla taşır. Doğrulama §5.

## 4. Modül sınırları

Güncel tablo (§11 D5–D18, D24 ve §12 D25–D34 birleştirildi; eski tablo kaldırıldı, tarihçesi D17 ve §12 D36'da). Kural: anlamı `money_owner` verir; parayı, makbuzu ve reddi `economic_actions`, tezgâh satışını ve indirimi `shop_trade` yazar; kart yalnız okur; hafızayı yalnız `npc_told` yazar. `money_owner` `game`'i içeri almaz; oturumu `game.py`'deki ince sarmalayıcılar bağlar.

| Modül | Sahip olduğu (tek yazar) | Güncel arayüz (niyet düzeyi) | Yazmadığı |
|---|---|---|---|
| `ai-dnd/money_owner.py` (yeni) | Bir turdaki paranın anlamı; uzatılan paranın tek tüketicisi; hangi kartın açılacağı; konuşma şemasının kalem listesi; pazarlık sonucu satırı | `read_deal(front, listed) -> Deal \| None`; `decide(world, *, person, amount_cp, deal, arrester) -> CoinDecision \| None` (D15 rüşvet önce; D29 sıfır tutarlı teklif; düşen model önerisi → `unclear`); `current(session)`; `claim(session, purpose) -> int \| None`; `blocks_money_moves(session) -> bool`; `parts_for(world, session, npc_id) -> list[str]`; `open_card_after_reply(session, result, coin_answer=None, coin_answer_for=None)`; `haggle(session, npc, check_result) -> str \| None` | kese, defter, makbuz, ret kaydı, fiyat/indirim |
| `ai-dnd/economic_actions.py` (var) | Kabul/ret kaydı, makbuz etiketi, bahşiş satırı | `DECLINE_CAP = 32`; `game_day(world)`; `record_decline(world, npc_id, part, amount_cp, *, day, turn) -> DeclineWrite`; `clear_decline(world, npc_id, part)`; `declined(world, npc_id, part, *, day) -> bool`; `recent_payments(world, limit=3, payee_id=None)`; `counter_purchase_offer(..., tip_cp=0)`; `repair_declines(world)`; `repair_ledger_labels(world)` | paranın anlamı |
| `ai-dnd/shop_trade.py` (var) | Tezgâh satışı ve onay kuralı, indirim | `_tip(world, npc_id, key, count, fresh)`; `commit` (D1 kuralları; ret sürerken `npc_declined`; B yolunda başarılı satıştan sonra bahşiş kartı isteği); `apply_cut(world, npc, key, base_cp)`; `_cut(npc, key, day)` | ret kaydı |
| `ai-dnd/bold_acts.py` (var) | Oda kartı ve tezgâh teklifinin açılması (karar okuyarak); oda fiyatı | `room_price(world, npc)`; `held_out_coin` → `money_owner.claim`; `_with_tender` (A yolu `tip_cp`, B yolu `tip_after_cp`); `drop_counter_tip(world, npc_id)`; `repair_counter_tip(world)` | paranın anlamı (karar varken kelime okumaz) |
| `ai-dnd/truth_card.py` (yeni) | Hiçbir şey (salt okur) | `narrator_view(world, *, npc, this_turn, max_bytes=600) -> str`; `npc_view(world, *, npc, held_out_cp, this_turn, max_bytes=600) -> str`; ortak iç yardımcı `_fit(lines, max_bytes)` (D33 taşma kuralı) | her şey |
| `ai-dnd/item_use.py` (yeni) | Tüketim kararı, ok sayacı tohumu | `kind_of(item)` (yalnız tablodan, D24); `consume(world, item_id) -> ConsumeResult`; `ammo_available(world, ammo_type)`; `ensure_ammunition(world)` (yalnız saldırı anında, D6); `ammo_note(world)` | envanter (düşürmeyi `equipment_economy.remove_item` yapar) |
| `ai-dnd/npc_told.py` (yeni) | "Oyuncu bu NPC'ye bunu söyledi" kaynağı | `KEEP_PER_NPC = 40`, `MAX_NPCS = 32`, `MAX_CHARS = 600`, `VIEW_ROWS = 3`, `VIEW_CHARS = 200`, `VIEW_BYTES = 600`; `remember(world, npc_id, player_line, *, turn) -> bool`; `relevant(world, npc_id, text, limit=3)`; `context_rows(world, npc_id, limit=3)`; `supports(world, npc_id, claim, *, about) -> list[str]` (yalnız örtüşen, kesilmemiş satırlar); `view(rows, *, header, max_bytes=600, max_chars=200) -> str`; `repair(world)` | iddia kararı |
| `ai-dnd/npc_statements.py` (var) | NPC'nin kendi sözleri | yeni saf `claim_about(claim) -> "own_words" \| "npc_words" \| "memory"` (NPC sözü kalıbı önce, D31) | oyuncunun sözleri |
| `ai-dnd/front_proposal.py` (var) | Ön okuma şeması | `listing()["goods"]`; şemada `deal`, `deal_goods`, `keep_change`; `consume` türü; `names_coin(line)`; `begin` oturum alanlarını sıfırlar | para kararı |
| `ai-dnd/equipment_economy.py` (var) | Envanter | yeni `remove_item(world, item_id)` | — |
| `ai-dnd/game.py` (var) | Yalnız bağlama | sarmalayıcılar `_hand_over_coin`, `_tell_the_coin` (adları korunur); konuşma şeması (`coin_answer`, `coin_answer_for`, `remember_player_line`, hepsi isteğe bağlı); iddia kapısı; `_carry_out_thread_turn` para kuralı; `_repair_dilim1_fields` (`load_game` içinde) | yeni alanların hiçbiri doğrudan |

Anlatıcı ve konuşma istemleri yalnız OKUR. `api/character_creation.py` değişmez (D6: yaratmada tohumlama yok).

## 5. Veri, doğrulama ve kayıt

**Yeni/genişleyen `world_state` alanları (güncel; §11 ve §12 birleştirildi):**
- `npc_told_v1`: `{npc_id: [{turn:int≥0, text:str 1..600, cut?:true}]}`; ≤40/NPC, ≤32 NPC (D27, D30). En kötü durum boyu: 32 × 40 × 600 karakter ≈ 768.000 karakter; Türkçe harflerle kayıtta yaklaşık 1–1,5 MB (hesap, ölçüm değil; §8).
- `flags.money_declined`: `{npc_id: {part: {amount_cp:int≥0, day:int, turn:int, taken?:[part]}}}`; `part` ∈ `tip`, `gift`, `room`, `goods:<anahtar>`, `*` (kapsamı belirsiz genel ret; `taken` o genel retten açık `takes` ile çıkan kalemlerdir). ≤32 NPC; yer gerekirse önce önceki günlerin kayıtları düşer; bugünkü kayıt sessizce düşmez (D25, D26). Süre tur sayısıyla değil, kabul ya da gün değişimiyle biter (D3).
- `flags.counter_offer_v1.tip_cp` (panel "evet" yolu): isteğe bağlı, int ≥ 1; yalnız D1'deki koşullarla geçerli. `flags.counter_offer_v1.tip_after_cp` (panel "hayır" yolu, D34): isteğe bağlı, int ≥ 1; mal satışı başarıyla makbuzlanınca Bahşiş kartına dönüşür ve silinir.
- `flags.economic_ledger.operations[op].label` (≤40 karakter) ve `.payee_id`: isteğe bağlı, yalnız yeni kayıtlarda; `economic_actions` yazar (D17).
- `npc.price_cut_cp_v1[anahtar]` (oda için `"room"`) ve `npc.price_cut_day_v1`: indirim yalnız o oyun günü geçerli, yerine geçer (D13).
- Eşya kaydına alan yazılmaz; tür yalnız `content/items/item_use.json` tablosundan, tam ada göre bulunur (D24). `quantity` kuralı (yalnız 1) değişmez.
- `ammunition` (var olan alan; artık yalnız ilk menzilli saldırıda tohumlanır) ve eşya üstünde `ammo_seeded_v1: true` (D6). `ammunition_seeded_items` alanı YOK.
- Oturumda kalan, KAYDEDİLMEYEN (her tur `front_proposal.begin` sıfırlar): `session._coin_decision`, `_coin_answer`, `_coin_answer_for`, `_coin_claimed`, `_turn_notes` (her not `(npc_id | None, metin)` biçiminde; NPC görünümü yalnız kendi kimliğini taşıyan notları okur, D28).

**Kampanya doğrulaması (`api/persistence/campaign_validation.py`):** ~~her yeni alan için şekil ve sınır denetimi~~ → güncel kural §11 D7: onarım `load_game` içinde, alan sahiplerinde; doğrulayıcı bu isteğe bağlı alanlar için hata fırlatmaz. Bozuk veri kaydın tamamını reddettirmez: bozuk satır atılır, ne atıldığı loga yazılır (onarım; sıfır tolerans "kayıt kaybı yok" demektir). Bilinmeyen eşya alanları bugün de serbest (`equipment_economy.py:232-279`).
**Geri al:** tüm yeni alanlar `world_state` içinde; tur geri alınınca anlık görüntüyle döner. `reconcile_offers_after_undo` aynen kalır. Panel "evet" yolunda bahşişli tezgâh alışverişi tek makbuzdur: tek Geri Al keseyi, satıcının kesesini, eşyayı ve bahşişli teklifi birlikte döndürür. Panel "hayır" yolunda (D34) iki makbuz vardır, ama Geri Al **tek adımdır** (§13 D37; motor kuralı değişmez): Geri Al yalnız en son tamamlanan turu, yani son onaylanan makbuzu geri alır. (1) Son tur bahşiş onayıysa: Geri Al yalnız bahşiş ödemesini döndürür ve Bahşiş kartı yeniden `prepared` olur (bugünkü `reconcile_offers_after_undo` kuralı: geri alınan işlemin tükettiği kart yeniden açılır, C11/D2; `AI-DND-c-merge` 3c733c57 `economic_actions.py:1309-1332` okundu, çalıştırılmadı). Mal makbuzu yerinde kalır. Ardından gelen ikinci Geri Al `409 undo_unavailable` alır ve hiçbir şeyi değiştirmez; mal onayını hedefleyen Geri Al da (bahşiş onayından önce ya da sonra) `409 undo_unavailable` alır. (2) Son tur mal onayıysa (bahşiş henüz onaylanmadı): Geri Al malı, 4 bakırı ve tezgâh teklifini (bekleyen `tip_after_cp` dahil) döndürür; o onayda açılan Bahşiş kartı `cancelled` olur (geri alınan turdan sonra hazırlanmış kart). Plan Görev 9 senaryo 25 B adım 3 ve 7, `test_b_path_undo_right_after_the_goods_takes_back_the_beer_and_closes_the_tip_card` ve `test_b_path_after_the_tip_confirm_one_undo_takes_back_only_the_tip` bunu sabitler.
**Tekrar (aynı `action_id`):** bugünkü bayt bayt tekrar yolu geçerli; kayıt satırı ve tüketim tur içinde yazıldığı için iki kez yazılmaz. Bu artık varsayım değil, D32 testleriyle gösterilir (kayıt öncesi hata, commit sonrası yanıt kaybı, bayt-aynı tekrar, gerçek yeniden açma, Geri Al sonrası sızıntı yok).
**Eski kayıtlar:** `npc_told_v1` yoksa boş başlar (geçmiş konuşmalardan doldurulmaz). Ok sayacı ilk menzilli saldırıda, işaretsiz paketten bir kez tohumlanır (D6; yüklemede tohumlama yok). Eşya türü okuma anında tablodan bulunur. Eski makbuzlar etiketsiz gösterilir. Sürüm numarası değişmez; hepsi isteğe bağlı alan.

## 6. Test stratejisi

**Güncellik notu:** bu bölüm §11 (D12, D20, D21) ve §12 (D25–D35) ile güncellendi. Senaryoların adım adım güncel hâli plandadır (`DILIM1_PLAN_20261104.md`).

**Kalkacak `known_broken` işaretleri (senaryo → adım):**
- 01 adım 3 (35): ~~senaryo ön okumalı hâle gelir~~ → D12: 01 yedek yolu sınamayı sürdürür ve işaret durur; ön okumalı ikiz `01b` işaretsiz geçer (parasız `deal goods` teklif açar, D29).
- 02 adım 2 (35): betiğe `deal {goods, bira, keep_change:true}`; panel "evet" yolunda adım tezgâhta `tip_cp 1, total 5` bekler; yeni onay adımı `/item shop_buy … 5` → kese 95, barmen 5, Bira 1. Panel "hayır" yolunda (D34) adım 2'de yolculuk gözlemi tezgâhta `tip_cp 0, total_cp 4` ve `kart: null` görür (`tip_after_cp` `tezgah` gözleminde yoktur; Görev 9'un birim testleri `test_b_path_tip_card_opens_only_after_a_paid_goods_receipt` ve `test_b_path_a_tip_decline_drops_the_waiting_tip_after_cp` teklifte bekleyen `tip_after_cp` değerini sınar); onay `… 4` → kese 96, Bira 1 ve Bahşiş kartı 1; ikinci onay → kese 95, barmen 5.
- 03 adım 2 (37): kart 45 bakır, metin "başarılı", "indirim"; onay adımı kese 55'e güncellenir. Adım 4 (38): `anlaticiya_giden` doğruluk kartındaki "oda tutuldu"yu görür.
- 04 adım 1–2 (54) ve adım 3 (56): senaryo ön okumalı; `consume` betiği; `source_items`'a 107 eklenir.
- 16 (3): `deal` yokken ya da `paid_before` iken kart açılmaz.
- 17 adım 3 (103): ~~panel kartı açılır, onay kesmez~~ → D3, D25, D26: ret kart açtırmaz; eksik/`none` cevap reddi korur; açık `takes` yalnız adı geçen kalemi açar; genel retteki öteki kalem (hediye) kapalı kalır.
- 18 (110 ve aynı adımdaki 115): iş kapanmaz, saat 0, Oda kartı 50. Senaryo 19'daki 115 işaretleri Dilim 2'de kalır.
- 36: sahte modelde işaret yok (rc1 gerçek zincir). Motor yarısı yeni senaryo 26 ile; gerçek yarısı kapıda rc1 koşusu.

**Yeni senaryolar:**
- `24_personal_memory` (116; `front_proposal: true`, iki NPC): kişisel bilgi (betik `speech.remember_player_line: true`) → `anlatilan` bilgiyi içerir (D20 d); beş dolgu konuşması; `reload` (D20 b; `reload_continue` yok); hatırlama sorusu → `inkar: false`, `konusmaya_giden` bilgiyi içerir, `yasak_metin` ["anımsamıyorum", "karıştırmış"]; uydurma kontroller (NPC'nin sözü hakkında, karışık cümle, kayıtsız ikinci NPC) → `inkar: true`; yalnız tek genel kök paylaşan iddia → `inkar: false` (D31, plan senaryo 24 adım 15: Python inkârı kalkar, model belirsizlik der); ikinci NPC'nin konuşma girdisinde birincinin bilgisi yok (D28). Gerçek zincir adımı ayrı. D27'nin "25 konuşma, en az 13'ü `remember=true`" ömür denetimi bu senaryoda **yoktur**; yalnız birim testidir (plan Görev 17 `test_twenty_five_talks_with_thirteen_kept_still_bring_back_the_first_fact`, konuşma yolundan geçer). Örnek cümleler Kadir'in oyunundan kopyalanmaz.
- `24r_personal_memory_real` (D35): kontrollü gerçek konuşma örneği; ilk anlatımda `remember_player_line` alanını model kendisi doldurur; beş kanıt ayrı raporlanır.
- `25_tip_in_one_line` (`zero_tolerance: true`): "bir bira, 5 bakır, üstü kalsın" tek satırda → tezgâh 4+1; onay → kese 95, barmen 5, Bira 1; aynı komutla yeni onay denemesi (bayat seq) hiçbir şey kesmez (D20 e); geri al → kese 100, barmen 0, Bira 0. Panel "hayır" yolunda iki işlem ayrı sınanır (D34); Geri Al tek adımdır (D37): mal onayından hemen sonraki Geri Al birayı döndürür ve Bahşiş kartını kapatır, bahşiş onayından sonraki Geri Al yalnız bahşişi döndürür ve bira kalır. Senaryoda art arda iki Geri Al adımı yoktur (düzenek 409'u kırık sayar); ikinci Geri Al'ın `409 undo_unavailable` alıp hiçbir şeyi değiştirmediği plan Görev 9'un HTTP testinde sınanır.
- `26_truth_card_price` (36, 2): tezgâhtan bira alınır; sonraki konuşma turunda `konusmaya_giden` ["bira 4 bakır", "Bira", "ödendi"]; anlatıcı turunda `anlaticiya_giden` aynı satırlar.
- `27_no_silent_gift`: sunucu olmayan kişiye `deal` olmadan para → kart yok; `deal gift` → Hediye kartı; `deal tip` açık teklif yokken → Bahşiş kartı.
- `28_consume_wrong_item`: `consume` önerisi kılıcı gösterir → hiçbir şey düşmez, kese ve çanta aynı.
- 18'in ikizleri: işsiz aynı satır → Oda kartı; "Tamam, işi yapıyorum" + ön okuma `work` → vardiya çalışır (8 saat, 26 bakır).

**Düzenek değişiklikleri — güncel hâli §11 D20 (`anlatilan`, `reload_continue` yok, `konus` adımı); aşağıdaki metin tarihçedir (`ai-dnd/api/tests/journeys`):** `NarratorInput` "speech" çağrılarını da tutar; yeni `expect` anahtarları `npc_sozleri` (kayıt satırlarında arar), `konusmaya_giden` (konuşma çağrısının girdisinde arar), `inkar` (cevap `_CLAIM_DENIAL_LINES`'tan mı); `tezgah` gözlemine `tip_cp`, `total_cp`; yeni `script` anahtarı `speech` (konuşma cevabına ek alanlar: `coin_answer`, `remember_player_line`); ön okuma betiğinde `item_name` → çantadaki kimliğe çevrilir (yalnız test tarafı); yeni eylem `reload_continue` (kayıttan açılan oturumla devam eder; bugünkü `reload` aynen kalır). `test_journey_schema.py:114-122`'deki sabit anahtar kümesi güncellenir.

**Birim testleri:** `money_owner` (her `deal` türü × doğrulama düşmesi → `unclear`; yapısal onarım yalnız `deal` hiç yokken; sessiz hediye yok; `blocks_money_moves`); `_carry_out_thread_turn`: para uzatılan "Oda için beş gümüş ödüyorum" satırında `work`/`pay` uygulanmaz (D4 b; eski liste para uzatılmayan satırda aynen çalışır); `truth_card` (600 bayt sınırı, kısaltma sırası, belirlenimcilik, gizli bilgi yok, test dilimlerine dokunmama); `item_use` (tür tablosu, tüketim, mühimmat tohumu tek sefer, tatar yayı → `bolt`, eski kayıt yükü); `npc_told` (sınırlar, koruma kuralları, getirme ≤3, destek/uydurma ayrımı, onarım); bahşiş makbuzu: kese −5, satıcı +5, eşya +1, tekrar onay 0, geri al hepsini döndürür; bahşişin para yetmeyince reddi (kese −4); ret: `declines` sonrası panel kartı açılmaz (D3).
**J-013 kabul testleri (§12; her biri plandaki bir görevde adıyla durur):**
- D25 ret ömrü: ret → tekrar para uzatma → eksik / `none` / bozuk cevap → yeni kart yok, kese aynı; 33 NPC'ye aynı gün ret yazılınca ilk NPC'nin reddi korunur ve 33. yazım `decline_cap_full` olarak loglanır; önceki günün kayıtları önce düşer.
- D26 ret kapsamı: yalnız bahşiş reddi → mal alınır, bahşiş 0; oda bedelinin açık reddi → oda kartı onayı 0 keser; kapsamı belirsiz ret → o NPC'ye hiçbir ödeme ilerlemez.
- D27 hafıza ömrü (birim testi, senaryo 24'te değil): aynı NPC ile 25 farklı konuşma, en az 13'ü `remember=true` → ilk kişisel bilgi kaynakta ve doğru soruda görünümde; 41. kaynak ilkini düşürür; 33. NPC en uzun süredir yazılmayanı düşürür.
- D28 sızıntı: A'ya özel aile ayrıntısı ve A'ya yapılan ödeme B'nin hiçbir konuşma girdisi kanalında yok; aynı adlı NPC içeren iki kampanya/karakter birbirini görmez; NPC görünümünde kese toplamı yok, "uzattığı N bakır" var.
- D29 teklif ≠ para: parasız `deal goods` doğru teklifi açar; geçersiz mal/kişi önerisi oda kelimesi içerse de başka karta dönüşmez; tek tutarı tek işlem sahiplenir.
- D30 uzun söz: önemli ayrıntı/olumsuzlama 200. karakterden sonra → kaynakta tam; görünüm "kısaltıldı" işaretli; 600'ü aşan söz `cut` ve destek değil.
- D31 destek: örtüşmesiz kendi-sözüm iddiası inkâr korumasında kalır; yalnız genel bir kökü paylaşan yanlış iddiada model girdisine yalnız gerçek satır gider, iddianın uydurma kısmı hiçbir girdide "söylendi" olarak yer almaz; olumsuzlamalı satır; aynı cümlede "ben söylemiştim" ve "sen söz vermiştin" → `npc_words`, inkâr.
- D32 atomiklik: kayıt öncesi hata → eski dünya/hafıza; commit sonrası yanıt kaybı → tekrar aynı sonuç, tek öğrenme; aynı action → bayt aynı, tek satır; yeni yönetici ile yeniden açma → hatırlama orada; Geri Al sonrası hiçbir konuşma girdisinde eski söz yok.
- D33 bayt: uzun ad/yer/etiket, birden çok tur notu ve Türkçe harfler birlikte; bütün isteğe bağlı satırlar atıldıktan sonra da ≤600 bayt; hafıza başlığı ve tırnaklar dahil ≤600; düşen zorunlu satır "(kısaltıldı: …)" ile adlanır.
- D34 panel "hayır": iki onay sırası, arada hata, ret, tekrar; Geri Al D37'ye göre: mal onayından hemen sonra Geri Al → bira geri, Bahşiş kartı `cancelled`; bahşiş onayından sonra Geri Al → yalnız bahşiş geri, kart yeniden `prepared`, bira kalır; ardından ikinci Geri Al ve mal onayını hedefleyen Geri Al → `409 undo_unavailable`, dünya ve kayıt değişmez.
- D37 tek Geri Al adımı: Geri Al gerektiren hiçbir test ya da senaryo art arda iki başarılı Geri Al beklemez; her tur kendi hemen ardından geri alınır (plan Görev 9, 21).

**Sıfır tolerans:** 11 (geri al/yenileme), 12 (yetersiz bakiye) ve yeni 25 `known_broken` olamaz. Araştırmanın saydığı para değişmezleri testleri (`test_economic_action_http`, `test_economic_resolution`, `test_economic_receipt`, `test_economic_undo`, `test_shop_trade*`, `test_shop_counter`) yeşil kalır; kırılan olursa adım geçmez.

**Eski testlerin yeniden yazımı (kalıcı izin, liste Kadir'e):** sessiz hediyeyi sabitleyenler (`test_economic_dialogue.py::test_tip_is_not_swallowed_by_currency_flag`, `test_carius_fifth_play.py:170-239`'daki "üstü kalsın, sipariş yok → hediye kartı" vakası) betiğe `deal` eklenerek aynı sıkılıkta yeniden yazılır; senaryo 01, 02, 03, 04 değişiklikleri de bu listeye girer. Silme, atlama, gevşetme yok.
**Tam paket yeşil kalır:** her görev sonunda ilgili dosyalar; kapıda tam test (`slot.sh … '^test_'`), node testleri, tüm yolculuklar (N geçti, M bilinen kırık, Z=0). `narrative_memory` test_5 (bilinen kararsız) bu dilimin uydurma kontrolüdür: kırmızıysa nedeni bulunmadan kapı geçmez.

## 7. Bitiş kapısı (`YOL_HARITASI_REVIZYON` §4)
1. §6'daki işaretler kalkmış, yeni kırık 0 (çalıştırıcı bayat işareti hata sayar).
2. Tam test paketi 0 kırık; node temiz; sıfır tolerans senaryoları yeşil.
3. Bağımsız bütün dal incelemesi (en güçlü model).
4. Gerçek zincirde kısa kontrol (Kadir "yap"; harcama günlük kayıtta, 3 USD/gün uyarısı). Güncel koşu listesi (§12 D35): rc1 (fiyat hatırlama), rc2 (ödeme sonrası tutarlılık), 24'ün hatırlama adımı, 04b'nin menzilli saldırı adımı (107'nin yönlendirme yarısı) ve `24r` (modelin ilk anlatımda öğrenme alanını kendisi doldurması); "5 üzerinden kaç". Hafıza için beş kanıt ayrı raporlanır: doğru dinleyen, kalıcı kaynak, yeniden açılmış kaynak, son model girdisi, son cevap. Modelin sözünü sınamak (son cevapta doğru ayrıntı) ile yalnız Python inkârının yokluğunu sınamak ayrı satırlardır. Son istem boyu bu koşuda ölçülür (D33).
5. Kadir 30 dakika oynar: **GEVŞETİLDİ → deftere "oynayış bekliyor"**. Ürün kabulü yine yalnız Kadir'in oynayışıyla.
6. Hafızanın dürüst kapsamı (§12 D27): kapı 116'yı yalnız "Dilim 1: NPC başına son 40 seçilmiş söz" olarak geçer; uzun süreli tam hafıza (tam arşiv) bu dilimle kapanmış sayılmaz ve rapor bunu bu sözle yazar.
Ek: `graphify update .`; Kadir'e düz Türkçe kısa rapor; Jarvis'e "Dilim 1 hazır" (19 maddelik test tetiği).

## 8. Riskler ve açık noktalar
- **Küçük model yeni alanları yanlış doldurabilir** (`deal`, `coin_answer`, `coin_answer_for`, `remember_player_line`). Güvenli varsayılanlar: `deal` yok → yapısal onarım; geçersiz `deal` → `unclear`, kart yok (D29); `coin_answer` yok/bozuk → var olan ret korunur, ret yoksa bugünkü davranış (D25); kalem belirsiz `declines` → o NPC'ye ödeme ilerlemez (D26); `remember` yanlış "evet" → yalnız oyuncunun kendi sözü yazılır. Gerçek zincir kontrolü bunu ölçer.
- **Yanlış genel ret oyuncuyu bekletebilir:** model kapsamı belirsiz bir `declines` verirse o NPC'ye o gün ödeme ilerlemez; oyuncu NPC ile konuşarak açık `takes` almalıdır. Bu, paranın yanlış kesilmesinden daha güvenli taraftır.
- **Tek kök örtüşmesi destek sayılır (D31):** "babam" gibi genel bir kökü paylaşan yanlış bir kendi-sözüm iddiasında Python inkârı kalkar; model yalnız gerçek satırı görür. Modelin bunu düzgün ayırıp ayırmadığı gerçek zincirde ve oynayışta görülür; eşik bu dilimde değiştirilmez.
- **Hafıza kaydı büyüyebilir:** en kötü durumda 32 NPC × 40 söz × 600 karakter; kayıt dosyası yaklaşık 1–1,5 MB büyüyebilir (hesap). Kayıt ve yükleme süresi ölçülmedi.
- **Yapısal oda tahmini** 50+ bakırlık bir hediyeyi Oda kartı yapabilir; oyuncu kartta görür ve iptal eder (para onaysız gitmez).
- **Ön okuma kapalı/çöktüğünde** eski kelime listesi yolu sürer: "alabilir miyim" o yolda hâlâ teklif açmaz; tüketim olmaz.
- **İstem boyutu ölçülmedi:** 600 baytlık kart + 600 baytlık hafıza görünümü (eski fiyat notları da kalıyor) 8192 tokenlık pencerede; gerçek istem boyu ölçüm koşusunda kaydedilir (D33). Token sayısı belge okumasından çıkarılamaz.
- **Hazır (Python) satırlar kartı okumaz:** `pocket.EMPTY_HANDED` ("eline geçen bir şey yok") ve `_UNKNOWN_LINES` ("Kimse bana bir şey anlatmadı") Dilim 1'de değişmez; senaryo 03 adım 5 bugün geçiyor.
- Doğrulanmayanlar: inkârı hangi dal üretti; "Öyle bir şey demedim" kaynağı; tezgâh satırı NPC sözü olarak kaydediliyor mu; ikna zarının yolu; madde 3'teki "yarım saat geçiyor"un kaynağı; senaryo 04'te motorun uzun yayı seçip seçmediği (39 ile karışabilir, Dilim 2); ilk koşuda `speak_to` adımının konuşma yoluna gittiği.
- Örtüşme ölçüsü genel hatırlama sorularında ("geçen sefer ne demiştim?") satır bulamayabilir; ~~bu durumda en yeni 3 satır verilir~~ → D31: en yeni 3 satır yalnız bağlamdır, inkâr koruması kalır ve NPC hatırlamadığını söyler (bilinçli karar, oynayış bekliyor).
- `free_v1` konuşma kipi bu tasarımın dışında; açılırsa hafıza ve ret yolu farklıdır.

## 9. KARARLAR (Kadir adına verdiğim; her biri onayına açık)
1. Ruling: Anlam kararı `money_owner`'da, para hareketi `economic_actions`/`shop_trade`'de kalır — tek kişinin hem anlamı hem defteri yazması `game.py` parçalanırken riskli — yanlışsa: iki modül arasında bir ara katman fazla olur, birleştirmek kolay.
2. Ruling: Para anlamını modelin `deal` alanı önerir (goods/room/tip/gift/paid_before/none) — kelime listesi yasak, anlamı okuyabilen tek parça model — yanlışsa: şema ve istem değişir, gerçek zincirde ölçüm gerekir.
3. Ruling: `deal` şemada `kind`'in hemen arkasına konur — küçük modeller sondaki alanları boş bırakıyor (şema notu) — yanlışsa: alan çoğu kez boş gelir, yapısal onarıma düşer.
4. Ruling: `deal` yoksa yalnız iki yapısal anlam (açık teklifin parası, oda) denenir, hediye asla varsayılmaz — sessiz hediye 35/103/110'un ortak kökü — yanlışsa: gerçek hediyeler kart açmaz, oyuncu "hediye ediyorum" demek zorunda kalır.
5. Ruling: Hiçbir anlam bulunmazsa kart açılmaz, NPC doğal olarak sorar (hazır bir "ne için?" satırı yok) — Kadir mekanik cevap istemiyor — yanlışsa: oyuncu parasını veremediğini sanabilir.
6. Ruling: Elden para çıkan satır asla iş değildir; ön okuma varken eski liste `work` diyemez — 110'un yapısal düzeltmesi, kelime eklemeden — yanlışsa: "işi yapıyorum, şu bakırı da al" gibi karma bir satır vardiyayı başlatmaz, oyuncu iki satırda söyler. *(Yerine geçti: D4/karar 57: eski listenin `work` yasağı kaldırıldı; kural `_carry_out_thread_turn`'de `blocks_money_moves`.)*
7. Ruling: Ön okuma kapalıyken eski kelime listeleri silinmez ve genişletilmez — yeni liste yasak, silme Dilim 1 kapsamını aşar — yanlışsa: yedek yolda 35/54 sürer.
8. Ruling: `paid_before` kart açmaz, makbuzları karta koyar — madde 3 ve "öde demedim/ödedim" tartışmasını motor gerçeği çözer — yanlışsa: gerçekten ikinci kez ödemek isteyen oyuncu bir satır daha yazar.
9. Ruling: Bahşiş tutarını Python hesaplar (uzatılan − fiyat), model rakam vermez — sıfır tolerans — yanlışsa: yok denecek kadar küçük; "2 bakır bahşiş" gibi açık rakamlı bahşiş ayrı kart olur.
10. Ruling: "Üstü kalsın" alışverişi yine tezgâh onayından geçer (R7), senaryo 02'ye onay adımı eklenir — onaysız para hareketi yok — yanlışsa: Kadir tek adım istiyorsa, açık teklife para koymak doğrudan ödemeye çevrilir (küçük değişiklik).
11. Ruling: Tezgâh teklifi ve anlatı toplamı açık yazar ("4 + bahşiş 1 = 5") ve onaylanan toplam 5'tir — oyuncu 4 sanıp 5 ödemesin — yanlışsa: `/item shop_buy` toplam alanı kafa karıştırır, arayüz cilası gerekir.
12. Ruling: Açık teklif yokken bahşiş ayrı "Bahşiş" kartıdır, Hediye değil — etiket yanıltmasın (notlar G) — yanlışsa: yalnız etiket.
13. Ruling: NPC reddi modelin `coin_answer` alanıyla gelir; ret bu satırdan hiçbir kartı açtırmaz — 103'ün kökü; model para yaratamaz, yalnız durdurur — yanlışsa: yanlış "reddediyor" etiketi meşru bir alışverişi o tur durdurur, oyuncu tekrar dener.
14. Ruling: Ret 2 tur geçerli `flags.money_declined` olarak kalır; o sürede panel kartı açılır ama onayı kesmez — senaryo 17 yazıldığı gibi kalır, oyuncu engellenmez ama para gitmez — yanlışsa: kart hiç açılmasın denirse 17'nin 2–3. adımları yeniden yazılır. *(Yerine geçti: D3/karar 56, sonra D25/D26/karar 66–67: ret kart açtırmaz, tur sayısıyla bitmez, yalnız açık `takes` ya da gün değişimiyle kalkar.)*
15. Ruling: Başarılı pazarlık zarı %10 (en az 1 bakır) indirim verir, kişi başına günde bir kez — Kadir "zar etkisiz" diye şikâyet etti; küçük, tek kural — yanlışsa: oran ya da "indirim yok, nedenini söyler" seçeneği; senaryo 03 iki adımı tekrar değişir.
16. Ruling: Oda fiyatı 50 bakır kalır, yalnız indirimle değişir — fiyat tablosu ayrı iş — yanlışsa: hanlara göre fiyat Dilim 3 dünya verisiyle gelir.
17. Ruling: Oda anahtarı eşya olmaz; doğruluk kartı "oda tutuldu" der (R8) — Kadir kararı — yanlışsa: "anahtarı alıyorum" hazır satırı hâlâ boş el der (Dilim 3).
18. Ruling: Tüketim ön okumanın yeni `consume` türüyle olur, kimlik çantadan seçilir — "model önerir" ve `hand_over` ile aynı doğrulama — yanlışsa: ön okuma kapalıyken yemek düşmez.
19. Ruling: Eşya türü yeni `kind` alanında, tek veri tablosundan; `resource_type` kullanılmaz — günlük erzak düşümüne karışmasın — yanlışsa: iki ayrı tür alanı kalır, ileride birleştirilir.
20. Ruling: Eski eşyalar yeniden yazılmaz, tür okuma anında tablodan bulunur — kayıt kaybı riski sıfır — yanlışsa: tablo ile kayıt adı uyuşmazsa (eski çeviri) o eşya tüketilmez.
21. Ruling: Yemek/içmenin oyun etkisi ve süresi yok; savaşta tüketim yok — az motor kuralı — yanlışsa: savaşta bira içmek "deneme" anlatısı olur, eşya düşmez.
22. Ruling: Yanlış türde eşya (kılıç) tüketilmez, sıradan deneme anlatısına onarılır — onarım, ret değil — yanlışsa: yok denecek kadar küçük.
23. Ruling: Mühimmat paket etiketinden (tam etiket → adet tablosu) bir kez, eşya kimliği başına tohumlanır; tür silah kataloğundan — oyuncu sözü değil, yazılmış veri; tatar yayı `bolt` ister — yanlışsa: başka paket etiketi eklendiğinde tabloya satır gerekir.
24. Ruling: Tohumlama yaratmada, yüklemede ve menzilli saldırı hazırlığında çalışır — eski kayıtlar ve sahne kurulumu da kapsansın — yanlışsa: aynı eşya listede yoksa iki kez sayılabilir; liste ≤64 bunu önler.
25. Ruling: "& 20 Ok" etiketi değişmez, sayı ayrı gösterilir — yaratma testleri etiketi sabitliyor — yanlışsa: oyuncu 19 ok kalmışken "20 Ok" okur (arayüz işi).
26. Ruling: Atılan oklar geri toplanmaz — Dilim 1 kapsamı — yanlışsa: ok biter, oyuncu satın alamaz (satış listesinde ok yok).
27. Ruling: Doğruluk kartı tek fonksiyon, dört ekleme noktası, `build_world_context` dışında — konuşma yolu onu çağırmıyor, süreklilik bütçesini itmesin — yanlışsa: ileride tek noktaya toplamak gerekir.
28. Ruling: Kart en çok 600 bayt, sabit kısaltma sırası — 8192 tokenlık yerel pencere — yanlışsa: ölçüm istem taştığını gösterirse bütçe küçülür.
29. Ruling: Kartta yalnız oyuncunun görebileceği bilgi — gizli ad/stok/geçmiş sızmasın (`test_phase7_package`) — yanlışsa: NPC'nin gizli adı ekranda çıkar (OYUN_TARIFI "isim ve kimlik").
30. Ruling: Kese kartta panelle aynı biçimde (altın/gümüş/bakır) — madde 12'deki gösterim çelişkisi — yanlışsa: yalnız metin biçimi.
31. Ruling: `price_note`/`room_note` silinmez, kart yanına eklenir — testler sabitliyor, kart hiçbir şey kaldırmıyor — yanlışsa: fiyat iki kez yazılır (birkaç bayt).
32. Ruling: Yeni makbuzlara `label` ve `payee_id` eklenir, eskiler etiketsiz kalır — kart "ne, kime" diyebilsin — yanlışsa: eski kampanyalarda son ödemeler belirsiz görünür.
33. Ruling: Tezgâhın hazır teklif satırı NPC'nin sözü olarak kaydedilir (bugün değilse) — fiyat hatırlaması dayanak bulsun (36) — yanlışsa: Python satırı NPC ağzına yazılmış sayılır; zaten NPC'nin sesiyle söyleniyor.
34. Ruling: Kişisel hafıza ayrı anahtar `npc_told_v1`, `npc["memory"]` değil — o kayıt bilerek "NPC sözü kanıt değildir" kuralıyla kurulmuş ve 16'lık kayan pencere — yanlışsa: iki hafıza yeri olur; birleşmesi Dilim sonrası defter işi.
35. Ruling: Kayda oyuncunun kendi sözü yazılır; model yalnız `remember_player_line` evet/hayır önerir — model içerik uyduramasın — yanlışsa: uzun satırlarda gereksiz kelimeler de kaydedilir (200 karakter sınırı). *(Sınır değişti: D30/karar 71: kaynak 600 karaktere kadar tam, görünüm 200.)*
36. Ruling: Bu alan konuşma şemasında, ön okumada değil — ön okuma kapalıyken de çalışsın, konuşma her NPC turunda var — yanlışsa: konuşma modeli ek alanı ihmal edebilir; o zaman ön okumaya taşınır.
37. Ruling: Senaryo 01 ön okumalı hâle getirilir — oyunda ön okuma açık (`local_play.py:216`); kapalı yol oyunun yolu değil — yanlışsa: işaret kalkar ama yedek yolda "alabilir miyim" kırık kalır.
38. Ruling: Kayıt koruma kuralları yalnız mevcut denetimlerdir (soru, `is_npc_historical_claim`, gizli profil, savaş, orada olmak) — yeni liste yok — yanlışsa: bazı kişisel satırlar ("daha önce kardeşime...") iddia sayılıp kaydedilmez.
39. Ruling: NPC başına 12 satır, 32 NPC, önem sıralaması yok — basit ve öngörülebilir; 20+ tur sorununu çözer — yanlışsa: çok konuşkan oyuncuda eski bilgi yine düşer. *(Yerine geçti: D27/karar 68: NPC başına 40 seçilmiş söz kaynağı, görünüm 3 satır.)*
40. Ruling: Getirme kelime kökü örtüşmesiyle, en çok 3 satır; hatırlama kendi sözü hakkındaysa ve örtüşme yoksa en yeni 3 satır — "en çok 3" Kadir'in kapsamı; genel soruları da kaçırmasın — yanlışsa: model ilgisiz satır söyler ya da ilgili satırı kaçırır. *(Daraltıldı: D31/karar 72: örtüşme yoksa en yeni 3 satır yalnız bağlamdır, destek değildir; inkâr koruması kalır.)*
41. Ruling: Kayıt "söylendi" anlamına gelir, "doğru" değil; istemde böyle etiketlenir — uydurma iddia hâlâ inkâr edilsin, NPC yalan söylenmiş olabileceğini bilsin — yanlışsa: NPC oyuncunun yalanını da hatırlar; bu doğal sayılır.
42. Ruling: NPC'nin kendi sözleri veya üçüncü kişiler hakkındaki iddia bugünkü kapıdan geçer — test_5 uydurması inkâr edilmeli — yanlışsa: oyuncunun "sen bana X dedin" yalanı inkâr edilmeye devam eder (istenen).
43. Ruling: Eski kampanyalar için hafıza geriye dönük doldurulmaz — `npc_statements.player` alanı modelin işaretlemediği her satırı içerir — yanlışsa: Kadir'in mevcut kampanyasında eski kişisel bilgiler hatırlanmaz.
44. Ruling: Yükte bozuk yeni alanlar atılır, kayıt reddedilmez — sıfır tolerans kayıt kaybı içindir — yanlışsa: bozuk satır sessizce gider (loga yazılır).
45. Ruling: Geri al ve tekrar için ayrı mantık yok; her şey `world_state` anlık görüntüsünde — bugünkü güvenli yol — yanlışsa: oturumda kalan alan (`_coin_decision`) sızarsa bir sonraki tur yanlış okur; her tur sıfırlanır.
46. Ruling: Düzeneğe `npc_sozleri`, `konusmaya_giden`, `inkar`, `speech` betiği, `item_name` çevirisi ve `reload_continue` eklenir; mevcut `reload` değişmez — 116 bugün gözlenemiyor; 11'in anlamı bozulmasın — yanlışsa: düzenek büyür; şema testi güncellenir.
47. Ruling: Senaryo 02, 03, 04 ve 01 değişiklikleri "eski davranışı sabitleyen testleri aynı sıkılıkta yeniden yazma" izniyle yapılır ve listelenir — son durum beklentileri aynı ya da daha sıkı — yanlışsa: Kadir istemezse ilgili işaret kalkmaz.
48. Ruling: Senaryo 18'deki 115 işareti aynı adımla birlikte kalkar; senaryo 19'un 115 işaretleri Dilim 2'de — işaret adıma bağlı, adım düzelince bayat sayılır — yanlışsa: 115 sayımı Dilim 2 raporunda bir eksik görünür.
49. Ruling: 107 (T7) senaryo 04'e kaynak olarak eklenir, ayrı senaryo açılmaz — aynı aile (yemek, içki, ok) — yanlışsa: T7'nin "ok atışı işlenmedi" kısmı ayrı izlenmez.
50. Ruling: 36'nın sahte model yarısı yeni senaryo 26 ile, gerçek yarısı kapıda rc1 ile kapanır — sahte model NPC'nin ne dediğini kanıtlayamaz — yanlışsa: gerçek koşu yapılmazsa 36 yarım kalır.
51. Ruling: Dilim 1 kodu Dilim 0 birleşmesinden sonra, düzeneğin bulunduğu dal üstünde başlar — senaryolar `c-merge`'de yok — yanlışsa: Dilim 0 gecikirse Dilim 1 bekler.
52. Ruling: Para satırı konuşmadan fazla oyun süresi harcatmaz; madde 3'teki "yarım saat"in kaynağı planda bulunur — 110'un saat kısmı — yanlışsa: kaynak bulunamazsa ayrı bulgu olarak raporlanır.
53. Ruling: Konuşma kipi `free_v1` kapsam dışı — varsayılan `legacy` — yanlışsa: Kadir o kipte oynarsa hafıza yine kaybolur.

## 10. Kapsam dışı
Görev eşyası çoğalması ve doğru alıcı (115, senaryo 19), konuşma kipi (4, 15, 41), silah kuşanma ve Ready/yaklaşma (39, 40), savaşta satın alma kuralının arayüz kısmı (Dilim 0) ve motor kısmı (114, Dilim 2), hazır Python satırlarının kartı okuması (`EMPTY_HANDED`, `_UNKNOWN_LINES`), çıkış verisi (21/105), anlatı kalitesi (43–46), başlangıç kesesi gösterimi (34, Dilim 0), XP/seviye/büyü (111, 112), açlık/sarhoşluk kuralları, ok geri toplama ve ok satışı, hanlara göre fiyat, `free_v1` konuşma kipi, `narrative_memory` ve defterin (DEFTER) yeniden tasarımı, `memory_archive.py`'nin bağlanması ve tam hafıza arşivi (Dilim 1 yalnız "son 40 seçilmiş söz"), hafıza satırına kaynak action/revizyon bağı ve "düzeltme ↔ eski söz" bağı (J-013 bulgu 6; not düşüldü), arayüz değişiklikleri (tek istisna: §11 D1'deki tezgâh paneli satırı, yalnız Kadir "evet" derse).

## 11. Eleştiri sonrası düzeltmeler (2026-11-04)

İki bağımsız eleştiri (kod ve test/kapsam) "önce düzelt" dedi. Engelleyici ve önemli bulguların hepsi aşağıda düzeltildi. Küçük bulguların da hepsi ele alındı. Kod gerçekleri `AI-DND-c-merge` (3c733c57) üzerinden yeniden okundu. Bu sürüm, `task/step2-measure-20261104` dalının atasıdır; satır numaraları aynıdır. Her madde şu sırayla yazıldı: ne yanlıştı, yeni kural, eski metnin hangi yeri değişti, hangi test sınar. K1 kod eleştirisi, K2 test/kapsam eleştirisidir.

**D1. Bahşişli onay (K1 engelleyici 1, K2 önemli 4).** Yanlış olan: `shop_trade.commit`, onaylanan toplam malın fiyatına eşit değilse `price_changed` diyor. Panel de yalnız birim fiyat × adet gönderiyor. Yani "5 bakırla onayla" bugün geçmezdi. commit bahşişi kendisi ekleseydi de oyuncu "4" görüp 5 öderdi.
Yeni kural (motor tarafı; panelden bağımsız güvenlidir):
- Bahşiş yalnız açık tezgâh teklifinde (`flags.counter_offer_v1`) durur. Aynı kişi, aynı mal ve aynı `seq` olmalı. Adet 1 olmalı. `tip_cp` 1 veya daha büyük bir tam sayı olmalı. Uzatılan para mal fiyatı + bahşiş kadar olmalı ve kesede bulunmalı.
- Onaylanan toplam = mal + bahşiş ise satış bahşişle yapılır: kese −5, satıcı +5, Bira 1. Tek makbuz yazılır, para üstü cümlesi çıkmaz.
- Onaylanan toplam = yalnız mal ise (eski panel 4 gönderir) satış bahşişsiz yapılır: kese −4. Cümleye "Bahşiş geçmedi; kesende kaldı." eklenir. Bu satışta uzatılan para hesaba katılmaz, para üstü cümlesi de çıkmaz.
- Onaylanan toplam mal + kayıtlı bahşişe eşit ama bahşiş artık geçerli değilse (kese azaldı) `tip_unavailable` döner ve hiçbir şey değişmez.
- Başka her toplamda `price_changed` aynen kalır. `test_shop_quote_http` ve `test_shop_trade_http` içindeki "bira 1 0 5" reddi (bahşişsiz teklifte) yeşil kalır.
- **Motor hiçbir koşulda onaylanan toplamdan fazlasını kesmez.** Bunu bir birim testi sınar.
- Komutun biçimi değişmez: `/item shop_buy <npc> <mal> <adet> <seq> <toplam>`. Senaryo 02 ve 25'teki komut `barman bira 1 0 5`'tir.
Arayüz: panelin bahşişi gösterip 5 göndermesi küçük bir arayüz işidir. Bu iş ancak Kadir "evet" derse yapılır (açık soru 1). "Hayır" derse panel 4 gönderir ve bira bahşişsiz satılır. Bahşiş o zaman ayrı bir Bahşiş kartıyla verilir (aşağıdaki karar 12 yolu). §3b'deki "onaylanan toplam 5'tir" sözü bu kurala bağlanır. Karar 11'in yerine karar 54 geçer.

**D2. "Konuş" kipinde para (K1 engelleyici 2).** Yanlış olan: Konuş kipinde (hedef seçili, `say`) ön okuma hiç çalışmıyor (`game.py:18281-18284`). Bu kipte para anlamı da iş kapısı kuralı da devreye girmez. Oysa eski kelime listesi `_thread_gate` bu kipte de çalışır.
Yeni kural: Konuş kipinde ön okuma yalnız bir koşulda çalışır: satırın bir cümleciğinde para birimi geçmeli. Bu, `coin_in`'in bugün kullandığı cümlecik sınamasıyla aynı sınamadır, yeni kelime yoktur. Kişi her zaman seçili hedeftir. Okumadan yalnız para (`coin_cp` ve `deal`) kullanılır, yol yine "hedefe konuş" kalır. Para geçmeyen Konuş satırı için model çağrısı eklenmez, gecikme değişmez. Tüketim Konuş kipinde okunmaz: o kipte yazılan satır söz sayılır.
Değişen yerler: §1 varsayım 1 ("oynanan yol ön okumalı yoldur") bu kuralla tamamlanır. §3a'ya bu kural eklenir. §9'a karar 55 eklenir.
Test: senaryo 18d (18'in Konuş kipindeki ikizi). Ayrıca bir birim testi: para geçmeyen Konuş satırında ön okuma çağrısı yapılmaz.

**D3. Ret kalıcıdır ve kart açtırmaz (K1 engelleyici 3, K2 önemli 7).** Yanlış olan: "2 tur geçerli" kaydı budandığında, önceden hazırlanmış bir kart yeniden geçerli hâle gelip NPC'nin geri çevirdiği parayı kesebilirdi.
Yeni kural:
- `coin_answer = declines` geldiğinde ret kaydı yazılır. Kaydı `economic_actions` tutar, çünkü kabulün sahibi odur.
- Kaydın yazıldığı anda o NPC'ye açık bütün Hediye ve Bahşiş kartları `cancelled` yapılır.
- Ret sürdükçe o NPC'ye Hediye veya Bahşiş kartı **hiç açılmaz**. `derive_acceptance` bunun için var olan "refused, kart açılmaz" yolunu kullanır (`reason_code="npc_declined"`). Mesaj tam şudur: "<ad> az önce parayı geri çevirdi."
- ~~Ret iki durumda biter: (a) sonraki bir turda aynı NPC'ye yine para uzatılır ve NPC bu kez reddetmez; (b) oyun günü değişir.~~ **Yerine geçti: D25.** Ret yalnız aynı NPC'nin aynı kalem için verdiği açık `takes` ile ya da oyun günü değişince biter; "reddetmemek" (eksik, `none`, bozuk cevap) reddi kaldırmaz. Tur sayısıyla süre tanımlanmaz.
- ~~Kayıt şudur: `flags.money_declined = {npc_id: {"amount_cp": int>0, "day": int}}`. En çok 8 kayıt tutulur.~~ **Yerine geçti: D25/D26.** Kayıt kaleme bağlıdır (§5 `money_declined`); sınır 32 NPC'dir, önce önceki günler düşer.
§3b'nin 2–3. maddeleri ve karar 14'ün yerine karar 56 geçer. Senaryo 17'nin başlığı bu seçeneğe izin veriyor, adımları yeniden yazılır: 1 ret; 2 panelden hazırla → kart yok, kese 100, "parayı geri çevirdi"; 3 aynı kişiye yine para uzat, NPC kabul eder; 4 hazırla → Bahşiş kartı 5; 5 onay → kese 95, Osman 5. *(Bu adım listesi tarihçedir; güncel altı adım D25/D26'ya göre plan Görev 10'dadır: "kabul eder" yalnız açık `takes` + kalemdir.)*
Birim testi: ret → kart yok; önceden açık kart ret anında iptal olur; ret → 3 tur bekle → yine kart açılmaz; gün değişince açılır.

**D4. Para satırı ne iş ne ücret başlatır (K1 önemli 4, K2 engelleyici 1).** İki düzeltme var:
- (a) §3a'daki ikinci kural **kaldırıldı**. O kural "ön okuma varken eski liste `work` diyemez" diyordu ve `test_said_is_real.py::test_until_the_evening_needs_no_front_reading` testini kırardı. Para uzatılmayan satırda eski liste aynen çalışır.
- (b) Para kuralı genişler. Bu turda oyuncunun elinden para çıkıyorsa (karardaki tutar 0'dan büyükse) iş kapısının para hareket ettiren iki kararı, `work` (vardiya ve yevmiye) ve `pay` (ücret ödeme), uygulanmaz. Satır kişiye söylenmiş sayılır. Kural tek yerdedir: `_carry_out_thread_turn` girişi. Bu yüzden `_thread_gate`, `_front_work` ve onlara düşen `_front_offer_gate`/`_front_hand_over` yolları aynı kuralı okur. Kelime eklenmez.
Karar 6'nın yerine karar 57 geçer. Testler: senaryo 18, 18b ve 18c (18c'de "Tamam, işi yapıyorum" ile vardiya yine çalışır). Bir birim testi daha: ücreti vadesi gelmiş bir işte "5 bakır atıyorum" → kese değişmez, `pay` uygulanmaz.

**D5. Paranın tek tüketicisi (K1 önemli 5).** `bold_acts.take_room`, `_room_asked` ve `shop_offer` iki durumda kelime okumaz: karar türü oda/mal ise ya da model geçerli bir `deal` vermişse. Bu durumda `money_owner` kararını uygularlar. Uzatılan parayı yalnız `money_owner.claim(session, amaç)` verir. `bold_acts.held_out_coin` da ona bağlanır. Bir turdaki para yalnız bir karta bağlanır. Karar yoksa (para yok, `deal` yok) eski kelime yolu aynen kalır: "bir bira alayım" bugünkü gibi çalışır.
Test: aynı satırda `deal gift` ve oda kelimesi → tek kart, o da Hediye.

**D6. Mühimmat: tohum eşyanın üstünde, saldırı anında (K1 önemli 6, K2 engelleyici 2 ve 3).** Yanlış olan iki şeydi:
- `weapon_catalog.lookup("Ağır Tatar Yayı & 20 Ok")` None döner, yani yaratmada çökme olurdu.
- Yaratma sonunda envanter düz metindir, `item_id` yoktur. Kimlikle tekilleştirme çalışmaz ve yaratmayı sabitleyen testler envanterin metin listesi olarak eşit kalmasını ister.
Yeni kural:
- Tür ve adet veri olarak tutulur: `content/items/item_use.json` → `ammunition: {tam etiket: {"type": "arrow"|"bolt", "count": 20}}`. `lookup` kullanılmaz. Tabloda olmayan etiket sessizce atlanır.
- Tohumlama yaratmada ve yüklemede **yapılmaz**. Yalnız menzilli saldırı çözülürken, azaltmadan hemen önce yapılır (`weapon_attack._resolve`).
- Bu işlem önce `equipment_economy.materialize(world)` çağırır, sonra tabloda olup üstünde `ammo_seeded_v1` işareti olmayan her eşyanın sayısını ekler ve eşyayı işaretler. İşaret eşyanın üstünde durduğu için aynı eşya iki kez sayılamaz. Kimlik listesi de tutulmaz.
- Saldırıdan önceki kontrol (`prepare`) hiçbir şey yazmaz. Yalnız "sayaç + işaretsiz paketler" toplamına bakar.
Karar 23–24'ün yerine karar 58 geçer. §5'teki `ammunition_seeded_items` alanı kaldırıldı.
Test: saldır → 19; kaydet-yükle → saldır → 18 (38 değil); eski kayıt (yalnız metin envanter) → saldır → 19.

**D7. Bozuk yeni alan kaydı reddettirmez: onarımın yeri (K1 önemli 7).** Onarım `game.load_game` içinde, dünya yüklendikten hemen sonra yapılır. Bu yol hem dosya hem kampanya yüklemesi için ortaktır (`restore_campaign_session` → `load_game`). Her alanın onarımı kendi sahibinde, ayrı ve loglu durur: `npc_told.repair`, `economic_actions.repair_declines`, `bold_acts.repair_counter_tip`, `economic_actions.repair_ledger_labels`. `_validate_save_payload` ve `campaign_validation` bu isteğe bağlı alanlar için hiçbir zaman hata fırlatmaz. §5'teki "kampanya doğrulamasında şekil denetimi" sözünün yerine bu kural geçer, karar 44 bu yerle kesinleşir.
Test: bozuk bir `npc_told_v1` satırı içeren kayıt yüklenir, satır atılır, kayıt yeniden yazılabilir.

**D8. Bahşiş satırı gerçekten ödenir (K1 önemli 8).** `counter_purchase_offer` bahşiş satırını (`tip:1`, alıcı satıcı) eklerken bir de `LineDecision(line_id="tip:1", status="accepted")` yazar. Böylece satır `no_decision` ile düşmez. `validate_economic_resolution` alıcıyı (satıcıyı) doğrular. Kese yetmezse D1'deki kural geçerlidir.
Birim testi: kese −5, satıcı +5, `refusals == []`.

**D9. Sessiz hediyeyi sabitleyen eski testlerin tam listesi (K1 önemli 9).** `_coin_paid`, `coin_cp`, `"gift"`, `Hediye` ve `COIN_LEFT_BEHIND` geçen testler tarandı. Yeniden yazılacaklar aşağıda. Hepsinde son durum beklentisi aynı kalır. Değişen tek şey, betiğin `deal` vermesi ya da testin kararı açıkça kurmasıdır.
- `test_economic_dialogue.py`: `test_refused_gift_does_not_debit`, `test_tip_is_not_swallowed_by_currency_flag`, `test_handed_coin_without_order_opens_gift_card_no_debit` (karar `gift` olarak kurulur). `test_unconfirmed_coin_prompt_never_says_taken` (not artık karardan okunur; beklenti aynı).
- `test_coin_writers.py::test_a_coin_handed_with_no_order_is_a_gift` (karar `gift`).
- `test_carius_fifth_play.py`: `test_a_gold_thrown_with_keep_the_change_pays_that_gold_and_buys_no_beer` ve `test_a_tip_after_the_beer_was_bought_still_pays` (`deal tip` → Bahşiş kartı; tutar ve tek ödeme aynı); `test_a_coin_handed_before_a_question_still_pays` (`deal gift`).
- `test_world_keeps_its_word.py`: `test_a_coin_given_leaves_the_purse_and_the_person_has_it`, `test_the_figure_in_the_line_beats_the_figure_in_the_reading`, `test_coin_with_no_figure_is_a_small_hand_not_the_readings_number` (`deal gift`).
Değişmeden geçmesi gerekenler (taranıp kontrol edildi): `test_shop_counter.py:146` (hediye olmadığını sınıyor), `test_economic_room.py::test_coin_taker_from_before_walk_opens_no_gift_card` (`COIN_LEFT_BEHIND` dalı korunur), `test_economic_bribe.py::test_coin_to_innkeeper_under_arrest_is_not_bribe` (`game._hand_over_coin` adı ve `_coin_paid` alanı korunur). Senaryo 02, 03, 16, 17 ve 18 değişiklikleri de bu listeye girer.
Liste, uygulama bitince bütünüyle ve bir kerede Kadir'e sunulur. Her satırda dosya, eski ve yeni ad, eski ve yeni beklenti ve gerekçe yazılır. Kalıcı izin bunu kapsar.

**D10. İddia kapısı (K1 önemli 10, K2 önemli 9 ve 10).** Yanlış olan üç şeydi:
- Oyuncunun kendi sözü "sen bana X dedin" uydurmasını destekleyebilirdi.
- `absent` sonucu iki anlam taşıyor.
- Destekli bir hatırlamayı 21720–21746'daki yankı süzgeci yine de hazır bir satırla değiştirebilirdi.
Yeni kural:
- Yeni saf yardımcı `npc_statements.claim_about(claim) -> "own_words" | "npc_words" | "memory"`. [Yerine geçti: D31 — karışık cümle NPC sözü sayılır, destek yalnız gerçek örtüşmeyle; aşağıdaki sıra eski metindir.] Bugünkü kalıpları aynı sırayla kullanır: önce birinci şahıs "söylemiştim/dedim…" kalıbı (`own_words`), sonra söz verme kalıpları ve `_SAID_CLAIM` (`npc_words`), geriye kalan her şey (`memory`). Yeni kelime eklenmez.
- `npc_told.supports` yalnız `own_words` ve `memory` için okunur. `npc_words` (NPC'nin kendi sözü ya da sözü) için kayıt **hiçbir zaman** destek sayılmaz. Bunun nedeni karar 41–42 ve test_5'tir.
- [Yerine geçti: D31 — son 3 satır yalnız bağlamdır, inkâr korumasını kaldırmaz.] Örtüşme yoksa "en yeni 3 satır" yalnız `own_words` için verilir. `memory` için bugünkü inkâr kalır.
- Destek bulunursa `experimental_unverified_claim` kurulmaz. Yankı süzgecinin ikinci dalı (`_unverified_past_event_assertion`) de atlanır.
- Kayıtlı sözü olmayan bir NPC'de (`absent`) de aynı yardımcı karar verir.
§3e'deki "İddia kapısı" bu kurala bağlanır.
Senaryo 24'e eklenenler: oyuncunun kendi sözüyle örtüşen uydurma "sen bana … bahsetmiştin" (inkâr), kayıtlı sözü olmayan ikinci bir NPC'ye uydurma (inkâr), soru işaretsiz bir hatırlama cümlesi (inkâr yok).
Gözlem `inkar` iki hazır satır ailesini de sayar: `_CLAIM_DENIAL_LINES` ve `interaction_adventure._UNKNOWN_LINES`.

**D11. Mal listesi ve tüketim türü ön okumada (K1 önemli 11).** `front_proposal.listing()` yeni bir `goods` listesi döndürür: `[{id: anahtar, name: etiket}]`. Liste konuşulan kişi satıcıysa onun, değilse oradaki tek satıcının mallarından kurulur (`shop_trade.goods`). Şemadaki alanlar düzdür ve `kind`'in hemen arkasına konur: `deal` (enum `goods|room|tip|gift|paid_before|none`), `deal_goods` (mal anahtarları + `none`), `keep_change` (bool). `validate` `deal_goods`'u bu listeyle denetler. `consume` hem `KINDS`'a hem `_PLANNER_STAYS_OUT`'a eklenir. Alanlar eksik gelirse "none/false" sayılır ve cevap reddedilmez (K2 küçük 15). Konuşma şemasındaki `coin_answer` ve `remember_player_line` alanları da şemada görünür ama zorunlu değildir; eksikse `none`/`false` sayılır.

**D12. 01 ve 04 aynen kalır, ön okumalı ikizleri eklenir (K1 önemli 12, K2 küçük 17).** 01 ve 04 ön okumasız (yedek) yolu sınamaya devam eder. 01 adım 3 [35] ve 04 adım 1–2 [54] işaretleri yedek yol için durur. Yeni `01b_beer_chat_front` ve `04b_consume_front` aynı adımları ön okumayla koşar ve işaret taşımaz. 04 adım 3 [56] işareti 04'te kalkar, çünkü mühimmat yoldan bağımsızdır. Sayımda "ön okuma açık: düzeldi, yedek yol: kırık" ayrımı görünür. Karar 37'nin yerine karar 59 geçer.

**D13. Pazarlık indiriminin ömrü (K1 küçük 13, K2 önemli 5).**
- İndirimi `shop_trade` yazar: `price_cut_cp_v1[anahtar]` alanına, oda için anahtar `"room"`dır. Verildiği gün de ayrı bir alanda tutulur: `price_cut_day_v1`.
- İndirim yalnız o oyun günü geçerlidir. Yeni indirim eskisinin yerine geçer, üst üste binmez. Kişi başına günde bir kez verilir.
- Oda fiyatı `bold_acts.room_price(world, npc)` ile bulunur. Ekonomik kartın oda satırı da fiyatı buradan okur.
- İndirim gelince oda kartı yeni fiyatla yeniden hazırlanır. Var olan kural (C12: yeni kart oyuncunun öteki açık kartlarını kapatır) eski kartı iptal eder. Böylece eski fiyattan ödeme olamaz. Dikkat: `context_digest` kartın kendi satırlarını okur, fiyat değişikliğini kendiliğinden yakalamaz. Güvenliği iptal sağlar ve bunu bir test sınar.
- Zarın atıldığı yer bulundu: `deterministic_check_for_action` "ikna etmeye çalışıyorum / pazarlık yap…" satırını İkna zarı yapar (`game.py:1228-1240`). Zar `game.py:15507-15540` bloğunda atılır, hemen ardından `apply_check_outcome_to_world_state` çağrılır. İndirim bu noktaya bağlanır.
- Senaryo 03'te bu bloğa gerçekten ulaşılıp ulaşılmadığı **doğrulanmadı**. Plan, işe bunu sınayan bir testle başlar. Ulaşılmıyorsa 37 bu dilimin kapısından ayrılır ve raporlanır.
- Anlatıdaki söz Python'dan gelir ve tam şudur: "İkna başarılı: <ad> indirim yapıyor, oda artık <fiyat> bakır." Başarısız zarda tam söz şudur: "İkna tutmadı: fiyat aynı, oda <fiyat> bakır."

**D14. `declines` neyi durdurur (K1 küçük 14).** Ret, cevaptan sonra açılan Hediye ve Bahşiş kartlarını durdurur, tezgâh teklifindeki `tip_cp`'yi de siler. Cevaptan önce açılmış oda kartına ve tezgâhtaki mal teklifine dokunmaz: oyuncu onları kartta görür ve iptal edebilir. §3b madde 1'in yerine bu geçer.
Test: ret alan satırda açık oda kartı kalır, bahşiş silinir.

**D15. Rüşvet önce gelir (K1 küçük 15).** `money_owner.decide`'ın ilk adımı bugünkü sırayla `world_reactions.arrester` denetimidir. Muhafıza ya da adı geçmeyen birine uzatılan para hangi `deal` gelirse gelsin rüşvet yoluna gider. A4 rüşvet testleri değişmeden geçer.

**D16. Doğruluk kartı keşif dalına girmez (K1 küçük 16).** Kartın girdiği yerler üçe iner: konuşma notu, ana anlatıcı istemi ve `interaction` kısa yolu. Karar 27'nin yerine karar 60 geçer.

**D17. Makbuz etiketi ekonomide üretilir (K1 küçük 17, K2 önemli 11).**
- `label` ve `payee_id` değerlerini `economic_actions` kendi `_line_label` mantığıyla yazar. `truth_card.receipt_label` kaldırıldı.
- Kart "son ödemeler" bilgisini `economic_actions.recent_payments(world, limit=3)` okuma yardımcısından alır. Bu yardımcı yalnız `net_debit_cp > 0` olan işlemleri verir.
- `money_owner` dışarıdan açık değerler alır: dünya, kişi, tutar ve `deal`. `game.py`'yi içeri almaz. Oturumu `game.py`'deki ince sarmalayıcılar bağlar. `_hand_over_coin` ve `_tell_the_coin` adları korunur.
- Ret kaydını `economic_actions` tutar.
- `money_owner` hiçbir fiyat durumu yazmaz. İndirimi `shop_trade` yazar.
§4 tablosu bu kurala göre okunur.

**D18. Eşyayı tek yer düşürür; kart başlığı (K1 küçük 18).**
- Tüketim eşyayı `equipment_economy.remove_item(world, item_id)` ile düşürür. Bu, tek bir yeni kaldırma yardımcısıdır. Ardından `validate_world` çalışır. `item_use` envanteri doğrudan yazmaz.
- [Yerine geçti: D28 — NPC görünümünün başlığı "SENİNLE OYUNCU ARASINDAKİ İŞLER".] Konuşma yolundaki kartın başlığı tam şudur: "OYUNCUNUN DURUMU (motor; sen bunu ancak görebildiğin kadar bilirsin):". Anlatıcı yolundaki başlık tam şudur: "MOTOR GERÇEĞİ (salt okunur):".

**D19. Kartın sabit sözleri (K2 önemli 6).** Kart satırları sabit sözlerle başlar ve bu sözleri bir birim testi sabitler. Kalıplar şunlardır:
- `oda tutuldu: <yer>, <ne zamana kadar>` / `oda tutulmadı`
- `ödendi: <etiket>, <N> bakır, <kime>, <K> tur önce` / `kayıtta ödeme yok`
- `açık teklif: … ; para henüz el değiştirmedi` / `açık teklif yok`
- `fiyatlar (motorun; başka fiyat söyleme): bira 4 bakır, …, oda 50 bakır`
- `çanta: …`
- `kese: …`
- `bu tur: …`
- `çıkışlar: …` / `kayıtlı çıkış yok`
§3d'deki "sorulmayan mallar önce kısalır" kuralının yerine şu geçer: kısaltmada açık teklifin malı ve oda kalır, diğer mallar düşer. "Sorulan" bilgisi kelimeyle bulunmaz.
Senaryo 03 başlığındaki "yer tutucu" notu güncellenir.

**D20. Düzenek (K2 önemli 8, küçük 14 ve 16).**
- (a) Yeni adıma bağlı gözlemler `_NOT_STATE` kümesine girer ve her eylemin başında sıfırlanır: `konusmaya_giden` ve `inkar`. Sıfırlama `_undo`, `_reload` ve `_Reader` içinde yapılır.
- (b) `reload_continue` **düşürüldü**. Var olan `reload` adımı canlı oturumla kayıt arasında her durum anahtarını karşılaştırır. Bunlara yeni `anlatilan` anahtarı da girer. Ardından canlı oturum sürer.
- (c) `SCRIPT_KEYS` kümesine `speech` eklenir. `_STEP_KEYS` kümesine `konus` (hedef kişi; gövdeye `interaction_mode: "say"` ve `target_id` yazar) eklenir.
- (d) `npc_sozleri` anahtarının adı `anlatilan` olur. Yalnız `world_state["npc_told_v1"][npc_id]` metinlerini okur, karşılaştırma alt dizi iledir.
- (e) Senaryo 25'teki "aynı onayın tekrarı" şöyle düzeltildi: "aynı komutla yeni bir onay denemesi (bayat seq) hiçbir şey kesmez". Aynı `action_id` ile tekrar, HTTP birim testinde sınanır.
- (f) `apply_setup` envanteri yazdıktan sonra `equipment_economy.materialize(world)` çağırır. Bu yalnız test tarafıdır. Gerekçe: tüketilebilir eşyalar oyunda tezgâhtan zaten kimlikli kayıt olarak gelir. Bu yüzden ön okuma listesine üründe materialize eklenmez.
- (g) Ön okuma betiğinde `item_name` alanı canlı çantadaki kimliğe çevrilir. Bu da yalnız test tarafıdır.
`tezgah` gözlemine `tip_cp` ve `total_cp` eklenir. `test_journey_schema.py`'deki sabit kümeler güncellenir. Karar 46'nın yerine karar 61 geçer.

**D21. 107'nin yönlendirme yarısı (K2 önemli 12).** 04b'ye betiksiz, `real_chain: true` bir adım eklenir: "Haydut'a uzun yayımla ok atıyorum". Bu adım kapıdaki gerçek zincir koşusuna girer. Sahte modelde 107'nin yalnız sayaç yarısı kapanır. Rapor bunu açıkça yazar. Karar 49'un yerine karar 62 geçer.

**D22. Dilim içi ara kapılar (K2 önemli 13).** Uygulama sıralı dört ara kapıdan geçer. Her kapıda ilgili yolculuklar ve para değişmezi testleri yeşil olmalıdır. Kapılar şunlardır:
- (A) para sahibi ve kart: 35, 3, 110, 103, 38 ve 36'nın motor yarısı
- (B) tüketim ve mühimmat: 54, 56 ve 107'nin sayaç yarısı
- (C) hafıza: 116
- (D) pazarlık: 37, yalnız zarın yolu doğrulanırsa
Bir kapı kırıksa sonraki gruba geçilmez.

**D23. 2 ve 12 yan etkidir (K2 küçük 18).** Senaryo 26 yalnız 36'yı sınar. Kart madde 2'ye (ödeme sonrası tutarlılık) ve madde 12'ye (kese gösterimi) de dokunur, ama bu iki madde Dilim 1 kontrol listesine **sayılmaz**. Raporda "yan etki olarak dokunulan" diye ayrı yazılır.

**D24. Ek: eşyaya `kind` alanı yazılmaz (kendi bulgum).** Makbuz testleri eşya hareketlerini kanonik JSON ile karşılaştırıyor (`economic_actions.py:651-674`, `test_economic_receipt`). Satışta eşyaya yeni bir alan yazmak bu testleri boşuna kırardı. Tür yalnız tablodan, eşyanın tam adına bakılarak bulunur (`item_use.kind_of`). Karar 19–20'nin yerine karar 63 geçer.

**Yeni kararlar (Kadir'in onayına açık; eski numaralar silinmedi):**
54. Ruling: Bahşiş tezgâh teklifinde durur. Onaylanan toplam mal + bahşişse bahşişle, yalnız malsa bahşişsiz satılır; motor gösterilenden fazlasını asla kesmez (karar 11'in yerine) — sıfır tolerans, panel değişmese de güvenli — yanlışsa: panel "evet" gelmezse bahşiş yalnız ayrı kartla verilir.
55. Ruling: Konuş kipinde ön okuma yalnız para geçen satırda ve hedef sabit olarak çalışır — 110 ve 35 oyuncunun en çok konuştuğu kipte de kapansın, gecikme yalnız para satırına eklensin — yanlışsa: Konuş kipindeki para satırları bir model çağrısı kadar yavaşlar.
56. Ruling: Ret kart açtırmaz, açık Hediye/Bahşiş kartlarını iptal eder; sonraki para uzatmada NPC kabul edene ya da gün değişene kadar sürer (karar 14'ün yerine) — bayat kartın sonradan para kesmesini imkânsız kılar — yanlışsa: NPC fikrini değiştirdiğinde oyuncu parayı yeniden uzatmalı. *(Yerine geçti: D25/D26/karar 66–67: "kabul eder" yalnız aynı kalem için açık `takes` demektir; eksik/`none`/bozuk cevap reddi korur.)*
57. Ruling: Elden para çıkan turda iş kapısının `work` ve `pay` kararları uygulanmaz; ön okuma varken eski listenin `work` yasağı kaldırıldı (karar 6'nın yerine) — 110'un yapısal düzeltmesi, var olan testi kırmadan — yanlışsa: "işi yapıyorum, şu bakırı da al" vardiyayı başlatmaz, iki satır gerekir.
58. Ruling: Ok sayacı tablodaki paket etiketinden, saldırı anında, eşya üstündeki işaretle bir kez tohumlanır; yaratmada ve yüklemede tohumlama yok (karar 23–24'ün yerine) — yaratma testleri ve çift sayım riski — yanlışsa: oyuncu ilk atıştan önce sayacı kartta "işaretsiz paketten" görür, sayaç kayıtta ilk atışta oluşur.
59. Ruling: 01 ve 04 ön okumasız yolu sınamaya devam eder; ön okumalı ikizleri 01b ve 04b eklenir (karar 37'nin yerine) — bilinen kırık gizlenmesin — yanlışsa: sayımda iki senaryo fazla görünür.
60. Ruling: Doğruluk kartı üç noktaya girer: konuşma, ana anlatıcı, `interaction` kısa yolu (karar 27'nin yerine) — keşif dalı kartı kullanamaz ve süzgece takılır — yanlışsa: keşif anlatısında fiyat ve kese yok (zaten yoktu).
61. Ruling: Düzeneğe `anlatilan`, `konusmaya_giden`, `inkar`, `speech` betiği, `konus` adım alanı, `item_name` çevirisi, kurulumda materialize ve `tezgah.tip_cp/total_cp` eklenir; `reload_continue` yok (karar 46'nın yerine) — `reload` zaten kaydı karşılaştırıyor — yanlışsa: düzenek biraz büyür.
62. Ruling: 107'nin sahte model yarısı 04 adım 3 ile, yönlendirme yarısı 04b'nin gerçek zincir adımıyla kapanır (karar 49'un yerine) — sahte model yönlendirmeyi kanıtlayamaz — yanlışsa: gerçek koşu yapılmazsa 107 yarım kalır.
63. Ruling: Eşya türü yalnız veri tablosundan ve ada göre bulunur, eşyaya alan yazılmaz (karar 19–20'nin yerine) — makbuz testleri eşyayı kanonik karşılaştırıyor — yanlışsa: başka adla satılan bir içki tüketilmez, tabloya satır gerekir.
64. Ruling: İddia kapısında kayıt yalnız "kendi sözüm" ve "hatırlıyor musun" türünde okunur, NPC'nin sözü hakkındaki iddiada asla (karar 42'yi kesinleştirir) — uydurma "sen dedin" inkâr edilmeye devam etsin — yanlışsa: "sen bana söz vermiştin" gibi gerçek bir anı kayıttan değil NPC sözleri defterinden gelmeli (bugünkü gibi).
65. Ruling: Pazarlık indirimi yalnız o oyun günü geçerli, yerine geçer, üst üste binmez (karar 15'i tamamlar) — süresiz indirim olmasın — yanlışsa: ertesi gün oyuncu yeniden pazarlık eder.

**Açık soru (yalnız Kadir'in verebileceği):** 1) Tezgâh paneli bahşişi göstersin ve 5 göndersin mi? Bu küçük bir arayüz değişikliğidir. Evet denirse plan Görev 11'i yapar. Hayır denirse sohbetteki "üstü kalsın" bira için ayrı bir Bahşiş kartı açar ve iki onay gerekir (güncel sıra §12 D34: Bahşiş kartı ancak bira başarıyla satıldıktan sonra açılır). Hayır yolunun ek sonucu (§13 D37): Geri Al tek adım olduğu için bahşiş onaylandıktan sonra Geri Al yalnız bahşişi geri alır, bira geri alınamaz.

## 12. J-013 sonrası düzeltmeler (2026-11-04)

Kaynak: Jarvis'in bağımsız incelemesi J-013 (12 bulgu) ve `DILIM1_J013_KARARLAR_20261104.md` (bağlayıcı kararlar). Bunlar belge incelemesi bulgularıdır; çalışan üründe yeniden üretilmiş hatalar değildir. D1–D24 değişiklik günlüğü olarak kalır; aşağıdakiler onlara eklenir ve çelişkide onların önüne geçer. Her madde: hangi bulgu/karar, yeni kural, değişen yer, hangi test sınar. Plan karşılıkları parantezde.

**D25. Ret ömrü (J-013 #1, KABUL).** Yanlış olan: eksik/geçersiz `coin_answer` `None` sayılıyor ve plan bu durumda `clear_decline` çağırıyordu; "NPC kabul etti" ile "model alanı vermedi" birleşiyordu. 8 kayıt sınırı da reddi üçüncü bir yolla bitiriyordu.
Yeni kural: Ret yalnız aynı NPC'nin ilgili kalem için verdiği **açık** `takes` ile ya da oyun günü değişince kalkar. `none`, eksik, bozuk ya da listede olmayan cevap reddi korur. Sınır 32 NPC'dir (`DECLINE_CAP = 32`). Yer gerekirse önce önceki günlerin kayıtları düşer; bugünkü kayıt sessizce düşmez. 32 bugünkü kayıt doluysa yeni ret yazılamaz, `decline_cap_full` loglanır ve o tur kart açılmaz (aynı gün 33 ayrı kişinin para reddetmesi gerektirir). Gün değişince ret biter; ret anında iptal edilmiş kartlar geri gelmez.
Değişen yer: §0, §3b madde 4–5, §5 `money_declined`; D3'teki "en çok 8 kayıt" ve "(a) NPC bu kez reddetmez" bitiş koşulu, karar 14 ve 56'daki "kabul edene" sözü ve Görev 10'daki "öteki değerler → `clear_decline`" kalktı (D3'te ve §9'da "yerine geçti" notu var). (Plan Görev 3, 10.)
Test: ret → tekrar para → eksik/`none`/bozuk cevap → yeni kart yok, kese aynı; 33 NPC'ye aynı gün ret → ilk NPC reddi sürer; dünkü kayıtlar önce düşer.

**D26. Ret hangi kaleme ait (J-013 #2, KABUL).** Yanlış olan: tek `coin_answer` değeri bahşiş reddini de oda/mal reddini de anlatıyordu; D14 oda kartını ve mal teklifini her retten koruyordu.
Yeni kural: `coin_answer_for` alanı motorun listelediği kalem kimliklerinden birini seçer: `tip`, `gift`, `room`, `goods:<anahtar>`, ya da `unclear`. Reddin etkisi yalnız o kalemedir (§3b madde 1). Kapsamı belirsiz genel ret (`unclear`, eksik ya da listede olmayan kalem) → o NPC'ye açık bütün para kartları ve tezgâh teklifi iptal edilir, ödeme ilerlemez, doğal konuşma netleştirir. Ret sürerken: panel hazırlığı `npc_declined`, tezgâh onayı `npc_declined` ile hiçbir şey değiştirmez. Yeni kelime listesi yok.
Değişen yer: §3b, §4 (`parts_for`, `record_decline(…, part, …)`, `declined(…, part, …)`), §5. D14 yalnız `tip`/`gift` kapsamlı retler için geçerli kalır. Karar 13 ve 56 bu kuralla daralır. (Plan Görev 3, 10, 9.)
Test: yalnız bahşiş reddi → mal alınır, bahşiş 0; oda bedelinin açık reddi → oda kartı onayı 0 keser; genel ret → o NPC'ye hiçbir ödeme ilerlemez.

**D27. Hafıza: kaynak ömrü görünümden ayrı (J-013 #3, KISMEN).** Yanlış olan: kaynak ve görünüm aynı 12 satırlık pencereye bağlıydı; 13. saklanmaya değer söz ilkini siliyordu; "20+ tur sorununu çözer" sözü fazla genişti.
Yeni kural: NPC başına 40 `remember=true` kaynak saklanır, görünüm en çok 3 satırdır. 41. kaynak o NPC'nin en eskisini düşürür; 33. NPC en uzun süredir yazılmayanı düşürür ve loglanır. 116 dürüstçe "Dilim 1: son 40 seçilmiş söz" diye yazılır; tam arşiv sonraya kalır (KISMEN: arşiv yok).
Değişen yer: §0, §3e Sınırlar, §4 `npc_told` sabitleri, §5, §7, §10; karar 39'un yerine karar 68. (Plan Görev 17, 23.)
Test (birim testi, Görev 17; senaryo 24 bu sayıyı taşımaz): aynı NPC ile 25 farklı konuşma, en az 13'ü `remember=true` → ilk bilgi kaynakta ve doğru soruda görünümde; 41. kaynak ilkini düşürür; 33. NPC sınırı.

**D28. NPC oyuncunun bildiği her şeyi bilmez (J-013 #4, KABUL).** Yanlış olan: konuşma modeline kese, çanta, oda ve bütün ödemeler gidiyordu; "görebildiğin kadar bil" başlığı bir süzgeç değildi.
Yeni kural: `truth_card.npc_view` ayrı kurulur (§3d): kese toplamı yerine "oyuncunun sana uzattığı: N bakır"; yalnız o NPC'nin teklifleri, ona yapılan ödemeler, kendi fiyatları, kendi yerindeki oda ve ona bağlı tur notları. Süzme, satır seçiminden ve bütçeden önce yapılır. Hafıza görünümü zaten NPC kimliğine göre seçilir; başka girdi kanallarından sızmadığı ayrıca test edilir.
Değişen yer: §3d, §4 `truth_card`, §5 `_turn_notes`; D18'deki konuşma başlığı değişti. (Plan Görev 12, 17.)
Test: A'ya özel aile ayrıntısı ve A'ya ödeme, B'nin konuşma çağrısının bütün mesajlarında yok; aynı adlı NPC içeren iki kampanya/karakter ayrı; NPC görünümünde "kese:" yok.

**D29. Teklif açmak para uzatmak değildir; `unclear` serbest yorum açmaz (J-013 #5, KABUL).** Yanlış olan: `decide` sıfır tutarda hemen `None` dönüyor, parasız `deal goods` eski yola düşüyordu; `unclear` kararından sonra kelime yolu yeniden açılıyordu; düşen model önerisi yapısal tahmine iniyordu.
Yeni kural: `goods`/`room` sıfır tutarla teklif/kart açar; pozitif tutar koşulu yalnız uzatılan para içindir. Karar yalnız "para yok ve `deal` yok/`none`" iken yoktur ve yalnız o zaman eski kelime yolu çalışır. Doğrulamada düşen model önerisi `unclear` olur; yapısal tahmin yalnız model hiç `deal` vermediyse denenir. `unclear` kart açmaz, kelime yolunu açmaz; para varsa not yazılır.
Değişen yer: §3a, §4 `decide`; karar 4'ü daraltır. (Plan Görev 4, 6, 7, 8.)
Test: parasız `deal goods` doğru teklifi açar; geçersiz mal/kişi önerisi oda kelimesi içerse de başka bir karta dönüşmez; tek tutarı tek işlem sahiplenir.

**D30. Tam söz 600 karakter, görünüm 200 (J-013 #6, KISMEN).** Yanlış olan: ilk 200 karakteri saklamak sondaki ayrıntıyı ya da olumsuzlamayı atabiliyordu.
Yeni kural: kabul edilen söz 600 karaktere kadar tam saklanır; görünümde satır başına 200 karakter, uzunsa "… (kısaltıldı; tamamı kayıtta)" işareti. 600'ü aşan söz `cut: true` alır ve hiçbir zaman kanıt sayılmaz. Düzeltme bağı ve kaynak action bağı Dilim 1 dışıdır (KISMEN; §10'a not düşüldü).
Değişen yer: §3e, §4, §5, §10; karar 35'teki 200 sınırı değişti. (Plan Görev 17.)
Test: önemli ayrıntı/olumsuzlama 200. karakterden sonra → kaynakta tam, görünüm işaretli; 700 karakterlik söz `cut` ve destek değil; hediye söylendi diye envanter değişmez.

**D31. İlgili satır bulmak destek değildir (J-013 #7, KABUL).** Yanlış olan: örtüşme yokken dönen "en yeni 3 satır" destek sayılıp inkârı ve yankı süzgecini kaldırıyordu.
Yeni kural: `supports` yalnız gerçek örtüşmesi (en az bir ortak kök) olan, kesilmemiş, o NPC'ye ait satırları döner. En yeni 3 satır yalnız `context_rows` ile bağlamdır; inkâr korumasını kaldırmaz. `claim_about` önce NPC sözü/vaadi kalıplarına bakar; karışık cümle `npc_words` olur (kaynak sahipliği). Genel "geçen sefer ne demiştim?" sorusunda örtüşme yoksa inkâr kalır: bilinçli ürün kararı.
Değişen yer: §3e; D10'daki "örtüşme yoksa en yeni 3 satır" ve `claim_about` sırası değişti; karar 40 ve 64 bu kuralla daralır. (Plan Görev 17, 18.)
Test: örtüşmesiz kendi-sözüm iddiası → inkâr; yalnız genel bir kökü paylaşan yanlış iddia → girdide yalnız gerçek satır, uydurma kısım "söylendi" olarak yok; olumsuzlama; "ben söylemiştim" + "sen söz vermiştin" aynı cümlede → inkâr.

**D32. Geri Al ve atomiklik kanıtı (J-013 #8, KABUL).** Yanlış olan: "world_state içinde, mevcut yol taşır" bir entegrasyon varsayımıydı; hafızaya özgü tekrar, yanıt kaybı ve gerçek yeniden açma sınanmıyordu.
Yeni kural: ayrı kayıt sahibi yaratılmaz; beş test eklenir: kayıt öncesi hata → eski dünya ve eski hafıza; commit sonrası yanıt kaybı → aynı action tekrarı makbuzla aynı sonuç, tek öğrenme; aynı action → bayt bayt aynı yanıt, tek satır; yeni oturum/yönetici ile gerçek yeniden açma ve soru orada; Geri Al sonrası kaynak ve bütün konuşma girdisi geri alınmış sözden arınmış.
Değişen yer: §3e, §5. (Plan Görev 21, Review Focus.)

**D33. 600 bayt ölçümü ve taşma kuralı (J-013 #9, KABUL).** Yanlış olan: "zorunlu alan hiç kısaltılmaz" ile "asla 600'ü aşma" her durumda birlikte sağlanamıyordu; hafıza başlığı ve tırnaklar bütçede değildi.
Yeni kural: ölçüm tamamlanmış UTF-8 metin üzerinde, başlık dahil. Zorunlu alan taşma kuralı §3d'dedir; öncelik aktif işlem > bu turun sonucu > anı. Düşen zorunlu satır "(kısaltıldı: …)" ile adlanır ve loglanır. Son istem boyu ölçüm koşusunda kaydedilir.
Değişen yer: §3d, §3e, §8; karar 28'i tamamlar. (Plan Görev 12, 17, 22.)
Test: uzun ad/yer/etiket + birden çok tur notu + Türkçe harfler; bütün isteğe bağlı satırlar atıldıktan sonra da ≤600; hafıza başlığı ve kaynağı dahil ≤600; kritik sonuç sessizce düşmez.

**D34. Panel "hayır" dalı iki ayrı işlemdir (J-013 #10, KABUL).** Yanlış olan: B yolu Bahşiş kartını mal satılmadan açıyordu; mal reddedilir ya da iptal olursa bahşişin ne olacağı tanımsızdı; tek Geri Al iki ödemeyi birlikte döndürmeyebilirdi.
Yeni kural: B yolunda bahşiş, başarılı mal makbuzundan **sonra** teklif edilir (`tip_after_cp` → Bahşiş kartı). Mal satılmazsa bahşiş kartı açılmaz. İki onay, iki makbuz, iki Geri Al adımı; her biri ayrı sınanır. *(Daraltıldı: §13 D37. Motor tek Geri Al adımı verir; "iki Geri Al adımı" art arda iki Geri Al değil, her onayın yalnız kendi turunun hemen ardından geri alınabilmesi demektir. Bahşiş onaylandıktan sonra mal geri alınamaz.)* Panel kararı gelmeden ana yolun ürün davranışı tamamlandı sayılmaz. D1'in "gösterilenden fazla kesmeme", "bahşiş sığmıyorsa hiçbir şey değişmez" ve HTTP tekrar koşulları korunur.
Değişen yer: §0, §3b, §5 Geri al, §6; Görev 9'un B yolu yeniden yazıldı. (Plan Görev 9.)
Test: iki onay sırası; aradaki hata (mal reddi/fiyat değişimi → bahşiş kartı yok); bahşiş reddi; aynı action tekrarı; her Geri Al adımı.

**D35. Gerçek zincir kapısı (J-013 #11, KISMEN).** Yanlış olan: hafıza kabulü betikle hazırlanmış öğrenmeye dayanıyordu; son ölçü yalnız `inkar:false` idi; 04b gerçek adımı koşu listesinde yoktu.
Yeni kural: hafıza için beş kanıt ayrı raporlanır (doğru dinleyen, kalıcı kaynak, yeniden açılmış kaynak, son model girdisi, son cevap). Son cevapta doğru ayrıntının bulunması, Python inkârının yokluğundan ayrı sınanır. Koşu listesi: rc1, rc2, 24 adım 12, 04b menzilli saldırı adımı ve kontrollü gerçek örnek `24r` (ilk anlatımda `remember_player_line`'ı model doldurur). KISMEN: geniş gerçek ölçüm yok; yalnız bu kısa liste.
Değişen yer: §6, §7 madde 4; D21'i tamamlar. (Plan Görev 18, 22, 23.)

**D36. Tek yerde okunur sözleşme (J-013 #12, KABUL).** Belgenin başına bir sayfalık Türkçe güncel özet (§0) kondu; §4 modül tablosu güncel hâliyle değiştirildi (kaldırılmış `truth_card.receipt_label`, `money_owner.record_decline`, eski fiyat sahipliği ve eski `session` arayüzleri tablodan çıktı); §3a, §3b, §3d, §3e, §5 ve §6 güncellendi; D1–D24 değişiklik günlüğü olarak kaldı. (Plan başlığı ve Öz-inceleme.)

**Yeni kararlar (Kadir'in onayına açık; eski numaralar silinmedi):**
66. Ruling: Ret yalnız açık `takes` ya da gün değişimiyle kalkar; eksik/bozuk cevap reddi korur; sınır 32, önce önceki günler düşer, bugünkü sessizce düşmez (D25) — "model alanı vermedi" "NPC kabul etti" sayılmasın — yanlışsa: NPC fikrini değiştirdiğinde model `takes` vermezse oyuncu ertesi güne kadar bekler.
67. Ruling: Ret motorun listelediği kaleme bağlanır; belirsiz kapsamlı ret o NPC'ye ödemeyi durdurur (D26; karar 13 ve 56'yı daraltır) — bahşiş reddi birayı, oda reddi parayı yanlış etkilemesin — yanlışsa: model kalemi yanlış seçerse yanlış kalem durur; para yine onaysız gitmez.
68. Ruling: NPC başına 40 seçilmiş söz kaynağı, görünüm 3 satır; Dilim 1'in sözü "son 40 seçilmiş söz" (D27; karar 39'un yerine) — 13. söz ilkini silmesin, kapsam dürüst yazılsın — yanlışsa: çok konuşkan oyuncuda 41. sözden sonra ilk bilgi yine düşer; tam arşiv sonraki iştir.
69. Ruling: NPC'ye ayrı görünüm; kese yerine "uzattığı N bakır"; süzme seçimden önce (D28) — NPC görmediğini bilmesin — yanlışsa: NPC oyuncunun parasının yetip yetmediğini kendiliğinden bilemez, oyuncu söyler.
70. Ruling: Teklif açma para uzatma değildir; eski yol yalnız "öneri hiç yok"ta; düşen model önerisi `unclear` olur (D29; karar 4'ü daraltır) — ikinci yorumlayıcı başka kart açmasın — yanlışsa: geçersiz öneri yapısal tahminle kurtarılamaz, oyuncu bir satır daha yazar.
71. Ruling: Kabul edilen söz 600 karaktere kadar tam; görünüm 200; kesilen kanıt değil; düzeltme bağı Dilim 1 dışı (D30; karar 35'teki sınırı değiştirir) — sondaki ayrıntı/olumsuzlama kaybolmasın — yanlışsa: kayıt dosyası büyür (§8).
72. Ruling: Destek yalnız gerçek örtüşme ve kaynak sahipliğiyle; son 3 satır bağlamdır, inkâr korumasını kaldırmaz; karışık cümle NPC sözü sayılır (D31; karar 40 ve 64'ü daraltır) — uydurma "sen dedin" desteklenmesin — yanlışsa: genel bir "ne demiştim?" sorusu "hatırlamıyorum" alır.
73. Ruling: Atomiklik, yanıt kaybı, tekrar, gerçek yeniden açma ve Geri Al sızıntısı testle gösterilir; ayrı kayıt sahibi yok (D32; karar 45'i kanıtla destekler) — varsayım kanıt sayılmasın — yanlışsa: düzenek biraz büyür.
74. Ruling: Bütçe tamamlanmış UTF-8 metinde ölçülür; zorunlu alan taşma kuralı aktif işlem > bu turun sonucu > anı; düşen satır adlanır (D33; karar 28'i tamamlar) — kritik sonuç sessizce düşmesin — yanlışsa: çok uzun adlarda kart "(kısaltıldı: …)" taşır.
75. Ruling: Panel "hayır" yolunda bahşiş başarılı mal makbuzundan sonra açılır; iki işlem ayrı sınanır (D34; Görev 9 B yolunu değiştirir) — mal alınmadan bahşiş ödenmesin — yanlışsa: oyuncu iki onay verir.
76. Ruling: Hafıza beş kanıtla ayrı raporlanır; gerçek koşu listesine 04b ve `24r` eklenir (D35; karar 50 ve 62'yi tamamlar) — betikli öğrenme ürün kanıtı sayılmasın — yanlışsa: gerçek koşu biraz daha pahalı (5 adım).
77. Ruling: Belgenin başında tek sayfalık güncel özet ve güncel modül tablosu; D1–D36 değişiklik günlüğü (D36) — eski kararlara yanlışlıkla dönülmesin — yanlışsa: yalnız belge düzeni.

## 13. Dilim 0 incelemesi sonrası düzeltme (2026-11-04)

Kaynak: Dilim 0 incelemesinde doğrulanan motor gerçeği. Bu bir belge düzeltmesidir; ürün kodu değişmez. Çelişkide §12 ve §11'in önüne geçer (§0 > §13 > §12 > §11).

**D37. Geri Al tek adımdır; panel "hayır" yolu buna uyar (Dilim 0 incelemesi, KABUL).**
Yanlış olan: §0, §3b, §5, §6, D34 ve plan Görev 9 (senaryo 25 B adım 4–5, `test_b_path_each_undo_step_returns_only_its_own_receipt`) art arda iki Geri Al bekliyordu: birincisi bahşişi, ikincisi birayı geri alacaktı. Motor bunu yapmaz.
Motor gerçeği (okundu, çalıştırılmadı; `AI-DND-c-merge` 3c733c57, `ae815c4f`'de aynı kod birkaç satır kaymış):
- Her tamamlanan tur, kart onayı dahil, tek bir `record.undo_checkpoint` yazar ve öncekinin üstüne yazar (`api/main.py:1971` tur yolu; `:1160` ekonomi yolu, yalnız kart tüketildiyse). Tezgâh onayı (`/item shop_buy`) ve kart onayı (`economic_action confirm`) ikisi de tur yolundan geçer.
- `undo_last_turn` (`:1991`) yalnız `target_action_id` bu son turun kimliğine eşitse çalışır; değilse `409`, `detail.code == "undo_unavailable"`, mesaj "Geri alınabilecek bir son tur yok." (`:2018-2022`) ve hiçbir şey değişmez (son turun kaydı da silinmez).
- Başarılı Geri Al'dan sonra kayıt silinir (`:2100` "One step only: a second undo needs a new completed turn first."). Arka arkaya ikinci Geri Al `409 undo_unavailable` alır.
- Aynı `action_id` ile gönderilen Geri Al yeni bir Geri Al değildir; ilk cevabın bayt bayt tekrarıdır (`:2008-2014`).
- Arayüz de tek adım gösterir: başarılı Geri Al'dan sonra `canUndo` yanlış olur (`artifacts/ai-dnd-experience/src/pages/game-browser.tsx:1359`, `:2416`; okundu, çalıştırılmadı).
Yeni kural (motor ve arayüz değişmez; sıfır tolerans):
1. Geri Al yalnız en son tamamlanan turu ve onun makbuzunu geri alır. Dilim 1'deki hiçbir test ya da senaryo art arda iki başarılı Geri Al beklemez.
2. Panel "hayır" yolu, bahşiş onaylandıktan sonra: Geri Al yalnız bahşiş makbuzunu döndürür (kese 95 → 96, barmen 5 → 4; aynı `offer_id`'li Bahşiş kartı yeniden `prepared`, `operation_id` ve `consumed_action_id` boş). Mal makbuzu, Bira ve 4 bakır yerinde kalır. Ardından ikinci Geri Al ve mal onayını hedefleyen Geri Al → `409 undo_unavailable`; dünya, defter ve kayıt değişmez. Yeni bir tur oynamak malı geri alınabilir yapmaz; Geri Al o zaman yalnız yeni turu geri alır.
3. Panel "hayır" yolu, mal onayından hemen sonra (bahşiş onaylanmadan): Geri Al malı, 4 bakırı ve tezgâh teklifini (bekleyen `tip_after_cp` 1 dahil) döndürür; o turda açılan Bahşiş kartı `cancelled` olur. Malı geri almanın tek yolu budur.
4. Panel "evet" yolu değişmez: tek makbuz, tek Geri Al kese, satıcı kesesi, eşya ve bahşişli teklifi birlikte döndürür.
5. Senaryolarda art arda iki `undo` adımı konmaz: düzenek `undo` adımında 200 dışı her cevabı kırık sayar (`test_journey_runner.py` "one undo per turn"). 409 beklentisi HTTP birim testlerinde sabitlenir.
Oyuncunun göreceği sonuç (Kadir'e bildirilecek): B yolunda "üstü kalsın" tek Geri Al ile tamamen silinmez. Bahşişten sonra Geri Al'a basan oyuncu bahşişini geri alır, birası ve 4 bakırlık ödemesi kalır; arayüz o anda Geri Al'ı artık sunmaz. Birayı da geri almak isteyen oyuncu Geri Al'ı bahşiş kartını onaylamadan önce kullanmalıdır. Bu, panel sorusunda (açık soru 1) "evet" için ek bir gerekçedir; "hayır" seçilirse bu davranış bilerek kabul edilmiş olur.
Değişen yer: §0 (Geri Al maddesi), §3b panel "hayır" yolu, §5 Geri al, §6 senaryo 25 ve D34 kabul testi; D34 "iki Geri Al adımı" sözü daraltıldı. (Plan: Global Constraints, Review Focus 5 ve 12, Görev 9 B yolu ve senaryo 25 B, Görev 21 `test_undo_restores_decline_consumption_and_memory`.)
Test: plan Görev 9 `test_b_path_undo_right_after_the_goods_takes_back_the_beer_and_closes_the_tip_card`, `test_b_path_after_the_tip_confirm_one_undo_takes_back_only_the_tip`; senaryo 25 B adım 3 ve 7; Görev 21 ikinci Geri Al 409 iddiası.

**Yeni karar (Kadir'in onayına açık):**
78. Ruling: Geri Al tek adımdır ve Dilim 1'de değişmez; panel "hayır" yolunda Geri Al yalnız son onayı (bahşiş onaylandıysa yalnız bahşişi) geri alır, ikinci Geri Al `409 undo_unavailable` alır; mal yalnız bahşiş onaylanmadan önce geri alınabilir (D37; D34'teki "iki Geri Al adımı"nı daraltır) — geri alda sıfır tolerans, motorun kanıtlı kuralı belge için değiştirilmesin — yanlışsa: B yolunda oyuncu bahşişten sonra birayı geri alamaz; isterse panel "evet" yolu bunu ortadan kaldırır.
