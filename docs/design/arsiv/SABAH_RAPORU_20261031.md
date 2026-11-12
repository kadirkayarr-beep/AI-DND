# Sabah raporu (2026-10-31)

Dal `task/c-series-merge`, son commit `db9d028`. Ürün kabulü değildir; kabul yalnız Kadir'de. Tarayıcıda denenmedi.

Son doğrulama `db9d028`: 5256 test, 0 başarısız, 166 atlanan. Dal uzak yedekte. `main` ve `dev/ai-dnd` değişmedi.

## 20 tur karşılaştırması

| Ölçüt | Akşam (`cba0408`) | Sabah (`db9d028`) |
|---|---|---|
| "Hangisini kastediyorsun" duvarı | 8 tur | 0 |
| İlk han | Kilitli | Açık, karakter içeri girdi |
| "Tamam, oraya gidiyorum" | Duvar | Gidiyor |
| Han konuşulurken "İsmi nedir?" | Duvar | Hanın adı |
| İsim sorusu | Duvar | NPC adını söylüyor |
| Şarkı, yazı tura, teklif geri çekme | Şablon veya ret | Modelle anlatılıyor |
| Açılış | 4 kampanyada aynı | 4 farklı kadro |
| Sırlar | Prompta gidiyordu | Hedef ve kilit bilgisi prompttan çıktı |
| Hazır hamleler | Hep açık, genel | Kapalı "Fikir lazım mı?", sahneden |
| NPC sesi | Yok | Kişi başına saklı ses özelliği, ör. "Adrie. Bu kadar sohbet için pek zamanım yok." |

## Hâlâ kötü

1. **Kampanya kilitlenebilir (en önemlisi).** Bir denemede model sınıflandırma çağrısında döngüye girdi, 503 döndü ve sonra o kampanyadaki tüm turlar 409 oldu. Kök neden bulunmadı. Oyun testinden önce çözülmeli.
2. **Anlatım hitabı kayıyor.** "şarkınız", "üzerinizde" ve bir turda "bakışım" geçti.
3. **Çevreyi gözleme kurudu.** "Çevremi gözlemliyorum" artık modelsiz, kısa ve kuru metin veriyor, "Gülümseyen biri: ..." biçimi yapay duruyor.
4. **Yer tutarlılığı tam değil.** Sokaktaki bir NPC için "tezgâhın arkasında" yazıldı.
5. **Bilinmeyen yer.** "Şehrin en zengin mahallesine gidiyorum" yeni bölge yaratmıyor, "yolu bulamıyorsun" diyor.
6. **Küçükler.** Ekmek kokusu nadir de olsa dönebiliyor. İyi bir NPC cevabını silen yankı onarımı duruyor. Konuşma hâlâ NPC'nin gerçek adını alıyor (saklı nedeni yoksa).

## Yapılmadı

- Motor defteri ve compact bellek (taslak `DEFTER_TASARIM_20261031.md`).
- Yaşayan dünya: NPC amacı, teklif, haber (eşleme `LIVING_WORLD_MAP_20261031.md`). Bugünkü oyun turunda hiçbir NPC zamanla kendi işini ilerletmiyor.
- DM tarzı seçimi, gerçek ölüm varsayılanı, mikrofon, Neverwinter içeriği, yoldaş.

## Kararını isteyen küçük seçimler

- Hanlar 07:00-24:00 açık sayıldı.
- Mesafesi kayıtsız kişi, savaş dışı saldırıda 5 ft sayıldı.
- Reddedilmiş davranışı sabitleyen testler değiştirildi, nedenleri commit mesajlarında.

## Sıradaki öneri

1. Kampanya kilitlenmesi.
2. Hitap ve yer tutarlılığı.
3. Defter ve compact bellek.
4. Yaşayan dünyanın en küçük dikey dilimi.
5. Sen tarayıcıda 15 dakika dene: bu, oyun testinden önce en değerli geri bildirim olur.
