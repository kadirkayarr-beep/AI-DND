# Oyunun geleceği: bağımsız görüş (Fable, 2026-10-31)

Salt okunur inceleme. Okunan kod `AI-DND-c-merge/ai-dnd` @ `fe4e34e`; oyun kaydı `%LOCALAPPDATA%\AI-DND\local-play.sqlite3` (30 tur, Carius). Hiçbir şey çalıştırılmadı, test koşulmadı. "Doğrulandı" = koddan/kayıttan sayıldı; "çıkarım" = benim yorumum.

## 0. Tek cümle

Oyun durmuyor çünkü Python modeli engelliyor; duruyor çünkü **ne Python'un ne modelin kente dair söyleyecek verisi var**. Sahibin 30 turunda iş/kent/olay sorduğu 10 turun 9'u modele gitti ve model, promptun dediği gibi ("bilmiyorsan bilmediğini söyle"), bilmediğini söyledi. Bu veri sorunu; yönlendirme sorunu ikincil. Önce dünya verisi, sonra mimari.

## 1. Eğlence ve 30 dakikalık hedef

**Eğlenceyi veren üç şey** (sahibin tarifinden, `OYUN_TARIFI_KADIR`): (a) söylenen her yer/kişi gerçek ve gidilebilir; (b) insanlar birbirini ve kentini biliyor, herkes yardım etmiyor; (c) kararın bir sonraki turda görünür sonucu var. Zar, sınıf özellikleri, ekipman ekonomisi bu listeye girmiyor; sahibin oyununda hiçbiri kullanılmadı (30 turda 0 savaş, 1 zar).

**Ölçülebilir 30 dakika hedefi** (sahip oynar, kayıt `campaign_history`'den sayılır, ~40 tur):
- ≥ 3 **gerçek ip** duyulur (NPC'nin söylediği yer/kişi/iş kayıtta `world_threads`/yer kaydı olarak var).
- ≥ 2 **yere varış** NPC'nin söylediği ada göre ("oraya gidiyorum" dahil).
- ≥ 1 **sonuçlu karar**: kabul/ret/ihanet sonrası dünyada değişen tek satır (iş gitti, kapı açıldı, biri soğudu).
- **Kelimesi kelimesine tekrar ≤ 1**, "bilmiyorum/tanımam" türü kapalı cevap ≤ %20.
- "Hangisini kastediyorsun" ve 409/503 = 0.
- Sahip kendi cümlesiyle "merak ediyorum, ilerleyebiliyorum" der. Bu olmadan diğerleri sayılmaz.

## 2. Mimari: "model önerir, Python doğrular ve işler" iddiası

**Doğrulanan sayılar**
- `_dispatch_player_turn` (`game.py:17105-17330`): anlatım boru hattından **önce 18 ayrı sahip** sırayla turu kapmaya çalışıyor (sahip modülü, konuşma bitirme, saldırı sorusu, `dialogue_runtime`, envanter, sığınak, sahne, `grounded_action`, yerel yer, günlük eylem, keşif, zindan, ekipman, büyü, sınırlı karşılaşma, canavar, aksiyon ekonomisi, ikinci `grounded_action`).
- Motor kodunda **920 sabit Türkçe anlatım satırı** (`game.py` 306, `grounded_action.py` 152, `local_places` 40, `local_dialogue` 39, `living_world` 32, `interaction_adventure` 30). `"model_calls": 0` ile biten 18 açık dönüş noktası.
- `game.py` 21.013 satır; motor toplamı ~102k satır Python; test 154k satır, 3.793 test fonksiyonu. Son 30 günde 874 commit.
- Sahibin 30 turu: **~18 tur modele ulaştı** (17 `experimental_attributed_speech` + 3 model anlatımı, biri karışık), **~12 tur saf Python** (isim, han bulma, konuşmayı bitirme, yere gitme, "memnun oldum", `proposal_rejected`, çevre gözlemi). İki tur boş anlatımla kaydedilmiş (32 action / 30 history): sessiz hata.
- Çıkmaz cevaplar ("Dinlenmeye uğradım sadece", "Ben sadece barmenlik yaparım", "Böyle birini tanımam", "Ne söyleyeyim…") **kaynak kodda yok** → model üretti. Prompt (`game.py:8092-8096`) açıkça "bildiğin iş/yer varsa söyle, yoksa bilmediğini söyle" diyor ve bağlama tek kamu bilgisi girmiyor. Tek Python çıkmazı: `interaction_adventure.py:984` "Bu konuda bir şey bilmiyorum, yabancı" (tur 25).
- Model yolu: `gemma4:e4b`, `num_ctx` 8192, tur başına ≤ 2 çağrı, 90 sn zaman aşımı; konuşma `num_predict` 220, anlatım 700. 20 tur ölçümünde en büyük istem 4.608 token, anlatım ~4 sn.

**Hüküm:** İddia **yarı doğru**. 20 tur ölçümündeki 8 "hangisini kastediyorsun" duvarı Python'dur ve sabah raporuna göre düşürülmüş. Sahibin oyununu durduran duvar ise modelin veri yoksunluğudur. Her yeni özel durum (Evet-soyma, "oraya", tür kökü eşleşmesi) 920 satırlık sabit metin katmanına yeni satır ekliyor; bu katman modelin yerine geçmeye çalışıyor ve "Gözüne Ahşap masa çarpıyor" gibi kuru çıktılar üretiyor. **Çıkarım:** 18 sahipli zincir her yeni istekte "hangi sahip önce" sorusuna dönüyor; özel durumların kaynağı bu sıra.

**8 GB'de Gemma 4 e4b ne taşıyabilir** (çıkarım, ölçüm değil; kanıt: sahibin oyunundaki model satırları okunabilir, tutarlı, tekrar az):
- Taşıyabilir: verilen ≤ 5 satırlık olguyu NPC sesiyle söyleme; verilen sonucu anlatma; 1 sayfalık sahne betimleme; "oyuncu neyi kastetti" için **listeden seçme** (aday id'leri verilip biri seçtirilince).
- Taşıyamaz (güvenle): dünya durumu uydurup tutarlı tutma, uzun JSON şema, kural hakemliği, 8 turdan uzun bellek, ne yapacağına kendi karar verme. Zar ve durum Python'da kalmalı; bu kısım doğru kurulmuş.

**Öneri: yeni çekirdek değil, kademeli oyma.** Yeniden yazım 100k satır + 154k test karşısında aylar alır ve sahibin hiç oynamadığı özellikleri yeniden üretir. Yapılacak şey: zinciri **üç sahibe** indirmek — (1) Python tam kesin eşleşmeler (bitir, git X'e, envanter, savaş komutu), (2) **tek "niyet + aday" çağrısı**: model `{hedef_id, eylem_türü}` seçer, Python kendi listesinden doğrular, uygulamayı Python yapar, (3) anlatım/konuşma çağrısı. `grounded_action.resolve_turn(phase="fallback")` zaten buna yakın (`game.py:17298-17308`); onu başa almak, 920 satırın yarısını dondurmak yeter. Mevcut 2 çağrı tavanı korunur.

## 3. Yerel mi, bulut mu? 25 USD/ay

**Ölçülebilen:** sahip 21 dakikada 30 tur oynadı (≈1,4 tur/dk). Günde 1 saat → ~80 tur, ayda ~2.400 tur. İstem ≤ 5k token, çıktı ~300. Fiyatlar Anthropic listesi (bu oturumdaki `claude-api` becerisi, 2026-10-06 önbelleği; canlı doğrulanmadı):

| Model | Tur başı (1 çağrı, önbelleksiz) | 2.400 tur/ay | 2 çağrı/tur |
|---|---|---|---|
| Haiku 5.5 ($0.10/$0.50) | $0,00065 | **$1,6** | $3,1 |
| Sonnet 5.5 ($2/$10) | $0,013 | $31 | $62 |
| Sonnet 5.5 + prompt cache (3k sabit önek, ~0,1×) | $0,0076 | **$18** | $37 |
| Opus 5.5 ($4/$20) | $0,026 | $62 | $125 |

**Hüküm:** 25 USD, **Haiku 5.5'i rahat, Sonnet 5.5'i yalnızca tek çağrı + önbellekle** karşılar. Bu, yerelin yerini alması için değil, **ölçüm için** kullanılmalı: aynı 20 turu Gemma ve Haiku ile koşup sahibin okumasıyla hangi işin modelden, hangisinin veriden kaynaklandığını ayırmak. Yerel zayıfsa bulut da aynı boş bağlamla "bilmiyorum" der. **Yerel yeter mi?** Sahibin barı için bence yetmez tek yerde: uzun, kişilikli, tekrar etmeyen konuşma. Orada Haiku/Sonnet görünür fark yaratır; ama bunu ölçmeden söylemek çıkarımdır.

**Kontrol edemediklerim:** güncel fiyatlar; Gemma'nın Türkçe token oranı (bayt/2 tahmini); diğer sağlayıcıların fiyatı; ağ gecikmesi; bulut çağrısında 8192 dışına çıkınca bağlam kırpıcısının (`_fit_context_packet`, 4800 bayt) davranışı.

## 4. Silinecek / dondurulacak

- **Dondur:** sınıf özellikleri (6 sınıf var; sahip Fighter oynuyor, 30 turda 0 savaş), Hit Dice/koşullar/kaynak bütçesi dalı (`task/b01` son 5 commit'in tamamı K07 kural kanıtı), büyü/sorcery, yoldaşlar, Neverwinter canon paketi ve `incidents/emergence` (model çağrısı harcıyor, kapalı). Yeni kural işi **oyun testi geçene kadar yok**.
- **Dondur:** test üretimi. 154k satır test / 102k satır motor; `run_tests` 5.256 test. Reddedilen davranışı sabitleyen testler sabah raporunda zaten değiştirildi; yeni testler yalnız §1 hedefini ölçen 20/30-tur koşusu ve kayıt uyumu için.
- **Dondur:** UI işi (6.751 satır tsx). Sahibin gördüğü 3 UI hatası (seviye düğmesi, "Hamle yap", 15/15 HP) yarım gün; ötesi yok.
- **Sil veya kapat:** `AMBİENT "DİKKATİNİ ÇEKEN"` kartı (tıklayınca "Karşılaşma ilerledi", hiçbir şey olmuyor); `free_v1` ile `legacy` ikiliği — **tek yol**, ölçümle seçilir (sabah planı legacy diyor; katılıyorum, ama 60 gün içinde biri silinmeli); `docs/evidence` ve `reports` altındaki ~120 dosyalık eski koşu kayıtları depodan (gitignore) çıkar.
- **Silme:** zar, durum, kayıt/geri alma, 2 çağrı tavanı, serializer allowlist. Bunlar iyi.

## 5. Yol haritası ve kapılar

| # | Adım | Geçiş kanıtı | Durdurup yön değiştiren sonuç |
|---|---|---|---|
| 0 | **Kilit ve sessiz hata.** 409/503 döngüsü (sabah raporu #1) + boş anlatımlı 2 turun nedeni | 50 tur, 0 boş/409 | Kök neden 2 günde bulunmazsa: model çağrısını tur dışına al (tolere faz), tur Python sonucuyla commit olsun |
| 1 | **Kent bilgisi + ipler + işaret** (`OYNANACAK_SEY_PLAN` T0–T3, modelsiz) | Carius 3 kişiye sorar, ≥ 1 gerçek yere yönlendirilir; "oraya gidiyorum" varır; kayıt yükle/kaydet eşit | Model verilen 5 satırı görmezden geliyorsa (3 denemede 0 yönlendirme): Python yedek satırı açık, ve §3 ölçümü hemen |
| 2 | **Sahip 30 dk oynar** (§1 hedefi) | 6 ölçütten ≥ 4 + sahibin cümlesi | "İlerleyemiyorum" yine geliyorsa: nedeni veri mi ses mi — aynı 20 turu Haiku ile tekrarla (≈ $0,02) |
| 3 | **Kabul/ret/doldurma** (T4–T5): dünya oyuncusuz hareket eder | Reddet, 1 gün bekle, iş gitmiş; teslimat tamamlanır | Yanlış pozitif kabul > 1/20 ise bağlama yalnız sahibiyle ve tek cümleyle |
| 4 | **Zinciri oyma:** 18 sahip → 3; `grounded_action` fallback başa; 920 satırın yarısı `legacy_debug`'a | 20 tur: "hangisini kastediyorsun" 0, sabit metin ≤ %30 tur | Niyet çağrısı yanlış hedef > %10 ise: aday listesi daraltılır, model değil Python sorar |
| 5 | **Model kararı:** aynı 30 tur Gemma e4b / qwen3.5 9b / Haiku 5.5 | Sahip kör okur, puanlar | Yerel ≥ Haiku'nun %80'i ise yerel kalır; değilse Haiku varsayılan, yerel çevrimdışı yedek |
| 6 | **Defter + compact bellek** (`DEFTER_YASAYAN_DUNYA` A) | "Hancı ne söz vermişti?" doğru | Bütçe 7.500 token'ı aşarsa defter 600 bayta |
| 7 | İkinci 30 dk oyun, sonra sınıf/kural dondurması kalkar | §1 hedefi 2 kez üst üste | Geçmezse 1–4 tekrar; yeni özellik yok |

**Sıra gerekçesi:** 0 ve 1 bir hafta; 2 sahibin eli. 3–4 iki hafta. 5 tek gün ama 2'nin sonucu olmadan anlamsız. Bu plan `OYNANACAK_SEY_PLAN` ile uyumlu, onu önceler; `DEFTER` planının B kısmı (ajanda) 3'e, A kısmı 6'ya katlanır; iki anahtar (`world_threads_v1`, `npc_agenda_v1`) birlikte yaşamaz.

## 6. Açık söylemem gerekenler

- Bu belgenin en zayıf yeri modelin kapasitesine dair hükümlerim: kanıt 30 tur + 20 tur, tek model, tek dil. Adım 5 bunu kapatır.
- "Yeni çekirdek" önermememin nedeni teknik değil, ekonomik: 874 commit/ay hızında yeniden yazım, bugünkü sorunların (veri yok) hiçbirini kendiliğinden çözmez.
- Sahibin kararı gereken tek şey: 25 USD'yi **ölçüm** için harcamaya razı mı (adım 2 ve 5), yoksa yerel-only mu. İkincisi de oynanabilir; yalnız konuşma uzunluğu ve kişilik tavanı daha erken gelir.
