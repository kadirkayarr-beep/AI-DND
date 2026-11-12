# Odaklı web test başlatıcısı — yalnız tasarım, 2026-11-05

Durum: uygulanmadı, doğrulanmadı. Başlatıcıları değiştirme yetkisi bu araştırmanın kapsamında değildir. Mevcut çalıştırma engeli devam eder.

## Yerel kaynakta gözlenenler
- AI-DND-TOOLS/slot.sh: test/par dalları git ağacını arşivleyip slot_sync.sh ve Python başlatıcısına gider. node dalı ek argüman iletmez ve slot_web.sh çağırır.
- slot_sync.sh Python sitecustomize.py SHA256 değerini denetler. slot_web.sh bu yolu kullanmaz; dosyaları çalışma kopyasından web kopyasına alır, tüm tsc/test:c06/test:standard komutlarını çalıştırır.
- slot_web.sh set -uo pipefail kullanır, set -e kullanmaz. Test komutlarından sonra echo çalıştığından testin hata kodu betiğin çıkış kodu olarak korunmayabilir. Başarıyı yalnız dış komut exit=0 ile yorumlamak güvenilir değildir.
- linux_guarded_launcher.py temiz ortam kurar, koruma kimliğini ve sentetik yasak erişimleri doğrular; Python unittest çocuğunu başlatır, sıfır testli başarıyı reddeder. tools/acceptance/linux_guard/sitecustomize.py Python sys.addaudithook ile dosya/ağ/alt süreç işlemlerini denetler. Node bu Python audit hook'unu kullanmaz. Dolayısıyla mevcut Python guard kanıtı Node için kanıt değildir.
- dilim0-ui.test.mjs ve shop-panel.test.mjs gerçek Vite createServer(middlewareMode:true) + ssrLoadModule + React static render kullanır. dilim0-ui ayrıca typescript/vm kullanır; mevcut before() bütün ilgili modülleri yükler. İsim filtresi bu kurulumu ya da eksik modül sorununu ortadan kaldırmaz.
- vite.config.ts eklentiler, alias ve /api proxy hedefi içerir; süreç ortamı davranışı değiştirir. Middleware modu tek başına ağ yokluğu kanıtı değildir. Paket/derleyici süreçlerinin fiilî ihtiyaçları bu çalışmada yürütülerek ölçülmedi.

## Önerilen en küçük işlevsel arayüz
Yeni, ayrı node-focused modu; eski test/par/node/codegen modlarının anlamını değiştirmez. Girdi sabit tuple tablosundan seçilir: (3, AI-DND-dilim0, tests/dilim0-ui.test.mjs) ve (2, AI-DND-dilim1, tests/shop-panel.test.mjs). Sonraki görevlerin ilgili regresyon dosyaları gerektiğinde açık incelemeyle tabloya eklenir. Serbest kabuk komutu, npm script adı, glob, isim regex'i, --require/--import veya ek Node bayrağı kabul edilmez.

Label dar ASCII karakter kümesi ve uzunluk sınırıyla doğrulanır; timeout pozitif, üst sınırlandırılmış tamsayıdır. Dosya adı tablo anahtarıdır, keyfi yol değildir. Yanlış yuva/klasör, ../, mutlak yol, symlink dışa çıkışı veya bilinmeyen seçenek ürün dosyası çalıştırılmadan reddedilir. Shell eval kullanılmaz; süreç argüman dizisiyle başlatılır.

Yuva kilidi kopyalama başlamadan atomik alınır; aynı yuva Python/web/derleme işlerinin tamamı için ortak olmalıdır. Yalnız hedef dosyada seri test yürütülür. Zaman aşımında tüm süreç grubu sonlandırılır; kilit finally/trap ile bırakılır. Bu, eldeki pgrep ön kontrolünün yarış penceresini kapatmayı gerektirir; mevcut modları sessizce genişletme gerekçesi değildir.

## Güvenli yürütme için zorunlu önkoşul
Yalnız hedef seçimi eklemek güvenlik çözümü değildir. Node ve olası Vite/derleyici çocukları için ayrı, denetlenmiş OS düzeyi koruma gerekir; Python guard'ı kapatıp Node başlatmak önerilmez.
- Salt okunur, seçili kaynak/dependency görüntüsü; gerçek Desktop/home/.git/.agents/.env/anahtarlar/kayıtlar ve Windows disk mount'ları görünmez. Symlinkler izinli görüntü dışına çıkamaz. Testlerin modül yüklemesi kod çalıştırdığı için yalnız test dosyası değil bütün yüklenen kaynak kapsamı önemlidir.
- Yalnız koşuya özel sentetik log/cache/tmp alanı yazılabilir. Üretim çalışma kopyasına geri kopyalama yok; codegen ayrı modda kalır. Ağ ve yerel gerçek API erişimi kapalı; anahtar/kimlik doğrulama/proxy/Node enjeksiyon ortamı aktarılmaz. Sabit asgari ortam sıfırdan kurulur.
- Node/Vite/esbuild benzeri süreç ihtiyacı kontrollü deneyle belirlenmeli; gerekli çocuklar aynı dosya/ağ sınırını miras almalıdır. Keyfi alt süreç izni verilmez. Bütün alt süreçleri kapatmak mevcut düzenekle uyumlu mu bilinmiyor; bu belirsizlik güvenliği gevşetme gerekçesi değildir.
- Olası mekanizma izole Linux mount/network/process ortamı ve kısıtlı kullanıcıdır. Bu makinede gerekli mekanizmanın kullanılabilirliği/etkinliği test edilmedi; bu belge çalışır sandbox reçetesi değildir. Vite HMR/listener engelde kalırsa kontrollü test-konfigürasyon değişikliği ayrıca incelenir; koruma kaldırılmaz.

## Kanıt ve kabul ölçüsü (henüz koşulmadı)
1. Ürün ithalinden önce, gerçek sır kullanmadan sentetik dış dosya okuma/yazma, localhost/DNS/dış ağ ve yasak alt süreç denemeleri başarısız olmalı. Çocuk süreç varsa aynı kısıtlar onun içinde de kanıtlanmalı. Kanıt eksikse ürün testi başlamamalı.
2. Guard/başlatıcı, Node sürümü, paket kilidi, hedef dosya ve kaynak görüntüsü özetleri rapora yazılır; çevre değişkenlerinin değerleri yazılmaz.
3. Bilinen geçen sentetik test exit=0; bilinen assertion hatası nonzero; kurulum hatası nonzero; sıfır test nonzero; timeout nonzero ve geride süreç yok. Son echo hata kodunu örtmemeli. Yapılandırılmış sonuçta tests>0, failed=0, cancelled=0 olmalı; skip/todo saklanmamalı, yeni atlama kabul edilmemeli.
4. Yanlış yuva/klasör, yol taşması, symlink kaçışı, iki eşzamanlı çağrı ve kesinti temizliği olumsuz kontrolleri geçmeli.
5. Ancak bunlardan sonra değişmemiş gerçek dosya çalışır: Dilim 0 için mevcut eksik quest-counter ile beklenen RED; Dilim 1 shop-panel mevcut başlangıç sonucu. Daha sonra görev TDD döngüsü. Bunlar tam tsc/tarayıcı/gerçek zincir kapılarının yerine geçmez.

Sonuç: en küçük kod yönlendirmesi yeni sabit hedef modu olabilir; en küçük güvenli çözüm bundan büyüktür, çünkü mevcut web yolu Python korumasının dışında kalır. Uygulama ve güvenlik doğrulaması ayrı yetkilendirilmiş araç işi olmalıdır. Bu araştırmada kurulum, paket indirme, test koşusu veya betik değişikliği yapılmadı.