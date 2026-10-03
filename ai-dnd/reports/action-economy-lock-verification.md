# Action Economy Lock — doğrulama raporu

## A) IMPLEMENTED

PHB 2024 esas alınarak mevcut combat state içine yaratık başına tur kaynakları eklendi. Ayrı bir çatışma, kayıt, zar veya LLM sistemi oluşturulmadı.

- Bir normal Action; kaynağı ve izin verilen Action türleri belli ek Action grant'ları.
- Attack Action içinde sunucu tarafından tanımlanabilen saldırı sayısı; ikinci saldırı ikinci Action değildir. Bu bir gelecek kural bağlantısıdır, Extra Attack sınıf özelliği uygulaması değildir.
- Yalnızca mevcut tür kuralları veya sunucu grant'ları tarafından verilen tek Bonus Action; Action öncesi ve sonrası kullanım.
- Reaction yalnızca gerçek, Python tarafından çözülen olaydan doğan fırsatla kullanılır; kendi tur başlangıcında yenilenir. Mevcut Stone Giant hasar azaltımı aynı Reaction kaynağını kullanır.
- Ortak hareket maliyeti, parçalı hareket, Dash, Speed değişiklikleri ve Prone maliyeti. Dash kalıcı Speed'i değiştirmez.
- Ready: bir Action veya hareket yanıtı, gerçek hareket/saldırı tetikleyicisi, Reaction maliyeti ve sonraki kendi turunda sona erme. NPC zamanlayıcısı oyuncunun gerçek Ready fırsatında durur, kullanma/atlama sonrasında ilerler.
- Büyü sistemi uygulanmadan, Action casting metadata'sını koruyan engine-only Ready spell bağlantı noktası.
- Yapılandırılmış adımlar ile desteklenen doğal dil dizileri aynı kaynak, hedef ve durum kontrollerini kullanır.
- Geçersiz dizi bütün halinde geri alınır. Mevcut HTTP turn-action receipt, request-hash conflict ve atomik autosave kullanılır.
- Arayüz sunucu kaynaklarını, Ready fırsatını ve doğrulanmış zar sonuçlarını gösterir. Zar veya hareket bütçesi üretmez.
- Önceki tek serbest-metin saldırı/otomatik tur tamamlama davranışı korunur. Yeni yapılandırılmış ve birleşik hamlelerde tur açık kalır, End Turn ile tamamlanır.

## B) VERIFIED

Son çalıştırmalar:

| Kontrol | Sonuç |
|---|---|
| Yeni Action Economy Python testleri | 38/38 geçti |
| İlgili mevcut Python regresyonları | 84/84 geçti |
| Experience arayüz testleri | 41/41 geçti |
| Python compileall | Geçti |
| Experience TypeScript kontrolü | Geçti |
| OpenAPI Orval codegen ve ortak library typecheck | Geçti |
| Experience production build | Geçti; sourcemap/chunk-size uyarıları var |
| git diff --check | Geçti |
| Çalışan Experience önizleme | Açılış ekranı görüntülendi |
| Yeni yapılandırılmış HTTP hamleleri | Test loglarında 0 chat model çağrısı |

Komutlar:

```sh
cd ai-dnd
python -m unittest api.tests.test_action_economy.ActionEconomyTests api.tests.test_action_economy.ActionEconomyApiTests -q
python -m unittest api.tests.test_combat_lifecycle api.tests.test_species_traits api.tests.test_death_system api.tests.test_campaign_time api.tests.test_campaign_time_edges api.tests.test_campaign_persistence -q
python -m compileall -q action_economy.py game.py combat_lifecycle.py api
# Workspace root:
pnpm --filter @workspace/api-spec run codegen
pnpm --filter @workspace/ai-dnd-experience run typecheck
PORT=22785 BASE_PATH=/ai-dnd-experience/ pnpm --filter @workspace/ai-dnd-experience run build
pnpm --filter @workspace/ai-dnd-experience test
git diff --check
```

İstenen 41 maddelik matrisin kanıt grupları:

- 1–4: başlangıç, valid miss tüketimi, hatalı hedef ve atomik dizi geri alma.
- 5–8: grant olmadan Bonus yok, tek Bonus, Orc Action/Bonus sıraları.
- 9–13: sahte fırsat reddi, kendi/başka turdaki Ready, çift kullanım reddi, round değişimi ile kendi tur başlangıcının ayrılması.
- 14–19: move–attack–move, Dash, ek Dash grant'ı, Speed değişiklikleri, kalıcı Speed'in korunması.
- 20: engine-only attacks-per-Action ve devam saldırısında Action maliyetinin sıfır olması.
- 21–27: Ready kaydı, Action maliyeti, hareket yanıtı, Bonus yanıtının reddi, gerçek olay, doğru expiry, Prone maliyeti.
- 28–30: kaynaklı/kısıtlı grant ve Incapacitated/Unconscious kontrolleri; NPC'nin eylemini atlaması.
- 31: aynı hareket/saldırı dizisinin doğal dil ve yapılandırılmış sonuçlarının eşitliği.
- 32–35: replay, değişen payload conflict, SQLite resume ve zorlanmış autosave failure.
- 36: bağımsız oturumun kaynakları/fırsatlarının değişmemesi.
- 37: yapılandırılmış hamlelerde sıfır model çağrısı; mevcut iki çağrı üst sınırı kodu değiştirilmedi.
- 38–41: mevcut Combat lifecycle, Campaign Time, edge-case ve Death System regresyonları.

### Ayrı eski V2 paketinin durumu

`test_combat_v2` ve `test_combat_v2_authoritative` birlikte 51 testtir: 45 geçti, 6 başarısız. Aynı altı test değişiklik öncesi HEAD motoru `/tmp` altında izole yüklenerek de başarısız bulundu. Bunlar yeni 84/84 regresyon sonucuna dahil edilmemiştir; bütün depo testlerinin yeşil olduğu iddia edilmez:

- `test_ambiguous_attack_in_player_turn_keeps_attack_clarification`
- `test_initiative_npc_higher`
- `test_wrong_location_blocked`
- `test_Q_location_change`
- `test_V3_legacy_turn_boundary_migrates_without_losing_cursor`
- `test_npc_knocks_out_player`

## C) NOT IMPLEMENTED / OUT OF SCOPE

Combat lifecycle, Initiative, Weapon/Attack, Monster Combat, Death System, Spells, tam Combat Test Matrix, persistence mimarisi, UI presentation mimarisi, Campaign Time ve Campaign Time Edge Cases yeniden tasarlanmadı.

Ek Action ve attacks-per-Action mekanizmaları gelecekteki kurallara bağlantıdır; Action Surge, Haste veya Extra Attack sınıf/büyü özellikleri uygulanmadı. Yeni spell, monster stat block veya condition engine oluşturulmadı. Initiative aşamasına başlanmadı.

## D) KNOWN LIMITATIONS

- Ready'nin bağlı gerçek olayları `actor_moves` ve tamamlanmış `actor_attacks` ile sınırlıdır. Grid, mesafe tabanlı opportunity attack ve genel olay dili uygulanmadı.
- Mekaniği bağlanmayan Action aileleri açıkça unavailable olarak döner; Dodge/Help vb. için hayali etkiler uygulanmaz.
- Hareket için ölçülebilir mesafe gerekir; belirsiz birleşik komutlar tahmini mesafe üretmeden reddedilir.
- Ready büyü metadata'sı korunabilir; büyü çözümü ve concentration bu aşamada uygulanmaz.
- Legacy tek saldırı otomatik tur tamamlama davranışı, yeni açık-tur adımlarından farklı bir uyumluluk davranışıdır.
- Eski V2 paketindeki yukarıdaki altı mevcut hata sürer.
- Gerçek tarayıcıyla kontrol akışını tıklayan E2E çalıştırılmadı. Arayüz SSR testleri, HTTP transaction testleri ve açılış önizlemesi doğrulandı.

## E) SCOPE CHECK

Python mekanik otoritesi, Qwen'in otorite dışı sınırı, frontend'in yalnızca sunucu sonucunu göstermesi, maksimum iki chat çağrısı, oturum ayrımı, Campaign Time V1/edge-case kuralları, Combat Design Lock, Death System, persistence, idempotency ve doğal dil oyuncu girdisi korundu. Yeni model entegrasyonu veya ikinci kampanya/kayıt sistemi kurulmadı.

## F) FILE DIFF SUMMARY

**Production**

- `ai-dnd/action_economy.py` — yeni ortak kaynak doğrulama ve mekanik bağlantıları.
- `ai-dnd/game.py` — mevcut başlangıç/ilerleme/attack/species/NPC zamanlayıcısı bağlantıları.
- `ai-dnd/combat_lifecycle.py` — ek Action'ları erken legacy guard ile engellememe.
- `ai-dnd/api/main.py` — mevcut turn işlemine yapılandırılmış payload ve fingerprint ekleme.
- `ai-dnd/api/schemas.py` — input ve authoritative output sözleşmesi.
- `ai-dnd/api/serializers.py` — kaynak projeksiyonu ve doğrulanmış economy history.
- `ai-dnd/api/persistence/campaign_validation.py` — economy history türünü mevcut validator'a ekleme.
- `artifacts/ai-dnd-experience/src/components/action-economy-panel.tsx` — küçük sunucu-kaynaklı kontrol bölümü.
- `artifacts/ai-dnd-experience/src/components/combat-panel.tsx` — nested sunucu attack sonuçları.
- `artifacts/ai-dnd-experience/src/lib/combat-history.ts` — yeni history türünün restore/dedup desteği.
- `artifacts/ai-dnd-experience/src/pages/game-browser.tsx` — aynı mutation/UUID retry akışından structured command gönderimi.
- `lib/api-spec/openapi.yaml` — sözleşmenin kaynağı.

**Tests**

- `ai-dnd/api/tests/test_action_economy.py` — 38 focused test.
- `artifacts/ai-dnd-experience/tests/combat-panel.test.mjs` — mevcut Death projection fixture'ının tamamlanması ve iki focused kaynak/history testi.

**Generated**

- `lib/api-client-react/src/generated/api.schemas.ts`
- `lib/api-zod/src/generated/api.ts`
- `lib/api-zod/src/generated/types/combatTurnResult.ts`
- `lib/api-zod/src/generated/types/gameCombat.ts`
- `lib/api-zod/src/generated/types/gameTurnInput.ts`
- `lib/api-zod/src/generated/types/index.ts`
- Yeni types: `combatActionInput.ts`, `combatTurnResultEconomyStepsItem.ts`, `economyStepInput.ts`, `economyStepInputKind.ts`, `economyStepInputResource.ts`, `gameCombatActionEconomy.ts`, `readyResponseInput.ts`, `readyResponseInputKind.ts`, `readyTriggerInput.ts`, `readyTriggerInputEvent.ts`.

**Documentation**

- Bu rapor.
- `.agents/memory/action-economy-compatibility.md` ve memory index bağlantısı.

**Unrelated**

Ekli Action Economy ve Initiative talimat dosyaları kullanıcı girdisidir; değiştirilmedi. Initiative dosyasından uygulama çalışması yapılmadı. İlgisiz production değişikliği yapılmadı.