# NPC'nin söylediği adlı mekâna seyahat — dar devir notu

## Kapsam

- Taban: `da2b4cf1ee7d670de7e751bd96c6f69383270ca3`
- Ayrı dal: `investigation/npc-named-place-travel-20261019`
- PR21 tabanı ve mevcut iki kırmızı regresyon korunarak aynı taban üzerinde ayrı dalda düzeltildi.
- `PLACE_NOUNS` listesine örnek mekân adları ya da “Camhanesi” eklenmedi.

## Çalıştırılan kanıt

İki sözleşme testi, `npc_statements.record()` ile kaydedilmiş sözlerden hareket ediyor. Ayrıca ASGI üzerinden gerçek kampanya API akışında sahte model önce NPC yanıtı üretiyor; API bu yanıttan atıflı yer referansı oluşturuyor, oyuncunun seyahat eylemini çalıştırıyor ve aynı `action_id` tekrarında cevabı tekrar oynatıyor. Bu, canlı model kabulü değildir.

```text
uv run --frozen --no-sync python -m unittest -v \
  api.tests.test_lr00_grounded_human.HumanP6Regressions.test_marek_said_named_camhouse_can_be_reached_by_natural_go_phrase \
  api.tests.test_lr00_grounded_human.HumanP6Regressions.test_unspoken_player_claim_does_not_create_a_named_npc_place \
  api.tests.test_lr00_grounded_human.HumanP6Regressions.test_negative_travel_to_a_spoken_place_does_not_materialize_or_move \
  api.tests.test_lr00_grounded_human.HumanP6Regressions.test_two_spoken_camhouse_names_materialize_as_distinct_city_places \
  api.tests.test_experimental_npc_dialogue.ExperimentalNpcDialogueTests.test_api_npc_reply_records_unknown_place_and_survives_save_resume
```

Sonuç: `Ran 5 tests ... OK`. Kapsam:

- NPC'nin API yanıtından tam adı ve `said_by`/alıntı kanıtı olan referans üretimi
- “Marek'in söylediği … yere gidiyorum” için API seyahati; sonuç `completed`
- Aynı eylem kimliğiyle replay; aynı yanıt, yeni konum yok
- Kaydetme ve yeni uygulama/manager ile `resume`; yer adı ve atfı korunuyor
- İkinci kampanyada ilk kampanyanın referansı yok
- Oyuncu iddiası tek başına konuşma kanıtı oluşturmuyor
- Olumsuz seyahat isteği konum veya mekân üretmiyor
- Farklı iki tam ad ayrı referans/konum kimliklerinde kalıyor

İlk kırmızı test “Marek'in söylediği” ifadesi yüzünden `dialogue/proposal_rejected` alıyordu; ayrı konuşma cümlesindeki birinci tekil “gidiyorum” eylemi raporlanan sözden ayırt edilmediği için adım eleniyordu. İkinci kırmızı testte `_named_places()` bilinmeyen yer başlığını çıkaramıyordu. İki sorun da şimdi hedefli düzeltildi.

## İlk kopuş ve sözleşme notu

Atıflı NPC sözünden en az üç kelimelik büyük-harfli tam özel ad, yeni başlık türü listesi gerektirmeden genel yer referansı olarak çıkarılıyor. Referans yalnız kaydedilmiş NPC alıntısına bağlanıyor; bu çıkarım mekânı gezilmeden dünya konumuna dönüştürmüyor. Seyahat adımı `reported` filtresinden ancak aktarılan söyleme ek olarak oyuncunun açık birinci tekil “go” eylemi varsa geçiyor.

Bu istek mevcut sabit başlık sözleşmesini genişletiyor. Genişletme yalnız daha önce gerçekten kaydedilmiş NPC sözüne dayanmalı; oyuncunun cümlesi tek başına NPC kanıtı veya dünya gerçeği sayılmamalı. İki ayrı tam ad iki ayrı referans/konum kimliğinde kalmalı; yeni yerler yalnız kampanyaya özgü kurgusal yerler olarak üretilmeli.

## En küçük düzeltme planı

1. Kaydedilmiş NPC sözünden bilinmeyen tam özel adı genel, kampanya kapsamlı referans olarak kaydet; oyuncu iddiasından kayıt üretme.
2. Aktarılan söze eşlik eden açık birinci tekil seyahati diyalog sayma; aynı referansı materyalize et, tekrar ziyarette ikinci yer yaratma.

## Kısa oyun dökümü (kontrollü sahte model)

```text
Oyuncu: Bana şehirde gidilecek başka bir yer öner.
Marek: Mavi Fener Camhanesi doğu kapısının yanında, şehirde bilinen bir yerdir.
Oyuncu: Marek'in söylediği Mavi Fener Camhanesi'ne gidiyorum.
Motor: Seyahat tamamlandı; Mavi Fener Camhanesi Kapısı kapalı ve kilitli, karakter mekânın önünde kalıyor.
```

Canlı Ollama listeleme kontrolü HTTP 502 verdi; bu nedenle bu dalda canlı model kabulü iddia edilmiyor.

## Önceki defter kontrolü — korunan kanıt

Önceki izole FastAPI ASGI HTTP kontrolünde sahte istemciyle oluşturulmuş `Yıpranmış Defter` için ayrı `Yıpranmış Defteri inceliyorum.` isteği `200` döndü. Oyun sonucu `action=inspect`, `status=observed`, `success=true`, `target_id=feature_001` idi; bu ID oluşturulan özelliğin ID'siyle eşleşti. Anlatı ad ve açıklamayı içerdi; inceleme hamlesi `model_calls=0` kullandı. Bu istek canlı Uvicorn servisine değil, ASGI test transport'una gönderilmişti.

O probe için ayrı komut/çıktı dosyası oluşturulmadı; asıl terminal çıktısı önceki oturumun araç yanıtındadır. Buradaki kısa kayıt, sonucu oturum dışına taşımak içindir.
