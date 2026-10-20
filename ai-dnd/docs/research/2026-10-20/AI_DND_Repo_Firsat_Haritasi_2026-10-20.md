# UNWRITTEN / AI-DND: yedi depodan uyarlanabilir özellikler ve gelecek fırsatları

20 Ekim 2026 · Araştırma ve ürün planlama önerisi · Uygulama, kurulum, migration veya dağıtım talimatı değildir.

## 1. Sonuç: yalnız bugfix değil, seçici ürün geliştirme

Bu depoları yalnız NPC'nin “bilmiyorum” cevabını düzeltmek için değil; kampanya yaratımı, keşif, okunur oyun arayüzü, uzun dönem karakter sürekliliği, kayıt güvenilirliği ve geliştirilebilir içerik için de kullanabiliriz. Fakat burada “kullanmak” öncelikle **tasarım fikrini mevcut AI-DND sahiplerine ve sözleşmelerine uyarlamak** anlamına geliyor. Kod kopyalamak, yeni framework kurmak, farklı motora geçmek veya başka bir servise bağlanmak bu araştırmanın sonucu olarak otomatik yetkili hale gelmez.

En mantıklı yaklaşım üç katman:

- **Yakın:** Oyuncunun bugünkü deneyimini ve geliştiricinin hata ayıklamasını iyileştiren dar eklemeler. Gözlemlenebilirlik, konuşma-state sınırı, yerel model contract testleri, save/retry kanıtları.
- **Orta:** Mevcut sistem doğrulanınca ürün dilimleri. Haritada anlamlı keşif, karakter ilişkisi, kaynaklı hafıza, içerik hazırlama/önizleme ve kampanya özeti.
- **Uzun:** Yazılabilir dünya paketleri, kontrollü rutin/faction simülasyonu, sürüm/alternatif kampanya dalları. Bunlar ayrı kapsam ve kapasite kararı ister.

WorldLines'ın kapalı çekirdeğini veya başka deponun genel mimarisini içeri almak yerine küçük davranışları bağımsız uygulamak, hem teknik borcu hem lisans belirsizliğini azaltır.

## 2. Mevcut projeyle ilişki: yeni bir roadmap ilan etmiyoruz

Bilinen ürün yönü Python'ın mekanik ve kalıcı durum otoritesini koruyan, React üzerinden sunulan, yerel Qwen3:8b ile yaratıcı AI DM deneyimi. Önceki kaynak incelemeleri AI-DND'de `validate_world_updates` ve `VERIFIED_SETTING_FACT`, `CAMPAIGN_FACT`, `PROCEDURAL_PERSONAL_FACT`, `EPHEMERAL_SCENE_TEXTURE` ayrımlarının zaten bulunduğunu gösteriyor. Bu yüzden aşağıdaki fırsatlar “sizde hiç yok” listesi değildir. İlgili mevcut modülün kapsamı, güncel branch ve aktif sözleşme kontrol edilerek güçlendirme veya yeni dilim kararı verilmeli. [Tarihsel doğrulanmış proposal sınırı](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/ai-dnd/game.py#L4750-L4815), [mevcut olgu kategorileri](https://github.com/kadirkayarr-beep/AI-DND/blob/476ba9bd148da18e24cb5dab020c116ba4907445/ai-dnd/local_dialogue.py#L1-L78).

LR00 → LR01 The Open Road → LR02 Living Souls → LR03 Steel & Sorcery → LR04 A World Alive → LR05 Beyond the Horizon ürün yönüyle olası eşleşmeler verilebilir. Ancak 14–16 Ekim belgeleri veya REVIEW metinleri, bugünkü aktif paket ve kabul durumunu kanıtlamaz. **Buradaki yakın/orta/uzun zamanlaması takvim taahhüdü değil; bağımlılık ve risk sırasıdır.** Her kartta verilen kabul kanıtı yeni PASS iddiası değildir.

Özellikle çağrı bütçesi, yeni narrator/owner, save şeması, yeni şehir/lore kaynağı, ekonomik ödül, faction kuralı ve multiplayer eklemek güncel sözleşmeyle ayrıca uzlaştırılmalı. Mevcut taşıma süreci bu araştırmadan bağımsız kalır.

## 3. Kullanıcının ek karşılaştırmasındaki düzeltmeler

Ek metin incelendi. Fikir aramak için yararlı bir başlangıç; fakat şu ifadeler teknik karar için düzeltilmeli:

| Ek metindeki iddia | Kaynak koddan daha doğru sonuç | Karara etkisi |
|---|---|---|
| Tüm projeler OpenAI/Gemini/Claude/Ollama vb. bağlantılara açıktır. | Ortak, çalışır provider desteği yok. llm_RPG'de gerçek Ollama adapter'i; NarrativeEngine'de native Ollama fakat tools/thinking sınırları; Axidify'de OpenAI-compatible/vLLM yolu; DungeonMind normal chat'te sabit GPT-4; dnd_ai_dm GPT-4 quest çağrısı; fedefreak'te LLM yok; WorldLines motor adapter'i açık değil. | “Modüler, o halde kolay entegre edilir” maliyet tahmini için yeterli değil. Qwen3:8b kalitesi hiçbiri için burada ölçülmedi. |
| dnd_ai_dm erişilemedi; muhtemelen Python, ilişkiler/konum/bilgi hafızası ve dünya zamanı tutar. | Depoya erişildi, Python olduğu doğrulandı. Ana `process_command` kullanıcı komutunu kullanmadan quest üretiyor. NPC/combat sınıfları ana döngüye tam bağlı değil; iddia edilen süreklilik doğrulanmadı. | Desteksiz topluluk özetini çalışan ürün özelliği olarak taşımayın. |
| DungeonMind sıkı D&D kurallarını uygular; NPC/quest mekanikleri hayata geçirilmiştir. | Başlangıç karakter kuralları ile chat sistem promptu farklı şeyler. Normal chat'te mekanik reducer yok; explicit inventory, dice, NPC/shared state README roadmap'inde. | Kural motoru değil, karakter/kampanya hazırlama fikri kaynağı olarak değerlendirin. |
| NarrativeEngine'de “bulut yok”; yalnız Node yeterli, ortam kolaydır. | Yerel çalışabilir ama uzak provider seçimi promptu dışarı gönderir. SQLite/native binding, sqlite-vec, ONNX embedding ve model indirimi gerçek bağımlılıklardır; ayrı DB sunucusu gerekmemesi DB olmadığı anlamına gelmez. | Çevrimdışı/privacy ve kurulum iddialarını seçilen provider/platform üzerinden test edin. |
| Axidify için Gemini anahtarı zorunlu; 821+ test mekanikleri güvence altına alıyor. | İncelenen yeni commit OpenAI-compatible/vLLM istemci içeriyor. Test sayısı yürütme/başarı/ürün kabulü kanıtı değil. Somut gate ve mutation riskleri de kaynakta var. | Eski README etiketi yerine sabit commit; gerçek test koşusu ve hedef senaryo kanıtı kullanın. |
| fedefreak motoru “sağlam temel”, herhangi tarayıcı ortamında sorunsuz çalışır. | Deterministik FSM örneği, LLM henüz roadmap. Save/load'da aktif diyalog düğümü geri yükleme sınırı var; ortam çalıştırılmadı. Lisans kişisel/ticari olmayan kullanımla sınırlı. | Kavramsal ilham alınabilir; kopyalanabilir üretim temeli veya garanti kurulum değildir. |
| WorldLines'ın arayüzü yok; Node.js ve JSON ile çalışan açık motor. | React/TypeScript SPA ve Tauri kabuk mevcut. `neonrp` motoru kapalı; UI sadece HTTP API ile konuşuyor. AGPL lisansın kapsamı shell ve örnekler. | UI/authoring örneği incelenebilir, motorun deterministik/replay garantileri koddan doğrulanmış sayılmaz. |
| WorldLines'ta her karakter ayrı agent; bütün modlar aynı. | Multi-agent soul modu ile `orch` data-driven NPC ve `fast` tek ses modu ayrılıyor. | Küçük bir sahne için bütün NPC'leri ayrı model çağrısına çevirmek zorunlu değil. |

Kaynak dayanakları: [dnd_ai_dm ana akış](https://github.com/msadeqsirjani/dnd_ai_dm/blob/db09ab403d234da37446ea4b73e4c3d349c40ece/core/game_manager.py#L1-L24), [DungeonMind chat](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/src/backend/orchestrator/main.py#L53-L83), [DungeonMind roadmap](https://github.com/guzmanvitar/dungeonmind-llm-rpg-adventure/blob/f1eb7dd1dfdcb0e01791870167eb98dd77fa3bd9/README.md#L134-L170), [NarrativeEngine Ollama body](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/utils/llmApiHelper.ts#L340-L412), [WorldLines UI](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/package.json#L1-L43), [WorldLines lisans kapsamı](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/LICENSE#L18-L26), [fedefreak lisansı](https://github.com/fedefreak92/dungeon-master-ai-project/blob/38b655aa432d73eec78eebcb0dbf0442f7491ab5/LICENSE#L1-L37).

Lisans konusunda ek düzeltme: DungeonMind README MIT derken LICENSE GPLv3; Axidify için açık permissive lisans doğrulanmadı. Ek raporda bu sınırlar görünmediği için “modül olarak alabiliriz” sonucu otomatik çıkarılamaz. Bu bir hukuki kesinlik değil, kopyalamadan önce çözülmesi gereken kaynak kontrolüdür.

## 4. Öncelik A: yakın dönem, küçük ve doğrulanabilir kazanımlar

### A1. Oyun içi teşhis: anlatı, işlem sonucu ve kaynak ayrı görülsün

**Kaynak / kanıt:** WorldLines React event tipleri turn sequence, commit, soul active reason ve trace bus taşır; UI `/traces` ve `/trace` okur. NarrativeEngine single-flight/recovery testleri commit tekrarlarını denetler. Bunlar gerçek kod; WorldLines sunucunun replay doğruluğu açık değil. [Event yüzeyi](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/src/play/stage/events.ts#L66-L136), [single-flight test](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/turn/__tests__/commitSingleFlight.test.ts#L69-L126).

**AI-DND uyarlaması:** Mevcut debug/receipt alanları varsa yeni sistem değil, bunları okuyan açılır geliştirici paneli. “Oyuncu niyeti → kullanılan NPC/fact kimlikleri → çözülen işlem → gate nedeni → model/fallback → kalıcı sonuç” zinciri. Normal oyuncuya yalnız gerekli sonuç gösterilir; gizli NPC iç sesi veya spoiler debug verisi oyuncu ekranına sızmaz.

**Önkoşul / çatışma:** Güncel receipt ve API sahipleri; redacted debug erişimi. UI tasarımını yeniden yazmaz. LR00 veya uygun sunum dilimine aday, güncel paket kapsamı kontrol edilmeli.

**Maliyet / kabul:** Düşük-orta; ek model çağrısı gerektirmez. Aynı tur için API ve görünen panel aynı sonucu göstermeli; ret sebebi izlenmeli; geç gelen A kampanyası cevabı B'ye görünmemeli; sır metni debug çıktısından sızmamalı. Lisans: WorldLines kodu AGPL; bağımsız panel tasarımı tercih. NarrativeEngine MIT şartları korunur.

### A2. Yerel-model uyumluluk paketi ve Qwen sözleşme testleri

**Kaynak / kanıt:** llm_RPG provider seçimi ve Ollama HTTP adapter'i; NarrativeEngine model listesi/native chat; Axidify OpenAI-compatible yol. Uyumluluk yüzeyleri gerçek ama eşdeğer değil. [llm_RPG Ollama](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/llm/providers/ollama.py#L20-L48), [NarrativeEngine adapter](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/utils/llmApiHelper.ts#L55-L108).

**AI-DND uyarlaması:** Qwen3:8b'yi değiştirmeden mevcut provider katmanı için model/version, structured output, thinking, timeout, cancellation, error ve token budget test matrisi. Cloud provider eklemek ayrı ürün/privacy kararı; sırf adapter var diye gerekmiyor.

**Önkoşul / çatışma:** Mevcut çağrı bütçesi ve retry kuralları korunmalı; ikinci adapter/narrator yaratılmamalı. Kurulu Ollama sürümü ayrıca doğrulanmalı.

**Maliyet / kabul:** Düşük-orta mühendislik, gerçek model koşusu sırasında yerel kaynak maliyeti. Türkçe diyalog, bozuk JSON, string-false, düşünme metni, olmayan item, timeout ve restart senaryoları; p50/p95 gecikme ve gate oranı önce/sonra. “Model yanıt verdi” başarı için yeterli değil. llm_RPG/NarrativeEngine MIT; Axidify kod kopyası lisans netleşmeden yok.

### A3. Güvenli kayıt ve retry: yeni event store'dan önce mevcut kayıt sınırını sağlamlaştır

**Kaynak / kanıt:** llm_RPG temp+replace snapshot; NarrativeEngine pending commit, single-flight, başarısız arşiv cevabını kurtarma ve campaign guard gerçek. Tam event-sourcing veya tek ACID transaction kanıtı değiller. [Snapshot](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/save_load.py#L61-L96), [pending commit](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/turn/pendingCommit.ts#L296-L319), [campaign guard](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/turn/tracks/guarded.ts#L1-L27).

**Uyarlama:** Mevcut AI-DND idempotency/save yolunu bu test örnekleriyle denetle; varsa mevcut çözümü koru. Yeni schema veya migration'ı sırf başka repo kullanıyor diye açma.

**Önkoşul / çatışma:** Geçerli save sözleşmesi, crash semantics, rollback sahipliği. Mevcut taşıma bitmeden veri geçişi yapılmaz.

**Maliyet / kabul:** Düşük-orta test/iyileştirme; bütün kayıt mimarisini değiştirmek yüksek. Aynı request iki kez, farklı payload aynı ID, response kaybı, commit öncesi/sonrası crash, save/reload ve kampanya değişimi testlerinde exact gold/item/HP ve journal eşitliği. Kaynaklar MIT; bu test fikrinin uygulanması mevcut veriye otomatik değişiklik yetkisi vermez.

### A4. Doğal NPC konuşması + doğrulanmış eylem sonucu

**Kaynak / kanıt:** llm_RPG küçük action allowlist ve kilitli sırları bağlam dışında tutma; Axidify engine-resolved interaction→narration. Prose ile action ayrı olabilir fakat her ikisinde de reddedilen işlemi önceden anlatma riski kalıyor. [Protokol](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/dialog_protocol.py#L108-L190), [sırlar](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/secrets.py#L32-L105), [önce çözüm](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/turn_service.py#L252-L320).

**Uyarlama:** Mevcut provenance ve proposal yollarını bir NPC pilotunda kullan; sohbetin kelimelerini değil, kalıcı olgu/işlem yetkisini sınırla. Ancak yaratıcı geleceğe dönük kampanya önerisini sahte gerçekleşmiş olaydan ayır: bütün yaratımı yasaklama.

**Önkoşul / çatışma:** Güncel üretim zarfı ve konuşma/mutation owner'ları; faz kapsamı ve model çağrı bütçesi. Geniş lore gate kaldırma yerine shadow log ve tek sahne pilotu.

**Maliyet / kabul:** Orta; ek çağrı gerektirmeyen sözleşme mümkün, ölçülmeli. Masum ortak sözcük, bilinmeyen olgu, sır, sahte geçmiş, item transferi, tekrar deneme, iki NPC/iki kampanya testleri; doğal Türkçe insan değerlendirmesi ve yetkisiz state sıfır. MIT protokol fikri; Axidify kodu için lisans belirsizliği.

## 5. Orta ve uzun dönem fırsat kartları

Aşağıdaki kartlarda uygulanmış kaynak özellikleri ile AI-DND için önerilen yeni davranışlar ayrı belirtilmiştir. Olası LR eşleşmeleri aktif paket ilanı değildir.

### B1. Uzun kampanya hafızası: olay, inanç ve söylenti ayrı tutulsun

**Kaynak / kanıt:** llm_RPG NPC başına kısa geçmiş + top-k anı seçimi; NarrativeEngine campaign_id ile vector arama, knownBy kapsamı, arşiv/recovery ve bütçeli retrieval; WorldLines soul başına kısa/uzun bellek dosyaları. İlk ikisinde gerçek kod mevcut; WorldLines'ın belleği nasıl seçtiği kapalı çekirdekte. [llm_RPG hafıza](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/npc_memory.py#L26-L90), [knownBy](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/campaign-state/knowledgeScope.ts#L119-L169), [vector kapsamı](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/server/lib/vectorStore.js#L334-L403).

**Uyarlama:** Mevcut memory/provenance alanlarına source_event, bilen kişiler ve doğrulanmış/söylenti/kişisel inanç anlamını oturt. Oturum özeti gerçek olaylardan üretilsin; oyuncunun “kral bana kaleyi verdi” cümlesi geçmiş olay haline gelmesin. NPC inancı yanlış olabilir; yanlış inancın varlığı ile dünyada gerçekten olan şey ayrı kaydedilir. Tüm sohbeti her seferinde modele vermek yerine son etkileşim + ilgili doğrulanmış anılar.

**Önkoşul / çatışma:** Mevcut kayıt sahibinin olay kimlikleri ve NPC/campaign izolasyonu; şema değişikliği gerekiyorsa ayrı karar. LR02 için aday; güncel memory zaten sağlıyorsa yalnız test ve görünürlük iyileştirmesi. İngilizce/ASCII tokenizer aynen kopyalanmamalı.

**Maliyet / kabul:** Basit top-k yaklaşımı orta; vector DB/model ekleme orta-yüksek. Önce mevcut yapı ile başla, embedding ancak ölçülen retrieval sorunu varsa. Beş oturum sonra eski verilen söz hatırlanmalı; hiç bulunmadığı sahnenin sırrını başka NPC bilmemeli; kampanya değişimi sızmamalı; Türkçe özel adlar ve ekler bulunmalı; silinmiş/ret edilmiş anlatı canon'a dönmemeli. MIT kaynakların koşulları korunur; WorldLines dosyaları doğrudan alınırsa AGPL değerlendirmesi gerekir.

### B2. Lore içe aktarma ve editör onaylı dünya hazırlama

**Gerçekte var:** NarrativeEngine metni background, locations, cultures, factions, threats, NPC ve diğer başlıklara LLM ile ayırıyor; kategori izin listesi ve JSON parsing var. Ayrı inceleme ekranında başlık/kategori değiştiriliyor, parçalar tek tek seçiliyor, yalnızca kabul edilenler draft’a birleştiriliyor; ham kaynak da callback’e aktarılıyor. Yardımcı model yoksa elle sınıflandırma yoluna düşüyor. Markdown dışa aktarımı mevcut.

**Sınır:** Sınıflandırılmış metin doğrulanmış kanon değildir. Bilinmeyen kategoriyi background’a çevirmek ve başlığı/gövdeyi yüzeysel kontrol etmek, entity referansları veya çelişkileri doğrulamaz. Fraksiyon başlığı bulunması siyasi/ekonomik simülasyon bulunduğunu göstermez.

**AI-DND uyarlaması:** Mevcut authoring/veri hattında “yapıştır → taslak parçalar → fark görünümü → onayla” akışı. Python/Pydantic doğrulama, React review paneli; Qwen3:8b yalnızca sınıflandırma/öneri rolünde. Dünya üretimini her oyun turunun maliyetine eklemeyin. Mevcut karanlık RPG UI’sına küçük panel, yeniden tasarım değil.

**Önkoşul / karmaşıklık:** Draft–published ayrımı, kalıcı entity ID, kaynak/provenance ve schema version; **orta**. LR00/authoring temeli veya LR05 içerik üretimi adayı.

**Kabul kanıtı:** Türkçe 20 karma lore örneğinde kaynak metin korunmalı; reddedilen bölüm yayımlanmamalı; hatalı JSON ve model yokluğu elle düzenlemeyi engellememeli; aynı import iki kez uygulanınca yinelenen entity oluşmamalı; taslak canlı kampanyayı kendiliğinden değiştirmemeli.

Kaynak: [Sınıflandırıcı L80–122](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/lore/worldLoreImport.ts#L80-L122), [review/merge L26–99](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/components/LoreImportReviewModal.tsx#L26-L99), [export L21–66](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/lore/worldLoreExport.ts#L21-L66).


**Lisans sınırı:** NarrativeEngine-P MIT; doğrudan kod aktarımında bildirimler korunmalı, örnek dünya/görsel/üçüncü taraf içerik hakları ayrıca kontrol edilmeli. Fikir değerlendirmesi kurulum veya kopyalama izni değildir.

### B3. Veriyle yazılan, doğrulanabilir macera paketleri

**Değer / aday faz:** Yeni han, mağara, NPC ve görev içeriğini motor koduna dokunmadan ekleme; kısa kampanyalarla sistemi büyütme. LR01 Open Road ve ileride LR05 Beyond Horizon.

**Kodda gerçekten var:** Axidify, ayrı YAML dosyalarından senaryo, konum, NPC, görev ve dükkân nesneleri yüklüyor; her yüklemede yeni nesneler kuruyor. Codec bilinmeyen alanı reddediyor. Testler sahne/çıkış referanslarını, tanımsız eşya ID'lerini, başlangıçtan sahnelere ulaşılabilirliği ve yüklemeler arası mutable-state sızıntısını kontrol ediyor. [Yükleyici](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/scenario_loader.py#L30-L86), [codec](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/src/data_codec.py#L57-L102), [paket testleri](https://github.com/Axidify/ai-dnd-rpg/blob/395f86a441984c9a2c91272ef2a502f2553d93e3/tests/test_scenario_loader.py#L38-L130).

**Uyarlama:** Mevcut AI-DND içerik formatı varsa yeni format yerine onun şemasına paket manifesti, sürüm, bağımlı ID ve kuru doğrulama eklemek. Python doğrular; React gelecekte paket önizleme ve hata listesi sunabilir. Qwen yalnız taslak içerik üretir; yayımlanacak veri deterministik doğrulamadan geçer. Görsel editör bu depoda kanıtlanmış hazır özellik değil, önerilen sonraki katmandır.

**Önkoşul / karmaşıklık:** İçerik ID politikası, mevcut import yolu, mekanik ve anlatı alanlarının ayrımı. Dosya tabanlı pilot orta; görsel editör ve canlı kampanya migration'ı yüksek.

**Kabul kanıtı:** İkinci küçük senaryo uygulama kodunu değiştirmeden yüklenir; kırık çıkış, eksik NPC/eşya, mükerrer ID reddedilir; paket iki kampanyada birbirini etkilemez; başarısız import state'i değiştirmez.

**Taşınmayacak ayrıntı:** `from_data` her scalar için strict tip doğrulayıcı değildir; unknown-field kontrolü tam schema validation demek değildir. llm_RPG'nin JSON modül yükleme fikri de yararlı, ama “atomic install” açıklaması tam transaction garantisi sayılmamalı: placement ve beat adımlarında tüm yan etkiler için undo kaydı görünmüyor, structures ayrı kurulur. [Modül kurulumu](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/dm_modules.py#L134-L225), [pack kurulumu](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/module_packs.py#L133-L155).


**Lisans sınırı:** llm_RPG MIT; Axidify açık permissive lisansı doğrulanmadı. Axidify yaklaşımı bağımsız uygulanmalı, kod kopyası lisans netleşmeden yapılmamalı.

### B4. Ulaşım türüne göre rota ve zaman önizlemesi

**Gerçekte var:** NarrativeEngine’in bağımsız JS modülü hücre arazi maliyetinden A* rota çıkarıyor; yürüyüş, binek, araba, tekne için geçilemez biyomlar farklı. Arama tavanı, başarısızlık nedenleri, birikimli maliyet ve gün hesabı kodda. Bu yalnızca “harita yapacağız” vaadi değil.

**Sınır:** Rota hesaplamak yolculuğu güvenli biçimde commit etmek değildir. Bu fonksiyon state yazmaz. Kendi özel maliyet tablosu D&D kuralı sayılmaz. Hedefi yakın geçilebilir hücreye kaydırma davranışı AI-DND’de kullanıcı niyetini değiştirebilir; olduğu gibi kopyalamayın.

**AI-DND uyarlaması:** Mevcut seyahat otoritesine Python saf rota servisi ve React “rota/süre/engel” önizlemesi eklenebilir. Qwen yolu seçen veya süreyi onaylayan otorite değil, onaylanmış sonucu anlatan katman olur. İlk sürümde yeni raster kıta yerine mevcut location-edge grafı yeterli olabilir.

**Önkoşul / karmaşıklık:** Kanonik bağlantılar, mesafe birimi, ulaşım modu, yolculuk ve zaman sözleşmesi; graf önizlemesi **orta**, tam hücresel/prosedürel dünya **yüksek**. LR01 Open Road adayı.

**Kabul kanıtı:** Aynı dünyada araba dağ geçidini kullanamamalı, tekne denizi kullanabilmeli; engellenmiş rotada zaman/konum değişmemeli; aynı rota onayı tekrarı ikinci hareket yaratmamalı; UI tahmini ve backend gerçek maliyeti eşleşmeli. Sadece rota hesaplaması ek LLM çağrısı üretmemeli.

Kaynak: [Mod/maliyet L37–63](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/public/bundled-mods/worldmap/pathfinder.js#L37-L63), [gerçek arama L264–399](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/public/bundled-mods/worldmap/pathfinder.js#L264-L399).


**Lisans sınırı:** NarrativeEngine-P MIT; doğrudan kod aktarımında bildirimler korunmalı, örnek dünya/görsel/üçüncü taraf içerik hakları ayrıca kontrol edilmeli. Fikir değerlendirmesi kurulum veya kopyalama izni değildir.

### B5. Söylenti haritası ve kademeli keşif

**Gerçekte var:** NarrativeEngine `rumoured`/`secret` yerlerin kesin konumunu ayırıyor; söylentiyi yaklaşık alan olarak hesaplıyor; ziyaret/birebir gözlem sonucunda bilinirlik yükseltiyor. WorldLines oyun haritası ise dünya düğümleri/yollarından kasaba alt-konumlarına inebilen gerçek React/SVG görünümü içeriyor.

**Sınır:** NarrativeEngine helper’ı istemciye gelen gizli koordinatları ortadan kaldırmıyor; çizimde saklamak erişim denetimi değildir. WorldLines’ın ayrı `WorldMapCanvas` gözlem ekranı lokasyonları reason metninden çıkarıp halka halinde dizer ve `edges=[]` kullanır; bunu gerçek coğrafya veya rota motoru sanmayın. Oyun içi `MapPanel` farklı, authored harita yüzeyidir.

**AI-DND uyarlaması:** “Duydum / yerini biliyorum / gittim” üçlüsü, kesin olmayan söylenti bölgeleri ve kasaba→han/çarşı detay seviyesi. Python görünürlük projeksiyonu yalnızca izinli konum verisini React’e gönderir. Qwen söylenti anlatabilir fakat keşif bayrağını tek başına yazamaz.

**Önkoşul / karmaşıklık:** Oyuncu/kampanya keşif durumu, gözlem kaynak event’i, mevcut knowledge/provenance hattı; **orta**. LR01 + LR02 adayı.

**Kabul kanıtı:** Gizli koordinat istemci ağ cevabında bulunmamalı; söylenti kesin pin olmamalı; bir NPC’nin söylediği yer otomatik “ziyaret edildi” olmamalı; yakınlaşma/uzaklaşma oyuncunun gerçek konumunu değiştirmemeli.

Kaynak: [knowledge.js L1–20](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/public/bundled-mods/worldmap/knowledge.js#L1-L20), [WorldLines katmanlı harita L99–125](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/src/play/stage/MapPanel.tsx#L99-L125), [ayrı gözlem tuvali L125–147](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/src/local/WorldMapCanvas.tsx#L125-L147).


**Lisans sınırı:** NarrativeEngine-P MIT; doğrudan kod aktarımında bildirimler korunmalı, örnek dünya/görsel/üçüncü taraf içerik hakları ayrıca kontrol edilmeli. Fikir değerlendirmesi kurulum veya kopyalama izni değildir. WorldLines UI/örnekler AGPL-3.0-or-later; neonrp ayrı kapalı çekirdek. Bağımsız tasarım tercih; doğrudan bileşen/prompt aktarımı lisans değerlendirmesi gerektirir.

### B6. NPC ve fraksiyon ilişkileri için içerik yazarlığı grafı

**Gerçekte var:** WorldLines StudioCanvas ilişki, harita ve hikâye verisini yükler; ilişki çizgisi oluşturma yön/strength/description alanları yaratır. Düğüm konumu ve viewport ile 800 ms gecikmeli kayıt vardır; eski kayıt cevabı UI durumunu yeni canvas’a taşımamak için sürüm kontrolü kullanılır. Bu uygulanmış istemci kodudur.

**Sınır:** İstemci kayıt isteği sunucuda atomik doğrulama garantisi vermez. Fraksiyon diplomasisi/ekonomi motoru doğrulanmış değil; graf görselleştirmesi ile simülasyonu ayırmak gerekir. Görsel çizgi değişikliği oyun ilişkisini doğrudan değiştirmek zorunda değildir.

**AI-DND uyarlaması:** İlk olarak salt okunur kişi–fraksiyon–mekân ilişkileri, sonra GM/yazar için draft düzenleme. React tarafı yakın, Python mevcut entity/ilişki API’sinden beslenebilir. Qwen yalnızca önerilen kenar/açıklama üretsin; “kanonik ilişki”, “kişisel inanç” ve “oyuncunun bildiği” farklı görünümler olsun.

**Önkoşul / karmaşıklık:** Stable ID, yönlü ilişki şeması, draft publish izni ve görünürlük; salt okunur **düşük–orta**, editör **orta**. LR02/LR04 içerik araçları adayı.

**Kabul kanıtı:** NPC adını değiştirmek bağlantıları koparmamalı; gizli fraksiyon üyeliği oyuncu görünümüne sızmamalı; kaydetme hatası başarı görünmemeli; iki editörde eşzamanlı değişiklik sessizce ezilmemeli.

Kaynak: [yükleme L105–164](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/src/local/StudioCanvas.tsx#L105-L164), [kayıt ve ilişki üretimi L189–269](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/src/local/StudioCanvas.tsx#L189-L269).


**Lisans sınırı:** WorldLines UI/örnekler AGPL-3.0-or-later; neonrp ayrı kapalı çekirdek. Bağımsız tasarım tercih; doğrudan bileşen/prompt aktarımı lisans değerlendirmesi gerektirir.

### B7. Karakter geçmişi ve olası gelişim çizgisi editörü

**Gerçekte var:** WorldLines SoulArcCanvas memory, wound, desire, bond, turning, choice, ending tiplerini destekler; düğüm/bağ ekleme, JSON serialize ve persist callback kodu var.

**Sınır:** Bu bir authoring aracı, arc düğümlerinin oyunda güvenilir tetiklenmesini kanıtlayan açık motor değil. “Ending” düğümü oyuncunun geleceğini zorunlu kılan senaryo rayına dönüşmemeli.

**AI-DND uyarlaması:** NPC yazar ekranında “geçmişte gerçekleşmiş olay” ile “olası gelişim / koşullu kanca” ayrı. Qwen3:8b’nin karaktere ait kısa motivasyon kartını seçili/ilgili düğümlerden oluşturmak; bütün grafı her tur prompt’a göndermemek. Oyuncu seçimlerini tahmin edip kanonlaştırmamak.

**Önkoşul / karmaşıklık:** Actual/candidate ayrımı, olay referansları, mevcut NPC hafıza bağlantısı; authoring **orta**, otomatik güvenli tetikleyici **yüksek**. LR02 Living Souls / LR05 adayı.

**Kabul kanıtı:** Olası ihanet yalnızca plan olarak kalmalı; gerçekleşmemiş geçmiş NPC hafızasında gerçek diye görünmemeli; oyuncu yolu reddedince alternatifler kapanmadan oyun sürmeli; ilgili 3–5 düğümle bağlam bütçesi ölçülmeli.

Kaynak: [tipler/parsing L25–54](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/src/local/SoulArcCanvas.tsx#L25-L54), [persist ve düzenleme L92–137](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/src/local/SoulArcCanvas.tsx#L92-L137).


**Lisans sınırı:** WorldLines UI/örnekler AGPL-3.0-or-later; neonrp ayrı kapalı çekirdek. Bağımsız tasarım tercih; doğrudan bileşen/prompt aktarımı lisans değerlendirmesi gerektirir.

### B8. Model çağrısı gerektirmeyen günlük NPC rutinleri

**Değer / aday faz:** Demircinin gündüz atölyede, akşam handa bulunması; NPC'nin yalnız konuşulduğunda var olan bir figür olmaması. LR02 Living Souls adayı.

**Kodda gerçekten var:** Meslek/archetype bazlı saat–aktivite–hedef listeleri ve gece taşması hesaplanıyor. Heuristic karar yolu önce acil açlık/yorgunluğa, sonra rutine bakıyor; aktivite bilgisi hareketle beraber taşınıyor. İşyerine varışta çalışma, müzik ve işyeri yerleşimi uygulanıyor. [Rutin seçimi](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/characters/schedules.py#L118-L153), [gerçek karar yolu](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/llm/providers/heuristic.py#L153-L183), [aktivite icrası](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/activities.py#L97-L148).

**Uyarlama:** Mevcut NPC simülasyonunu genişletip ilk etapta üç NPC ve iki zaman dilimiyle sınırlayın. Python aynı hareket/state doğrulama yolunu kullanır; React NPC kartında yalnız gözlemlenebilir aktiviteyi gösterir. Qwen rutin kararı vermek yerine mevcut durumu karakter sesiyle anlatır. Sohbet sürerken NPC'nin sessizce sahneden ayrılmaması için encounter kilidi gerekir.

**Önkoşul / karmaşıklık:** Tek oyun saati, konum/movement otoritesi, savaş/quest/acil durum önceliği; orta, pathfinding ve off-screen simülasyon eklenirse yüksek.

**Kabul kanıtı:** Gece yarısı doğru rutin; kapalı rota için tanımlı fallback; uyuyan NPC'nin aynı anda dükkânda bulunmaması; save/load ve hızlı zaman atlama tutarlılığı; 100 rutin turunda model çağrısı sıfır. Oyuncunun erişmesi gereken görev NPC'si rutinden dolayı kalıcı kilitlenmez.


**Lisans sınırı:** llm_RPG MIT. Kendi rutin ve içerik kuralları AI-DND’ye aynen taşınmaz; bildirimler ve üçüncü taraf hakları korunur.

## Uzun dönem: ayrı kapsam ve kapasite kararı isteyenler

### C1. Oyun sürümü, kayıt sürümü ve alternatif geçmişi birbirinden ayır

**Kaynak / kanıt:** NarrativeEngine durable commit ve arşiv kurtarma; WorldLines UI commit tabanlı rollback isteği gönderiyor. Bu, açık kaynak bir deterministik event-sourcing motoru bulunduğu anlamına gelmez. [Rollback istemcisi](https://github.com/LudicDynamics/WorldLines/blob/4ee61a368c381f2f8db43b4454f088a7388693bf/ui/src/play/stage/stageClient.ts#L64-L83).

**Uyarlama:** İlk ürün hedefi güvenli devam etme ve anlaşılır kayıt özeti. Sonraki ayrı hedef bir sahneden alternatif kampanya dalı açma olabilir; ana geçmişi sessizce değiştiren undo değil. Kayıt formatı version alanı, içerik paketi sürümü, model sürümü ve campaign branch farklı kavramlar olarak ele alınmalı.

**Önkoşul / çatışma:** Save migration ve event otoritesi; RNG kayıt/replay stratejisi; kullanıcıya hangi branch'te olduğunu açıkça gösterme; otomatik eski save dönüştürme yetkisi yok. Mevcut LR00 save sağlamlaştırmasının yerine geçmez, uzun vadeli ayrı paket.

**Maliyet / kabul:** Snapshot güvenliği orta; gerçek branch/replay yüksek. Aynı event dizisinden state hash eşitliği, eksik event'te açık hata, branchler arası item/quest sızmaması ve eski save'in bozulmaması. Model prose'unun birebir tekrar üretimi ile mekanik state replay aynı başarı ölçütü değildir. WorldLines AGPL UI + kapalı motor nedeniyle fikir bağımsız uygulanmalı.

### C2. Oyuncu dışındaki ilişkiler ve sınırlı faction gündemleri

**Değer / aday faz:** Dünya yalnız oyuncu etrafında dönmez; NPC arkadaşlığı/husumeti, fraksiyonun toparlanma veya güçlenme hedefi yeni görev bağlamları üretir. NPC ilişkileri LR02, fraksiyon gündemleri LR04 World Alive adayı.

**Kodda gerçekten var:** Sosyal grafik NPC çiftlerinin ilişkisini değiştirip eşik geçişlerini bir defa duyuruyor. Fraksiyon gündemi strength/stores alanlarını, diplomasi eşiklerini ve recover/dominate geçişlerini güncelliyor; gündem/ilişki/latch state'i serileştiriliyor. Günlük turn pipeline iki sistemi çağırıyor. [Sosyal grafik](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/social_graph.py#L38-L111), [fraksiyonlar](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/faction_agendas.py#L70-L170), [pipeline bağlantısı](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/engine/turn_pipeline.py#L205-L239).

**Uyarlama:** Önce mevcut ilişki/olay yapısında küçük, sınırlandırılmış simülasyon. Her değişim mevcut canonical update kapısından geçer; Qwen sonucu anlatır, rastgele savaş ilan ederek state yazmaz. React oyuncunun bildiği ilişki ve haberleri gösterir; bütün sosyal grafiği açmaz.

**Önkoşul / karmaşıklık:** Rutinlerden sonra oyun-günü tekliği, olay kaynak kimliği, sonuçların görevlere etkisi, NPC kimlikleri; orta-yüksek. Büyük ekonomi veya çok-agent LLM ağı şart değil.

**Kabul kanıtı:** Aynı günün tekrar işlenmesi çift etki yaratmaz; aynı eşik bir kez haber olur; oyuncunun henüz duymadığı olay prompt'a gitmez; aynı başlangıç ve RNG durumu tekrarlanabilir; kayıttan dönüş ilişkiyi korur. Kaynak eşik/kalıcılık testleri yazılı, çalıştırılmadı: [fraksiyon testleri](https://github.com/gddickinson/llm_RPG/blob/ad760b3c52db072188e1a79cd1cb2983eb8321e6/tests/test_faction_agendas.py#L65-L125).

**Sınır:** “Heuristic deterministic” açıklaması her kayıt yüklemesinde replay garantisi değildir; social graph rastgele çift seçer. Faction etiketinden otomatik düşmanlık üretme kuralını aynen almak karakter derinliğini azaltabilir. Latch temizliği/histerezis ayrıca tasarlanmalı.


**Lisans sınırı:** llm_RPG MIT; Axidify açık permissive lisansı doğrulanmadı. Axidify yaklaşımı bağımsız uygulanmalı, kod kopyası lisans netleşmeden yapılmamalı.

### C3. Bütçeli sahne-dışı yaşam ve zaman atlama özeti

**Gerçekte var:** NarrativeEngine sadece uygun/doldurulmuş NPC’leri aynı bölge, ortak fraksiyon veya ilişki yakınlığıyla seçer. Olasılıksal tick hedef ilerlemesi, hedef çakışması, kişilik/skill değişim önerileri ve görünürlüğe göre digest içerir. Normal temel tick yolu LLM çağırmadan işler; zaman atlama yolu durum simülasyonundan sonra ek toplu anlatım çağrısı yapabilir.

**Sınır:** Bu tam günlük iş/uyku/alışveriş rutini veya fraksiyon ekonomisi değil, bütçeli NPC hedef ilerlemesidir. Varsayılan RNG Math.random; tekrar üretilebilirlik kendiliğinden gelmez. Zaman atlama tespiti İngilizce regex’ler kullanır; Türkçe “üç gün bekliyorum” için hazır çözüm değildir.

**AI-DND uyarlaması:** Mevcut world clock ve validator üzerinden az sayıda ilgili NPC hedefini ilerletme; kalan dünya özetlenmiş/uykuda. İlk pilot tek han ve 3 NPC; daha sonra fraksiyon baskı saatleri. Qwen3:8b yalnızca kabul edilmiş değişimlerin kısa “sen yokken” anlatımını üretir. Türkçe niyet ayrıştırması, doğrulanmış zaman ilerlemesinin yerine geçmez.

**Önkoşul / karmaşıklık:** Güvenilir campaign time, bir kez işlenen zaman event’i, hedef durumları, kayıtlı seed/roll ve görünürlük; **yüksek**. LR04 World Alive adayı; günlük rutin sistemi ayrıca tasarlanmalı.

**Kabul kanıtı:** Aynı zaman event’i retry sonrası iki kez ilerlememeli; ölü/uygunsuz NPC aktif olmamalı; oyuncu şakada “bir yıl sonra” deyince dünya atlamamalı; yalnız yetkili elapsed-time event’i etkili olmalı; gizli gelişme oyuncuya açıklanmamalı; NPC sayısı artınca tur başına LLM çağrıları doğrusal artmamalı.

Kaynak: [yakınlık ve fraksiyon filtresi L20–73](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/npc/agency/agencyHeartbeat.ts#L20-L73), [tick L77–177](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/npc/agency/agencyEngine.ts#L77-L177), [zaman atlama ve anlatım L330–367](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/npc/agency/agencyEngine.ts#L330-L367), [İngilizce parser L34–107](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/npc/agency/agencyTimeskipRun.ts#L34-L107).


**Lisans sınırı:** NarrativeEngine-P MIT; doğrudan kod aktarımında bildirimler korunmalı, örnek dünya/görsel/üçüncü taraf içerik hakları ayrıca kontrol edilmeli. Fikir değerlendirmesi kurulum veya kopyalama izni değildir.

### C4. Önce veri paketleri, sonra kontrollü mod ekosistemi

**Gerçekte var:** NarrativeEngine native mod JS dosyalarını tarayıcıda dinamik import eder; bildirilen hook export’larını çözer, CSS ekler/kaldırır, mod başına cache tutar. Native trust kaydı ayrı modülde bulunur. Yani gerçek bir uzantı yüzeyi var, fakat kopyalanacak küçük bir JSON loader’dan çok daha geniş sistemdir.

**Sınır:** Native kod uygulama sayfasının yetkileriyle çalışır; modun varlığı sandbox güvenliği kanıtı değildir. Kullanıcı onayı alınmış olması kodun güvenli olduğunu göstermez. Prompt interceptor’ları dünyaya ve model davranışına geniş etki yaratabilir.

**AI-DND uyarlaması:** İlk aşamada çalıştırılabilir JS/Python modları yerine versioned, declarative NPC/yer/eşya/karşılaşma paketleri. Mevcut Python validator ile import preview/çatışma raporu, React paket yöneticisi. Qwen çalışma sırasında mod talimatlarını üst düzey sistem talimatına yükseltmemeli. Tam mod SDK’sı yalnız gerçek eklenti ihtiyacı görülünce.

**Önkoşul / karmaşıklık:** Paket sürümü, namespace, content schema, bağımlılık/çatışma ve migrate/disable davranışı; veri paketi **orta**, native SDK **yüksek**. LR05 Beyond Horizon adayı.

**Kabul kanıtı:** Bilinmeyen alan/izin ve ID çakışması sessiz kabul edilmemeli; paket devre dışı bırakılınca eski save açılmalı veya açık migration hatası vermeli; taslak import kanonu değiştirmemeli; veri paketi hiçbir kod çalıştırmamalı.

Kaynak: [gerçek import/hook L195–275](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/mods/native/nativeLoader.ts#L195-L275), [yetki açıklaması L20–24](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/mods/native/nativeLoader.ts#L20-L24), [trust kayıt modülü L31–70](https://github.com/Sagesheep/NarrativeEngine-P/blob/a5020b93fccd56ea91a5b1b2dd30053b35c5a66b/src/services/mods/nativeTrustStore.ts#L31-L70).


**Lisans sınırı:** NarrativeEngine-P MIT; doğrudan kod aktarımında bildirimler korunmalı, örnek dünya/görsel/üçüncü taraf içerik hakları ayrıca kontrol edilmeli. Fikir değerlendirmesi kurulum veya kopyalama izni değildir.

## 6. Yalnız ilham veya şimdilik kaçınılacak yollar

- **Her NPC için sürekli LLM ajanı:** WorldLines soul mimarisi ilginç ama açık motor güvencesi yok ve çok sayıda çıkarım gecikme/maliyet doğurabilir. Önce yalnız sahnedeki NPC'ler ve deterministic zaman/rutin; arka plan agent toplumu ancak ölçülmüş ihtiyaç ve ayrı bütçeyle.
- **Tüm world state'i konuşmadan çıkarmak:** NarrativeEngine automatic inventory scanner gibi hatlar doğal anlatı sunar fakat yetkisiz eşya/kanıt üretimini kalıcılaştırabilir. İlham olarak bile “kolay state yönetimi” diye alınmamalı.
- **Gizli bilgiyi UNKNOWN FACTS listesiyle aynı modele vermek:** Rol talimatı, bilgi izolasyonunun yerine geçmez. Özellikle ayrı NPC konuşması için sır metni filtrelenmeli.
- **Sosyal ilişkiyi her mesajda artırmak veya birkaç başarısızlıktan global game over üretmek:** llm_RPG ve Axidify örnekleri küçük oyun tasarım kararlarıdır; doğal uzun kampanya ilişkisini garanti etmez. Ölçülü, olay-kaynaklı ve NPC'ye özgü değişim daha uygun.
- **Kampanya lore'unu internetten otomatik topluca içeri almak:** DungeonMind scraping/RAG hattı hazırlık fikri sağlar; fakat izin, telif, edition, setting ve kaynak pinleri çözülmeden AI-DND'nin otoritesine eklenmemeli. Önce mevcut izinli kaynakların indekslenmesi.
- **Yedi repo arasında framework alışverişi:** Pygame, Flask, Node, SQLite-vec, Tauri ve çok-agent runtime'ı bir araya getirmek özellik değil bakım maliyeti üretir. Mevcut Python+React katmanında en küçük bağımsız dilim tercih.
- **Tam D&D uygunluğu veya sorunsuz Replit kurulumu varsaymak:** Hiçbirini canlı çalıştırmadık. Basit kod/README, hedef platform ve kurallar için kabul kanıtı değildir.

## Fırsatların tek bakışta sırası

| Öncelik | Adaylar | Oyuncu / geliştirici değeri | Başlama koşulu |
|---|---|---|---|
| Yakın | A1 teşhis, A2 Qwen adapter testleri, A3 kayıt/retry, A4 tek NPC pilotu | Hatanın kaynağı görünür, oyun sonucu korunur, sohbet doğal kalır | Mevcut modül/sözleşme envanteri ve izole test sahnesi |
| Orta | B1 kaynaklı hafıza, B2 lore review, B3 veri paketleri | Uzun kampanya ve yeni içerik daha güvenilir yönetilir | Authoring draft/publish ve mevcut provenance sınırı |
| Orta | B4 rota önizleme, B5 keşif haritası | Yolculuk ve bilinmeyen dünya oyuncuya anlamlı görünür | Kaynaklı rota/zaman ve backend görünürlük projeksiyonu |
| Orta | B6 ilişki grafı, B7 koşullu arc editörü, B8 rutin pilotu | Karakterler tutarlı motivasyon ve gündelik yaşam kazanır | Stable NPC ID, geçmiş/olasılık ayrımı, tek oyun saati |
| Uzun | C1 branch/replay, C2 faction, C3 sahne-dışı hedefler | Seçimlerin ve zamanın daha geniş dünya etkisi | Kalıcılık, RNG, zaman, event sahipliği ve bütçe |
| Uzun | C4 veri paketi ekosistemi, ileride mod SDK | İçerik üretimi/özelleştirme ölçeklenir | Paket sürümü, yetki ve save uyumluluğu; native kod güvenlik tasarımı |
| İlham / kaçın | Her NPC’ye sürekli LLM, prose→inventory, kapalı motoru kopyalamak | Şimdi maliyet/risk faydasından yüksek | Ayrı gerekçe ve kabul kanıtı olmadan başlanmaz |

## 7. Uygulamaya geçmeden seçim kapısı

Her aday için kısa bir karar kaydı yeterli:

1. Mevcut AI-DND'de aynı yetenek hangi modülde var ve hangi kısmı gerçekten eksik?
2. Güncel onaylı sözleşme/faz ile uyumlu mu, yoksa ayrı kapsam kararı mı gerekiyor?
3. Kaynaktan yalnız fikir mi alınıyor, kod/asset/prompt da taşınacak mı? Lisans ve üçüncü taraf içerik sınırları çözüldü mü?
4. En küçük oyuncu-visible dikey kesit ve geri dönüş/feature flag yolu nedir?
5. Mekanik doğru çalıştığını ve oyuncuya iyi hissettirdiğini ayrı ayrı neyle göstereceğiz?
6. Gerçek Qwen'de çağrı/token/gecikme ve restart/izolasyon kanıtı nedir?

Önerilen ilk değerlendirme paketi: A1 teşhis, A2 provider contract testleri, A3 mevcut save/retry test boşluğu ve A4 tek NPC pilotu. Bunları takip edecek içerik/keşif/hafıza adayları güncel roadmap ile eşleştirilsin. Bu seçim bir uygulama başlatma kararı değildir.
