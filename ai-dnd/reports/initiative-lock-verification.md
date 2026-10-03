# Initiative Lock — kanıt raporu

## A) IMPLEMENTED

Salt okunur denetim mevcut sıra, round, RNG, oyuncu öncelikli eşitlik, Death
boundary ve receipt altyapısını doğruladı. Eksik parçalar mevcut combat kaydına
eklendi; ikinci combat/scheduler/persistence sistemi oluşturulmadı.

Kaynaklar: yüklenen 2024 PHB, Initiative (basılı s.23; PDF s.22) ve
Incapacitated glossary; 2024 MM, Initiative (basılı s.7; PDF s.10); 2024 DMG,
Rolling Initiative/Using Initiative Scores (basılı s.42; PDF s.45).

- Combat sahibi başlangıcı onayladıktan sonra mevcut RNG ve ortak d20 resolver
  kullanılır. Oyuncunun Dexterity modifier'ı, NPC'nin authoritative Initiative
  modifier'ı ve kaynaklı ek modifier'lar ayrı kaydedilir.
- Ham zarlar, seçilen zar, Advantage/Disadvantage kaynakları, iptal bilgisi,
  Surprise, grup ve stat-block bağlamı mevcut combat kaydında tutulur.
- 2024 Surprise ve Initiative anındaki Incapacitated Disadvantage verir;
  Surprise ilk turu atlatmaz. Sonraki condition/modifier değişimi reroll yapmaz.
- Açık grup ve stat-block kimliği bulunan, aynı roll kurallarına sahip
  yaratıklar tek zar paylaşır. Benzer isim/role otomatik grup oluşturmaz.
- Sıra yüksekten düşüğe; mixed tie'da player, diğer eşitliklerde actor ID.
  Eşitlik çözümü RNG tüketmez.
- Engine-only ON_INITIATIVE_ROLL, AFTER_INITIATIVE_ROLL ve
  AFTER_INITIATIVE_ORDER_INITIALIZED bağlantıları; kaynaklı count adjustment
  ve willing/same-side/Incapacitated kontrolü olan swap desteklenir.
- Yeni katılanın sonucu hesaplanır, mevcut sonuçlar reroll olmaz. Aynı mevcut
  gruba katılım canonical grup sonucunu paylaşır. Current actor ve kaynakları
  korunur. Önüne eklenen katılımcı sonraki round'u bekler; sonrasına eklenen
  bu round'da oynayabilir.
- Ayrılma kalan sayıları korur; current actor ayrılırsa turn boundary mevcut
  scheduler/Action Economy üzerinden yürür. Son rakip ayrılırken mevcut
  Combat/Death sahibi kapanış veya player-only death_resolution kararını verir.
- 0 HP/unconscious slot seçimi ile savaşabilecek rakip bulunması ayrıldı.
  Böylece bilinçsiz slot korunurken mevcut no-active-opponents kapanışı bozulmaz.
- Geçersiz sıra/cursor/kimlik/zar/audit tutarsızlığı açıkça reddedilir;
  sessiz reroll veya sahte düzeltme yoktur.

Tam dosya listesi F bölümündedir.

## B) VERIFIED

| Kontrol | Sonuç |
|---|---|
| Yeni Initiative testleri | 73/73 |
| Action Economy testleri | 38/38 |
| Combat lifecycle, species, Death, Campaign Time, edge cases, persistence regresyonları | 84/84 |
| Toplu Python çalıştırması | 195/195 |
| Experience testleri | 41/41 |
| Python compileall | Geçti |
| Experience typecheck | Geçti |
| git diff --check | Geçti |
| OpenAPI/codegen | Uygulanabilir değil: dış API sözleşmesi değiştirilmedi |
| Production build | Uygulanabilir değil: frontend/build girdileri değiştirilmedi |

Komutlar:

```sh
cd ai-dnd
python -m unittest api.tests.test_initiative.InitiativeTests api.tests.test_initiative.InitiativeApiTests api.tests.test_action_economy.ActionEconomyTests api.tests.test_action_economy.ActionEconomyApiTests api.tests.test_combat_lifecycle api.tests.test_species_traits api.tests.test_death_system api.tests.test_campaign_time api.tests.test_campaign_time_edges api.tests.test_campaign_persistence -q
python -m compileall -q initiative.py action_economy.py combat_lifecycle.py game.py api
python -m unittest test_combat_v2 test_combat_v2_authoritative -q
# Workspace root:
pnpm --filter @workspace/ai-dnd-experience run typecheck
pnpm --filter @workspace/ai-dnd-experience test
git diff --check
```

73 yeni test; dice/modifier/Advantage/Surprise/group/tie, turn/round/reset,
player ve NPC unconscious boundary, newcomer/departure, feature hooks,
save/resume, session isolation ve integrity senaryolarını kapsar.

JSON save/load grup, sıra, cursor ve RNG'yi aynen korudu. SQLite resume combat
audit ve receipt'i korudu. Tekrarlanan combat-start ve turn receipt aynı yanıtı
döndürdü; yeniden zar/round ilerlemesi olmadı. Zorlanan autosave failure state,
RNG ve receipt'i geri aldı. Qwen whitelist ve HTTP ekstra alan/command reddi
Initiative değişimini engelledi.

Kontrollü HTTP test loglarında 0 veya 1 model çağrısı görüldü. Model entegrasyonu
değiştirilmedi; mevcut 2 çağrı üst sınırı korunuyor. Canlı Qwen smoke çalıştırılmadı.

FastAPI workflow yeniden başlatıldı ve temiz açıldı. Experience başlangıç
ekranı görüntülendi; gerçek preview rotaları
/ai-dnd-experience/api/game/health ve /ai-dnd-experience/api/game/campaigns 200 döndü.

## C) NOT IMPLEMENTED / OUT OF SCOPE

#01 Campaign Time V1, #02 Campaign Time Edge Cases, #03 Combat Design Lock,
#04 Action Economy, #06 Weapon & Attack, #07 Monster Combat, #08 Death System,
#09 Spell Scope, #10 Combat Test Matrix, #11 Persistence/Idempotency architecture
ve #12 UI Presentation yeniden tasarlanmadı. Gerekli membership/death boundary
bağlantıları mevcut sahipler üzerinden kuruldu.

Alert, Feral Instinct, Gloom Stalker ve Bard özelliklerinin gerçek mekanikleri
bu işte uygulanmadı: mevcut feat/class mekaniği sahibi yok; genel authoritative
bağlantılar sağlandı. Stealth/awareness sistemi ve Initiative Score modu eklenmedi.
Stat-block score yalnız audit bilgisi; canonical mode gerçek zar.

## D) KNOWN LIMITATIONS

- Surprise için trusted authoritative başlangıç bilgisi gerekir; anlatımdan veya
  frontend'den Surprise üretilmez. Awareness/Stealth sistemi eklenmedi.
- NPC unconscious boundary korunur ve otomatik atlanmaz. NPC death-save/recovery
  mekanikleri eklenmedi; bu slot mevcut/future Death sahibinin işlemine açıktır.
- Legacy kayıtta integer Initiative toplamları varsa newcomers desteklenir;
  geçmiş zarlar uydurulmadan legacy_preserved etiketiyle saklanır. Toplamları null
  olan eski encounter'a ekleme açıkça reddedilir; mevcut sıra reroll yapılmaz.
- Ayrı eski V2 paketinde 51 testten 45'i geçti, aynı 6 eski başarısızlık sürdü:
  test_ambiguous_attack_in_player_turn_keeps_attack_clarification,
  test_initiative_npc_higher, test_wrong_location_blocked, test_Q_location_change,
  test_V3_legacy_turn_boundary_migrates_without_losing_cursor,
  test_npc_knocks_out_player. Önceki Action Economy raporunda baseline başarısızlığı
  olarak doğrulanmışlardı. Bütün deponun yeşil olduğu iddia edilmiyor.
- Önizleme çalışırken kök /favicon.ico 502 döndü; UI/root routing bu işte değişmedi.

## E) SCOPE CHECK

Python authority, D&D 2024 kaynakları, Qwen/frontend sınırları, mevcut Initiative
RNG, action receipt ve rollback, session isolation, Campaign Time, Combat
lifecycle, Action Economy, Death System, save/resume, doğal dil girdisi,
player agency ve tur başına en fazla 2 model çağrısı korunmuştur.

01–05 COMPLETE. #06 başlatılmadı; sonraki kilitlere geçilmedi.

## F) FILE DIFF SUMMARY

**Production:**
- ai-dnd/initiative.py — Initiative audit/rules, trusted hooks, membership ve atomic error rollback.
- ai-dnd/game.py — mevcut start/scheduler/validation/lifecycle bağlantıları.
- ai-dnd/action_economy.py — aynı resource factory kullanılarak yeni actor initialization.

**Test:**
- ai-dnd/api/tests/test_initiative.py — 73 focused test.
- ai-dnd/api/tests/test_combat_lifecycle.py — tek fixture düzeltmesi: NPC-first
  senaryosundaki player toplamı artık Dex + minimum geçerli d20 değeridir;
  mevcut sonuç beklentisi değiştirilmedi.

**Generated:** Yeni değişiklik yok.

**Documentation:**
- ai-dnd/reports/initiative-lock-verification.md
- .agents/memory/initiative-boundaries.md
- .agents/memory/MEMORY.md

Initiative öncesi çalışma ağacında Action Economy değişiklikleri zaten vardı.
Başlangıç dosya kopyalarıyla karşılaştırıldığında game.py +60/-31,
action_economy.py +21/-9 Initiative değişikliğidir. Önceden bulunan API
schema/serializer, Experience UI/tests, OpenAPI/generated client/Zod,
Action Economy test/rapor/dosyaları ve yüklenen promptlar bu işin yeni farkı
değildir. API schema/serializer, OpenAPI spec ve combat panel başlangıç
kopyalarıyla byte-identical doğrulandı. İlgisiz yeni değişiklik yapılmadı.