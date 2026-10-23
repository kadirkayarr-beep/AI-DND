# NPC konuşma kalitesi ve 9B geçişi: devir belgesi (23 Ekim 2026)

Dal: `dev/ai-dnd`. Bu belge başka bir yapay zekâ asistanının (ChatGPT) işe kaldığı yerden devam edebilmesi için yazıldı.
Önce "Kurallar" bölümünü oku, sonra "Kalan işler".

## 1. Ne yapıldı (özet)

Amaç: NPC'lerle konuşurken oyunun neden "ölü" hissettirdiğini bulmak ve motorun gereksiz engellerini azaltmak.
Bulgu: sorun büyük ölçüde modelde değil, motorda. Oyuncunun gördüğü cevapların çoğu motorun şablonuydu
ve iyi model cevapları motor tarafından atılıyordu.

Başlıca değişiklikler (commit sırasıyla, hepsi `ai-dnd/game.py` ağırlıklı):

| Commit | Ne |
|---|---|
| 5acfcac | Lore koruması: sorunlu cümleyi çıkar, cevabın tamamını atma. "Yakındaki kişi:" gibi genel etiketler kişi adı sayılmaz. |
| 451d604 | `resolve_npc_reference`: oyuncunun gördüğü etiketi ("Yakındaki kişi") yazınca o kişi hedeflenir. Eskiden kimse hedeflenmiyor, her takip sorusu "Hangisini kastediyorsun?" döngüsüne giriyordu (şikâyetin ana kaynağı). Tekrar koruması gerçek cevabı korur. |
| 1d1231e | Tekrar eden "göz gezdiriyorsun" ve "Seni dinliyorum" satırları tekrarda değişir. |
| 5902e73 | `aldırmak` ("umursamak") ve tırnak içi NPC sözü oyuncu eylemi sayılmaz. Son çare "değişiklik olmuyor" cümlesi 3 varyant. |
| f1a3088 | Tırnak içi `istersen/dilersen` serbest (anlatıcı metninde hâlâ yasak). 40 girdilik masum-cevap taraması eklendi. |
| c48df86 | Tekrar eden NPC cevabı, "Bu konuda bir şey bilmiyorum" ile değiştirilmez. Yalnızca Python'un çözdüğü somut sonuç varsa değişir. |
| 7531084 | `_salvage_plain_speech`: model cevabı iyiyken yardımcı konuşma önerisi bozuksa cevabı koru. Yalnızca işlem yok + `meaning` in (yok, "other") iken. |
| 078b76b | Varsayılan model `qwen3.5:9b-q4_K_M`. `start_local.ps1` loopback belirteci ve modeli aktarır. |
| a49939f | `query_type` yalnızca soru cümlesinde geçerli; "Belki" yanlış pozitifi; lore onarımı tırnağı ortadan bölmez; başıboş kapanış tırnağı temizliği; konuşma istemine 3 satır. |
| (son) | Tekrarlanan engelli maymuncuk denemesi farklı cümle döner (`grounded_action.py`). |

## 2. Kurallar (çiğneme)

* Python gerçeği yönetir: HP, zar, envanter, kalıcılık, gizli adın sızmaması **sert değişmezlerdir**. Gevşetme.
* "Model dedi" ile "dünyada doğru" ayrı kalır. NPC'nin söylediğini profile gerçek bilgi diye yazma (uydurmayı kalıcılaştırır).
* Her değişiklikten önce ve sonra ölç (aşağıdaki araçlar). Önce başarısız olan bir testle hatayı yeniden üret, sonra düzelt.
* Rapor dili: "tam regresyon temiz" **deme**. Doğru ifade: "tabana kıyasla yeni hata kimliği görülmedi".
  Baz çizgisinde 13 başarısız + 35 hata var (ortam kaynaklı, bkz. 4.g).
* Tek koşu kanıt değildir. Qwen örneklemesi her koşuda değişir; tek koşuda 29 ile 30 arasındaki fark gürültüdür.
* `.cursor/rules/ai-dnd-owners.mdc`: `game.py`'ye yeni özellik ekleme. **Bu çalışma buna uymadı** (bkz. 4.h, borç).

## 3. Araçlar ve komutlar

Windows PowerShell, `ai-dnd` klasöründen. UTF-8 zorunlu: `$env:PYTHONUTF8='1'`.

```powershell
# Çevrimdışı ölçüm (sahte model, hızlı)
python -m unittest api.tests.test_npc_transcript_replay_baseline
$env:NPC_STAGE_A_EVIDENCE_DIR = "$env:TEMP\npc_out"   # tur başına JSON + özet yazar

# Tam API testi (~17 dk). Bu makinede `.\dev.ps1` ve `unittest discover` çalışmaz (POSIX / modül çakışması):
$mods = Get-ChildItem api/tests -Filter 'test_*.py' | ForEach-Object { 'api.tests.' + $_.BaseName }
python -u -m unittest @mods *> out.txt
# Başarısız kimlikleri baz çizgisiyle karşılaştır:
#   docs/evidence/qwen-live-replay-20261023/baseline_failing_tests.txt  (46 benzersiz ad)
```

Çevrimdışı test dosyası `api/tests/test_npc_transcript_replay_baseline.py`. Sınıflar:
`TranscriptReplayBaseline` (Quenna ve han/kapı senaryoları), `BenignReplySweep` (40 girdi, model sahte ama masum),
`ProposalSalvage`, `NarrationGuardUnitTests`, `InteriorBaseline`. Ortak taban `ReplayHarness` (kendi testi yok).

Gerçek model ölçümü (Ollama açık olmalı; `ollama pull qwen3.5:9b-q4_K_M`):
`docs/evidence/qwen-live-replay-20261023/live_qwen_run.py` (tarama: `python live_qwen_run.py out.json sweep 40`) ve
`live_flow_run.py` (uçtan uca akış + kaydet/devam et). İkisi izole loopback portunda (8118/8119) ve geçici
SQLite ile çalışır, kalıcı kayda dokunmaz. `AI_DND_OLLAMA_MODEL=qwen3:8b` ile eski modele dönülür.
Ham sonuçlar aynı klasörde (`live_sweep_*.json`, `live_flow_2.json`).

Oyunu çalıştırmak: `.\start_local.ps1` (Ollama kontrolü, API :8008, arayüz :22785). Bu makinede yalnızca sözdizimi
doğrulandı, uçtan uca çalıştırılmadı (bkz. 4.j).

## 4. Kalan işler ve nasıl yapılır

**a. NPC konuşma hafızası istemlere taşınmıyor (en önemli).**
Bulgu: "Az önce ne sormuştum?" isteminde önceki soru yok; "Ailen var mı?" ikinci kez sorulunca önceki cevap istemde yok;
NPC bağlamında `conversation_focus` hep `null`. İki cevabın aynı çıkması hafızadan değil, aynı girdiye aynı çıktıdan.
Nasıl: NPC başına son N (örn. 6) konuşmayı **"söylendi, doğrulanmadı"** etiketiyle (konuşmacı, metin) istem bağlamına ekle.
Yer: `_experimental_npc_dialogue_context` ve `interaction_adventure.context` (`game.py`, `interaction_adventure.py`).
Profile veya `personal_profile`'a yazma. Test: önce `ProposalSalvage` benzeri bir test yaz (model bir önceki cevabı görmeli,
çelişen yeni cevabı kabul etmemeli); canlı doğrulama `live_flow_run.py` M2/M4/M5 adımları.

**b. Çoğu tur modelsiz şablon.**
Quenna senaryosunun 8 turunun 8'i motor şablonu ("Seni dinliyorum", "Ben X. Kent sakini olarak buradayım", "İyiyim; sabah erken kalktım").
Kişilik hissi yok. Nasıl: sade sohbet/selam/ad sorusunu modele aç, ama önce (a) yapılsın ve 9B'nin kalan hataları (c) süzülsün.
Yer: `_direct_npc_smalltalk_response`, `local_dialogue.personal_answer`. Model çağrı bütçesi (eylem başına 0–2) korunmalı.

**c. 9B'nin kalan model hataları.**
Profilde olmayan olgu uydurma ("Benim ailem yok"), uydurma tanışıklık ("senin yüzün bana tanıdık geliyor"), uzun anlatıcı
paragraflarında oyuncu adına eylem yazma (süzgeç doğru reddediyor). Uzun/uydurma sahne **tutarlıysa** sorun değil (sahibin kararı).
"Pelerini düzeltir" tiki için eklenen istem satırı ölçülebilir etki göstermedi (8'den 8'e); tutmak ya da kaldırmak sahibin kararı.
Nasıl: a ile olgu tutarlılığı; gerekirse dar süzgeç (oyuncunun cümlesini aynen tekrar, "Bulunduğun yer:" gibi iç sızıntı).

**d. Kalan reddedilen model turları.**
`UNVERIFIED_CONVERSATION_RESOLUTION`: cevabın kaderi modelin kendi `meaning` etiketine bağlı (kırılgan). Yer: `finish_conversation_resolution`.
`UNVERIFIED_LORE_CLAIM` zararsız selamda ("İyi günler"). `EMPTY_NARRATION`: model boş cevap döndürüyor (model hatası, yeniden deneme bütçesi yok).
"Bu şehir nasıl bir yer?" gibi dünya soruları lore kapısına takılıp NPC yerine anlatıcı cevabı veriyor
(`game.py` ~`world_subject_question` bloğu, `_unverified_lore_response`). Bilinçli tasarım; sahibin kararı gerekir.

**e. Genel "bina" iç mekânları (dükkân, ev) boş kalabiliyor.** Han sahnesi doğru doluyor (`commit_location_change` →
`materialize_scene`). Genel bina türleri için `living_world.materialize_scene` hiçbir şey eklemiyor; yeniden üretemedim,
tahminle kişi uydurma. Nasıl: önce hangi akışla boş kaldığını `InteriorBaseline` benzeri testle yeniden üret.

**f. Tam testlerde her koşuda farklı tek bir test düşüyor** (`test_compound_query...`, `test_walk_up_and_greet...`); tek başına
40/40 geçiyor. Şüphe: dünya rastgele kuruluyor (tohumsuz). Nasıl: tohumu sabitleyerek yeniden üret.

**g. Baz çizgisindeki 48 hata** (ortam): `test_api` (22 hata; örnek neden: `AuthenticationError: No server authenticator is configured`, yani testler bir kimlik
doğrulayıcı ortamı bekliyor; diğer hatalar incelenmedi), POSIX gerektiren
`test_runner_inventory`, `test_spells_v1` modül adı çakışması (`unittest discover` çöker), `test_ai_pipeline_port` iki test
birleşik koşuda düşer, tek başına geçer. Nasıl: Windows'ta atla/işaretle ya da WSL'de çalıştır. Önce tek tek kök neden.

**h. Mimari borç: `game.py`'ye eklenen yardımcılar** (`_salvage_plain_speech`, `_trim_dangling_quote`,
`_split_sentences_keep_speech`, `_variation_index`, `_CONVERSATION_OPENINGS`, `_look_opening`, `_model_query_type_is_plausible`).
Sahip kuralı bunu yasaklar. Nasıl: davranış değiştirmeden `local_dialogue.py` ya da yeni bir `narration_repair.py`'ye taşı,
`game.py`'de ince bir içe aktarma bırak; her taşımadan sonra bu belgedeki testleri koştur.

**i. İzlenmeyenler:** `.cursor/mcp.json` (boş taslak), `ai-dnd/docs/evidence/door-live-231b6cd-20261016/` (ikili SQLite + ekran görüntüsü,
eski commit'e ait; yeniden koşulmalı). Karar sahibin.

**j. `start_local.ps1` uçtan uca denenmedi.** Çalıştır, `http://127.0.0.1:8008/api/game/health` `model` alanında
`qwen3.5:9b-q4_K_M` görmelisin. Kod yolu adaptör üzerinden Ollama'da doğrulandı (yalnızca 9B yüklendi).

**k. Eski dumanlar `qwen3:8b`'ye sabitli:** `api/live_smoke.py`, `api/tests/live_*_smoke.py`, `live_*_test.py`. Üretim varsayılanına
(`PRODUCTION_LOCAL_MODEL`, `api/local_model_config.py`) bağla ya da bilerek 8B bırak.

**l. Oyun tasarımı sorusu:** oyuncunun başlangıçta hırsız aleti yok, kilitli kapıda maymuncukla ilerleyemiyor ve alet edinme yolu
gösterilmiyor (cevap "başka giriş ara"). Bir döngü açığı mı, bilinçli mi? Sahibin kararı.

**m. Oyuncuya görünen mekanik tekrarlar:** aynı engelli eylem tekrarında artık 3 varyant var; "Çevreyi gözlemliyorum" 4 varyant.
Daha çok çeşit istenirse havuzları genişlet (`_LOOK_OPENINGS`, `_CONVERSATION_OPENINGS`, `_GENERIC_NO_CHANGE_RESPONSES`).

## 5. Ölçüm özeti (gerçek `qwen3.5:9b-q4_K_M`, 40 giriş, tek kampanya)

| | Başlangıç | Son |
|---|---|---|
| "Bulunduğun yer:" sızıntısı / asistan sesi / başıboş tırnak | 1 / 1 / 1 | 0 / 0 / 0 |
| Modelin metninin oyuncuya ulaştığı tur (34 model turundan) | 29 | 30 (gürültü içinde) |
| Reddedilen model turu | 4 | 4 |

Uçtan uca akış (Quenna → bitir → han → git → kapı/maymuncuk → kaydet → devam, 22 adım): takılma yok, kaydet/devam et sonrası
durum farkı 0 giriş. Yalnızca F12 (aynı engelli eylemin tekrarı) işaretlendi; sonrasında varyantlarla giderildi.
