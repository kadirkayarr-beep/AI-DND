# R01 devir kaydı — aynı hesap yeniden açılışında pending bağlamı (2026-10-27)

Kısa kayıttır; gerçek tarayıcı/Clerk kanıtı değildir (gerçek kabuk mount'u R09'da). Sır, jeton yok.

## Kaynak kimliği
- Dal `task/b01-source-identity-20261026`, HEAD `78b380384e70832156d2d9aa2785192bbbbdb74b`; R01 değişiklikleri izlenen iki dosyada ve izlenmeyen bir test dosyasında, commit yok.

## Kök neden
- `nextAccountClient`, `previous` boşken (her ilk mount ve sayfa yenilemesi) koşulsuz `clearAccountBrowserState()` çağırıyordu; kimlik `userId:sessionId` olduğu için token yenilenip oturum değişince `ClerkApiSession` efekt temizliği de depoyu siliyordu.

## Değişiklik
- `artifacts/ai-dnd-experience/src/lib/account-session.ts`: `classifyOwnerTransition(previous, resolved)` (`unresolved|same|changed`); sahip = Clerk kullanıcı kimliği (oturum kimliği değil), `localStorage["ai-dnd-account-owner"]` içinde saklanır; yalnız `changed` iken depo temizlenir ve sahip yazılır. Sahibi kayıtlı olmayan veri `changed` sayılır (kurtarılmaz). Çözülmemiş kimlik depoya dokunmaz. Epoch dönüşü, `cancelQueries`/`clear` ve geç yazma engeli korunuyor.
- `artifacts/ai-dnd-experience/src/components/clerk-api-session.tsx`: kimlik değişimi efekt temizliği artık depoyu silmez; depo yalnız doğrulanmış çıkışta (`isLoaded && isSignedIn !== true`) veya bileşen sökülürken (çıkışta `Show` söker) temizlenir.

## Test
- `artifacts/ai-dnd-experience/tests/roadmap-r01.test.mjs` (8 test) önce kırmızı (4 düştü), sonra yeşil.
- `pnpm install --frozen-lockfile` bu klasörde çalıştırıldı (izlenen dosya değişmedi; `node_modules` gitignored).
- Paket klasöründen `node --experimental-strip-types --test tests/*.test.mjs`: 191 test, 189 geçti, 1 atlandı, 1 dosya düştü (`play-screen-ui-regression`: `CHROMIUM_PATH` yok, ortam). Plandaki `cmd` depo kökünden çalıştırılınca eski testler `vite.config.ts` yolunu bulamıyor; paket klasörü cwd olmalı.
- `tsc` bu ortamda TS6305 (api-client-react dist üretilmemiş) verdi; R01 değişikliklerinden bağımsız. typescript-patterns-enforcer kancası dosyada önceden var olan 6 kural ihlali bildirdi (döngüler, 401, 3, 8192, regex); dokunulmadı.

## Açık
- Gerçek Clerk/tarayıcı yenileme doğrulaması yok (R09). Bağımsız inceleme yapılmadı.
- Bileşen davranışı (çıkış/sökme) birim testinde yalnız kaynak düzeyinde sabitlendi; React render testi yok.
- `docs/acceptance` kayıtları ve test dosyası commit edilmedi.
