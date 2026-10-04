# Monster Combat: canlı veri bağlantısı için gerekli sözleşme

## Durum

İncelenen üretim kodunda Monster Combat'ın hedef algısı, taktik mesafe ve
doğrulanmış rota girdilerini üreten bir kaynak bulunamadı. Mevcut tüketiciler
vardır; testlerin bu girdileri doğrudan doldurması bir üretim kaynağı değildir.
Bu belge bir uygulama veya onaylanmış karşılaşma tanımı değildir.

Bu nedenle gerçek üretim kaynağından beslenen hedef seçimi, legal
yürüyüş/kaçış, kaynak tüketimi ve save/resume replay zinciri henüz HTTP
üzerinden kanıtlanamaz.

### Hardening sonrası yeniden denetim — 2026-10-04

Denetlenen checkout: `main`,
`79b61ff917be462296b048c432330bdd96d15a3c`.
Bu denetim önceki eksik-owner sonucunu varsaymak yerine güncel üretim
yollarını yeniden incelemiştir.

- `api.session_manager.SessionManager.create_campaign`, gerçek session
  factory ve canonical başlangıç konumu akışını kullanır.
- `living_world.materialize_scene`, mevcut `game.create_npc_from_ai`
  girişinden canonical NPC oluşturur. NPC kimliği ve `location` alanı
  vardır; seçilmiş MM statblok eşlemesi üretmez.
- `living_world.set_player_position` yalnızca yer/seated/standing kaydı
  üretir. `scheduled_events.visible_npcs` oyuncuya sunulan bilgiyi filtreler.
  Bunlardan taktik mesafe veya NPC yönlü görüşü çıkarılamaz.
- `action_economy.move` movement bütçesini tüketir; mesafe çiftleri veya
  rota uç noktaları üretmez. `weapon_attack.push` ise ancak mevcut
  canonical mesafe ve doğrulanmış koridor girdisini kullanarak yer
  değiştirmeyi çözer; eksik geometri için başlangıç üreticisi değildir.
- Güncel üretim yollarında `monster_perception`, `monster_routes` veya
  seçilmiş `monster_stat_block` girdilerini oluşturan kaynak bulunmadı.
  Frontend/request movement mesafesi de canonical NPC geometry kaynağı
  değildir.

Sonuç: gerekli üretim sahipleri eksik olduğundan canlı HTTP tamamlanma
koşulu **NO-GO** durumundadır. Bu belge kaynaklar yaratmaz ve fixture
verisini production bağlantısı olarak kabul etmez.

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
- Bu küme combat içindeki bütün canonical hostile katılımcıları içermelidir.
  Hostile'ın rotadan çıkarılması veya mesafesinin bilinmemesi güvenli
  hareket kanıtı değildir; hardening sonrası tüketici böyle bir rotayı
  legal listesine almaz.
- Kullanılıyorsa `movement_intent`.

Başlangıç mesafeleri canonical çift mesafeleriyle aynı olmalıdır.
Hız, Prone, difficult terrain, Frightened ve Action Economy kontrolleri
mevcut sahiplerde kalır. Reaction/OA sahibi olmayan bir sınır geçişi
başarılı kaçış olarak varsayılamaz. Hareket tek başına combat üyeliğini
bitirmez.

Burada yeni geometry veya pathfinding önerilmemektedir. Önceden mevcut,
doğrulanabilir ve onaylanmış bir konum/rota kaynağı gerekir; kaynağın
bulunmaması tüketicinin varsayım üretmesiyle giderilemez.

## Eksik sahipler ve en küçük sonraki kapsam

| MISSING OWNER | WHY REQUIRED | CURRENT CONSUMER | MINIMUM DATA CONTRACT | SMALLEST FUTURE IMPLEMENTATION |
|---|---|---|---|---|
| Seçilmiş MM→NPC eşleme sahibi | NPC varsayılanları MM doğrulaması değildir | `monster_capabilities.capabilities` | Açık NPC ID→statblok ID eşlemesi; MM baskı/sayfa kanıtı; doğrulanmış mekanik alanlar ve desteklenen owner'lar | Onaylanan tek karşılaşma için sınırlı, kaynak doğrulanmış statblok bağlantısı; isim/rol çıkarımı ve full importer yok |
| Taktik mesafe ve yönlü algı sahibi | Ortak location, feet veya görüş kanıtlamaz | `weapon_attack.pair`, `monster_perception.snapshot` | Canonical aktör/hedef ID'leri; doğrulanmış mesafe; yönlü görünürlük/sense kanıtı; kaynağın üretim ve geçersizleşme olayları | Owner tarafından onaylanan tek sahnenin konum/görüş verisini mevcut tüketicilere sağlayan sınırlı üretim girişi |
| Doğrulanmış yürüyüş/rota sahibi | Movement bütçesi rota güvenliği veya OA kanıtlamaz | `action_economy.monster_routes` | Bilinen/açık rota; gerçek maliyet; canonical başlangıç/bitiş mesafeleri; bütün hostile katılımcılar; mevcut terrain ve action sınırları | Aynı onaylı sahnenin gerçek rotalarını mevcut arayüze sağlayan sınırlı üretim girişi; generic pathfinding yok |

Bu sonraki kapsamlar uygulanmış değildir. Konum, görüş ve rota verilerinin
hangi gerçek kaynakta tutulacağı ve hangi canonical olaylarla değişeceği
owner tarafından onaylanmadan yeni üretici kurulamaz. HTTP karşılaşma
kabulü ancak bu kaynaklar ve açık statblok seçimi sağlandıktan sonra
yapılabilir.

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