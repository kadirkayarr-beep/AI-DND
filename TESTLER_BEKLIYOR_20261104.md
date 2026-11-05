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

- [ ] Dilim 0 Görev 6 (Jarvis, J-019): NODE tam kontrolü bekliyor: bash /c/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh 3 AI-DND-dilim0 node. Odaklı web RED yolu mevcut değil; görev tamamlanmadı. Tarayıcı: plandaki BROWSER ile kabul edilen kasaba işi, Süren görevler 1 / rozet 01 / boş mesaj yok kontrolü bekliyor.

- [ ] Dilim 1 Görev 12 (f77df47c, J-020): genel test_journeys otomatik incelemede geniş koşu olarak reddedildi; koşulmadı. Yetkili uzun kontrol aşamasında: bash /c/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh 2 AI-DND-dilim1 test D1T12JOURNEYS 900 api.tests.test_journeys. 03 adım 4 ve 26 tüm adımlar odaklı test_truth_card içinde geçti.
- [ ] Dilim 1 Görev 12: plan Step 4 kalan regresyonları ve MONEY bekliyor: test_narrative_memory, test_lasting_consequences, test_f04_frozen_d06_restart, test_f04_n08_api_resume_context, test_f04_n08_process_restart, test_phase7_package ve planın MONEY listesi; komut DILIM1_PLAN_20261104.md Task 12 Step 4 (RUN D1T12 1800 ...). Claude bağımsız incelemesi bekliyor; 46 odaklı test tam paket kanıtı değildir.

- [ ] Dilim 1 Görev 14 (9b657b87, J-021): MONEY ve genel yolculuk kapısı bekliyor. Yetkili uzun kontrol aşamasında plan Task 14 Step 4 MONEY listesi; genel yolculuk komutu: bash /c/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh 2 AI-DND-dilim1 test D1T14JOURNEYS 900 api.tests.test_journeys. 04b/28 yalnız test_item_use içinde sahte modelle geçti. 104 ve 63 odaklı test koşuları tam paket değildir. Claude bağımsız incelemesi bekliyor.

- Jarvis Görev 15 (8aedb6dc): MONEY/genel yolculuk/tam paket/tarayıcı ve 04b yeni gerçek-zincir ok yönlendirme adımı bekliyor; yalnız odaklı FINAL 327 ve FEATURES 258 test geçti (J-022). Gerçek model koşusu yapılmadı.

- [ ] Dilim 1 Görev 11 (J-023): başlamadı; yuva 2 için izinli odaklı web RED/GREEN yolu yok. Planın slot.sh 3 AI-DND-dilim1 node komutu son yuva kuralına aykırı ve tam web paketi çalıştırıyor; KOŞULMADI. Odaklı yol sağlanınca test_counter_reports_the_held_tip_only_while_it_is_valid ve panel shows the tip and confirms the total with it birlikte doğrulanmalı. MONEY/contract_parity ve tam web kapısı yetkili sonraki aşamada kalır.

- [ ] Dilim 0 Görev 6–10 ve 11 UI (J-024): yuva 3'te odaklı web RED/GREEN yolu yok; tam node/tsc ve tarayıcı bekliyor. Görev 11 katalog alt parçasının Python doğrulaması tamam: 25850a09, 155 test OK; bu sonuç web/bütün görev kabulü değildir.

- [ ] Dilim 1 Görev 10 (09ef524, J-026): odaklı 45 testte 2 satın alma-kartı ret testi FAIL. Önce economic_actions kapsam kararı ve TDD düzeltmesi; ardından Task 10 Step 4 tam MONEY kapısı uygun yetki/boş bilgisayarda. 17'nin altı adımı odaklı geçti; genel paket başarısı yok. İNCELEME BEKLİYOR (sıfır tolerans).

- Jarvis Görev 17 (9f5c6a4, J-027): uzun MONEY/tam paket/web/gerçek zincir koşulmadı; Görev 21 kayıt-Geri Al kanıtları ve bağımsız inceleme bekliyor. Odaklı altı modül koşuldu: 133 test/4 taban FAIL. Görev 10 şema/istem düzeltmesi sonrası aynı JVD1T17FOCUS modülleri yeniden koşulmalı; 17 yeni hafıza testi FINAL2 OK.

- Jarvis Görev 18 (4d3d269, J-028): iki ret senaryosu kırık; plandaki mevcut korumayı koruma şartıyla çelişki çözülmeli. 24/24r senaryoları yazılmadı; genel journeys/MONEY/tam paket/web/gerçek zincir koşulmadı. Altı odaklı modül 132 test/6 FAIL; dört continuity hatası tabandan, test_5 OK. Bağımsız inceleme bekliyor.

- 93b739e8: purchase decline repair; 138 focused OK; full MONEY and independent zero-tolerance review pending (J-029).

- 449e6975: two recall failures fixed; four known continuity schema/prompt failures, scenarios 24/24r, long gates and independent review pending. J-030.

- J-032: four continuity failures closed; 24/24r files created; real 24 step12 + all four 24r steps still unrun; long gates/review pending.

- J-033 Task20: 201 focused OK; full MONEY/gateD,11/12/25 journeys and independent zero-tolerance review pending.

- Görev 21 / 8f3fad79: tam MONEY, bütün dal ve gerçek süreç restart kapıları + bağımsız sıfır tolerans incelemesi bekliyor; 149 ilgili kayıt testi geçti (J-034), bunlar genel kabul değildir.

- J-037: açık ürün-sözleşme kararı ve kırmızı UnrelatedSocialCheck; a22ce75c son seçim129/1FAIL, tam MONEY geçmedi. J-038/039 teknik düzeltmeleri bağımsız inceleme bekler; uzun/gerçek kapılar değişmedi.
