# AI-DND V13 — Mimari ve oynanabilirlik incelemesi

29 Eylül 2026. **Sonuç: temel eksik, kalıcı ve etkileşilebilir sahne yaşam döngüsü.** Daha edebî bir Qwen promptu tek başına çözmez. Üretim izinleri gündelik oyuncu eylemlerine bağlanmıyor; geçici anlatının hedeflenebilir bir varlığa dönüşme yolu yok; canon denetimi yerel meslek ve gündelik konuşmayı da engelleyebiliyor. Sonuçta doğru çalışan kayıt sistemi çoğu zaman boş dünyayı doğru biçimde kaydediyor.

## İnceleme kapsamı ve kanıt sınırı

Önceki sohbetin gerçek ekinden `AIDND V13.rar` alındı. Bu Windows oturumunda `/mnt/data/...` bulunmuyordu; sohbet eki yerel geçici dosya olarak erişilebildi. Arşiv üye yolları mutlak yol, üst dizine çıkış ve linkler açısından kontrol edilerek ayrı `work/review-source/` klasörüne çıkarıldı. İç içe kaynak yedeği çalıştırılmadı/açılmadı. Proje kaynaklarına, yapılandırmalarına ve arşivdeki kampanya veritabanına değişiklik yapılmadı.

- Arşiv SHA-256: `255a8d7c2b70a205b0874ce1386fc6b3e955eec3fb297c25366c4cf7fbbc2b16`.
- İncelenen `ai-dnd/game.py` SHA-256: `463b0d9b1a8079b37744f6535748358af50bee6dfca7180de68560fcf89a18cb`. Son Neverwinter V1 raporuyla eşleşiyor.
- Aktif motor/API, lore registry ve pack loader, bellek/director, persistence, aktif React ekranı, OpenAPI/generated client yapısı, root yapılandırmalar, ilgili testler ve tarihli raporlar incelendi. Yedek motorlar ve diğer UI projeleri aktif uygulama olarak değerlendirilmedi.
- **Yerel olarak 44 test geçti:** `test_narrative_safety_calibration`, `api.tests.test_narrative_memory`, `api.tests.test_narrative_director`. Python 3.12.14 kullanıldı; eksik `ollama` modülü yalnızca bu izole test sürecinde ağ çağırmayan bir stub ile değiştirildi. Bu, Replit/Python 3.13 veya gerçek Qwen doğrulaması değildir.
- Aşağıdaki kısa davranış probları güncel kaynak üzerinde bellekte çalıştırıldı. Tam API/build ve canlı Qwen smoke bu incelemede çalıştırılmadı; yerel ortamda FastAPI, httpx, Ollama bağımlılıkları yok. Eski canlı sonuçlar rapor kaynaklı olarak ayrıca belirtiliyor.

Dosya/satır referansları arşiv köküne göredir ve bu hash'e aittir.

## Gerçek uçtan uca akış

| Aşama | Güncel uygulama | Önemli sınır |
|---|---|---|
| Oyuncu mesajı | `artifacts/ai-dnd-experience/src/pages/game-browser.tsx:752`: `usePlayGameTurn` üzerinden mesaj, varsa combat `target_id` | UI NPC/özellik üretmiyor; `result.narration` doğrudan transcript'e yazılıyor. |
| HTTP sözleşmesi | `lib/api-spec/openapi.yaml:567`, generated React client ve Zod; `/api/game/sessions/{id}/turn` | FastAPI schemas ve serializer allowlist'i ile eşleniyor. |
| Tur sınırı | `ai-dnd/api/main.py:578`: oturum kilidi, engine/RNG/messages snapshot'ı, hata ve model çağrı kontrolü | En fazla iki model çağrısı; model hatasında API rollback yapabiliyor. |
| Lore retrieval | `api/main.py:134,636` → `LoreRegistry.retrieve_lore_context` (`registry.py:505`) | **Intent ve seyahat çözülmeden önce** mevcut campaign binding, konum ve mesajdan çekiliyor. |
| Intent/action | `game.py:7156` → erken deterministik yanıtlar → `parse_player_intent:3420` → normalize/validate → `execute_intent:6843` | Qwen sınıflandırır; zar, hasar, envanter ve seyahati Python uygular. Erken yanıtlar narrator/üretimi atlayabilir. |
| Dünya/sahne | `commit_location_change:3324`, `_ensure_location_entities:3670`, üretim gate'leri `4561,4570` | Ayrı scene materializer yok. `_ensure_location_entities` yalnızca iki ön tanımlı konumun kapılarını sağlar. |
| Bellek ve prompt | `api/narrative_director.py:48` wrapper'ları → `build_world_context:3115`; bounded continuity eklenir | Director yeni varlık yaratmaz; canonical world, lore packet ve action result Qwen'e gider. |
| Qwen üretimi | `ask_dungeon_master:5857`: `qwen3:8b`, JSON narration/world_updates/lore_claims, 700 çıktı tokenı | Narration ve öneriler aynı çağrıda gelir; model Python'un kabul kararını o çağrı içinde göremez. |
| Öneri doğrulama | `game.py:7550–7670`: önce lokasyon, sonra NPC/feature/shop; ID'leri Python atar | Lore metin denetimi başarısızsa bu öneri aşamasının world/action snapshot'ına dönülür. Önceden tamamlanan bilinen seyahat ayrı durumdur. |
| Son anlatım | `finalize_narration:6313`, safety `3996`, lore text guard `5082` | İki agency nedeni için cümle çıkarma; diğer birçok durumda tüm anlatım fallback olur. |
| Kalıcı sonuç | `api/main.py:757–986`: lore evidence, narrative memory, journal, state projection, autosave, HTTP yanıtı | Başarılı tur SQLite'a kaydedildikten sonra yanıtlanır. `campaign_store.py:89` transaction; resume engine save/RNG/bellek/lore/journal/history'yi yükler. |

Root `main.py` terminal girişidir; aktif web oyunu FastAPI + `ai-dnd-experience` artifact'idir. `.replit` API workflow'unu, artifact TOML/Vite UI hizmetini tanımlar. `artifacts/api-server` route index'i yalnızca health bağlar; asıl oyun motoru değildir. `lib/db` TypeScript altyapısı da bu Python SQLite kampanya yolunun yerine geçmez. pnpm workspace/lockfile/TS references kod üretimi ve build düzenini kurar; `.replit` ve root package scripts arşivde bulunmayan `scripts/` dosyalarına da referans verir. Bu, Replit'te build/preflight kontrol edilmelidir; boş dünya nedeninin kanıtı değildir.

## Sorunların somut nedenleri

### 1. Başlangıç boş; sıradan bakış boşluğu gideremiyor

`game.py:1203` başlangıçta boş NPC/feature/event listeleri ve açıklamasız genel `tavern/forest/castle` kayıtları oluşturur. `SessionManager._install_canonical_start_location` (`api/session_manager.py:166`) Neverwinter'ı da boş açıklamalı bir konum olarak ekler; sokak, yerel mekân veya nüfus üretmez.

`should_generate_npcs` belirli sözcük köklerini veya boş konuma seyahati arar. `should_generate_features` daha dar araştırma/check/seyahat koşullarına bağlıdır. İzole problarda:

| Girdi | NPC / feature üretim izni |
|---|---|
| Etrafıma bakıyorum. | false / false |
| Kimler var? | false / false; ayrıca presence query |
| Barmene yaklaşıyorum. | false / false |
| Şu muhafıza yaklaşıyorum. | false / false |
| Bir tüccar arıyorum. | false / false |
| Bir masaya oturuyorum. | false / false |

`arıyorum`, gate'in `ara\w*` biçimiyle eşleşmiyor. Daha önemlisi `Kimler var?`, `_handle_query:989` içinde **“Burada kayıtlı bir NPC yok.”** döndürür; `run_player_turn:7497` direct-response dönüşü nedeniyle scene generation'a hiç ulaşmaz. “Mevcut kayıt yok” ile “orada gerçekten kimse yok” aynı ürün davranışına dönüşür.

### 2. Görülebilen geçici kişi, sonraki turda hedeflenemiyor

Kontrollü model yanıtıyla normal bakış turunda **“Kapıda isimsiz bir muhafız bekliyor.”** kabul edildi; modelin aynı yanıttaki NPC önerisi izin kapalı olduğu için atıldı; `world_state.npcs` boş kaldı. Bu, güncel kaynak üzerinde yeniden üretildi; eski Elara raporuna dayanan bir tahmin değil.

`resolve_npc_reference:2900` yalnızca kalıcı mevcut NPC ad/rolleri ve altı turluk konuşma odağını bilir. Son sahnedeki “kapıdaki adam” için handle/alias yoktur. `api/narrative_memory.py:353–365` narrator metnini `[presentation omitted from continuity]` ile değiştirir ve temporary texture kayıtlarını ayıklar. `build_narrative_context:640` texture'ın entity/interactive object'e yükseltilmemesini söyler. `ask_dungeon_master` geçmiş `messages` parametresini model mesaj listesine aktarmıyor; yalnızca system/current user context gönderiyor.

Bu yaklaşım yanlış belleği önlüyor fakat **güvenli promotion köprüsü olmadığı için oyuncunun gerçekten gördüğü ayrıntıya geri dönmesini de engelliyor.** Çözüm transcript'i gerçek kaynağı ilan etmek değil; sunulmadan önce kabul edilmiş, sınırlı scene mention kayıtları tutmak.

### 3. Yerel üretim yolu test senaryosuna daraltılmış

`validate_world_updates:2783` genel NPC önerilerinde shopkeeper rollerini dışlar. Tüccar önerisi `allow_new_npcs=True` iken bile boş sonuç verdi. Shop yolu açık bir “kur/oluştur” isteği gerektirir; `run_player_turn:7301` civarındaki kontrol bütün kampanyayı tek dükkân/dükkâncı ile sınırlar. “Tüccar bulmak” doğal karşılaşma olmaktan çıkıp kurulum komutuna dönüşmüş.

Feature doğrulama (`2820–2849`) ad **ve açıklamadaki** bardak, bira, yemek, dükkân vb. sözcükleri dışlar. “Ahşap masa / Üzerinde bir bardak durur” önerisi tamamen reddedildi. Özelliklerin stable ID'si yok: kayıtlar location/name/description düzeyinde; API `_FEATURE_FIELDS` de aynı üç alanı taşır. Lore procedural ref koleksiyonları NPC/location/shop ID'lerini toplar, feature'ları toplamaz. Dolayısıyla özellikler depolanabilir, ancak güvenilir hedefleme/promotion bağlantısı eksiktir.

### 4. Canon kontrolü yerel meslek ve konuşmayı setting iddiası sanıyor

Kaynak registry/review/visibility sınırları değerli; hata bunları yerel cümlelerde global sözcük filtresi gibi kullanmakta. `_LORE_UNSUPPORTED_DETAIL_PATTERNS:4932` içindeki `demirci`, `zırh`, `gümüş`, `iki gün`, nedensellik vb. kalıpları cümle öznesinin setting canon mu yerel NPC mi olduğuna bakmadan çalışır.

Doğrulanmış izole örnekler:

- Python'da kayıtlı Rana için **“Rana demirci olarak çalışır.”** genel safety'den geçti, lore guard'dan geçmedi.
- **“Rana bir demircidir.”** ise geçti: politika anlamdan çok sözcük sınırına bağlı.
- **“Rana, ‘İki gün önce geldim,’ diyor.”** lore guard'a takıldı; yerel kişisel ifade rota/mesafe filtresine girdi.
- “Bir demirci buluyorum” turunda üretim izni açıktı. Geçerli Rana/Demirci önerisi önce birleştirildi, yukarıdaki cümle lore guard'a takılınca NPC geri alındı; oyuncuya `UNVERIFIED` fallback'i gösterildi.

`_has_unregistered_narrative_entity:4881` büyük harfli ad/başlık sezgileri de sıradan “Barmen, ‘Merhaba,’ diyor” örneğini reddedebiliyor. `3996` sonrası safety, “istersen/dilersen” ve istenmemiş içecek davetlerini de engeller; **teklif etmek** ile **oyuncuya kabul ettirmek** gereğinden fazla birleşmiş. Mecburi içme, para düşme ve eşya transferi engellenmeli; NPC'nin konuşarak teklif yapması aynı şey değildir.

Bu bulgular canon kontrolünü kaldırmayı gerektirmez. Kaynaksız kral, tanrı, şehir, resmî tarih/rota veya politik ilişki hâlâ reddedilmelidir. Yerel demircinin mesleği “Neverwinter resmen şu zanaatta uzmanlaşmıştır” iddiasına eşit değildir.

### 5. Fallback oyuncuya gerçek ürün metni olarak gidiyor

Güncel aktif motor içinde literal `NO_STATE_CHANGE` bulunmadı. Ancak eşdeğer debug anlatımı doğrudan mevcut:

- `game.py:3816–3845`: **“Python world state'te bulunan bilgiler doğrulandı, yeni nesne veya ipucu eklenmedi.”**
- `game.py:6126–6160`: **“… çevresinde kayıtlı olanlar …”**, **“… kayıtlı ayrı bir kişi … yok.”**
- `game.py:5076`: **“… UNVERIFIED olarak kalıyor …”**
- `game.py:6397` civarı: **“… kayıtlı bir NPC kimliği yok …”**
- Shop ve unsupported action erken dönüşleri: kayıt, sürüm, doğrulama ve dünya durumuna ekleme açıklamaları.

Bunlar sadece log değildir. FastAPI narration'ı taşır; UI `game-browser.tsx:766` bunu aynen hikâyeye basar. UI'da ayrıca “Motor çevre özelliği kaydetmedi”, “yerel kayıt”, “kanonik dünya durumu sağ panelde” gibi metinler oyun hissini daha da teknikleştirir.

### 6. Güvenli anlatım ve kabul edilmiş öneri arasında tek sözleşme yok

Prompt aynı yanıt içinde yeni entity önerisini isterken **“onaylanmadan narration içinde kullanma”** der (`game.py:5954–5960`). Model henüz Python'un kararını görmemiştir. Sonrasında kabul/redde bağlı entity referanslarını yeniden bağlayan bir render sözleşmesi yok; çoğunlukla metnin tümü korunur ya da fallback'e düşer.

`_remove_trigger_sentence:6198` yalnızca `INVENTED_PLAYER_ACTION/OBJECTIVE` için çalışır. Lore hatası tüm öneri paketini geri alabilir. Öte yandan genel safety fallback'i, daha önce kabul edilmiş önerileri her durumda geri almaz. Bu farklılık açık acceptance/render kuralları ve testler gerektirir.

### 7. Dünya değişkenliği ve konum hiyerarşisi sınırlı

Konumlar düz bir registry; genel “Taverna”nın Neverwinter'a bağlı yerel bir mekân olduğunu taşıyan parent/exit ilişkisi yok. Bilinmeyen hedef çağrısında narrator önceki konum bağlamıyla proposal üretirken NPC doğrulaması daha sonra hedef konumda yapılır. Lore retrieval da seyahat öncesindedir. Bunlar destination-aware scene plan gerektirir; her seyahat kesin bozulur anlamına gelmez.

`world_metadata.py:149` mevcut day/weather değerlerini korur; varsayılan day/clear. Sahne aktivitesi, visit revision, kalabalık davranışı veya yerel bekleme adımı yok. Tek NPC bir kez yaratılınca çoğu giriş “mevcut NPC'yi yeniden kullan” yönlendirmesine döner. Quest kataloğu bilinçli olarak boş; yeni quest/economy sistemi bu düzeltmeye gizlice eklenmemeli.

## Eski PASS neden yeterli değil?

- Phase D raporu: 11 turda 8 anlatım değişimi; smoke bunu başarısızlık saymadı.
- Safety calibration raporu: 14 turda 6 replacement; yine PASS. Bunların hepsi hata değil—destekli isim hatırlama gibi deterministik yanıtlar ayrı sayılmalı.
- Son Neverwinter V1 raporu ve güncel hash: 20 tur, 15 model çağrısı; çoğu tur deterministik canon/refusal. Tek açık kurulum isteğiyle bir shop/NPC; feature listesi tüm koşuda boş, tavernada yeni NPC yok, combat yapılmamış. Bu **dar canon ve persistence başarısıdır**, normal oyunun canlılık testi değildir.
- `run_tests.py` 17 script çalıştırır; yeni safety dosyası ayrıca çalıştırılmalıdır. Frontend test dosyası combat/skill/quest bileşenlerine odaklıdır; doğal world → entity → referans → resume zincirini ölçmez.
- Root lore integration raporunun “production registry boş” notu tarihseldir. Güncel `pack_loader.py:124` incelenmiş Neverwinter pack'ini yükler; mevcut katalog The North/Neverwinter, 1501 DR ve `VERIFIED_PARTIAL` kapsamını gösterir.

## Tek çözüm: Playable Living World V1

Tek tur koordinatörü altında şu sözleşme kurulmalı:

**resolve → destination/scene plan → bounded local materialization → scoped lore + memory → Qwen proposal/prose → typed validation → accepted references ile final narration → atomic persistence.**

1. **Resmî canon:** reviewed kaynaklar, epoch/region/visibility ve onaylı campaign override; otoritesi değişmez.
2. **Kalıcı yerel kurgu:** stable ID'li ordinary NPC, mekân, önemli feature ve yerel sonuç; Python doğrular/commit eder. Model bunları resmî FR gerçeği ilan edemez.
3. **Sahneye bağlı arka plan:** oyuncunun seçebileceği anonim kişi/nesne için bounded handle, kaynak turu ve scene ID. Oyuncu ilgi gösterirse aynı varlık bir kez promote edilir.
4. **Saf atmosfer:** ışık/koku/ses; mekanik hak sağlamaz. Uydurulan eski konuşma, büyü, eşya veya politik olgu hiçbir şekilde bu yoldan aklanmaz.

NPC/feature boşluğu, presence yanıtından **önce** sahne anlamına göre ele alınmalı. Her yerde zorla kalabalık yaratılmamalı; ıssız sahne geçerli bir seçim olmalı. Rutin yerel eylemler ve doğal diyaloglar karşılık bulmalı; ambient teklif, oyuncunun kabulü veya inventory transferi sayılmamalı. Local visit/activity state dönüşte tutarlılık ve sınırlı yenilik üretmeli; yeni takvim, hava simülasyonu, ekonomi veya quest motoru açılmamalı.

Bu düzeltme motorun ilgili tur/sahne/validation/persistence noktalarına sınırlı değişiklik gerektirir. Yalnız UI ya da wrapper ile yapılması sorunu gizler. Ekteki tek master prompt bu izinli yüzeyi, korunacak invariant'ları ve **36 turluk gerçek oynanabilirlik kapısını** tanımlar. Daha geniş engine değişikliği için önce somut etki analizi sunulup kullanıcı onayı beklenmelidir.
