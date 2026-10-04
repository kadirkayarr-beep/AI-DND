# Monster Combat: canlı veri bağlantısı için gerekli sözleşme

## Durum

İncelenen üretim kodunda Monster Combat'ın hedef algısı, taktik mesafe ve
doğrulanmış rota girdilerini üreten bir kaynak bulunamadı. Mevcut tüketiciler
vardır; testlerin bu girdileri doğrudan doldurması bir üretim kaynağı değildir.
Bu belge bir uygulama veya onaylanmış karşılaşma tanımı değildir.

Bu nedenle gerçek üretim kaynağından beslenen hedef seçimi, legal
yürüyüş/kaçış, kaynak tüketimi ve save/resume replay zinciri henüz HTTP
üzerinden kanıtlanamaz.

## Mevcut sahipler ve sınırları

| Kaynak | Gerçekten sahip olduğu bilgi | Kanıtlamadığı bilgi |
|---|---|---|
| `living_world.set_player_position` | `location_id`, standing/seated ve oturulan nesne kimliği | Feet cinsinden mesafe, koordinat, görüş hattı veya yürünebilir rota |
| `scheduled_events.visible_npcs` | Oyuncunun gözlemlemediği olayların NPC konumunu bilgi sunumundan gizleme | NPC→oyuncu görüşü, karşılıklı görünürlük veya fiziksel menzil |
| `game.create_npc_from_ai` ve `ensure_npc_combat_stats` | Canonical NPC kimliği ve mevcut Python NPC profili | Onaylanmış Monster Manual statblok eşlemesi |
| `weapon_attack.pair` | Önceden verilmiş çift mesafesi ve yönlü saldırı ortamının tüketimi | Mesafe veya görüş üretimi |
| `monster_perception.snapshot` | Önceden doğrulanmış algı verisinin sınırlandırılmış tüketimi | Yeni algı çözümlemesi veya görünürlük üretimi |
| `action_economy.monster_routes` | Önceden verilmiş rotanın bütçe ve mevcut mekaniklerle legal olup olmadığını kontrol etme | Pathfinding veya rota üretimi |

Bir konumu paylaşmak beş feet uzakta olmak anlamına gelmez. Oyuncuya
gösterilebilir olmak, NPC tarafından görülebilir olmak anlamına gelmez.
Anlatım, NPC adı, rolü veya bir başarılı genel Perception kontrolü tek başına
belirli bir hedefin mesafesini/görünürlüğünü belirlemez.

## Owner tarafından onaylanması gereken girdiler

### 1. Canonical karşılaşma ve statblok seçimi

Her seçilmiş NPC için:

- Canonical NPC kimliği ve karşılaşmanın üretim kaynağı.
- Kullanılacak MM 2024 statblokunun tam adı, baskısı ve basılı sayfası.
- NPC ile statblok arasındaki açık eşleme; isim/rol benzerliğiyle eşleme yok.
- Kaynaktan doğrulanmış AC, HP politikası, initiative verisi, hız, duyular,
  saldırılar, Multiattack kombinasyonları ve sınırlı kaynaklar.
- Her yeteneğin mevcut mekanik sahibi ve destek durumunun ayrı kaydı.

Mevcut tüketici `npc.monster_stat_block.source` ve `capabilities` alanlarını
okur. Her capability mevcut sözleşmedeki `capability_id`, `kind`,
`action_source` ve ilgili saldırı/kullanım alanlarını taşımalıdır.
Kaynak metninin mevcut olması, bir NPC için bu seçimin yapılmış olduğu
anlamına gelmez.

Spell, special ability, special movement veya başka bir effect owner yoksa
ilgili yetenek unavailable kalmalıdır. Bir fixture executor native owner
olarak kaydedilemez.

### 2. Mesafe ve yönlü algı

Onaylanmış üretim kaynağı mevcut arayüzlere şu bilgiyi sağlamalıdır:

- `world_state.attack_environment.pairs["actor_id|target_id"]`:
  gerçek, sonlu ve negatif olmayan `distance_ft`; gerçekten doğrulandığında
  yönlü `attacker_sees_target` ve mevcut saldırı ortamı alanları.
- `world_state.monster_perception[actor_id][target_id]`:
  doğrulanmış `visible` veya mevcut arayüzün desteklediği açık located/sense
  kanıtı. Sense menzili ve hedef koşulları ayrıca geçerli olmalıdır.
- Konum paylaşılacaksa mevcut `position_known`/`position` girdisi için
  aktörün gerçekten bildiği konum kanıtı.

Her bilgi için kaynak sahibi, hangi canonical olayın ürettiği ve ne zaman
geçerliliğini kaybettiği belirlenmelidir. Bunlar mevcut kodun otomatik olarak
ürettiği veya doğruladığı ek provenance alanları olarak kabul edilmemelidir;
onaylanacak kaynak sözleşmesinin gereksinimleridir.

Mesafe simetrik olabilir; görüş, cover ve diğer yönlü bilgi ters yönden
kopyalanamaz. Hidden, Invisible, Blinded, konum değişimi ve yeni combat
durumlarında eski bilgi kaynağın tanımlı kurallarıyla geçersizleştirilmelidir.

### 3. Legal yürüyüş/kaçış rotası

Onaylanmış kaynak, mevcut
`world_state.monster_routes[actor_id]` listesine en az bir gerçek rota
sağlamalıdır. Mevcut tüketicinin kullandığı alanlar:

- `route_id`, `destination`, `known`, `clear`.
- Gerçek yürüyüş maliyeti için `distance_ft`; mevcut sınırlar içinde `mode`
  ve `difficult_terrain`.
- Aynı hedef kümesini kapsayan `start_distances` ve `target_distances`.
- Kullanılıyorsa `movement_intent`.

Başlangıç mesafeleri canonical çift mesafeleriyle aynı olmalıdır.
Hız, Prone, difficult terrain, Frightened ve Action Economy kontrolleri
mevcut sahiplerde kalır. Reaction/OA sahibi olmayan bir sınır geçişi
başarılı kaçış olarak varsayılamaz. Hareket tek başına combat üyeliğini
bitirmez.

Burada yeni geometry veya pathfinding önerilmemektedir. Önceden mevcut,
doğrulanabilir ve onaylanmış bir konum/rota kaynağı gerekir; kaynağın
bulunmaması tüketicinin varsayım üretmesiyle giderilemez.

## HTTP tamamlanma kanıtı

Veri kaynağı ve seçilmiş MM→NPC eşlemesi sağlandıktan sonra:

1. Karşılaşma normal üretim oluşturma yoluyla oluşur; test endpoint öncesinde
   mesafe/algı/rota/statblok sözlüklerini doğrudan doldurmaz.
2. HTTP turu yalnızca kanıtlanmış hedefi seçer.
3. Onaylı rota üzerinden legal yürüyüş veya kaçış, mesafeyi ve movement/action
   kaynağını doğru değiştirir.
4. Aynı HTTP action receipt tekrarlandığında RNG, hareket, hasar ve kaynaklar
   yeniden tüketilmez.
5. Save/resume sonrası aynı receipt sonucu korunur; tamamlanmış çocuk
   eylemler yeniden uygulanmaz.
6. Native mekanik sahibiyle çalışan sonuçlar ve fixture executor ile
   doğrulanan sözleşmeler ayrı raporlanır.

## Değişmeyen kapsam

Death, Spell, geometry/pathfinding, Persistence ve UI mimarisi kurulmaz.
Ölüm sistemi çalışması başlatılmaz. Önceki fazlar yeniden tasarlanmaz.
Merge, push, publish veya reset yapılmaz.