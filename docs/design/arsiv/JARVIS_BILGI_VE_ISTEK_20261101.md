# Jarvis için iki mesaj (2026-11-01)

Sırayla gönder: önce Mesaj 1, Jarvis özetini verince Mesaj 2.

---

## Mesaj 1: Bilgilendirme

Jarvis, proje son iki günde çok değişti. Takip sayfanı güncellemeden önce bunu oku. Önceki dosyaların bir kısmı artık geçerli değil. Kod yazma, model çalıştırma, test koşma. Bu mesaj yalnız bilgi ve takip güncellemesi içindir.

### Kaynak ve kanıt sınırı

- Aşağıdakiler Claude'un raporudur; sen bağımsız doğrulamadın, öyle yaz.
- Ürün kabulü yalnız Kadir'dedir. Ajan oyunları kabul değildir.
- Çalışma dalı `task/c-series-merge`, son raporlanan temiz nokta `c4139bc`. `main` ve `dev/ai-dnd` değişmedi. Depo private.
- Testler: 6213 test, 0 başarısız, 166 atlanan (guard altında). Atlananlar geçmiş sayılmaz. Şu an yeni döngü sürdüğü için en yeni commit'in test sonucu henüz yok.
- Tarayıcıda yalnız ilk akış denendi: karakter oluşturma ve ilk konuşma turu. Son sürümün tarayıcı kabulü yok.

### Yol haritası değişti

Geçerli belge `YOL_HARITASI_ONERI_20261031.md`, Kadir onayladı. Önceki sıraların yerine geçer.

- **Başarı ölçüsü artık test sayısı değil:** Kadir 30 dakika oynar, en az 2 gerçek iz bulur, birinin peşine düşer, seçiminin sonucunu görür ve "şimdi ne olacak?" der.
- **Yeniden yazma yok:** Kural, savaş, kayıt ve makbuz motoru kalıyor. Serbest yazı parça parça "model önerir, Python doğrular, kaydeder" düzenine geçiyor.
- **Dondurulanlar:** Yeni sınıf, kural ve büyü işi; her şikâyete yeni kalıp eklemek; soylu yoluna özel zincir.
- **Sıra:** temizlik, model denemesi, şehir bilgisi ve işler, Kadir'in 30 dakikası, sonuçlar, 18 katmanı 3'e indirme, defter, üç oturumluk oyun testi, ilk sürüm.
- Oyun testi dili **Türkçe**. Eski "İngilizce oyun testi" kararı kalktı. Kadir, Türkçe model kalitesini sınırlıyorsa dilden vazgeçmeye razı olduğunu söyledi.

### Kadir'in ilk gerçek oyunu ne gösterdi

Kadir 30 tur oynadı ve "ilerleyemiyorum" dedi. Mekanik çalışıyordu, ama şehirde yapacak hiçbir şey yoktu. Fable analizi kök nedeni gösterdi: model "iş biliyorsan söyle" talimatı alıyordu, ama şehir bilgisi almıyordu. Kadir'in anlatımı `OYUN_TARIFI_KADIR_20261031.md` dosyasında. Örnekler oyuna kopyalanmaz.

### Model kararı

Aynı 30 Türkçe turla ölçüldü (tek koşu, Gemma için prompt o sırada ayarsızdı):

| Model | Sonuç | Maliyet |
|---|---|---|
| Sonnet 5.5 | En insani | Ayda ~25 USD, şu an bütçe dışı |
| Haiku 5.5 | Çok iyi | Ayda ~1 USD |
| Gemini 3.5 Flash-Lite | İyi, kısa, çok hızlı | Ücretsiz |
| Gemma 4 E4B (yerel) | Dünyayı taşıyamadı | Ücretsiz |
| GLM-4.7-Flash | Tekrar ediyor, reddedildi | Ücretsiz |

Karar: **Gemini ana, Haiku yedek (ayda en çok 4 USD), Gemma son yedek.** Zincir kodda, yalnız yerel oyunda çalışır. Anahtarlar depo dışındadır, asla yazdırılmaz. Sansürsüz seçenek ileride yerel model olarak ayrıca düşünülecek; Claude açık yetişkin içerik yazmaz.

### Yapılanlar (raporlanan)

- **Konuşma ve yer:** "Hangisini kastediyorsun" duvarı kalktı. Kapı, gitme, isim, kişi etiketleri, hazır hamleler, açılış çeşitliliği düzeltildi.
- **Kilitlenme:** 503 sonrası kampanya kilitlenmesi çözüldü; kök neden açık hamle kaydının kapanmamasıydı.
- **Şehir bilgisi:** İnsanlar mesleğine göre sınırlı bilgiye sahip.
- **Dünya işleri:** Jarvis kataloğu bağlandı; iş kalıpları ve ortam olayları çalışıyor.
- **Gerçek ölüm:** Varsayılan oldu. Tur başına bir ölüm zarı, ölüm hikâyesi, ölenler geri dönmez.
- **Gerçek işler:** Teklif, kabul, ret, vazgeçme, süre, teslimat, vardiya, keseye gerçek ödeme. Jarvis'in `offer_answers` verisi kullanıldı.
- **İsimler:** Jarvis'in `name_pools` verisi yeni kampanyalarda kullanılıyor.
- **Sözler:** NPC kendi sözünü inkâr etmiyor; söz kayda bağlanıyor.
- **Dünya tepkisi:** Ceset bulunuyor, boş nöbet yeri doluyor, haber gerçek yollardan yayılıyor, muhafız arıyor.
- **Hikâye bağları:** Dört tür bağ: karşı, dönüş, vade, kanıt. Söylentiler ve mektuplar bağlandı.

### Son ajan oyunu (157 tur, kanıt kabul değildir)

Hedefin 4 ölçüsünden 3'ü tuttu, dördüncüsü kısmen. Kırık mühür ücreti yarıya indirdi, satıcı sırt çevirdi, dövülen kâhya hatırladı, sokak dedikodu yaptı. Mektup gerçek merak yarattı, sonra söndü. Ajanın özeti: "Oyun artık tepki veriyor ama üstüne inşa etmiyor."

### Şu an çalışan döngü

"Söylenen şey gerçek olsun": model bir defter anlatıyorsa gerçekten çantaya girsin, NPC "tamam" deyince iş kaydedilsin, tehditler saatte gerçekleşsin, soylu hedefine genel bir yol açılsın, modelin önce anlamı önerdiği yol genişlesin. Sonunda ajan koda bakmadan oynayıp "Kadir'e hazır mı" diye değerlendirecek.

### Yeni kapanan kararlar

- Hanlar 07:00-24:00 açık. Kampanya en erken 07:00 başlar.
- Savaş dışı saldırıda kayıtsız mesafe 5 ft.
- Karakter: Carius, Human Fighter, seviye 3, Soldier, Champion, geç yirmili yaşlar, ordudan ayrılmış.

### Senden istediğim

1. Takip sayfasını buna göre güncelle. Eski "açık/bekliyor" satırlarını düzelt, tarihsel kayıtları silme.
2. Değişiklik listesini geri okuyup doğrula.
3. Bana en çok 10 satırlık özet ver. Bir sonraki mesajda iş isteyeceğim.

---

## Mesaj 2: İstek

Jarvis, Claude oyuna içerik verisi bağlayacak. Kod yazma, model çalıştırma. Tek ZIP, UTF-8. Önce önceki paketlerin şemasını oku: `thread_templates`, `ambient_events`, `offer_answers`. Aynı düzeni kullan: `schema_version`, `field_descriptions`, `binding_rules`, `items`.

### Amaç

Son oyunda iki boşluk çıktı:
- Başarılı zarlarda bulunacak bir şey yok: "başardım ama hiçbir şey bulamadım" hissi.
- Okunacak metin az. Mektup merak yarattı, ama içerik tükeniyor.

### Çalışma yöntemi

Superpowers disiplininde çalış: önce kısa plan, sonra üret, sonra kendi çıktını bağımsız gözle denetle. Doğrulama yapmadan "hazır" deme; neyi doğruladığını açıkça yaz. Toplu üretimde örnek sayısını tutturmak için tekrar yapma: aynı cümle iskeletini 3'ten fazla kullanma.

### Dosya 1: `scene_details.json`, 150 kayıt

Başarılı Algı, Araştırma veya inceleme sonucunda bulunabilecek küçük şeyler.

Alanlar:
- `id`
- `place_tags`: `sokak`, `han`, `pazar`, `liman`, `tapinak`, `soylu_konagi`, `muhafiz_karakolu`, `lonca_atolyesi`, `sehir_kapisi`, `sehir_cevresi`
- `object_tags`: `kapi`, `mentese`, `kutu`, `sandik`, `mezar_tasi`, `duvar`, `masa`, `ayak_izi`, `zemin`, `dolap`, `kiler`
- `text`: en çok 160 karakter, ikinci tekil şahıs, şimdiki zaman
- `slots`: `{yer}` `{kisi}` gibi boşluklar
- `reveals`: `hic`, `kisi_izi`, `yer_izi`, `is_ipucu`
- `severity`: `gundelik`, `merak`, `tehlike_isareti`

Kurallar: Kayıt tek başına gerçek olay, eşya, ödül veya suçlu yaratmaz. Motor bağlamadan bilgi kesinleşmez. Kişi adı uydurma, yalnız boşluk kullan. Oyuncunun ne hissettiğini yazma.

### Dosya 2: `written_texts.json`, 80 kayıt

Mektup, not, ilan, defter sayfası, makbuz, tehdit notu.

Alanlar:
- `id`
- `kind`: `mektup`, `not`, `ilan`, `defter`, `makbuz`, `tehdit`
- `tone`: `resmi`, `korkmus`, `kaba`, `kurnaz`, `yarim`, `dalgin`
- `text`: en çok 300 karakter
- `slots`: `{gonderen}`, `{alici}`, `{yer}`, `{is}`, `{zaman}`
- `leaves_question`: oyuncuda bıraktığı soru, tek cümle
- `public`: herkes okuyabilir mi

Kurallar: Sırrı doğrudan söyleme, soru bırak. Türler ve tonlar dengeli dağılsın. Yarım metinler gerçekten yarım kalsın. Tarih ve miktar yazma, gerekirse boşluk kullan.

### Dosya 3: `work_lines.json`, 60 kayıt

Oyuncunun fiilen çalışırken gördüğü kısa anlatım. "Akşama kadar çalışıyorum" gibi satırlara cevap olacak.

Alanlar: `id`, `work_kind` (`tasima`, `sayim`, `onarim`, `nobet`, `ulak`, `temizlik`, `kayit`), `place_tags`, `text` (en çok 180 karakter), `time_phrase` (`kisa`, `yarim_gun`, `tam_gun`).

Kurallar: Ücret, saat, sonuç söyleme. Bunları motor verir. Oyuncu adına duygu yazma. Her çalışmada ayrı küçük bir insan ayrıntısı olsun.

### Ortak sınırlar

- Forgotten Realms atmosferi, kanon iddiası yok, kitap metni yok.
- Kadir'in örnek hikâyelerini kopyalama: hırsız ekibi, kapüşonlu kadın, dördüncü oda, boş kasa, elmas soygunu.
- Açık cinsel içerik yok, reşit olmayan kimse yok.
- Türkçe doğal olsun: çeviri kokmasın, ek uyumu boşlukla bozulmasın.
- Ekmek kokusu ve "görev yok" gibi meta cümleler yok.

### Teslim

- Üç JSON, `00_ONCE_OKU_CLAUDE_TR.md`, `99_DOGRULAMA_TR.md`, `MANIFEST.md`.
- Doğrulama: JSON ayrıştırma, kayıt sayısı, benzersiz kimlik, boşluk tutarlılığı, uzunluk sınırı, dağılım tablosu, tekrar denetimi.
- Motorun bu veriyi okuduğunu iddia etme; bağlamayı Claude yapacak.
