# NPC dünya bilgisi ve anlatıcı: tasarım (D-249, D-250) — 2026-11-16

Durum: onaylı (Kadir, 2026-11-16). Üst belge: `MOTOR_HAKEM_MODEL_YAZAR_TASARIM_20261113.md` bölüm 4b (öneri şeritleri; onaylı, Kadir 2026-11-13). Bu belge o bölümdeki Ş4 "Söylenti ve iz" şeridini açar ve Ş6 "Yer" şeridini NPC konuşmasına genişletir.

## 1. Neden

Kadir'in şikâyeti: NPC'ler "bilmiyorum" diyor, kasaba ölü. Ölçüm (KOD 1 araştırması, 2026-11-15, `ARASTIRMA_MODEL_YARATICILIK_20261115.md` C-4, C-5): 21 konuşmanın 6'sında söz 60 harfin altında; modelin uydurduğu "iki kervan" ve mahzen izi motorda hiçbir yere yazılmadı, oyuncu peşine düşemedi.

Kadir'in kararları:
- 2026-11-16: D-249 ve D-250 bu dilimin ana işi.
- 2026-11-16: model yer, kişi ya da iz uydurabilir; motor bunu kaydeder ve oyuncu peşine düşebilir (seçenek B: "model serbest").
- Kalıcı kural: eski kayıtların önemi yok; bu dilim eski kayıt için hiçbir uyumluluk işi yapmaz.

## 2. Hedefler

1. NPC kasabayı tanır: yerlerin kısa tarifini, sorununu, orada hangi rollerin bulunduğunu, duyulmuş söylentileri bilir.
2. Bir NPC bir yer ya da iz söylediğinde motor onu "duyulmuş" olarak kaydeder. Sonraki turda başka NPC'ler de bunu bilebilir; oyuncu "oraya gidiyorum" dediğinde yol bulunur.
3. Anlatıcı daha cesur yazar: varış anlatısı daha uzun olabilir, hava serbest, geçmiş daha uzun okunur, bulut modellere kendi istemleri gider.

## 3. Hedef olmayanlar

- İş, ödül, para, fiyat, eşya değeri, XP, zar, süre: model hâlâ bunlara dokunamaz (üst belge 4b, "hiçbir şeritte").
- Konuşmadan yeni NPC kaydı açmak: NPC'nin bahsettiği kişi bu dilimde yalnız söylenti metni olarak kalır; kişi kaydı oyuncu onu bulduğunda mevcut Ş3 yoluyla açılır.
- Eski kayıt göçü ya da onarımı (Kadir kuralı).
- Arayüz değişikliği (A2 hattı ayrı; A2'den sonra arayüze Vercel v0 yardımı planlı).

## 4. Olmaması gerekenler (başarısızlık sayılır)

- Model söylentisi gerçek bir görev, ödül ya da para doğurur.
- Reddedilen bir öneri oyuncuya hata satırı olarak görünür ("bunu doğrulayamıyorum" türü).
- Aynı yer iki kez kaydedilir (aynı sokakta üç "Eski Mahzen").
- Tur başına 2 model çağrısı sınırı aşılır.
- Kelime listesiyle niyet yönlendirme eklenir (proje kuralı).

## 5. Kısıtlar

- Tur başına en çok 2 model çağrısı: `api/ollama_adapter.py` `MAX_MODEL_CALLS_PER_TURN = 2`. Bu dilim yeni model çağrısı eklemez.
- Haiku'ya sıcaklık gönderilemez (`api/model_chain.py` `haiku_body`: varsayılan dışı değer 400 hatası verir). Haiku yalnız istemle ayarlanır.
- Haiku dilbilgisi sınırı: `arrival_narration.py` şema yorumu "bir alan daha Haiku sınırını aşar" diyor. NPC konuşma şemasına (`game.py` `_EXPERIMENTAL_NPC_SPEECH_SCHEMA`) eklenen alan Haiku ile gerçekten denenmeden kabul edilmez.
- Model önerir, Python denetleyip kaydeder; model kayda doğrudan yazmaz.
- Yeni dünya alanları kayıt (save) ve Geri Al ile tutarlı olmalı: kaydet-yükle ve Geri Al sonrası aynı.

## 6. Düşünülen yollar

Kadir B'yi seçti (model serbest). Nasıl yapılacağı için iki yol düşünüldü:

| Yol | Ne | Artı | Eksi |
|---|---|---|---|
| 1. Söylendiği anda kayıt | NPC cevabına isteğe bağlı küçük bir "bahsedilen yer/iz" alanı; Python denetler, "duyulmuş" kaydeder | Dünya hemen tutarlı; başka NPC sorulunca bilir | Şema büyür; model alanı unutabilir |
| 2. Takip anında kayıt | Hiçbir şey kaydedilmez; oyuncu ize gidince motor son konuşmalarda adı bulur, anlatıcı yeri o an yaratır | Az kod; bugünkü yolun yarısı var | Başka NPC'ye sorulursa yine "bilmiyorum" (şikâyet kalır) |

Seçim (KOD 2 kararı, Kadir "nasıl"ı devretti): Yol 1 ana yol; Yol 2 yalnız modelin alanı unuttuğu durum için güvenlik ağı.

Ayrıca reddedilen seçenek: konuşmadan sonra ikinci bir model çağrısıyla yer ve iz çıkarmak. Tur başına 2 çağrı sınırını aşar.

## 7. Tasarım

### 7.1 NPC'nin bildiği (D-249 birinci kısım)

Yer: `ai-dnd/town_knowledge.py` `public_knowledge`.
- `MAX_ITEMS` 5'ten 10'a, `MAX_BYTES` 600'den 1500'e (KOD 2 kararı; ölçümle ayarlanabilir).
- Yer maddesi yalnız "Ad (tür)" değil: tarifin ilk cümlesi (en çok 120 harf), `local_issue` varsa kısa hâli, orada bulunan rollerin listesi (adlar değil roller: "bir demirci, iki muhafız").
- Söylenti: `town_rumours.rumour_for` kişi başına 1 yerine en çok 2 söylenti; kaynak açık "trouble" konuları artı 7.2'deki duyulmuş söylentiler.
- Hangi NPC neyi bilir: bugünkü tohumlu kapsama kuralı (`_coverage`, rol tablosu) aynen; duyulmuş söylentiler de aynı kuralla dağılır (söyleyen kişi her zaman bilir).
- `hidden` yerler yine gönderilmez; duyulmuş söylentide geçen bir yer gizli değildir.

### 7.2 Söylenti ve iz şeridi (Ş4, Kadir B)

Hangi konuşma yolu: `_EXPERIMENTAL_NPC_SPEECH_SCHEMA` kullanan bütün NPC konuşmaları (Gemini, Haiku ve yerel Gemma aynı şemayı alır; yerel model alanı doldurmazsa 7.3 karşılar) (KOD 2 kararı).

NPC konuşma şemasına isteğe bağlı tek alan: `mentions` (en çok 1 öğe; KOD 2 kararı, Haiku sınırı yüzünden dizi değil tek nesne de olabilir; yapıcı Haiku ile dener ve seçer):
- `kind`: `place` ya da `trail`.
- `name`: yerin adı (en çok 60 harf, `validate_location_proposal` ile aynı ad kuralı).
- `place_kind`: `local_places.PLACE_KINDS` listesinden biri (kapalı liste, şemada enum; üst belge Ş6 "türü listeden"). `trail` için boş olabilir.
- `about`: kısa tarif ya da iddia (en çok 120 harf).

Ayrı bir "yakınında" alanı yok: duyulmuş yer her zaman konuşmanın geçtiği yerleşimin altına yazılır (KOD 2 kararı; şemayı küçük tutar, yol ve komşuluk kodu değişmez).

Python denetimi:
- Ad var olan bir yere çözülüyorsa (`resolve_location_reference`) yeni kayıt açılmaz; söylenti o yere bağlanır.
- İçinde para, fiyat, eşya değeri ya da mekanik iddia olan `about` boşaltılır (mevcut tarif temizleyicisi, `validate_location_proposal` içindeki).
- Yer bu kasabanın altına yazılır (`parent_location_id` = konuşmanın geçtiği yerleşim).
- Sınırlar: konuşma başına en çok 1 öneri; yerleşim başına en çok 24 duyulmuş yer (KOD 2 kararı); genel 80 yer sınırı aynen. Kasaba başına 8 yer sınırı (`MAX_LOCAL_PLACES_PER_SETTLEMENT`) duyulmuş yerleri saymaz.

Kayıt:
- `place`: sıradan bir `local_places` yerel yer kaydı (`local_places.create_local_place` yolu; adı modelden gelir, yapıcı işleve ad parametresi ekler), `place_kind` şemadan, `parent_location_id` ve `exit_location_id` yerleşimden, `reality_layer = "PROCEDURAL_LOCAL_FICTION"`, `provenance = {"source": "npc_rumour", "said_by": <npc id>, "turn": <tur>}`, `rumoured = true`. Gizli değildir: seyahat çözümü, yer listeleri ve NPC bilgisi onu normal yer gibi görür; oyuncu adını söyleyince yol bugünkü yerel yer yoluyla bulunur. Genel 80 yer sınırına sayılır; kasaba başına 8 sınırına sayılmaz (sayım `rumoured` kayıtları atlar).
- Varış: oyuncu oraya ilk kez vardığında bugünkü yerel yer varışı çalışır (varış anlatısı tur başına 2 çağrı sınırı içinde, mevcut `arrival_narration` yolu); `rumoured` alanı silinir (Ş6, yer gerçekleşir). Yeni model çağrısı yok.
- Sınır dolarsa (yerleşim başına 24 `rumoured` yer): yeni öneri kabul edilmez değil, en eski hiç ziyaret edilmemiş `rumoured` yer silinir ve ona bağlı söylentilerin `place_id` alanı boşalır (KOD 2 kararı; şerit 24'te sessizce durmasın diye). Gerçekleşmiş yer hiç silinmez.
- `trail` ve her öneri: dünyada yeni bir liste `world["heard_rumours"]`: `{id, text, said_by, place_id (varsa), turn}`. Tüketicisi NPC bilgisidir (7.1; başka NPC'ler tohumlu kapsama kuralıyla tekrarlar); yeri olmayan iz yalnız söylenti metnidir, oyuncu ona 7.3 ad eşleşmesiyle ya da ileride yeri söylendiğinde ulaşır. Ana anlatıcıya ayrıca gönderilmez (KOD 2 kararı; istem bütçesi). Söylenti görev, ödül ya da para doğurmaz. Liste üst sınırı yapıcıya kalır (bölüm 9).
- Reddedilen öneri: kayda girmez; NPC'nin sözü olduğu gibi kalır (NPC yanılabilir ya da yalan söyleyebilir). Para ve eşya iddiaları mevcut K2 süzgeçlerinden geçmeye devam eder.
- Geri Al ve kayıt: o turda açılan duyulmuş yer ve söylenti, turun Geri Al'ı ile kalkar; kaydet-yükle sonrası aynıdır. Yapıcı önce dünya anlık görüntüsünün (`_capture_runtime_snapshot` ve Geri Al kaydı) bu yeni anahtarları kapsadığını testle gösterir; kapsamıyorsa ekler. Yeni kampanya `heard_rumours` listesini boş olarak kurar; okuma yerinde `setdefault` yeterlidir (eski kayıt göçü yok).

### 7.3 Güvenlik ağı: takipte kayıt (Yol 2)

Oyuncu kayıtlı olmayan bir yere gitmek isterse (bugün `game.py` seyahat niyeti, `proposal_required`):
- Hedef ad, seyahat niyetinin bugün çıkardığı `target_reference`'tır (yeni model adımı yok). Kesme işaretinden sonraki ek atılır ("Eski Mahzen'e" → "Eski Mahzen"); sonra büyük-küçük harf ve Türkçe harf katlamasıyla, aynı yerleşimdeki NPC'lerin son konuşmalarından birinde (`_NPC_SPEECH_KEEP = 4`) birebir geçiyorsa (kelime listesi değil) anlatıcının yer önerisi açık sokak dışında da kabul edilir. Yer 7.2'deki gibi `rumoured` olmadan, gerçek yerel yer olarak konuşmanın geçtiği yerleşimin altına yazılır, `provenance.source = "npc_rumour"`.
- Böyle bir eşleşme yoksa bugünkü davranış aynen.

### 7.4 Kent tarifi

- Bir yerleşime ilk varışta varış anlatısı zaten model çağrısıdır (`arrival_narration.narrate`). Yeni şema alanı eklenmez (Haiku sınırı). Onaylanan ilk varış metninin ilk iki cümlesi yerleşim kaydına `town_portrait` olarak yazılır.
- NPC bilgisi (7.1) bu tarifin ilk cümlesini taşır.
- Model çağrısı yoksa ya da düşerse: motorun kendi verisinden (yerleşim tarifi, yer türleri) Python yedeği; yedek kalıcı yazılmaz, bir sonraki model varışında yeniden denenir.

### 7.5 Anlatıcı (D-250)

`ai-dnd/arrival_narration.py`:
- Cümle sınırı ilk varışta 4'ten 6'ya, dönüşte 3'ten 4'e (`_shaped` `limit`) (KOD 2 kararı).
- "Havadan söz etme" kuralı kalkar (ana anlatıcı zaten serbest; çelişki kalkar).
- `son_anlatim` 400 harften 1200 harfe.
- Tırnaklı konuşma yasağı kalır (KOD 2 kararı): varışta konuşmayı kimin söylediği motorda bağlanmıyor; kaynaksız söz üst belgedeki S5 "tek ses" kuralını bozar.
- "Yeni kişi, eşya, çıkış, yol, ücret, para ya da görev ekleme" kuralı kalır (varış öneri şeridi değil).

`api/model_chain.py`:
- Bugün Gemini ve Haiku aynı istemi alıyor; yerel model ek olarak `LOCAL_STYLE_RULES` alıyor. Bulut için ayrı bir üslup bloğu (`CLOUD_STYLE_RULES`) eklenir: duyusal ayrıntı, cümle uzunluğu çeşitliliği, karanlık fantezi tonu, kısa cevap yerine sahneye bağlı cevap. Haiku ve Gemini farkı gerekirse sağlayıcı başına iki blok.
- Sıcaklık bu dilimde değişmez (KOD 2 kararı). 7.6 ölçümü Kadir'in bütçe onayından sonra yapılır; ölçüm gerekirse Gemini'nin serbest metin çağrıları (varış, NPC konuşması) için ayrı bir küçük iş açılır. JSON çıkaran ana anlatıcı 0.35'te kalır.

### 7.6 Ölçüm (önce ve sonra)

- Sabit tohumlu bir kasabada 20 NPC konuşması ve 10 varış: 60 harfin altındaki konuşma oranı (bugün 6/21), çıplak "bilmiyorum" sayısı (hedef 0, D-237 testi), uydurma izlerden kaçının kaydedildiği ve takip edilebildiği.
- Gerçek model çağrısı harcar: bütçe tahmini önce Kadir'e (Kadir kuralı D-262/D-263 ile aynı).

## 8. Test ve şerit açma koşulları (üst belge 4b)

1. Kırmızı testler (sahte model):
   - `mentions` içinde para ya da fiyat iddiası: kayıt açılır ama iddia boşalır; para hareket etmez.
   - Var olan yerin adı: yeni kayıt yok, söylenti var olana bağlanır.
   - 25. duyulmuş yer: en eski ziyaret edilmemiş `rumoured` yer silinir, yenisi kaydedilir; gerçekleşmiş yer silinmez; oyuncuya hata görünmez.
   - Kasaba başına 8 sınırı dolu bir yerleşimde duyulmuş yer yine kaydedilir.
   - Geri Al: duyulmuş yeri açan tur geri alınınca yer ve söylenti kalkar.
   - Söylenti görev ya da ödül açmaz.
2. Sabit tohumlu yolculuk senaryosu (yeni numara, `api/tests/journeys/report.py` tablosuna türüyle): NPC A bir yer söyler → NPC B'ye sorulur, bilir → oyuncu gider, varır → kaydet-yükle → Geri Al: her adımda kayıt tutarlı.
3. Güvenlik ağı testi: model `mentions` doldurmaz ama adı söyler → oyuncu gider → yer yaratılır.
4. Haiku şema testi: yeni şema Haiku dilbilgisi sınırının altında (gerçek çağrı, küçük maliyet; Kadir onayıyla).
5. Komşu set: `api.tests.test_journey_runner`, `test_journey_report`, `test_journey_schema`, `test_journeys`; ayrıca `test_town_knowledge`, `test_npc_never_bare_unknown`, `test_narration_proposal_marker`, `test_arrival_narration`, `test_model_chain`.
6. Şerit bir ayar anahtarıyla kapatılabilir (`AI_DND_RUMOUR_LANE=0`).
7. Kadir oynar ve kabul eder (oynayış kapısı).

İnceleme: yeni dünya alanları kayıt ve Geri Al'a dokunur; bağımsız Opus incelemesi.

## 9. Yapıcıya bırakılanlar

- `mentions` tek nesne mi dizi mi (Haiku sınırına göre).
- `heard_rumours` listesinin üst sınırı ve en eskiyi atma kuralı.
- `CLOUD_STYLE_RULES` metni (Kadir'in "sinematik anlatım" isteğine ve 18+ karanlık fantezi kapsamına uygun; yumuşatma yok).
- 7.1'deki sayılar (10 madde, 1500 bayt, 120 harf) ölçümle değişebilir; değişiklik ledger'a Ruling olarak yazılır.

## 10. Riskler

- Dünya şişer ya da çelişir: kopya denetimi (ad çözümü), yerleşim başına 24 sınırı, ölçü olarak reddedilen öneri oranı.
- Yerel Gemma alanı doldurmayabilir: güvenlik ağı (7.3) bunu karşılar.
- Daha uzun NPC bilgisi yerel modelin bağlamını zorlayabilir: ölçümde yerel model ayrı ölçülür.

## 11. Doğrulanmayanlar

- Haiku'nun genişleyen NPC şemasını kabul edip etmediği (denenmedi).
- "eski mahzen" gibi serbest adların bugün `PLACE_KINDS` köklerine takılıp takılmadığı.
- NPC konuşmasındaki `commitment` ve `front` alanlarının nerede tüketildiği (bu tasarım onlara dokunmuyor).
