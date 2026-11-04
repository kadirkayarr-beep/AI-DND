# Dilim 1, kişisel hafıza: salt-okuma araştırma sonucu (2026-11-04)

Kaynak: üç salt-okuma ajanı (workflow wf_a547af3a-ef1), `AI-DND-c-merge` (3c733c57) kodu. Hiçbir şey çalıştırılmadı, model çağrılmadı. Kesinlik düzeyleri parantezde. Madde 116 / T16 (kişisel hafıza kaybı) için.

## Kök neden (orta-yüksek)
1. **Oyuncunun söylediği kişisel bilgiyi (kardeş adı, hediye) hiçbir yer GERÇEK OLARAK saklamıyor.** Sıradan model-konuşma yolunda ("experimental attributed speech") yalnız şunlar yazılır: `npc_speech_log` (kişi başına son 4 konuşma), `npc_statements` (NPC'nin KENDİ sözleri; oyuncu satırı `player` alanında durur ama geri okuyan kod yok) ve API katmanı `narrative_memory.npc_interactions` (20 satır, konuşma istemine girmez). `npc["memory"]` bu yolda YAZILMAZ (`game.py:14704-14713`). Oyuncunun adı ayrıdır: ayrı kod ("Benim adım X.") `npc["memory"]`'ye yazar, bu yüzden isim kalıyor, kardeş adı ve hediye kalmıyor.
2. **Hatırlama sorusu belirlenimci bir inkâra gidiyor.** "hatırlıyor musun", "söylemiştim" gibi cümleler `is_npc_historical_claim` (regex, `game.py:1143-1164`) ile "tarihî iddia" sayılır; dayanak yoksa `_CLAIM_DENIAL_LINES[0]` ("Öyle bir şey konuştuğumuzu anımsamıyorum. Beni başka biriyle karıştırmış olmalısın.", `game.py:7006-7008`) Python tarafından yazılır; model uyum gösterse bile cevap bununla değiştirilir (`game.py:21713-21746`). `claim_support` yalnız NPC'nin kendi sözlerine bakar (`npc_statements.py:678-727`).
3. **Kaydet-yenile bağımsız neden DEĞİL:** hepsi `world_state` içinde ve kaydediliyor; yenileme yalnız pencerenin zaten boşaldığını gösteriyor.
4. Ek: pencere sayıları: konuşma istemine giren `conversation_so_far` son 4, `recent_player_utterances` son 4, `perspective` son 6; `npc["memory"]` 16 giriş (8 konuşma); `narrative_memory.npc_interactions` 20 (söz/vaat kalıbı eşleşmeyen "orta önem" satırlar ~20 satır sonra atılır; "20+ tur" gözlemiyle uyumlu).
5. Tasarım belgelerinde (DEFTER, YAŞAYAN DÜNYA, LIVING_WORLD_MAP) oyuncunun NPC'ye söylediği bilginin saklanması YOK; NPC'nin söyledikleri tutuluyor. Eksik parça: "oyuncunun bu NPC'ye ne açtığı" için motor sahipli kayıt.

## Doğrulanmayan
- Hangi yolun inkârı ürettiği (Python dalı mı, konuşma yolu yedeği mi) sahibinin kaydında yok; `AI_DND_SPEECH_DEBUG` izi ya da kaydedilmiş kampanyadaki `npc_speech_log` bakılırsa netleşir.
- `narrative_memory` test_5 kararsızlığının nedeni bulunamadı.
- `free_v1` konuşma kipi açıksa inkâr yolu farklıdır (varsayılan `legacy`).

## Test için bulgular (Adım 2 düzeneği)
- Bugün çalıştırıcı bu yolu gözleyemez: `read_observed`'da `npc_speech_log`, `npc_statements`, `npc["memory"]` anahtarı yok; `NarratorInput` yalnız "narration" çağrılarını tutar, "speech" çağrısını tutmaz (`anlaticiya_giden` konuşma turlarında None).
- En küçük senaryo (kesinlik orta): `front_proposal: true`, tek NPC; adım 1 kişisel bilgi (`speak_to` ön okuma + `spoken`); 5 aynı-NPC dolgu konuşması (pencereyi taşırır); `reload` adımı (yalnız gözlemi karşılaştırır, canlı oturum sürer); hatırlama adımı. `expect`: `yasak_metin` ["anımsamıyorum", "karıştırmış"] ve yeni anahtarlar: kayıt anahtarı (`npc_sozleri`) + konuşma girdisi anahtarı (`konusmaya_giden`). `EXPECT_KEYS` kümesi `test_journey_schema.py`'de sabitli; anahtar eklenince güncellenmeli.
- Sahte model "NPC'nin gerçekten SÖYLEDİĞİNİ" kanıtlayamaz, yalnız motorun doğru bilgiyi modele sunduğunu ve inkâr satırının yazılmadığını kanıtlar.

## Önerilen yön (Dilim 1 tasarımına girdi; taslak)
- Motor sahipli, sınırlı bir "oyuncunun bu NPC'ye söyledikleri" kaydı (kişi başına ayrı, kendi üst sınırıyla, 4'lü pencereden bağımsız), kayıtla birlikte saklanır ve doğrulanır.
- Kayıt "model önerir, Python doğrular, saklar" ilkesiyle dolar (kelime listesi yok): kişinin orada olması, uzunluk sınırı, savaş dışı, gizli bilgi yok.
- Hatırlama iddiası bu kayıtla DESTEKLENEBİLİR olmalı (belirlenimci inkâr yalnız kayıtta olmayan uydurma iddia için kalır; `narrative_memory` test_5'in "Elaris bana ejderha hazinesinden bahsetmişti" uydurması hâlâ inkâr edilir).
- İstem tarafı: ilgili kayıtları (söz örtüşmesi) en çok 3 satır olarak konuşma bağlamına koy.
