# Diyalog Sınırı Sözleşmeleri: Tasarım

Tarih: 2026-10-25. Dal: `cursor/v02-consistent-world-20261025` (v0.2c). Onay: kullanıcı, "2. ile başla ve açık sınırları kapat" ve tasarım onayı "evet".

## Amaç

v0.2b'de yazılmayan üç Faz 5 diyalog testini yazmak ve bu sırada bulunan tek gerçek kusuru düzeltmek. Kapsam dışı: olay tetikleyicisi, istem metni, `free_v1`, v0.1 sahne sınırları (kullanıcı yalnız bu parçayı seçti).

## Kararlar (kullanıcı)

1. Gizli kelime testi **gizli NPC kimliği** üzerinedir (`HIDDEN_NPC_IDENTITY_DISCLOSURE`).
2. Dünyayla çelişen NPC sözü **yalnız atıf** olarak kalır: işaret yok, yalan çıkarımı yok, dünya değişmez. Yalan yalnız kayıtlı motif ve kanıtla açılır (`deception_context`).
3. Test derinliği: sahip modüllerde birim testi, ayrıca gizli kimlik için gerçek ASGI yolunda tek uçtan uca test.
4. Düzeltme **dar**: yalnız ay adı kalıbı. Rol adları ve diğer homograflar kapsam dışı.

## Ölçülmüş kusur

Gizli adı `Kasım` olan NPC varken `_narration_safety_decision`:

| Metin | Bugün | Olması gereken |
|---|---|---|
| Kasım ayı soğuk geçti, rüzgar sertleşiyor. | reddedilir (yanlış alarm) | kabul |
| Kasım ayında hava soğur. | reddedilir (yanlış alarm) | kabul |
| Kasım gülümsüyor. | reddedilir | reddedilir |
| Ben Kasım, demirciyim. | reddedilir | reddedilir |

## Tasarım

### Birim testleri (sahip modüller)

- `npc_statements.record` ve `claim_support`: NPC sözü dünyayla çelişse de ifade defterinde NPC'ye ait kalır. Oyuncunun "söylemiştin" iddiası NPC'nin gerçek alıntısıyla desteklenir. Dünya (`features`, `feature_marks`, `surface_items`, `flags`, `locations`, `inventory`, `relationships`) `npc_statements` dışında birebir aynıdır.
- `dialogue_runtime.deception_context`: çelişen ifade kaydedildikten sonra `None` döner. Kanıtsız motifin `remaining_uses` değeri harcanmaz. Konuşma turu yeni motif üretmez.

### Ürün düzeltmesi (tek)

`npc_speech_boundary.mask_calendar_month_name(text, identity)`: gizli kimlik on iki Türkçe ay adından biriyse ve hemen ardından ay kalıbı gelirse (`ayı`, `ayında`, `ayının`, `ayına`, `ayından`, `aylarında`) o geçiş kimlik taramasında boşlukla maskelenir. Ayı olmayan her geçiş (çıplak ad, "Ben Kasım", "Kasım gülümsüyor") maskelenmez ve reddedilmeye devam eder. Bu bir tarama görünümüdür, anlatımı değiştirmez.

`game.py::_narration_safety_decision` içinde `hidden_identity_scan_text` çağrısından sonra tek satır eklenir. `game.py` kuralı bu iş için kullanıcı tarafından önceden gevşetilmiştir.

### Uçtan uca test

Gerçek ASGI yolu, betikli model, `AI_DND_NPC_SPEECH=1`, hedef NPC `Lysa`, ikinci gizli NPC `Kasım`:

- "Kasım ayı soğuk geçti" içeren NPC yanıtı kabul edilir (`last_narration_safety['handling'] == 'accepted'`).
- Kontrol: "Kasım gülümsüyor" içeren yanıt reddedilir (`HIDDEN_NPC_IDENTITY_DISCLOSURE`) ve metin ekranda ve `campaign_history` içinde yoktur.

## Hata durumları ve riskler

- Ay kalıbı yalnız gerçek ay adlarında çalışır. Adı "… ayı" ile biten başka bir NPC maskelenmez; yeni sızıntı yolu açılmaz.
- Normalizasyon mevcut `_normalize_turkish_typos` ile aynıdır, yeni katlama kuralı yok.
- Rol adları ("demirci") ve diğer homograflar ("Yağmur yağıyor") aynen reddedilmeye devam eder. Belgelenmiş sınır.

## Doğrulama

Yeni testler önce kırmızı yazılır, düzeltme sonra gelir. Sonra: 33 kapı, `test_campaign_api` kimlik kümesi, `lr00`, `test_npc_speech_identity_inflection`, `test_npc_p2_continuity`, `test_narrative_safety_calibration`, v0.2b sahne paketleri. Hepsi baseline ile aynı olmalıdır. Bağımsız inceleme alt ajanı, sonra commit ve itme. Birleştirme yok. Canlı olay UNRESOLVED kalır.

## Test adları

`test_npc_mistake_stays_attributed_not_canon`, `test_model_contradiction_not_reclassified_as_intentional_lie`, `test_secret_word_in_harmless_smalltalk_does_not_block_speech`, ay adı kalıbı için birim testleri ve gerçek kimlik ifadesinin hâlâ reddedildiğini kanıtlayan kontrol testleri.
