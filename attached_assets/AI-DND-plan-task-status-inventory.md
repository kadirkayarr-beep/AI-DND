# AI-DND — Plan ve görev durum dökümü

## Kapsam ve doğruluk notu

Bu döküm, workspace'te bulunan görev dışa aktarımı (#1–#339), bu oturumda görünen güncel açık görevler (#467–#491) ve ekli plan metinlerinden hazırlanmıştır. **#340–#466 aralığının tam task kayıtları görünür kaynaklarda yok**; bu aralıktakileri tamamlandı/iptal diye varsaymadım. Eski dışa aktarım tarihsel bir anlık görüntüdür; özellikle eski PROPOSED kayıtlarının bugünkü tracker durumu ayrıca doğrulanamıyor.

Eski dışa aktarımda: **265 MERGED**, **52 CANCELLED**, **22 PROPOSED**. Bu 339 kayıtta ayrı bir DRAFT veya WAITING state yok. Güncel görünen açık listede **11 PROPOSED** ve **#491 IN_PROGRESS / WAITING_FOR_INPUT** var.

## A. Arşivdeki #1–#339 görevleri (numara sırasıyla)

| No | Dışa aktarımdaki durum | Başlık |
|---|---|---|
| #1 | MERGED — TAMAMLANDI/KATILDI | Keep separate adventures from sharing game state |
| #2 | MERGED — TAMAMLANDI/KATILDI | Keep legacy test setup from changing the default adventure |
| #3 | MERGED — TAMAMLANDI/KATILDI | Make older combat checks reliable again |
| #4 | MERGED — TAMAMLANDI/KATILDI | Catch combat dice leaking between adventures |
| #5 | MERGED — TAMAMLANDI/KATILDI | Catch dice-routing errors in the remaining adventure-isolation tests |
| #6 | MERGED — TAMAMLANDI/KATILDI | Catch dice crossing between simultaneous adventures |
| #7 | MERGED — TAMAMLANDI/KATILDI | Catch crossed damage dice when both adventures take hits |
| #8 | MERGED — TAMAMLANDI/KATILDI | Catch one adventure’s knockout affecting another |
| #9 | MERGED — TAMAMLANDI/KATILDI | Catch knockout status leaking between adventures after loading a save |
| #10 | MERGED — TAMAMLANDI/KATILDI | Catch players staying knocked out after loading a conscious save |
| #11 | MERGED — TAMAMLANDI/KATILDI | Confirm a failed load leaves every adventure unchanged |
| #12 | MERGED — TAMAMLANDI/KATILDI | Confirm unreadable saves leave every adventure unchanged |
| #13 | MERGED — TAMAMLANDI/KATILDI | Keep every adventure intact when a save write fails |
| #14 | MERGED — TAMAMLANDI/KATILDI | Keep other adventures' held references intact when a save is invalid |
| #15 | MERGED — TAMAMLANDI/KATILDI | Keep existing adventures intact when a save stops during writing |
| #16 | MERGED — TAMAMLANDI/KATILDI | Keep held adventure references intact when a different adventure loads successfully |
| #17 | MERGED — TAMAMLANDI/KATILDI | Keep explicit adventures intact when the default adventure rejects a save |
| #18 | MERGED — TAMAMLANDI/KATILDI | Keep adventure messages and dice streams untouched when loading a save |
| #19 | MERGED — TAMAMLANDI/KATILDI | Keep other adventures intact when the default adventure saves |
| #20 | MERGED — TAMAMLANDI/KATILDI | Confirm Turkish AI narration works with the live model |
| #21 | MERGED — TAMAMLANDI/KATILDI | Keep active adventures unchanged when loading the default adventure |
| #22 | CANCELLED — İPTAL | Restore broad Turkish AI behavior coverage for the current game |
| #23 | CANCELLED — İPTAL | Keep known landmarks from being mistaken for invented people |
| #24 | CANCELLED — İPTAL | Keep an invalid default load from changing any adventure |
| #25 | CANCELLED — İPTAL | Keep chat histories and dice unchanged during default saves |
| #26 | CANCELLED — İPTAL | Preserve other adventures when a default save fails |
| #27 | CANCELLED — İPTAL | Connect the verified game engine to a browser through a direct Python API |
| #28 | CANCELLED — İPTAL | Keep campaign progress after a server restart |
| #29 | CANCELLED — İPTAL | Apply the approved story-first design to the campaign browser |
| #30 | CANCELLED — İPTAL | Keep campaigns resumable after a game-server restart |
| #31 | CANCELLED — İPTAL | See the time-aware adventure in forests and city streets |
| #32 | CANCELLED — İPTAL | Let players resume campaigns after server restarts |
| #33 | CANCELLED — İPTAL | Let players create a character before starting a campaign |
| #34 | CANCELLED — İPTAL | Give campaigns a canonical world record in the next phase |
| #35 | CANCELLED — İPTAL | Add the deferred Journal and Quest views in a later phase |
| #36 | CANCELLED — İPTAL | Let the Journal track quests from confirmed game outcomes |
| #37 | CANCELLED — İPTAL | Kayıtlı çatışmayı açınca önceki zar sonuçlarını da göster |
| #38 | CANCELLED — İPTAL | Complete the remaining Phase 1 skill checks after approval |
| #39 | CANCELLED — İPTAL | Approve richer scene narration without changing game rules |
| #40 | CANCELLED — İPTAL | Make narration more vivid while keeping game rules authoritative |
| #41 | CANCELLED — İPTAL | Run all AI-DND checks without a test-runner crash |
| #42 | CANCELLED — İPTAL | Stop unsupported Forgotten Realms details from appearing as established facts |
| #43 | CANCELLED — İPTAL | Make supported Neverwinter questions answer across everyday wording |
| #44 | CANCELLED — İPTAL | Let players meet a local merchant without making it canon |
| #45 | CANCELLED — İPTAL | Make reviewed smoke runs show a clear pass |
| #46 | CANCELLED — İPTAL | Stop NPCs from sharing player names they have not been told |
| #47 | CANCELLED — İPTAL | Keep exact failure details in live-smoke reports |
| #48 | CANCELLED — İPTAL | Verify persistent narration evidence in an approved live V1.1 run |
| #49 | CANCELLED — İPTAL | Restore the character-creation flow’s generated API types and verify it |
| #50 | CANCELLED — İPTAL | Etkileşimli dünya olaylarına kurallara uygun sonuçlar ekle |
| #51 | CANCELLED — İPTAL | Let players interact with supported ambient events from the game screen |
| #52 | CANCELLED — İPTAL | Make Human and Half-Elf bonus features work in character creation |
| #53 | CANCELLED — İPTAL | Show every Fighter style and accurate HP/AC before starting |
| #54 | CANCELLED — İPTAL | Measure how players use ambient-event choices |
| #55 | CANCELLED — İPTAL | Make Aasimar, Goliath, and Orc abilities work during play |
| #56 | CANCELLED — İPTAL | Catch real-model misunderstandings of Turkish game commands |
| #57 | CANCELLED — İPTAL | Confirm real Ollama handles Turkish name and attack commands |
| #58 | CANCELLED — İPTAL | Let players choose and keep their Expertise skills |
| #59 | CANCELLED — İPTAL | Give stabilized characters a supported recovery path |
| #60 | CANCELLED — İPTAL | Canlı karşılaşmalarda eksik Monster Combat veri bağlantılarını tamamla |
| #61 | MERGED — TAMAMLANDI/KATILDI | Manuel push öncesi commit kaynağını açıklığa kavuştur |
| #62 | MERGED — TAMAMLANDI/KATILDI | Manuel push öncesi commit’i oluşturan işlemin kesin kaydını edin |
| #63 | MERGED — TAMAMLANDI/KATILDI | 563/563 test sonucunu özgün koşu kaydıyla doğrula |
| #64 | MERGED — TAMAMLANDI/KATILDI | Keep test-run evidence so reported results remain verifiable |
| #65 | MERGED — TAMAMLANDI/KATILDI | Make travel and invalid-target regression checks reliable again |
| #66 | MERGED — TAMAMLANDI/KATILDI | Prevent live HTTP checks from overwriting earlier acceptance evidence |
| #67 | MERGED — TAMAMLANDI/KATILDI | Catch travel commands that silently do nothing |
| #68 | CANCELLED — İPTAL | Identify the code version behind each future HTTP acceptance result |
| #69 | MERGED — TAMAMLANDI/KATILDI | Make combined regression runs reliable instead of failing on shared test mocks |
| #70 | MERGED — TAMAMLANDI/KATILDI | Keep interrupted returns from charging twice after a retry or campaign reload |
| #71 | CANCELLED — İPTAL | Keep interrupted reroutes from charging twice after reload or retry |
| #72 | MERGED — TAMAMLANDI/KATILDI | Keep older test scripts from breaking broader regression runs |
| #73 | MERGED — TAMAMLANDI/KATILDI | Repair the old combat test so it can check authoritative attacks again |
| #74 | CANCELLED — İPTAL | Bring the remaining old combat gates in line with current attack rules |
| #75 | CANCELLED — İPTAL | NPC’lerin gerçekten sahip oldukları eşyaları güvenle takas edebilmesi |
| #76 | CANCELLED — İPTAL | Zırh ve kalkan değişikliklerinin AC ve oyun süresini güvenle güncellemesi |
| #77 | MERGED — TAMAMLANDI/KATILDI | Restore reliable tests that campaigns cannot affect one another |
| #78 | MERGED — TAMAMLANDI/KATILDI | Catch attacks borrowing distance from another campaign |
| #79 | MERGED — TAMAMLANDI/KATILDI | Catch attacks borrowing visibility from another campaign |
| #80 | MERGED — TAMAMLANDI/KATILDI | Catch attacks borrowing hidden-attacker advantages from another campaign |
| #81 | MERGED — TAMAMLANDI/KATILDI | Catch attacks borrowing another campaign’s cover protection |
| #82 | MERGED — TAMAMLANDI/KATILDI | Catch attacks borrowing another campaign’s damage resistance |
| #83 | MERGED — TAMAMLANDI/KATILDI | Keep invalid cover in one campaign from disrupting another campaign’s attack |
| #84 | MERGED — TAMAMLANDI/KATILDI | Catch attacks borrowing another campaign’s guessed target location |
| #85 | MERGED — TAMAMLANDI/KATILDI | Catch attacks using visibility facts from the wrong direction |
| #86 | MERGED — TAMAMLANDI/KATILDI | Stop duplicated session tests from hiding regression checks |
| #87 | MERGED — TAMAMLANDI/KATILDI | Keep a reverse-direction location guess from making a valid attack miss |
| #88 | MERGED — TAMAMLANDI/KATILDI | Catch attacks consuming another campaign’s temporary HP |
| #89 | MERGED — TAMAMLANDI/KATILDI | Keep temporary-HP grants from refilling another campaign’s reserve |
| #90 | MERGED — TAMAMLANDI/KATILDI | Catch one campaign borrowing another player’s once-only survival ability |
| #91 | MERGED — TAMAMLANDI/KATILDI | Prevent regression checks from silently disappearing across the test suite |
| #92 | MERGED — TAMAMLANDI/KATILDI | Keep reverse-only location guesses from deciding an attack |
| #93 | MERGED — TAMAMLANDI/KATILDI | Keep one campaign’s rest from recharging another Orc’s ability |
| #94 | MERGED — TAMAMLANDI/KATILDI | Stop an exhausted Orc ability from borrowing another campaign’s remaining uses |
| #95 | MERGED — TAMAMLANDI/KATILDI | Prevent a fatal blow in one campaign from triggering another Orc’s survival ability |
| #96 | MERGED — TAMAMLANDI/KATILDI | Reject attacks when the only known distance is invalid |
| #97 | MERGED — TAMAMLANDI/KATILDI | Prevent standalone regression checks from being silently overwritten |
| #98 | MERGED — TAMAMLANDI/KATILDI | Keep retired prototype combat checks out of release results |
| #99 | MERGED — TAMAMLANDI/KATILDI | Prevent valid backup distances from hiding invalid attack geometry |
| #100 | MERGED — TAMAMLANDI/KATILDI | Keep interrupted rests from refreshing another campaign’s abilities |
| #101 | MERGED — TAMAMLANDI/KATILDI | Keep one campaign’s spent bonus action from blocking another Orc’s ability |
| #102 | MERGED — TAMAMLANDI/KATILDI | Prevent assignments from silently replacing regression checks |
| #103 | MERGED — TAMAMLANDI/KATILDI | Prevent an NPC’s backup distance from hiding an invalid attack distance |
| #104 | MERGED — TAMAMLANDI/KATILDI | Restore trustworthy combat release checks without weakening the rules |
| #105 | MERGED — TAMAMLANDI/KATILDI | Confirm city observation still returns a usable exploration result |
| #106 | MERGED — TAMAMLANDI/KATILDI | Keep interrupted long rests from healing or restoring another campaign’s spells |
| #107 | MERGED — TAMAMLANDI/KATILDI | Keep one species’ spent bonus action from blocking another campaign’s transformation |
| #108 | MERGED — TAMAMLANDI/KATILDI | Preserve NPC distance fallback when an attack pair omits distance |
| #109 | MERGED — TAMAMLANDI/KATILDI | Catch regression methods replaced after their class is defined |
| #110 | MERGED — TAMAMLANDI/KATILDI | Keep fatal-hit protection tied to each campaign’s temporary health |
| #111 | MERGED — TAMAMLANDI/KATILDI | Keep a fatal-hit rollback from restoring another campaign’s Orc abilities |
| #112 | MERGED — TAMAMLANDI/KATILDI | Keep one campaign’s fear transformation from affecting another campaign’s enemies |
| #113 | MERGED — TAMAMLANDI/KATILDI | Keep interrupted-rest health and spells unchanged after saving and reopening |
| #114 | MERGED — TAMAMLANDI/KATILDI | Let older saved battles resume without losing their turn |
| #115 | MERGED — TAMAMLANDI/KATILDI | Make combat narration clearly report when an enemy dies |
| #116 | MERGED — TAMAMLANDI/KATILDI | Keep malformed attack distances from being replaced by an NPC’s valid distance |
| #117 | MERGED — TAMAMLANDI/KATILDI | Keep city observation and discovery working after reopening a campaign |
| #118 | MERGED — TAMAMLANDI/KATILDI | Preserve fatal-hit outcomes and Orc survival uses after reopening campaigns |
| #119 | MERGED — TAMAMLANDI/KATILDI | Keep a fatal-hit rollback from restoring another campaign’s journal |
| #120 | MERGED — TAMAMLANDI/KATILDI | Catch regression tests lost through a class alias before checks run |
| #121 | MERGED — TAMAMLANDI/KATILDI | Keep malformed battle distances from bypassing checks through reverse enemy pairs |
| #122 | MERGED — TAMAMLANDI/KATILDI | Keep one campaign’s expiring fear from clearing another campaign’s enemies |
| #123 | MERGED — TAMAMLANDI/KATILDI | Keep interrupted-rest progress safe when saving fails |
| #124 | MERGED — TAMAMLANDI/KATILDI | Keep both campaigns safe when a death rollback checkpoint is rejected |
| #125 | MERGED — TAMAMLANDI/KATILDI | Keep an enemy’s fallback distance from hiding malformed reverse-pair geometry |
| #126 | MERGED — TAMAMLANDI/KATILDI | Make fatal enemy attacks clearly report the player’s death |
| #127 | MERGED — TAMAMLANDI/KATILDI | Confirm rejected test files cannot execute any gate in a real runner process |
| #128 | MERGED — TAMAMLANDI/KATILDI | Keep discovered tavern visits and city returns intact after reopening |
| #129 | MERGED — TAMAMLANDI/KATILDI | Keep spent actions spent when an older battle reopens |
| #130 | MERGED — TAMAMLANDI/KATILDI | Keep permanent-death outcomes intact after reopening campaigns |
| #131 | MERGED — TAMAMLANDI/KATILDI | Keep earlier combat results unchanged when the next turn runs |
| #132 | MERGED — TAMAMLANDI/KATILDI | Keep earned healing and spell recovery from surviving a failed rest save |
| #133 | MERGED — TAMAMLANDI/KATILDI | Keep fatal death-save results intact after reopening a campaign |
| #134 | MERGED — TAMAMLANDI/KATILDI | Keep valid enemy distances usable when reverse geometry omits distance |
| #135 | MERGED — TAMAMLANDI/KATILDI | Keep real gate failures from being reported as a successful test run |
| #136 | MERGED — TAMAMLANDI/KATILDI | Keep returning tavern visits on the same saved location |
| #137 | MERGED — TAMAMLANDI/KATILDI | Keep quest and story progress safe when a fatal turn cannot be saved |
| #138 | MERGED — TAMAMLANDI/KATILDI | Report every enemy attack when several enemies act in one turn |
| #139 | MERGED — TAMAMLANDI/KATILDI | Prevent conflicting saved action records from granting an extra action |
| #140 | MERGED — TAMAMLANDI/KATILDI | Keep every failed gate visible when several checks fail |
| #141 | MERGED — TAMAMLANDI/KATILDI | Keep enemy attacks working when player-side geometry omits distance |
| #142 | MERGED — TAMAMLANDI/KATILDI | Keep the player’s saved location unchanged when a tavern return cannot be saved |
| #143 | MERGED — TAMAMLANDI/KATILDI | Keep restored Orc abilities from surviving a failed short-rest save |
| #144 | MERGED — TAMAMLANDI/KATILDI | Keep replayed combat results unchanged after later turns |
| #145 | MERGED — TAMAMLANDI/KATILDI | Prevent reopening a campaign from rolling the same nonfatal death save twice |
| #146 | MERGED — TAMAMLANDI/KATILDI | Keep every invalid test visible before checks start |
| #147 | MERGED — TAMAMLANDI/KATILDI | Let a failed fatal turn be retried without losing progress or resolving twice |
| #148 | MERGED — TAMAMLANDI/KATILDI | Keep an unsaved tavern discovery from appearing after reopening |
| #149 | MERGED — TAMAMLANDI/KATILDI | Keep the player inside the tavern when an exit cannot be saved |
| #150 | MERGED — TAMAMLANDI/KATILDI | Show enemy attacks after the player explicitly ends a turn |
| #151 | MERGED — TAMAMLANDI/KATILDI | Reject malformed enemy attack distances without changing campaign state |
| #152 | MERGED — TAMAMLANDI/KATILDI | Keep a natural-20 revival intact after reopening a campaign |
| #153 | MERGED — TAMAMLANDI/KATILDI | Keep Orc abilities depleted when a short rest is interrupted |
| #154 | MERGED — TAMAMLANDI/KATILDI | Keep saved combat results safe when a caller edits a returned receipt |
| #155 | MERGED — TAMAMLANDI/KATILDI | Keep a stabilized player’s recovery deadline intact after reopening |
| #156 | MERGED — TAMAMLANDI/KATILDI | Restore reliable combat and narration regression checks |
| #157 | MERGED — TAMAMLANDI/KATILDI | Keep the documented API compatible with campaign clients |
| #158 | MERGED — TAMAMLANDI/KATILDI | Reject enemy attacks when the enemy’s saved distance is invalid |
| #159 | MERGED — TAMAMLANDI/KATILDI | Keep replay results unchanged when a caller edits the receipt supplied for saving |
| #160 | MERGED — TAMAMLANDI/KATILDI | Keep depleted Orc abilities unchanged when an interrupted rest cannot be saved |
| #161 | MERGED — TAMAMLANDI/KATILDI | Confirm test children use the chosen Python environment |
| #162 | MERGED — TAMAMLANDI/KATILDI | Keep an unsaved merchant discovery from appearing after reopening |
| #163 | MERGED — TAMAMLANDI/KATILDI | Prevent an older open campaign from undoing a saved tavern exit |
| #164 | MERGED — TAMAMLANDI/KATILDI | Keep an interrupted rest’s decision pending when saving the response fails |
| #165 | MERGED — TAMAMLANDI/KATILDI | Keep saved combat history unchanged when a caller edits its input |
| #166 | MERGED — TAMAMLANDI/KATILDI | Recover a failed fatal turn after reopening the campaign |
| #167 | MERGED — TAMAMLANDI/KATILDI | Keep valid enemy attacks working when older distance data is broken |
| #168 | MERGED — TAMAMLANDI/KATILDI | Keep cancelled recovery from returning after reopening |
| #169 | MERGED — TAMAMLANDI/KATILDI | Keep valid API formatting from causing false compatibility failures |
| #170 | MERGED — TAMAMLANDI/KATILDI | Show enemy attacks after the player resolves a readied reaction |
| #171 | MERGED — TAMAMLANDI/KATILDI | Stop further enemy attacks when a death save stabilizes the player |
| #172 | MERGED — TAMAMLANDI/KATILDI | Confirm listing test suites never starts a test |
| #173 | MERGED — TAMAMLANDI/KATILDI | Let an older open campaign continue safely after reopening |
| #174 | MERGED — TAMAMLANDI/KATILDI | Reject altered exit retries even from an older open campaign |
| #175 | MERGED — TAMAMLANDI/KATILDI | Keep a saved merchant from multiplying when searched for again |
| #176 | MERGED — TAMAMLANDI/KATILDI | Keep earlier city progress when a later merchant discovery cannot be saved |
| #177 | MERGED — TAMAMLANDI/KATILDI | Keep location questions factual even while talking to an NPC |
| #178 | MERGED — TAMAMLANDI/KATILDI | Keep earlier combat results unchanged when later turns reset resources |
| #179 | MERGED — TAMAMLANDI/KATILDI | Confirm unsupported suite names never start a test |
| #180 | MERGED — TAMAMLANDI/KATILDI | Keep the same saved merchant when players ask in different words |
| #181 | MERGED — TAMAMLANDI/KATILDI | Prevent damaged saved turn receipts from triggering another action |
| #182 | MERGED — TAMAMLANDI/KATILDI | Keep valid forward attacks working when reverse geometry is broken |
| #183 | MERGED — TAMAMLANDI/KATILDI | Keep earlier city progress when a tavern discovery cannot be saved |
| #184 | MERGED — TAMAMLANDI/KATILDI | Refresh remembered conversations when reopening an older campaign |
| #185 | MERGED — TAMAMLANDI/KATILDI | Keep permanent-death outcomes retryable after a failed save and reopening |
| #186 | MERGED — TAMAMLANDI/KATILDI | Keep a resolved rest encounter resolved when replaying the old rest |
| #187 | MERGED — TAMAMLANDI/KATILDI | Keep an interrupted rest decision pending when saving combat entry fails |
| #188 | MERGED — TAMAMLANDI/KATILDI | Keep recent combat results intact when older history rolls off |
| #189 | MERGED — TAMAMLANDI/KATILDI | Keep character facts accurate while talking to an NPC |
| #190 | MERGED — TAMAMLANDI/KATILDI | Keep scheduled recovery when healing restores no health |
| #191 | MERGED — TAMAMLANDI/KATILDI | Keep a new recovery deadline after damage and a second reopening |
| #192 | MERGED — TAMAMLANDI/KATILDI | Confirm missing test files stop every test before execution |
| #193 | MERGED — TAMAMLANDI/KATILDI | Return control immediately when a direct death save stabilizes the player |
| #194 | MERGED — TAMAMLANDI/KATILDI | Keep declined merchant searches from rediscovering a shop after reopening |
| #195 | MERGED — TAMAMLANDI/KATILDI | Keep a failed tavern search safely retryable after reopening |
| #196 | MERGED — TAMAMLANDI/KATILDI | Keep push effects from using the wrong direction’s clear path |
| #197 | MERGED — TAMAMLANDI/KATILDI | Catch mismatched death-save details before clients receive them |
| #198 | MERGED — TAMAMLANDI/KATILDI | Catch incompatible species-action requests and responses before release |
| #199 | MERGED — TAMAMLANDI/KATILDI | Keep a failed reaction response safely retryable without repeating enemy attacks |
| #200 | MERGED — TAMAMLANDI/KATILDI | Keep newer recovery intact when an older interrupted rest is retried |
| #201 | MERGED — TAMAMLANDI/KATILDI | Keep remembered disclosures private to the right NPC after reopening |
| #202 | MERGED — TAMAMLANDI/KATILDI | Prevent damaged rest and reaction receipts from repeating resolved actions |
| #203 | CANCELLED — İPTAL | Restore campaign test collection so persistence regressions can run normally |
| #204 | MERGED — TAMAMLANDI/KATILDI | Keep an interrupted rest unfinished when saving combat exit fails |
| #205 | MERGED — TAMAMLANDI/KATILDI | Keep older combat results when saving a new result fails |
| #206 | MERGED — TAMAMLANDI/KATILDI | Keep scheduled recovery intact when invalid healing is rejected |
| #207 | MERGED — TAMAMLANDI/KATILDI | Catch character-answer and NPC-memory regressions in release checks |
| #208 | CANCELLED — İPTAL | Stop all tests safely when a selected test file has unreadable text |
| #209 | MERGED — TAMAMLANDI/KATILDI | Keep a newly stable turn unchanged when retried after reopening |
| #210 | MERGED — TAMAMLANDI/KATILDI | Keep enemy pushes from using the player’s reverse clear path |
| #211 | MERGED — TAMAMLANDI/KATILDI | Keep a failed merchant search safely retryable after reopening |
| #212 | MERGED — TAMAMLANDI/KATILDI | Keep declined tavern searches from finding a tavern after reopening |
| #213 | MERGED — TAMAMLANDI/KATILDI | Keep later damage and spent resources intact when a completed rest is retried |
| #214 | MERGED — TAMAMLANDI/KATILDI | Catch species-action routes wired to the wrong contract before release |
| #215 | MERGED — TAMAMLANDI/KATILDI | Catch death-save responses linked to the wrong client schema |
| #216 | CANCELLED — İPTAL | Keep a failed readied movement safely retryable without changing attack distances |
| #217 | MERGED — TAMAMLANDI/KATILDI | Keep enemy-to-enemy pushes from reusing blocked reverse paths |
| #218 | MERGED — TAMAMLANDI/KATILDI | Prevent an older campaign session from duplicating a newly found merchant |
| #219 | MERGED — TAMAMLANDI/KATILDI | Keep spent Orc abilities spent when an older short rest is retried |
| #220 | MERGED — TAMAMLANDI/KATILDI | Keep natural-20 revival unchanged when retried after reopening |
| #221 | MERGED — TAMAMLANDI/KATILDI | Keep old combat commands from running again after their results leave history |
| #222 | MERGED — TAMAMLANDI/KATILDI | Restore reliable release checks for player knockouts |
| #223 | MERGED — TAMAMLANDI/KATILDI | Return a clear error when a saved action response is incomplete |
| #224 | MERGED — TAMAMLANDI/KATILDI | Catch turn routes linked to the wrong request or reply before release |
| #225 | MERGED — TAMAMLANDI/KATILDI | Keep unresolved rest encounters pending when their time window closes during combat |
| #226 | MERGED — TAMAMLANDI/KATILDI | Keep scheduled recovery intact when an invalid HP limit is rejected |
| #227 | MERGED — TAMAMLANDI/KATILDI | Keep tavern distance questions from triggering discovery after reopening |
| #228 | CANCELLED — İPTAL | Keep remembered names private when direct NPC memory is missing |
| #229 | MERGED — TAMAMLANDI/KATILDI | Catch enemy combat results linked to the wrong client schema |
| #230 | MERGED — TAMAMLANDI/KATILDI | Keep scheduled recovery on time after an accepted positive HP-limit change |
| #231 | MERGED — TAMAMLANDI/KATILDI | Run existing death-save safety checks during normal releases |
| #232 | MERGED — TAMAMLANDI/KATILDI | Keep a natural-1 death-save penalty from repeating after reopening |
| #233 | MERGED — TAMAMLANDI/KATILDI | Reject changed combat commands even after their history expires |
| #234 | MERGED — TAMAMLANDI/KATILDI | Keep city-ruler questions from becoming NPC identity answers after reopening |
| #235 | MERGED — TAMAMLANDI/KATILDI | Keep rest replay checks from failing when reopening updates the timestamp |
| #236 | MERGED — TAMAMLANDI/KATILDI | Keep expired rest encounters intact when saving the combat exit fails |
| #237 | MERGED — TAMAMLANDI/KATILDI | Catch session creation and resume routes linked to the wrong client schemas |
| #238 | MERGED — TAMAMLANDI/KATILDI | Keep repeated pushes from exceeding the remaining clear corridor |
| #239 | MERGED — TAMAMLANDI/KATILDI | Return a safe error when a saved event response is incomplete |
| #240 | MERGED — TAMAMLANDI/KATILDI | Confirm damaged in-memory action replies cannot repeat gameplay |
| #241 | MERGED — TAMAMLANDI/KATILDI | Keep a refreshed older session from duplicating a saved merchant |
| #242 | MERGED — TAMAMLANDI/KATILDI | Keep saved merchants intact if a recovered search cannot be saved |
| #243 | MERGED — TAMAMLANDI/KATILDI | Keep a completed push from authorizing movement in the opposite direction |
| #244 | MERGED — TAMAMLANDI/KATILDI | Check combat reply isolation even when reopening changes the timestamp |
| #245 | MERGED — TAMAMLANDI/KATILDI | Keep expired combat action IDs from being reused for rest commands |
| #246 | MERGED — TAMAMLANDI/KATILDI | Keep expired rest encounters unresolved when saving the final decision fails |
| #247 | MERGED — TAMAMLANDI/KATILDI | Keep a fatal death-save result from repeating after reopening |
| #248 | MERGED — TAMAMLANDI/KATILDI | Return safe errors when an in-memory action receipt loses its identity fields |
| #249 | MERGED — TAMAMLANDI/KATILDI | Keep personal NPC answers tied to the saved person after reopening |
| #250 | MERGED — TAMAMLANDI/KATILDI | Keep verified city-ruler answers available after reopening |
| #251 | MERGED — TAMAMLANDI/KATILDI | Keep saved event replies tied to the correct action and encounter |
| #252 | MERGED — TAMAMLANDI/KATILDI | Keep the original recovery time when stabilization is repeated after reopening |
| #253 | MERGED — TAMAMLANDI/KATILDI | Prevent release checks from passing when a scheduler suite runs no tests |
| #254 | MERGED — TAMAMLANDI/KATILDI | Keep Normal and Ironman fatal-save results unchanged after reopening |
| #255 | MERGED — TAMAMLANDI/KATILDI | Keep saved rest action IDs from being reused for combat after reopening |
| #256 | MERGED — TAMAMLANDI/KATILDI | Restore the standalone checks for verified city-ruler answers |
| #257 | MERGED — TAMAMLANDI/KATILDI | Confirm a new rest restores resources after resolving an expired combat interruption |
| #258 | MERGED — TAMAMLANDI/KATILDI | Keep personal answers from using an expired conversation after reopening |
| #259 | MERGED — TAMAMLANDI/KATILDI | Catch turn results linked to the wrong nested reply models |
| #260 | MERGED — TAMAMLANDI/KATILDI | Catch saved combat history linked to the wrong result model |
| #261 | MERGED — TAMAMLANDI/KATILDI | Keep recovered merchant searches from overwriting a newer campaign save |
| #262 | MERGED — TAMAMLANDI/KATILDI | Keep completed player–NPC pushes from permitting reverse movement |
| #263 | MERGED — TAMAMLANDI/KATILDI | Catch campaign creation and save routes linked to the wrong client schemas |
| #264 | MERGED — TAMAMLANDI/KATILDI | Catch campaign read routes linked to the wrong client response schemas |
| #265 | MERGED — TAMAMLANDI/KATILDI | Keep completed timed recovery from healing again after reopening |
| #266 | MERGED — TAMAMLANDI/KATILDI | Keep verified lore answers from bypassing unconscious-character restrictions |
| #267 | MERGED — TAMAMLANDI/KATILDI | Keep conflicting event retries safely rejected when a saved reply is damaged |
| #268 | MERGED — TAMAMLANDI/KATILDI | Keep malformed in-memory event receipts from repeating event outcomes |
| #269 | MERGED — TAMAMLANDI/KATILDI | Reject changed fatal-save retries after reopening without altering the accepted result |
| #270 | MERGED — TAMAMLANDI/KATILDI | Keep reverse pushes blocked after reopening a campaign |
| #271 | MERGED — TAMAMLANDI/KATILDI | Keep scheduler loading errors from producing a release-pass result |
| #272 | MERGED — TAMAMLANDI/KATILDI | Keep simultaneous retries of the same merchant search from running twice |
| #273 | MERGED — TAMAMLANDI/KATILDI | Keep saved rest IDs from triggering world events after reopening |
| #274 | MERGED — TAMAMLANDI/KATILDI | Keep a failed new rest retryable after an expired combat interruption |
| #275 | MERGED — TAMAMLANDI/KATILDI | Keep an expired conversation from overriding a newly selected person |
| #276 | MERGED — TAMAMLANDI/KATILDI | Keep conversation targeting correct at the expiry boundary |
| #277 | MERGED — TAMAMLANDI/KATILDI | Keep reopened combat replies safe from caller edits |
| #278 | MERGED — TAMAMLANDI/KATILDI | Keep verified lore answers blocked for dead characters |
| #279 | MERGED — TAMAMLANDI/KATILDI | Catch turn quest outcomes linked to the wrong reply model |
| #280 | MERGED — TAMAMLANDI/KATILDI | Catch campaign history lists linked to the wrong entry models |
| #281 | MERGED — TAMAMLANDI/KATILDI | Keep NPC push corridors invalidated after reopening |
| #282 | MERGED — TAMAMLANDI/KATILDI | Keep a new injury from reusing an already completed recovery timer |
| #283 | MERGED — TAMAMLANDI/KATILDI | Keep conflicting species-action retries rejected when a saved reply is damaged |
| #284 | MERGED — TAMAMLANDI/KATILDI | Keep damaged legacy event reservations from repeating gameplay |
| #285 | MERGED — TAMAMLANDI/KATILDI | Catch character setup routes linked to the wrong client replies |
| #286 | MERGED — TAMAMLANDI/KATILDI | Catch health routes linked to the wrong client reply |
| #287 | MERGED — TAMAMLANDI/KATILDI | Keep changed fatal-save retries rejected in Permadeath after reopening |
| #288 | MERGED — TAMAMLANDI/KATILDI | Reject damaged in-memory request hashes instead of reporting retry conflicts |
| #289 | MERGED — TAMAMLANDI/KATILDI | Keep every failed API gate visible in the release summary |
| #290 | MERGED — TAMAMLANDI/KATILDI | Catch campaign details linked to the wrong summary model |
| #291 | MERGED — TAMAMLANDI/KATILDI | Catch saved combat history that loses its validation rules |
| #292 | MERGED — TAMAMLANDI/KATILDI | Keep simultaneous first merchant searches from leaving duplicate shops |
| #293 | MERGED — TAMAMLANDI/KATILDI | Reject changed merchant-search retries after competing requests reuse one ID |
| #294 | MERGED — TAMAMLANDI/KATILDI | Keep saved world-event IDs from being reused for rests after reopening |
| #295 | CANCELLED — İPTAL | Catch character setup routes linked to the wrong client response models |
| #296 | MERGED — TAMAMLANDI/KATILDI | Catch health checks linked to the wrong client response model |
| #297 | MERGED — TAMAMLANDI/KATILDI | Keep a failed post-combat rest retryable after reopening again |
| #298 | MERGED — TAMAMLANDI/KATILDI | Keep reopened species-action replies safe from caller edits |
| #299 | MERGED — TAMAMLANDI/KATILDI | Keep pronoun-based greetings directed at the selected person |
| #300 | CANCELLED — İPTAL | Reject retries that redirect a saved personal answer to another person |
| #301 | MERGED — TAMAMLANDI/KATILDI | Keep pronoun-based conversations directed at the selected person |
| #302 | MERGED — TAMAMLANDI/KATILDI | Keep unknown named conversation targets from selecting someone else |
| #303 | MERGED — TAMAMLANDI/KATILDI | Keep API loading errors and assertion failures visible together |
| #304 | MERGED — TAMAMLANDI/KATILDI | Keep conflicting merchant retries rejected before recovery |
| #305 | MERGED — TAMAMLANDI/KATILDI | Keep a rest retryable when saving fails again after reopening |
| #306 | MERGED — TAMAMLANDI/KATILDI | Keep separate first merchant searches retryable after a save race |
| #307 | MERGED — TAMAMLANDI/KATILDI | Keep competing world events and rests from sharing one saved action ID |
| #308 | MERGED — TAMAMLANDI/KATILDI | Keep saved species replies safe from autosave input edits |
| #309 | MERGED — TAMAMLANDI/KATILDI | Keep partially marked dead characters from receiving verified lore answers |
| #310 | MERGED — TAMAMLANDI/KATILDI | Catch missing health-check success responses before clients ship |
| #311 | MERGED — TAMAMLANDI/KATILDI | Catch saved story history that silently drops required fields |
| #312 | MERGED — TAMAMLANDI/KATILDI | Keep pending death saves on schedule after reopening a newly injured character |
| #313 | MERGED — TAMAMLANDI/KATILDI | Keep valid older event results retryable at validation limits |
| #314 | MERGED — TAMAMLANDI/KATILDI | Keep conflicting turn retries rejected when a saved reply is damaged |
| #315 | MERGED — TAMAMLANDI/KATILDI | Keep conflicting unsaved-session retries rejected when a reply is damaged |
| #316 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Catch quest objective lists linked to the wrong client models |
| #317 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep fatal death-save retries valid when their combat has already ended |
| #318 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Catch campaign replies that stop requiring saved history lists |
| #319 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Catch campaign start choices linked to the wrong regions or locations |
| #320 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep unknown conversation targets from selecting the only nearby person |
| #321 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Catch damaged saved request hashes after reopening a campaign |
| #322 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Catch health replies that stop requiring correctly typed fields |
| #323 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep empty API suites visible alongside other failures |
| #324 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Catch campaign summaries that lose required or correctly typed details |
| #325 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep identical merchant retries replayable before recovery |
| #326 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep short rests retryable after repeated save failures and reopening |
| #327 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep first merchant searches retryable if saving fails again after recovery |
| #328 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep saved world-event replies safe from autosave input edits |
| #329 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep Ironman death restrictions ahead of verified lore answers |
| #330 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep competing world events and rests from overwriting saves opened separately |
| #331 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep health contract checks from flagging valid error responses |
| #332 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep pending failed death saves intact after reopening |
| #333 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep out-of-combat natural-twenty revival from restarting death saves after reopening |
| #334 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep older event retries valid when saved identity strings are empty |
| #335 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Catch saved combat history text fields changing to the wrong types |
| #336 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep changed combat commands rejected when their saved reply is damaged |
| #337 | PROPOSED — TASLAK/ÖNERİ, henüz başlamamış | Keep combat replay checks reliable when reopening updates campaign timestamps |
| #338 | CANCELLED — İPTAL | Catch missing or extra successful replies in character setup |
| #339 | CANCELLED — İPTAL | Keep exhausted push corridors blocked after reopening |

## B. Güncel task görünümünde açık olanlar

| No | Durum | Başlık |
|---|---|---|
| #467 | PROPOSED | Catch contract-check slowdowns before release validation times out |
| #468 | PROPOSED | Explain invalid YAML mapping keys instead of crashing the contract reader |
| #481 | PROPOSED | Prevent completed checks from leaving background work running |
| #482 | PROPOSED | Catch character-creation responses that advertise unsupported fields |
| #483 | PROPOSED | Keep unused world-event and rest retries rejected until the stale session is reopened |
| #485 | PROPOSED | Keep losing reaction choices rejected before reopening a stale campaign |
| #486 | PROPOSED | Keep natural-20 revivals retryable when a campaign save fails |
| #487 | PROPOSED | Keep rest and event retries safe when an evicted receipt cannot be read |
| #488 | PROPOSED | Catch saved replies with valid JSON but the wrong top-level shape |
| #489 | PROPOSED | Keep prone readied movement within its speed limit across retries |
| #490 | PROPOSED | Keep conflicting death markers rejected after reopening a campaign |
| #491 | IN_PROGRESS — WAITING_FOR_INPUT | Keep ability-check turns retryable when SQLite rejects a save |

## C. Ekli planlarda ayrıca belirtilen eski iptal kayıtları

Bir sonraki görev promptunda aşağıdaki eski iptal planları yeniden seçilmiş ve tamamlanması/doğrulanması istenmiş. Bu, önceki CANCELLED durumunu değiştirildiği veya işin sonradan tamamlandığı anlamına tek başına gelmez; o sonraki çalışmanın final task-state kaydı görünür kaynaklarda yok.

- **#25** — Açık session kaydederken mesajları ve RNG'yi koru. Task dışa aktarımındaki başlık: “Keep chat histories and dice unchanged during default saves.”
- **#60** — Canlı karşılaşmalarda eksik Monster Combat veri bağlantılarını tamamla.
- **#76** — Zırh/kalkan giyme-çıkarma davranışını AC, oyun zamanı, kaynaklar ve kayıtla tutarlı yap.
- **#216** — Başarısız readied movement kaydı tekrar denenebilir olsun; saldırı mesafeleri değişmesin.
- **#228** — Yeniden açılan kampanyada NPC'ye özel isim bilgisini yalnızca doğru NPC'de tut.
- **#300** — Kaydedilmiş kişisel yanıtı aynı action ID ile başka hedefe yönlendiren tekrar denemeyi reddet.
- **#340** — Yolculuk zarları başarısız olsa da zindan kontrolleri test edilebilir kalsın; gerçek browser flow ile doğrula. Ekli seçim promptu bunu iptal planlarından biri olarak yeniden kapsama aldı; güncel sonuç kaydı görünmüyor.
- **#436** — Aynı promptta açıkça kapsam dışı bırakılmış; iş listesine alınmadı.

Ekli ilk plan dosyasında ayrıca **#339 CANCELLED** ve **#340 Plan** metinleri var. #339'un iptali #1–#339 dışa aktarımında da doğrulanıyor.

## D. Durumların anlamı

- **MERGED:** görev kaydında birleştirilmiş/tamamlanmış olarak işaretli.
- **CANCELLED:** o task kaydı iptal edilmiş.
- **PROPOSED:** öneri/taslak; başlamış veya tamamlanmış sayılmaz.
- **IN_PROGRESS — WAITING_FOR_INPUT:** sürüyor, fakat kullanıcı girdisi bekliyor.
- **Kayıt yok:** tamamlandı veya iptal edildi anlamına gelmez; bu dökümde durumu doğrulanamıyor.
