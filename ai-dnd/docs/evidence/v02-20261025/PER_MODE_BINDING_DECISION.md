# Faz 3 Karar Belgesi: Kip Başına Bağlama

Durum: **uygulandı.** Nesne iddiası yarısı v0.2'de; K3 onaylandı ("bunları da onaylıyorum") ve `DM_RESPONSE_SCHEMA`'ya isteğe bağlı `player_line` ve `feature_refs` eklendi (zorunlu alanlar aynı). Kanıt: `api/tests/test_scene_representation_contract.py` (8 test). Sınır: istem metni modele bu alanları henüz üretmesini söylemiyor; alanlar yalnız geldiğinde doğrulanır. Aşağıdaki "Karar gereken" bölümü tarihsel kayıttır.
Kaynak: `v0.1` üstü, dal `cursor/v02-consistent-world-20261025`.

## Bu belge neyi sabitliyor

Aşağıdaki tablo, hangi noktada kim karar veriyor ve test nerede. "Varsayılan" kip, `free_v1` olmayan mevcut anlatım yoludur.

| Rol | Ham şema | Doğrulama sahibi | Yetkili oluşturma | Ekranda gösterim | Geçmişe kabul |
|---|---|---|---|---|---|
| Anlatıcı dokusu | `narration` + `world_updates` + `lore_claims` | `game._narrate_resolved_turn`, `finalize_narration`, `_unregistered_persistent_object_claim` (`game.py` ~8552) | yok (doku dünya yazmaz) | yalnız doğrulanmış metin, ret olursa deterministik yedek | `campaign_history.narration`, gösterilenle aynı |
| İddia edilen nesne | `world_updates.create_features[]` | `validate_world_updates` (`game.py` ~5135), `create_local_feature` (~3441) | `create_local_feature`, yalnız mevcut konumda, 16 sınırı, görünürlük süzgeci | kayıtlıysa anlatılabilir | feature kimliği ile |
| NPC konuşması | `spoken_text`, `stage_direction` | `dialogue_runtime.validate_reply/prepare_turn` | NPC dünya yazamaz | atıflı konuşma | `local_dialogue.remember_speech_exchange` (atıflı, olgu değil) |
| Oyuncu iddiası | oyuncu metni | `is_player_world_assertion` | yok | atıflı söz | `history_authority = attributed_speech_not_fact` |
| Mekanik olgu | Python | oyun motoru | yalnız motor | motor metni | motor durumu |

## Bu fazda bulunan ve düzeltilen kusur

**Gizli özellik, ad çakışmasında "mevcut kayıt" olarak geri veriliyordu.** `create_local_feature` yalnızca `parent_id` varken gizli çakışmayı reddediyordu (`_legacy_hidden_feature_name_collision`). Üst düzey öneri gizli bir özellikle aynı adı taşırsa gizli kaydı geri döndürüyordu. Çağıranlar bunu kayıtlı nesne sayıp gizli adın anlatıma geçmesine izin verebilirdi.
Düzeltme (`game.py`): mevcut kayıt yalnızca `living_world.visible_features` içindeyse yeniden kullanılır, değilse `None`. Test: `test_hidden_feature_collision_does_not_disclose_name`.

## Testle sabitlenenler (`test_scene_claim_contract`, 8 test)

- Reddedilen kalıcı nesne iddiası ne ekranda ne `campaign_history` içinde ne asistan mesajlarında (`test_rejected_claim_never_enters_display_or_history`).
- Zararsız doku (keman sesi, çocuk) korunuyor.
- Oyuncunun "kral kaleyi bana verdi" cümlesi envanter, özellik veya paket olgusu yaratmıyor, atıflı söz olarak kalıyor.
- Aynı adlı öneri yeni kimlik üretmiyor, 16 sınırı dolduğunda öneri reddediliyor.
- İki farklı oyuncu mesajı aynı NPC için farklı `player_message` paketine ulaşıyor.

## Kapsam dışı kalanlar ve nedeni

1. **`free_v1` kipi:** bu belge yalnız varsayılan (legacy) kipi sabitler. `free_v1` için aynı ret/geçmiş testi ayrı bir kampanya kurulumu ister, yazılmadı.
2. **Devredilen şaka, sağlanan alıntı, saldırı makbuzu eşleşmesi** (`test_delegated_joke_has_player_line_and_specific_npc_reaction` vb.): mevcut şema oyuncu sözünü ve anlatıcı bölümünü ayrı alan olarak taşımıyor. Plan bunu yeni alan olarak tanımlıyor ve "onaylı sınırı aşarsa kullanıcıya dön" diyor.
3. **Noktalı büyük İ:** `"İ".casefold()` iki karakter üretir, bu yüzden `KİL TESTİ` ile `Kil testi` farklı özellik sayılır. Sıradan büyük/küçük harf farkı çalışıyor. Düzeltme ayrı karar ister (Türkçe normalleştirme sahibi `living_world.normalize_text`).
4. **A–G, kesme sınırı (240/400):** model paketine giden gerçek içeriği denetleyen test yazılmadı. Büyük bellek sistemi eklenmiyor.

## Karar gereken (K3)

Oyuncu sözü ve anlatıcı bölümü için üretim şemasına **yeni alan** eklensin mi? Önerilen tek dar seçenek:

```json
{
  "narration": "string",
  "player_line": {"text": "string"},
  "feature_refs": ["feature_001"],
  "world_updates": {},
  "lore_claims": []
}
```

- Geriye uyum: eksik `player_line` ve `feature_refs` mevcut davranışa eşit, ret yok.
- Geçersiz `feature_refs` (var olmayan, gizli veya başka konum): alan yok sayılır, anlatım deterministik yedeğe düşer, model çağrı sayısı değişmez.
- Bu seçenek onaylanmadan şema değişmez. Reddedilirse yukarıdaki 2. madde "kapsam dışı" olarak kalır.
