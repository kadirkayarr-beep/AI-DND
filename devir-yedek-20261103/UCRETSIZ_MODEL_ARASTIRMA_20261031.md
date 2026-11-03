# Ücretsiz Bulut LLM Araştırması: Türkçe Metin RPG

Tarih: 2026-10-31. Aşağıdaki tüm kaynaklara erişim tarihi 2026-10-31'dir. Hiçbir servise kayıt olunmadı, anahtar alınmadı, canlı çağrı yapılmadı.

## 1. Kısa sonuç

- **Oturumu sığdıran gerçekten ücretsiz seçenekler az.** Sayıları tutan iki aday var: Gemini 3.5 Flash-Lite ve Cloudflare üzerinden GLM-4.7-Flash. Mistral üçüncü aday, ama sayıları hesap paneli olmadan doğrulanamadı.
- **Groq düz okumada uygun görünür, oturumu taşımaz.** Limit tablosu izleyicideki değerlerle aynı, ama 200K TPD, 1,4 çağrı/dakikada yaklaşık 25-39 dakikada biter.
- **Hiçbir ücretsiz modelin Türkçe RPG kalitesi kanıtlı değil.** Kota sığması kaliteyi göstermez; karar ancak aynı turlarla yapılacak testle verilebilir.
- **Claude Haiku 5.5 fiyatı doğru:** girdi $0,10, çıktı $0,50 / milyon token. Bu kullanımda ayda yaklaşık $1-4 tutar.
- **Önbellek bu oyunda ayda yaklaşık 32 sent kazandırır** (%30). Faydalı, ama kararı değiştirecek büyüklükte değil.

## 2. Yöntem ve güven düzeyi

- **[DOĞRULANDI]:** resmi sayfadan okundu.
- **[İKİNCİL]:** yalnızca üçüncü taraf kaynakta var; resmi teyit yok.
- **[ÇIKARIM]:** benim hesabım veya yorumum.
- **[OKUNAMADI]:** sayfa açılmadı ya da bilgi içermiyordu.

Çoğu sayfa, özet üreten bir araçla okundu. Groq limit tablosu ve OpenRouter model/veri politikası bilgileri ham veriden ayrıca kontrol edildi. Groq'ta özet aracının yorumu yanlış çıktı, ham HTML ile düzeltildi (bölüm 5).

## 3. Kullanım hesabı [ÇIKARIM]

Tek çağrı için iki boyut alındı: tipik 3.700 token (3.500 girdi + 200 çıktı), üst sınır 5.700 token (5.000 + 700).

| Ölçü | Tur başına 1 çağrı | Tur başına 2 çağrı |
|---|---|---|
| Çağrı/dakika | 1,4 | 2,8 |
| Token/dakika, tipik - üst | 5.180 - 7.980 | 10.360 - 15.960 |
| 1 saatlik oturum, çağrı | 84 | 168 |
| 2 saatlik oturum, çağrı | 168 | 336 |
| 1 saatlik oturum, token | 311K - 479K | 622K - 958K |
| 2 saatlik oturum, token | 622K - 958K | 1,24M - 1,92M |
| Ayda (2.400 tur), çağrı | 2.400 | 4.800 |
| Ayda, token | 8,9M - 13,7M | 17,8M - 27,4M |

Yeniden deneme çağrıları bu tabloya dahil değildir. Geçersiz JSON onarımları gerçek kullanımı artırır.

## 4. Sağlayıcı özeti

"Sığar mı" sütunu benim hesabımdır. Limitlerin kaynağı bölüm 5'tedir.

| Sağlayıcı / model | Durum | Ana limit | 1-2 saat sığar mı | Kart | Eğitim / inceleme |
|---|---|---|---|---|---|
| Gemini 3.5 Flash-Lite | Süresi belirtilmemiş ücretsiz katman | 10 RPM, 250K TPM, 500 RPD [İKİNCİL] | **Evet**, 2 çağrıyla bile (336 < 500) | Sayfada yazmıyor | **Evet, insan incelemesi dahil** |
| Gemini 3.8 / 3.6 Flash | Ücretsiz katman | 5 RPM, 20 RPD [İKİNCİL] | **Hayır**, yaklaşık 14 dakika | Sayfada yazmıyor | **Evet** |
| Cloudflare GLM-4.7-Flash | Günlük yenilenen kota | 10.000 neuron/gün, 300 RPM | **Evet, 1 çağrıyla**; 2 çağrı + üst boyutta hayır | Sayfada yazmıyor | Hayır |
| Z.ai GLM-4.7-Flash | Ücretsiz model | Sayısı bulunamadı | **Bilinmiyor** | Bilinmiyor | API'de açık onay olmadan hayır |
| Mistral Free / Experiment | Değerlendirme amaçlı | Hesap panelinde; ~1 RPS, 1B/ay [İKİNCİL, çelişkili] | **Muhtemelen**, doğrulanmadı | Gerekmiyor | Muhtemelen evet [İKİNCİL] |
| Groq gpt-oss-120b, qwen3.8 | Ücretsiz plan | 30 RPM, 8K TPM, 1K RPD, 200K TPD | **Hayır**, 25-39 dakika | Sayfada yazmıyor | Varsayılan saklama yok |
| OpenRouter `:free` | Kalıcı ama değişken liste | 20 RPM, 50 RPD | **Hayır**, 18-36 dakika | Gerekmiyor [İKİNCİL] | Modele göre değişir |
| NVIDIA NIM | Deneme | 40 RPM [İKİNCİL] | Hız olarak evet, şart olarak **hayır** | Bilinmiyor | **Evet** |
| Cerebras | Tek seferlik $5, 30 gün | 5 RPM, 1M TPD | Kısa süre evet, kalıcı **hayır** | **Gerekli** | Politika net değil |
| SambaNova | Ücretsiz katman | 20 RPD | **Hayır**, yaklaşık 14 dakika | Ödeme yöntemi eklenirse katman değişir | Okunamadı |
| Cohere trial | Değerlendirme anahtarı | 20 RPM, 1.000 çağrı/ay | **Hayır**, ayı taşımaz | Bilinmiyor | Şartlara bakın |
| Vercel AI Gateway | Aylık $5 kredi | Model bazlı, sayı yok | Model seçimine bağlı | Bilinmiyor | Modele göre |
| GitHub Models | **Kapandı** | - | Hayır | - | - |
| Hugging Face | Ücretsiz kredi yok | - | Hayır | Satın alma gerekir | - |
| Together | Ücretsiz deneme yok | En az $15 alım | Hayır | Gerekli | - |
| Ollama Cloud | Ücretsiz değil, token başına ödeme | - | Hayır | Bilinmiyor | Hayır |
| Alibaba Model Studio | 90 günlük kota | Model başına ~1M token | Kalıcı değil | Yazmıyor | Okunmadı |

## 5. Sağlayıcı ayrıntıları

### Google AI Studio / Gemini API

**Doğrulandı:**
- Ücretsiz katmanda şunlar var: Gemini 3.8 Flash, 3.6 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite, 3 Flash Preview, 2.5 Pro/Flash/Flash-Lite ve Gemma 4. Tüm satırlarda ücretsiz katman için "ürün iyileştirmede kullanılır: Evet", ücretli için "Hayır" yazıyor ([pricing](https://ai.google.dev/gemini-api/docs/pricing), güncelleme 2026-10-30).
- Limitler proje başınadır. Resmi sayfa model bazlı ücretsiz sayıları **göstermiyor**, AI Studio'ya yönlendiriyor ([rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits), güncelleme 2026-10-28; Almanca sürüm de aynı).
- 2.5 modelleri yalnızca daha önce kullananlara açık. Yeni projeler için 3.5 Flash-Lite veya 3.8 Flash öneriliyor. 3.5 Flash-Lite için kapanış tarihi yok; 3.1 Flash-Lite en erken 2027-05-07'de kapanabilir ([deprecations](https://ai.google.dev/gemini-api/docs/deprecations)).
- Ücretsiz katman için süre sonu yazmıyor, kart gereği de belirtilmiyor. Ücretli katman faturalama ve ön ödeme ister ([billing](https://ai.google.dev/gemini-api/docs/billing)).
- Türkiye desteklenen bölgeler listesinde ([regions](https://ai.google.dev/gemini-api/docs/available-regions)).

**Şartlar [DOĞRULANDI]** ([terms](https://ai.google.dev/gemini-api/terms)):
- Google ücretsiz katman içeriğini ürünlerini ve makine öğrenmesi teknolojilerini geliştirmek için kullanır.
- İnsan inceleyiciler girdi ve çıktıları okuyabilir; Google bu veriyi önce hesaptan ayırdığını söylüyor.
- 18 yaş şartı var.
- Servis, tüketici kullanımı için değil, "profesyonel veya iş amaçlı" geliştiriciler içindir. Oyun için açık bir yasak yok, ama kişisel kullanım açısından gri bir nokta [ÇIKARIM].

**Oyun metni kurgusal ve kişisel veri değil.** Bu yüzden eğitim ve inceleme kabul edilebilir [ÇIKARIM]. Oyuncunun serbest metin alanına kişisel bilgi yazması ayrı bir risktir.

**İçerik:** Gemini 2.5 ve sonrasında ayarlanabilir filtreler varsayılan olarak kapalı; çocuk güvenliği gibi temel korumalar kapatılamaz ([safety](https://ai.google.dev/gemini-api/docs/safety-settings)). Kullanım politikası cinsel içeriği ve şiddeti teşvik eden içeriği yasaklar; sanatsal istisna Google'ın takdirindedir ([policy](https://policies.google.com/terms/generative-ai/use-policy)).

**JSON:** Yapılandırılmış çıktı var ve örnekler `gemini-3.8-flash` kullanıyor ([doküman](https://ai.google.dev/gemini-api/docs/structured-output)). 3.5 Flash-Lite için açık onay bulunamadı; bağlam ve çıktı sınırı da [models](https://ai.google.dev/gemini-api/docs/models) sayfasında yok.

**İzleyici kontrolü (21 Ekim, 3.5 Flash-Lite 15 RPM / 250K TPM / 500 RPD):**
- 250K TPM ve 500 RPD ikincil kaynakla örtüşüyor.
- RPM farklı: [ScriptByAI](https://www.scriptbyai.com/gemini-api-free-tier-limits/) 10 diyor, izleyici 15 diyordu.
- Kaynak AI Studio ekranını gösterdiğini söylüyor, ama resmi sayfadan teyit edilemedi. **Hesaptaki [AI Studio limit ekranına](https://aistudio.google.com/rate-limit) bakılmalı.** Bu sayfa giriş ister, okunamadı.
- 10 veya 15 RPM bu oyun için fark yaratmaz (en çok 2,8 çağrı/dakika).

### Groq

**Doğrulandı ([rate-limits](https://console.groq.com/docs/rate-limits), ham HTML):** Sayfada iki tablo var.

| Model | Plan | RPM | RPD | TPM | TPD |
|---|---|---|---|---|---|
| gpt-oss-120b, gpt-oss-20b, qwen3.8-27b | Free | 30 | 1K | 8K | 200K |
| gpt-oss-120b | Developer | 1K | 500K | 250K | - |

**İzleyici kontrolü:** 30 RPM / 8K TPM / 1000 RPD / 200K TPD değerleri **hâlâ geçerli**. Sayfa metnindeki "Developer planı temel limitleri" ifadesi Developer sekmesine aittir [ÇIKARIM].

**Oturuma etkisi [ÇIKARIM]:**
- 200K TPD: 35-54 çağrı. Tur başına 1 çağrıyla 25-39 dakika, 2 çağrıyla 12-19 dakika.
- 8K TPM: tek çağrı sığar, ama üst boyutta 1 çağrı/tur sınırın dibindedir, 2 çağrı/tur aşar.
- Sonuç: bir oturumun başını karşılayan yedek olur, ana sağlayıcı olmaz.

**Modeller ([models](https://console.groq.com/docs/models)):** gpt-oss-120b üretim modeli, 131.072 bağlam. qwen3.8-27b önizleme; sayfa önizleme modellerinin üretimde kullanılmaması ve kısa sürede kaldırılabileceğini belirtiyor. llama-3.1 ve 3.3 artık Enterprise.

**JSON:** Üç modelde de strict JSON şema destekleniyor; akış (streaming) ile birlikte kullanılamıyor ([doküman](https://console.groq.com/docs/structured-outputs)).

**Veri:** Varsayılan olarak çıkarım verisi saklanmaz; sorun giderme veya kötüye kullanım için 30 güne kadar log tutulabilir ([your-data](https://console.groq.com/docs/your-data)). Eğitim hakkında bu sayfa bilgi vermiyor. Üçüncü taraf bir kaynak eğitim yok diyor [İKİNCİL].

**Okunamadı:** [Fiyat sayfası](https://groq.com/pricing) ücretsiz planı anlatmıyor. [Site şartları](https://groq.com/terms-of-use) GroqCloud'u kapsamıyor; Groq Services Agreement okunmadı. Yani kullanım kısıtı ve içerik kuralı doğrulanmadı.

### Cloudflare Workers AI

**Doğrulandı:**
- Günlük 10.000 neuron ücretsiz, sıfırlama 00:00 UTC ([pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)).
- Metin üretimi varsayılan 300 RPM. Workers Paid gerektiren modellerde limit farklı ([limits](https://developers.cloudflare.com/workers-ai/platform/limits/)).
- Cloudflare, Workers AI içeriğini model eğitiminde kullanmaz ([data-usage](https://developers.cloudflare.com/workers-ai/platform/data-usage/)).
- deepseek-v4, glm-5.x ve kimi-k2.6/k2.7 gibi modeller Workers Paid ister. Aşağıdaki modellerin sayfasında böyle bir şart görülmedi, ama açık "ücretsiz" ifadesi de yok.
- Bu modeller `response_format` parametresi listeliyor, JSON modu açıkça onaylanmıyor. [JSON mode](https://developers.cloudflare.com/workers-ai/features/json-mode/) listesinde yalnızca altı eski model var. **Test gerekir.**

**Günlük kapasite [ÇIKARIM].** Neuron fiyatlarından hesaplandı. Tipik = 3.500/200, üst = 5.000/700.

| Model | Bağlam | Neuron/çağrı, tipik - üst | Çağrı/gün, tipik - üst | 2 saat 1 çağrı (168) |
|---|---|---|---|---|
| [glm-4.7-flash](https://developers.cloudflare.com/workers-ai/models/glm-4.7-flash/) | 131K | 27 - 53 | 377 - 188 | Evet |
| [gemma-4-26b-a4b-it](https://developers.cloudflare.com/workers-ai/models/gemma-4-26b-a4b-it/) | 256K | 37 - 65 | 268 - 154 | Tipik evet, üstte hayır |
| gpt-oss-20b | - | 69 - 110 | 144 - 90 | 1 saat olur |
| [gpt-oss-120b](https://developers.cloudflare.com/workers-ai/models/gpt-oss-120b/) | 128K | 125 - 207 | 80 - 48 | Hayır |
| llama-3.3-70b | - | 134 - 277 | 74 - 36 | Hayır |

GLM-4.7-Flash, günde bir oturum için yeter. 2 çağrı/tur ve 2 saatlik oturumda tipik boyutta sığar (yaklaşık 8.900 neuron), üst boyutta sığmaz.

**Şart:** Modeller üçüncü taraf ürünü sayılıyor, sağlayıcı kullanım kuralları geçerli ([terms](https://www.cloudflare.com/service-specific-terms-developer-platform/)). Başlangıç için hesap, API token ve Account ID gerekiyor; [doküman](https://developers.cloudflare.com/workers-ai/get-started/rest-api/) kart istemiyor. Kart gerekmediği bilgisi yalnızca [Apidog](https://apidog.com/blog/free-ai-api/) kaynağında [İKİNCİL].

### Z.ai (GLM doğrudan API)

**Doğrulandı:**
- GLM-4.7-Flash, GLM-4.5-Flash ve GLM-4.6V-Flash tüm kalemlerde ücretsiz ([pricing](https://docs.z.ai/guides/overview/pricing)).
- GLM-4.7-Flash: 200K bağlam, 128K en çok çıktı ([doküman](https://docs.z.ai/guides/llm/glm-4.7)).
- JSON için `json_object` modu var; Flash için açık onay yok ([doküman](https://docs.z.ai/guides/capabilities/struct-output)).
- [Şartlara](https://docs.z.ai/legal-agreement/terms-of-use) göre API kullanıcılarının içeriği, açık onay olmadan hizmet geliştirmede kullanılmaz. Bireysel kullanıcılar için ayrı ve daha geniş bir hüküm var; hangisinin uygulanacağı netleştirilmeli. İnsan incelemesi konusunda şartlar sessiz. Yasaklı bölgelerde Türkiye yok.

**Okunamadı:** Limit sayfası [z.ai paneline](https://z.ai/manage-apikey/rate-limits) yönleniyor ve sayı içermiyor. Üçüncü taraf kaynaklar çelişkili: [Puter](https://developer.puter.com/tutorials/zai-glm-api-pricing/) sınırlı diyor, [Novita](https://blogs.novita.ai/glm-free-api/) tavan yok diyor. Eşzamanlılık bilinmiyor. Kalıcılık taahhüdü bulunamadı.

### Mistral

**Doğrulandı:**
- Ücretsiz mod varsayılandır, en düşük limitlere sahiptir, "değerlendirme ve prototipleme" içindir ([help](https://help.mistral.ai/en/articles/698531-why-am-i-hitting-api-rate-limits-and-how-do-i-increase-them)).
- API erişimi kartsız açılır ([quickstart](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key)).
- Limitler RPS, token/dakika ve token/ay olarak uygulanır; sayılar yalnızca panelde görünür.
- [Ticari şartlar](https://legal.mistral.ai/terms/commercial-terms-of-service) varsayılan olarak eğitimde kullanmıyor, ama ücretsiz planı kapsamıyor. Labs ve önizleme modelleri ise eğitimde kullanılabilir.

**İkincil ve çelişkili:**
- Limit: [mintlify kopyası](https://mintlify.com/cheahjs/free-llm-api-resources/providers/free/mistral-plateforme) 1 RPS / 500K TPM / 1B token ay diyor; [unified.to](https://unified.to/blog/how_to_get_a_mistral_ai_api_key_and_connect_it_to_your_product) yaklaşık 2 RPM diyor.
- Eğitim: [OpenRouter blog](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/) ve [Costbench](https://costbench.com/software/llm-api-providers/mistral-ai/free-plan/), Experiment planında eğitim onayının şart olduğunu söylüyor.
- Telefon doğrulaması yalnızca üçüncü taraf kaynakta var.

**Sonuç [ÇIKARIM]:** 1 RPS doğruysa rahat sığar (27M token/ay, 1B yanında çok küçük). 2 RPM doğruysa 1 çağrı/tur sığar, 2 çağrı/tur sığmaz. Eski limit sayfası adresleri 404 döndü.

### OpenRouter ücretsiz modeller

**Doğrulandı ([limits](https://openrouter.ai/docs/api/reference/limits), [FAQ](https://openrouter.ai/docs/faq)):** 20 RPM, 50 RPD. Tüm zamanlarda en az 10 kredi alınmışsa 1.000 RPD. FAQ bu modellerin "genellikle üretim için uygun olmadığını" söylüyor.

**Oturuma etkisi [ÇIKARIM]:** 50 RPD, tur başına 1 çağrıyla yaklaşık 36 dakikadır. 1.000 RPD oturumu rahat taşır, ama bir defalık 10 kredi alımı gerekir, yani "ödemesiz" değildir.

**Bugünkü ücretsiz liste ([ham API](https://openrouter.ai/api/v1/models)):**

| Model | Bağlam | JSON | Sağlayıcı veri politikası |
|---|---|---|---|
| google/gemma-4-31b-it:free | 262K | response_format | Eğitim yok, 55 gün saklama, Google AI Studio |
| google/gemma-4-26b-a4b-it:free | 262K | response_format | Google AI Studio |
| nvidia/nemotron-3.5-super-vl:free | 1M | Şema var | **Eğitim var, saklama var** |
| xingchen-agi/xing4.0-29b-a4b:free | 262K | Şema var | Eğitim yok, saklama yok (Phala) |
| dots-studio/dots-3-note-preview:free | 512K | Şema var | Saklama var; **bitiş 2026-12-31** |
| thinkingmachines/inkling:free | 1M | Yok | **Eğitim var, saklama var** |
| cohere/north-mini-code:free | 256K | Yok | Saklama 30 gün |
| recursive/flint-v1.0:free | 262K | response_format | **Şu an hizmet dışı görünüyor** |
| poolside/laguna-s/xs-2.1:free | 262K | Yok | **Bitiş tarihi bugün** |

`openrouter/free` yönlendiricisi de var, ama model değişimi oyunda ses ve format tutarlılığını bozar [ÇIKARIM]. Gemma 4 ücretsiz satırında OpenRouter "eğitim yok" gösterirken Google'ın ücretsiz katman şartları tersini söylüyor. Bu farkın sebebi doğrulanamadı.

### Diğer sağlayıcılar

- **GitHub Models:** 2026-07-30'da tamamen emekli edildi ([doküman](https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models)). OpenRouter blogundaki limitler eskidir.
- **Cerebras:** Kalıcı ücretsiz katman yok. Doğrulanmış ödeme yöntemi sonrası tek seferlik $5, 30 gün geçerli; "üretim için değil" ([pricing](https://www.cerebras.ai/pricing), [limits](https://inference-docs.cerebras.ai/support/rate-limits)). Deneme limiti: 5 RPM, 30K TPM, 1M TPD; gpt-oss-120b ve qwen-3.8-27b; bağlam 65K ([models](https://inference-docs.cerebras.ai/models/overview)). Girdi/çıktı saklamadığını söylüyor, eğitim konusunda politika net değil ([gizlilik](https://www.cerebras.ai/privacy-policy)).
- **NVIDIA NIM:** [Deneme şartları](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf) erişimi sınırlı deneme amacıyla verir, üretim kullanımını yasaklar ve kullanıcı içeriğini yapay zekâ modelleri dahil ürün geliştirmede kullanır. 40 RPM yalnızca [forum](https://forums.developer.nvidia.com/t/is-nim-free/369368) kaynaklı [İKİNCİL]. Kredi sisteminin durumu çelişkili. Düzenli oyun, deneme amacını aşar [ÇIKARIM].
- **SambaNova:** Ödeme yöntemi yoksa model başına 20 RPM, **20 RPD**, 200K TPD ([limits](https://docs.sambanova.ai/docs/en/models/rate-limits)). Modeller: gpt-oss-120b, DeepSeek-V3.1/3.2, gemma-4-31B, Llama 3.3. [Gizlilik sayfası](https://sambanova.ai/privacy-policy) API verisini kapsamıyor.
- **Cohere:** Trial anahtarı 20 RPM, 1.000 çağrı/ay ([limits](https://docs.cohere.com/docs/rate-limits)). Ayda 2.400 turu taşımaz. [Şartlar](https://cohere.com/terms-of-use) iş kullanımı için ve kişisel kullanımı yasaklıyor, ama sayfa 2022 tarihli, güncelliği doğrulanmadı.
- **Hugging Face:** Ücretsiz kullanıcıya aylık kredi yok, kullanım için kredi satın alınmalı ([pricing](https://huggingface.co/docs/inference-providers/pricing)).
- **Together:** Ücretsiz deneme yok, en az $15 alım gerekiyor ([billing](https://docs.together.ai/docs/billing)). [Fiyat sayfasında](https://www.together.ai/pricing) sıfır fiyatlı Ternary Bonsai 27B görünse de erişim için alım şartı kalkıyor mu doğrulanmadı.
- **Vercel AI Gateway:** [Ücretsiz katman](https://vercel.com/docs/ai-gateway/pricing) model alt kümesi ve aylık kredi içerir, sayılar [yayınlanmıyor](https://vercel.com/docs/ai-gateway/rate-limits). $5 tutarı [arama özetinden](https://vercel.com/docs/ai-gateway/pricing) geldi, okuduğum metinde yoktu. [Ücretsiz model sayfasının](https://vercel.com/ai-gateway/models?freeTier=true) ilk %43'ünde Haiku 5.5 "free" etiketli görünmüyor. Sayfanın kalanı okunmadı. Eğer panelde Haiku 5.5 uygun çıkarsa $5, bu kullanımı karşılardı; bu olasılık düşük görünüyor ve doğrulanmadı.
- **Ollama Cloud:** $0 aboneliği olan plan token başına ödemelidir, ücretsiz kota değildir. Gemma4 $0,14 / $0,40; prompt saklanmaz ve eğitimde kullanılmaz ([pricing](https://ollama.com/pricing)).
- **Alibaba Model Studio:** Model başına yaklaşık 1M token, 90 gün, yalnızca Singapur bölgesi ([quota](https://www.alibabacloud.com/help/en/model-studio/new-free-quota)). Kalıcı değil.

## 6. Türkçe yeteneği

Güncel modeller için Türkçe yaratıcı yazım karşılaştırması **bulunamadı**. Çok seçmeli sınavlar anlatı kalitesini ölçmez [ÇIKARIM].

- **[TurkBench](https://arxiv.org/html/2601.07020v1)** (Ocak 2026, sayfanın ilk bölümü okundu): gpt-oss-120b 78,6; GLM-4.6 76,9; DeepSeek-V3.1 75,2; Qwen3-Next-80B 75,0; Qwen3-30B 73,4; gemma-3-27b 73,0. GLM-4.7-Flash, Gemma 4 ve Gemini bu sıralamada görülmedi. GLM-4.6 sonucu Flash modeline aktarılamaz [ÇIKARIM].
- **[Yerel model çalışması](https://arxiv.org/html/2609.28007v1)** (Eylül 2026): küçük 7-8B modeller, belge soru-cevap. Türkçeye uyarlanmış olmak başarıyı garanti etmiyor. Bu oyunla doğrudan ilgili değil.
- **Gemini için** bağımsız Türkçe RPG ölçümü bulunamadı.
- **Proje testi** tek doğrudan kanıttır: Sonnet 5.5 ve Haiku 5.5, Gemma'dan çok daha iyi. Cloudflare ve OpenRouter'daki Gemma 4 aynı ailedendir; büyük sıçrama beklemek için kanıt yok [ÇIKARIM].

## 7. Claude Haiku 5.5 fiyatı ve önbellek

### Fiyat [DOĞRULANDI]

İki resmi sayfa aynı: [platform pricing](https://platform.claude.com/docs/en/about-claude/pricing) ve [claude.com/pricing](https://claude.com/pricing). [Vercel model listesi](https://ai-gateway.vercel.sh/v1/models) de aynı rakamları veriyor.

| Haiku 5.5, $/milyon token | 100K'ya kadar prompt | 100K üstü prompt |
|---|---|---|
| Girdi | 0,10 | 0,50 |
| Çıktı | 0,50 | 2,50 |
| 5 dakikalık önbellek yazma | 0,125 | 0,625 |
| 1 saatlik önbellek yazma | 0,20 | 1,00 |
| Önbellek okuma | 0,01 | 0,05 |

**Kullanılan 0,10 / 0,50 tablosu doğru.** Düşük görünmesinin sebebi Haiku 4.5'in on katı olması ($1 / $5). Oyun 100K altında kalır.

### Önbellek kuralları [DOĞRULANDI]

Kaynak: [prompt caching dokümanı](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).

- **En küçük önbelleklenebilir boyut:** Haiku 5.5 için 512 token. Altında istek hata vermeden önbelleksiz işlenir.
- **Ömür:** Varsayılan 5 dakika, her kullanımda ücretsiz yenilenir. İstenirse 1 saat (`"ttl": "1h"`), yazması 2 kat.
- **Süre ölçümü:** İsteğin başından sayılır, cevabın sonundan değil.
- **Hit şartı:** İşaretli bloğa kadar her şey yüzde yüz aynı olmalı. Sıra `tools`, `system`, `messages`. Bir seviyedeki değişiklik o seviyeyi ve sonrasını geçersiz kılar.
- **Bozan şeyler:** Araç tanımları hepsini bozar. `tool_choice`, görseller, thinking ayarları ve `output_config.effort` değişimi `messages` kısmını bozar.
- **Kesme noktası:** Değişen bloktan (zaman damgası, oyuncu mesajı) önce, son sabit bloğa konur. Değişen bloğa konursa her istek yeni kayıt yazar ve hiç hit olmaz.
- **Sınırlar:** En çok 4 kesme noktası. Üst seviye `cache_control` ile otomatik önbellek Haiku 5.5'te kullanılabilir.
- **Kontrol:** Yanıttaki `cache_read_input_tokens` ve `cache_creation_input_tokens` alanları izlenmeli. İkisi de 0 ise önbellek çalışmıyordur.
- **Kapsam:** Claude API'de önbellek workspace'e özeldir.

### Bu oyuna uygulanması [ÇIKARIM]

- **Boyut:** 1.500 tokenlik sabit önek 512 sınırını yaklaşık 3 kat geçer. Bu sayı Anthropic token sayımıyla doğrulanmalı.
- **Canlı kalma:** 1,4 tur/dakika, yaklaşık 43 saniyede bir çağrı demektir. Bu, 5 dakikalık pencerenin çok içindedir ve her hit süreyi yeniler. Yani oyun sürerken önbellek düşmez; 5 dakikadan uzun mola bir yeniden yazmaya mal olur.
- **1 saat gerekmez:** Bir soğuk yazma yalnızca yaklaşık $0,0002'dir.
- **Risk:** Önek içinde tur sayacı, saat, oyuncu durumu veya değişen JSON sırası olursa hit olmaz.

### Aylık maliyet [ÇIKARIM]

Varsayım: 2.400 tur, tur başına 1 çağrı, 3.500 girdi, 200 çıktı, 1.500 sabit önek. 2.400 tur yaklaşık 28,6 saattir, yaklaşık 20 oturum ve 20 soğuk yazma kabul edildi.

| Senaryo | Girdi | Önbellek | Çıktı | Toplam |
|---|---|---|---|---|
| Önbelleksiz | $0,84 | - | $0,24 | **$1,08** |
| 5 dakika önbellekli | $0,48 | $0,04 | $0,24 | **$0,76** |
| 1 saat önbellekli | $0,48 | $0,04 | $0,24 | **$0,76** |
| Her istekte hit kaçarsa | $0,48 | $0,45 | $0,24 | **$1,17** |
| 120 soğuk yazma (sık mola) | $0,48 | $0,06 | $0,24 | **$0,78** |
| İyimser: 3.000 token sabit | $0,12 | $0,08 | $0,24 | **$0,44** |

Üst kullanım (4.800 çağrı, 5.000 girdi, 700 çıktı): önbelleksiz **$4,08**, 1.500 önekle yaklaşık **$3,44**. İki çağrı tipi aynı öneki paylaşmazsa her biri ayrı önbellek ister.

### Önbellek gerçekte ne kazandırır?

Açıkça: **ayda yaklaşık 32 sent, %30.**

- Çıktı ücreti değişmez ve değişken 2.000 token tam fiyatla ödenir.
- Tasarım hatası hit'i bozarsa maliyet önbelleksizden %8 yüksek olur.
- Haiku'yu kullanmak mantıklıysa önbelleği birkaç satırla eklemek de mantıklıdır, ama bütçe kararını değiştirmez.
- 3.000 tokenlik örnek, oyun durumunun bayt bayt aynı kalmasını gerektirir ve gerçekçi değildir.
- Sonnet 5.5'te oran benzer, tutar büyür: aynı senaryoda yaklaşık $21,60 yerine $14,83. Sonnet okuması taban fiyatın 0,05 katıdır.

### Batch API

Canlı oyunda **kullanılamaz.** İşlem eşzamansızdır, çoğu batch 1 saat içinde biter, sonuç 24 saate kadar sürebilir ([doküman](https://platform.claude.com/docs/en/build-with-claude/batch-processing)). %50 indirimi yalnızca model karşılaştırması gibi çevrimdışı işlerde işe yarar. Ayrıca önbellek için `max_tokens: 0` ön ısıtması batch içinde desteklenmiyor.

## 8. Test edilecek ilk 3

Sıralama kapasite, kalıcılık ve veri koşullarına göredir, Türkçe kalitesine göre değil. Çünkü kalite henüz bilinmiyor.

### 1. Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`)

- **Neden:** 2 çağrı/tur ile 2 saatlik oturum sığar, 164 çağrı yedek kalır. Kapanış tarihi yok. Türkiye destekli.
- **Zayıf yön:** Eğitim ve insan incelemesi var. Limit sayıları resmi sayfada görünmüyor. JSON şema desteği bu model için test edilmeli.
- **Sahibin yapacağı:**
  1. Google hesabıyla AI Studio'ya girip proje oluşturmak ve API anahtarı almak.
  2. Faturalama bağlamamak.
  3. [Limit ekranından](https://aistudio.google.com/rate-limit) gerçek RPM, TPM ve RPD değerlerini okuyup not etmek.
  4. Eğitim ve inceleme şartını kabul edip etmediğine karar vermek.

### 2. GLM-4.7-Flash, Cloudflare üzerinden (`@cf/zai-org/glm-4.7-flash`)

- **Neden:** Cloudflare eğitimde kullanmıyor. Günde 188-377 çağrı, tek oturum için yeterli. Aynı model Z.ai'de ücretsiz, yani ikinci kapı var.
- **Zayıf yön:** Günlük neuron tavanı var, 2 çağrı/tur ve uzun oturumda dolabilir. JSON modu açıkça onaylı değil. Türkçe kalitesi bilinmiyor.
- **Sahibin yapacağı:**
  1. Cloudflare hesabı açmak.
  2. Kart istenip istenmediğine bakmak.
  3. Workers AI izinli API token ve Account ID almak.
  4. Oynarken gerçek neuron tüketimini panelden izlemek.

### 3. Mistral ücretsiz mod

- **Neden:** Kartsız. 1B token/ay doğruysa en geniş aylık kota.
- **Zayıf yön:** Sayılar ve model listesi doğrulanamadı. Eğitim onayı büyük ihtimalle şart [İKİNCİL]. Amaç değerlendirme olarak tanımlı.
- **Sahibin yapacağı:**
  1. Mistral Studio hesabı açmak ve API anahtarı almak.
  2. Telefon doğrulaması isterse tamamlamak.
  3. Admin panelindeki Limits ekranından gerçek değerleri okumak.
  4. Eğitim ayarını kontrol etmek.

**Test önerisi:** Önceki Claude/Gemma denemesindeki aynı Türkçe turlar kullanılsın. Hepsi aynı ölçütle puanlansın: JSON geçerlilik oranı, Türkçe doğallık, kural tutarlılığı, gecikme. Her aday için en az bir tam 1 saatlik oturum oynansın, çünkü kısa testler günlük limitleri göstermez.

## 9. Gerçekçi karar

**Kota açısından:** Evet, düzenli oyun ücretsiz bulutta mümkün görünüyor. Ama ancak Flash-Lite sınıfı veya küçük bir modelle ve günde yaklaşık bir oturumla.

**Kalite açısından:** Bilinmiyor. Claude düzeyinde Türkçe RPG yazımının ücretsiz modellerden geleceğine dair kanıt yok. Bu testle cevaplanmalı.

**Süreklilik açısından:** Zayıf. Bu araştırmada bile görüldü: GitHub Models kapanmış, Cerebras kart şartına geçmiş, Gemini 3.8 Flash bilinen ikincil sayılarla 20 RPD'de, iki OpenRouter modelinin bitişi bugün. Ücretsiz katmanlara garanti gözüyle bakılmamalı [ÇIKARIM].

**Önerilen kurulum, test sonucuna bağlı [ÇIKARIM]:**

1. Ana sağlayıcı: testi geçen ücretsiz model (öncelik Gemini 3.5 Flash-Lite).
2. Bulut yedeği: Cloudflare GLM-4.7-Flash.
3. Son yedek: mevcut yerel gemma4:e4b.
4. Model değişiminin Türkçe sesi ve JSON biçimini bozmaması için sağlayıcı değişiminde oyuncuya görünür bir uyarı konması düşünülebilir.

**Maliyet karşılaştırması:** Ücretsiz seçenekler test edilip kalite yetmezse, Haiku 5.5 ayda yaklaşık $1-4 ile çok ucuz bir geri dönüş yoludur. Ödemesiz kalma hedefi korunacaksa bu yalnızca bilgi olarak duruyor; karar sahibindir.

## 10. Okunamayan veya doğrulanamayan noktalar

- Gemini ücretsiz katman sayıları: [AI Studio](https://aistudio.google.com/rate-limit) giriş ister, resmi doküman sayı vermiyor.
- Mistral limitleri, Experiment plan şartları ve tüketici şartları: eski adresler 404, sayılar panelde. [Pricing](https://mistral.ai/pricing) ve [inference pricing](https://docs.mistral.ai/inference/pricing) ücretsiz API sayısı vermiyor.
- Z.ai ücretsiz model limitleri ve eşzamanlılık.
- NVIDIA güncel kredi modeli ve resmi RPM. `build.nvidia.com/faq` 404 döndü. Şart PDF'i Ekim 2025 tarihli.
- Groq Services Agreement ve eğitim politikası.
- SambaNova API veri politikası.
- Cohere güncel şartları ve trial kuralları.
- `cheahjs/free-llm-api-resources` README ham adresi 404 döndü.
- OpenRouter genel sıralama sayfası yalnızca iki model gösterdi; liste ham API'den alındı.
- Vercel ücretsiz model sayfasının kalan %57'si.
- Anthropic prompt caching sayfasının son bölümü yalnızca anahtar kelime aramasıyla kontrol edildi.
- Hiçbir limit canlı istekle sınanmadı. Sağlayıcılar kapasite durumuna göre daha erken 429 dönebilir.
