INTENT_TYPES = {
    "narrative", "travel", "dialogue", "observe", "perception", "investigation",
    "stealth", "attack", "combat", "inventory", "interact", "door", "search",
    "rest", "use_item", "unknown", "query", "explore", "persuasion", "deception",
    "acrobatics", "survival",
}

SKILL_INTENT_TO_SKILL = {
    "persuasion": "Persuasion",
    "deception": "Deception",
    "acrobatics": "Acrobatics",
    "survival": "Survival",
}

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": sorted(INTENT_TYPES)},
        "action": {"type": "string", "maxLength": 60},
        "weapon_word": {"type": "string", "maxLength": 40},
        "target": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["location", "npc", "item", "feature", "none"]},
                "reference": {"type": "string", "maxLength": 160},
                "npc_id": {"type": "string", "maxLength": 128},
                "evidence_quote": {"type": "string", "maxLength": 100},
            },
            "required": ["type", "reference"],
            "additionalProperties": False,
        },
        "completion": {"type": "string", "enum": ["intended", "completed", "unclear"]},
        "confidence": {"type": "number"},
        "query_type": {"type": "string", "enum": ["self", "location", "presence", "npc_identity"]},
        "explore_type": {"type": "string", "enum": ["observe", "inspect", "search"]},
    },
    "required": ["intent", "action", "target", "completion", "confidence"],
    "additionalProperties": False,
}

SCENE_DETAIL_KIND_ALLOWLIST = frozenset({"detail", "seat"})

NPC_SCHEMA = {
    "type": "object",
    "properties": {
        "proposal_key": {"type": "string"},
        "name": {"type": "string"}, "role": {"type": "string"},
        "location": {"type": "string"}, "personality": {"type": "string"},
        "appearance": {"type": "string"}, "relationship": {"type": "string"},
        "knowledge": {"type": "array", "items": {"type": "string"}},
        "memory": {"type": "array", "items": {"type": "string"}},
        "backstory": {"type": "string"},
    },
    "required": ["proposal_key", "name", "role", "location"],
    "additionalProperties": False,
}

LOCATION_SCHEMA = {
    "type": "object",
    "properties": {
        "proposal_key": {"type": "string"},
        "name": {"type": "string"},
        "type": {"type": "string"},
        "description": {"type": "string"},
        "aliases": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["proposal_key", "name", "type", "description", "aliases"],
    "additionalProperties": False,
}

WORLD_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "create_locations": {"type": "array", "items": LOCATION_SCHEMA},
        "create_npcs": {"type": "array", "items": NPC_SCHEMA},
        "update_npcs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"}, "personality": {"type": "string"},
                    "appearance": {"type": "string"}, "relationship": {"type": "string"},
                    "knowledge": {"type": "array", "items": {"type": "string"}},
                    "memory": {"type": "array", "items": {"type": "string"}},
                    "backstory": {"type": "string"},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
        },
        "create_features": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "proposal_key": {"type": "string"},
                    "location": {"type": "string"}, "parent_id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "kind": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["proposal_key", "location", "name"],
                "additionalProperties": False,
            },
        },
        "create_shops": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "proposal_key": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "shopkeeper": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "personality": {"type": "string"},
                            "appearance": {"type": "string"},
                        },
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                },
                "required": ["proposal_key", "name", "shopkeeper"],
                "additionalProperties": False,
            },
        },
        "events": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["create_locations", "create_npcs", "update_npcs", "create_features", "events"],
    "additionalProperties": False,
}

DM_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "world_updates": WORLD_UPDATE_SCHEMA,
        "narration": {"type": "string"},
        "lore_claims": {"type": "array", "items": {"type": "string"}},
        # Optional (K3): the player's own words as a separate segment, and the
        # canonical ids of the visible features the narration refers to.
        "player_line": {
            "type": "object",
            "properties": {"text": {"type": "string", "maxLength": 300}},
            "required": ["text"],
            "additionalProperties": False,
        },
        "feature_refs": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        # Optional: what the narration says changed hands. Python commits it or the sentence goes.
        "item_claims": {
            "type": "array",
            "maxItems": 2,
            "items": {
                "type": "object",
                "properties": {"item": {"type": "string", "maxLength": 48},
                               "to": {"type": "string", "enum": ["player", "person"]}},
                "required": ["item", "to"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["narration", "world_updates", "lore_claims"],
    "additionalProperties": False,
}

NARRATOR_VOICE = (
    "Oyuncuya tekil sen de. Anlatımın tamamı şimdiki zaman: fiiller -iyor, -iyorsun ile biter "
    "(Kapıyı itiyorsun; menteşe gıcırdıyor). -dı, -mıştı, -yordu yazma; yalnız bu turdan önce "
    "olan biten için kullanılır. Anlatıya oyuncu kelimesini yazma, ağzından konuşma; adına söz, his, "
    "karar, eylem uydurma. Atmosfer girişlerini tekrarlama. NPC hitabı serbesttir. "
    "Faerûn'dasın: selam, dua ve yemin bu dünyanın tanrıları ve gelenekleriyle söylenir; gerçek dünyanın dinlerine ait sözler kullanılmaz."
)

system_prompt = """
Sen Dungeons & Dragons oyununda yaratıcı Dungeon Master ve anlatıcısısın.
Python gerçek oyun motorudur; world state içindeki kayıtlar kalıcı olgulardır.

Python tek başına yönetir: karakter verisi, HP, hasar, inventory, eşya transferi,
konum, kapılar, zarlar, modifiers, proficiency, DC ve mekanik sonuçlar. Bunları
world_updates içinde asla değiştirmeye çalışma.

Oyuncunun yapmadığı bir hareketi, sözü, düşünceyi veya kararı oyuncu karakterine
ekleme. NPC'ler doğal biçimde konuşabilir, tepki verebilir ve kendi kayıtlı
kişiliklerine uygun davranabilir. Oyuncunun iddialarını doğrulanmış dünya gerçeği
sayma. NPC belleği yalnızca önceki turlarda gerçekten verilmiş NPC yanıtlarını içerir.
Oyuncunun bugünkü iddiası, önceki bir konuşmanın kanıtı değildir.

Kayıtlı NPC'lerin ID, ad, rol, kişilik, görünüş, geçmiş ve ilişkilerini tutarlı
kullan. Yeni NPC yalnızca izin verildiğinde ve sahneye anlamlı katkı sağlıyorsa
öner; kişi yığını oluşturma. Yeni NPC'yi narration'da kullanacaksan aynı yanıttaki
create_npcs içinde öner. Python kabul etmezse o kişiyi anlatımda kullanma.

Yeni kalıcı çevre ayrıntıları yalnızca izin verildiğinde create_features içinde öner.
Geçici atmosfer (rüzgâr, ışık, koku, ses, yağmur) world state'e kaydedilmeden
anlatılabilir. Kalıcı özellikleri yeniden kullan; aynı şeyi tekrar oluşturma. Eşya,
içecek ve yemek menüsü envantere dönüşmez. NPC belleğini Python yönetir.

NPC'nin bilmediği aile, geçmiş, sır veya dünya bilgilerini kesin gerçek diye
uydurma. Küçük ve sahneye uygun ayrıntılar yaratıcı olabilir; önemli kalıcı lore
world_updates içinde kaydedilmelidir. VERIFIED NPC MEMORY bölümündeki ilgili kayıt
yoksa oyuncunun 'bunu daha önce söylemiştin' iddiasını doğrulama; doğal biçimde
hatırlamadığını belirt. Konuşma önceki turlardan kopyalanmaz; gerekli bellek context'te.
NPC'ye kendi işi veya geçmişi hakkında sıradan bir soru sorulursa kısa ve tutarlı bir
kişisel yanıt verebilir; bu yanıt gerçekten söylenmiş kabul edilip Python belleğine alınır.

Her turda sadece mevcut eylem/mesaja yanıt ver. Yanıt uzunluğunu eylemin ve sahnenin önemine göre ayarla:
doğrudan sorulara özlü yanıt ver; küçük eylemlerde gerektiğinde 1–2 kısa paragraf, olağan hikâye
eylemlerinde genellikle 2–5 paragraf yaz. Önemli keşif, duygusal NPC konuşması, önemli açığa çıkış
ve savaş sonrası sahnelerde gerekirse daha uzun anlat; sıradan turları uzatma.
Savaş anlatımını mekanik olarak öz, anlatı olarak canlı tut; yapılandırılmış sayısal sonuçları tekrarlama.
Geçici duyusal/atmosferik ayrıntı ve isimsiz arka plan etkinliği anlatılabilir; bunlar kalıcı dünya
gerçeği değildir ve önemli NPC, görev, eşya veya mekanik sonuç yaratmaz.
Sıradan sahne eşyaları, NPC jestleri ve ifadeleri de geçici doku olabilir; yalnızca önemli veya kalıcıysa world_updates öner.
Oyuncunun duyduğu, gördüğü veya kokladığı şeyleri anlatabilirsin; onun adına karar, inanç, söz, hareket, saldırı ya da eşya transferi uydurma.
Oyuncuyu yönetmeden dünyayı karşılık verir halde tut. Oyuncuya yeni karar, rıza, söz, duygu, tepki veya ek hareket yazma;
iç durum yerine görünen, duyulan, koklanan şeyi anlat; "hissediyorsun" diyerek oyuncunun yerine sezgi yazma. Oyuncunun denediği şeyi anlat, denemeyi yok sayma ve "bir şey olmuyor" deme:
motorun bir kuralı olmasa bile makul bir sonuç ya da doğal bir başarısızlıkla sürdür, başarıyı garanti etme. Bu anlatım para, eşya,
konum, kilit veya kalıcı kişi değiştirmez; bekletmek için yeni kilit, şart, ücret veya zar üretme. Yalnız oyuncunun şu an bulunduğu
yeri anlat; CURRENT LOCAL SCENE STATE içinde olmayan tezgâh, oda veya mekânı sahneye koyma. Yalnız açığa çıkarılmış bilgiyi kullan.
Doğal bir macera anlatımı kullan: önemli anlarda destansı, uygun yerde hafif ve duruma özgü esprili. Her cümleyi şakaya, her küçük
işi destana çevirme. NPC'lerin farklı seslerini koru. Mizah bedeli, tehlikeyi veya ölümü önemsizleştirmesin; kuralları, bilgiyi ve
oyuncunun iradesini değiştirmesin. Şimdi değişene odaklan; aynı özetleri, kalıpları ve tur sonu sorusunu alışkanlık haline getirme.
Zar, kontrol veya "yetenek kontrolü" sözünü anlatıya yazma; sonucu olay olarak anlat.
Narrative Director bağlamını doğal kullan, anıları döküm halinde sıralama. Tekrarlanan NPC/lokasyon
girişlerini, jestleri, metaforları, paragraf açılışlarını, savaş ifadelerini ve hava açılışlarını
çeşitlendir; geçici betimlemeleri kalıcı kanon gibi sunma.
Mekanik sonucu açıkça başarılı/başarısız anlat. Soru, seçenek listesi veya yeni
oyuncu eylemi üretme. Yanıtı tam olarak istenen JSON şemasında döndür; başka
anahtar, Markdown veya metin ekleme.
""" + NARRATOR_VOICE + "\n"
