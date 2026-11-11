# MOTOR DENETİMİ (snapshot 724b0419, salt okuma)

## 1) Motor nasıl çalışıyor

Bir tur şöyle akar:

```
yazdığın satır
  -> api/main.py play_turn: niyet kaydı, kilit, anlık görüntü (snapshot)
  -> MODEL ÇAĞRISI 1: "ön okuma" (satır kime/neye; game.py:18383)
  -> sahne planlayıcı (Python kelime listeleri; game.py:16713)
  -> _dispatch_player_turn: sırayla ~25 "sahip" denenir, ilk eşleşen alır (game.py:18529)
  -> Python kuralları (zar, para, envanter)
  -> MODEL ÇAĞRISI 2: NPC konuşması VEYA anlatıcı (biri)
  -> tur-sonu kancalar: oda parası, dünya tepkileri, haberciler (game.py:17824-17834)
  -> kayıt: tek SQLite işlemi, makbuz, geri alma noktası
```

Dünya tek bir büyük sözlükte (world_state, ~100 anahtar); herkes her şeyi yazabilir. Saat ilerleyince haberler yayılır, işler kapanır, haberci gelir. Modelin dediği doğrudan duruma yazılmaz; ancak birkaç alan ("threat", "item_claims", kişi adı) Python kontrolü olmadan duruma giriyor. Model çağrıları önce Gemini'ye, sonra Haiku'ya, sonra yerel Gemma'ya gider (api/model_chain.py:465-494); f6'da 116 çağrının 112'si Gemini.

## 2) En çok sorun çıkaran 10 yer

**1. NPC cevabındaki "threat" alanı seni tehdit etmiş sayıyor (KRİTİK)**
Ne oluyor: NPC sadece bir işten bahsedince model o işin id'sini "threat" alanına yazıyor; motor bunu "oyuncu tehdit etti" diye okuyup 6-20 saat sonra düşman haberci yolluyor ("Söylediklerini unutmadı").
Oyunda: f6 T39-41 (demirci), T57-59 (seni işe alan sepetçi), f5 T33/T62 (gece bekçiliği veren ev).
Neden: mimari; alan zorunlu (game.py:7953-7955), hiçbir Python kontrolü yok.
Nerede: world_happenings.py:170-182, town_knowledge.py:603, content/world/town_threads.json:727.
Ne yapılmalı: alanı isteğe bağlı yap; haberci yalnızca defterde bir eylem (saldırı, hırsızlık) varsa ya da oyuncunun kendi satırı tehdit testini geçerse gelsin. İş id'si asla "warned" tonu vermesin.
Adım: 3c.

**2. Para iki yerde, kimse kontrol etmiyor, oyuncu göremiyor**
Ne oluyor: altın önce envanterde "10 Altın" yazısı, ilk harcamada cüzdana dönüşüyor; çantadan "kayboluyor". Anlatı "30 bakır çıktı" dese de cüzdan oynamayabiliyor; makbuz kontrolü parayı hiç bakmıyor.
Oyunda: f6 T13 (altınlar yok oldu), T43 (anlatı para dedi, cüzdan sabit), f4 T4.
Neden: mimari.
Nerede: api/action_contract.py:61-66, bold_acts.py:584-612, equipment_economy.py:579-587, 753-765.
Ne yapılmalı: tek para deposu; karakter yaratılırken dönüştür; cüzdanı herkese açık duruma ve commit kontrolüne ekle; her para hareketi tek fonksiyondan (kim, kime, ne kadar, neden) geçsin.
Adım: 3b.

**3. Modelin okuması var ama eski kelime listeleri önce davranıyor**
Ne oluyor: model "yürü/konuş" dese de pano, çanta, cep, cüret gibi 10+ eski sahip satırı kapıyor; okuma ancak hiçbiri eşleşmezse kazanıyor.
Oyunda: f6 T45/T46 ("sepetçiye yürüyorum, ilan vardı ya" -> pano okundu), f4 T103, f5 T28.
Neden: mimari (sıra).
Nerede: game.py:18546-18678 (sahipler), 18661 (pano sadece speak_to'da atlanıyor), 18679 (okuma burada kullanılıyor).
Ne yapılmalı: geçerli okuma varsa önce ona göre dağıt; kelime-listesi sahipleri sadece attempt/look/unclear için çalışsın.
Adım: 3a.

**4. Haberci evine dönemiyor, düşmanlaşınca sonsuza dek kalıyor**
Ne oluyor: habercinin "geldiği yer" gönderenin yeri; sen zaten oradaysan "gitti" yazılır ama NPC sahnede kalır. Vurulan haberci hiç ayrılmaz.
Oyunda: f6 sepetçi/oduncu haberci sahneleri (T57-68).
Neden: yerel hata.
Nerede: world_happenings.py:521-526, 544-547, 561.
Ne yapılmalı: haberciyi bulunduğun yerden farklı bir yere gönder; düşman haberciyi de süre dolunca çıkar.
Adım: 3c.

**5. İki parçalı satırda çanta iki kez basılıyor, soru cevapsız kalıyor**
Ne oluyor: "kesemi yokluyorum, biram nerde?" -> envanter listesi iki kez, bira sorusu yok.
Oyunda: f6 T14, T16, T75.
Neden: yerel hata; "bag" dalı konuşma modunu kontrol etmiyor, satırın kalanı aynı okumayla yeniden dağıtılıyor.
Nerede: game.py:18650-18653, 17904-17927.
Ne yapılmalı: kalan kısmı dağıtmadan önce okumayı speak_to'ya daralt ya da bag dalını say modunda kapat.
Adım: 0.

**6. Kâhyaya söylenen söz Gizlenme zarı attırıyor**
Ne oluyor: "saklanmanın anlamı yok" -> "Saklanma girişimin başarılı olur" ve bu kâhyanın ağzına konuyor.
Oyunda: f6 T30-31.
Neden: yerel hata; "saklan" alt-dizesi olumsuzluk/soru kontrolü olmadan Stealth seçiyor, konuşma yolu da bu kontrolü çalıştırıyor.
Nerede: game.py:1264, 15497-15501.
Ne yapılmalı: intent "dialogue" ise zar atma; diğer becerilerdeki olumsuzluk korumasını (game.py:1234-1262) buraya da uygula.
Adım: 0.

**7. Tur başına 2 model çağrısı; ikinci yarı ve onarımlar için çağrı kalmıyor**
Ne oluyor: 1. çağrı hep ön okuma; NPC konuşunca kota biter, satırın kalanı ya da bozuk cevap onarımı hazır Python metnine düşer, sessizce.
Oyunda: f6 T6/T22 (basmakalıp cümle), f4 #11 (ikinci yarı düştü).
Neden: mimari.
Nerede: api/ollama_adapter.py:27, 268-272; game.py:17914, 17988.
Ne yapılmalı: bütçeyi bilinçli seç (onarım için 3. çağrı ya da also_says'i aynı konuşma çağrısında cevapla); kota aşımını "bütçe" diye ayrı logla.
Adım: 5.

**8. Model kimseyi adlandırmayınca satır son konuştuğuna yapıştırılıyor; "threat_to" tek kelimeyle iz bırakıyor**
Ne oluyor: "pazarlık eden satıcıya yaklaşıyorum" -> barmen cevaplıyor. Modelin threat_to dediği kişiye kontrolsüz "guarded" bağ açılıyor.
Oyunda: f6 T19, f5 T28 (olası).
Neden: yerel hata.
Nerede: front_proposal.py:320-322, game.py:18233-18235, 18683.
Ne yapılmalı: person_word varsa onu tercih et; threat_to'yu strike ile aynı kelime testinden geçir.
Adım: 3a.

**9. Anlatıcının uydurduğu eşya çantaya giriyor**
Ne oluyor: çekmecede anlatılan parşömen gerçek oluyor, anahtar olmuyor.
Oyunda: f4 T132-134.
Neden: mimari; "ekran gösterdi" kontrolü aynı modelin düzyazısı.
Nerede: game.py:19342-19352, pocket.py:245-265.
Ne yapılmalı: yalnızca Python kaydında olan (yer, özellik, NPC) eşya verilsin.
Adım: 3b.

**10. Tur-içi geçici alanlar anlık görüntü dışında**
Ne oluyor: _handed_note tur sonunda silinmiyor; sonraki herhangi bir NPC "az önce bana N bakır verdin" sanabilir. Başarısız turdan _front_ahead kalırsa eski rota ve para bir sonraki tura taşınır.
Oyunda: doğrudan görülmedi, koddan.
Neden: yerel hata.
Nerede: game.py:18318-18320, 17730-17740; front_proposal.py:367-386.
Ne yapılmalı: tüm _front_*/_coin_* alanlarını API tur sınırında sıfırla (finally içinde).
Adım: 0.

## 3) Güçlü taraflar (koru)

- Kayıt yolu sağlam: niyet kaydı, kilit, iki katmanlı snapshot, tek işlemde commit, dijestle doğrulanan geri alma, karantina (api/main.py:148-207, runtime_recovery.py:20-35). f6'da 75 tur, 0 geri alma.
- Anlatıcının dünya önerileri reddediliyor (game.py:19156-19160); yalnızca Python'un doğruladığı değişiklik işleniyor.
- Model zinciri ve anahtar yönetimi temiz (başlıkta taşınır, loglanmaz, trust_env kapalı).
- Eylem defteri (bold_acts.remember) ve haberin kapı kapı yayılması iyi fikir; sorun tetikleyicide, mekanizmada değil.

## 4) Doğrulanmayanlar

- Hiçbir kod çalıştırılmadı; bağlantılar kod okuması + f4/f5/f6 kayıtlarından. f4/f5/f6 sunucularının tam bu commit'te koştuğu doğrulanmadı.
- Modelin ham ön-okuma cevabı loglanmıyor; 5, 7, 8 numaralı bulgularda "also_says" ve "speaking_with onarımı" çıkarım.
- 10 numaralı bulgu ve "_person_answers_stock" orta-tur geri yüklemesi yeniden üretilmedi.
- Makbuzların sıkıştırılmaması (1.42 MB / 75 tur), Gemini zaman aşımı (20 sn) ve bulut veri gizliliği gerçek ama oyunda henüz acı vermedi; listeye alınmadı.
- Roadmap adım atamaları bu raporun yorumudur (0=hemen, 3a=rota, 3b=durum/para, 3c=dünya, 5=model); plan sahibi düzeltebilir.
