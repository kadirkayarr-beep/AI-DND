# AI-DND — UI Style Direction v1
**Tarih:** 2026-10-10
**Durum:** Sahip tarafından seçilmiş tasarım yönü; uygulama veya faz kabul kanıtı değildir.
**Kapsam:** Oyuncu ana menüsü ve karakter yaratma arayüzü.

## Vizyon
AI-DND, bir yapay zekâ sohbet uygulaması veya geliştirici paneli değil, 1501 DR Forgotten Realms evreninde geçen sürükleyici bir masaüstü RPG gibi hissettirmelidir. Ana menü maceranın kapısı, karakter yaratma ise bir kahramanın doğuşu hissini taşımalıdır.

## Ana menü
- **Ouroboros**, AI-DND'nin belirgin görsel amblemidir: kadim, incelikli, sıcak altın ve sönük zümrüt dokunuşları. Bu tasarım sembolü, Forgotten Realms içinde doğrulanmış bir tanrı/faksiyon simgesi ya da oyun içi lore gerçeği olarak sunulmaz.
- Sis, derinlik, kadim taş, ay ışığı, uzak ateş veya hafif büyülü izler gibi atmosfer unsurları; sade, sinematik kompozisyon. Gereksiz animasyon ve neon kullanılmaz.
- AI-DND başlığı ve tek kısa atmosferik motto. Birincil eylemler: **Yeni Macera**, **Maceraya Devam Et**, **Karakterler**. Yardımcı eylem: **Ayarlar**.
- Mevcut sistemde gerçekten bulunmayan bir sayfaya işlevsiz düğme eklenmez; mevcut rota ve davranışlar korunur. Devam etme gibi eylemlerin görünür/etkin olması gerçek kayıt durumuna dayanır.
- Oyuncuya teknik teşhis, sunucu, model, debug veya durum paneli gösterilmez. Gerekli hata/bağlantı bilgileri anlaşılır, kısa ve eyleme dönük ifadelerle verilir.

## Ortak görsel dil
- **Zemin:** kömür/siyah-antrasit. **Birincil vurgu:** sıcak, eskitilmiş altın. **İkincil:** derin zümrüt. **Okunabilir metin:** fildişi. Parşömen yalnız seçili, dengeli yüzeylerde.
- **Tipografi:** başlıklarda karakterli ama okunur fantastik serif; gövde ve kontrol metinlerinde erişilebilir, temiz yazı. Fontlar mevcut lisanslı varlıklardan veya güvenli sistem yedeklerinden seçilir.
- **Bileşenler:** tek bir token sistemi; aynı buton, kart, panel, kenarlık, boşluk, hover, focus, selected ve disabled davranışları.
- Gösterişsiz mikrohareket: sis/ışık, çok hafif amblem parıltısı; `prefers-reduced-motion` desteklenir. Döngülü, göz yorucu hareketler yok.
- Ana menü daha sinematik/ferah; karakter yaratma daha yoğun/işlevsel olabilir ancak ikisi aynı görsel dünyaya aittir.

## Karakter yaratma
- Oyuncu uzun form doldurmuyormuş gibi hissetmeli; sınıf, soy, geçmiş ve diğer seçenekler seçimin karakterini yansıtan kartlarla sunulmalı.
- **Sol:** kısa seçim kartları/liste. **Sağ:** seçili öğenin doğrulanmış özet bilgisi, uygun açıklama, gerekiyorsa görsel. **Alt:** sabit Önceki/Sonraki, mevcut adım ve küçük ilerleme göstergesi.
- Tüm adımlar için tek, büyük ve yer kaplayan adım çubuğu kullanılmaz; içeriğin ve kartların açıklamaları kısa tutulur, ayrıntı seçimle açılır.
- Karakterin mekanik özetleri yalnızca mevcut Python/otoritatif kaynaktan gelen bilgilerle gösterilir; frontend yeni seçenek/özellik veya kural icat etmez.
- Tamamlama ekranı güçlü kontrast, anlamlı görsel hiyerarşi ve belirgin son onay içerir. Mevcut adım doğrulaması ve kayıt davranışı bozulmaz.

## Masaüstü yerleşimi ve erişilebilirlik
- Birincil tasarım hedefi **1920×1080'de ana menü ve karakter yaratmanın ana akışında sayfa düzeyinde dikey mouse scroll olmaması**.
- Başlık/ilerleme alanı kompakt; seçim ve detay panelleri kullanılabilir yüksekliği paylaşır; alt gezinme görünür kalır.
- 1366×768 ve daha küçük pencerelerde taşma veya kesilmiş eylem yerine duyarlı yerleşim ve gerekirse **yalnız panel içi kaydırma** kabul edilir. Yazılar aşırı küçültülmez.
- Klavye kullanımı, görünür odak, kontrast, semantik kontroller ve ekran okuyucu etiketleri korunur.
- Oyuncuya görünen metinler tutarlı Türkçe seçilir; mevcut yerelleştirme altyapısı varsa onun üzerinden yönetilir.

## Yapılmayacaklar
- Dashboard, SaaS, launcher veya chat arayüzü estetiği; aşırı kutu, uzun metin duvarı, parlak neon, rastgele altın süs.
- Gerçek olmayan işlevsel düğmeler, sahte durum verileri, lore/oyun mekaniği üreten CSS veya frontend kuralları.
- Bu tasarım kararı gerekçesiyle Python, Qwen, SQLite, save, canon/lore, `.gitattributes`, pin veya production/deploy ayarlarını değiştirme.
- Lisans hakkı olmayan Forgotten Realms kitap görsellerini veya kaynakları kamuya açma.

## Uygulama ilkesi
İlk uygulanacak yüzeyler yalnızca mevcut oyuncu **ana menüsü** ve **karakter yaratma akışı**. Önce mevcut bileşen ve route'ları oku; sonra küçük, gözden geçirilebilir UI değişiklikleri yap. Görsel değişikliklerin gerçek gameplay, kayıt, adım doğrulaması ve oturum yalıtımını etkilemediğini sınamadan PASS deme. F01 kapanışı yeniden açılmaz; F02/F12 gibi geliştirme kapıları ayrıca yönetilir.

## Kabul gözlemi
1920×1080 masaüstünde menü ve karakter yaratmanın her adımı için ekran görüntüsü/viewport gözlemi; kesilmiş içerik, dikey sayfa kaydırması, tab erişimi, odak, kontrast, Türkçe metinler ve düğmelerin gerçek çalışması ayrı ayrı raporlanır. Test yapılmadıysa açıkça NOT TESTED denir.
