# Public API değerlendirmesi (2026-10-31)

Tüm kaynaklara erişim tarihi: 2026-10-31. Hiçbir servise kayıt olunmadı, anahtar alınmadı, medya dosyası veya veri dökümü indirilmedi, hiçbir şey entegre edilmedi. Kod okuması `AI-DND-c-merge` üzerinde yalnız okuma ile yapıldı (HEAD `2d140cc`). O worktree okuma sırasında değişiyordu, yani bu tablo anlık görüntüdür. Bu belge kabul iddiası taşımaz.

**Etiketler:** [D] resmi sayfadan veya canlı anonim GET çağrısından doğrulandı. [İ] yalnız ikincil kaynak. [Ç] benim çıkarımım. [O] okunamadı veya sayfada bilgi yok. Çoğu sayfa özet aracıyla okundu, hukuki metinlerin son hali asıl sayfadan teyit edilmeli.

Canlı kontrol: Open5e, dnd5eapi ve GitHub'ın anahtarsız uçlarına küçük JSON GET çağrıları yapıldı. Sonuçlar diske yazılmadı.

## 1. Kısa sonuç

- **Şu anki adıma doğrudan yarayan API yok.** Amaç olan "AI'ın oyunda istediğimiz gibi oynaması" dış veriyle değil, şehir bilgisi ve dünya işleriyle ilerliyor. Bunlar zaten repoda.
- **Tek küçük "şimdi" adayı:** Vikisözlük dökümünü bir kez alıp yerel Türkçe kelime listesi yapmak. Yalnız geliştirme ölçümü içindir, oyunda engelleme için değil. Bunun da önce sahibin kararına ihtiyacı var (bölüm 6).
- **Sonra işe yarayacak en büyük boşluk canavar verisi.** Motor var, ama kodda görülen stat block'lar az. SRD 5.2 anlık görüntüsü bunu kapatır.
- **Büyü açıklaması indirmek büyüyü oynatmaz.** Repoda 391 büyünün metaverisi var, ama çözücü yalnız 4 büyü için var. Eksik olan veri değil, motor.

## 2. Karar tablosu

| Aday | Ne için | Karar | Oyun sırasında servis? | AI'a etkisi |
|---|---|---|---|---|
| Wiktionary (Vikisözlük dökümü) | Türkçe kelime listesi | **Şimdi, küçük ve yalnız ölçüm için** | Hayır | Dolaylı: hatalı kelimeyi ölçer |
| Open5e `srd-2024` | Canavar, büyü metni | Sonra (adım 3 sonrası) | Hayır, tek seferlik görüntü | Var, savaş ve anlatı bağlamı |
| dnd5eapi `/api/2024` | Open5e çapraz kontrolü | Sonra | Hayır | Dolaylı |
| Freesound | Ortam sesi | Sonra (adım 8) | Hayır, elle seçim | Yok, atmosfer |
| Met Museum | Yer, eşya görseli | Sonra (adım 8) | Hayır | Yok |
| Iconify + Game Icons | Durum, eşya ikonu | Sonra (adım 8) | Hayır, derleme anında | Yok |
| anaislalovi/dnd5e-icons | Durum ikonu | Sonra (adım 8) | Hayır | Yok |
| Openverse | Medya arama aracı | Sonra, yalnız elle keşif | Hayır | Yok |
| Pixabay | Görsel | Sonra, yalnız elle seçim | Hayır | Yok |
| DiceBear | NPC yer tutucu yüz | Sonra, isteğe bağlı | Hayır | Yok |
| Hugging Face | Model, veri seti indirme | Sonra, gerekirse | Hayır | Olabilir, çıkarım servisi için değil |
| Groq | Yedek LLM, Whisper | Sonra, yalnız kısa karşılaştırma | Evet | Ana sağlayıcı olamaz |
| LibreTranslate | Yerel çeviri | Atla | Hayır | Gerek yok |
| Datamuse | Kelime yardımı | Atla | Evet | Türkçe yok |
| Jina AI | Embedding, Reader | Atla | Evet | Şimdilik gerek yok |
| Icons8 | İkon | Atla | - | Yok |
| Pexels | Foto | Atla | - | Yok |
| Unsplash | Foto | Atla | **Evet, hotlink zorunlu** | Yok |
| Spotify | Müzik | Atla | Evet | Yok, şartlar da uymuyor |
| Jamendo | Müzik | Atla | **Evet, önbellek yasak** | Yok |
| eidosSpeech | Sesli anlatım | Atla | Evet | Güvenilir değil |
| Replicate | Ücretli model servisi | Atla | - | Bir satır: kullandıkça ödemeli, sayfada ücretsiz katman geçmiyor [D](https://replicate.com/pricing) |
| Sunor | Ücretli müzik servisi | Atla | - | Bir satır: 1 kredi $0,01, çok modelli toplayıcı, resmi Suno olduğunu söylemiyor [D](https://docs.sunor.cc) |

## 3. Gerçekten işe yarayanlar, sırayla

1. **Hiçbir şey eklememek (adım 1-3 boyunca).** Şehir bilgisi işi sürüyor, dışarıdan veri onu hızlandırmaz.
2. **Vikisözlük'ten yerel kelime listesi,** ölçüm betiğinde (sahip isterse).
3. **Elle yazılmış isim listesi.** Türkçe isim için API yerine en ucuz yol bu [Ç].
4. **SRD 5.2 canavar anlık görüntüsü,** adım 3 sonrasında oyun ihtiyaç gösterirse.
5. **Medya paketi (adım 8):** Freesound CC0 sesleri, Met görselleri, Game Icons ikonları. Hepsi elle seçilir, repoda durur, oyunda ağ istemez.

## 4. Zaten çözülmüş olanlar

| İhtiyaç | Mevcut çözüm | Sınır |
|---|---|---|
| Büyü verisi | `content/rules/phb2024/spells.json`: 391 büyü (seviye, okul, sınıf, menzil, süre, bileşen, sayfa) | Kitap metni ve etki yok, bilinçli |
| Büyü motoru | `spell_registry.py`, `spell_scope.py`, `spells.py` | `CATALOG`'da 4 çözücü: Fire Bolt, Magic Missile, Cure Wounds, Sacred Flame |
| Feat | `feats.json`: 75 | Yalnız indeks |
| Silah, zırh | `weapons_armor.json`: 38 silah, 12 zırh, 8 mastery; `weapon_catalog.py`, `equipment_rules.py` | Sihirli eşya verisi görülmedi |
| Sınıflar | `classes/`: 6 sınıf dosyası | Kalan sınıflar donduruldu |
| Canavar motoru | `monster_combat.py`, `monster_capabilities.py`, `monster_perception.py`, `monster_sense.py` | Kodda görülen stat block'lar: `mm2024.commoner`, `authored_traveler_v1`; `content/rules` altında canavar veri seti yok |
| Karakter görseli | `attached_assets/generated_images`: sınıf ve tür portreleri, oluşturma ekranı ve oyun ekranında kullanılıyor | NPC portresi yok |
| Arayüz sesi | `gate-sound.ts`: Web Audio ile üretilen kısa işaretler, dosya yok | Repoda takip edilen ses dosyası 0, ortam sesi yok |
| İkon | `lucide-react` bağımlılığı | Oyuna özel ikon değil |
| NPC'nin şehir bilgisi | `town_knowledge.py`, `world_threads.py`, `content/world/town_threads.json`, `local_places.py` | Başka ajan yazıyor, dokunulmamalı |
| NPC isimleri | `living_world.py`: tohumsuz 16, tohumlu 101 isim | Fantazi isimleri, Türkçe değil; "Marek" tohumsuz eski havuzda duruyor |
| Dünya bilgisi | `ai-dnd/api/lore_authority/packs`: incelenmiş lore paketleri | Bazı paketler `INCOMPLETE` |
| LLM seçimi | `UCRETSIZ_MODEL_ARASTIRMA_20261031.md` | Groq ve HF burada yeniden açılmaz |

## 5. Kural sürümü ve lisans uyarıları

- **SRD lisansı:** SRD 5.1 OGL 1.0a ve CC-BY-4.0, SRD 5.2 CC-BY-4.0 ile sunuluyor. Güncel İngilizce sürüm 5.2.1. Türkçe sürüm listelenmiyor: yalnız Almanca, İspanyolca, Fransızca, İtalyanca [D](https://www.dndbeyond.com/srd). Tam atıf cümlesi [O]: denenen PDF adresi 403 döndü ve adres resmi sayfadan alınmamıştı. İkincil kaynaklardaki cümleler kopyalanmamalı, cümle resmi sayfadaki PDF'ten alınmalı.
- **SRD, PHB 2024 demek değildir.** Canlı karşılaştırma: Open5e `srd-2024` 339 büyü, yerel 391; adı birebir eşleşen 322 [D]. Kalan 17 SRD adının gördüğüm 15'i büyük ölçüde adı kısaltılmış büyüler (Melf's Acid Arrow → Acid Arrow). Hepsi öyleyse SRD'de gerçekten olmayan yaklaşık 52 büyü kalır [Ç].
- **2014 ve 2024 karışmamalı.** Open5e'de 24 belge var, çoğu 2014 ve OGL. Mutlaka `document__key=srd-2024` ile süzülmeli. `open5e-2024` belgesi 2024 etiketli ama OGL ve SRD değil [D](https://api.open5e.com/v2/documents/?format=json).
- **Proje kuralı:** `origins.json`, SRD 5.1'i "kullanıcının onayladığı yerel kaynak kapsamı dışında" diye kaydediyor, Half-Elf ve Half-Orc da bu yüzden `BLOCKED_SOURCE_NOT_LOCAL`. SRD'yi kaynak olarak eklemek sahibin kararıdır [D, repo].
- **Veri, motor değildir.** İndirilen açıklama yalnız anlatıcıya bağlam olur. Motorda çözücü yoksa `spell_registry` `unsupported` döner. Model açıklamayı okuyup etki uydurmamalı [Ç].
- **Medyada her dosya ayrı kontrol edilir.** Lisans API'nin değil, tek tek dosyanındır. Seçilen her dosya için kaynak adresi, yazar, lisans ve tarih kaydedilmeli [Ç].

## 6. "Şu anki adım" sorusu

| Konu | Yardım eden var mı | Dürüst cevap |
|---|---|---|
| NPC'nin şehri bilmesi | **Hayır** | Bilgi kampanyaya özgüdür, `town_knowledge.py` ile Python üretiyor. Hiçbir API bunu bilemez. Open5e veya Wikipedia benzeri veri isabet etmez [Ç]. |
| Türkçe isim | **Hazır çözüm yok** | Okuduğum belgelerde hiçbir adayın hazır Türkçe isim listesi geçmiyor [Ç]. Vikisözlük'te özel ad kategorisi olabilir, kontrol edilmedi [O]. Elle yazılmış 50-100 isim daha ucuz. `RANDOM_NAMES` ve `_LOCAL_NAMES` zaten değiştirilebilir, ama eski kayıtlar için eski havuz korunmalı. |
| Türkçe kelime yardımı | **Kısmen, geliştirmede** | Vikisözlük ölçüm betiğinde "sözlükte olmayan kelime" sayar. Oyunda engel olarak kullanılmamalı: sahibin yönü az engel ve onarımdır. Çekim ekleri liste eşleşmesini yanıltır, sonuç ancak inceleme işaretidir [Ç]. Datamuse Türkçe vermiyor. LibreTranslate çeviri aracıdır, sözlük değildir. |

**Karar sahibinde:** Vikisözlük verisi CC BY-SA olduğu için türetilmiş liste repoya girerse atıf ve aynı lisans bildirimi gerekir. Yalnız yerel ölçüm için tutulursa bu soru küçülür [Ç].

## 7. Adaylar

Her satır sırayla: **1** ihtiyaç, **2** ne verir, **3** lisans ve şartlar, **4** kota, **5** yerel kullanım, **6** veri modeli uyumu, **7** maliyet, yedek, doğrulama. Maliyetler kaba tahmindir [Ç].

### Open5e

1. Canavar, büyü metni, sihirli eşya. Şimdi değil, sonra.
2. Yapılandırılmış REST verisi. 33 kaynak [D](https://api.open5e.com/v2/). `srd-2024`: 339 büyü, 331 yaratık [D]. Büyüde `damage_roll`, `saving_throw_ability`, `casting_options` alanları var; ama bazı etkiler yine yalnız metinde (Acid Arrow'un sonraki tur hasarı) [D].
3. Lisans belge başınadır: SRD 5.2 CC BY 4.0, diğerleri çoğunlukla OGL [D](https://api.open5e.com/v2/documents/?format=json). Kod lisansı [O]: GitHub "Other" gösteriyor, LICENSE yolu 404. [Yasal sayfanın](https://open5e.com/legal) lisans listesi okunamadı [O].
4. Anahtarsız yanıt verdi [D]. Oran sınırı yayımlanmamış [O]. V1 kullanımdan kalkmış, V2 güncel [D](https://open5e.com/api-docs). Yanıtta 2 günlük önbellek başlığı görüldü [D].
5. Evet. Tek seferlik anlık görüntü yeterli. Kendi sunucusu da kurulabilir, veri `/data` altında [D](https://raw.githubusercontent.com/open5e/open5e-api/staging/README.md).
6. Uyar, ama eşleme gerekir: isimler farklı, `monster_stat_block` biçimi ayrı. Metin İngilizce.
7. Orta: görüntü dosyası, kaynak kaydı, eşleme. Yedek: görüntü yerelde olduğu için servis düşmesi etkilemez. Doğrulama: 5 canavarı resmi SRD PDF'iyle elle karşılaştır.

### D&D 5e SRD API (dnd5eapi)

1. Open5e ile aynı ihtiyaç; en iyi kullanımı çapraz kontrol.
2. REST. `/api/2014` ve `/api/2024` ayrı [D](https://docs.dnd5eapi.co/). Canlı sayılar 2024: 339 büyü, 341 canavar, 182 ekipman, 17 feat, 9 tür, 4 geçmiş, 262 sihirli eşya; 2014: 319 büyü, 334 canavar [D]. Fireball'da kurtarma zarı yalnız metinde, hasar yarı yapılandırılmış [D](https://www.dnd5eapi.co/api/2024/spells/fireball).
3. Kod MIT [D](https://raw.githubusercontent.com/5e-bits/5e-srd-api/main/LICENSE.md). 2024 verisinin lisansı belirtilmemiş [O]. Arşivlenmiş eski veritabanı README'si OGL 1.0a diyor [D](https://raw.githubusercontent.com/5e-bits/5e-database/main/README.md), bu 2024 verisini kapsamaz [Ç]. Atıf SRD'nin kendisine yapılmalı [Ç].
4. Anahtarsız yanıt verdi. Yanıt başlığında sınır 100 görüldü, pencere bilinmiyor [D]. Yayımlanmış sınır bulunamadı [O].
5. Evet. Kaynak ve veri açık, Node 24 ve pnpm ile kendi kurulumu mümkün [D](https://raw.githubusercontent.com/5e-bits/5e-srd-api/main/README.md).
6. 2024 ucu kullanılırsa uyar. Canavar sayısı Open5e'den farklı (341 ve 331), nedeni bilinmiyor [O].
7. Küçük. Doğrulama: iki kaynağın canavar adlarını karşılaştır, farkı resmi SRD'den çöz.

### Freesound

1. Ortam sesi: han, sokak, orman, yağmur. Adım 8.
2. Ses arama ve dosya. Önizleme ve orijinal ayrı.
3. Lisans ses başına: CC0, BY, BY-NC, eskilerde Sampling+ [D](https://freesound.org/help/faq/). API şartları ayrı: ticari kullanım pazarlığa bağlı, tam veritabanı kopyası ve benzer veritabanı yasak, gerekmeyen kopya silinmeli, lisans her an geri çekilebilir [D](https://freesound.org/help/tos_api/).
4. Anahtar gerekir. 60/dk, 2.000/gün. Orijinal indirme 30/dk, 500/gün ve OAuth2 [D](https://freesound.org/docs/api/overview.html).
5. API yerine site üzerinden 10-20 sesin elle seçilmesi en uygunu. Her dosya kendi lisansıyla repoda durur [Ç]. Yalnız CC0 tercih, BY-NC hariç.
6. Oyun durumuyla bağı yok; `kind` veya mekân etiketine göre seçim yeterli [Ç].
7. Küçük-orta: oynatıcı ve ses dosyası bağlama. Yedek: sessizlik. Doğrulama: tek bir CC0 han sesini lisans kaydıyla dene.

### DiceBear

1. NPC yer tutucu yüzü. Gerekli değil.
2. Tohumdan üretilen SVG veya PNG avatar.
3. Kod MIT. Stil lisansları ayrı: 42 CC0, 14 CC BY 4.0, 1 MIT, 4 sanatçı şartı [D](https://www.dicebear.com/licenses/).
4. Anahtarsız. SVG 50/sn, diğerleri 10/sn, haber vermeden değişebilir [D](https://www.dicebear.com/how-to-use/http-api/).
5. Evet, kendi barındırması mümkün.
6. Çizgi film tarzı, mevcut portrelerle uyumsuz olabilir [Ç]. Yüz göstermek "tanınmayan kişi" kurallarını etkilemez, ama isim sızdırılmamalı [Ç].
7. Küçük. Yedek: mevcut baş harf. Doğrulama: bir CC0 stili portre yanında gözle karşılaştır.

### Openverse

1. Elle medya keşfi.
2. Görsel ve ses meta verisi arama; dosyayı üçüncü taraf barındırır.
3. **Lisans doğrulamaz,** sorumluluk kullanıcıdadır. Kazıma yasak, ağır veya ticari kullanıma ücret gelebilir [D](https://docs.openverse.org/terms_of_service.html).
4. Anonim kullanım var, sayı okunamadı [O]. Standart katman için OAuth [D](https://docs.openverse.org/api/reference/authentication_and_throttling.html).
5. Bulunan dosya kaynağından kontrol edilir, Openverse servis olarak oyuna girmez.
6. Yok.
7. Sıfır entegrasyon: web arayüzü yeter. Doğrulama: bir sonucun lisansını kaynak sayfada karşılaştır.

### Met Museum API

1. Yer ve eşya görseli: zırh, silah, harita, ortaçağ eserleri. Adım 8.
2. Nesne meta verisi ve yüksek çözünürlüklü JPEG.
3. Seçili veri setleri CC0. Görsel yalnız Open Access ise gelir, `isPublicDomain` her nesnede kontrol edilmeli. Telifli nesnelerin kimlik verisi de var. Kullanım şartları ayrıca bağlı, okunmadı [D](https://metmuseum.github.io/).
4. Anahtarsız, saniyede 80 istek sınırı isteniyor [D].
5. Evet. En temiz tek seferlik seçenek.
6. Gerçek eserdir, fantazi sahnesi değildir; eşya ve atmosfer için uygun [Ç].
7. Küçük. Yedek: görsel yok. Doğrulama: 5 eseri `isPublicDomain` ile kaydet.

### Pixabay

1. Görsel. Ses ihtiyacını karşılamaz: API yalnız görsel ve video [D](https://pixabay.com/api/docs/).
2. Medya arama.
3. Atıf gerekmez, ama olduğu gibi yeniden dağıtma ve marka içeren ticari kullanım yasak [D](https://pixabay.com/service/license-summary/). API sonucu gösterilirken kaynak belirtilmeli, sistematik toplu indirme yasak [D](https://pixabay.com/api/docs/).
4. Anahtar gerekir. 100 istek/60 sn, istekler 24 saat önbelleklenmeli [D].
5. Kalıcı hotlink yasak, dosya indirilmeli. API değil, elle seçim uygun [Ç].
6. Yok. Üçüncü taraf hakları dosya başına kontrol edilmeli [D].
7. Sıfır entegrasyon. Doğrulama: seçilen dosyanın sayfasını kaydet.

### Pexels

1. Fotoğraf. Fantazi sahnesine pek uymaz [Ç].
2. Foto ve video arama.
3. Atıf gerekmez [D](https://www.pexels.com/license/). API için belirgin Pexels bağlantısı isteniyor [D](https://www.pexels.com/api/documentation/). Sistematik kopyalama izinsiz yasak [D](https://www.pexels.com/terms-of-service/).
4. Anahtar gerekir. 200/saat, 20.000/ay [D].
5. Elle mümkün, API'ye gerek yok.
6. Yok.
7. Atla, Met daha uygun.

### Icons8

1. İkon.
2. İkon, API.
3. Ücretsiz kullanım için Icons8'e bağlantı şart, ödemeli planda kalkar [İ](https://icons8.com/icons/pricing). [Lisans sayfası](https://icons8.com/license) 403 döndü [O].
4. API planları $15-$2.000+/ay [İ](https://developers.icons8.com/).
5. Şartlar doğrulanmadı.
6. Yok.
7. Atla. Iconify ücretsiz ve yerel alternatif sunuyor.

### Iconify

1. Oyuna özel ikon.
2. 200+ açık ikon setinde 300 bin+ ikon, API ve npm paketleri [D](https://iconify.design/docs/api/).
3. **Lisans set başınadır.** Site Apache 2.0, bu setleri kapsamaz. Game Icons: CC BY 3.0, 4.133 ikon [D](https://icon-sets.iconify.design/game-icons/). Atıf gerekir [D](https://game-icons.net/about.html).
4. Herkese açık API'de sınır var, sayı yok [D].
5. Evet. `@iconify-json/{prefix}` ile derleme anında, oyunda ağ yok [D](https://iconify.design/docs/icons/icon-data/).
6. `lucide-react` yanında durabilir, UI işi. AI'a etkisi yok.
7. Küçük. Doğrulama: atıf satırıyla tek setten 5 ikon.

### anaislalovi/dnd5e-icons

1. Durum ve özellik ikonu.
2. **API değil, ikon deposu.** README lisans söylemiyor, "free for everyone" diyor [D](https://raw.githubusercontent.com/anaislalovi/dnd5e-icons/main/README.md).
3. **Çelişki:** GitHub lisans alanı MIT [D](https://api.github.com/repos/anaislalovi/dnd5e-icons). Open5e aynı seti CC0 listeliyor [D](https://api.open5e.com/v2/documents/elderberry-inn-icons/?format=json). Daha sıkı olan MIT bildirimi korunmalı [Ç].
4. Kota yok. Son güncelleme 2023 [D].
5. Evet, dosyalar repoya girebilir.
6. 2014 etiketli ama ikonlar kural taşımaz [Ç]. Open5e görsel ucunda 32 kayıt var [D].
7. Küçük. Doğrulama: depodaki LICENSE dosyasını oku.

### Groq

1. Yedek LLM; ileride mikrofon için Whisper.
2. Model servisi.
3. Varsayılan saklama yok, izleme için 30 güne kadar log olabilir; kapatılabilir [D](https://console.groq.com/docs/your-data). Eğitim ve Services Agreement [O].
4. gpt-oss-120b: 30 RPM, 1K RPD, 8K TPM, 200K TPD. whisper-large-v3: 20 RPM, 2K RPD. Sayfa planı adlandırmada tutarsız, önceki araştırma ham HTML ile Free planı doğruladı [D](https://console.groq.com/docs/rate-limits).
5. Hayır, oyun sırasında servis.
6. JSON şeması önceki araştırmada doğrulandı. Oturumu taşımaz: 25-39 dakika.
7. Küçük, yalnız karşılaştırma. Yedek: yerel Gemma. Doğrulama: aynı Türkçe turları karşılaştır.

### Hugging Face

1. Yerel model ve veri seti indirme.
2. Model deposu. Inference Providers ayrı ve ödemelidir.
3. Lisans model ve veri seti başına [Ç].
4. Ücretsiz kullanıcıya aylık kredi yok [D](https://huggingface.co/docs/inference-providers/pricing). Hub: ücretsiz kullanıcı 5 dakikada 5.000 indirme isteği, Eylül 2025 tablosu [D](https://huggingface.co/docs/hub/rate-limits).
5. Evet, indirme için. Çıkarım için hayır.
6. Yerel Gemma düzeniyle uyumlu [Ç].
7. Küçük, yalnız gerekirse. Mevcut LLM kararını değiştirmez.

### Jina AI

1. Embedding (defter hatırlama), Reader (araştırma). Adım 6 ihtiyaç göstermeden gereksiz [Ç].
2. Model servisi.
3. API kullanımında ayrı lisans gerekmez. Ağırlık lisansı modele göre değişir: CC BY-NC modeller ticari lisans ister, v4 Qwen Research lisanslıdır, eski v1-v2 Apache-2.0 [D](https://jina.ai/embeddings/). Reader "profesyonel kullanım" diyor, API verisi eğitimde kullanılmıyor [D](https://jina.ai/reader/).
4. Ücretsiz anahtar 100 RPM, 100K TPM; yeni anahtara 10M token. Reader anahtarsız 20 RPM. Sayfada 500 ve 100 RPM çelişkisi var [D].
5. Hayır, servis gerekir. Yerel seçim daha uygun [Ç].
6. Türkçe açıkça belirtilmiyor [D].
7. Atla.

### Unsplash

1. Fotoğraf.
2. Foto arama.
3. **Hotlink zorunlu,** atıf ve indirme tetiklemesi şart. Çekirdek deneyimi kopyalama yasak [D](https://help.unsplash.com/en/articles/2511245-unsplash-api-guidelines). Lisans genel olarak geniş, rakip servis için derleme hariç [D](https://unsplash.com/license).
4. Demo 50/saat, üretim 1.000/saat [D](https://unsplash.com/documentation).
5. API ile **hayır:** oyun sırasında ağ ister. Bu, yerel tercihine terstir.
6. Yok.
7. Atla.

### Spotify

1. Müzik.
2. Katalog ve oynatma kontrolü, müzik dosyası değil.
3. Yerel önbellek ve süresiz saklama yasak, AI eğitimi ve modele alma yasak, yalnız açıkça izin verilen kullanım [D](https://developer.spotify.com/terms). Modele beslemek de bu nedenle kapalı.
4. Geliştirme modu: Premium, en çok 5 kullanıcı. Genişletilmiş kota: kayıtlı şirket ve 250 bin aylık kullanıcı [D](https://developer.spotify.com/documentation/web-api/concepts/quota-modes).
5. Hayır.
6. Yok.
7. Atla.

### LibreTranslate

1. SRD metnini Türkçeye çevirme.
2. Yerel çeviri sunucusu, Argos modelleri.
3. AGPLv3 [D](https://raw.githubusercontent.com/LibreTranslate/LibreTranslate/main/README.md). Argos model lisansı [O].
4. Yerelde kota yok. Barındırılan API fiyatı ve anahtarı [O].
5. Evet, kendi barındırılır. Türkçe dil paketi var [D](https://libretranslate.com/languages).
6. RPG kalitesi bilinmiyor. Çeviri motoru Türkçe sesi taşımaz; narratör zaten Türkçe üretiyor [Ç].
7. Atla. İleride SRD çevirisi gerekirse aynı terim listesiyle Haiku denenebilir [Ç].

### Datamuse

1. Kelime yardımı. **Karşılamaz.**
2. Kelime ve anlam sorgusu.
3. Lisans belirtilmemiş, herkese açık uygulamalarda dokümanda atıf isteniyor [D](https://www.datamuse.com/api/).
4. 100.000 istek/gün. Anahtar zorunluluğu tarihi sayfada çelişkili: 2027-01-01 ve 2027-02-01 [D].
5. Hayır.
6. Yalnız İngilizce ve İspanyolca belirtilmiş, Türkçe yok [D].
7. Atla.

### Jamendo

1. Arka plan müziği.
2. Creative Commons müzik, API ve akış.
3. Lisans parça başına, sayfası izlenmeli. API serbest yalnız ticari olmayan kullanımda; reklam ve ortaklık geliri ticari sayılır. **Önbellek için tasarlanmış uygulama ve çevrimdışı erişim yasak.** Atıf ve parça bağlantısı şart [D](https://devportal.jamendo.com/api_terms_of_use).
4. Kayıt ve OAuth gerekir [D](https://developer.jamendo.com/v3.0/docs). Ticari olmayan plan ayda 35.000 istek [D](https://developer.jamendo.com/v3.0).
5. API ile **hayır.** Fesihte içerik kaldırılmalı.
6. Yok.
7. Atla. Müzik gerekirse Freesound CC0 veya ayrı bir araştırma.

### Wiktionary / Vikisözlük

1. Türkçe kelime listesi, ölçüm betiği için.
2. MediaWiki API ve veri dökümü. `trwiktionary` dökümü 68,7 MB, dosya tarihi 2026-10-01 [D](https://dumps.wikimedia.org/trwiktionary/latest/). kaikki.org hazır çıkarım sunuyor: `tr-extract.jsonl`, sıkışık 43,8 MB [D](https://kaikki.org/dictionary/rawdata.html), lisans belirtmiyor [O].
3. CC BY-SA 4.0 ve GFDL; atıf, değişiklik bildirimi ve aynı lisans gerekir [D](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use).
4. API'de seri istek, anlamlı User-Agent, `maxlag` isteniyor [D](https://www.mediawiki.org/wiki/API:Etiquette). Döküm tek dosyadır, API yükü doğurmaz.
5. **Evet.** Bir kez alınır, geliştirme makinesinde durur.
6. 1.607.664 içerik sayfası var [D](https://tr.wiktionary.org/wiki/Özel:İstatistikler), ama bu çok dillidir, Türkçe girdi sayısı bilinmiyor [O]. Türkçe satırlar ayrılmalı, çekimli biçimler ayrıca ele alınmalı [Ç].
7. Küçük: tek betik, ürün koduna dokunmaz. Yedek: yok, oyun etkilenmez. Doğrulama: bilinen 50 kelimeyi ve bu projedeki 20 gerçek anlatı metnini tarayıp yanlış alarm oranını say.

### eidosSpeech

1. Sesli anlatım. Adım 8.
2. Metinden sese, MP3.
3. Çıktı kullanıcıya ait, ama sesler Microsoft Edge TTS ve "Microsoft şartlarına tabi". Çalışma garantisi yok, her an kapanabilir. İşleten şirket adı yok [D](https://eidosspeech.xyz/tos).
4. Kayıtlı: 30 istek/gün, çağrı başına 1.000 karakter, 3/dk [D](https://eidosspeech.xyz). 1,4 tur/dk ile yaklaşık 21 dakika [Ç].
5. Üretilen MP3 saklanabilir, ama anlatı canlı olduğu için servis gerekir [Ç].
6. Türkçe listede, ses adı ve kalite verilmiyor [D]. Kalite ölçülmedi: anahtar gerekir.
7. Atla. Edge TTS yolunun resmi olmadığı ve Aralık 2025'te bir eklenti için engellendiği ikincil kaynakta geçiyor [İ](https://addons.mozilla.org/addon/edge-tts/). Sesli anlatım zamanı gelince resmi veya yerel seçenek ayrıca araştırılmalı.

## 8. Okunamayan veya doğrulanamayan noktalar

- SRD 5.2.1 tam atıf cümlesi (PDF 403).
- Open5e kod lisansı, yasal sayfanın lisans listesi, oran sınırı.
- dnd5eapi 2024 veri lisansı, yayımlanmış oran sınırı, 341 ve 331 canavar farkının nedeni.
- Openverse anonim sayıları, Met kullanım şartları, Argos model lisansı.
- Icons8 lisans sayfası (403), bilgiler arama özetinden.
- LibreTranslate barındırılan API fiyatı, Groq Services Agreement.
- Vikisözlük'teki Türkçe girdi sayısı ve özel ad kapsamı.
- eidosSpeech Türkçe ses kalitesi, Microsoft'un bu kullanıma bakışı.
- Hiçbir kota sınanmadı. Hiçbir medya dosyasının lisansı tek tek incelenmedi.
- Repo taraması tam denetim değildir. "Görülmedi" ifadeleri, kodda aranıp bulunmadı demektir.
