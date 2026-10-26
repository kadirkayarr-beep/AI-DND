# AI-DND — LR00 devir prompt'u (26 Ekim 2026)

Bu belge yeni bir Claude oturumuna verilecek **bağımsız bir istemdir**. Tahmin etme. Belirsizse "bilinmiyor" de. Aşağıdaki "Kapatılamayanlar" ve "Karar bekleyenler" bölümlerini kendi kararınla kapatma. Ayrıntılı durum: `ai-dnd/docs/LR00_STATUS_2026-10-26.md`. Uygulanan plan: `ai-dnd/docs/superpowers/plans/2026-10-26-lr00-closure.md`.

## 1. Kimlik ve değişmez kurallar

- Ürün AI-DND: Python dünya gerçeğinin sahibidir (HP, zar, savaş, envanter, büyü, XP, kalıcılık, işlenmiş dünya). Qwen Türkçe niyeti ayırır ve anlatır; model metni dünya gerçeği değildir. Tarayıcı yalnız sunucu durumunu gösterir.
- Üretim modeli `qwen3.5:9b-q4_K_M`. `qwen3:8b` yalnız fixture. **8008 kapısı oyuncu sunucusudur, kullanılmaz.**
- Yeni kural mevcut sahip modüle girer; `game.py`'ye "bir özellik daha" eklenmez. Prompt guard gevşetilmez. Wave3, Spells V1, XP V1 adlandırılmadıkça açılmaz.
- Test beklentisi kırmızıyı örtmek için değiştirilmez; yalnız bir **ürün kararına** dayanıyorsa, gerekçesiyle değiştirilir. Test emekliliği yalnız sahip onayıyla.
- Commit/push yalnız istenince. Force-push, reset, `main` birleştirmesi yok. Commit mesajına atıf (attribution) satırı eklenmez.
- Ürün `.py` dosyaları çalışma ağacında CRLF, indekste LF. `PYTHONUTF8=1`; testler `ai-dnd` içinden `PYTHONPATH=.` ile. Faz 7 kapanmış sayılmaz; canlı olay UNRESOLVED.

## 2. Ne yapıldı (kanıtlı)

Temiz `cb40a59`'da 2874 testin **141'i** düşüyordu. Her testin ilk kırıldığı commit 7 geçmiş noktada koşularak ölçüldü. Son tam koşu (Windows, çalışma ağacı): **2882 test, 13 başarısızlık (11 test yöntemi), 0 hata**; hepsi §4'teki D4–D6 kümelerinde.

**Gerçek ürün hataları (düzeltildi, testli)**
- `5a83e6d`: adlandırılmış ama kayıtsız bir nesne aranınca miss, modelin sahne-ayrıntısı önerisi doğrulanmadan veriliyordu (OH1-05 yaratım kırıktı). Karar `game.py` tur akışında, öneri doğrulandıktan sonra; genel miss yalnız **başarılı** zarda. LR00-P2 testi değiştirilmeden geçiyor.
- Ollama `num_ctx` hiç verilmiyordu (varsayılan 4096): canlı 9b çağrılarının 5/47'si `done_reason=length` ile kesilip "Çevrede şimdilik belirgin…" yedeğine düşüyordu. `api/ollama_adapter.py` artık 8192. Son canlı prob: kesilen 0.
- Model **geçersiz JSON** döndürünce tur normal başarı gibi görünüyordu: `infrastructure_failure` (`a99564f`) bir birleştirmede kaybolmuştu; geri getirildi (503, tur kaydedilmez). Provider kesintisi/zaman aşımı eskisi gibi deterministik yedekle sürer.
- 80 konum sınırı (`limit_reached`) aynı birleştirmede kaybolmuştu; geri getirildi.
- "Hoş geldin/Hoş geldiniz" uydurma oyuncu eylemi sayılıp NPC cevabını siliyordu.
- `save_campaign`: yabancı, var olmayan kimlikle aynı 404'ü görür (önceden 409 ile kampanya varlığı sızıyordu).
- `exact_narration_evidence_ids` (`api/lore_authority/claim_authorization.py`): `narration_only` istemi atıf istemediği için kayıtlı resmi lore cümlesi desteksiz sayılıp düşüyordu.
- Küçükler: savaşta tekrar eden "Rakibin savunmaya geçer", "Kılıç zaten yerde" dalı, UI'da ölü `interaction_mode` kastı.

**Test altyapısı:** NPC konuşması tek çağrılık yapılandırılmış paket (`spoken_text`, `stage_direction`); eski sahte modeller bu şemayı tanımıyordu. Ortak yardımcı `ai-dnd/api/tests/speech_double.py`; `auth_fixture.TestPlayerSessionManager`.

**Doğrulamalar**
- 33 kapı: WSL2 Ubuntu-24.04 (Linux dosya sistemi kopyası) **33/33 geçti**; günlük `ai-dnd/docs/evidence/v02-20261025/wsl-gates-20261026/gates.log`.
- UI: 158 geçti 1 atlandı; ek 20/20; Chrome `test:ui` 1/1 (`CHROMIUM_PATH` ile); `pnpm run typecheck` temiz.
- Canlı 9b prob (`live_lr00_probe.py`, `AI_DND_OLLAMA_MODEL`): `lr00-probe-20261026-qwen35-9b-final/` 62 tur, 48 çağrı, kesilen 0, sönük tur 1. `…-qwen3-8b-fixture/` 9b kanıtı **değildir**.

## 3. Kapatılamayanlar — nedenleriyle

| Konu | Neden kapatılamadı |
|---|---|
| **P0 canlı olay** (H01–H05) | Kaynak kişisel kampanya kaydı. Sahip D2'de okuma izni **vermedi**. Yeni sentetik tur bunu kapatmaz. UNRESOLVED kalır. |
| **P6 çıkış kararı, GOLD-EXPERIENCE** | Spec §11.3: proje sahibinin insan okuması gerekir. Test yeşilliği oyun kabulü değildir. PASS yazma. |
| **Python 3.13'te 33 kapı** | WSL'de yalnız 3.12.3 var, proje 3.13 istiyor. 3.13'te sonuç bilinmiyor. |
| **OH1-05 tam zinciri** (oluşum→kayıt→referans→etkileşim) | Canlıda uçtan uca, iki temiz kampanyada gösterilmedi; yalnız birim/sözleşme testleri var. |
| **B jesti, barmen akıcılığı** | 5 koşuluk örneklem; B bir kez NPC jesti verdi (model örneklemesi, süzgeçten değil). Dağılım ölçülmedi. |

## 4. Karar bekleyenler (13 başarısız test) — tahminle seçme

- **D4 (1 test)** `test_default_npc_targeting…respects_locked_target`: NPC kilitli han'ı öneriyor. Ürün (`_ground_local_place_recommendation_reply`) cümleyi "kilitli; doğrulamadan önermem" ile değiştiriyor; test NPC'nin kendi atıflı cümlesini bekliyor. Her ikisi savunulabilir; seçim ürün tasarımı.
- **D5 (9 satır)** `test_campaign_api`: profil/sınıflandırıcı yolunda ürün tur başına **2 model çağrısı** yapıyor (sınıflandırıcı + konuşma); testler tam 1 bekliyor. Çağrı bütçesi (OH1-08) ve rota kararı. `conversation_proposal_rejection` (3 alt-test) ve `missing_conversation_fields` temiz HEAD'de yalnız eski sahte model geçersiz paket döndürdüğü için tesadüfen geçiyordu.
- **D6 (3 test)** `test_stability_repairs`: "Bardak durur." büyük harfli sıradan nesne olarak `UNREGISTERED_NAMED_ENTITY` sayılıyor ("Elara durur." ile ayırt edecek sözlük yok); "Bu şehrin hükümdarı kim?" adı geçmediği için çözülmüyor. Sezgi/sözlük kararı; tahminle değiştirmek yeni yanlış-pozitif üretir.

## 5. Bilinen tuzaklar

- Python ile dosya düzenlerken `\b` kaçışı geri-silme karakterine (0x08) dönüşebilir; düzenleme sonrası `0x08` ve satır sonu taraması yap. `t.index('\nclass ')` ile araya girmek `\r\r\n` üretir.
- GateGuard hook'u ilk düzenleme/silme/yeni dosyada gerekçe ister; yıkıcı bulduğu komutu silmeden yeniden kur.
- WSL `/tmp` yeniden başlatmada silinir; kalıcı ortam `~/ai-dnd-gates`, `~/gates-venv`.
- NPC lore iddiası artık **atıf**tır (Faz 5/K4); "desteksiz lore reddedilir" koruması NPC konuşması için kalktı. Tekrar eden NPC cevabı korunur (`c48df86`).

## 6. Sonraki oturumun işi

1. Sahipten D4, D5, D6'yı iste (her biri için §4'teki ayrımı sun). Cevap gelmeden ilgili testleri değiştirme.
2. D5 cevabına göre ya çağrı bütçesini ya da 8 testin sözleşmesini düzelt; sonra tam suite'i koş: `python -m unittest $(ls api/tests/test_*.py | sed 's#/#.#g;s#\.py$##')` (≈18 dk, arka planda).
3. OH1-05 zincirini canlıda iki temiz kampanyada göster; B/barmen için ≥5 ek koşu.
4. 33 kapıyı mümkünse Python 3.13'te koş.
5. P6 için sahibin okuyacağı kısa paket hazırla (3 canlı oturum özeti + açık kusurlar). PASS yazma.
