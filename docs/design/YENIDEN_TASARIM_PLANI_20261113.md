Kısayol: (1) sayım (a) çıkış düzeyinde yapıldı; çıkışların çağırdığı alt işlevlerin iç dalları tek tek sayılmadı. (2) sayım (b) metin aramasıyla yapıldı; hiçbir test koşulmadı. (3) sayım (d) yapılamadı, kayıt tutmuyor; tahmin verildi. (4) ui-a ile main birleştirmesi denenmedi; yalnız dosya kesişimine bakıldı. (5) ekran görüntüleri ve prototip dosyası açılmadı; hedefler belgelerdeki tariflerden yazıldı. (6) ikinci sürümde A0'ın 18 önerisi koda ve görüntülere bakılmadan yazıldı; narration-source dalının yeni commit'lerinin yalnız başlıkları okundu; incelemenin D7'de saydığı üç şey doğrulanamadan plana alındı (bölüm 11).

# YENİDEN TASARIM PLANI (2026-11-13): üst plan

## Durum 2026-11-22

- Sıra ve durum artık `docs/design/YOL_HARITASI.md`'de; çelişkide o dosya esastır. Motor yapısında bölme tasarımı (§11, §12) ve ADR 0001 geçerlidir.
- TB (tur bölme) adımı eklendi: B2.x, B3b, B0c ve B4.4 TB'den sonra gelir (plan incelemesi I1). B1b ve B3c donmuş işlevlerde "önce taşı, sonra düzelt" ile yapılır.
- KRİT-02 kapandı (D-166, fc671b7b; Kadir 2026-11-15): tutarı motor belirler; yeniden sorulmaz.
- D-301 = K29: gidiş cümlesi anlatıcıya gider, iş B2.1'de; yeniden sorulmaz.
- Eski kayıt soruları kaldırıldı: eski kayıtlar önemsizdir (Kadir; CLAUDE.md "Eski kayıtlar").
- Bu belgede "en güçlü model" Opus demektir; fable yalnız Kadir o iş için söylerse. Tur bölme Kadir'in seçimiyle Fable ile yürür (2026-11-22).
- B2 test bölünmesi yapıldı (B2 bölümündeki "Düzeltme 22 Kasım 2026").
- Push, PR ve merge için "taze onay" diyen eski cümleler eskidi: geçerli kural CLAUDE.md "Push/merge/yayın" (Kadir 2026-11-22).

Durum: Kadir onayladı, 13 Kasım 2026.
Onaylanan hâl: bağımsız incelemenin (`PLAN_INCELEMESI_20261113.md`) D1, D2, D4-D8 düzeltmeleri işlenmiş ikinci sürüm; D3 Kadir'in kararıyla uygulanmadı. Aynı gün Kadir K1 ve K3-K23'ü önerildiği gibi kapattı, K24'ü (harcama) verdi; O17 ve O18 eklendi. Açık karar kalmadı. Onay planın kendisinedir: her kalem başlamadan önce kendi planı yazılır; push, PR ve merge her seferinde Kadir'in taze onayını ister.
İkinci sürümde değişenler: B0b'nin adı B0c oldu; B2.0 (çıkışta etiketleme) eklendi; Hat C (Kapı 1 sonrası) yazıldı ve 21 "havuz" satırı ona bağlandı; Kapı 1 artık Tur 1 ve Tur 2'den sonra; O11 Kapı 1'in sert ön koşulu ve Haiku sayacı okundu; K15 düzeltildi; A0'ın 18 sorusuna öneri yazıldı; O13-O16 ve B4.13 eklendi; K2 kapandı, K23 eklendi.
Üçüncü sürümde değişenler (13 Kasım 2026, akşam): A0 kapandı (17 cevap; 6. ve 17. değişti); kitap yönü taslağı tema setinin hedef resmi oldu (A0b: T1-T13 ve G1-G13 yerleştirildi); A1 üç temaya ve kitap parçalarına göre güncellendi, yazı tipleri oyunun içine alınacak, A1 istemi yazıldı (`A1_ISTEMI_20261113.md`; Kadir görmeden başlatılmaz); Risk 11 (sayfalama) ve 12, Çelişki 22-28, O19 eklendi; Codex nihai raporunun 63 bulgusu T9'a alındı, B5.1-B5.10 ve Kapı 1 öncesi adaylar yazıldı. O akşam açık kalan üç karar (K25, K26, K27) aynı gece kapandı; aşağıdaki satır. Bu sürümde de kod, test ve ayar dosyası değişmedi.
Üçüncü sürümün kapanışı (13 Kasım 2026, gece): Kadir K25, K26 ve K27'yi kapattı (bölüm 12). **K25:** YÜK-04'ün üç dalı B1a'ya paketlenir; KRİT-03 ayrı parça olur (B1c); tavan yalnız M-a aşaması için 6. **K26:** sayfalama ile Dünya ve Günlük sayfaları Kapı 1'den sonra; dinlenme düğmeleri Karakter sayfasında, mumların altında (K7 değişti). **K27:** görev ödülü altındır; kartın söylediği ödenir. Ayrıca: bütünleştirme dalını A1 kurmaz (yeni O20); A1 isteminde beş değişiklik yapıldı; O19'un tema satırı ayrı belge PR'ına ayrıldı. **Açık karar kalmadı.**
Bu belge kalemleri, sırayı, bağımlılıkları, kapıları ve kanıtı tanımlar. Adım adım görev planı burada yoktur; her kalem başlamadan önce kendi planı yazılır (o planlarda `writing-plans` ve `brainstorming` kullanılır).
Bu oturumda kod, test ve ayar dosyası değişmedi. Commit, push, merge, silme yapılmadı. Sunucuya dokunulmadı. Anahtar dosyası açılmadı.
Doğrulama yöntemi: `git fetch`, `git` okuma komutları, `gh` okuma komutları, `graphify query`, `origin/main` içeriğinin geçici klasöre çıkarılıp okunması, `%LOCALAPPDATA%\AI-DND` altındaki kullanım ve rota kayıtlarının alan adları ve sayıları.

Kalem numaraları: A0, A0b, A1, A2.1-A2.20 (arayüz); B0, B0c, BA, B1a (YÜK-04'ün üç dalı içinde; K25), B1b, B1c (KRİT-03; K25, K27), BS, B2 (alt kalemleri B2.0-B2.4), B3a, B3b, B3c, B3d (KRİT-01), B4.1-B4.14, B5.1-B5.10 (motor); C1-C5 (Hat C, Kapı 1 sonrası); O1-O20 (küçük işler, bölüm 10); K1-K27 (Kadir'in kararları, bölüm 12; hepsi kapalı); T1-T13 ve G1-G13 (kitap yönü taslağı, A0b; bölüm 8'deki T1-T9 tablolarıyla karışmasın); "§n" bu belgenin bölümü.

---

## 1. Bugünkü durum (13 Kasım 2026, `git fetch` sonrası)

`origin/main` = **10ffd8cb** (PR #34 birleşmesi). Son CI koşusu yeşil: "AI-DND bounded verification", koşu 43337843149, push, 13 Kasım 00:32 UTC.

| Dal | Klasör | Yerel uç | Uzak uç | main'e göre önde / geride | PR | Bu planda ne olur |
|---|---|---|---|---|---|---|
| `main` (yerel) | worktree yok | a3ff9828 | 10ffd8cb | 0 / 6 | - | Temel. Yerel dal ileri alınır (O10) |
| `dev/ai-dnd` | `AI - DND` (Kadir'in oyun klasörü) | a3ff9828 | 8dc5c18b (eski) | 0 / 6 | #13 ve #21 (Ekim) bu dalı hedefliyor | Kapı 1'den önce güncellenir (O10). Uzak dala dokunulmaz |
| `task/ui-a-gorsel-20261112` | `AI-DND-ui-a` | 7d61ee5e | 885f4447 | 31 / 6 | yok | Hat A'nın temeli (K3). Bir commit push bekliyor (O2) |
| `task/portre-p1-20261112` | `AI-DND-portre` | d3fd6932 | d3fd6932 | 5 / 10 | yok | Bekler (donuk: G2). Uzakta yedekli |
| `task/dilim4d-places-20261112` | `AI-DND-4d` | a566212a | uzakta yok | **0** / 10 | yok | Bırakılır, silinmez. Dalda main'de olmayan commit yok (O3) |
| `task/narration-source-20261113` | `AI-DND-narration-source` | 72f649bf (13:30'da) | 256109d7 | 3 / 0 | yok | Birleştirilir (B0). Başka oturum yürütüyor; dokunulmadı. Sabah 7bd49a27 idi; main'in üstüne alınmış, iki commit eklenmiş, biri push bekliyor |
| `task/debt-register-20261113` | `AI-DND-debt` | 6df2124a | uzakta yok | 1 / 0 | yok | Borç defteri (O4). Push ve PR Kadir'in onayıyla |
| `claude/ui-l-motor-a-0bbf39` | `AI - DND\.claude\worktrees\ui-l-motor-a-0bbf39` | dd398b16 | dd398b16 | 0 / 1 | #34 birleşti (13 Kasım 03:32) | Bitti. Bırakılır |
| Diğerleri: `task/ui-slice3-20261112`, `task/rc18-text-20261112`, `task/docs-eol-20261111`, `task/c-series-merge`, `task/b01-source-identity-20261026` (PLAN klasörü), `AI-DND-jarvis-test`, `Documents` altındaki iki worktree, eski Ekim dalları | | | | | #22, #23, #24 (Ekim) | Bu planın konusu değil. Dokunulmaz |

Ek gözlemler:
- Açık PR: beş tane, hepsi Ekim'den (#13, #21, #22, #23, #24). Bu planın dallarıyla ilgisi yok.
- CI yalnız main push ve PR'da koşar; ui-a, portre, 4D ve narration-source dallarının kendi CI koşusu yok.
- Sunucular: 8009 ve 22786 dinliyor (inceleme kopyası). 8008 ve 22785 şu an dinlemiyor.
- `AI-DND-4d` klasöründe izlenmeyen `docs/superpowers/plans/` var. `AI-DND-portre` klasöründe izlenmeyen `docs/design/PORTRE_TASARIM_20261112.md` ve `docs/superpowers/plans/` var. Bunlar yalnız Kadir'in bilgisayarında.
- İstemdeki bilgiden farklar: narration-source dalında artık üç commit var (istem "henüz commit yok" diyordu). 4D dalı main'den 0 commit önde; yedek push'un yedekleyeceği commit yok.
- Sunucular 13:30'da da aynı: 8009 ve 22786 açık, 8008 ve 22785 kapalı.

**B0'ın durumu (başka oturum; 13 Kasım 13:30'da yeniden bakıldı):** dal main'in üstüne alınmış ve üç commit olmuş: 5c1630db (kayıt; sabahki 7bd49a27'nin yenisi), 256109d7 (kayıttaki izinli liste ile motorun bildirdiği değerlerin aynı küme olduğunu denetleyen test; envanter 5.19), 72f649bf (yan tablosu olmayan dosya da yüklenir ve kaydedilir). İlk ikisi uzakta, sonuncusu push bekliyor. PR yok. Kaynak, `campaign_history_sources` adlı yan tabloya yazılıyor; kayıt şeması sürümü artmıyor. Sabahki commit 6 dosyaya dokunuyordu (`ai-dnd/api/main.py`, `campaign_store.py`, `schemas.py`, `session_manager.py`, test dosyası, `lib/api-spec/openapi.yaml`); yeni commit'lerin dosyalarına bakmadım. Push koşulu (inceleme D7): tam paketin birinci parçası (para ve kayıt modülleri) yeşil özet verecek. Üretilen istemcilerin (`lib/api-client-react`, `lib/api-zod`) güncellenip güncellenmediğini doğrulamadım.

**Hangi iş hangi daldan çıkar (Kadir onayladı, 13 Kasım 2026; K3):**
- Yeni motor işi: her kalem `origin/main`'den kendi dalında ve kendi worktree'sinde. Aynı anda tek motor kalemi yazar.
- Yeni arayüz işi: `task/ui-a-gorsel-20261112` ucundan açılan bir bütünleştirme dalı. Önce `origin/main` bu dala alınır (6 commit; iki tarafta da değişen tek dosya `content/names/tr_names.json` ve içeriği iki dalda aynı). Her ekran bu daldan kendi dalında yapılır; Kadir kabul edince bütünleştirme dalına girer. Tur sonunda (Kadir'in kabulü, tam paket, bütün dal incelemesi) main'e PR açılır. **Durum (13 Kasım 2026, gece bakıldı): bütünleştirme dalı yok.** Yerelde de uzakta da böyle bir dal bulunmadı. Bugünkü fark: main'de ui-a'da olmayan 20 commit var (yukarıdaki "6" eskidi; PR #35-#39 sonradan girdi); ui-a'da main'de olmayan 31 commit var (biri, 7d61ee5e, yalnız yerelde). Dalı A1 kurmaz; ayrı küçük iş kurar (O20; Kadir, 13 Kasım 2026).
- ui-a'daki 31 commit: silinmez, yeniden yazılmaz. İlk arayüz turunun PR'ıyla main'e girer. Gerekçe: Kadir görünüşe NO-GO dedi; adım sırası, adım zarları, seviye kartı, XP çubuğu, dinlenme komutu, müzik ve ad tablosu bağlantısı çalışıyor ve yeni tasarım bunları kullanacak. 31 commit 71 dosyaya dokunuyor (+1854, -395); hepsi arayüz, testler, `public/`, `CLAUDE.md` ve içeriği aynı olan ad tablosu.
- "Arayüz işi" bölümü: 7d61ee5e yalnız `CLAUDE.md`'ye 13 satır ekliyor. Öneri: bu commit ayrı küçük bir belge PR'ıyla hemen main'e girsin (O9), çünkü motor worktree'leri ve diğer oturumlar kuralı bugün görmüyor. ui-a sonra birleşince aynı satırlar çakışmaz.
- `task/portre-p1-20261112`: bekler. `task/dilim4d-places-20261112`: bırakılır.

---

## 2. Dört sayım

Hepsi `origin/main` **10ffd8cb** üzerinde yapıldı (`git show` ve `git archive` ile geçici klasöre çıkarıldı). Çalışma klasörleri a3ff9828'de kaldığı için kullanılmadı.

### (a) `finish_turn` çıkışları

`ai-dnd/game.py` 24.360 satır. `finish_turn(` 56 kez geçiyor (1 tanım, 55 çağrı); `direct_response` 132 kez. İkisi de a3ff9828 ile aynı (PR #34 `game.py`'ye 8 satır ekledi).

**Asıl bulgu: turun iki çıkış katmanı var; tasarım belgesi yalnız birini sayıyor.**
- Katman 1, `_dispatch_player_turn`: 51 `return`. 7'si alt katmana ya da modele devrediyor, 2'si kendini yeniden çağırıp cümle ekliyor. **42'si `finish_turn`'e hiç uğramadan, motorun cümlesiyle bitiyor.**
- Katman 2, `_run_player_turn_internal` içindeki `finish_turn`: 55 çağrı. Bitiş biçimi: 20'si `is_final=True` (19 hazır cümle, 1 kabul edilmiş model konuşması); 21'i durum ya da `safety_handling` yüzünden motor cümlesi sayılıyor; 6'sı duruma göre değişiyor; 8'i model anlatımına gidiyor.

Toplam 97 çıkış. Yüzeye göre:

| Yüzey | Katman 1 | Katman 2 | Toplam | Dilim 1 kapsamı |
|---|---|---|---|---|
| Varış ve gezinme | 7 | 0 | 7 | evet |
| Kimler var (yere girişle ortak tek çıkış) | 0 | 1 | 1 | evet |
| İnceleme (nesne, pano, yazı, etrafa bakma) | 5 | 3 | 8 | evet |
| Arama | 0 | 2 | 2 | evet (yalnız bir şey bulunmadığında) |
| Konuşmayı bitirme | 1 | 0 | 1 | evet |
| Savaş sonucu | 7 | 8 | 15 | evet |
| **Dilim 1 toplamı** | **20** | **14** | **34** | |
| NPC konuşması ve kişi sorgusu (hazır cevap) | 1 | 19 | 20 | hayır (2c, 2d) |
| Soru ve onay (kavga onayı, hangi hamle) | 6 | 0 | 6 | hayır (2c) |
| Para, teklif, alışveriş | 6 | 5 | 11 | hayır (para) |
| Plan, söz, teklif cevabı | 0 | 5 | 5 | hayır |
| Envanter ve kese listesi, eşya alma | 5 | 1 | 6 | hayır |
| Bilgi sorgusu (konum, karakter, görev, bilgi) | 0 | 7 | 7 | hayır |
| Zaman ve dinlenme | 1 | 1 | 2 | hayır |
| Büyü | 0 | 1 | 1 | hayır |
| Diğer (sahip modül cevabı, ceset, gündelik eylem) | 3 | 0 | 3 | hayır |
| Çok yüzeyli genel çıkış (çözülemeyen eylem reddi, genel son çıkış) | 0 | 2 | 2 | kısmen |
| **Toplam** | **42** | **55** | **97** | |

Para içerebilen çıkış: 24 (Katman 1'de 11, Katman 2'de 13). Dilim 1 yüzeylerinin içinde para ya da XP satırı taşıyanlar: yağma sonucu (arama çıkışı), savaş sonucu çıkışlarındaki XP satırı, genel son çıkış. Bunlar S2 gereği motor cümlesi kalır.

Belirsizlik: Katman 2'de dört çıkışın (rakip sırası tamamlandı, geçersiz hedef, belirsiz saldırı hedefi, küçük sohbet) modele gidip gitmediği o turdaki duruma bağlı. Katman 1'de `grounded_action.resolve_turn` hem varış hem inceleme yapıyor, `_local_place_turn` hem arama hem varış yapıyor. Sayılar ±3 oynayabilir.

### (b) Hazır cümleyi sabitleyen testler

767 dosya tarandı: 583 Python test dosyası, 95 arayüz testi, 89 yolculuk senaryosu.

| Ölçü | Dosya | Test |
|---|---|---|
| Dar: Dilim 1 yüzeylerinin sabit cümle parçalarını içeren | **35** | **72** (31 Python dosyasında 68, 4 yolculuk senaryosu) |
| ...varış ve gezinme | 17 | 24 |
| ...savaş sonucu | 16 | 42 |
| ...arama / inceleme / kimler var / konuşmayı bitirme | 2 / 2 / 1 / 0 | 3 / 2 / 1 / 0 |
| Model çağrısının 0 olmasını bekleyen | 25 | 61 |
| `narration_source` değeri bekleyen | 14 | 40 |
| `direct_response` üzerinde doğrulama yapan | 26 | 36 |
| Yolculuk senaryosunda `gerekli_metin` beklentisi | 31 | 60 adım |
| Geniş: anlatım metninde Türkçe sabit cümle bekleyen her test | 139 | 497 |

Planlama rakamı: **en az 72 test, 35 dosya**. Model çağrısı sayısını ve kaynağı sabitleyen testler eklenince 130-170 (tahmin; çakışmalar düşülmedi). Üst sınır 497. Hepsi Dilim 1'de eşit sıkılıkla yeniden yazılır ve onay listesine "[GEVŞETME OLABİLİR]" işaretiyle girer. 2a için ayrıca: ret cümlelerini sabitleyen 7 test, 7 dosya.

### (c) Yerel Gemma ile tur süresi

Ölçüldü; yeni ölçüm gerekmedi. Kaynak: `%LOCALAPPDATA%\AI-DND\route-log.jsonl` ve `route-log.usage.jsonl` (tur başına rota ve çağrı sayısı) ile `model-usage.jsonl` (çağrı başına `seconds`). 13 Kasım oynayışının penceresinde 65 rota satırı ve 74 Gemma çağrısı var; iki kaydın toplamı tutuyor, çağrılar turlara sırayla eşlendi. 67 girişten ikisi (teklif onayı, Geri Al) rota kaydından geçmiyor.

| Tur türü | Tur | Ortanca model süresi |
|---|---|---|
| Model çağırmayan | 15 | 0 sn (motorun kendi süresi kayıtta yok) |
| Tek çağrı | 26 | 10,5 sn (en az 4,6; en çok 21,5) |
| İki çağrı | 24 | 17,0 sn (en az 11,3; en çok 33,3) |
| Model çağıran bütün turlar | 50 | **14,3 sn**; onda dokuzu 23,4 sn'nin altında |
| 65 turun tümü | 65 | 12,0 sn |

Sınır: bu, model çağrılarının süresidir; tarayıcıdan ölçülen uçtan uca süre değildir.

Bulut kipi için aynı kayıttan (çağrı başına, "cevapladı" satırları; tur başına değil): Gemini 746 çağrıda ortanca 1,7 sn; Haiku 382 çağrıda 2,5 sn; yerel Gemma 122 çağrıda 9,9 sn. Yani bulutta iki çağrılı bir tur yaklaşık 4 sn sürer (tahmin). Kapı 1 bulut zinciriyle oynanacağı için tur süresi ölçütü o kipte ölçülür (K15).

Yan bulgular:
- İki çağrılı turda ilk çağrı (hamleyi okuma) ortanca 10,2 sn, ikinci çağrı (anlatım) 5,8 sn. Yavaş olan anlatım değil, hamleyi okumaktır.
- Hamle kaynağı artık ölçüm: anlatım için model çağrısı 28 turda var, 37 turda yok; rota kaydı olmayan 2 sistem satırıyla 67'nin 39'u (%58) motor cümlesi. Notlardaki çıkarım (41 / 22 / 4) ile yakın. Varsayım: rota adı `front:` ya da `fallback:` ile başlayan turda ilk çağrı hamleyi okumadır (`front_proposal.py`).
- Sistem ve para satırları çıkınca 58 tur kalıyor; 27'sinde (%47) anlatım modelden. Dilim 1'den sonra tahmin: %78-81. %80 hedefi sınırda.
- Dilim 1 tur süresi tahmini: bütün turların ortancası 12,0 sn'den yaklaşık 12,8 sn'ye çıkar (iki kat eşiğinin içinde). Savaş turları 0 sn'den yaklaşık 6 sn'ye çıkar. İkisi de tahmin.

### (d) Model önerileri

**Yapılamadı. Kayıt bunu tutmuyor.** Tur geçmişi yalnız hamle, anlatım ve zamanı tutuyor; rota kaydında öneri alanı yok; kabul ve ret listeleri (`accepted_proposal_keys`, `rejected_proposal_names`) `_narrate_resolved_turn` içinde yerel değişken olarak kalıp atılıyor.

Koddan okunan, her şeridin hangi turda açık olduğu:

| Öneri türü | Açık olma koşulu (işlev) |
|---|---|
| Sahne ayrıntısı | `_scene_detail_proposals_allowed`: kip "Söyle" ya da "Anlatıcıya Sor" değil; oyuncu dünya hakkında iddia etmiyor; `should_generate_features` doğru (yapı sorusu, "etrafı araştır / çevreyi incele / ipuçlarını araştır / gizli ... ara" kalıbı, başarılı Algı ya da Araştırma zarı, ya da yer değişti ve sahnede hiç ayrıntı yok); sahnede bağlanacak bir üst öğe var |
| Kişi | `should_generate_npcs`: oyuncu iddia etmiyor; cümlede "ara, bul, sor, tanış, karşılaş" kökü var, ya da yer değişti ve sahnede kimse yok |
| Dükkân | Yalnız oyuncu açıkça dükkân istediğinde (`shop_request`) |
| Yer | `_may_propose_local_place`: motor hedefi çözemedi ("öneri bekliyor"), oyuncu yerleşimin açık sokağında ve iddia etmiyor |
| Eşya isteği | `_grounded_item_request_proposal`: yalnız NPC konuşması yolunda |

Önemli yapı bilgisi: kişi, ayrıntı, yer ve dükkân izinleri `_run_player_turn_internal`'ın sonuna doğru hesaplanıyor. Katman 1'deki 42 çıkış ve Katman 2'nin kesin biten çıkışları hiçbir şeridi açmıyor. Şerit ancak genel anlatım yoluna ve NPC konuşmasına ulaşan turda açılabiliyor.

Tahmin (ölçüm değil): 67 turun en çok 5-11'inde bir şerit açıktı; kabul edilmiş model önerisi büyük olasılıkla 0; ret sayısı bilinmiyor.

Eklenmesi gereken alan (B0c): tur başına açık şeritler, sunulan öneri sayısı, kabul edilen sayı ve ret nedeni kodu; B0'ın yan tablosunun yanına.

---

## 3. Hat A: Arayüz

Ortak kurallar: `CLAUDE.md` "Arayüz işi" bölümü. Tek ekran, tek oturum. Aynı anda tek ekran açık. Bir turda en çok beş ekran. Motor verisi hazır olmayan ekran o veriyi uydurmaz.

Bugünkü kod (ui-a dalı, sayıldı): `src/components/ui` altında 56 hazır bileşen var ama dışarıda yalnız 3 dosya kullanıyor. Ham tarayıcı kontrolü: `<select` 59 yerde (19 dosya), onay kutusu 33 yerde (20 dosya), radyo 7 yerde (4 dosya), sayı kutusu 4 yerde. `three` paketi kurulu değil.

Hedef resim durumu: onaylı prototip tek dosya (`UI_PROTOTIP_V4_20261111/index.html`) ve yalnız göstergeleri, zarı, efektleri, atmosferi ve bilgi kutularını gösteriyor. Savaş, kurulum adımları, ana menü ve pencereler için onaylı hedef resim **yok**. Bu ekranlarda kural gereği önce Kadir'e taslak gösterilir, sonra kod yazılır.

**Güncelleme (13 Kasım 2026, 18:55): kitap yönü taslağı tema setinin hedef resmi oldu (A0b).** Hedef resmi artık olan ekranlar: oyun ekranı (hikâye iki sayfada; Gündüz, Gece, Karanlık), Karakter, Çanta, Dünya ve Günlük sayfaları, Ayarlar'ın "Arayüz" bölümü, kurulumun tür adımı, telefonda hikâye ve karakter. Hâlâ hedef resmi olmayanlar: savaş, kurulumun diğer yedi adımı, dükkân, seviye atlama, giriş ve kayıt (G4); bunlarda önce taslak gösterilir.

### A0. Tasarım konuşması (S; en güçlü model; kod yok)

Çıktı: cevaplanmış soru listesi, PLAN klasöründe tek dosya. Kapanmış kararlar yeniden sorulmaz.
Her sorunun altında önerim ve tek cümlelik gerekçesi var. Kadir "hepsi öneri gibi" diyebilir ya da soru numarasıyla değiştirir. Öneriler ekran görüntülerine bakılmadan, notlardaki tariflerden yazıldı.
13 Kasım kararlarıyla kapananlar: soru 1 (K20: önce SVG zar; 3B zar Kapı 1'den sonra). **Diğer 17 soru da kapandı (Kadir, 13 Kasım 2026, akşam): 6. ve 17. cevap değişti, kalan 15'i önerildiği gibi.** Kapanış notu soru listesinin altındadır; sorular ve öneriler kayıt olarak duruyor.

Tema kontrol setini etkileyenler:
1. Zar: 3B zar için `three` paketi eklensin mi, yoksa önce SVG zar yapılıp 3B zar sonra mı gelsin? (Paket bugün kurulu değil.)
   - Öneri: önce SVG zar; 3B zar Kapı 1'den sonra Hat C'de (C5). Gerekçe: zarın motorun sayısını doğru göstermesi, üç boyutlu görünmesinden önce gelir ve paket bugün kurulu değil.
2. Mühür: can göstergesi nerede durur (üst çubuk, karakter özeti, savaş kartı) ve kaç boyda çizilir?
   - Öneri: üç yerde, iki boyda: üst çubukta küçük; karakter özetinde ve savaşta oyuncunun kartında büyük. Düşmanın kartında mühür durum sözcüğüyle durur, sayı yazmaz. Gerekçe: can, oyuncunun her an görmesi gereken tek göstergedir.
3. Mumlar: büyü yuvaları seviye başına ayrı sıra mı, tek sıra mı?
   - Öneri: seviye başına ayrı kısa sıra, başında seviye rakamı. Gerekçe: oyuncu "2. seviye yuvam kaldı mı" diye bakar; tek sırada bu okunmaz.
4. Seçili kartın işareti balmumu damga mı olsun? (Notlar U-3.)
   - Öneri: evet; ayrıca çerçeve kalınlaşır ve "seçildi" bilgisi ekran okuyucuya gider. Gerekçe: onaylı mühür diliyle aynıdır; yalnız renge dayanan işaret herkes için okunmaz.
5. Ayar çarkı küçük açılır pencere mi, yandan açılan sayfa mı? İçindeki sıra ne?
   - Öneri: masaüstünde çarkın yanında açılan küçük pencere; 390 pikselde alttan açılan sayfa. Sıra: ses (müzik aç/kapa, müzik düzeyi, tuş sesi), görünüm (tema, efekt seviyesi), okuma, göstergeler. Gerekçe: en sık değişen ayar en üstte durur ve küçük pencere oyunu örtmez.
6. Renk teması: gece, gündüz ve sistem dışında başka renk seçeneği olacak mı? (Notlar B-8 "mavi, gri, siyah, beyaz" diyor.)
   - Öneri: şimdilik yalnız gece, gündüz, sistem. Gerekçe: her yeni renk, yirmi ekranın kontrast kanıtını bir kez daha ister; eksikliğini bir ekranda görürsen o zaman eklenir.
7. Kayıt bildirimi mühür basma biçiminde mi olsun? (Notlar U-5.)
   - Öneri: evet; sağ üstte küçük mühür ve "Kaydedildi", 2 saniyede solar; kayıt başarısızsa kalır ve nedenini yazar. Gerekçe: istediğin biçim buydu (küçük, sağ üst, solan); hata ise kaybolmamalı.
8. Pencere başlıkları: "YOLCU" yerine "Karakter"; "Dünyanın çevresi" başlığı kalksın mı?
   - Öneri: başlıklar "Karakter" ve "Dünya"; "YOLCU" ve "Dünyanın çevresi" kalkar. Gerekçe: başlık pencerenin ne olduğunu söylemeli.
9. Yetenek sayıları el yazısı ve altçizgili mi olsun? (Prototip 11.) Kurulumda da mı?
   - Öneri: evet, karakter sayfasında ve kurulum özetinde; puan satın alma adımında düz rakam. Gerekçe: prototipte onaylıydı; ama artı ve eksiyle değişen sayı düz yazıyla daha hızlı okunur.
10. Kâğıt dokusu ve düğmenin basılınca inmesi tema setine girsin mi? (Prototip 4 ve 7; hiçbir sıraya yazılmamış.)
   - Öneri: ikisi de girsin; efekt seviyesi "Kapalı" iken doku düz renge döner, inme yerine yalnız renk değişir. Gerekçe: ucuzdur, prototipte onaylıydı ve kitap hissini her ekrana bunlar taşır.

İlk turun ekranlarını etkileyenler:
11. Savaş düzeni: üstte sıra şeridi, sağda eylem sayfası önerisi kabul mü?
   - Öneri: evet; ortada anlatı kalır. Gerekçe: `KESME_SONRASI` 10.8'in birinci tasarım kuralı budur ve anlatı ortada kalınca savaş hikâyeden kopmaz.
12. Savaşta hedef nereden seçilir: katılımcı kartından mı, eylem sayfasından mı?
   - Öneri: katılımcı kartına dokunarak; seçili hedefin adı eylem sayfasının başında yazar. Gerekçe: oyuncu önce "kime", sonra "neyle" diye düşünür; ayrı duran açılır liste bugünkü kopukluğun nedenidir.
13. Savaş günlüğü ayrı bir alan mı, anlatı sütununun kendisi mi?
   - Öneri: anlatı sütununun kendisi; zar ve hasar satırı anlatının içinde ayrı biçimle durur. Gerekçe: 10.8 zarı anlatı sütununa koyuyor; ikinci bir günlük aynı bilgiyi yineler (notlar X-9).
14. Büyü seçiminde çakışan seçenek soluk kalıp yanında nedeni mi yazsın? (Notlar U-1.)
   - Öneri: evet. Gerekçe: şikâyetin tam olarak buydu: neyin neden engellendiği anlaşılmıyor.
15. Kimlik: öneri penceresi kalkıp her alana zar düğmesi gelince zarın yazdığı metin hazır listeden mi gelir, modelden mi?
   - Öneri: modelden; zar bugünkü öneri yolunu çağırır, metin doğrudan alana yazılır, yanında "eskiye dön" olur; model cevap vermezse tek satır hata. Gerekçe: metin karaktere (tür, sınıf, geçmiş) uyar ve yeni içerik listesi yazmak gerekmez. Bedeli: yerel modelde yaklaşık 10 sn, bulutta yaklaşık 2 sn bekleme.
16. Ahlaki yönelim 3x3 ızgara mı olsun? (Notlar U-2.)
   - Öneri: evet. Gerekçe: dokuz seçenek tek bakışta görünür ve açılır liste kalkar.
17. Kurulum düzeni: her adım bir sayfa ve özet sol sayfada mı (Notlar U-4), yoksa bugünkü adım şeridi mi?
   - Öneri: adım şeridi kalsın; özet sütunu kitabın sol sayfası gibi giydirilsin; sayfa çevirme hareketi Hat C'de (C4). Gerekçe: düzeni baştan kurmak sekiz kurulum ekranını birden etkiler; önce her adımın içi düzelsin.
18. Yazı kutusu: "Yap / Söyle / Anlatıcıya Sor" kipleri kalacak mı? Mikrofon düğmesi nerede durur? Savaştaki "Kapat" düğmesi ne olur?
   - Öneri: üç kip kalsın ama tek satırlık küçük seçici olsun; mikrofon gönder düğmesinin solunda dursun; "Kapat"ın ne yaptığı koddan okunsun: işe yarıyorsa adı işini söylesin, yaramıyorsa kalksın. Gerekçe: kipler motorun hamleyi doğru okumasına yarıyor (söz mü, eylem mi); "Kapat"ın ne kapattığını bugün kimse bilmiyor.

**A0 kapanışı (Kadir, 13 Kasım 2026, akşam).**
- **6. soru değişti.** Yeni cevap T8'dir (A0b): görünüm varsayılan olarak hikâyedeki saati izler; elle Gündüz, Gece ve Karanlık seçilir. "Cihaz ayarını izle" seçeneği yok (Ruling, karar belgesinde: varsayılan artık hikâyenin saati; yanlışsa bir seçenek eklemek kolaydır).
- **17. soru değişti.** Yeni cevap T2, T4 ve T5'tir (A0b). Sayfa çevirme hareketi Hat C'de kalır (C4).
- **Diğer 15 soru (2, 3, 4, 5, 7-16, 18): önerildiği gibi.** Renk temaları (cilt rengi olarak) sonraya kalır.

Öneri gibi kapanan cevapların taslakla birlikte okunuşu (Ruling: taslak daha yeni olduğu için çakışan ayrıntıda taslağa bakılır; yanlışsa galeri ya da ekran taslağı onayında düzeltilir, maliyeti bir parçanın yeniden çizilmesidir):
- 2: "üst çubuktaki küçük mühür" taslakta sağ sayfanın başlığında durur; büyük mühür Karakter sayfasındadır.
- 5: çarkın küçük penceresi kalır. T3'ün "Arayüz" bölümü görünüm, sayfa düzeni, el yazısı ve yazı boyunu toplar; ses, efekt seviyesi ve gösterge seçimi ayrı bölümlerdir. Bölümlerin sırası ve kapsamı A2.8 taslağında sorulur (G11; Çelişki 27).
- 7: kayıt bildirimi ile taslağın "kurdele kayıttır" ilkesi çakışıyor (Çelişki 24); galeride ikisi de gösterilir, Kadir seçer.
- 8: "Karakter" ve "Dünya" artık pencere başlığı değil ayraç adıdır. Ayraçlar: Hikâye, Karakter, Çanta, Dünya, Günlük.
- 11-13: "sağda eylem sayfası" taslaktaki sağ sayfadır. Savaş başlayınca sağ sayfanın kendiliğinden savaş sayfasına dönmesi (G5) A2.1 taslağında karara bağlanır.

### A0b. Kitap yönü taslağı: hedef resim, T1-T13, G1-G13 (Kadir, 13 Kasım 2026, 18:55)

Kadir bu taslağı tema setinin (A1) **hedef resmi** olarak onayladı. Sözü: "Onaylıyorum ama notlara geliştirilecek diye yaz; bu yalnız taslak, son hâli değil."

- Karar belgesi: `kitap-taslagi-20261113/KITAP_YONU_TASLAK_KARARLARI_20261113.md` (PLAN klasöründe). Tasarım ilkeleri 4. bölümünde, renk ve yazı değerleri 5. bölümünde.
- Hedef resimler: `kitap-taslagi-20261113/hedef-resimler/` (13 görüntü; 1440×900 ve 390×844). "Arayüz işi" kuralındaki hedef budur.
- `kitap-taslagi-20261113/kaynak/` oyunun kodu değildir. **Aynen alınabilenler (Kadir, 13 Kasım 2026, gece):** içindeki çizimler (mühür, mum, lamba, kalem ucu, kenar simgeleri, kurdele) ve iki kâğıt dokusu (`kagit-tanesi-acik.png`, `kagit-tanesi-koyu.png`). **Taşınmayanlar:** düzen işaretlemesi ve stil kodu; renk ve ölçü değerleri `src/index.css` değişkenlerine elle taşınır. **Çizimlerin iç renkleri (Kadir, 13 Kasım 2026, gece; karar belgesi 9. bölüm):** gölge, ışık ve renk geçişi durakları çizimin parçasıdır, olduğu gibi kalır. Yalnız temaya göre değişen üç renk değişkenden gelir: `--mum-cizgi`, `--soluk`, `--mum`. Çizimler oyunda ayrı bir klasörde durur; "elle yazılmış renk kodu yok" araması o klasörü kapsamaz. Çizimlerin dosyası ve nasıl bulunacağı karar belgesinin 9. bölümünde. Klasörde altı `.dc.html` dosyası, bir `canvas.json` ve iki doku resmi var (dosya adlarına bakıldı; içleri açılmadı).
- Bir oturum arayüz işine başlamadan önce karar belgesini ve hedef resimleri okur.

**Kararlar (T1-T13) ve plandaki yerleri:**

| No | Karar | Planda yeri |
|---|---|---|
| T1 | Yön kitaptır: açık kitap, iki sayfa, bez cilt, sayfa yığını, sırta doğru kavis, kurdele, sayfanın üstünden çıkan ayraçlar | A1 (kitap kabuğu parçaları); A2.6 (oyun kabuğu); kurulum ekranları ve A2.9 aynı kabuğu kullanır |
| T2 | Varsayılan düzen: hikâye iki sayfaya yayılır. Karakter, Çanta, Dünya ve Günlük ayraçla açılır | A2.6, A2.7; A2.10 (Karakter ve Çanta sayfaları); A2.11 (Dünya ve Günlük sayfaları; Tur 3, Kapı 1'den sonra: K26). K19 ve K7 ile ilişkisi: Çelişki 22 ve 23 (23 kapandı: dinlenme düğmeleri Karakter sayfasında) |
| T3 | Ayarlar'da "Arayüz" bölümü: görünüm, sayfa düzeni, el yazısı, yazı boyu; ileride başka seçenekler | A2.8; seçici düğmeler A1 |
| T4 | Sayfa düzeni seçilebilir: "İki sayfa hikâye" (varsayılan) ve "Karakter açık" | A2.6, A2.8 |
| T5 | Hiçbir hikâye satırı kaybolmaz. Defter açıkken hikâyenin son kısmı ve yazma alanı sol sayfada görünür; eski satırlara geri gidilir | A2.7, A2.6. Kırmızı test: ayraç ve düzen değişiminde gönderilen satır kaybolmaz. Borç D-082'nin takip mantığıyla aynı dosyalara dokunur |
| T6 | Gece siyah sayfa değildir: sararmış kâğıt, karanlık oda, yukarıdan düşen ışık | A1 (üç tema: Gündüz, Gece, Karanlık) |
| T7 | Işık kaynağı: kitabın üst kenarına kıskaçla tutturulmuş pirinç okuma lambası; gündüz görünmez | A1 (lamba parçası); G6, G10 |
| T8 | Görünüm hikâyedeki saati izler (varsayılan); elle Gündüz, Gece ve Karanlık seçilir. Seçici dört seçeneklidir: "Hikâyedeki saati izle", Gündüz, Gece, Karanlık | A1 (seçici), A2.8, A2.6. Motor verisi **var** (bölüm 5 tablosu). Açık kalan: motorun dört bölümünün (şafak, gündüz, akşam, gece) hangi görünüme denk geldiği. Taslak "akşam"ı Gece, "öğle"yi Gündüz gösteriyor; şafak A2.8 taslağında sorulur |
| T9 | "Karanlık" (koyu sayfa) seçeneği kalır | A1; her ekranın kanıtına üçüncü tema girer (Risk 12) |
| T10 | El yazısı sırası: B (Kalam), A (Charm), C (Bad Script); varsayılan B; üçü de Ayarlar'dan seçilir | A1 (yazı tipleri oyunun içinde), A2.8 |
| T11 | Mekân atmosferi kitabın çevresinde gösterilir (ışık, renk; ileride ses) | Hat C, C3 |
| T12 | Açıklama yazısı yok; mum grubunun altında yalnız seviye adı yazar | A1 (mum). "Sayı her zaman yazılı kalır" kuralıyla ilişkisi: Çelişki 25 |
| T13 | Süs için renk lekesi yok | A1; her ekranın ayrı göz incelemesinde bakılır |

**Geliştirilecekler (G1-G13) ve plandaki yerleri.** Taslak son hâl değildir.

| No | Konu | Planda yeri | Not |
|---|---|---|---|
| G1 | **Sayfalama:** metin sayfa dolunca karşı sayfaya geçer; iki sayfa dolunca sayfa çevrilir. Taslakta yok | A1'e girmez. **Kapı 1'den sonra** (K26; Kadir, 13 Kasım 2026): A2.7'nin ardından ayrı deneme ve ayrı kalem. Kapı 1'de uzun metin sayfanın içinde kayar | En riskli iş: Risk 11 |
| G2 | Sayfa çevirme hareketi | Hat C, C4 | |
| G3 | Elle çizilmiş görseller (mühür, mum, kalem, lamba) | Hat C, C4 | A1'de kodla çizilir |
| G4 | Tasarlanmamış ekranlar | Savaş: A2.1. Kurulumun diğer yedi adımı: A2.13, A2.14, A2.15, A2.2, A2.16, A2.3, A2.4. Dükkân: A2.19. Seviye atlama: A2.7. Giriş ve kayıt: A2.9 | Her birinde önce taslak, Kadir'in onayı, sonra kod. Giriş ve kayıt sayfasının A2.9'a girip girmediği A2.9 taslağında sorulur |
| G5 | Savaşta sağ sayfa: savaş başlayınca kendiliğinden savaş sayfasına dönsün mü | A2.1 taslağı | A0-11 ile uyumlu; karar verilmedi |
| G6 | Telefon: tek sayfa çalışıyor; Ayarlar bölümü ve okuma lambası telefonda yok | A1 (390 galerisi), A2.8 | A0-5: 390'da alttan açılan sayfa |
| G7 | Kitabın ekranla büyümesi (taslak sabit 1440×900) | A1 (kabuk parçası), A2.6 | Kanıta 1440'tan geniş bir görüntü eklenir |
| G8 | Tür sayfasının boş kalan sol altı (aday: türün çizimi ya da portre) | A2.12 | |
| G9 | Gündüz için mekân atmosferi | Hat C, C3 | |
| G10 | Karanlık temada ışık (lamba yalnız gecede görünüyor) | A1 galerisinde Kadir'e sorulur | |
| G11 | "Arayüz" bölümünün kapsamı | A2.8 taslağı | |
| G12 | Gerçek metin: çanta, günlük, dünya ve tür metinleri motorun verisinden gelir | Her A2 ekranı; BA (Türkçe adlar) | Kural zaten var: ekran veriyi uydurmaz |
| G13 | Gönder ve mikrofon (taslakta cevap gelmez; mikrofon yalnız düğme) | A2.5 | |

### A1. Tema kontrol seti ve galeri (L; en güçlü model)

Tek galeri sayfası; **üç tema** (Gündüz, Gece, Karanlık; T6, T9); 1440 ve 390 piksel. Kadir galeriyi ekran görüntüsünden onaylamadan A2 başlamaz.

**Hedef resim:** `kitap-taslagi-20261113/hedef-resimler/` (A0b). Kesin renk ve yazı değerleri karar belgesinin 5. bölümünde ve `kaynak/Main.dc.html` dosyasının stil bölümündedir. `kaynak/` içindeki çizimler ve iki kâğıt dokusu aynen alınabilir; düzen işaretlemesi ve stil kodu taşınmaz, değerler `src/index.css` değişkenlerine elle taşınır (A0b). Kâğıt dokusu küçük döşeme resmiyle yapılır, tam sayfa SVG filtresiyle değil. Kontrast ekran görüntüsündeki gerçek piksellerden ölçülür; sırt gölgesine düşen kenar notları dahil. Bütünleştirme dalını A1 kurmaz (O20). İstem: `A1_ISTEMI_20261113.md` (PLAN klasöründe; ikinci hâli, 13 Kasım gece); Kadir görmeden başlatılmaz.

| Parça | Dayanacağı hazır bileşen (`src/components/ui`) | Not |
|---|---|---|
| Düğme | `button.tsx`, `button-group.tsx` | Basılınca inme A0-10'a bağlı |
| Açılır liste | `select.tsx` | 59 ham `select`'in yerine geçecek |
| Onay kutusu | `checkbox.tsx`, `switch.tsx` | |
| Seçim kartı | `card.tsx`, `radio-group.tsx`, `toggle-group.tsx` | Seçili işareti A0-4 |
| Sayaç | `button.tsx`, `input.tsx` | Hazır yok; yeni küçük bileşen |
| Rozet | `badge.tsx` | |
| Bölüm başlığı | `separator.tsx`, `label.tsx` | Hazır yok; yeni küçük bileşen |
| Sayı kutusu | `input.tsx`, `field.tsx` | Hata iletisi alanın yanında |
| Kendiliğinden kapanan bildirim | `sonner.tsx`, `toast.tsx` | Sağ üst, küçük, solar |
| Pencere ve yapışkan kapatma | `dialog.tsx`, `sheet.tsx`, `drawer.tsx`, `scroll-area.tsx`, `alert-dialog.tsx` | Temalı kaydırma çubuğu burada çözülür |
| Ayar çarkı | `popover.tsx` ya da `sheet.tsx`, `slider.tsx`, `switch.tsx` | Biçimi A0-5 |
| Mikrofon düğmesi | `toggle.tsx`, `tooltip.tsx` | Tarayıcı desteklemiyorsa görünmez |
| Can göstergesi: mühür; şişe seçenek | Hazır yok; yeni | Sayı her zaman yazılı kalır |
| Büyü yuvası: mum | Hazır yok; yeni | Sayı her zaman yazılı kalır |
| Zar | Hazır yok; yeni | Sayı yalnız motor sonucundan; teknolojisi A0-1 |
| Ek: sekme, ipucu, boş durum, yükleniyor | `tabs.tsx`, `tooltip.tsx`, `empty.tsx`, `skeleton.tsx`, `spinner.tsx` | |
| Kitap kabuğu: bez cilt, iki sayfa, sırt kavisi, sayfa yığını, kurdele | Hazır yok; yeni | T1. Ekranla büyür (G7); 390'da tek sayfa. Kâğıt dokusu A0-10: küçük döşeme resmi (taslağın iki doku dosyası), tam sayfa SVG filtresi değil |
| Ayraç (sayfanın üstünden çıkan sekme) | `tabs.tsx` | T2. Klavyeyle gezilir; seçili ayraç ekran okuyucuya bildirilir |
| Kenar notu (kuralın sesi: yeşil, eğik, küçük simgeli) | Hazır yok; yeni küçük bileşen | Taslak ilkesi "iki el": para, zar, iş, geri alma kenarda durur |
| Oyuncunun eli ve yazma alanı (kalem ucu, altın çizgi) | `textarea.tsx`, `input.tsx` | T10: üç el yazısı. Geri alınan hamlenin üstü çizilir, silinmez |
| Boş çizgili satır (yazılmamış olan) | `empty.tsx` | Taslak ilkesi 2 |
| Okuma lambası | Hazır yok; yeni | T7: gündüz görünmez. Karanlık temadaki durumu G10; telefondaki durumu G6 |
| Seçici düğme grubu (görünüm, sayfa düzeni, el yazısı, yazı boyu) | `toggle-group.tsx` | T3, T4. Düğmeler en az 44 piksel. Görünüm seçicisi dört seçeneklidir: "Hikâyedeki saati izle" (varsayılan), Gündüz, Gece, Karanlık; ayar bölümünün adı "Arayüz" (Kadir, 13 Kasım 2026, gece) |

Kanıt: galerinin altı görüntüsü (üç tema, 1440 ve 390) ve hedef resimlerle yan yana karşılaştırması, her parçanın boş, dolu, hata, devre dışı ve odak hâli; renklerin yalnız `src/index.css` değişkenlerinden geldiğini gösteren arama sonucu; ekran görüntüsünün gerçek piksellerinden ölçülen kontrast tablosu (sırt gölgesine düşen kenar notları dahil); arayüz testleri yeşil. Ayrı gözle inceleme oturumu zorunlu.
Hat B bağımlılığı: yok (zar ve göstergeler galeride sahte veriyle gösterilir; oyunda yalnız motor verisi).
İtiraz (bölüm 11): A1 tek oturuma sığmayabilir; iki oturum, tek galeri onayı önerisi.

**Yazı tipleri: karar verildi (Kadir, 13 Kasım 2026, akşam): yazı tipleri oyunun içine alınır, ağdan gelmez.** Neden (D-082 dersi): yazı tipleri bugün ağdan geliyor (`src/index.css` birinci satır, Google Fonts, `display=swap`). Geç gelince sayfayı yeniden diziyor: 800 piksel genişlikte hikâye 24 piksel kayıyor; borç defteri D-082'deki zıplamanın tetikleyicisi de bu (ayrıntı ve ölçümler o kayıtta). Alınacak yazı tipleri (karar belgesi bölüm 5): Literata (gövde, kenar notu, etiket, başlık) ve oyuncunun eli için Kalam, Charm, Bad Script (T10). Dosyalar depoya girer; `src/index.css`'in ağ satırı kalkar. A1'de bakılacaklar: seçilen yazı tiplerinin lisansı ve kaynak notu; çevrimdışı ve uzaktan oynayışta ağ isteği kalmaması; yazı tipi yüklenirken sayfanın kaymaması (galeri kanıtına bir satır: yazı tipi geç gelince ölçülen kayma). Otomatik alta takip düzeltmesi bundan bağımsızdır ve ayrı dalda yapılıyor.

### A2. Ekranlar

**Sekiz maddenin kanıtı (her ekranda aynı biçim):**

| # | Bitti tanımı maddesi | Kanıt |
|---|---|---|
| 1 | Hedefle yan yana karşılaştırma, kalan farklar | Hedef (ya da onaylı taslak) ile yeni görüntünün yan yana dosyası ve fark listesi |
| 2 | Boş, yükleniyor, hata, uzun içerik | Her durumun ayrı görüntüsü; ekrana özgü durumlar aşağıda |
| 3 | Gece ve gündüz | Üç temada görüntü: Gündüz, Gece, Karanlık (T6, T9). `CLAUDE.md` yalnız "gece ve gündüz" diyor; üçüncü tema bu planın eklediği kanıttır (Çelişki 26) |
| 4 | 390 pikselde yatay kaydırma yok | 390 görüntüsü ve ölçülen sayfa genişliği |
| 5 | Klavyeyle gezinme, odak görünür | Odak sırasının yazılı listesi ve odaklı hâlin görüntüsü |
| 6 | Renk, yazı tipi, boşluk yalnız `src/index.css` değişkenlerinden | Değişen dosyalarda elle yazılmış renk kodu aramasının boş sonucu. Arama çizim klasörünü kapsamaz (Kadir, 13 Kasım 2026: taslaktan alınan çizimlerin iç renkleri olduğu gibi kalır; A0b). `CLAUDE.md` (6) bu istisnayı söylemiyor; ayrı göz incelemesine istisna ayrıca bildirilir |
| 7 | Ham `select`, `checkbox`, `alert` yok | Değişen dosyalarda aramanın boş sonucu ve kullanılan hazır bileşenlerin adı |
| 8 | Bütün arayüz testleri yeşil | Koşunun çıktısı |

Görüntüler `UI_EKRAN_GORUNTULERI_20261113/<ekran kodu>_<gece ya da gunduz>_<1440 ya da 390>.png` adıyla saklanır. Raporun ilk satırı "Kısayol:" ile başlar. Her ekrandan sonra kodu yazmamış ayrı bir oturum `ui-design-review:review` ile bakar; bulgular Kadir'e gider. Ekranı yalnız Kadir kabul eder.

**İlk ekranda bir kez:** A2.2 (büyü seçimi) iki ayrı worktree'de, iki ayrı modelle yapılır; görüntüler A ve B diye gösterilir, Kadir seçer, sonra model adları ve harcanan token söylenir (`ARAYUZ_KALITE_KURALLARI` bölüm 5). İkisi de ortak dala girmez; Kadir'in seçtiği girer.

**Tur sonu oynayışı (Kadir, 13 Kasım 13:12):** her arayüz turunun sonunda Kadir en az 10 dakika oynar. Bu oynayış Kapı 1 sayılmaz. Tur 1'in sonundaki oynayışta Kadir dört kutunun durumunu not eder: iki iz buldu mu, birinin peşine düştü mü, bir seçiminin sonucunu gördü mü, "şimdi ne olacak?" dedi mi. Not ledger'a ve `OYNAYIS_NOTLARI` şablonuna yazılır; Kapı 1'e kadar neyin eksik kaldığını erken gösterir.

**Kapı 1'in yeri (karar K2, kapandı):** Kapı 1, Tur 1 ve Tur 2 (on ekran: A2.1-A2.10) kabul edildikten sonra yapılır.

#### Tur 1

**A2.1 Savaş ekranı** (L; en güçlü model)
- Hedef: onaylı resim yok; A0-11, 12, 13 ve `KESME_SONRASI` 10.8'in sekiz tasarım kuralına göre taslak, Kadir'in onayı. Bugünkü hâl: Screenshot 21-23. Göstergeler: prototip 8, 10, 15.
- Şikâyet: notlar X (12 bulgu), X-ek (5 ek bulgu); "yine rezalet, direkt tasarım yok".
- Bileşenler: `button`, `badge`, `card`, `select`, `sheet` (390'da alttan sayfa), `tooltip`, `scroll-area`; A1'in mühür, mum ve zar parçaları.
- 2. madde durumları: savaş yok; sıra oyuncuda; sıra rakipte; eylem hakkı bitmiş; yapılamayan eylem ve nedeni; bilinç kapalı; dört ve daha çok katılımcı; uzun yetenek listesi.
- Hat B: BS (düşman durumu, Yaklaş/Uzaklaş, doğru bonus eylem listesi), B3a (Türkçe neden), BA (Türkçe adlar). Hazır değilse o parça olmadan teslim edilir ve raporda yazılır; ekran veriyi uydurmaz.
- Kadir'in kararı: taslak onayı; BS gecikirse bekle ya da parçasız teslim.

**A2.2 Büyü seçimi, kurulum 5. adım** (M; iki modelle kör karşılaştırma)
- Hedef: onaylı resim yok; taslak. Bugünkü hâl: SS4, SS5, SS6.
- Şikâyet: notlar C-15, C-16, F-SS4, F-SS5/6; "hepsi düz yazı, rezil"; engelin nedeni anlaşılmıyor.
- Bileşenler: `card`, `checkbox`, `toggle-group`, `badge`, `tabs`, `select`, `field`, `tooltip`.
- 2. madde durumları: büyüsü olmayan sınıf; hiç seçim yok; sınır dolu; çakışan seçim ve nedeni; 16 ve daha çok büyü; alt sınıf ve nitelik artışı seçimi olan 2-5. seviye.
- Hat B: BA (alt sınıf, hüner, özellik adları). Yoksa İngilizce adlar `lang="en"` ile kalır ve yazılır.
- Kadir'in kararı: A ile B arasında seçim; A0-14.

**A2.3 Kimlik, kurulum 7. adım** (M)
- Hedef: taslak. Bugünkü hâl: SS8.
- Şikâyet: notlar C-18, F-SS8; "Windows 7 tarzı mavi liste"; öneri penceresi böyle olmamalı, alan başına zar.
- Bileşenler: `select`, `textarea`, `field`, `tabs`, `button`, `toggle-group` (3x3 yönelim); zar düğmesi A1'den.
- 2. madde durumları: boş alanlar; öneri yükleniyor; öneri alınamadı; çok uzun metin; sayfa yenilenince metnin akıbeti.
- Hat B: yok (öneri temizliği main'de: bfeb0fdd). Zar metninin kaynağı A0-15.
- Kadir'in kararı: A0-15, A0-16.

**A2.4 Karakter sayfası özeti, kurulumun son adımı** (M)
- Hedef: taslak; göstergeler prototip 8, 10, 11. Bugünkü hâl: SS9, SS10.
- Şikâyet: notlar C-19, F-SS9, F-SS10; "komple facia"; rakam yerine "Oluşturulduğunda sunucu hesaplayacak".
- Bileşenler: `card`, `badge`, `separator`, `tooltip`, `scroll-area`; mühür ve mum.
- 2. madde durumları: büyüsüz sınıf; boş kimlik alanları; 6 kalemli envanter; uzun köken metni.
- Hat B: BA. Ayrıca can ve inisiyatifin onaydan önce gösterilmesi motor verisi ister; bugün hesap karakter oluşunca yapılıyor. Veri gelene kadar bu iki kutu ekrana konmaz (karar K17).
- Not: "karakter sayfası özeti" sözünü kurulumun son adımı olarak okudum; oyun içi Karakter penceresi A2.10'dur.

**A2.5 Yazı kutusu, mikrofon dahil** (M)
- Hedef: taslak; `KESME_SONRASI` 10.7. Bugünkü hâl: SS15 ve Screenshot 21-23'ün alt bölümü.
- Şikâyet: notlar X-8 (hedef seçimi kutuyla ilişkisiz, ne kapattığı belli olmayan "Kapat"); envanter 4.11.
- Bileşenler: `textarea`, `button`, `toggle`, `toggle-group`, `tooltip`, `select`.
- 2. madde durumları: boş kutu; gönderiliyor; model cevap vermedi ve yeniden dene; mikrofon dinliyor; mikrofon izni reddedildi; tarayıcı desteklemiyor (düğme yok); çok uzun hamle; savaşta.
- Hat B: yok. Ön koşul: Kadir mikrofonu Chrome'da elle dener; Edge ve Safari'de düğmenin görünüp görünmediğine bakılır.
- Kadir'in kararı: A0-18.

#### Tur 2

**A2.6 Oyun kabuğu: üst çubuk, sağ Anlatıcı paneli, sol "Yanında" menüsü, kayıt bildirimi** (L)
- Hedef: taslak. Bugünkü hâl: SS15, SS18, `vid1.mp4`.
- Şikâyet: notlar M (9 madde), T-SS18, T-video, X-10; anlamsız etiketler, teknik "Defter numarası", küçük yer adı, kalıcı kayıt bildirimi.
- Bileşenler: `sonner`, `badge`, `button`, `collapsible`, `scroll-area`, `tooltip`, `sheet` (390).
- 2. madde durumları: konuşma yok; konuşma açık; uzun yer adı; boş Kişiler; kayıt başarısız; 390'da alt gezinme.
- Hat B: yok.

**A2.7 Hikâye sütunu: anlatı, zar sonucu, seviye kartı, Geri Al çubuğu** (M)
- Hedef: prototip 1 (mürekkep belirme) ve 15-18 (zar); yerleşim taslak.
- Şikâyet: yolculuk satırı 24 (zar görünmüyor), notlar X-11, U-6; 12 Kasım "hikâye penceresi küçük".
- Bileşenler: `card`, `scroll-area`, `button`, `badge`; zar A1'den; var olan `ink-text.tsx`, `skill-check-result.tsx`, `level-up-card.tsx`, `last-turn-bar.tsx`.
- 2. madde durumları: ilk sahne; çok uzun anlatı; zar atılan tur; seviye atlanan tur; Geri Al onayı; model bekleniyor.
- Hat B: zar için tur yanıtındaki zar verisi; hangi turların zar verisi taşıdığını doğrulamadım.

**A2.8 Ayar çarkı paneli: ana menü, kurulum, oyun içi** (M)
- Hedef: taslak (A0-5, A0-6). Bugünkü hâl: SS13 (iki ayrı ses kontrolü), SS19 (Görünüm sayfası).
- Şikâyet: notlar B (8-11), A-4, G-4, G-5, G-7, T-SS19.
- Bileşenler: `popover` ya da `sheet`, `switch`, `slider`, `radio-group`, `separator`.
- 2. madde durumları: ses kapalı; müzik dosyası yüklenemedi; 390; klavyeyle açıp kapama.
- İçinde: tuş sesi, müzik aç/kapa, müzik düzeyi, renk teması, efekt seviyesi, okuma ayarları, gösterge seçimi (mühür ya da şişe), zar seti. Eski `GateSoundControl` ve eski Görünüm sayfası kalkar.
- Hat B: yok.

**A2.9 Ana menü ve kapak girişi: logo, müzik, kitap rafı, silme onayı** (M)
- Hedef: taslak; logo `UI_LOGO_TASLAK_20261112`. Bugünkü hâl: SS13, `UI_EKRAN_GORUNTULERI_20261113/ana_ekran_1440.png` ve `ana_ekran_390.png` (390'da yatay taşma var).
- Şikâyet: notlar A (1-7), G-SS13, G-2, G-3, G-6.
- Bileşenler: `button`, `alert-dialog`, `card`, `scroll-area`.
- 2. madde durumları: kampanya yok; tek kampanya; çok kampanya; yükleniyor; motor hatası; hareketi azalt; gizli sekme; müzik engellendi.
- Hat B: yok. Varlıklar depoya sıkıştırılmış girer; kaynak notu yazılır.
- Kadir'in kararı: kapak görseli (taslak).

**A2.10 Karakter sayfası penceresi, oyun içi** (M)
- Hedef: taslak; göstergeler prototip 8, 10, 11. Bugünkü hâl: SS16.
- Şikâyet: notlar T-SS16; başlık "YOLCU", kapatma çubuğu içerikle kayıyor, İngilizce bloklar, okunmaz büyük harf.
- Bileşenler: `dialog`, `scroll-area`, `tabs`, `badge`, `progress` (XP), `separator`.
- 2. madde durumları: büyüsüz sınıf; 20 ve daha çok hazır büyü; boş kimlik; düz envanter listesi; en yüksek seviye; çatışma var (dinlenme kapalı); kabul edilmemiş iş var.
- **Dinlenme düğmeleri buradadır: mumların altında** (K26; Kadir, 13 Kasım 2026, gece; K7'nin yerini aldı). Başka yerde dinlenme düğmesi olmaz; yazıyla dinlenme her yerde çalışır (B3c). Büyüsüz sınıfta mum yoktur; düğmelerin o durumda nerede duracağı bu ekranın taslağında gösterilir.
- **Kabul düğmesi** (YÜK-16; K25): "Açık işler"de henüz kabul edilmemiş işin satırında durur; motorun teklif cümlesi düğmenin yerini söyler. İptal düğmesi ORTA-29 düzelmeden eklenmez.
- Hat B: BA; kabul düğmesi için teklif cümlesi (`dialogue_commitments.py`).

#### Tur 3

**A2.11 Dünya ve Günlük sayfaları: Dünya, Kişiler, Günlük, Çatışma** (M; dinlenme A2.10'a taşındı)
- Hedef: taslak. Bugünkü hâl: SS17, SS20.
- Şikâyet: notlar T-SS17, V-SS20; aynı ad iki kez, boş yer tutucu, kutu içinde kutu; dinlenme düğmeleri iki yerde.
- Bileşenler: `dialog`, `tabs`, `card`, `empty`, `button`, `badge`.
- 2. madde durumları: hiç kişi yok; süren görev yok; çatışma yok; çatışma var; uzun günlük.
- Hat B: BA ("Divine Sense"). Dinlenme düğmeleri bu ekranda değildir: Karakter sayfasına, mumların altına taşındı (A2.10; K26). Bu ekran Kapı 1'den sonradır (Tur 3; K26); Kapı 1'de Dünya ve Günlük ayraçları bugünkü içerikle, yeni kabuğun içinde açılır.

**A2.12 Tür adımı** (M)
- Hedef: taslak. Bugünkü hâl: SS1. Şikâyet: C-12, F-SS1 (kesilen özellik kutuları, açıklamasız "30" rozeti).
- Bileşenler: `card`, `radio-group`, `badge`, `tooltip`, `collapsible`; adım zarı.
- 2. madde durumları: hiçbir şey seçili değil; seçili; uzun özellik listesi; 390 tek sütun.
- Korunan davranış (ui-a'da var): adım sırası Tür, Sınıf, Geçmiş; adım zarları. Hat B: BA (tür adları; "Ejderhasoyu" ya da "Ejderdoğan", karar K5).

**A2.13 Sınıf ve başlangıç seviyesi** (M)
- Hedef: taslak. Bugünkü hâl: SS2. Şikâyet: C-13, F-SS2 (kutu içinde kutu, teknik dil).
- Bileşenler: `card`, `radio-group`, `toggle-group` (seviye 1-5), `collapsible`.
- 2. madde durumları: sınıf seçilmemiş; her seviye; uzun sınıf açıklaması.

**A2.14 Geçmiş: nitelik artışı, İnsan'ın ek hüneri** (M)
- Hedef: taslak. Bugünkü hâl: SS3. Şikâyet: C-14, F-SS3 (liste düğmenin üstüne biniyor, özet sütunu taşıyor).
- Bileşenler: `card`, `radio-group`, `select`, `field`, `badge`.
- 2. madde durumları: geçersiz artış; İnsan'da aynı hüner reddi; özet sütununda uzun değer.

**A2.15 Yetenekler: puan satın alma, standart dizi** (S)
- Hedef: taslak; el yazısı sayılar prototip 11. Bugünkü hâl: 12 Kasım notu AJ.
- Şikâyet: +/- düğmeleri 28 piksel; sabit çubuk "Toplam" satırını kapatıyor.
- Bileşenler: A1 sayacı, `toggle-group`, `badge`.
- 2. madde durumları: puan bitti; en düşük ve en yüksek değer; standart dizi.

#### Tur 4

**A2.16 Ekipman** (S). Hedef: taslak. Bugünkü hâl: SS7. Şikâyet: C-17, F-SS7 (bozuk paket listesi, düz A/B kartları). Bileşenler: `card`, `radio-group`, `badge`. Hat B: BA (eşya adları tabloda var).

**A2.17 Açılış sayfası ("Macerayı aç")** (M). Hedef: taslak; prototip 8, 10, 11. Bugünkü hâl: SS11, SS12. Şikâyet: C-19, F-SS11/12 (okunmayan yazılar, iki ayrı tür adı, boş rozet). Bileşenler: `card`, `badge`, `button`, `scroll-area`. Hat B: BA.

**A2.18 Ölüm kurtarma sayacı ve ölüm ekranı** (M). Hedef: taslak. Bugünkü hâl: 12 Kasım notları AD, AE. Şikâyet: sayaç yok; ölümden sonra yazı kutusu açık; ölüm anının ağırlığı yok. Bileşenler: `alert-dialog`, `badge`, `button`. Hat B: yok (başarı ve başarısızlık sayıları API'de var).

**A2.19 Teklif ve alışveriş kartları, sağ panel** (M). Hedef: taslak. Bugünkü hâl: SS14, SS15. Şikâyet: M-3 (ham üçgen ok), M-4 (kutu içinde düğme). Bileşenler: `card`, `button`, `input`, `collapsible`. Hat B: B1a ve B3a (ret nedeni). Para hareketi motorda kalır; ekran yalnız gösterir.

**A2.20 Büyü paneli ve Hazırlık ekranı, oyun içi** (M). Hedef: `UI_S5_EKRANLAR_20261112` görüntüleri bugünkü hâldir; yeni taslak gerekir. Şikâyet: C-19 "kalan büyü yuvaları tasarımı çok kötü", T-SS16. Bileşenler: `card`, `tabs`, `checkbox`, `badge`; mum. Hat B: BA.

Yerleşim kararı: ana menü, ses, logo ve ayar çarkı Tur 2'dedir (A2.8, A2.9); çarkın ve müzik düğmesinin kendisi A1 galerisindedir. Bu, notlar U'daki sırayla çelişir (bölüm 11, Çelişki 3).

---

## 4. Hat B: Motor

Kurallar: aynı anda tek motor kalemi; `game.py` tek yazıcı; dokunulan bölge önce ayrı modüle taşınır ve taşıma davranış değiştirmez; her kalem kırmızı testle başlar; her görevde sabit komşu yolculuk seti koşar; yeni kampanya açan her test tohumu sabitler.

Yolculuk senaryoları (`MOTOR_HAKEM` bölüm 7; üçü de yeni, sabit tohumlu; numaraları kalem planında verilir ve rapor tablosuna türleri eklenir): **S-liman** (liman işi ve ücret), **S-han** (han bulma ve girme), **S-kervan** (kervancı, itme, savaş, tanıklar). Bugün 89 senaryo dosyası var.

Sıra (Kadir onayladı, 13 Kasım 2026; K1, K25): B0, BA, B1a (YÜK-04'ün üç dalıyla), B1c, BS, B3a, [ara kapı], B1b, B2 (B2.0, B2.1, B2.2, B2.3, sonra süre ölçümü ve B2.4 kararı), B3b, B3c (YÜK-12 testiyle), B3d, [Kapı 1], B4, B5 ve Hat C. M-a altı parçadır (tavan yalnız bu aşama için 6; K25), M-b beş. Codex bulguları yerleştirildi (O17; bölüm 4'teki aday tablosu ve T9).

Ruling: B1c, B1a'nın hemen ardına kondu — iki para kalemi ve iki para incelemesi art arda gelir, aynı modül bilgisi taze kalır — yanlışsa maliyeti yalnız sıra değişikliğidir (B1c'nin B1a'ya kod bağımlılığı yok). Ruling: K25'in adını anmadığı üç aday önerildiği gibi yerleştirildi (KRİT-01: B3d, M-b'nin beşinci parçası; YÜK-12: B3c'ye bir kırmızı test; YÜK-16: A2.10) — Kadir'in sözü önerilen "paketle" seçeneğini tek değişiklikle (KRİT-03 ayrı parça) kabul ediyor diye okundu — yanlışsa maliyeti bu üç satırın B5'e taşınmasıdır; kod yazılmadı.

### B0. `narration_source` tur kaydına yazılır (S; sürüyor)
- Durum: bölüm 1. Kadir onayladı (13 Kasım 03:17).
- Kodda bugün var olan değerler (tam liste): `qwen`, `python_memory_response`, `deterministic_fallback`, `deterministic_system`. Başka değer yok (`game.py` ve `dialogue_runtime.py`). Beşinci değer `mixed_engine_model` Kadir'in kararıyla (envanter 5.18) B2.0'da eklenir; B0'da eklenmez.
- %80 ölçütünde **modelden sayılan değerler `qwen` ve `mixed_engine_model`**'dir (karar 5.18; `qwen` hangi sağlayıcı olursa olsun "model" demektir). `python_memory_response`, `deterministic_fallback` ve `deterministic_system` motordan sayılır.
- Bilinen eksik (envanter 5.17): kaynak bildirmeyen çıkışların turu boş kaydediliyor ve motor bildirdikten sonra metni değiştiren üç adım var. Bunu B0 değil B2.0 kapatır; B2.0'dan sonra boş kayıt kalmamalıdır. O zamana kadar yapılan ölçümde boş kayıtların sayısı ayrıca yazılır.
- Küme testi (envanter 5.19): dalda yazıldı (256109d7).
- Push koşulu: tam paketin birinci parçası (para ve kayıt modülleri) yeşil özet verecek.
- Para / kayıt / XP / Geri Al: kayda dokunur. İnceleme: bağımsız, en güçlü model. Geri alma: yan tablo okunmazsa oyun aynen çalışır; commit geri alınır.
- Kadir'in kontrolü: yok (oyunda görünmez). Kanıt: bir oynayıştan sonra kaynak dökümü.

### B0c. Öneri şeridi ve sonuç alanı (S-M; Kapı 1 sonrası)
- Ad notu: ilk sürümde "B0b" idi. Tasarımın "Dilim 0b"si başka bir iştir (çıkışta etiketleme; bu planda B2.0); karışmasın diye adı B0c oldu.
- Ne: bölüm 2 (d)'deki dört alan, B0'ın yan tablosunun yanına. Davranış değişmez.
- Dosyalar: `game.py` (`_run_player_turn_internal` içindeki izin değişkenleri, `_narrate_resolved_turn` içindeki kabul ve ret listeleri), `api/persistence/campaign_store.py`, `api/main.py`.
- Kırmızı test (önerilen ad): `test_turn_record_keeps_open_lanes_and_proposal_outcomes`; sahte model bir kişi önerir, biri kabul biri ret; kayıt ikisini ve ret nedenini tutar; Geri Al sonrası tutarlı.
- Kayda dokunur: bağımsız inceleme. B4.4'ün ön koşuludur.

### BA. Tek Türkçe ad tablosunun genişletilmesi (M)
- Bugün: tek kaynak zaten var. `content/names/tr_names.json` (392 büyü, 64 eşya, 9 takma ad) main'de ve ui-a'da aynı dosya. Motor `ai-dnd/tr_names.py` ile okuyor; arayüz ui-a'daki `src/lib/tr-names.ts` ile aynı JSON'u içe alıyor. İstemdeki "iki ayrı yerde" tespiti bu dosya için doğru değil (bölüm 11, Çelişki 6).
- Asıl ikilik: tür, sınıf, alt sınıf, özellik ve hüner adları tabloda yok; adlar üç ayrı yerden geliyor: `ai-dnd/api/dnd_2024_rules.py` ("Ejderhasoyu"), `src/lib/character-catalog-defaults.ts` (aynısının kopyası), `src/lib/campaign-presentation.ts` ("Ejderdoğan"). Ayrıca `src/lib/skill-label.ts`, `src/lib/catalog-display.ts`, `src/lib/spell-names.ts`.
- Karar önerisi (K4): tek kaynak `content/names/tr_names.json`. Yeni türler: `species`, `classes`, `subclasses`, `features`, `feats`, `conditions`. **Yazıcı Hat B'dir.** Arayüz yalnız `tr-names.ts` üzerinden okur; kendi tablolarını (`campaign-presentation.ts` içindeki ad tabloları, `skill-label.ts`) bu kaynaktan türetir ya da kaldırır. Katalogdaki Türkçe adlar aynı tablodan doldurulur.
- Önce ayrılacak bölge: yok (`game.py`'ye dokunmaz).
- Kırmızı testler (önerilen adlar): `test_every_catalog_species_class_subclass_feat_has_a_table_name`; `test_catalog_names_come_from_the_table` (iki ayrı ad kalmaz); arayüzde `test_no_second_name_table_in_ui`.
- Yolculuk: yok. Para / kayıt / XP / Geri Al: hayır; kimlikler İngilizce kalır, eski kayıt bozulmaz.
- İnceleme: orta model, ucuz kapsamlı inceleme. Adları Kadir okur ve onaylar. Geri alma: tabloda adı olmayan özgün adıyla görünür.
- Kadir'in kontrolü: karakter sayfasında ve savaşta İngilizce özellik adı kalmış mı.

### B1a. İş ücreti hatası (M; para)
- Kayıttan görülen: tur 10 rota `front:offer_answer`, sahip `work`, durum `resolved`. Tur 11 ("10 bakırı alıp teşekkür ediyorum") rota `front:economic`, durum `prepared`: cümle para teklifi olarak okunmuş. Tur 12 onay reddi nedensiz. Tur 13 rota `front:bag`, sahip `inventory`: yalnız kese listesi. Yani ücret büyük olasılıkla tur 10'da ödendi; "para ikinci cümlede geçti" okuması kayıtla uyuşmuyor (bölüm 11, Çelişki 11). Kese değerlerini doğrulamadım.
- Dosya ve işlevler: `game.py` (`_front_step`, `_front_economic_offer`, `_front_work`, `_thread_gate`), `front_proposal.py`, `economic_actions.py` (`prepare_offer`, `confirm_offer`, `_summary`), `world_threads.py` (`wage_due`).
- Önce ayrılacak bölge: `game.py` içindeki `_front_*` kapıları (ekonomi, iş, teklif cevabı, verme, tüketme) ayrı modüle.
- Kırmızı testler (önerilen adlar): `test_taking_the_paid_wage_opens_no_tip_offer` (ücret ödendi; "parayı alıp teşekkür ediyorum" teklif açmaz, kese değişmez); `test_refused_offer_confirmation_gives_the_reason` (ret nedeni sade Türkçe); `test_wage_line_and_purse_move_in_the_same_turn`.
- Yolculuk: S-liman. Para: evet. İnceleme: bağımsız, en güçlü model. Geri alma: commit geri alınır; kayıt biçimi değişmez.
- İkinci model ailesiyle inceleme denemesi (`KESME_SONRASI` 10.9; O15) bu kalemin incelemesinde yapılır; kurulumdan önce Kadir'in ayrıca onayı gerekir.
- Kadir'in kontrolü: limanda işi bitir, "paramı alıp teşekkür ediyorum" yaz; teklif kartı açılmamalı.
- **Pakete giren (K25; Kadir, 13 Kasım 2026, gece): YÜK-04'ün kabul, tüketim ve devir dalları.** Nötr bir cümle yanlış model etiketi alınca iş kabul edilip aynı turda ücret yazılabiliyor, yiyecek tüketilebiliyor, paket teslim edilip ücreti yazılabiliyor (tüketim dalı okunarak doğrulandı; öbür ikisi doğrulanmadı). Yeri bu kalemin ayırdığı bölgenin kendisidir: `_front_offer_gate`, `_front_consume`, `_front_hand_over`. Kırmızı testler (önerilen adlar): `test_neutral_line_labelled_accept_opens_no_job`, `test_neutral_line_labelled_consume_eats_nothing`, `test_neutral_line_labelled_hand_over_delivers_nothing`. Kırmızı testi yazılamayan dal doğrulanmamış sayılır ve düzeltilmez. Kalemin boyutu M'den L'ye çıkar. Tehdit, yangın ve hırsızlık dalları Kapı 1'den sonradır (B5.5).

### B1c. Görev ödülünün birimi: kartın söylediği ödenir (S-M; para; yeni parça, K25 ve K27)
- Kaynak: KRİT-03 (Codex; okunarak doğrulandı, çalıştırılarak üretilmedi). Teklif kartı "Ödül: 25 altın" yazıyor (`dialogue_commitments.render_cards`); ödül yazıcısı aynı sayıyı keseye ekliyor (`adventure/rewards.py`); kese bakır tutuyor (100 bakır = 1 altın). Sonuç: 25 altın söyleniyor, 25 bakır ödeniyor (kent soruşturmasında 20).
- **Karar (K27; Kadir, 13 Kasım 2026, gece): ödül altındır; kartın söylediği ödenir.** Düzeltme yalnız diyalog ve macera görevlerinin ödül yoluna uygulanır; kasaba işlerine dokunulmaz. Kart ve ödeme aynı motor alanından, birimiyle okunur.
- Dosya ve işlevler: `dialogue_commitments.py` (`render_cards`), `adventure/rewards.py` (ödül yazıcısı), ödül sayısını üreten görev ve macera tanımları. Aynı alanı bakır olarak kullanan kasaba işi yolu (`world_threads.py` içindeki `wage_due`) okunur ama değiştirilmez. Tam liste kalem planında çıkarılır; bu satırdaki adlar Codex doğrulama belgesinden alındı, koda yeniden bakılmadı.
- Önce ayrılacak bölge: yok (`game.py`'ye dokunmaz; doğrulamadım, kalem planında bakılır).
- Kırmızı testler (önerilen adlar): `test_offer_card_and_reward_read_one_field_with_its_unit` (kart ve ödeme aynı alanı, birimiyle okur); `test_dialogue_delivery_pays_the_gold_the_card_says` (kart 25 altın der, kese 25 altın artar); `test_adventure_quest_pays_the_gold_the_card_says`; `test_town_job_wage_is_unchanged` (kasaba işi aynı bakırı öder); `test_reward_survives_save_and_undo_once` (ödül bir kez yazılır, Geri Al tam geri alır).
- Bugünkü ödemeyi (25 bakır) bekleyen test varsa (Codex `test_dialogue_quest_offer.py` dosyasını gösteriyor; doğrulamadım) eşit sıkılıkla yeniden yazılır ve onay listesine girer.
- Etki notu: ödenen para 100 katına çıkar (25 bakır yerine 2500 bakır). Kasaba işi iki günde 46 bakır ödüyor; dükkân fiyatlarıyla dengesine Kapı 1 oynayışında bakılır.
- Yolculuk: S-liman'a bir teslimat adımı ya da ayrı senaryo (kalem planında). Para: evet. İnceleme: bağımsız, en güçlü model. Geri alma: commit geri alınır.
- Kadir'in kontrolü: bir teslimatı bitir; kartta yazan altın kadar kesen artıyor mu.

### B1b. Genel sözcükle hana girme (S)
- Kayıttan: tur 16 `local_search / found`; tur 17 `enter / unresolved` ("Girebileceğin belirgin bir yer göremiyorsun."); tur 18 adla giriş `grounded_action / completed`.
- Dosya ve işlevler: `game.py` (`plan_living_world_turn` içindeki giriş dalı ve `explicit_tavern_target`, `_ensure_local_tavern`, `resolve_location_reference`, `_local_place_turn`), `living_world.py` (`has_tavern_reference`).
- Önce ayrılacak bölge: `plan_living_world_turn`'ün giriş dalı.
- Kırmızı test (önerilen ad): `test_generic_inn_word_enters_the_inn_just_found`. Bulma ile girme aynı konum kuralını kullanır.
- Yolculuk: S-han. Para / XP: hayır; konum değişir. İnceleme: orta model, ucuz kapsamlı inceleme. Geri alma: commit geri alınır.
- Kadir'in kontrolü: "han arıyorum", sonra "hana giriyorum".

### BM. Önce model: cümleyi modelden önce yakalayan kelime yolları (M-L; K37)
- Ne: oyuncunun cümlesini modelden önce yakalayan motor yolları (dükkân sorusu, takip, bilgi sorusu, isim söyleme, hitap, söylenti/bilgi kapısı ve benzerleri) tek listede sayılır. Modelin hamle okuması (`front_proposal`) belirleyici olur; bu yollar yalnız model hiç cevap vermezse yedek kalır. Hazır cümle en son çaredir ve kasaba bilgisi yedeğinden geçer; çıplak "bilmiyorum" yok.
- Dayanak: 16 Kasım oynayışı (`OYNAYIS_NOTLARI_20261116.md`, `OYNAYIS_TANI_20261116.md`): 28 hamlenin 11'i hazır cümleyle bitti; 3. hamlede model "konuşmak" okudu, motor "dükkân" kelimesiyle dükkân satırı bastı.
- Sıra: D-249 düzeltmesinden sonra, BS'den önce. İlk adım: yolların sayımı ve her biri için kırmızı test (model okuması X iken motor Y basmaz).
- Ölçüm: her oynayışta tur kaydından (`route-log.jsonl`) modele ulaşmayan ve hazır cümleyle biten hamle sayısı; hedef: para, zar ve kural satırları dışında sıfıra yakın.
- Sınır: para, zar, XP, satın alma ve kural reddi motor cümlesi kalır (B2 kapsamı aynı). Kelime listesiyle yeni yönlendirme eklenmez.
- İnceleme: bağımsız, Opus (tur akışının merkezi; Geri Al ve kayıt testleri koşar).

### BS. Savaş ekranının motor verisi (M)
- Ne: (1) oyuncu olmayan katılımcı için durum alanı (sağlam, yaralı, ağır yaralı); (2) "Yaklaş / Uzaklaş"; (3) doğru bonus eylem listesi (M2: `bonus_rules` bugün yalnız tür yeteneklerini sayıyor); (4) savaş turu sayacı zaten `round` olarak veriliyor, yalnız adı değişir.
- Bugün: `CombatParticipantState` her katılımcının `current_hp` ve `max_hp` değerini sayı olarak veriyor. Yapılı eylem türleri arasında `move`, `disengage`, `dash` var. "Yaklaş / Uzaklaş"ın bunlara nasıl bağlanacağını doğrulamadım.
- Dosya ve işlevler: `ai-dnd/api/serializers.py`, `ai-dnd/api/schemas.py`, `ai-dnd/action_economy.py` (`bonus_rules`, eylem hakları dökümü), `lib/api-spec/openapi.yaml` ve üretilen istemciler.
- Önce ayrılacak bölge: yok (`game.py`'ye dokunmaz).
- Kırmızı testler (önerilen adlar): `test_enemy_health_is_a_state_word_not_a_number`; `test_class_bonus_actions_count_as_available`; `test_approach_and_withdraw_are_structured_actions`.
- Yolculuk: var olan savaş senaryoları ve S-kervan. Para / kayıt / XP: hayır; API sözleşmesi değişir. İnceleme: orta model, bağımsız inceleme (sözleşme). Geri alma: durum alanı eklemedir. Karar K16 (Kadir, 13 Kasım 2026): düşmanın can sayısı API yanıtından da kalkar; bunu bekleyen testler kalem planında sayılır.
- Kadir'in kontrolü: savaşta "Bonus eylem" satırı düğmelerle tutuyor mu.

### B3a. Nedenli ret (2a; M)
- Bugün: ret metinleri için tek tablo zaten var: `ai-dnd/refusals.py` (`REFUSAL_TEXT`, 116 satır; genel cümle `FALLBACK_TEXT`). Yeni tablo yazılmaz; bu genişletilir.
- Kapsam: "Çevrede şimdilik belirgin bir değişiklik olmuyor" (`game.py`, `_fallback_narration`; tur 40, 42); "Öyle olsun bakalım" (`interaction_adventure.py`, `immersive_unknown`; tur 55, 56); "İşlem gerçekleşmedi; hiçbir şey ödenmedi." (`economic_actions.py`, `_summary`; tur 12); savaş düğmelerinin ham kodları (M3: `paladin-controls.tsx`, `fighter-controls.tsx`, `action-economy-panel.tsx`; çeviri `src/lib/combat-ui-contract.ts`).
- Önce ayrılacak bölge: `_fallback_narration` ve çevresi.
- Kırmızı testler (önerilen adlar): `test_no_refusal_reaches_the_player_without_a_reason`; `test_unknown_code_shows_one_general_line_and_logs_the_code`; `test_repeated_refused_move_does_not_repeat_the_same_empty_line`.
- Yolculuk: S-kervan (büyüyle kese), S-liman (onay reddi). Para: `_summary` para kodundadır; yalnız metin değişir. İnceleme: o parça için bağımsız, en güçlü model; gerisi orta model. Geri alma: karşılığı olmayan kod genel cümleye düşer.
- Kadir'in kontrolü: "büyüyle kesesini alıyorum" yaz; neden olmadığını söylüyor mu.

### B2. Dilim 1: parasız sonuçları model anlatır (L; beş alt kalem)
- **Düzeltme 22 Kasım 2026 (plan incelemesi I7, M12, M18; Kadir "B2 planını şimdi düzelt"):** (1) B2 tur bölmeden (TB) sonra başlar; `finish_turn`'ü ayırmak elle çıkarma işidir ve TB'nin parçasıdır. (2) Anlatı yeni bir ad içerdiği için tümden reddedilmez: "reddetme, onar" kuralı (Kadir; NPC tasarımı §7.2 "NPC'nin sözü olduğu gibi kalır"). Tümden ret yalnız motorun reddettiği bir eylemi başarılı anlatan metin içindir. (3) Sayılar 13 Kasım'dandır; iş başlarken yeniden ölçülür (aşağıda). Önceki metin: `AI-DND-TOOLS/measure/plan-review-20261122/YENIDEN_TASARIM_PLANI_20261113.before-b2-fix.md`.
- Kapsam: bölüm 2 (a)'daki 34 çıkış. Para, yağma, satın alma, teklif, zar ve XP satırı motor cümlesi kalır. Savaşta en çok üç cümle.
- Alt kalemler, sırayla: **B2.0 çıkışta etiketleme** (aşağıda); B2.1 varış ve gezinme (7 çıkış); B2.2 kimler var ve inceleme (9); B2.3 arama ve konuşmayı bitirme (3); B2.4 savaş turu sonucu (15).
- **B2.0, çıkışta etiketleme (S-M; tasarımın "Dilim 0b"si; envanter 5.17 ve 5.18).** Kaynak, turun bittiği tek noktada, metnin son hâliyle birlikte etiketlenir. Kaynak bildirmeyen çıkışlar (envanter 43 `return` ve 4 dış çıkış sayıyor; ben 42 doğrudan dönüş saydım, fark sayım tanımından; iş başlarken tek liste çıkarılır; bölmeden sonra çıkışlar üç katmanda: `game_parts/turn_front.py` (yalnız orada 39 `direct_response`), `game_parts/turn.py` ve `game.py`; tek liste üçünü birden sayar) ve metni sonradan değiştiren üç adım (`_person_answers_stock`, `_the_rest_of_the_line`, kapı metinleri) bu yolla kapanır. Son metin model anlatımı ile motor satırının birleşimiyse değer `mixed_engine_model` olur. Kayıttaki izinli liste (`campaign_store._NARRATION_SOURCES`) aynı değeri alır; B0'ın küme testi önce kırmızıya döner ve eklemeyi zorlar. Bu iş, B2'nin "çıkışları ayrı modüle taşı" adımıyla aynı bölgededir; o yüzden B2'nin ilk alt kalemidir ve tavan sayısını değiştirmez. Davranış değişmez; para ve Geri Al'a dokunmaz; kayıttaki izinli listeye dokunduğu için bağımsız inceleme ister.
- B2.0'ın kırmızı testleri (önerilen adlar): `test_every_turn_exit_saves_a_source`; `test_text_changed_after_the_engine_reported_is_labelled_by_its_final_form`; `test_model_narration_joined_with_an_engine_line_is_mixed_engine_model`.
- **B2.4 koşulludur (inceleme D8).** B2.1-B2.3 bitince tur süresi ölçülür (K15'teki yöntemle, iki kipte). Savaş anlatımının yapılıp yapılmayacağına Kadir o ölçümle karar verir. Bugünkü tahmin: yerel modelde her vuruşa yaklaşık 6 sn, bulutta yaklaşık 2 sn ekler.
- Dosya ve işlevler (13 Kasım adlarıyla; bölmeden sonra çoğu `game_parts/` altında, `turn.py` ve `turn_front.py` başta; iş başlarken `graphify query` ile yerleri yeniden yazılır): `game.py` (`finish_turn`, `_dispatch_player_turn`'ün doğrudan dönüşleri, `_narrate_resolved_turn`, `_narration_fact_packet`, `_narrator_fact_view`, `finalize_narration`, `_drop_repeated_sentences`, `_combat_narration`, `_scene_presence_text`), `narration_claims.py` (`packet_from_result`), `grounded_action.py` (`resolve_turn`), `town_knowledge.py` (`board_turn`), `local_places.py`, `action_economy.py` (`execute`).
- Önce ayrılacak bölge: (1) `finish_turn` ve çıkış sınıflaması ayrı modüle (B2.0 bunu yapar); (2) yeni denetim kuralları yeni modüle (`_narration_safety_decision` büyütülmez).
- Kırmızı testler, sahte modelle (önerilen adlar): `test_arrival_result_is_given_to_the_narrator_as_fact`; `test_presence_is_narrated_from_the_fact_packet`; `test_unbacked_coin_item_or_damage_in_narration_is_removed_or_repaired` (desteksiz para/eşya/hasar cümlesi çıkar ya da motor değeriyle onarılır; anlatının kalanı durur; kese ve çanta bayt bayt aynı); `test_a_new_name_in_narration_is_not_registered_but_the_narration_stays` (ad kayda, dünyaya ve günlüğe girmez; metin kalır); `test_refused_action_cannot_be_narrated_as_done` (tümden ret yalnız bu durumda); `test_success_narrated_as_failure_is_repaired` ve `test_failure_narrated_as_success_is_repaired` (sahte model, zarla çelişen anlatı); `test_front_reading_and_narration_make_two_model_calls_never_three` (kod bu sınırı zaten koyuyor; eksik olan test); `test_combat_narration_is_at_most_three_sentences_and_the_dice_line_stays`; `test_ready_line_comes_only_after_model_failure_or_failed_repair` (onarılabilen anlatı hazır cümleye düşmez); `test_speaker_label_and_model_text_are_joined_in_one_place`; `test_same_scene_sentence_is_not_repeated_next_turn`; `test_undo_after_a_narrated_turn_restores_purse_and_bag`.
- Yolculuk: üçü de; var olan komşu set. Bölüm 2 (b)'deki testler eşit sıkılıkla yeniden yazılır ve onay listesine "[GEVŞETME OLABİLİR]" ile girer.
- Para / kayıt / XP / Geri Al: para satırına dokunmaz ama para yalanını yakalayan denetimi yazar; kayıt ve Geri Al testi var. İnceleme: bağımsız, en güçlü model; her alt kalemde.
- Bitiş koşulu: tur süresi bölüm 2 (c) yöntemiyle yeniden ölçülür; Kadir'in oynayacağı kipte (bulut zinciri) ve ayrıca kısa bir yerel model ölçümüyle (K15). Bugünkü yerel değerler: bütün turlar 12,0 sn, model çağıran turlar 14,3 sn. Bulut kipinde tur başına ölçüm henüz yok. Bu sayılar 13 Kasım'dandır: B2.1 başlamadan rota ve kullanım kaydından taze bir K15 taban ölçümü alınır ve karşılaştırma ona göre yapılır; K15 eşikleri (bulut 4 sn, yerel 8 sn) ve %80 ölçütü değişmez.
- Geri alma: model düşerse ya da onarım başarısız olursa (denetim onarılmış metni de iki kez geri çevirirse) tur hazır cümleyle biter (S4). Denetim önce onarır: desteksiz para/eşya/hasar cümlesini çıkarır ya da motor değeriyle düzeltir, yeni adı kayda almaz; metnin tümünü yalnız motorun reddettiği eylemi başarılı anlatıyorsa reddeder. Yüzey listesi tek yerde durur; boşaltılınca bugünkü davranış döner.
- Kadir'in kontrolü: "burada kimler var", bir yere git, bir savaş turu; cümleler anlatı gibi mi, para ve zar sayıları aynı mı.

### B3b. Yazı ile düğme aynı yol (2b; M)
- Ne: yazıyla söylenen sınıf ve tür yeteneği (İlahi Darbe, Şifa Eli, Divine Sense ve diğerleri) düğmenin gönderdiği yapılı eyleme eşlenir. Eşleme BA'nın tablosundan yapılır.
- Kayıttan: tur 61 ("ilahi darbe kullanıyorum") rota `skipped:combat`, sahip `narrative`, iki model çağrısı; motor sonucu yok.
- Dosya ve işlevler: `action_economy.py` (`natural_command`, `execute`), `tr_names.py`, `intent_contract.py`, `paladin_features.py`, `api/schemas.py`.
- Önce ayrılacak bölge: `_dispatch_player_turn`'ün savaş komutu bölümü.
- Kırmızı testler (önerilen adlar): `test_typed_divine_smite_resolves_like_the_button`; `test_typed_feature_without_engine_result_is_never_narrated_as_done`.
- Yolculuk: S-kervan. Kayıt: evet (büyü yuvası harcar). İnceleme: bağımsız, en güçlü model. Geri alma: eşleme tablosundan satır çıkarılır; yazı eski yola döner.
- Kadir'in kontrolü: savaşta "ilahi darbe kullanıyorum" yaz; hasar ve yuva düşüyor mu.

### B3c. Konuşma hamleyi yutmaz; savaş onayı tutarlı (2c; M)
- Kayıttan: tur 33 ("Bir saat kısa dinleniyorum") rota `front:wait` ama sahip `dialogue`; dinlenme çalışmadı. Tur 44 ("Kervancı itiyorum") `dialogue`; tur 46 `clarification` (kavga sorusu); tur 55-56 (muhafız) `proposal_rejected`; tur 58 `dialogue`, zarsız.
- Dosya ve işlevler: `game.py` (`_dispatch_player_turn`'ün `wait`, `strike`, `blow_asked` dalları, `_ask_about_the_blow`), `dialogue_runtime.py` (`resolve_turn`), `timed_gameplay.py` (`pass_time`, `resolve_input`), `combat_lifecycle.py` (`unbound_attack_reply`), `bold_acts.py`.
- Önce ayrılacak bölge: `_dispatch_player_turn`'ün konuşma öncesi eylem denemeleri.
- Kırmızı testler (önerilen adlar): `test_short_rest_typed_during_a_conversation_runs_the_rest`; `test_push_asks_the_same_fight_question_for_every_person`; `test_missing_case_suffix_still_reads_as_the_push`.
- Yolculuk: S-kervan. Kayıt ve XP: evet (dinlenme can ve zamanı değiştirir; savaş başlatır). İnceleme: bağımsız, en güçlü model. Geri alma: commit geri alınır.
- Kadir'in kontrolü: biriyle konuşurken "kısa dinleniyorum" yaz; dinlenme oluyor mu.

### Codex denetiminden Kapı 1 öncesine adaylar (yerleşim: K25 ve K27, Kadir kapattı, 13 Kasım 2026 gece)

**Karar:** YÜK-04'ün üç dalı B1a'ya paketlendi; KRİT-03 ayrı parça oldu (B1c; ödül altın); tavan yalnız M-a için 6. KRİT-01, YÜK-12 ve YÜK-16 önerildiği gibi yerleşti (Ruling; bölüm 4, Sıra). Aşağıdaki tablo değerlendirmenin kaydıdır; "Önerilen yer" sütunu kararla güncellendi.

Kaynak: `CODEX_DENETIM_NIHAI_RAPOR_20261113.md` (63 bulgu) ve `CODEX_NIHAI_DOGRULAMA_20261113.md` (63'ün 10'u bağımsız okunarak doğrulandı; hiçbiri çalıştırılarak üretilmedi). Bütün bulgular T9'dadır (bölüm 8). **Kural (Kadir, 13 Kasım 2026): her düzeltme önce kırmızı testle başlar; kırmızı test yazılamayan bulgu doğrulanmamış sayılır.**

| Bulgu | Değerlendirme | Önerilen yer |
|---|---|---|
| **KRİT-01** (ortam olayı kaydından sonra hata; okunarak doğrulandı) | Kapı 1'in dört kutusunu engellemez ve seyrek tetiklenir: kayıttan sonra Geri Al parmak izi adımında hata gerekir; canlı veri kaybı görülmedi. Ama kayıp sessizdir (dünya eski hâle döner, makbuz ve hikâye satırı kalır) ve Kadir'in 30 dakikalık kaydını bozabilir. Düzeltme dar: `api/main.py` içindeki ortam olayı kayıt bloğu | **Kapı 1'den önce.** Yeni kalem **B3d**, M-b'nin beşinci parçası. Kırmızı test (önerilen ad): `test_fingerprint_failure_after_an_ambient_commit_keeps_the_saved_world`. Kayıt ve Geri Al: bağımsız inceleme, en güçlü model |
| **KRİT-03** (kart "25 altın" der, 25 bakır öder; okunarak doğrulandı) | Kadir Kapı 1'de bir ipucunu izleyip teslimat alırsa bunu görür: söylenen para ile ödenen para farklı. B1a'nın konusuyla aynıdır. Hangisinin yanlış olduğu belli değil; birim kararı Kadir'de (K27). Codex'in uyarısı: aynı alanı bakır olarak kullanan kasaba işlerine topluca ×100 uygulanmaz | **Kapı 1'den önce, ayrı parça: B1c** (K25). Birim altın; kartın söylediği ödenir (K27). Kırmızı testler B1c'de. Para: bağımsız inceleme, en güçlü model |
| **YÜK-16** (günlükte kabul düğmesi yok) | Diyalog teklifi "Görev günlüğünden kabul edebilirsin" diyor (`dialogue_commitments.py`). Günlükte kabul düğmesi yalnız eski teklif listesinde var; dinamik görev satırlarında yok (`quest-journal-section.tsx`; denetlenen commit'te okundu). "Bir ipucunu izle" kutusunu doğrudan engeller. Yazıyla kabulün çalışıp çalışmadığına bakılmadı | **Kapı 1'den önce.** Hedef resimde "Açık işler" Karakter sayfasındadır ve "Henüz kabul etmedin" yazar; kabul düğmesi **A2.10**'a (Tur 2) girer, motorun cümlesi düğmenin yerini söyler. Yeni parça değil. İptal düğmesi ORTA-29 düzelmeden eklenmez (API'den iptal kurye paketini oyuncuda bırakıyor). A2.10 Tur 2'dedir, yani Kapı 1'den öncedir (K26 bunu değiştirmedi) |
| **YÜK-04: kabul, tüketim, devir dalları** (tüketim dalı okunarak doğrulandı) | **B3b ve B3c ile örtüşmüyor.** B3b yazılan sınıf yeteneğini düğmenin yoluna bağlar; B3c konuşmanın hamleyi yutmasını düzeltir (bunun tersi). Üç dal `_front_offer_gate`, `_front_consume` ve `_front_hand_over` işlevlerindedir (denetlenen commit'te okundu); bunlar B1a'nın "önce ayrılacak bölge"sinin kendisidir ve B1a'nın ilk kırmızı testi aynı sınıftan bir hatadır (nötr söz para teklifi sanılıyor). Etkisi Kapı 1'de görünür: nötr bir cümle iş kabul edip aynı turda ücret yazabilir, yiyeceği tüketebilir, paketi teslim edip ücreti yazabilir. Canlı modelin yanlış etiket sıklığı ölçülmedi | **Kapı 1'den önce, B1a'ya paketlendi** (K25). Kırmızı testler (önerilen adlar): `test_neutral_line_labelled_accept_opens_no_job`, `test_neutral_line_labelled_consume_eats_nothing`, `test_neutral_line_labelled_hand_over_delivers_nothing`. Para ve kayıt: bağımsız inceleme, en güçlü model. Tehdit, yangın ve hırsızlık dalları Kapı 1'den sonra (B5.5) |
| **YÜK-11 ve YÜK-13** (başlangıç eşyası; YÜK-11 kısmen izlendi, YÜK-13 doğrulanmadı) | Para, kayıt ya da dört kutu değil. Kadir'in Kapı 1 karakteri dart ya da hançer paketi taşıyorsa ilk atışta paketin tamamı gider; kalkanını atarsa +2 Zırh Sınıfı kalır. Dosyaları (`character_creation.py`, `weapon_attack.py`, `equipment_economy.py`, `pocket.py`) B1a ve B3 bölgelerinden ayrıdır; yeni bir parça ister | **Kapı 1'den sonra,** B5.6'nın ilk işi (K25'te öne alınmadı) |
| Ek aday: **YÜK-12** (geri alınan savaş onayı yaşar; doğrulanmadı) | B3c'nin bölgesindedir (`combat_lifecycle.py`, bekleyen saldırı onayı). Sonraki ilgisiz "evet" eski hedefe saldırı başlatabilir | B3c'ye bir kırmızı test olarak eklenir: `test_undone_fight_question_does_not_answer_a_later_yes` (Ruling; bölüm 4, Sıra). Test yazılamazsa bulgu doğrulanmamış sayılır ve B3c'ye girmez |

Kapı 1'den önceye **almadığım** ama Kapı 1'i etkileyen iki bulgu, kod yazmadan önlem: ORTA-08 (aynı aylık Haiku dosyasına yazan iki süreç bir artışı kaybedebilir): Kapı 1'de ve her sayaç okumasında tek sunucu süreci çalışır (O8, O11). ORTA-10 (anlatıcının yanlış kese cümlesi): B2'nin "para yalanını yakalayan denetim" testine bakiye cümlesi eklenir.

### B4. Kapı 1'den sonra (sıra Kapı 1'in notlarından çıkar)

| # | Kalem | Dosya ve işlevler | Para / kayıt / XP | Boyut | İnceleme |
|---|---|---|---|---|---|
| B4.1 | 2d: bileşik hamle (tanış ve sor) | `local_dialogue.py` (`INTRODUCTION_REPLIES`), `interaction_adventure.py`, `game.py` | Hayır | M-L | Orta |
| B4.2 | Dilim 3: model iş önerir, ücreti motor belirler | `content/world/catalog/thread_templates.json`, `world_threads.py`, `adventure/dialogue_jobs.py` | Para ve kayıt | L | Bağımsız, en güçlü |
| B4.3 | Dilim 4: üslup (`LOCAL_DM_EXAMPLE`, NPC sesi, beş sabit sahnede karşılaştırma) | `api/ollama_adapter.py` | Hayır | S-M | Orta; Kadir puanlar |
| B4.4 | Öneri şeritleri Ş2-Ş7; sıra B0c ölçümünden | `game.py` (`validate_npc_proposal`, `create_local_feature`, `validate_location_proposal`, `validate_shop_proposal`) | Kayıt | şerit başına M | Bağımsız |
| B4.5 | Cinayet XP kuralı (M1) | `xp.py` (`award_defeated_combat`, `award_downed`, `reward_for`), `fallen.py`, savaşı kimin başlattığını tutan yeni alan | XP ve kayıt | M-L | Bağımsız, en güçlü |
| B4.6 | İş şablonlarının anlaşılmaz satırları | `thread_templates.json` (`public_line_template`) | Hayır (yalnız içerik) | S | Ucuz; Kadir okur |
| B4.7 | Açılış cümlesindeki ham köken metni | `api/opening_narrative.py` ("... uzakta kaldı.") | Hayır | S | Ucuz |
| B4.8 | Yer kimliği: peynir evi sokak pazarı gibi anlatılıyor | `local_places.py`, `game.py` (`_local_place_turn`) | Konum kaydı | M | Orta |
| B4.9 | Motor cümlelerindeki İngilizce sözcükler ("Prone", "Dagger") | `game.py` (`_unarmed_save_text`), BA tablosu | Hayır | S | Ucuz |
| B4.10 | Şifa Eli miktarı (karar K10) | `paladin_features.py`, `action_economy.py` | Kayıt | S | Orta |
| B4.11 | Faz 2 borçları: D-020, D-056, D-061, D-062; "Söyle" kipi konuşma açılmadan çalışmıyor; yazıyla satın alma döngüsü; 12 Kasım bulguları | çeşitli | D-062 ve satın alma: para | her biri S-M | Para olanlar bağımsız |
| B4.12 | 4D: han odası, nesne durumu, Neverwinter Wood yolu, bayat sahne | çeşitli | Kayıt | L | Bağımsız |
| B4.13 | Muhafız öldürülünce yasanın görünür tepkisi (başarı ölçüsünün "seçimin sonucunu görme" kutusu). Önce: kervancı ölünce çalışan tepki muhafızda neden görünmedi, kayıttan bakılır | `world_reactions.py`, `witness_recall.py`, `fallen.py` | Kayıt (dünya durumu) | M | Bağımsız |
| B4.14 | Kurulum özetinde can ve inisiyatifin onaydan önce hesaplanıp verilmesi (karar K17); o zamana kadar A2.4'te bu iki kutu yok | karakter oluşturma yanıtı (`api/schemas.py`, `api/serializers.py`); hesabın yeri kalem planında bulunur | Hayır (kayıttan önce; önizleme) | S-M | Orta |

B4 kalemlerinin kırmızı testleri, yolculukları ve geri alma yolları kendi kalem planlarında yazılır. B4.5'in kuralı kapalıdır (`KESME_SONRASI` 10.8, karar 1).

**Yerleştirme özeti:** envanter 5.1 B1a; 5.2 B1b; 5.3 B4.3 ve Kapı 1'in bulut zinciriyle oynanması; 5.4 B4.2; 5.5 B4.6; 5.6 B0; 5.7 iş yok; 5.8 B2; 5.9 B4.7; 5.10 B3b; 5.11 B3c; 5.12 B3a; 5.13 B4.5; 5.14 B4.10; 5.15 B4.4; 5.16: M1 B4.5, M2 BS, M3 B3a, M4 B3b. Açılış cümlesi B4.7; peynir evi B4.8; "Prone" B4.9. İkinci sürümde eklenenler: envanter 5.17 ve 5.18 B2.0; 5.19 B0; muhafız ölünce yasa tepkisi (notlar W-3) B4.13.

### B5. Codex denetiminden gelenler (Kapı 1'den sonra; O17)

Sıra Kapı 1'in notlarından çıkar; B4 ile aynı kuyruktadır. Her bulgu önce kırmızı testle başlar; kırmızı test yazılamayan bulgu doğrulanmamış sayılır ve düzeltilmez. Bulgu başına satır T9'dadır (bölüm 8). 53 bulgu bağımsız doğrulanmadı.

| # | Kalem | Bulgular | Para / kayıt / XP / Geri Al | İnceleme |
|---|---|---|---|---|
| B5.1 | Kayıt ve Geri Al bütünlüğü | YÜK-05, YÜK-09, YÜK-10, YÜK-18, ORTA-01, ORTA-02, ORTA-03, ORTA-04, ORTA-12, ORTA-20, ORTA-21 | Kayıt ve Geri Al | Bağımsız, en güçlü; bulgu başına ayrı kırmızı test |
| B5.2 | İşlem kimliği ve eşzamanlı istekler | YÜK-01, YÜK-02, YÜK-06, ORTA-11, DÜŞ-02, DÜŞ-05 | Kayıt (çift işlem) | Bağımsız, en güçlü |
| B5.3 | Para, ödül ve eşya muhasebesi | KRİT-04, YÜK-03, YÜK-14, ORTA-29; KRİT-02 kapandı (D-166) | Para, XP, eşya | Bağımsız, en güçlü. YÜK-14'te beklentiyi sabitleyen test yeniden yazılır ve onay listesine girer |
| B5.4 | Görev ve yolculuk akışı | YÜK-15, YÜK-21, YÜK-22, YÜK-23, ORTA-28, ORTA-30 | Kayıt (görev ve konum) | Bağımsız |
| B5.5 | Yanlış model etiketi: YÜK-04'ün tehdit, yangın ve hırsızlık dalları | YÜK-04 (üç dal) | Kayıt (ilişki, suç kaydı) | Bağımsız |
| B5.6 | Savaş ve kural doğruluğu; ilk iş başlangıç eşyası | YÜK-11, YÜK-13, YÜK-17, YÜK-19, YÜK-20, ORTA-19, ORTA-24, ORTA-25, ORTA-26, ORTA-27 | Kayıt (envanter, can, yuva) | Bağımsız; envantere dokunanlar en güçlü |
| B5.7 | Model zinciri, harcama sayımı, gizlilik | YÜK-07, ORTA-07, ORTA-08, ORTA-09 | Harcama sayacı (para yüzeyi); YÜK-07 gizlilik | Bağımsız, en güçlü. YÜK-07 Kapı 3'ten (başkaları oynamadan) önce biter |
| B5.8 | Arayüz ile motor arasındaki sözleşme | YÜK-08, ORTA-13, ORTA-31; ORTA-22'nin motor yanı | Hayır (sözleşme) | Orta; sözleşme değişirse bağımsız |
| B5.9 | Test ve CI altyapısı | ORTA-15, ORTA-16, ORTA-17, DÜŞ-03 | Hayır | Ucuz. ORTA-17 (CI'da dört yolculuk modülü yok) küçüktür ve öne alınabilir. ORTA-15'in bir dosyası D-084 ile düzeldi (PR #40) |
| B5.10 | Belgeler ve sözleşme metinleri | ORTA-05, DÜŞ-01, DÜŞ-04, DÜŞ-06 | Hayır | Ucuz |

Arayüz ekranlarına giden bulgular: YÜK-16 A2.10; ORTA-14 A2.4; ORTA-18 A2.15; ORTA-22 A2.11; ORTA-02 ve ORTA-31'in görünen yanı A2.1; YÜK-08'in görünen yanı A2.7. ORTA-06 (oyuncu başına kota) Aşama 3'tedir (K24 b).

---

## 4b. Hat C: hikâye içi öğeler, efektler, atmosfer (Kapı 1'den sonra)

Neden ayrı hat: Kadir'in prototipte onayladığı bu öğeler ilk sürümde "havuz"daydı. Havuz "bir kapı göstermedikçe yapılmaz" demektir; bu öğelerin önceki planlardan düşmesinin nedeni de buydu (inceleme D2). Bu hat onlara ad, sıra ve hedef verir. Kapı 1'den önce başlamaz.

Hedef resim: bu hatta onaylı hedef **var**: `UI_PROTOTIP_V4_20261111/index.html` ve `PROTOTIP_ENVANTERI` satırları. Her kalem "Arayüz işi" kurallarıyla biter (sekiz madde, ayrı göz, Kadir'in kabulü). Motor alanı gereken yerde alanı Hat B yazar (tek yazıcı, kırmızı testle); arayüz veriyi uydurmaz. Sıra, envanter bölüm 6'daki sıradır.

| # | Kalem | Prototip satırları | Motor verisi | Boyut | Model |
|---|---|---|---|---|---|
| C1 | Hikâye içi öğeler: mürekkep altçizgili bilgi kutuları (eşya, kişi, yer); "Defterine ekle" ve Notlar paneli | P32, P33 | Bilgi kutusu: anlatıdaki kişi, yer ve eşyanın kimliği işaretli gelmeli (bugün geliyor mu doğrulamadım). Notlar: oyuncu notu alanı (donuk H parçasında tanımlı) | M | İlk bilgi kutusu en güçlü; gerisi orta |
| C2 | Efektler: beş büyü efekti (ateş, soğuk, yıldırım, nekrotik, ışınsal), vuruş, şifa; var olan efekt kaydı altyapısının üstüne | P19-P26 | Hasar türü (büyü yanıtında dolu mu doğrulanacak); şifa kaynağı (tur yanıtında var, kalıcı alan yok) | L (efekt başına S-M) | İlk efekt en güçlü; gerisi orta |
| C3 | Atmosfer: önce doğrulama (katman oyunda görünüyor mu; motor havayı dolduruyor mu), sonra genişletme (vakit ve mekân tablosu, kalabalık, ateş, pencere, hava, mekâna göre örnek satırlar, 14 öğe kuralı) | P27-P31 | Günün vakti var; mekân türü ve kimliği, kalabalık, ateş, pencere, hava: yok ya da doğrulanmadı | M-L | Orta |
| C4 | Kalan prototip öğeleri: mum ışığı havuzu, sayfa çevirme, mührün kintsugi onarımı | P5, P6, P12 | Kintsugi için şifa kaynağı (C2 ile aynı alan) | M | Orta |
| C5 | 3B zar (K20 onaylanırsa; `three` paketi) | P15'in 3B hâli | Yok; sayı A1'deki SVG zarla aynı motor verisinden | M | En güçlü |

Kitap yönü taslağından gelenler (A0b): T11 (mekân atmosferi kitabın çevresinde) ve G9 (gündüz çevresi) C3'e; G2 (sayfa çevirme hareketi) ve G3 (mühür, mum, kalem ve lambanın elle çizilmiş hâlleri) C4'e girer. G1 (sayfalama) Hat C'de değildir; Kapı 1'den sonra, A2.7'nin ardından ayrı deneme ve ayrı kalemdir (K26).

Bağımlılık: C2, C3 ve C4'teki kintsugi ile C1'deki Notlar, Kadir'in dondurduğu E (mekân ve sahne verisi) ve H (durum ve ayrıntı verisi) parçalarının bazı alanlarını ister (Çelişki 18; karar K23). C1'in bilgi kutuları, C4'ün ilk iki öğesi ve C5 yeni motor alanı istemez. C3'ün doğrulama adımı kod yazmadan yapılır.

Kurallar prototipteki gibidir: efekt seviyesi Kapalı, Az, Tam; hareketi azalt ayarına uyulur; en çok 14 hareketli öğe; sekme gizlenince durur; sayı her zaman yazılı kalır; hiçbir efekt motorun vermediği bir sonucu göstermez. Her kalemin kendi planı, kırmızı testleri ve görüntü kanıtı başlamadan önce yazılır.

---

## 5. Hatlar arası bağımlılık ve ortak dosyalar

| Ortak dosya | Tek yazıcı | Sıra ve kural |
|---|---|---|
| `lib/api-spec/openapi.yaml` | Hat B | Önce Hat B değiştirir ve main'e girer; Hat A main'i kendi dalına alır. Hat A bu dosyaya yazmaz |
| Üretilen istemciler: `lib/api-client-react`, `lib/api-zod` | Hat B | `openapi.yaml` ile aynı commit'te üretilir. Hat A elle düzeltmez |
| `content/names/tr_names.json` | Hat B (BA) | Hat A yalnız okur. Eksik ad görürse deftere yazar |
| `ai-dnd/tr_names.py` | Hat B | |
| `src/lib/tr-names.ts` | Hat A | Yalnız okuma katmanı; tablo içeriği taşımaz |
| `ai-dnd/api/schemas.py`, `ai-dnd/api/serializers.py` | Hat B | |
| Kayıt şeması ve yan tablolar (`campaign_store.py`) | Hat B | Her değişiklik bağımsız inceleme |
| `CLAUDE.md` | Kadir'in onayıyla tek PR (O9) | İki hat da yazmaz |
| `src/lib/combat-ui-contract.ts` | Hat A | Ret metinleri motordan gelir (B3a); bu dosya yalnız gösterim |

**Arayüzün motordan beklediği veriler:**

| Veri | Bugün | Kalem | Bekleyen ekran |
|---|---|---|---|
| Düşman canı durum olarak | Yok; sayı veriliyor | BS | A2.1 |
| "Yaklaş / Uzaklaş" eylemi | `move` ve `disengage` var; bağlantısı doğrulanmadı | BS | A2.1 |
| Eylem haklarının doğru listesi (Eylem, Bonus eylem, Tepki, hareket) | Bonus eylem yanlış | BS | A2.1 |
| Yapılamayan eylemin Türkçe nedeni | 116 satırlık tablo var; düğmeler ham kod basıyor | B3a | A2.1, A2.19 |
| Seviye atlama verisi | Var (`level_up`, kazanılan can) | - | A2.7 |
| Ölüm kurtarma verisi | Var (başarı ve başarısızlık sayısı) | - | A2.18 |
| Tür, sınıf, alt sınıf, özellik, hüner adları | Tabloda yok | BA | A2.1, A2.2, A2.4, A2.10, A2.11, A2.12, A2.17, A2.20 |
| Onaydan önce can ve inisiyatif | Yok; karakter oluşunca hesaplanıyor | yok (K17) | A2.4 |
| XP eşiği | Arayüzde ayna tablo; bir test motorla eşitliği denetliyor | - | A2.10 |
| Zar sonucu verisi | Hangi turların taşıdığı doğrulanmadı | - | A2.7 |
| Hikâyedeki saat ve günün bölümü (T8) | **Var.** `campaign_time` (saat 0-23; günün bölümü: şafak, gündüz, akşam, gece; yazılı tarih) ve `world.time_of_day`. Arayüz bugün okuyor (`environment-theme.tsx`, `scene-atmosphere.ts`, `campaign-context-panel.tsx`). Sözleşmede ve arayüz kodunda okundu; çalışan oyunda her turda dolu geldiği denenmedi. Dünya bilgisi yoksa günün bölümü "gündüz" varsayılır | - | A2.8, A2.6 |
| Hasar türü, şifa kaynağı, kalabalık, ateş, pencere, hava | Yok ya da doğrulanmadı | Hat C başlarken Hat B yazar (K23) | C2, C3, C4 |
| Anlatıdaki kişi, yer, eşya kimlikleri; oyuncu notu | Doğrulanmadı | Hat C başlarken Hat B yazar (K23) | C1 |

Kural: veri hazır değilse ekran bekler ya da o parça olmadan teslim edilir; hangisi olduğu ekranın raporunda ilk satırda yazılır.

---

## 6. Kapılar ve kayıt

Ledger: `C:\Users\Kadir\Desktop\AI - DND\.superpowers\sdd\yeniden-tasarim-20261113\progress.md` (iki hat için iki bölüm; kararlar "Ruling", küçük bulgular "park").

| Kapı | Koşul | Kim geçirir |
|---|---|---|
| Galeri kapısı (A1 sonu) | Altı görüntü (üç tema, iki genişlik), hedef resimlerle yan yana karşılaştırma, ayrı göz incelemesi, arayüz testleri yeşil | Kadir, ekran görüntüsünden |
| Her ekran | Sekiz madde, ayrı göz, "Kısayol:" satırı | Kadir |
| Her arayüz turunun sonu | Kadir en az 10 dakika oynar; oynayıştan önce ve sonra sayaç okunur ve fark yazılır (K24); Tur 1'in sonunda dört kutunun durumunu not eder (Kapı 1 sayılmaz); **tam paket ve bütün dal incelemesi** (en güçlü model); main'e PR için taze onay | Kadir |
| Her motor kaleminin sonu | Kırmızı-yeşil test, komşu yolculuk seti, inceleme; Kadir'in tek kontrolü (bölüm 4) | Kadir |
| Motor ara kapısı (B3a'dan sonra; K1) | **Tam paket ve bütün dal incelemesi**; Kadir 10 dakika oynar | Kadir |
| Kapı 1 öncesi | **Sert ön koşullar:** O11 (Haiku sayacının Kapı 1 kipinde arttığı görülmeden Kapı 1 başlamaz); K24: Kadir Anthropic panelinden aylık harcama sınırını koymuş olur ve sayaç oynayıştan hemen önce okunup yazılır. Ayrıca: ertelenen ön inceleme turları, yeni arayüzle bir kez (O12); **tam paket ve bütün dal incelemesi** | - |
| **Kapı 1** | Koşul: arayüzün Tur 1 ve Tur 2'si (on ekran, A2.1-A2.10) kabul edildi (Kadir, 13 Kasım 13:12); B0-B3 bitti; O11 kapandı. Kadir 30 dakika, bulut zinciriyle oynar | Kadir |

Kapı 1'in geçme ölçütü: dört kutunun dördü (en az iki iz, birinin peşine düşme, bir seçimin sonucunu görme, "şimdi ne olacak?") ve "devam ederdim". Ek ölçütler (`MOTOR_HAKEM` bölüm 6): sistem ve para satırları hariç turların en az %80'inde anlatım modelden, yani kaynağı `qwen` ya da `mixed_engine_model` (bugün çıkarımla %47); motor sonucu olmayan hiçbir eylem başarılı anlatılmamış; sessiz ret sıfır; tur süresi ölçütü Kadir'in oynadığı kipte, yani bulut zinciriyle ölçülür ve yerel model için ayrı kısa bir ölçüm yapılır (K15; tasarım belgesi "yerel modelde" diyor, yerel ortanca bugün 12,0 sn). Hüküm Kadir'indir; rakam hükmün yerini tutmaz.

Kabul edilen bedel (Kadir, K2): başarı ölçüsünün sınanması on ekranın bitmesine kadar ertelenir. Karşılığı: Tur 1'in sonundaki oynayışta dört kutunun durumu not edilir.

Kapı 1 geçilmezse (`KESME_SONRASI` bölüm 1 kural 3 ve 10.2): Aşama 1 başlamaz. Yalnız çekirdek onarılır; çekirdek artık arayüzü de kapsar. Kapı 1 tekrarlanır. İki denemede tutmazsa yön yeniden konuşulur. 13 Kasım oynayışının birinci deneme sayılıp sayılmadığı belgelerde açık değil (karar K13).

Kapı 1'den sonrası (yalnız başlık): Aşama 1; Kapı 2; Aşama 2; Aşama 3 (uzaktan erişim; kodda ortak harcama tavanının yeniden eklenmesi ve onun içinde oyuncu başına sınır, K24; kayıt ayrımı); Kapı 3; Faz 4; Faz 5; Faz 6. Bu sürümde eklenen: Kapı 1'den sonra arayüzün Tur 3 ve Tur 4'ü, B4 kalemleri ve Hat C (bölüm 4b) aynı iki hat kuralıyla yürür; sıraları Kapı 1'in notlarından çıkar.

**Harcama kuralı (K24; Kadir, 13 Kasım 2026).** Kodda bugün tutar sınırı yok: aylık dolar sınırı 3 Kasım'da kaldırıldı, `HaikuSpend` yalnız sayıyor. (a) Kadir Anthropic panelinden aylık harcama sınırı koyar; bu kod işi değildir. (b) Kodda ortak tavan ve oyuncu başına sınır Aşama 3'te yapılır; ikisi de para yüzeyidir (kırmızı test, bağımsız inceleme, en güçlü model). (c) Kapı 1'den ve her arayüz turu oynayışından önce ve sonra sayaç okunur ve fark ledger'a yazılır. Sayaç Python'la okunur; uygulamanın içindeki PowerShell eski bir kopyayı gösterir (bölüm 10, O11 notu).

Sürekli kurallar: Kadir oynarken koda ve sunucuya dokunulmaz. Her kapıdan sonra yolculuk tablosu güncellenir ve en çok beş satırlık özet yazılır. Push, merge ve yayın her seferinde Kadir'in taze onayıyla.

---

## 7. Tavan denetimi

Kapı 1'den önceki kalemler:

| Hat | Kalemler | Sayı |
|---|---|---|
| Arayüz ekranı | Tur 1: A2.1-A2.5; Tur 2: A2.6-A2.10 | **10** (Kadir'in K2 kararı; iki tur, her biri 5, aralarında Kadir'in kabulü: tavan her turda tutuyor). Ayrıca ekran olmayan iki iş: A0, A1 |
| Motor kalemi | B0, BA, B1a, B1b, BS, B3a, B2, B3b, B3c | **9** (tavanı 4 aşıyor). İnceleme kapısı olarak **13**: B2 beş alt kalemdir (B2.0-B2.4) ve her biri ayrı inceleme ister. K25'ten sonra **11** kalem ve **15** kapı: B1c ve B3d eklendi (aşağıda) |

Neden 9: `MOTOR_HAKEM` kendi beş dilimini sayıyor (Dilim 0, Dilim 1, 2a, 2b, 2c). Ücret ve han hataları aynı hatta ayrı kalemler (2 tane). İlk turun ekranları iki yeni motor kalemi istiyor: BA ve BS. Tasarımın "Dilim 0b"si (çıkışta etiketleme) B2'nin ilk alt kalemi B2.0 olduğu için sayıyı artırmaz. İnceleme "9 kalem gerçekte 12 inceleme kapısıdır" demişti; B2.0 eklenince 13 oldu. B2.4 koşulludur: yapılmazsa 12.

Öneri (karar K1), ikisinden biri:
1. **İki aşama, arada kabul.** Aşama M-a (5 parça): B0, BA, B1a, BS, B3a; sonra motor ara kapısı. Aşama M-b (4 parça): B1b, B2, B3b, B3c; sonra Kapı 1. Tavan "iki kabul arası en çok beş" diye okunur (ekranlarda da böyle uygulanıyor). Bedeli: `MOTOR_HAKEM`'deki sıra değişir, 2a Dilim 1'in önüne geçer; nedeni savaş ekranının ret nedenlerini beklemesi.
2. **Erteleme.** Adaylar ve bedelleri: BS'nin "Yaklaş / Uzaklaş" parçası (savaş ekranı o düğmeler olmadan teslim edilir); B1b (çaresi var: hanın adını yazmak; ama `KESME_SONRASI` 10.3b bunu Kapı 1 koşulu sayıyor); B3c (Kapı 1'in "bağsız anlatım sıfır" ölçütü riske girer). Üçü ertelense bile sayı 6-7 kalır; tavan yine aşılır.

**Karar (K1; Kadir, 13 Kasım 2026): birinci seçenek.** İki aşama, arada kabul: B0, BA, B1a, BS, B3a; motor ara kapısı; B1b, B2, B3b, B3c; Kapı 1. K25 ile M-a'ya B1c, M-b'ye B3d eklendi (aşağıda).

**Codex adayları ve tavan (üçüncü sürüm; bu paragraf önerinin kaydıdır, karar hemen altında).** Bugün M-a beş parça (B0 bitti; BA, B1a, BS, B3a sırada), M-b dört parça. Kapı 1'den önceye önerdiğim Codex bulguları (bölüm 4, "Codex denetiminden Kapı 1 öncesine adaylar"): KRİT-01, KRİT-03, YÜK-04'ün üç dalı, YÜK-12 ve YÜK-16. Yerleştirme önerim parça sayısını 5 ve 5'te tutar: KRİT-01 M-b'nin beşinci parçası olur (B3d); KRİT-03 ve YÜK-04'ün üç dalı B1a'nın alt kalemleri olur (B1a.2, B1a.3); YÜK-12 B3c'ye bir kırmızı test olur; YÜK-16 A2.10'a girer. **Ama dürüst sayımla tavan zorlanır:** B1a M'den L'ye büyür ve para ya da kayıt incelemesi isteyen kapı sayısı 13'ten 16'ya çıkar; alt kalemler ayrı parça sayılırsa M-a yedi olur. Bu yüzden karar bende değil: K25. YÜK-11 ve YÜK-13 Kapı 1'den önce istenirse M-b altı parça olur.

**Karar (K25; Kadir, 13 Kasım 2026, gece):** YÜK-04'ün üç dalı B1a'ya paketlenir; KRİT-03 ayrı parça olur (B1c); **tavan yalnız bu aşama (M-a) için 6'dır.** Sayım:

| Aşama | Parçalar | Sayı | Tavan |
|---|---|---|---|
| M-a | B0 (bitti), BA, B1a (YÜK-04'ün üç dalıyla), B1c, BS, B3a | 6 | 6 (yalnız bu aşama; K25) |
| M-b | B1b, B2, B3b, B3c (YÜK-12 testiyle), B3d | 5 | 5 |

Kapı 1'den önceki motor kalemi 9'dan 11'e çıkar. Para ya da kayıt incelemesi isteyen kapı sayısı 13'ten 15'e çıkar (B1c ve B3d birer kapı; YÜK-04 dalları B1a'nın kapısının içinde, YÜK-12 B3c'nin kapısının içinde). Tavanın 6 olması başka aşamaya, arayüz turlarına ya da sonraki dilimlere taşınmaz.

---

## 8. İzlenebilirlik tabloları

Her satırın tek karşılığı var. Sınıflar: **kalem** (bu planın Kapı 1 öncesi ya da tur içi kalemi), **K1 sonrası** (Kapı 1'den sonraki kalem ya da aşama), **havuz**, **donuk** (Kadir dondurdu), **bitti** (kanıtıyla), **yapılmayacak** (nedeniyle).

### T1. `ANA_ENVANTER_20261113.md` (bölüm 0-11)

| Kaynak | Ne | Sınıf | Karşılık |
|---|---|---|---|
| 0.1 | Motor hakem, model yazar ilkesi | kalem | B2 |
| 0.2 | Ana fikir bütün arayüze uygulanır | kalem | A1 |
| 0.3 | Hız kuralları askıda, kalite önde | kalem | §6 |
| 0.4 | Çizgi altı işler donuk | donuk | Kadir, notlar G-12 |
| 0.5 | PR #34 CI yeşil olunca birleşir; ui-a ve portre sonra | bitti | 10ffd8cb, CI yeşil; ui-a için K3 |
| 0.6 | Üç iş aynı anda yürümez | yapılmayacak | 10.3b ile değişti (Çelişki 1) |
| 0.7 | Tema seti tek galeride; onaysız ekrana geçilmez | kalem | A1 |
| 0.8 | Her ekran bitti tanımına göre biter | kalem | A2 (ortak kanıt tablosu) |
| 1.1 | Tek tema kontrol seti | kalem | A1 |
| 1.2 | Karakter yaratma SS1-SS12 baştan | kalem | A2.2-A2.4, A2.12-A2.17 |
| 1.3 | Karakter, Dünya, Görünüm pencereleri | kalem | A2.10, A2.11, A2.8 |
| 1.4 | Kayıt bildirimi küçük, sağ üst, solan | kalem | A2.6 |
| 1.5 | Dinlenme düğmeleri tek yerde | kalem | A2.10 (K26; K7'nin yerine) |
| 1.6 | Faz 0 bu hâliyle no-go | kalem | §6 (Kapı 1) |
| 2.1 | Kapak girişi müziği başlatır | kalem | A2.9 |
| 2.2 | Logo yavaş sürekli döngü | kalem | A2.9 |
| 2.3 | "Unwritten"; şeritler kalkar; yer adı büyür | kalem | A2.6, A2.9 |
| 2.4 | Eski `GateSoundControl` kalkar | kalem | A2.8 |
| 2.5 | Ayar dişlisi üç yerde | kalem | A2.8 |
| 2.6 | Dişlinin içeriği | kalem | A2.8 |
| 2.7 | Ana ekran hep koyu açılıyor; tema seçimi | kalem | A2.8 |
| 2.8 | Ana ekran durumları (yok, tek, çok) | kalem | A2.9 |
| 2.9 | Macerayı sil: temalı onay | kalem | A2.9 |
| 2.10 | Müzik menüden ve yaratımdan çıkınca kapanır | kalem | A2.9 |
| 2.11 | Müzik dosyası, sıkıştırma, kaynak notu | kalem | A2.9 |
| 2.12 | Yeni macera basınca müzik kesiliyor | kalem | A2.9 |
| 2.13 | Logo döngü dikişi, Safari yolu | kalem | A2.9 |
| 3.1 | Adım sırası Tür, Sınıf, Geçmiş | kalem | A2.12 (davranış ui-a'da var) |
| 3.2 | Adım zarları | kalem | A2.12 (davranış ui-a'da var) |
| 3.3 | Seviye seçici sade; bilgi tıklayınca | kalem | A2.13 |
| 3.4 | Cinsiyet | donuk | F |
| 3.5 | Portre seti G1, G2 | donuk | G1, G2 |
| 3.6 | Yapışkan alt çubuk kalkar | kalem | A2.2 |
| 3.7 | Adım 7 sekmeleri; boş alan metni; özet envanteri | kalem | A2.3, A2.4 |
| 3.8 | Puan satın alma düğmeleri 44 piksel | kalem | A2.15 |
| 3.9 | Köken önerisi: temizlik ve panel | kalem | A2.3 (temizlik main'de: bfeb0fdd) |
| 3.10 | Beyaz kaydırma çubuğu | kalem | A1 |
| 3.11 | Metin en az 12 piksel, kontrast, noktalı İ | kalem | A1 |
| 3.12 | Mobil yaratım | kalem | A2.2-A2.4, A2.12-A2.16 (390 kanıtı) |
| 4.1 | Seviye atlama kartı, XP çubuğu | kalem | A2.7, A2.10 |
| 4.2 | Ölüm kurtarma sayacı, ölüm ekranı | kalem | A2.18 |
| 4.3 | Savaş ekranı baştan | kalem | A2.1 |
| 4.4 | Magic Missile hedef reddi | bitti | fa522fbd, 87ad0c6d, dd398b16 (PR #34) |
| 4.5 | Türkçe adlar; özellik ve alt sınıf yok | kalem | BA |
| 4.6 | "Söyle" kipi konuşma açılmadan çalışmıyor | K1 sonrası | B4.11 |
| 4.7 | Metinle satın alma döngüsü | K1 sonrası | B4.11 |
| 4.8 | Sağ panel ve üst çubuk | kalem | A2.6 |
| 4.9 | Çanta, Büyü hazırlama, Defter, Harita, Kaydet/Yükle | donuk | L'nin beş paneli (K19) |
| 4.10 | Pazar ekranı | donuk | J |
| 4.11 | Mikrofonla yazma | kalem | A2.5 |
| 5.1 | İş ücreti hatası | kalem | B1a |
| 5.2 | "Hana gir" girmiyor | kalem | B1b |
| 5.3 | Gemma düz cümle; bulutla deneme | K1 sonrası | B4.3 (K11) |
| 5.4 | İşler hazır şablondan | K1 sonrası | B4.2 |
| 5.5 | "Nemli paketler" | K1 sonrası | B4.6 |
| 5.6 | Hamle kaynağı sayımı; `narration_source` | kalem | B0 |
| 5.7 | Katip adı değişmez | yapılmayacak | Kadir kararı; iş yok |
| 5.8 | Keluvarel "Drago" notu | kalem | B2 |
| 5.9 | Açılışta ham köken metni | K1 sonrası | B4.7 |
| 5.10 | İlahi darbe: motor sonucu yok | kalem | B3b |
| 5.11 | İtme üç yolla çözülüyor | kalem | B3c |
| 5.12 | "Büyüyle keseyi alıyorum" sessiz ret | kalem | B3a (K9) |
| 5.13 | Cinayet XP kararı | K1 sonrası | B4.5 |
| 5.14 | Şifa Eli miktarı | K1 sonrası | B4.10 (K10) |
| 5.15 | Model muhafıza uydurma geçmiş yazıyor | K1 sonrası | B4.4 |
| 5.16-M1 | XP kuralı | K1 sonrası | B4.5 |
| 5.16-M2 | "Bonus eylem: uygun yetenek yok" | kalem | BS |
| 5.16-M3 | İç hata kodları | kalem | B3a |
| 5.16-M4 | İlahi Darbe yazıyla çözülmüyor | kalem | B3b |
| 5.17 | Kaynak bildirmeyen çıkışlara kaynak verilmesi (43 dönüş ve 4 dış çıkış) | kalem | B2.0 |
| 5.18 | Beşinci kaynak değeri; etiket turun bittiği tek noktada | kalem | B2.0 |
| 5.19 | Küme testi: kayıttaki liste ile motorun değerleri aynı | kalem | B0 (dalda yazıldı: 256109d7) |
| 6-sıra1 | Göstergeler ve zar tema setine | kalem | A1 |
| 6-sıra2 | Hikâye içi öğeler | K1 sonrası | C1 |
| 6-sıra3 | Efektler ve motor alanları | K1 sonrası | C2 |
| 6-sıra4 | Atmosfer doğrulaması | K1 sonrası | C3 |
| 6-ek | Mürekkep şişesi ayarda seçilebilir | kalem | A1 |
| 6-eksik | Kâğıt dokusu, ışık havuzu, sayfa çevirme, düğme hissi | kalem | A0 (soru 10) |
| 6-karar | 3B zar her atışta | kalem | A1 (K20) |
| 7-E | Mekân ve sahne verisi | donuk | E |
| 7-F | Cinsiyet | donuk | F |
| 7-G | Portre G1, G2 | donuk | G1, G2 |
| 7-H | Durum ve ayrıntı verisi | donuk | H |
| 7-I | Görünüm kaydı | donuk | I |
| 7-J | Pazar | donuk | J |
| 7-M | Dış varlıklar | donuk | M |
| 7-L | L'nin beş paneli | donuk | L (K19) |
| 7-lisans | Lisans doğrulamaları | donuk | M ile birlikte |
| 8-Faz0 | Faz 0 kapısı açık | kalem | §6 (Kapı 1) |
| 8-Faz1 | Bekleyen kararlar | kalem | §12 |
| 8-Faz2 | Oynayışın kırıkları | K1 sonrası | B4.11 |
| 8-Faz3 | Üç oturum | K1 sonrası | §6 (Kapı 2, Kapı 3) |
| 8-Faz4 | Kendi dünya, lisans | K1 sonrası | §6 (Faz 4) |
| 8-Faz5 | Kapalı test | K1 sonrası | §6 (Faz 5) |
| 8-Faz6 | Satış | K1 sonrası | §6 (Faz 6) |
| 8-4D | Han odası, nesne durumu, orman yolu, bayat sahne | K1 sonrası | B4.12 |
| 8-telefon | Telefon desteği; 390'da taşma | kalem | A2.9 |
| 8b-1 | Müzik kararı | kalem | A2.9 |
| 8b-2 | 3B zar kararı | kalem | A1 |
| 8b-3 | Telefon desteği | kalem | A2 (her ekranda 390 kanıtı) |
| 8b-4 | Katip adı | yapılmayacak | Kadir kararı |
| 8b-5 | Cinayet XP'si | K1 sonrası | B4.5 |
| 8b-6 | Düşman canı durumla | kalem | BS |
| 8b-7 | "Yaklaş / Uzaklaş" | kalem | BS |
| 8b-8 | "Savaş turu" | kalem | A2.1 |
| 9-1 | Kaydet-çık-dön ve kalan denemeler | bitti | notlar W (denendi) |
| 9-2 | Faz 2 borçları (D-020, D-056, D-061, D-062 ve bekleyenler) | K1 sonrası | B4.11 |
| 9-3 | Borç defteri | kalem | O4 |
| 9-4 | Onay listesine eklenecekler | kalem | O5 |
| 9-5 | İki bayat test | bitti | bf0a91dc |
| 9-6 | Ticari kullanım dayanağı | K1 sonrası | §6 (Faz 6) |
| 9-7 | İçerik sınırları belgesi | K1 sonrası | §6 (Faz 5) |
| 10-1 | PR #34 | bitti | O1 |
| 10-2 | İnceleme sunucuları kapatılır | kalem | O8 |
| 10-3 | Oynarken koda dokunulmaz | kalem | §6 |
| 10-4 | Yeni oturumun ilk mesajı | yapılmayacak | bu istem yerine geçti (Çelişki 2) |
| 11-1 | Yıldızsız satırlar koddan teyit edilmeli | kalem | §11 (kalanlar "Doğrulanmayanlar"da) |
| 11-2 | 12 Kasım ince bulguları tek tek sayılmadı | bitti | bu plan, tablo T4 |
| 11-3 | Nemotron kaydı yok | yapılmayacak | `MOTOR_HAKEM` bölüm 9 |

Sayım T1: 119 satır. kalem 71, K1 sonrası 23, havuz 0, donuk 14, bitti 6, yapılmayacak 5. Karşılıksız: 0.

### T2. `PROTOTIP_ENVANTERI_20261113.md` (33 madde)

| Kaynak | Ne | Sınıf | Karşılık |
|---|---|---|---|
| P1 | Mürekkep gibi beliren hikâye | bitti | `ink-text.tsx` (main'de) |
| P2 | Okuma teması gece, gündüz, sistem | bitti | main'de çalışıyor |
| P3 | Efekt seviyesi, hareketi azalt | bitti | main'de çalışıyor |
| P4 | Kâğıt dokusu, cilt oluğu | kalem | A0 (soru 10) |
| P5 | Mum ışığı havuzu | K1 sonrası | C4 |
| P6 | Sayfa çevirme | K1 sonrası | C4 |
| P7 | Düğme basılınca iner | kalem | A1 |
| P8 | Can: balmumu mühür | kalem | A1 |
| P9 | Can: mürekkep şişesi | kalem | A1 |
| P10 | Büyü yuvası: mum | kalem | A1 |
| P11 | El yazısı yetenek sayıları | kalem | A1 |
| P12 | Mühür onarımı (kintsugi) | K1 sonrası | C4 |
| P13 | Can sayısı sayarak değişir | kalem | A1 |
| P14 | Ayarda gösterge, yuva, zar seti seçimi | kalem | A2.8 |
| P15 | 3B d20 | kalem | A1 (K20) |
| P16 | Zarın sayısı yalnız motor sonucundan | kalem | A1 |
| P17 | Zar: GPU bütçesi, SVG yedek | kalem | A1 |
| P18 | Zar süresi efekt seviyesine göre | kalem | A1 |
| P19 | Ateş efekti | K1 sonrası | C2 |
| P20 | Soğuk efekti | K1 sonrası | C2 |
| P21 | Yıldırım efekti | K1 sonrası | C2 |
| P22 | Nekrotik efekti | K1 sonrası | C2 |
| P23 | Işınsal efekti | K1 sonrası | C2 |
| P24 | Vuruş efekti | K1 sonrası | C2 |
| P25 | Şifa efektleri | K1 sonrası | C2 |
| P26 | Efekt kaydı altyapısı | K1 sonrası | C2 |
| P27 | Vakit ve mekân tablosu | K1 sonrası | C3 |
| P28 | Kalabalık, ateş, pencere | K1 sonrası | C3 |
| P29 | Hava | K1 sonrası | C3 |
| P30 | Mekâna göre örnek satırlar | K1 sonrası | C3 |
| P31 | En çok 14 hareketli öğe kuralı | K1 sonrası | C3 |
| P32 | Bilgi kutuları | K1 sonrası | C1 |
| P33 | Notlar paneli | K1 sonrası | C1 |

Sayım T2: 33 satır. kalem 12, K1 sonrası 18, havuz 0, donuk 0, bitti 3, yapılmayacak 0. Karşılıksız: 0.

### T3. `OYNAYIS_NOTLARI_20261113.md` (A-V, L-sonuç, W, X, L-sonuç TEKRAR, X-ek)

| Kaynak | Ne | Sınıf | Karşılık |
|---|---|---|---|
| A-1 | Logo sürekli dönmüyor | kalem | A2.9 |
| A-2 | Logo yalnız koyu temada düzgün | kalem | A2.9 |
| A-3 | Müzik kendiliğinden başlamıyor | kalem | A2.9 |
| A-4 | Ses düzeyi ayarı yok | kalem | A2.8 |
| A-5 | "Unwritten gerçek oyun" yazısı | kalem | A2.9 |
| A-6 | Müzik kurulum boyunca sürsün | kalem | A2.9 |
| A-7 | Ana menü kitap temasına benzemiyor | kalem | A2.9 |
| B-8 | Ayar çarkı ve içeriği | kalem | A2.8 |
| B-9 | Çark kurulum sayfasında | kalem | A2.8 |
| B-10 | Çark oyun içinde | kalem | A2.8 |
| B-11 | Çark temaya uygun | kalem | A1 |
| C-12 | Tür özellik kutuları görünmüyor (SS1) | kalem | A2.12 |
| C-13 | Başlangıç seviyesi seçici (SS2) | kalem | A2.13 |
| C-14 | Geçmiş nitelik artışı (SS3) | kalem | A2.14 |
| C-15 | Beceriler tikli seçim (SS4) | kalem | A2.2 |
| C-16 | Büyü seçimi düz yazı; engelin nedeni yok (SS5, SS6) | kalem | A2.2 |
| C-17 | Ekipman (SS7) | kalem | A2.16 |
| C-18 | Kimlik: diller, yönelim, öneri penceresi, zar (SS8) | kalem | A2.3 |
| C-19 | Son adım okunmuyor (SS9-SS12) | kalem | A2.4, A2.17 |
| C-20 | "Sorun yok dersen bu işi yapamıyorsun" | kalem | A2 (ayrı göz ve Kadir kabulü) |
| D-21 | Oyun açıldı (not; istek ya da hata yok) | yapılmayacak | istek içermiyor |
| E-1 | Kurulum panelleri öne çekilsin mi | bitti | notlar G-14 ile kapandı |
| E-2 | Müziğin kendiliğinden açılması için seçenek | kalem | A2.9 |
| E-3 | Müzik kurulum ekranında duruyor | kalem | A2.9 |
| E-4 | Ses düzeyi ve tuş sesi ayarı yok | kalem | A2.8 |
| F-SS1 | Kart yüksekliği, "30" rozeti, gereksiz satırlar | kalem | A2.12 |
| F-SS2 | Kutu içinde kutu, çıplak seçici, teknik dil | kalem | A2.13 |
| F-SS3 | Çıplak radyo, binen liste, özet taşması | kalem | A2.14 |
| F-SS4 | Çıplak onay kutuları, tekrar eden cümle, çift dilli ad | kalem | A2.2 |
| F-SS5/6 | Stilsiz bölüm, İngilizce, bozuk cümle, sessiz çakışma | kalem | A2.2 |
| F-SS7 | Bozuk paket listesi, düz kartlar, karışık adlar | kalem | A2.16 |
| F-SS8 | Çıplak seçici, kafa karıştıran öneri denetimleri | kalem | A2.3 |
| F-SS9 | Can ve inisiyatif rakamı yok; okunmayan blok | kalem | A2.4 (K17) |
| F-SS10 | İngilizce satırlar, boş yarı | kalem | A2.4 |
| F-SS11/12 | Boş rozet, iki ayrı ad, düşük kontrast | kalem | A2.17 |
| F-ortak-1 | Çıplak tarayıcı kontrolleri | kalem | A1 |
| F-ortak-2 | İngilizce sızıntı | kalem | BA |
| F-ortak-3 | "Sunucu" dili oyuncuya sızıyor | kalem | A2.2-A2.4, A2.12-A2.17 |
| F-ortak-4 | Özet sütunu taşması | kalem | A2.2 |
| F-ortak-5 | Turuncu zeminde turuncu yazı | kalem | A1 |
| F-ortak-6 | Hata uyarısı alanın yanında değil | kalem | A1 |
| G-SS13 | Ana ekranda iki ayrı ses kontrolü, boş alt yarı | kalem | A2.9 |
| G-1 | Motor dalı PR; ui-a ve portre sonra | bitti | PR #34; ui-a için K3 |
| G-2 | Logo yavaş sürekli döngü | kalem | A2.9 |
| G-3 | Kapak girişi; müzik orada başlar | kalem | A2.9 |
| G-4 | Ana ekran hep koyu; seçim çarkta | kalem | A2.8 |
| G-5 | Ayar çarkı sağ altta, üç yerde | kalem | A2.8 |
| G-6 | Yalnız "Unwritten"; altbaşlık tek metin | kalem | A2.9 |
| G-7 | Eski ses kontrolü kalkar | kalem | A2.8 |
| G-8 | XP eşikleri ayna tablo kalır | bitti | onay listesi 5; ui-a `xp-progress.ts` |
| G-9a | Muharebe siperi çizgi altında | donuk | Kadir, G-9 |
| G-9b | Mobil boş şerit yeniden tasarımda | kalem | A2.6 |
| G-10 | Onay listesine üç madde | kalem | O5 |
| G-11 | Borç defteri ayrı dalda | kalem | O4 |
| G-12 | Çizgi altı donuk | donuk | Kadir |
| G-13 | A5 ve A8 testleri onaylandı | bitti | onay listesi 1, 2 |
| G-14 | Önce tasarım konuşması, sonra adımlar | kalem | A0 |
| H-1 | Ücret cümlesi bahşiş teklifi açmasın | kalem | B1a |
| H-2 | Reddin gerçek nedeni gösterilsin | kalem | B1a |
| H-3 | Anlatım ile ödeme aynı adımda | kalem | B1a |
| I-1 | Bulunan hana aynı kuralla girilsin | kalem | B1b |
| I-2 | Bul ve gir kuralı tek yerde | kalem | B1b |
| I-3 | Liman ve han gerçek yolculuk senaryosu | kalem | B1b |
| J-1 | Barmen cevabı kendi içinde çelişiyor | K1 sonrası | B4.3 |
| J-2 | Ad ile cümle arasında ayırıcı yok | kalem | B2 |
| J-3 | Aynı sahne bulut zinciriyle | kalem | §6 (Kapı 1 bulut zinciriyle; K11) |
| J-ek | Adla giriş çalışıyor, "han" sözcüğüyle çalışmıyor | kalem | B1b |
| K-1 | Daha zengin örnek ve üslup yönergesi | K1 sonrası | B4.3 |
| K-2 | Sıcaklık ve üst sınır | K1 sonrası | B4.3 |
| K-3 | Uydurmayı denetimle engelle | kalem | B2 |
| K-4 | Hazır satırları anlatıcıya yazdır | kalem | B2 |
| K-5 | Karşılaştırma; Kadir puanlar | K1 sonrası | B4.3 |
| K-6 | Nemotron denemesi | yapılmayacak | `MOTOR_HAKEM` bölüm 9 |
| L-1 | Hamle kaynağı sayımı | bitti | notlar L-sonuç TEKRAR; bu plan §2 (c) |
| L-2 | Barmen iş sorusuna cevap vermedi | K1 sonrası | B4.1 |
| M-1 | "Sahnenin sözü burada yankılanır" | kalem | A2.6 |
| M-2 | Tur sayısı ve "Aa" kalsın | kalem | A2.6 |
| M-3 | "Para ver ya da teklif hazırla" ham ok | kalem | A2.19 |
| M-4 | "Tezgâhtan satın al" kutu içinde | kalem | A2.19 |
| M-5 | "Konuşuyorsun" satırı çok küçük | kalem | A2.6 |
| M-6 | Konuşmayı bitir ve dinlenme düğmeleri biçimsiz | kalem | A2.6 |
| M-7 | "Gerçek kampanya" ve altyazı | kalem | A2.6 |
| M-8 | "Defter numarası" şeridi | kalem | A2.6 |
| M-9 | Yer adı daha büyük | kalem | A2.6 |
| M-not | Oyun içi çark; dinlenme düğmelerinin yeri | kalem | A2.8 |
| N | Anlaşılmaz şablon satırları | K1 sonrası | B4.6 |
| O | İş çeşitliliği | K1 sonrası | B4.2 |
| P | Hangi cümle motordan, hangisi modelden | kalem | B2 |
| Q-1 | Model iş verebilmeli | K1 sonrası | B4.2 |
| Q-2 | "Model varlık yaratamaz" kuralı değişir | K1 sonrası | B4.2 |
| R | Motorun yazmaması gerekenler | kalem | B2 |
| S | "Motor hakem, model yazar" onayı | kalem | B2 |
| T-SS16 | Karakter penceresi: başlık, kayan çubuk, İngilizce | kalem | A2.10 |
| T-SS17 | Dünya penceresi kusurları | kalem | A2.11 |
| T-SS18a | Kayıt bildirimi kalıcı duruyor | kalem | A2.6 |
| T-SS18b | Peynir evi sokak pazarı gibi; "Zaten içindesin" | K1 sonrası | B4.8 |
| T-SS19 | Görünüm sayfası | kalem | A2.8 |
| T-video | Sol menü: küçük yazı, boş Kişiler | kalem | A2.6 |
| T-dinlen | Çatışma altındaki dinlenme düğmeleri güzel | kalem | A2.10 (K26: yeri Karakter sayfası, mumların altı; görünüşü korunur) |
| T-tür | Tür yetenekleri alanı geliştirilebilir | kalem | A2.11 |
| T-Faz0 | Faz 0 no-go | kalem | §6 (Kapı 1) |
| T-düzeltme | Hangi düğmelerin kastedildiği belirsiz | kalem | §12 (K7) |
| U-neden | Prototip öğeleri havuzda kalmış | kalem | A1 |
| U-sıra | Önce çark, müzik, logo | kalem | A1 (Çelişki 3) |
| U-kural | Sayı yazılı kalır; zar motor sonucunu gösterir | kalem | A1 |
| U-1 | Çakışan büyü soluk ve nedeni yanında | kalem | A2.2 |
| U-2 | Yönelim 3x3 ızgara | kalem | A2.3 |
| U-3 | Seçili karta balmumu damga | kalem | A1 |
| U-4 | Kurulum sayfa çevirme düzeni | kalem | A0 (soru 17) |
| U-5 | Kayıt bildirimi mühür gibi | kalem | A2.6 |
| U-6 | Mekâna girişte başlık | kalem | A2.7 |
| U-7 | İlan kâğıt kartı, görev sayfası, damga | havuz | ekranlar |
| U-8 | NPC adı konuşmada büyük | kalem | A2.6 |
| U-9 | Ortam sesi | donuk | M3 |
| U-10 | Sol menü rozetleri, boş satır | kalem | A2.6 |
| U-elenen | Cam kart, neon, portreyi yıpratma | yapılmayacak | kontrolde elendi |
| V-SS20 | "Divine Sense" İngilizce | kalem | BA |
| V-iki yer | Aynı dinlenme düğmeleri iki yerde | kalem | A2.10 (K26) |
| V-prototip | Prototip öğeleri listelensin | bitti | `PROTOTIP_ENVANTERI_20261113.md` |
| V-şişe | Mürekkep şişesi ayardan seçilebilir | kalem | A1 |
| Ls-1 | Gezinme, arama, ücret, tanışma motor cümlesi | kalem | B2 |
| Ls-2 | Tanışma kalıbı ikinci soruyu yuttu | K1 sonrası | B4.1 |
| Ls-3 | "Kısa dinleniyorum" çalışmadı | kalem | B3c |
| Ls-4 | Tur 11 ücret hatası motor tarafında | kalem | B1a |
| Ls-5 | Tur 17 "hana giriyorum" reddi | kalem | B1b |
| Ls-6 | Kaynak alanı eksik | kalem | B0 |
| W-A3 | Muhafıza uydurma geçmiş | K1 sonrası | B4.4 |
| W-C4 | Büyüyle kese: sessiz ret | kalem | B3a |
| W-D021 | İtme üç yolla çözülüyor | kalem | B3c |
| W-savaş | Sıra ve düşman canı metinde yok | kalem | A2.1 |
| W-darbe | İlahi darbe yalnız model | kalem | B3b |
| W-şifa | Şifa Eli miktarı sorulmuyor | K1 sonrası | B4.10 |
| W-geri al | Geri Al çalıştı | bitti | notlar W, tur 37 |
| W-1 | Açılışta ham köken metni | K1 sonrası | B4.7 |
| W-2 | Cinayet ödüllendiriliyor | K1 sonrası | B4.5 |
| W-3 | Muhafız ölünce yasa tepkisi görünmüyor | K1 sonrası | B4.13 |
| W-4 | Muhafız konuşmaları uzun ve dolgu | K1 sonrası | B4.3 |
| W-5 | Yazım hatası karşılanmadı | kalem | B3c |
| W-6 | Aynı cevap iki kez | kalem | B3a |
| X-1 | Dar sütun, iç içe kaydırma | kalem | A2.1 |
| X-2 | Ham İngilizce, noktalı İ | kalem | BA |
| X-3 | Ham hata anahtarı | kalem | B3a |
| X-4 | Bozuk düzen | kalem | A2.1 |
| X-5 | Ham tarayıcı bileşenleri | kalem | A2.1 |
| X-6 | 11 piksel büyük harf duvarı | kalem | A2.1 |
| X-7 | Düşman ve sıra küçük düz metin | kalem | A2.1 |
| X-8 | Hedef seçimi ilişkisiz; "Kapat" | kalem | A2.1 |
| X-9 | Yinelenen bilgi | kalem | A2.1 |
| X-10 | Eski şerit hâlâ var | kalem | A2.6 |
| X-11 | Zar yok | kalem | A1 |
| X-12 | "Geri alınamaz" uyarısı küçük | kalem | A2.1 |
| X-hedef | Kadir'in savaş ekranı hedefi | kalem | A2.1 |
| LsT-1 | Gezinme, savaş, yağma motor cümlesi | kalem | B2 |
| LsT-2 | Savaşta model yalnız İlahi Darbe'yi yazdı | kalem | B3b |
| LsT-3 | Tur 23: iş sorusu cevapsız | K1 sonrası | B4.1 |
| LsT-4 | Tur 33: dinlenme çalışmadı | kalem | B3c |
| LsT-5 | Tur 55-56: aynı şablon, sonuç yok | kalem | B3a |
| LsT-6 | Kaynağı kayda yazan alan | kalem | B0 |
| Xek-K1 | Cinayet XP'si kararı | K1 sonrası | B4.5 |
| Xek-K2 | Düşman canı durumla | kalem | BS |
| Xek-K3 | "Yaklaş / Uzaklaş" | kalem | BS |
| Xek-K4 | "Savaş turu" sayacı ayrı | kalem | A2.1 |
| Xek-B1 | "Bonus eylem: uygun yetenek yok" | kalem | BS |
| Xek-B2 | Savaş durumu üç yerde | kalem | A2.1 |
| Xek-B3 | İki tur sayacı | kalem | A2.1 |
| Xek-B4 | "Şifa Eli (can)" açıklamasız kutu | kalem | A2.1 |
| Xek-B5 | "Turu bitir" kaydırmanın altında | kalem | A2.1 |
| Xek-T1 | Sıra şeridi ve eylem sayfası | kalem | A0 (soru 11) |
| Xek-T2 | Eylem hakları üç işaret | kalem | A2.1 |
| Xek-T3 | Yapılamayan soluk, yanında neden | kalem | A2.1 |
| Xek-T4 | "Turu bitir" her zaman görünür | kalem | A2.1 |
| Xek-T5 | Serbest yazma savaşta kalır | kalem | A2.5 |
| Xek-T6 | Zar anlatı sütununda | kalem | A2.7 |
| Xek-T7 | 390'da alttan açılan sayfa | kalem | A2.1 |
| Xek-M1 | XP kuralı | K1 sonrası | B4.5 |
| Xek-M2 | Bonus eylem listesi | kalem | BS |
| Xek-M3 | İç hata kodları | kalem | B3a |
| Xek-M4 | İlahi Darbe yazıyla | kalem | B3b |

Sayım T3: 178 satır. kalem 144, K1 sonrası 20, havuz 1, donuk 3, bitti 7, yapılmayacak 3. Karşılıksız: 0.

### T4. `OYNAYIS_NOTLARI_20261112.md` (bölüm 6, 7, 8)

| Kaynak | Ne | Sınıf | Karşılık |
|---|---|---|---|
| 6-ajan-1 | "Seviye 3 seçilemiyor" (yanlış bulgu) | yapılmayacak | yanlış bulgu, notta düzeltilmiş |
| 6-ajan-2 | "Söyle" kipi konuşma açılmadan çalışmıyor | K1 sonrası | B4.11 |
| 6-ajan-3 | A3 ve D-021 sonuçları | kalem | B3c |
| 6-ajan-4 | Ödül çelişkisi ("verilecek ödül yok") | K1 sonrası | B4.11 |
| 6-ajan-5 | "Söylentiler belirsiz"; Algı zarı görünmedi | K1 sonrası | B4.11 |
| 6-ajan-6 | Han ve meyhane yok | K1 sonrası | B4.12 |
| 6-ajan-7 | Metinle satın alma döngüsü | K1 sonrası | B4.11 |
| 6-ajan-8 | Kısa dinlenmede oyuncuya "tür" dili | K1 sonrası | B4.11 |
| 6-ajan-9 | Okunabilirlik: kontrast, 8-10 piksel, erişilebilir ad | kalem | A1 |
| 6-ajan-10 | Taşan panel (1024 genişlikte görüldü) | yapılmayacak | ölçüm hatası; 1280'de yeniden üretilmedi |
| 6-ajan-11 | Oyuncu cümlesinin yankısı, yer dışı ortam olayı | K1 sonrası | B4.11 |
| 6-A | Onay ekranında yapışkan şerit rakamların üstünde | kalem | A2.17 |
| 6-B | İngilizce büyü adlarında noktalı İ; çift eşya adı | kalem | BA |
| 6-C | 8-10 piksel etiketler | kalem | A1 |
| 6-D | Hikâyedeki kişi gerçek kişi değil | kalem | B2 |
| 6-E | Telefon düzeni düzgün (not) | kalem | A2 (her ekranda 390 kanıtı) |
| 6-F | Çalışanlar listesi (not) | bitti | 12 Kasım notu F |
| 6-G | Pencere üst bandı boş ve yapışık | kalem | A1 |
| 6-H | Beyaz kaydırma çubuğu | kalem | A1 |
| 6-I | Aynı pencerede iki metin rengi | kalem | A2.10 |
| 6-açılış-1 | "Bir hikâyeye sessizce adım at" kalksın | bitti | ui-a 0c3a980a (onay listesi 1) |
| 6-açılış-2 | Bozuk "i" bilgi kutusu kalksın | bitti | ui-a 0c3a980a |
| 6-açılış-3 | "Hesabın ve kampanyaların" kutusu kalksın | bitti | ui-a 0c3a980a |
| 6-açılış-4 | Yükleme animasyonu (Ouroboros) | kalem | A2.9 |
| 6-ilke | Gereksiz metin, kutu, süs yok | kalem | A1 |
| 6-kural | Ana fikir her ekrana uygulanır | kalem | A1 |
| 6-J | Kurulumda gereksiz bilgi kalabalığı | kalem | A2.13 |
| 6-K | Beyaz kaydırma ve yapışık alt çubuk | kalem | A2.2 |
| 6-L | Portreler tek stil; P1 birleşimi | donuk | G1, G2 |
| 6-M | Cinsiyet seçimi | donuk | F |
| 6-N | Adım sırası | bitti | ui-a (onay listesi 6) |
| 6-O | Adım zarları | bitti | ui-a `step-dice.tsx` (onay listesi 7) |
| 6b | Harcama kaydı; Kadir'in oyunundan kayıt yok | kalem | O11 |
| 7-P | Adım 7'de 38 küçük metin | kalem | A2.3 |
| 7-Q | Adım 7 sekmeleri stilsiz | kalem | A2.3 |
| 7-R | Büyü adları İngilizce, noktalı İ | kalem | BA |
| 7-S | Boş alan metinleri tutarsız | kalem | A2.4 |
| 7-T | Özet envanteri eksik | kalem | A2.4 |
| 7-U | Açılış kartı dar sütunda | kalem | A2.17 |
| 7-V | Görünüm paneli | kalem | A2.8 |
| 7-Wa | Çanta, Hazırlık, Defter, Harita paneli yok | donuk | L (K19) |
| 7-Wb | "Dinleniyorum" çalışmadı | kalem | B3c |
| 7-X | Yükleme ve kayıt yuvası yok | donuk | L |
| 7-Y | Mobilde üst şerit büyük, 38 piksel sekmeler | kalem | A2.6 |
| 7-Z | Macerayı sil onayı; beyaz kaydırma | kalem | A2.9 |
| 7b | Yerel `confirm()` penceresi | kalem | A2.9 |
| 8-AA | Savaş panelinde küçük yazılar | kalem | A2.1 |
| 8-AB | Magic Missile hedef reddi | bitti | PR #34 |
| 8-AC | Anlatımda İngilizce eşya adı ("Dagger") | K1 sonrası | B4.9 |
| 8-AD | Ölüm kurtarma sayacı yok | kalem | A2.18 |
| 8-AE | Ölüm ekranı zayıf | kalem | A2.18 |
| 8-AF | `level_up` kullanılmıyor; XP eşiği yok | kalem | A2.7 |
| 8-AG | Dinlenme düğmesi yok | kalem | A2.10 (K26) |
| 8-AH | Geri Al onay çubuğu örnek | kalem | A2.9 |
| 8-AI | Gündüz temasında küçük metinler; yüksek kontrast farkı az | kalem | A1 |
| 8-AJ | 28 piksel düğmeler; sabit çubuk | kalem | A2.15 |
| 8-AK | Köken önerisi: giriş cümlesi, stilsiz panel | kalem | A2.3 |
| 8-AL | Mobil yaratım: iki satır şerit, binen çubuk | kalem | A2.2 |
| 8-AM | Macerayı sil (kesinleşti) | kalem | A2.9 |

Sayım T4: 59 satır. kalem 38, K1 sonrası 8, havuz 0, donuk 4, bitti 7, yapılmayacak 2. Karşılıksız: 0.

### T5. `KESME_SONRASI_TASARIM_20261112.md` yolculuk tablosu (bölüm 2 ve 10.5; 35 satır)

| Kaynak | Ne | Sınıf | Karşılık |
|---|---|---|---|
| Y1 | Açılış ekranı | kalem | A2.9 |
| Y2 | Giriş ve hesap (uzaktan) | K1 sonrası | §6 (Aşama 3) |
| Y3 | Karakter kurma | kalem | A2.2-A2.4, A2.12-A2.17 |
| Y4 | İlk sahne ve anlatım | kalem | A2.7 |
| Y5 | Biriyle konuşma (koşulu bilinmeyen bozukluk) | kalem | O12 |
| Y6 | Etrafa bakma, iz bulma | kalem | O12 |
| Y7 | Savaş | kalem | A2.1 |
| Y8 | Alışveriş: yazıyla döngü | K1 sonrası | B4.11 |
| Y9 | Çantaya bakma | kalem | A2.10 (ayrı panel donuk; K19) |
| Y10 | Büyü hazırlama | kalem | A2.20 |
| Y11 | Dinlenme | kalem | A2.11 |
| Y12 | Seviye atlama | kalem | A2.7 |
| Y13 | Ölüm | kalem | A2.18 |
| Y14 | Kaydetme ve yükleme (çok kayıt noktası) | havuz | ekranlar |
| Y15 | Geri Al | bitti | notlar W, tur 37 |
| Y16 | Ertesi gün geri dönme | K1 sonrası | §6 (Aşama 1) |
| Y17 | Yön bulma (harita yok) | havuz | ekranlar |
| Y18 | Model cevap vermezse | kalem | B2 (model hatası testi) |
| Y19 | Uzaktan bağlanma | K1 sonrası | §6 (Aşama 3) |
| Y20 | Harcama sınırı | K1 sonrası | §6 (Aşama 3) |
| Y21 | Kayıtların ayrılması | K1 sonrası | §6 (Aşama 3) |
| Y22 | Telefondan oynama | kalem | A2.6 |
| Y23 | Oyunun kullanımını öğrenme | kalem | A2.5 |
| Y24 | Zar ve kural sonucunu görme | kalem | A2.7 |
| Y25 | Macera başlangıcını seçme | kalem | O12 |
| Y26 | Görev kabul etme ve bırakma | kalem | O12 |
| Y27 | Ortam olaylarına karşılık verme | kalem | O12 |
| Y28 | Yarım kalan hamleyi sürdürme | kalem | O12 |
| Y29 | Oturumu kapatma | kalem | O12 |
| Y30 | Yapılan işin ücretini almak | kalem | B1a |
| Y31 | Anlatıcının söylediği yere girmek | kalem | B1b |
| Y32 | Sesi ve temayı ayarlamak | kalem | A2.8 |
| Y33 | Bir işin ne olduğunu anlamak | K1 sonrası | B4.6 |
| Y34 | Oyunu Türkçe okumak | kalem | BA |
| Y35 | Konuşarak hamle yazmak | kalem | A2.5 |

Sayım T5: 35 satır. kalem 25, K1 sonrası 7, havuz 2, donuk 0, bitti 1, yapılmayacak 0. Karşılıksız: 0.

### T6. `UI_KURULUM_AKISI_TASARIM_20261112.md` (parçalar A0-M ve bölüm 0 ek şartları)

| Kaynak | Ne | Sınıf | Karşılık |
|---|---|---|---|
| A0 | Eksik ekranların denetimi | bitti | 12 Kasım notları bölüm 7 ve 8 |
| D0 | Logo tasarımı | bitti | seçilen döngü `ouroboros_loop.mp4`; ui-a `ouroboros-logo.tsx` |
| D1 | Logo animasyonu ve yükleme | kalem | A2.9 |
| A | Görsel temizlik | kalem | A1 |
| L-adlar | Türkçe ad tablosu (karar 15) | kalem | BA |
| L-dinlenme | Dinlen düğmesi (karar 16) | kalem | A2.11 |
| L-seviye | Seviye atlama kartı, XP çubuğu (karar 17) | kalem | A2.7 |
| L-ölüm | Ölüm kurtarma sayacı, ölüm ekranı | kalem | A2.18 |
| L-füze | Magic Missile hedef reddi | bitti | PR #34 |
| L-köken | Köken önerisi temizliği | bitti | bfeb0fdd (panel stili A2.3) |
| L-sayfa | Karakter sayfası düzeltmeleri | kalem | A2.10 |
| L-beş panel | Çanta, Hazırlık, Defter, Harita, Yükle (karar 18) | donuk | Kadir (K19) |
| B | Adım sırası | bitti | ui-a (onay listesi 6); main'e Tur 1 PR'ıyla |
| C | Adım zarları | bitti | ui-a `step-dice.tsx`; main'e Tur 1 PR'ıyla |
| D | Logo ve müzik | kalem | A2.9 |
| E | Mekân ve sahne verileri | donuk | Kadir |
| F | Cinsiyet | donuk | Kadir |
| G1 | Portre kart seti | donuk | Kadir |
| G2 | Kişiye özel portre | donuk | Kadir |
| H | Durum ve ayrıntı verileri | donuk | Kadir |
| I | Görünüm kaydı | donuk | Kadir |
| J | Pazar ekranı | donuk | Kadir |
| M1 | Simgeler | donuk | Kadir |
| M2 | Mekân görselleri | donuk | Kadir |
| M3 | Ortam sesi | donuk | Kadir |
| M-ret | Reddedilen dış servisler | yapılmayacak | planın kendi ret listesi |
| K-ses | Ses, hesaba bağlı ayarlar | havuz | ekranlar |
| K-telefon | Oyun ekranının telefon uyumu | kalem | A2.6 |
| K-oyun içi | Söyle kipi, hayalet kişi, ödül çelişkisi | K1 sonrası | B4.11 |
| Şart-1 | fa522fbd için ters test ve bağımsız inceleme | bitti | 87ad0c6d, dd398b16 (PR #34) |
| Şart-2 | Ad tablosu tek kaynak | bitti | c8abbe1c (genişletme BA) |
| Şart-3 | Logo önce basit yolla | kalem | A2.9 |
| Şart-4 | Varlıklar sıkıştırılır, kaynak notu | kalem | A2.9 |
| Şart-5 | A5 ve A8 testleri onay listesinde | bitti | onay listesi 1, 2 |
| Şart-6 | Yerel dallar yedek için gönderilir | kalem | O2 |

Sayım T6: 35 satır. kalem 12, K1 sonrası 1, havuz 1, donuk 11, bitti 9, yapılmayacak 1. Karşılıksız: 0.

### T7. `KARAR_LISTESI_20261112.md` ve `ONAY_LISTESI_UI_20261112.md`

| Kaynak | Ne | Sınıf | Karşılık |
|---|---|---|---|
| KL-onaylı | Karar listesinin A1, B1-B6, C1-C3, C5-C7 maddeleri (Hat C kalemleri değil) | bitti | Kadir'in cevabı (liste bölüm D) |
| KL-A2 | Hangi kontrollerin değiştiği tek satırla yazılsın | kalem | O5 |
| KL-A3 | "Evet, tell me about the guard" kavga başlatıyor mu | kalem | B3c (K21) |
| KL-C4 | Para geçen büyü cümlesi büyü sayılmıyor | kalem | B3a (K9) |
| KL-D014 | İngilizce iş teklifi "?" ile bitince | K1 sonrası | §6 (Faz 6) |
| KL-D020 | Sokakta duyulan iş izi; yolculuk 41 | K1 sonrası | B4.11 |
| KL-D021 | "Muhafızı itiyorum" her zaman soru açmıyor | kalem | B3c |
| KL-D023 | Healer's Kit yok | havuz | dünya |
| KL-D034 | Katip adı | yapılmayacak | Kadir kararı, ad değişmez |
| KL-D039 | Eski Wizard kayıtlarında büyü kitabı yok | havuz | ekranlar |
| KL-D056 | İyileştirme büyüleri savaş dışında çalışmıyor | K1 sonrası | B4.11 |
| KL-D061 | Yazılamayan XP için oyuncuya tek satır | K1 sonrası | B4.11 |
| KL-D062 | Reddedilen ödül her tur yeniden deneniyor | K1 sonrası | B4.11 |
| KL-borç | Borç defteri güncellenmedi | kalem | O4 |
| OL-1 | A5 ana ekran testi | bitti | Kadir onayladı (notlar G-13) |
| OL-2 | A8 kurulum başlığı testi | bitti | Kadir onayladı (notlar G-13) |
| OL-3 | Senaryo 21: sorulmadan verilen karar | kalem | O5 |
| OL-4 | Test sahte ortamlarına eklenen satırlar | kalem | O5 |
| OL-5 | XP eşikleri ayna tablo | bitti | Kadir kararı (notlar G-8) |
| OL-6 | Adım sırası testleri | kalem | O5 |
| OL-7 | Adım zarları testleri | kalem | O5 |
| OL-8 | Logo ve müzik testleri | kalem | O5 |
| OL-9 | Ad tablosu testleri | kalem | O5 |
| OL-ek-1 | Dinlenme ifadesi düzeltmesi | kalem | O5 |
| OL-ek-2 | Ölü yazma kutusu testi | kalem | O5 |
| OL-ek-3 | Yaratım özeti testleri | kalem | O5 |

Sayım T7: 26 satır. kalem 14, K1 sonrası 5, havuz 2, donuk 0, bitti 4, yapılmayacak 1. Karşılıksız: 0.

### T8. `UI_BILINEN_KIRIKLAR_20261111.md`

| Kaynak | Ne | Sınıf | Karşılık |
|---|---|---|---|
| BK-1 | `conditional-renderers.test.mjs`: bayat beklenti | bitti | bf0a91dc (main'de) |
| BK-2 | `roadmap-r02.test.mjs`: bayat test ortamı | bitti | bf0a91dc; dosyada `combatStartInjection` var |
| BK-3 | İki dosya standart kümeye eklensin | bitti | `package.json` `test:standard` ikisini de içeriyor |

Sayım T8: 3 satır. kalem 0, K1 sonrası 0, havuz 0, donuk 0, bitti 3, yapılmayacak 0. Karşılıksız: 0.

### T9. `CODEX_DENETIM_NIHAI_RAPOR_20261113.md` (63 bulgu: 4 kritik, 23 yüksek, 29 orta, 7 düşük)

Doğrulama durumu `CODEX_NIHAI_DOGRULAMA_20261113.md` dosyasındandır: 10 bulgu bağımsız okunarak doğrulandı ("doğrulandı"), ikisi kısmen izlendi, kalanı doğrulanmadı. Hiçbiri çalıştırılarak üretilmedi. "kalem" sınıfındaki yedi satırın yeri K25 ile kesinleşti (13 Kasım 2026, gece): ikisi Kadir'in sözüyle (KRİT-03, YÜK-04), üçü Ruling ile (KRİT-01, YÜK-12, YÜK-16; bölüm 4 Sıra), ikisi zaten var olan kalemlerin içinde (ORTA-10: B2; ORTA-14: A2.4). YÜK-04 altı dalıyla tek satırdır.

| Kaynak | Ne | Sınıf | Karşılık |
|---|---|---|---|
| KRİT-01 | Ortam olayı kaydedildikten sonra Geri Al parmak izi hatası: eski dünya geri yüklenir, sonraki kayıt olayı siler, makbuz kalır. Doğrulandı | kalem | B3d (M-b'nin beşinci parçası; Ruling, bölüm 4 Sıra) |
| KRİT-02 | Eski NPC konuşmasında modelin önerdiği tutar NPC kesesinden oyuncuya ödenir. Doğrulandı | donuk | Bilinçli C5 kararı; değiştirmek Kadir'in onayını ister. Açılırsa B5.3. Not (Kadir, 14 Kasım 2026): önerilen yön, ödenecek tutarı modelin değil motorun belirlemesiydi. Kapandı: D-166 (Kadir 2026-11-15). |
| KRİT-03 | Diyalog teslimatı kartta "25 altın" der, 25 bakır öder (kent soruşturması 20). Doğrulandı. Karar K27: ödül altın, kartın söylediği ödenir | kalem | B1c (ayrı parça; K25, K27) |
| KRİT-04 | Tür yeteneğinin tur sonu hasarı ödül avı hedefini düşürürse görev ödülü (60 XP, 80 bakır, makbuz) yazılmaz (eski ORTA-23) | K1 sonrası | B5.3 |
| YÜK-01 | Model hatasından sonra eski kimlikli gecikmiş istek ile yeni gönderim iki tur oluşturabilir. Doğrulandı | K1 sonrası | B5.2 |
| YÜK-02 | Açık tur niyetinin önüne Geri Al, görev kabulü, tür yeteneği, büyü hazırlama ya da ortam olayı geçebilir | K1 sonrası | B5.2 |
| YÜK-03 | Hırsızlık kaynaktan düşmeden 5-40 bakır ya da eşya üretir. Doğrulandı | K1 sonrası | B5.3 |
| YÜK-04 | Nötr söz yanlış model etiketi alınca iş, ilişki, envanter ya da suç kaydı değişir (altı dal). Tüketim dalı doğrulandı | kalem | Kabul, tüketim, devir: B1a'ya paketlendi (K25). Tehdit, yangın, hırsızlık: B5.5 |
| YÜK-05 | Kaydedilmiş ödemenin Geri Al noktası depo hatasında kurulmayabilir; yanıt kaybında ekran geçerli hedefi siler | K1 sonrası | B5.1 |
| YÜK-06 | Tur, tür eylemi ve büyü hazırlamada işlem kimliği isteğe bağlı; kimliksiz istek iki kez işlenebilir | K1 sonrası | B5.2 |
| YÜK-07 | Bulut zinciri açıkken oyun metnine yapıştırılan yerel belirteç dış sağlayıcıya gidebilir. Doğrulandı | K1 sonrası | B5.7; Kapı 3'ten önce |
| YÜK-08 | Her turdan sonra bütün hikâye ve makbuzlar yeniden okunuyor. Gecikme ölçülmedi | K1 sonrası | B5.8; görünen yanı A2.7 |
| YÜK-09 | IRONMAN'ın son ölümü Geri Al ile geri alınabiliyor. Kısmen izlendi | K1 sonrası | B5.1 |
| YÜK-10 | Eski v5 kayıtta ölüm noktası eski karakteri v6 biçimiyle geri yükler; doğrulayıcı reddeder | K1 sonrası | B5.1 |
| YÜK-11 | "10 Dart" ve "5 Hançer" tek eşya; ilk atışta paketin tamamı gider. Kısmen izlendi | K1 sonrası | B5.6'nın ilk işi (K25'te öne alınmadı) |
| YÜK-12 | Geri alınan saldırı onayı yaşar; sonraki ilgisiz "evet" eski hedefe saldırı başlatır | kalem | B3c'ye ek kırmızı test (Ruling, bölüm 4 Sıra) |
| YÜK-13 | Atılan başlangıç kalkanının +2 Zırh Sınıfı kalır; çift el hasarıyla birlikte uygulanabilir | K1 sonrası | B5.6'nın ilk işi (K25'te öne alınmadı) |
| YÜK-14 | Kayıp Kişi görevinde tutsağı öldürmek kurtarma hedefini de tamamlar; test bunu bekliyor. Doğrulandı | K1 sonrası | B5.3 |
| YÜK-15 | Sığınaktan "Dışarı" çıkınca kayıt oyuncuyu içeride gösterir | K1 sonrası | B5.4 |
| YÜK-16 | Diyalog teklifi "günlükten kabul et" der; dinamik görev satırında kabul ve iptal düğmesi yok. Arayüz kodunda okundu | kalem | A2.10 (Tur 2, Kapı 1'den önce) ve motor cümlesi (Ruling, bölüm 4 Sıra) |
| YÜK-17 | İç mekân yangınında tahliye edilen Yolcu yüzünden tur kaydedilemez ve geri sarılır | K1 sonrası | B5.6 |
| YÜK-18 | Reddedilen saldırının önizlemesi NPC mesafesini belleğe yazar; Geri Al bayatlar | K1 sonrası | B5.1 |
| YÜK-19 | "Mass Healing Word" kısa adla eşleşip tek hedefli şifa, yuva ve eylem harcar | K1 sonrası | B5.6 |
| YÜK-20 | Üç büyünün saldırı zarı yorgunluk cezasını atlar | K1 sonrası | B5.6 |
| YÜK-21 | Kurye işi öndeyken sığınaktaki kurtarma yanlış görevin kişisine yazılır | K1 sonrası | B5.4 |
| YÜK-22 | Etkin görevde özel seyahat yolu konumu doğrudan yazar; kapalı rota aşılır, süre uygulanmaz | K1 sonrası | B5.4 |
| YÜK-23 | Zamanlanmış olayların 256 sınırını bitmiş olaylar da doldurur; yeni görev kabulü geri sarılır | K1 sonrası | B5.4 |
| ORTA-01 | Kart iptali ya da Geri Al sonrası hikâye sırası ile tur numarası ayrılır; zar kartı geçmişten düşebilir | K1 sonrası | B5.1 |
| ORTA-02 | Geri alınan saldırı savaş günlüğünde uygulanmış görünür | K1 sonrası | B5.1; görünen yanı A2.1 |
| ORTA-03 | İşlem tekrarında makbuzun bütünlük özeti karşılaştırılmıyor | K1 sonrası | B5.1 |
| ORTA-04 | Sürüm numarası 6 olan eski düzenli veritabanında göç izni kapalıyken tablo eklenebilir | K1 sonrası | B5.1 |
| ORTA-06 | Oyuncu başına maliyet ayrımı ve kota yok. Doğrulandı | K1 sonrası | Aşama 3 (K24 b) |
| ORTA-07 | Kullanımı gelmeyen cevap ya da okunamayan günlük sıfır harcama gibi görünür | K1 sonrası | B5.7; sayaç okumalarında not edilir (O11) |
| ORTA-08 | Aynı aylık Haiku dosyasına yazan iki süreç bir artışı kaybedebilir | K1 sonrası | B5.7; o zamana kadar tek sunucu süreci (O8, O11) |
| ORTA-09 | İlk sağlayıcı token sınırında durunca zincir cevabı başarılı sayar; yedek denenmez | K1 sonrası | B5.7 |
| ORTA-10 | Anlatıcının yanlış kese cümlesi geçmişe yazılabilir | kalem | B2 (para yalanını yakalayan denetime bakiye cümlesi eklenir) |
| ORTA-11 | Terk edilmiş geçici oturumlar ve başarılı yanıtlar bellekte kalır | K1 sonrası | B5.2 |
| ORTA-12 | Yarıda kalan geçici yazım sağlam kaydı bozuk gibi gösterebilir | K1 sonrası | B5.1 |
| ORTA-13 | Yolcu kaydında iki anahtar eksik gelebilir; arayüz şeması zorunlu tutar | K1 sonrası | B5.8 |
| ORTA-14 | 4. seviyede Çeviklik artışında yaratım ekranı eski Zırh Sınıfını gösterir | kalem | A2.4 (önizleme hesabı; kırmızı test) |
| ORTA-15 | Kampanya oluşturan en az 64 test modülünde tohum sabit değil | K1 sonrası | B5.9 |
| ORTA-16 | Çevrimdışı sürücüde atlanan 83 adım konsolda geçmiş sayılıyor | K1 sonrası | B5.9 |
| ORTA-17 | CI seçkisinde dört yolculuk modülü yok. Doğrulandı | K1 sonrası | B5.9 (küçük; öne alınabilir) |
| ORTA-18 | Karakter yaratımında altı seçim kutusunun ve 12 artı/eksi düğmesinin erişilebilir adı yok | K1 sonrası | A2.15 |
| ORTA-19 | Tür panelinden dinlenme ölümle biterse yanıt reddedilir; ölüm ve süre geri sarılır | K1 sonrası | B5.6 |
| ORTA-20 | Geçici oturumda vazgeçilmiş Geri Al kimliği sonradan uygulanabilir | K1 sonrası | B5.1 |
| ORTA-21 | "Etkileşime geç" tek tıkta iki tur yazar; Geri Al yalnız konuşmayı kaldırır | K1 sonrası | B5.1 |
| ORTA-22 | Kısa dinlenmede can zarı harcamanın ekranda karşılığı yok | K1 sonrası | Karakter sayfası, dinlenme düğmelerinin yanı (A2.10'un Kapı 1 sonrası eki; K26); motor yanı B5.8 |
| ORTA-24 | Yangın saati, mekân özelliği ve suç kaydı ayrışabilir | K1 sonrası | B5.6 |
| ORTA-25 | Mesafe üç yerde tutuluyor; menzil ve hareket tutarsız | K1 sonrası | B5.6; BS'nin "Yaklaş / Uzaklaş" parçası başlarken okunur |
| ORTA-26 | Yolcu'nun hızı savaş aktörüne taşınmıyor; Dodge'un etkisi uygulanmıyor | K1 sonrası | B5.6 |
| ORTA-27 | Aasimar Fighter `Light` kullanamıyor; Fırtına Devi itmesi hedefi oynatmıyor | K1 sonrası | B5.6 |
| ORTA-28 | Hedefsiz inceleme görüşülmemiş görev verenin kimliğini delile ekler; hedef ilerler | K1 sonrası | B5.4 |
| ORTA-29 | Görev API'sinden iptal kurye paketini oyuncuda bırakır | K1 sonrası | B5.3; düzelmeden günlüğe iptal düğmesi eklenmez (YÜK-16) |
| ORTA-30 | Varış kaydolurken kişisel ziyaret hedefi açık kalabilir | K1 sonrası | B5.4 |
| ORTA-31 | Şifa büyüsü günlükte "Saldırı eylemi çözüldü" görünür; kapanışta panel "Pasif" yazar | K1 sonrası | B5.8; görünen yanı A2.1 |
| ORTA-05 | Geliştirici belgesi bütün ticarette kart gerektiğini söylüyor; doğrudan katalog ticareti destekleniyor (düşük) | K1 sonrası | B5.10 |
| DÜŞ-01 | Seviye yükseltme uçlarının hata yanıtları sözleşmede yok | K1 sonrası | B5.10 |
| DÜŞ-02 | Geçici oturum durum sorgusu geçersiz kimlikte sözleşme dışı cevap döner | K1 sonrası | B5.2 |
| DÜŞ-03 | Bellek testinin son doğrulaması boş liste üzerinde; her zaman doğru | K1 sonrası | B5.9 |
| DÜŞ-04 | Kayıt README'si ve CI belgesi eski | K1 sonrası | B5.10 |
| DÜŞ-05 | Geri Al kimliğinde durum yanıtı sözleşmedeki biçimde değil | K1 sonrası | B5.2 |
| DÜŞ-06 | Blessed Warrior açıklaması yalnız Sacred Flame diyor | K1 sonrası | B5.10 |

Sayım T9: 63 satır. kalem 7, K1 sonrası 55, havuz 0, donuk 1, bitti 0, yapılmayacak 0. Karşılıksız: 0. Rapordaki borç notu (D-007: `player_stable` gerekçesi güncel değil; XP verilip verilmeyeceği ürün kararı) 63 bulgunun dışındadır; borç defterinde D-007 satırına not olarak işlenir (O4 ile aynı dal).





### Toplam

| Tablo | Satır | kalem | K1 sonrası | havuz | donuk | bitti | yapılmayacak |
|---|---|---|---|---|---|---|---|
| T1 Ana envanter | 119 | 71 | 23 | 0 | 14 | 6 | 5 |
| T2 Prototip envanteri | 33 | 12 | 18 | 0 | 0 | 3 | 0 |
| T3 13 Kasım notları | 178 | 144 | 20 | 1 | 3 | 7 | 3 |
| T4 12 Kasım notları | 59 | 38 | 8 | 0 | 4 | 7 | 2 |
| T5 Yolculuk tablosu | 35 | 25 | 7 | 2 | 0 | 1 | 0 |
| T6 Kurulum akışı parçaları | 35 | 12 | 1 | 1 | 11 | 9 | 1 |
| T7 Karar ve onay listeleri | 26 | 14 | 5 | 2 | 0 | 4 | 1 |
| T8 Bilinen kırıklar | 3 | 0 | 0 | 0 | 0 | 3 | 0 |
| T9 Codex nihai raporu | 63 | 7 | 55 | 0 | 1 | 0 | 0 |
| **Toplam** | **551** | **323** | **137** | **6** | **33** | **40** | **12** |

Karşılıksız satır: **0**. Sayım betikle yapıldı (her satırda dört hücre, sınıf altı değerden biri, karşılık dolu; kullanılan her kalem numarası bu belgede tanımlı). T9 üçüncü sürümde eklendi ve ayrı betikle sayıldı: 63 satır, 63 ayrı kimlik, eksik ya da fazla kimlik yok.

İkinci sürümde değişen: T1'e üç satır eklendi (envanter 5.17, 5.18, 5.19); T1'in üç ve T2'nin on sekiz "havuz" satırı Hat C kalemlerine bağlanıp "K1 sonrası" oldu; T3'te W-3 "havuz"dan B4.13'e geçti. İlk sürüm: 485 satır, havuz 28. Kalan 6 "havuz" satırı: T3 U-7 (ilan kartı, görev sayfası), T5 Y14 ve Y17 (çok kayıt noktası, harita), T6 K-ses, T7 D-023 ve D-039.

Sınır: kaynak satırlarını ben böldüm. Bir paragraftaki iki ayrı isteği tek satır saymış olabilirim; inceleme de bu 500'e yakın satırı kaynaklarla tek tek karşılaştırmadığını yazdı. 13 Kasım notlarının E, P, R ve S bölümleri yorum ve karar kaydıdır; her biri tek satır olarak alındı.

---

## 9. Bütçe ve model

Token bütçesi kabadır: düşük (tek kısa oturum), orta (tek uzun oturum), yüksek (birden çok uzun oturum ya da bağımsız incelemeli iş). Rakam veremem; kullanım kayıtlarını görmedim.

| Kalem | Model | Bütçe |
|---|---|---|
| A0 | En güçlü | Düşük |
| A1 | En güçlü | Yüksek |
| A2.1 | En güçlü | Yüksek |
| A2.2 | İki model (kör karşılaştırma: biri en güçlü) | Yüksek |
| A2.3, A2.4, A2.5 | Orta model (dil A1 ve A2.1'de kuruldu) | Her biri orta |
| A2.6 | En güçlü (oyun kabuğu yeni dil kurar) | Yüksek |
| A2.7-A2.20 | Orta model | Her biri orta; A2.15 ve A2.16 düşük |
| Her ekranın ayrı göz incelemesi | Orta model | Düşük |
| B0 | Başka oturum; incelemesi en güçlü | Düşük |
| BA | Orta model | Orta |
| B1a | En güçlü (para) | Orta; YÜK-04'ün üç dalıyla yüksek (K25) |
| B1c | En güçlü (para; K27) | Orta |
| B1b | Orta model | Düşük |
| BS | Orta model; incelemesi bağımsız | Orta |
| B3a | Orta model; para metni parçası en güçlü | Orta |
| B2 (beş alt kalem; B2.0 küçük, B2.4 koşullu) | En güçlü | Yüksek (en pahalı kalem) |
| B3b, B3c | En güçlü | Her biri orta |
| B3d | En güçlü (kayıt ve Geri Al; KRİT-01) | Orta |
| Bütün dal incelemesi: motor ara kapısı, arayüz Tur 1, arayüz Tur 2, Kapı 1 öncesi | En güçlü | Her biri yüksek |
| Kapı 1 sonrası: B0c, B4.1-B4.14, C1-C5, arayüz Tur 3 ve Tur 4 | Kalem tablolarındaki gibi | Kalem planında yazılır; para ve kayda dokunanlar yüksek |

En güçlü modeli isteyenler, Kapı 1'e kadar: A0, A1, A2.1, A2.2'nin yarısı, A2.6, B1a, B1c, B2 (B2.4 yapılırsa beş kez), B3b, B3c, B3d, B0 ve B3a incelemeleri, dört bütün dal incelemesi. Yirmiyi aşan ağır iş (K25 ile iki tane arttı). K2 kararıyla Tur 2 de Kapı 1'in önüne geçti; bu, ilk sürüme göre bir ağır ekran (A2.6) ve bir bütün dal incelemesi ekler.

Haftalık limite sığar mı: **bilmiyorum.** Limitin rakamını ve bu haftaki kullanımı göremiyorum. Sığmazsa önerdiğim sıra: aynı haftaya iki "yüksek" iş koyma. A1 ile B2 çakışırsa B2 bekler (A1 Kadir'in önündeki ilk kapı). B2'nin alt kalemleri ayrı haftalara yayılabilir. A2.2'nin kör karşılaştırması bir kez yapılır, tekrarlanmaz.

---

## 10. Bekleyen küçük işler

| # | İş | Kim | Ne zaman | Kadir'in onayı |
|---|---|---|---|---|
| O1 | PR #34 ve main CI | - | Bitti: 10ffd8cb, CI yeşil (koşu 43337843149) | - |
| O2 | ui-a dalındaki 7d61ee5e'nin push'u (yedek) | Claude Code | Plan onaylanınca | Evet (push) |
| O3 | İzlenmeyen tek kopyaların yedeği: `AI-DND-4d` altındaki `docs/superpowers/plans/`; `AI-DND-portre` altındaki `docs/design/PORTRE_TASARIM_20261112.md` ve `docs/superpowers/plans/` | Claude Code | Plan onaylandı; ilk küçük işlerle birlikte | Verildi (K18; Kadir, 13 Kasım 2026): 4D dalı push edilmez; bu dosyalar PLAN klasörüne kopyalanır; dallar ve klasörler silinmez. Kopyalama henüz yapılmadı |
| O4 | Borç defteri güncellemesi (Görev 8). Kısmen yapıldı: `task/debt-register-20261113` dalı (6df2124a, klasör `AI-DND-debt`, uzakta yok) D-074, D-075, D-076'yı ekledi (3 satır). Görev 8'in istediği 12 Kasım kararları (D-020, D-056, D-061, D-062 ve bekleyenler) ve kırılgan arayüz testi satırı o commit'te yok; aynı dala eklenir | Claude Code, aynı dal | Motor ara kapısından önce | Push ve PR için evet |
| O5 | Onay listesine eklenecekler: dinlenme ifadesi düzeltmesi; ölü yazma kutusu testi; yaratım özeti testleri. Listede Kadir'in cevabını bekleyenler: madde 3, 4, 6, 7, 8, 9 | Claude Code yazar, Kadir cevaplar | Arayüz Tur 1 PR'ından önce | Evet |
| O6 | `docs/design/INDEX.md` güncellemesi: bu plan, `ANA_ENVANTER`, `KESME_SONRASI`, `MOTOR_HAKEM`, `PROTOTIP_ENVANTERI`, `ARAYUZ_KALITE_KURALLARI` eklenir | Claude Code | O9 ile aynı PR | Evet (PR) |
| O7 | Bu planın yerine geçtiği belgeler (silinmez; başlarına not düşülür): `ANA_ENVANTER` bölüm 10'un ilk mesaj satırı ve ilke 6; `KESME_SONRASI` 10.3'ün sırası; `ON_INCELEME_PLANI`'nın Görev 3-5 zamanlaması; `UI_KURULUM_AKISI` bölüm 4 sırası; `YOL_HARITASI` Faz 2-3 sırası; `UI_DILIM1_PLAN`; `MOTOR_HAKEM` bölüm 5'in sırası (K1 onaylanırsa) | Claude Code | Plan onaylanınca | Hayır (depo dışı belgeler) |
| O8 | İnceleme kopyası sunucularının kapatılması (8009, 22786; hâlâ açık) | Kadir söyleyince Claude Code | narration-source oturumu bitince; kullanıp kullanmadığını doğrulamadım | Evet |
| O9 | "Arayüz işi" bölümünün main'e girmesi (yalnız `CLAUDE.md`, 13 satır) | Claude Code | Plan onaylanınca, ilk iş | Evet (PR ve merge) |
| O10 | Yerel `main`'in ve oyun klasörünün (`AI - DND`, `dev/ai-dnd`) 10ffd8cb'ye alınması | Claude Code | Kadir oynamıyorken | Evet |
| O11 | **Kapı 1'in sert ön koşulu.** Haiku sayacı ve harcama kaydı (Görev 1). Bugün okunan: sayaç çalışıyor (aşağıda). Kalan: Kadir'in Kapı 1'de kullanacağı başlatma yoluyla tek Haiku çağrısı yapılıp sayacın arttığı görülür; oynayıştan önce ve sonra sayaç okunup notlara yazılır (K24 bunu her arayüz turu oynayışına da yaydı; O18) | Claude Code | Kapı 1'den hemen önce; bitmeden Kapı 1 başlamaz | Evet (küçük harcama: tek çağrı) |
| O12 | Ertelenen ön inceleme turları (Görev 3-5), yeni arayüzle bir kez; yolculuk satırı 5, 6, 25-29 burada denenir | Claude Code | Kapı 1'den hemen önce | Harcama tavanı için evet |
| O13 | `slot.sh` ve `slot_web.sh` korumaları (Kadir onayladı; koşulları narration-source oturumunun ledger'ında). **Bitene kadar kural:** commit edilmemiş işi olan klasörde `node` ve `codegen` çalıştırılmaz. Kural Hat A'nın her ekran oturumu için de geçerlidir | O oturum ya da Claude Code | Hat A'nın ilk ekran oturumundan önce | Verildi |
| O14 | B0'ın push'u ve PR'ı. Koşul: tam paketin birinci parçası (para ve kayıt modülleri) yeşil özet verir | narration-source oturumu | Koşul sağlanınca | Evet (push, PR, merge) |
| O15 | İkinci model ailesiyle (Codex) bağımsız inceleme denemesi (`KESME_SONRASI` 10.9): yalnız inceleme, kod yazmaz; B1a'nın incelemesinde bir kez; iki rapor yan yana konur. Kalıcı olma koşulu: Claude incelemesinin kaçırdığı en az bir gerçek kusur bulması | Claude Code | B1a başlamadan önce kurulum | Evet, kurulumdan önce ayrıca (kod OpenAI'a gider; anahtarı yalnız Kadir girer) |
| O16 | Plan belgelerinin yedeği (`claude/yedek/PLAN_BELGELERI_YEDEK_20261113.md`, projede) bu plan onaylanınca yenilenir | Bulut oturumu | Plan onaylandı; şimdi | Hayır |
| O17 | Codex denetim bulgularının doğrulanıp motor hattına yerleştirilmesi. Başka bir oturumda Codex ile salt okunur tam depo denetimi yürüyor (temiz klon, main 10ffd8cb). Bulgular bulut oturumunda doğrulanır; doğrulananlar motor hattına kalem olarak girer. Şimdi yer ayrılmadı; bulgular gelince sıralanır ve tavan kuralına (bölüm 7) göre yerleştirilir. **Güncelleme (13 Kasım 2026, akşam): nihai rapor geldi (63 bulgu; 10'u bağımsız okunarak doğrulandı). Hepsi T9'a alındı; Kapı 1 sonrası olanlar B5.1-B5.10'da; Kapı 1 öncesi adaylar bölüm 4'te; yerleşim K25 ve K27 ile kapandı (aynı gece). Kural: her düzeltme önce kırmızı testle başlar; kırmızı test yazılamayan bulgu doğrulanmamış sayılır** | Bulut oturumu doğrular; Claude Code plana işler | Bitti (plana işlendi; K25 ve K27 kapandı) | Sıra değişirse evet |
| O18 | Harcama koruması (K24). (a) Kadir Anthropic panelinden aylık harcama sınırı koyar; kod işi değildir. (b) Kodda ortak tavan ve oyuncu başına sınır Aşama 3'te yapılır; ikisi de para yüzeyidir. (c) Kapı 1'den ve her arayüz turu oynayışından önce ve sonra sayaç okunur ve fark yazılır | (a) Kadir; (b) Aşama 3'ün kalemi; (c) Claude Code | (a) ilk bulut zinciriyle oynayıştan önce; (b) Aşama 3; (c) her oynayışta | (a) Kadir'in kendi işi; (b) kalem planında; (c) hayır (okuma) |
| O19 | Kitap yönü taslağının depoya yansıması: (a) `docs/design/INDEX.md`'ye karar belgesi, hedef resim klasörü ve A1 istemi için satır; (b) `CLAUDE.md` "Arayüz işi" bölümünde hedef listesine kitap taslağı klasörünün eklenmesi; (c) bitti tanımı (3)'ün üç temayı söylemesi (Çelişki 26). **Durum (13 Kasım 2026, gece): Kadir yalnız (c)'yi istedi; ayrı belge dalında yapıldı (`task/arayuz-uc-tema-20261113`, commit 3b1f7e46, main'in 6be96c9f ucundan; yalnız `CLAUDE.md`, tek satır: "(3) üç tema: Gündüz, Gece ve Karanlık"). Kadir push'a evet dedi: PR #41 açıldı. CI ilk denemede kırmızı (koşu 43481782694; yalnız arayüz tarayıcı testi düştü, D-082), aynı kodda yeniden koşuda yeşil. Kadir'in onayıyla birleşti: 9d250a9d (13 Kasım 2026, 21:44). (c) kapandı.** (a) ve (b) açık; A1 başlamadan önce ayrıca sorulur. Not: bitti tanımı (6) çizim klasörü istisnasını söylemiyor (A0b, çizimlerin iç renkleri); istenirse aynı tür belge düzeltmesiyle eklenir | Claude Code | A1 başlamadan önce | (c) bitti; (a) ve (b) için ayrıca evet |
| O20 | **Arayüz bütünleştirme dalının kurulması.** Bugün yok (13 Kasım 2026 gece bakıldı). `task/ui-a-gorsel-20261112` ucundan (7d61ee5e; biri yalnız yerelde 31 commit) yeni dal açılır ve `origin/main` içine alınır (bugün 20 commit). Çakışma çıkarsa çözümü, `typecheck`, `test` ve `test:ui` çıktısı rapora yazılır; koşmayan test geçti sayılmaz. Önerilen ad: `task/ui-butunlestirme-20261113`. **A1 bu dalı kurmaz; hazır bulur, yoksa durur** (Kadir, 13 Kasım 2026, gece). **Durum (13 Kasım 2026, 21:24): kuruldu.** Kadir işi kod oturumuna verdi ("Onayım: kur"). Dal `task/ui-butunlestirme-20261113`, uç 1df7065a, worktree `C:\Users\Kadir\Desktop\AI-DND-butunlestirme`; ebeveynleri 7d61ee5e (ui-a yerel ucu) ve 6be96c9f (o anki main, PR #39 dahil). Plan oturumu şunları kendi baktı: iki ebeveyn, `readerLeftStoryBottom` dalda (`game-browser.tsx` içinde 3 yerde), dal uzakta yok (push edilmedi). **Yeşil koşu raporu (kod oturumunun raporu; plan oturumu yeniden koşmadı):** çakışma yok, dört dosya otomatik birleşti (`CLAUDE.md`, `content/names/tr_names.json`, `play-screen-ui-regression.test.mjs`, `game-browser.tsx`; kaydırma mantığı yalnız main'den geliyor); `typecheck` geçti (önce kütüphaneler `tsc --build` ile derlenmeli, yoksa 318 TS6305 hatası verir; kod hatası değil); `test` 531 + 258 test, 0 başarısız, 1 atlanan (hangisi olduğuna bakılmadı); `test:ui` 7/7 geçti (`CHROMIUM_PATH` ayarlanınca; tek koşu, yineleme yok); `play-viewport.test.mjs` 22/22; dört yolculuk komşu modülü 162 test, hata yok. **Açık:** (1) push Kadir'in onayını bekliyor (kod oturumu sordu); (2) dal kurulduktan sonra main ilerledi (PR #38 birleşti: c946e292; PR #40 ve #41 merge onayı bekliyor; hepsi belge, iki test dosyası ve `CLAUDE.md`, arayüz kodu yok), A1 ön koşulu "`origin/main` dalın atası" yeniden tutsun diye main bir kez daha içine alınmalı; bunu worktree'nin sahibi olan kod oturumu yapar | Claude Code: kod oturumu, ayrı worktree'de; A1 oturumu değil | A1 başlamadan önce | Kuruldu (Kadir'in "kur" onayıyla). Push için taze onay bekleniyor. Main'in ikinci kez alınması aynı işin devamıdır |

**O11 için bugün okunan (13 Kasım 13:30; yalnız okuma). Sayaç dosyasında anahtar ya da gizli bilgi yok; üç alan var: `month`, `input_tokens`, `output_tokens`.**
- **Haiku sayacı çalışıyor.** Gerçek dosya `%LOCALAPPDATA%\AI-DND\model-chain-spend.json` en son 12 Kasım 14:34'te yazılmış: ay 2026-11, girdi 9.344.320 token, çıktı 296.505 token. Bu saat 12 Kasım'daki ajan oynayışının (son Haiku çağrılarının) saatine denk geliyor.
- **"3 Kasım'dan beri değişmemiş" görüntüsü yanlıştı; nedeni bulundu.** Claude masaüstü uygulaması, kendi içinden çalışan araçlara (PowerShell, `ls`) bu dosyanın eski bir kopyasını gösteriyor: `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\AI-DND\model-chain-spend.json` (3 Kasım 00:15; girdi 6.142.331, çıktı 198.491). Oyunun Python'u gerçek dosyayı okuyup yazıyor; aynı Python'la okuyunca doğru dosya görünüyor. Kural: sayaç bundan sonra yalnız Python'la okunur. "Sayaç iki ayrı dosyada tutuluyor olabilir" şüphesinin kaynağı da budur: ikinci dosya oyunun değil, uygulamanın kopyasıdır.
- **Sınır yok, yalnız sayaç var.** `ai-dnd/api/model_chain.py` içindeki nota göre aylık dolar sınırı 3 Kasım 2026'da sahibinin kararıyla kaldırıldı. `HaikuSpend` yalnız token sayar; Haiku'yu ancak dosya okunamazsa ya da yazılamazsa durdurur. Kapı 1'de harcamayı durduran bir kapı yoktur; koruma, oynayıştan önce ve sonra sayacı okumaktır. Düzeltilecek bir para hatası bulunmadı.
- Sayaç ile kullanım kaydı tutarlı: kullanım kaydı (4 Kasım'da başlıyor) Kasım için 397 Haiku satırı, 2.992.461 girdi ve 91.411 çıktı token gösteriyor; sayacın 3 Kasım 00:15'ten sonraki artışı 3.201.989 girdi ve 98.014 çıktı. Fark, kullanım kaydının başlamasından önceki bir buçuk güne denk geliyor (çıkarım).
- `KESME_SONRASI` bölüm 8'deki fiyatla (milyon token başına girdi 0,10 ve çıktı 0,50 USD) Kasım'ın bugüne kadarki Haiku tutarı yaklaşık 1,1 USD eder (tahmin; fiyatı ben doğrulamadım).
- Harcama kaydı: Windows'tan açılan sunucular (inceleme kopyası dahil) `%LOCALAPPDATA%\AI-DND\model-usage.jsonl` dosyasına yazıyor (1342 satır: 823 Gemini, 397 Haiku, 122 Gemma). 12 Kasım ajan oynayışı bu dosyada var.
- Bakılmayan: WSL ev klasörü; Kadir'in Kapı 1'de kullanacağı başlatma yolunun aynı dosyaya yazdığı (O11'in kalan adımı).

---

## 11. Riskler, çelişkiler, itirazlar, doğrulanmayanlar

### Riskler

| # | Risk | Belirtisi | Karşılığı |
|---|---|---|---|
| 1 | Başarı ölçüsü geç sınanır (K2'nin kabul edilen bedeli) | Kapı 1 on ekranın arkasında; dört kutu haftalarca sınanmamış kalır | Tur 1'in sonundaki 10 dakikalık oynayışta dört kutunun durumu not edilir; eksik kutu erken görülürse motor sırası ona göre değişir |
| 2 | Dilim 1 savaşı ağırlaştırır | Savaş turu yerel modelde 0 sn'den yaklaşık 6 sn'ye, bulutta yaklaşık 2 sn'ye çıkar (tahmin) | Üç cümle sınırı; B2.4 koşullu: B2.1-B2.3'ten sonra iki kipte ölçüm, sonra Kadir'in kararı (K15) |
| 3 | Test yeniden yazımı gevşetmeye döner | 72 ile 497 arası test kırılır | Önceden sayıldı; her biri onay listesine işaretli girer; yüzey yüzey ilerlenir |
| 4 | Motor hattı darboğaz olur | 9 kalem sırada; Tur 1 ekranları BA, BS, B3a'yı bekler | K1 sırası: bekleyen veriler öne; ekran veri yoksa parçasız teslim |
| 5 | En güçlü model haftalık limiti | On beşe yakın ağır iş | Bölüm 9 sırası; aynı haftaya iki "yüksek" yok |
| 6 | Eski arayüz kodu yeni tasarıma karışır | 59 ham `select`; yeni ekranda eski CSS sınıfları | Sekizinci maddelerin 6 ve 7'si her ekranda aramayla kanıtlanır |
| 7 | Yanlış Türkçe ad her yere yayılır | Tek tablo tek hata noktası | BA'da adları Kadir okur; tabloda olmayan ad özgün hâliyle görünür |
| 8 | %80 ölçütü tutmaz | Tahmin %78-81; ret ve soru satırları motor cümlesi. B2.4 yapılmazsa savaş turları motorda kalır ve oran düşer | K14: payda tanımı; B2.4 kararı verilirken oranın etkisi de yazılır; Kapı 1 bulut zinciriyle |
| 9 | `narration_source` boş kayıtlar ölçümü bozar | Kaynak bildirmeyen çıkışların turu boş kaydediliyor (envanter 5.17) | B2.0: etiket turun bittiği tek noktada; ondan sonra boş kayıt kalmaz. B2.0'dan önceki ölçümde boş sayısı ayrıca yazılır |
| 10 | Kadir'in önünde iş birikir | Galeri, 10 ekran, 11 motor kontrolü (15 inceleme; K25'ten sonra), üç kapı | Aynı anda tek ekran ve tek motor kalemi; her kontrol tek şey |
| 11 | **Sayfalama (G1) en riskli arayüz işidir.** İstenen: metin sayfa dolunca karşı sayfaya geçer, iki sayfa dolunca sayfa çevrilir. Taslakta yok; uzun metin sayfanın içinde kayıyor | Sayfa sınırı yazı boyuna (19 ve 21 piksel), el yazısı seçimine, ekran genişliğine ve yazı tipinin yüklenme anına göre değişir. Kenar notu kendi satırından kopabilir. Model cevabı yazılırken sınır kayar. Pencere boyutu değişince okurun yeri kaybolur (T5'i bozar). 390'da tek sayfa ayrı düzen ister. Ekran okuyucu ve klavye sırası iki sayfada bozulabilir. Bugünkü kaydırma testleri (`play-viewport`, `play-screen-ui-regression`; D-082'nin takip mantığı) kaydırmayı sabitliyor; sayfalama onları yeniden yazdırır | (1) A1'e girmez. (2) A2.7'nin ardından, atılacak küçük bir denemeyle başlar: gerçek uzun bir kayıt, üç tema, iki yazı boyu, 1440 ve 390. Aday yol tarayıcının çok sütunlu metin akışıdır; denemedim, doğrulanmadı. (3) Deneme tutmazsa geri çekilme: taslaktaki hâl, yani sayfa içinde kaydırma. T5 iki yolda da kırmızı testle korunur. (4) Kaydırma testleri eşit sıkılıkla yeniden yazılır ve onay listesine girer ("gevşetme olabilir" işaretiyle). (5) Yazı tipleri oyunun içine alınmadan (A1) deneme yapılmaz; yoksa D-082'nin kayması sayfa sınırını da oynatır. (6) Zamanı: Kapı 1'den sonra (K26; Kadir, 13 Kasım 2026, gece) |
| 12 | Üç tema kanıt yükünü artırır (T6, T9) | Her ekranda dört yerine altı görüntü; yirmi ekranda kırk ek görüntü | Renkler yalnız `src/index.css` değişkenlerinden geldiği için tema başına ek kod beklenmez. Kontrast galeride üç temada ölçülür; ekranlarda yalnız galeride olmayan yeni bir renk çifti kullanılırsa yeniden ölçülür |

### Çelişkiler

| # | Çelişki | Öneri |
|---|---|---|
| 1 | `ANA_ENVANTER` ilke 6 "üç iş aynı anda yürümez"; `KESME_SONRASI` 10.3b iki hattı aynı anda yürütür | 10.3b geçerli (istemde belirtildi) |
| 2 | `ANA_ENVANTER` bölüm 10 "yeni oturumun ilk mesajı" | Yerine bu istem geçti |
| 3 | Notlar U sırası: önce çark, müzik, logo. `KESME_SONRASI` 10.3 ve istem: önce tema seti, sonra şikâyet sırasıyla ekranlar | Çarkın ve müzik düğmesinin kendisi A1 galerisinde; ana menü ve çark paneli Tur 2'de. Gerekçe: U bir öneriydi, 10.3 onaylı ve daha yeni; en ağır şikâyetler savaş, büyü seçimi ve özet |
| 4 | `ANA_ENVANTER` 4.9 ve notlar G-12: beş panel donuk. `KESME_SONRASI` 10.5: satır 9 (çanta) ve 10 (büyü hazırlama) "Sıra 2" | Var olan ekranların (Hazırlık ekranı, karakter sayfasındaki düz envanter listesi) temaya uydurulması A2'de; yeni paneller (ayrı Çanta, Defter, Harita, Kaydet/Yükle) donuk. Karar K19 |
| 5 | Dinlenme düğmeleri: `ANA_ENVANTER` 1.5 tek yeri Çatışma kartı sayıyor; notlar T düzeltmesi "belirsiz, sorulacak"; `KESME_SONRASI` 10.6 açık bırakıyor | Karar K7 |
| 6 | İstem "tek ad tablosu bugün iki ayrı yerde" diyor. Kod: `tr_names.json` tek ve iki dalda aynı; ui-a'daki `tr-names.ts` aynı dosyayı okuyor | Asıl ikilik katalog ve arayüz ad tablolarında. BA bunu çözer |
| 7 | `MOTOR_HAKEM` bölüm 5 "Kapı 1'den önce tavan beş parça" derken yalnız kendi dilimlerini sayıyor; aynı hatta ücret ve han da var | Bölüm 7; karar K1 |
| 8 | `MOTOR_HAKEM` bölüm 2 hazır cümleyi `finish_turn` çıkışı olarak tarif ediyor. Kod: 42 çıkış `finish_turn`'e uğramıyor | B2 iki katmanı da kapsar; itiraz 1 |
| 9 | Notlar L-sonuç (çıkarım): varış turları (6, 18, 26) "Motor". Rota kaydı: bu turlarda iki model çağrısı var | Sonuç değişmiyor (motor payı %58, eşik %40). B0 kesinleştirir |
| 10 | `KESME_SONRASI` bölüm 3 ve Görev 1: "12 Kasım ajan oynayışı kayda yazılmadı". 12 Kasım notları bölüm 6: 46 satır sayıldı. Bugünkü dosyada o günün satırları var | Soru büyük olasılıkla yanlış kurulmuş; kayıt var. O11 kalan adımı kapatır |
| 11 | Notlar H: "para ikinci cümlede geçti; anlatıcı parayı motordan önce yazdı". Rota kaydı: tur 10 `work / resolved`, tur 13 yalnız kese listesi | Ücret büyük olasılıkla tur 10'da ödendi. B1a'nın üçüncü testi bunu sabitler; ilk iki kusur gerçek |
| 12 | `ANA_ENVANTER` 2.9, 3.1, 3.2, 4.1 durumu "YOK". ui-a dalında var: `window.confirm` kalkmış, adım sırası ve zarlar, `level-up-card.tsx`, `xp-progress.ts`. Kadir'in oynadığı sürüm de ui-a idi | "YOK" görünüş için okunur; davranış korunur, ekranlarda yeniden giydirilir |
| 13 | `KESME_SONRASI` bölüm 9: "iki tür daha, hedef 12 tür". Veri (`origins.json`): 10 tür | Karar K6 |
| 14 | `ANA_ENVANTER` bölüm 9 ve `UI_BILINEN_KIRIKLAR`: iki bayat test açık. main'de bf0a91dc ikisini düzeltmiş; ikisi de `test:standard` kümesinde | Bitti sayıldı. Testleri koşmadım |
| 15 | Görev 0 "4D dalını yedekle". Dal main'den 0 commit önde | O3, karar K18 |
| 16 | `MOTOR_HAKEM` 2a "tek Türkçe tablo" yeni iş gibi. `ai-dnd/refusals.py` zaten tek ret tablosu | B3a genişletir, yenisini yazmaz |
| 17 | "Karakter sayfası özeti" iki ekranı da anlatabilir: kurulumun son adımı (SS9-SS10) ya da oyun içi pencere (SS16) | İlkini A2.4, ikincisini A2.10 yaptım. K2 kararıyla ikisi de Kapı 1'den önce; sıra önemini yitirdi |
| 18 | Hat C'nin istediği motor alanları (hasar türü, şifa kaynağının kalıcı alanı, kalabalık, ateş, pencere, hava, mekân türü, oyuncu notu) Kadir'in dondurduğu E ve H parçalarının içinde (`ANA_ENVANTER` bölüm 7; notlar G-12). İnceleme D2 ise bu öğelerin plana eksiksiz girmesini istiyor | Hat C Kapı 1'den sonra; sırası gelince Kadir E ve H'nin yalnız bu alanlarını açar. E ve H'nin geri kalanı donuk kalır. Karar K23 |
| 19 | İlk sürüm "sayaç dosyası 3 Kasım'dan beri değişmemiş" dedi. Gerçek dosya 12 Kasım 14:34'te yazılmış; uygulamanın içindeki araçlar eski bir kopyayı gösteriyor | Bölüm 10'daki O11 notu. Sayaç Python'la okunur |
| 20 | Envanter 5.17 kaynak bildirmeyen 43 dönüş ve 4 dış çıkış sayıyor; bu planın (a) sayımı `finish_turn`'e uğramayan 42 doğrudan dönüş sayıyor | Fark sayım tanımından (hangi dönüşün devretme sayıldığı; dış çıkışlar bu planda sayılmadı). B2.0 başlarken tek liste çıkarılır |
| 21 | `KESME_SONRASI` bölüm 5: "ortak aylık Haiku sınırı var (`HaikuSpend`)". Kod: sınır 3 Kasım'da kaldırılmış; `HaikuSpend` yalnız sayıyor | Kapandı: `KESME_SONRASI` 10.10 düzeltme notu eklendi; karar K24 |
| 22 | K19 ve Çelişki 4: "ayrı Çanta ve Defter paneli donuk; yeni panel yazılmaz". Kitap yönü taslağı (T2): Çanta ve Günlük kendi ayracıyla açılan ayrı sayfalardır | T2 daha yeni ve Kadir'in kararı. Ruling: yeni veri ve yeni özellik yazılmaz; var olan düz envanter listesi Çanta sayfasına, var olan Günlük sekmesi Günlük sayfasına taşınır. A2.10 "Karakter ve Çanta sayfaları", A2.11 "Dünya ve Günlük sayfaları" diye okunur; ekran sayısı değişmez, tavan tutar. Yanlışsa maliyeti: bir oturumun ikiye bölünmesi. Kapı 1'e etkisi (K26, kapandı): Dünya ve Günlük sayfaları Kapı 1'den sonradır (A2.11, Tur 3); Karakter ve Çanta sayfaları Tur 2'dedir |
| 23 | K7: dinlenme düğmelerinin tek yeri "Dünya penceresi, Çatışma sekmesi". Taslakta Çatışma sekmesi ve dinlenme düğmesi yok; beş ayraç var | Kapandı (K26; Kadir, 13 Kasım 2026, gece): dinlenme düğmeleri Karakter sayfasında, mumların altında (A2.10). K7'nin yer cümlesi bununla değişti; "yazıyla dinlenme her yerde çalışır" kısmı aynen kalır |
| 24 | A0-7 (öneri gibi kapandı): kayıt bildirimi sağ üstte küçük mühür. Taslak ilkesi 3: "kurdele kayıttır"; ilke 5: kırmızı yalnız mühür ve kurdelededir | Galeride iki seçenek yan yana gösterilir; Kadir seçer. Seçilene kadar A0-7 geçerli |
| 25 | A1 tablosu ve Hat C kuralı: "sayı her zaman yazılı kalır". T12: mum grubunun altında yalnız seviye adı; "4'te 2 yanıyor" satırı yok | Ruling: görünen yazıyı T12 belirler; kalan yuva sayısı ekran okuyucuya okunur ve ipucunda yazar. Mühürde sayı görünür kalır (taslakta "43 / 49"). Yanlışsa maliyeti: bir satır metin |
| 26 | `CLAUDE.md` "Arayüz işi" bitti tanımı (3): "gece ve gündüz teması". T6 ve T9: üç tema var | Plan üç temayı kanıta ekledi (A1, A2 madde 3, galeri kapısı). Kadir `CLAUDE.md` metninin üç temaya göre düzeltilmesini istedi (13 Kasım 2026, gece); düzeltme main'e girdi (PR #41, 9d250a9d; O19 c). **Kapandı:** depodaki metin artık "üç tema: Gündüz, Gece ve Karanlık" der |
| 27 | A0-5 (öneri gibi kapandı): ayar sırası ses, görünüm (tema, efekt seviyesi), okuma, göstergeler. T3: "Arayüz" bölümü görünüm, sayfa düzeni, el yazısı, yazı boyu | "Arayüz" bölümü T3'teki gibidir; ses, efekt seviyesi ve gösterge seçimi ayrı bölümdür. Sıra ve kapsam A2.8 taslağında (G11) |
| 28 | 11 Kasım tarihli `UI_TASARIM_PLANI`: gece sayfası `#11161B`. Taslak: bu renk artık "Karanlık" temasının sayfasıdır; varsayılan gece sararmış kâğıttır (`#D4C394`) | Karar belgesinin 3. bölümü geçerli |

### İtirazlar

1. **Dilim 1'in kapsamı eksik tarif edilmiş.** Hazır cümleyle biten 42 çıkış `finish_turn`'den geçmiyor. "Dokunduğun yeri önce ayır" kuralı bu yüzden iki bölgeyi ayırmayı gerektirir ve iş büyür. B2'yi beş alt kaleme böldüm (B2.0 çıkışta etiketleme, sonra dört yüzey). İnceleme bu itirazı haklı buldu.
2. **Tur süresi ölçütü savaşı gizliyor.** Ortanca iki kat eşiğinin içinde kalır (tahmin 12,0 sn'den 12,8 sn'ye), çünkü yavaş olan zaten hamleyi okuma çağrısı. Ama savaş turları bugün model çağırmıyor; Dilim 1'le her vuruş yerel modelde yaklaşık 6 sn, bulutta yaklaşık 2 sn bekletir. İncelemeyle birlikte çözüm: B2.4 koşullu oldu ve ölçüm Kadir'in oynadığı kipte yapılacak (K15).
3. **Kapı 1'in koşulu dar.** (Kapandı: Kadir, 13 Kasım 13:12, Kapı 1'i Tur 1 ve Tur 2'den sonraya aldı.) İlk sürümdeki itiraz: "ilk tur kabul edildi" denirse Kadir 30 dakikayı eski oyun kabuğunda geçirir.
4. **%80 ölçütünün paydası tanımsız.** Ret, soru ve onay satırları tasarım gereği motor cümlesidir; sayılırsa hedef tutmayabilir (K14, hâlâ açık). Kaynağı boş turlar sorusu Kadir'in 5.18 kararıyla kapandı: B2.0'dan sonra boş kayıt kalmaz; `qwen` ve `mixed_engine_model` modelden sayılır.
5. **A1 tek oturuma fazla.** On beşten çok parça, üç yeni gösterge ve zar. Öneri: iki oturum (temel kontroller; göstergeler ve zar), tek galeri, tek onay. "Tek ekran, tek oturum" kuralının amacı kaliteyi korumaktır; galeriyi tek oturuma sıkıştırmak tersini yapar.
6. **İki yeni tür.** Oyunun kural kaynağında 10 tür var. İki tür daha eklemek kural kaynağının dışından içerik demektir ve lisans sorusunu açar. Kararı yeniden açmıyorum; öneri: hangi tür olduğu Faz 4 (kendi dünya ve lisans) ile birlikte kararlaştırılsın, o zamana kadar 10 tür.
7. **Düşman canının sayısı API'de kalırsa** tarayıcının ağ sekmesinden okunur. Karar "sayıyla gösterilmez" diyor; ruhuna uygunu sayının yanıttan da kalkmasıdır (K16). Test etkisini saymadım.
8. **B0 commit'i `openapi.yaml`'ı değiştiriyor** ama üretilen istemciler commit'te görünmüyor. CI'da "üretilen kod güncel mi" denetimi varsa kırılır. Doğrulamadım; o oturuma dokunmadım.
9. **Görev 0 gereksiz görünüyor** (Çelişki 15).
10. **Öneri (belgelerde yok, yeni özellik değil):** rota kaydı (`route-log.jsonl`) zaten var ve her oynayışın tur başına çağrı sayısını tutuyor. Kapı 1 notlarının resmi ölçüm kaynağı yapılırsa (c) ve hamle kaynağı her oynayışta kod yazmadan ölçülür.

**Bağımsız incelemeye (`PLAN_INCELEMESI_20261113.md`) itirazım: yok.** D1, D2, D4, D5, D6, D7 ve D8 işlendi; D3 Kadir'in kararıyla uygulanmadı. İki küçük düzeltme notu:
- D8 "9 kalem gerçekte 12 inceleme kapısıdır" diyor. D1'in istediği B2.0 eklenince sayı 13 oldu (B2.0 kayıttaki izinli listeye dokunduğu için ayrı inceleme ister). B2.4 yapılmazsa 12.
- D2 prototip öğelerinin plana eksiksiz girmesini istiyor; girdi (Hat C). Ama bu öğelerin bir bölümü motor alanı ister ve o alanlar Kadir'in dondurduğu E ve H parçalarının içindedir. Bunu ne D2 ne de ilk sürüm söylüyordu; Çelişki 18 ve karar K23 olarak yazdım.
- D7'de adı geçen üç şeyi doğrulayamadım: `slot.sh` ve `slot_web.sh` korumalarının koşulları (betikler `AI-DND-TOOLS` klasöründe; anahtar yasağı nedeniyle klasörü açmadım, yalnız birkaç dosya adını gördüm), narration-source oturumunun ledger'ı (bulamadım) ve projedeki yedek dosyası (bu bilgisayarda değil). O13, O14 ve O16 incelemenin yazdığı hâliyle plana girdi.

### Doğrulanmayanlar

- Hiçbir test koşulmadı; oyun çalıştırılmadı; hiçbir ekran görüntüsü ve prototip dosyası açılmadı.
- Sayım (a): çıkışların çağırdığı alt işlevlerin (`grounded_action.resolve_turn`, `action_economy.execute`, `bold_acts.resolve` ve diğerleri) iç dalları sayılmadı. Dört çıkışın modele gidip gitmediği duruma bağlı.
- Sayım (b): metin araması. Bir cümleyi değişken üzerinden bekleyen test yakalanmaz; sahte model çıktısını bekleyen test geniş ölçüye fazladan girer.
- Sayım (c): model çağrısı süresi; uçtan uca süre değil. "İlk çağrı hamleyi okumadır" varsayımı rota adından çıkarıldı.
- Sayım (d): yapılamadı.
- ui-a ile main'in birleşmesi denenmedi.
- B1a: kese değerleri tur 10 öncesi ve sonrası okunmadı. B1b ve B1a'nın kök nedenleri kod ve rota kaydı okumasıdır; kırmızı testle doğrulanmadı.
- BS: "Yaklaş / Uzaklaş"ın var olan `move` ve `disengage` eylemlerine nasıl bağlanacağı.
- B0: üretilen istemcilerin durumu; boş kaynak kayıtlarının oranı (B2.0 kapatacak).
- WSL ev klasöründeki kayıtlar; 8009 ve 22786'yı şu an kimin kullandığı; Kadir'in Kapı 1'de kullanacağı başlatma yolunun Haiku sayacını artırdığı (bugün yalnız dosya okundu, çağrı yapılmadı).
- İkinci sürümde eklenenler: narration-source dalındaki iki yeni commit'in içeriği (yalnız başlıklarını okudum); `slot.sh` ve `slot_web.sh` korumalarının koşulları; o oturumun ledger'ı; projedeki yedek dosyası; borç defteri dalının PR durumu.
- Hat C: bilgi kutuları için anlatıdaki kişi, yer ve eşya kimliklerinin işaretli gelip gelmediği; büyü yanıtında hasar türünün dolu olup olmadığı.
- Bulut kipinde tur başına süre: yalnız çağrı başına ortanca var (Gemini 1,7 sn, Haiku 2,5 sn); tur başına ölçüm yapılmadı.
- A0'daki 18 öneri ekran görüntülerine ve koda bakılmadan yazıldı; özellikle 15 (zarın bugünkü öneri yolunu çağırabilmesi) ve 18 ("Kapat" düğmesinin işi) koddan doğrulanmadı.
- Mikrofon hiçbir tarayıcıda elle denenmedi (belgelerdeki web kaynağı bilgisi aynen geçerli).
- Atmosfer katmanının oyunda görünüp görünmediği; motorun `world.weather` doldurup doldurmadığı.
- Yolculuk satırı 5 ve 6'nın kök nedeni; 25-29'un çalışıp çalışmadığı.
- Elle yazılmış renk kodu sayısı (ham `select` sayıldı, renk kodu sayılmadı).
- Kurallar kitabında 10 tür olduğu: yalnız `origins.json`'dan biliyorum; kitapla karşılaştırmadım.
- `task/ui-slice3-20261112` dalının main'den neden 5 commit önde göründüğü (PR #31 birleşmiş).
- Haftalık model limitinin rakamı ve bu haftaki kullanım.
- Kitap yönü taslağı (üçüncü sürüm): 13 hedef resmin hepsine bakıldı; `kaynak/` dosyaları ve canlı taslak sayfası açılmadı (değerler karar belgesinin 5. bölümünden alındı).
- T8: `campaign_time` ve `world.time_of_day` API sözleşmesinde ve arayüz kodunda okundu; çalışan oyunda her turda dolu geldiği denenmedi.
- Dört yazı tipinin (Literata, Kalam, Charm, Bad Script) lisansı ve dosya düzeyinde Türkçe harf desteği. Hedef resimlerde ç, ğ, ı, ö, ş, ü doğru görünüyor.
- Sayfalama için çok sütunlu metin akışı önerisi (Risk 11): denenmedi.
- Codex raporu: 63 bulgunun 53'ü bağımsız doğrulanmadı; hiçbiri çalıştırılarak üretilmedi. Bu sürümde yalnız üç şeyi denetlenen commit'te (10ffd8cb) kendim okudum: YÜK-04'ün kabul, tüketim ve devir dallarının `_front_offer_gate`, `_front_consume`, `_front_hand_over` işlevlerinde olduğu; diyalog teklifinin "Görev günlüğünden kabul edebilirsin" dediği; günlük bileşeninde kabul düğmesinin yalnız eski teklif listesinde bulunduğu. Yazıyla görev kabulünün çalışıp çalışmadığına, canlı modelin yanlış etiket sıklığına ve KRİT-01'in gerçekte tetiklenip tetiklenmediğine bakılmadı.
- B5 kalemlerinin boyutu ve sırası: yazılmadı; her kalemin kendi planında, kırmızı testler yazılabildikten sonra belli olur.
- Taslakta kurulumun 5. adımının adı "Beceriler"; bu planda A2.2 "Büyü seçimi, kurulum 5. adım". Koddaki adım adına bakılmadı; A2.2 başlamadan bakılır.
- `ARAYUZ_KALITE_KURALLARI` bölüm 2'deki üç sorunun cevabı: ikincisi (hazır bileşenler) ve üçüncünün yarısı (ham `select`) bu planda sayıldı; ekran görüntüsü alma aracı `KESME_SONRASI` 10.1'e göre kanıtlanmış, ben yeniden denemedim.

---

## 12. Kadir'in kararları

**Açık karar yok.** K25, K26 ve K27 13 Kasım 2026 gecesi kapandı (aşağıdaki tablonun son üç satırı). Kadir 13 Kasım 2026'da planı onayladı; K1 ve K3-K23'ü önerildiği gibi kapattı; K2'yi aynı gün 13:12'de vermişti; K24 yeni karardır. Aynı günün akşamı A0'ı kapattı, kitap yönü taslağını (T1-T13) ve yazı tiplerinin oyunun içine alınmasını onayladı.

### Kapatılan kararlar

| # | Konu | Karar | Kim, ne zaman |
|---|---|---|---|
| K1 | Motor hattında Kapı 1'den önce 9 kalem var, tavan 5 | İki aşama, arada kabul: B0, BA, B1a, BS, B3a; motor ara kapısı; B1b, B2, B3b, B3c; Kapı 1. K25 ile M-a'ya B1c, M-b'ye B3d eklendi | Kadir, 13 Kasım 2026 |
| K2 | Kapı 1'in yeri ve ilk turların ekranları | Kapı 1, arayüzün Tur 1 ve Tur 2'si (on ekran) kabul edildikten sonra yapılır. Tur dizilişi plandaki gibi kalır. Kabul edilen bedel: başarı ölçüsünün sınanması on ekranın bitmesine kadar ertelenir. Her arayüz turunun sonunda Kadir en az 10 dakika oynar; bu oynayışlar Kapı 1 sayılmaz ama dört kutunun durumu not edilir | Kadir, 13 Kasım 2026, 13:12 |
| K3 | Arayüzün temel dalı ve ui-a'daki 31 commit | Yeni arayüz işi ui-a dalının ucundan çıkar; 31 commit ilk tur PR'ıyla main'e girer. "Arayüz işi" kuralı ayrı küçük PR ile hemen girer (O9) | Kadir, 13 Kasım 2026 |
| K4 | Tek ad tablosu | Kaynak `content/names/tr_names.json`; yazıcısı motor hattı (BA) | Kadir, 13 Kasım 2026 |
| K5 | Tür ve sınıf adı | Kurulumda görünen adlar kalır: "Ejderhasoyu" ve "Şövalye" | Kadir, 13 Kasım 2026 |
| K6 | Eklenecek iki tür | Şimdi karar verilmez; 10 türle devam edilir; hangi türler olduğu Faz 4 ile birlikte kararlaştırılır | Kadir, 13 Kasım 2026 |
| K7 | Dinlenme düğmelerinin tek yeri | Dünya penceresi, Çatışma sekmesi, "Karakterinin kökeni" kartı. Sağ paneldekiler kalkar; yazıyla dinlenme her yerde çalışır (B3c). **Yer cümlesi K26 ile değişti: Karakter sayfası, mumların altı** | Kadir, 13 Kasım 2026; yer K26 ile aynı gece değişti |
| K8 | Model iş üretmeden (Dilim 3) önce Kapı 1 | Evet; Dilim 3 Kapı 1'den sonra (B4.2) | Kadir, 13 Kasım 2026 |
| K9 | "Büyüyle keseyi alıyorum" reddinde neden (envanter 5.12) | Neden söylenir; B3a kapsamında tek cümleyle | Kadir, 13 Kasım 2026 |
| K10 | Şifa Eli miktarı (envanter 5.14) | Miktar yazılmadıysa sorulur: "Kaç can? Havuzda 24 var" (B4.10) | Kadir, 13 Kasım 2026 |
| K11 | Bulut zinciriyle ayrı anlatım denemesi (envanter 5.3) | Ayrı deneme yapılmaz; Kapı 1 bulut zinciriyle oynanır ve cevabı o verir | Kadir, 13 Kasım 2026 |
| K12 | Ücretsiz Gemini katmanının veri kullanımı | Kapı 3'ten önce yakınlara söylenir ve onayları alınır; ücretli katman Kapı 2'deki harcama ölçümünden sonra değerlendirilir | Kadir, 13 Kasım 2026 |
| K13 | 13 Kasım oynayışı Kapı 1'in birinci denemesi mi | Sayılmaz: dört kutu sınanmadı ve yerel modelle oynandı | Kadir, 13 Kasım 2026 |
| K14 | %80 ölçütünün paydası ve kaynak etiketi | Ret, soru ve onay satırları "sistem" sayılıp paydadan çıkar; sayıları ayrıca yazılır. Etiket turun bittiği tek noktada verilir; beşinci değer `mixed_engine_model`; `qwen` ve `mixed_engine_model` modelden sayılır (envanter 5.18, 5.19; B2.0) | Kadir, 13 Kasım 2026 |
| K15 | Tur süresi ölçütü ve savaş anlatımı (B2.4) | Süre Kadir'in oynadığı kipte (bulut zinciri) rota ve kullanım kaydından ölçülür; yerel model için aynı sahnelerle ayrı kısa ölçüm yapılır. B2.1-B2.3 bitince iki kipte ölçülür ve B2.4'e Kadir o ölçümle karar verir. Eşik: savaş turunun ortancası bulutta 4 sn'yi, yerelde 8 sn'yi geçmez | Kadir, 13 Kasım 2026 |
| K16 | Düşman canının sayısı | API yanıtından da kalkar (BS) | Kadir, 13 Kasım 2026 |
| K17 | Kurulum özetinde can ve inisiyatif | Onaydan önce gösterilir, ama Kapı 1'den sonra (B4.14); o zamana kadar bu iki kutu ekranda olmaz | Kadir, 13 Kasım 2026 |
| K18 | 4D ve portre klasörlerindeki izlenmeyen tek kopyalar | 4D dalı push edilmez. `AI-DND-4d` ve `AI-DND-portre` altındaki izlenmeyen plan ve tasarım dosyaları PLAN klasörüne kopyalanır. Dallar ve klasörler silinmez (O3) | Kadir, 13 Kasım 2026 |
| K19 | Donuk beş panelden var olan ekranlar | Hazırlık ekranı ve düz envanter listesi temaya uydurulur (A2.20, A2.10); yeni panel yazılmaz | Kadir, 13 Kasım 2026 |
| K20 | 3B zar ve `three` paketi | Önce SVG zar (A1 galerisinde); 3B zar Kapı 1'den sonra ayrı kalem (C5) | Kadir, 13 Kasım 2026 |
| K21 | "Evet, tell me about the guard" testi (karar listesi A3) | B3c'de incelenir; beklenti "bilgi sorusu kavga başlatmaz" olarak yeniden yazılır ve onay listesine girer | Kadir, 13 Kasım 2026 |
| K22 | İnceleme sunucuları ve ui-a'nın bekleyen commit'i | Sunucular (8009, 22786) narration-source oturumu bitince kapatılır; ui-a'nın commit'i plan onaylandığı için push edilebilir. İkisi de işlem anında Kadir'in taze onayıyla yapılır | Kadir, 13 Kasım 2026 |
| K23 | Hat C'nin istediği motor alanları (donuk E ve H'nin içinde) | Hat C'nin ilgili kalemi başlarken yalnız bu alanlar açılır; E ve H'nin geri kalanı donuk kalır. Kapı 1'i bekletmez | Kadir, 13 Kasım 2026 |
| K24 | Harcama: kodda tutar sınırı yok | (a) Kadir Anthropic panelinden aylık harcama sınırı koyar; kod işi değildir. (b) Kodda ortak tavan ve oyuncu başına sınır Aşama 3'te yapılır; ikisi de para yüzeyidir. (c) Kapı 1'den ve her arayüz turu oynayışından önce ve sonra sayaç okunur ve fark yazılır (bölüm 6, O18) | Kadir, 13 Kasım 2026 |
| A0 | Tasarım konuşmasının 17 sorusu (2-18) | 6. cevap T8 oldu; 17. cevap T2, T4 ve T5 oldu; diğer 15'i önerildiği gibi (bölüm 3, A0 kapanışı) | Kadir, 13 Kasım 2026, akşam |
| T1-T13 | Kitap yönü taslağı | Tema setinin (A1) hedef resmi olarak onaylandı; son hâl değil, geliştirilecek (G1-G13). Kararlar ve plandaki yerleri: bölüm 3, A0b | Kadir, 13 Kasım 2026, 18:55 |
| Yazı tipleri | Ağdan mı, oyunun içinden mi | Oyunun içine alınır (A1); D-082 dersi | Kadir, 13 Kasım 2026, akşam |
| K25 | Codex adaylarının Kapı 1 öncesine yerleşimi ve tavan | YÜK-04'ün üç dalı (kabul, tüketim, devir) B1a'ya paketlenir. KRİT-03 ayrı parça olur (B1c). Tavan yalnız bu aşama (M-a) için 6. Adı anılmayan üç aday önerildiği gibi yerleşti (Ruling, bölüm 4 Sıra): KRİT-01 B3d, YÜK-12 B3c'ye kırmızı test, YÜK-16 A2.10. YÜK-11 ve YÜK-13 Kapı 1'den sonra | Kadir, 13 Kasım 2026, gece |
| K26 | Kitap yönü taslağının Kapı 1 öncesine etkisi | Sayfalama (G1) Kapı 1'den sonra. Dünya ve Günlük sayfaları (A2.11) Kapı 1'den sonra; Tur 3'te kalır. Dinlenme düğmeleri Karakter sayfasında, mumların altında (A2.10); K7'nin yer cümlesi değişti | Kadir, 13 Kasım 2026, gece |
| K27 | KRİT-03'ün birimi | Ödül altındır; kartın söylediği ödenir. Düzeltme yalnız diyalog ve macera görevlerinin ödül yoluna uygulanır; kasaba işlerine dokunulmaz. Kart ve ödeme aynı motor alanından, birimiyle okunur (B1c) | Kadir, 13 Kasım 2026, gece |
| K28 | D-249 oynayışı ile A2'nin sırası | Kadir D-249 dilimini 10 dakika oynamadan kod yazılmaz; yalnız hazırlık yapılır (A2.2 taslak istemi, v0 paketi, BS kalem planı) | Kadir, 16 Kasım 2026 |
| K29 | D-301: "X'a gidiyorum" | Gidiş cümlesi de anlatıcıya gider; iş B2.1'e (varış anlatımı) bağlanır | Kadir, 16 Kasım 2026 |
| K30 | Hat A ile Hat B | Paralel; ayrı worktree, her birinde tek yazıcı; her dalgadan sonra haftalık kullanım ölçülür, %80'de durulur | Kadir, 16 Kasım 2026 |
| K31 | A2.2'nin iki taslağı ve v0 | A: Opus, B: v0 (Vercel). İstemi Claude yazar, Kadir v0.dev'e yapıştırır ve çıktıyı verir; en çok 3 düzeltme isteği. Körlük yok; seçim sekiz madde kanıtı, ayrı göz ve Kadir'in gözüyle. Kazanan yol Tur 1'in kalanında kullanılır (S5'in "Tur 1'den sonra" kararı buna göre güncellendi) | Kadir, 16 Kasım 2026 |
| K32 | v0'a gidecek paket | Yazılı hedef (şikâyet notları ve sekiz madde), `src/index.css` tema değişkenleri, bileşen listesi, SS4-SS6 görüntüleri, kitap hedef resmi. Motor kodu, kayıtlar, anahtarlar ve oyun içeriği dosyaları gitmez | Kadir, 16 Kasım 2026 |
| K33 | Ekran taslağı | Her A2 ekranında önce kodsuz HTML taslak; Kadir görüntüden onaylar; kod ondan sonra | Kadir, 16 Kasım 2026 |
| K34 | Tur 1 sırası | A2.2, A2.3, A2.5, A2.4, A2.1 (savaş ekranı BS'yi bekler) | Kadir, 16 Kasım 2026 |
| K35 | Hat B sırası (16 Kasım durum taramasından sonra) | Önce BS, sonra BA, sonra planın sırası. Kısmen bitmiş B1a, B1b, B3a tek pakette: planın testleri yazılır, yeşilse kapanır. D-297 B1b'ye girer; D-302 Kapı 1 öncesi ölçüme; kalan D-294..D-306 park, Kapı 1'den sonra B5 kuyruğu. Durum taraması (origin/main 9f3fe9fa): B0, B1c, B3d, B3c'nin YÜK-12 parçası bitti; BA, B1a, B1b, B3a, B2.1-B2.3 kısmen; BS, B2.0, B3b, B3c'nin kalanı, B0c yapılmadı | Kadir, 16 Kasım 2026 |
| K36 | Kapı 1 koşulu ve eski dallar | Kapı 1 koşulu aynı kalır. Main'e alınmayan eski dallar arşiv olarak durur, birleştirilmez ve silinmez | Kadir, 16 Kasım 2026 |
| K37 | Önce model (BM) | Yeni kalem BM, Hat B'de BS'den önce: modelin hamle okuması belirleyici olur; cümleyi modelden önce yakalayan kelime yolları yalnız model cevap vermezse yedek kalır; hazır cümle en son çaredir ve kasaba bilgisini kullanır. Dayanak: 16 Kasım oynayışında 28 hamlenin 11'i motor hazır cümlesiyle bitti (`OYNAYIS_TANI_20261116.md`). D-249 düzeltmesi önce biter | Kadir, 16 Kasım 2026 |
| A1 istemi | Beş değişiklik | (a) `kaynak/` içindeki çizimler ve iki kâğıt dokusu aynen alınabilir; düzen işaretlemesi ve stil kodu taşınmaz. (b) Kontrast ekran görüntüsündeki gerçek piksellerden ölçülür; sırt gölgesine düşen kenar notları dahil. (c) Görünüm seçicisi dört seçenekli: "Hikâyedeki saati izle" (varsayılan), Gündüz, Gece, Karanlık; bölümün adı "Arayüz". (d) Bütünleştirme dalı A1'in içinde kurulmaz (O20). (e) Kâğıt dokusu küçük döşeme resmiyle yapılır, tam sayfa SVG filtresiyle değil | Kadir, 13 Kasım 2026, gece |

### Açık kararlar: yok

Aşağıdaki tablo 13 Kasım akşamı Kadir'e sunulan seçeneklerin kaydıdır. Üçü de aynı gece kapandı; kararlar yukarıdaki tablonun K25, K26 ve K27 satırlarındadır. Bu tablodaki "B1a.2" ve "B1a.3" adları artık kullanılmıyor: KRİT-03 ayrı parça oldu (B1c), YÜK-04'ün üç dalı B1a'nın içine girdi.

| # | Konu | Sunulan seçenekler ve öneri (kayıt) |
|---|---|---|
| K25 | Codex adaylarının Kapı 1 öncesine yerleşimi ve tavan (bölüm 7) | **Seçenek 1 (öneri): paketle.** KRİT-03 ve YÜK-04'ün kabul, tüketim, devir dalları B1a'nın alt kalemleri olur (B1a.2, B1a.3: aynı `_front_*` bölgesi, aynı para incelemesi); KRİT-01 M-b'nin beşinci parçası olur (B3d); YÜK-12 B3c'ye bir kırmızı test olur; YÜK-16 A2.10'a girer. Parça sayısı 5 ve 5 kalır; bedeli: B1a büyür (M'den L'ye) ve inceleme kapısı 13'ten 16'ya çıkar. **Seçenek 2: üçüncü aşama.** M-a ve M-b olduğu gibi kalır; KRİT-01, KRİT-03 ve YÜK-04 dalları üç parçalık üçüncü aşama olur, önünde bir ara kapı daha. Tavan her aşamada tutar; bedeli bir tam paket, bir bütün dal incelemesi ve bir oynayış daha; Kapı 1 gecikir. **Seçenek 3: ertele.** Kapı 1'den önce yalnız YÜK-16 ve KRİT-03'ün kart metni; gerisi Kapı 1'den sonra (B5). Bedeli: Kapı 1'de nötr bir cümle iş kabul edebilir ya da eşya tüketebilir; seyrek kayıt hatası (KRİT-01) açık kalır. YÜK-11 ve YÜK-13 üç seçenekte de Kapı 1'den sonradır (B5.6'nın ilk işi); önce istenirse M-b altı parça olur |
| K27 | KRİT-03'ün birimi: diyalog teslimatı ve kent soruşturması ödülü altın mı, bakır mı | Karar Kadir'in. Bilinen: kart "25 altın" yazıyor, kese 25 bakır artıyor; kasaba işi iki günde 46 bakır ödüyor. Bakır seçilirse yalnız kartın sözcüğü değişir, ödeme kodu değişmez. Altın seçilirse ödül yazıcısı değişir (para yüzeyi; aynı alanı bakır kullanan kasaba işlerine dokunulmaz). İki yolda da kart ile ödeme aynı birimi söyler ve kırmızı test bunu sabitler |
| K26 | Kitap yönü taslağının Kapı 1 öncesine etkisi (üç alt soru) | **(a) Sayfalama (G1) Kapı 1'den önce mi?** Öneri: hayır. Tur 2'de hikâye iki sayfada durur ama uzun metin sayfanın içinde kayar (taslaktaki hâl); sayfalama denemesi Kapı 1'den sonra, A2.7'nin ardından ayrı kalem olur. Gerekçe: Risk 11; Kapı 1 hikâyeyi sınar, sayfa çevirmeyi değil. Bedeli: Kapı 1'de kitap hissi eksik kalır. **(b) Dünya ve Günlük sayfaları (A2.11) Kapı 1'den önce mi?** Bugün Tur 3'te, yani Kapı 1'den sonra; ama ayraçları Tur 2'nin kabuğunda görünecek. Öneri: Kapı 1'de bu iki ayraç bugünkü içerikle, yeni kabuğun içinde açılır; A2.11 Tur 3'te kalır. Öbür yol: A2.11 Tur 2'ye alınır; tur altı ekran olur ve tavan (bir turda en çok beş ekran) aşılır. **(c) Dinlenme düğmelerinin yeri (K7).** Taslakta Çatışma sekmesi yok. Öneri: A2.11 taslağında yeri gösterilir ve o zaman karar verilir; o zamana kadar K7 geçerli |

### Kararla kapanmayan, sırası gelince Kadir'in önüne gelecek olanlar

Bunlar açık karar değildir; planın kapılarıdır ve kendi adımlarında sorulur.
- A0 kapandı (13 Kasım 2026). Galeri ve taslak onaylarında sorulacaklar: G10 ve kayıt bildirimi (A1 galerisi; Çelişki 24); G5 (A2.1 taslağı); G11 ve şafağın hangi görünüme denk geldiği (A2.8 taslağı); giriş ve kayıt sayfasının kapsamı (A2.9 taslağı); G8 (A2.12 taslağı).
- A1 galerisinin onayı; her ekranın taslak onayı ve kabulü; A2.2'de A ile B arasında seçim.
- BA'da Türkçe ad listesinin okunup onaylanması.
- B2.4 (savaş anlatımı): B2.1-B2.3'ten sonraki ölçümle.
- O15: Codex kurulumu için ayrıca onay (kod OpenAI'a gider).
- O17: Codex denetiminden doğrulanan bulguların motor sırasına yerleştirilmesi.
- Her push, PR ve merge için işlem anında taze onay.
- Kapı 1'den sonra: B4 ve Hat C'nin sırası (Kapı 1'in notlarından).
- **KRİT-02:** kapandı (D-166, Kadir 2026-11-15): tutarı motor belirler; yeniden sorulmaz.
