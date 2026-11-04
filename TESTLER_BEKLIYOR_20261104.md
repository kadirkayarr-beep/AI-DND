# Yapılacak testler (Kadir / Jarvis koşturur) — 2026-11-04

Kadir kararı (2026-11-04): "Kodlamayı bitir, testleri bekleme." Ajanlar yalnız kendi görevlerinin odaklı testlerini (kırmızı/yeşil) koşar; uzun kontroller bu listeye yazılır ve sonra koşulur. **Buradaki hiçbir kontrol henüz koşulmadı; "geçti" demek yok.** Sıfır tolerans alanları (para, kayıt, Geri Al) bu yüzden sonda MUTLAKA koşulmalı: bir şey kırıksa en son yazılan göreve bakılır (commit listesi `git log`).

## Nasıl koşulur
- Python: Git Bash'ten `bash C:\Users\Kadir\Desktop\AI-DND-TOOLS\slot.sh <yuva> <klasör> test|par ...` (Jarvis için: yalnız `AI-DND-jarvis-test`, yuva 1, `NOSTAGE=1`, kural `AI-DND-ORTAK\KURALLAR.md`).
- Sonuç satırları: kaç test, kaç atlanan, kaç kırık. Kırıksa test adlarını Claude'a ver.
- Sıra: önce küçük gruplar (MONEY), sonra tam paket, sonra yolculuk senaryoları, sonra tarayıcı, en son gerçek zincir (para harcar, yalnız Kadir "yap" derse).

## Dilim bazında genel kapılar (ajanlar atladı; komutlar Dilim planlarında)
- **Dilim 1** (`AI-DND-dilim1`, yuva 2): Görev 1'deki ölçümle karşılaştır (başlangıç: MONEY 422 test OK; tam paket 7866 test, 166 atlanan, 0 kırık; yolculuk 14 geçti, 18 bilinen kırık, 0 yeni kırık). Ara kapılar (Görev 13, 16, 19), Görev 22 (bütün dal doğrulaması, bağımsız inceleme, gerçek zincir kısa kontrolü `--max-calls 100`).
- **Dilim 0** (`AI-DND-dilim0`, yuva 3): Görev 12 (ara kapı), 13 (tarayıcı doğrulaması, ayrı portlar 8018/22795, geçici kayıt, yerel Gemma/Ollama), 14 (bütün dal doğrulaması).
- **Dilim 2** (başlamadı; plan `DILIM2_PLAN_20261104.md`): aynı türde kapılar.

## Ajanların eklediği satırlar (görev görev)
- [ ] Dilim 1 Görev 9: para güvenliği takımı (MONEY) bahşişli tezgâh değişikliğinden sonra temiz mi: "OK", yolculuklarda 0 yeni kırık, 02 ve 25 işaretsiz geçer, test_shop_quote_http ve test_shop_trade_http içindeki bahşişsiz teklifte "bira 1 0 5" reddi (price_changed) yeşil kalır — komut: cd /c/Users/Kadir/Desktop/AI-DND-dilim1 && bash /c/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh 2 AI-DND-dilim1 test D1T9MONEY 1800 api.tests.test_counter_tip api.tests.test_economic_action_http api.tests.test_economic_resolution api.tests.test_economic_receipt api.tests.test_economic_undo api.tests.test_economic_offer api.tests.test_economic_dialogue api.tests.test_economic_room api.tests.test_economic_bribe api.tests.test_coin_writers api.tests.test_shop_trade api.tests.test_shop_trade_http api.tests.test_shop_quote_http api.tests.test_shop_counter api.tests.test_carius_fifth_play api.tests.test_world_keeps_its_word api.tests.test_said_is_real api.tests.test_journeys

## ÖNEMLİ NOT (2026-11-05, J-015/J-016): tam paket nasıl koşulur
İlk bağımsız tam paket koşusu (Jarvis, yuva 1, Dilim 1 Görev 7 sonu) zaman aşımına uğradı ve **geçerli sonuç vermedi**: aynı anda başka yuvalarda da test koşuyordu. Tam paketi (`par`) yalnız **başka hiçbir test koşmuyorken, tek başına** koştur; hiçbir şey çıkarılamayan bir "0 test" satırı başarı değildir. Dilim 0/1 iş akışları açıkken tam paket koşturma.
