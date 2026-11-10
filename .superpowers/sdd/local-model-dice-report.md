# Yerel model: zar kuralı düzeltmesi — rapor

Durum: DONE_WITH_CONCERNS. Dal task/dilim3-world-behaviours-20261109. Push yok.

## 1. Hangi anlatı yolunda motor sonucu var
Yerel 12B'ye giden tek anlatı istemi `game.py` `get_dm_response` (user_prompt). Motor sonucu "PYTHON ACTION RESULT (tek mekanik doğruluk kaynağı)" bölümünde ve "NARRATION FACTS" içinde gider; `action_result` çözülmüş kontrol/saldırı/kurtarma/alışveriş/yolculuk turlarında dolu, saf konuşma ve sade bakış turlarında boş `{}` gider. Yani iki durum da gerçek. Niyet okuma (classifier/front) ve karakter notu çağrıları LOCAL_STYLE_RULES almaz (değişmedi). Zarı her zaman Python atar; model hiçbir yolda zar istemez.

## 2-3. Değişiklik (`ai-dnd/api/ollama_adapter.py`)
- Eski "zar iste ve dur" cümlesi gitti. Yeni kural: "İstemdeki PYTHON ACTION RESULT bölümünde bir sonuç varsa tam olarak o sonucu anlat; başarıyı ya da başarısızlığı değiştirme. Sonuç yoksa kısa anlat; başarı, başarısızlık ya da sayısal sonuç uydurma." Zar atma/isteme anlamı yok.
- LOCAL_DM_EXAMPLE tam olarak istenen metin (başlık ve tırnak yok).

## 4. Testler (`api/tests/test_local_gemma_12b.py`)
Kırmızı önce görüldü (red1: 2 başarısız). Sonra yeşil: g1 = test_local_gemma_12b, test_local_gemma_fast, test_local_model_selection, test_model_chain + komşu set (journey_runner/report/schema/journeys), 337 test, exit 0. Sabit kasaba gerektiren yeni kampanya testi yok.
Yeniden yazılan testler:
1. `test_the_rules_say_what_the_owner_asked`: eski "zar iste ve dur" cümlesi yerine yeni kural cümlesi (tam metin), örnek için `assertIn('zar', ...)` yerine `assertEqual(LOCAL_DM_EXAMPLE, tam metin)`. Eşit sıkı ya da daha sıkı; sınır yeniden tanımlanmadı, kural kasıtlı olarak ters çevrildi (sahip kararı). [GEVŞETME OLABİLİR] işareti: yok, ama onay listesine "kural ters çevrildi" diye girer.
Yeni: `test_the_engine_rolls_so_no_local_prompt_asks_for_a_roll`: kurallar, örnek, tam yerel sistem metni ve motor metni sonrası eklenen kısımda "zar at", "zarını", "zar iste", "roll", "ve dur" yok; örnekte "direniyor" yok.

## 5. Gerçek Ollama (gemma4-12b-dm, num_ctx 12288, num_predict 300, think false)
Ollama erişilebilirdi. Not: istem gerçek motor sistem metni değil kısa bir yedek sistem + gerçek LOCAL_STYLE_RULES + LOCAL_DM_EXAMPLE + gerçek bölüm başlıklarıyla küçültülmüş kullanıcı mesajı. Her durum 3 kez. Hiçbir çıktıda zar istenmedi (anahtar kelime denetimi: 27/27 temiz).

Eylem 1 (kilit açma, örnekle aynı sahne): sonuç var/başarı 3/3 ve sonuç YOK 3/3 çıktı örnek cümlenin birebir kopyası ("Kilidin içine maymuncuğu sokuyorsun. Mekanizma bir kez tıkırdıyor, sonra direnmeden açılıyor. ..."); başarısızlık sonucunda model kopyalamadı: "Maymuncuk metale çarpıp sert bir ses çıkarıyor. ... Kapı açılmıyor."
Eylem 2 (ağır sandık itme), örnek başlıksız (üretimdeki hali):
- başarı sonucu: 3/3 başarı anlatıldı. başarısızlık sonucu: 3/3 başarısızlık ("Sandık yerinden milim bile kıpırdamıyor").
- sonuç yok: 3 çıktının biri başarı, ikisi başarısızlık uydurdu (kural ihlali; model buna güvenilir uymuyor).
Aynı eylem, örnek önünde eski "ÜSLUP ÖRNEĞİ (yalnız üslup için; içeriğini bu sahnede kullanma)" başlığı ile: başarı 3/3, başarısızlık 3/3, sonuç yok 3 çıktının ikisi başarı, biri başarısızlık uydurdu. Başlığın uydurmaya etkisi görülmedi, kopyalamayı azalttığına dair kanıt yok (kopyalama yalnız eylem örnekle aynı sahneyse görüldü).
Örnek çıktılar (UTF-8, ham): "Sandığı güçlü bir şekilde iterken kasların geriliyor. Sandık, büyük bir çaba ve gürültüyle pencerenin altına doğru kayıyor." (başarı sonucu); "Sandık yerinden milim bile oynamıyor. Ağırlığı ve sürtünme kuvveti seni durduruyor." (sonuç yok, başarısızlık uydurma).

## Kontrol listesi
(a) Yerel kurallar tek noktadan (`_cache_friendly`, style=True) tüm yerel anlatı çağrılarına gidiyor; yeni kural bu yolların hepsinde. (b) uygulanmaz: kayıt alanı yok. (c) uygulanmaz: istem sabit metin. (d) Yeni kampanya başlatan test yok. (e) Oyuncuya yalan gerekçe yok; "zar iste" kaldırıldı. (f) Kırmızı önce görüldü; gevşetme yok. (g) uygulanmaz: para/envanter yolu değişmedi.

## Concern
- Ruling: örnekte başlık yok (sahip "tam olarak" dedi) — yanlışsa maliyeti: model aynı sahnede örneği kopyalar (kilit açma turunda görüldü); başlık geri eklemek tek sabit.
- "Sonuç yoksa uydurma" kuralına 12B güvenilir uymuyor (6 denemenin 3'ünde başarı uydurdu); asıl koruma Python'un doğrulaması, kural yalnız eğilim verir.
- `game.py` ~5834 oyuncuya gösterilen ölüm-kurtarma metninde "zarını at" var; yerel model istemi değil, bu işin kapsamı dışı; sahibin oyun kuralına uyup uymadığına bakılmalı (park).
