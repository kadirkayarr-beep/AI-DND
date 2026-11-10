# Implementer önsözü (her implementer istemine eklenir)

Ana ilke: kalite ve güvenlik kaybına müsamaha göstermeden hız. Çelişkide kalite ve güvenlik kazanır.

## Koda giriş
- Koda `graphify query "<soru>"` ile gir; ham dosyayı yalnız grafiğin ya da önceki okumanın gösterdiği satırlar için oku. Grafik JSON içeriğini (şablon, katalog, menü tablosu) ve dinamik yolları görmez; oralarda dosyayı oku.
- Görev sonunda ve rapordan önce bir kez `graphify update .` çalıştır (commit etme).
- Testleri yalnız korumalı WSL başlatıcısıyla koş; önce hızlı set (yeni testler + `api.tests.test_journey_runner`, `test_journey_report`, `test_journey_schema`, `test_journeys`), uzun set görev sonunda bir kez.

## Kontrol listesi (her maddeyi cevapla; uygulanmıyorsa "uygulanmaz" + neden)
- (a) Tüm çağıran yollar yeni davranışı alıyor mu (ikinci yol, savaş içi yol, karakteri geçmeyen çağıran)?
- (b) Eski kayıt (alan yok) uyumu?
- (c) Geri Al ve yeniden yükleme sonrası aynı durum?
- (d) Rastgele kasabaya bağlı test yok mu (sabit tohum: `fixed_town`, `campaign_seed`)?
- (e) Oyuncuya gösterilen metin o durumda doğru mu (yalan gerekçe yok)?
- (f) Önce kırmızı test; gevşetilen test yok.
- (g) Para ve envanter yalnız doğrulanmış bir kartla değişir; görev ve iz yalnız motor kaydıyla değişir (model tek başına değiştirmez).

## Karar
Belirsizlikte dur ve sorma: karar ver, raporda `Ruling: <karar> — <neden> — <yanlışsa maliyeti>` yaz. Yalnız geri alınamaz işlem, güvenlik açısından hassas işlem, worktree dışı yan etki ya da bozuk plan durdurur.
