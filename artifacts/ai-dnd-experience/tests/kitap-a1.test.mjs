// A1 Oturum 1 (book UI theme set): the three book themes, the drawing folder, the book shell and the base controls,
// rendered from the real modules (vite ssrLoadModule + renderToStaticMarkup, the pattern of tests/dilim0-ui.test.mjs).
// Keyboard movement comes from Radix (roving focus); here the roles and names it needs are pinned.
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4192';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

const root = path.join(process.cwd(), 'src');
const read = (rel) => readFileSync(path.join(root, rel), 'utf8');
const css = read('index.css');

let vite, React, render, tema, kitap, kontrol, yazma, ayar;
before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  tema = await vite.ssrLoadModule('/src/lib/kitap-tema.ts');
  kitap = await vite.ssrLoadModule('/src/components/kitap/kitap-kabugu.tsx');
  kontrol = await vite.ssrLoadModule('/src/components/kitap/kontroller.tsx');
  yazma = await vite.ssrLoadModule('/src/components/kitap/yazma-alani.tsx');
  ayar = await vite.ssrLoadModule('/src/components/kitap/arayuz-ayarlari.tsx');
  React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  render = (type, props, ...children) => renderToStaticMarkup(React.createElement(type, props, ...children));
});
after(async () => { await vite?.close(); });

/** The rule block of one selector, comments removed. */
function block(selector) {
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const at = bare.indexOf(`${selector} {`);
  assert.notEqual(at, -1, `${selector} is missing from src/index.css`);
  return bare.slice(at, bare.indexOf('}', at));
}
const token = (body, name) => new RegExp(`${name}:\\s*([^;]+);`).exec(body)?.[1]?.trim();

// Decision document, section 5 (KITAP_YONU_TASLAK_KARARLARI_20261113.md), and kaynak/Main.dc.html for the rest.
const PALETTE = {
  gunduz: { '--sayfa': '#DCD8C8', '--murekkep': '#26211A', '--soluk': '#4A4439', '--hakem': '#1D5145', '--mum': '#603F08', '--cizgi': '#B4AE9B', '--bez': '#2D4A44', '--mum-cizgi': '#8C846E' },
  gece: { '--sayfa': '#D4C394', '--murekkep': '#1F1810', '--soluk': '#30281B', '--hakem': '#0F362E', '--mum': '#4D3003', '--cizgi': '#8E7F56', '--bez': '#1F2C29', '--mum-cizgi': '#75683F' },
  karanlik: { '--sayfa': '#11161B', '--murekkep': '#E6DFCE', '--soluk': '#A9A595', '--hakem': '#7DB5A8', '--mum': '#D9A441', '--cizgi': '#2E3840', '--bez': '#1B2C2A', '--mum-cizgi': 'transparent' },
};

test('three book themes carry the decision document values under [data-kitap-tema], the seal red is shared', () => {
  for (const [name, values] of Object.entries(PALETTE)) {
    const body = block(`[data-kitap-tema="${name}"]`);
    for (const [variable, value] of Object.entries(values)) {
      assert.equal(token(body, variable)?.toUpperCase(), value.toUpperCase(), `${name} ${variable}`);
    }
  }
  assert.equal(token(block('[data-kitap-tema]'), '--muhur')?.toUpperCase(), '#A8332E');
});

test('old screens are untouched: the book tokens never sit on :root and the --unw night base keeps its values', () => {
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, '');
  for (const name of ['--sayfa', '--murekkep', '--soluk', '--mum', '--mum-cizgi', '--hakem']) {
    const rules = [...bare.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(([, , body]) => new RegExp(`(^|[;\\s])${name}:`).test(body));
    assert.ok(rules.length > 0, `${name} is defined`);
    for (const [, selector] of rules) assert.match(selector.trim(), /^\[data-kitap-/, `${name} leaks outside the book scope: ${selector.trim()}`);
  }
  assert.equal(token(block(':root,\n:root[data-unw-theme="night"]'), '--unw-page'), '#11161B');
});

test('type: Literata body 19px (21px large), hand face per choice, paper grain tile per theme, effects off drops the grain', () => {
  const base = block('[data-kitap-tema]');
  assert.match(token(base, '--kitap-yazi') ?? '', /^'Literata'/);
  // 19px and 21px up to 1440px wide; --buyume (finding 5) is 0px there and grows the type only on wider screens.
  assert.equal(token(base, '--govde'), 'calc(19px + var(--buyume))');
  assert.equal(token(block('[data-kitap-boy="buyuk"]'), '--govde'), 'calc(21px + var(--buyume))');
  assert.match(token(base, '--buyume') ?? '', /^clamp\(0px, calc\(\(100vw - 1440px\) \* [0-9.]+\), [0-9]+px\)$/);
  assert.match(token(block('[data-kitap-el="b"]'), '--el-aile') ?? '', /^'Kalam'/);
  assert.match(token(block('[data-kitap-el="a"]'), '--el-aile') ?? '', /^'Charm'/);
  assert.match(token(block('[data-kitap-el="c"]'), '--el-aile') ?? '', /^'Bad Script'/);
  assert.equal(token(block('[data-kitap-el="b"]'), '--elb'), '20px');
  assert.equal(token(block('[data-kitap-el="a"]'), '--elb'), '23px');
  assert.equal(token(block('[data-kitap-el="c"]'), '--elb'), '21px');
  assert.match(token(block('[data-kitap-tema="gunduz"]'), '--tane') ?? '', /cizimler\/kagit-tanesi-koyu\.png/);
  assert.match(token(block('[data-kitap-tema="gece"]'), '--tane') ?? '', /cizimler\/kagit-tanesi-koyu\.png/);
  assert.match(token(block('[data-kitap-tema="karanlik"]'), '--tane') ?? '', /cizimler\/kagit-tanesi-acik\.png/);
  assert.equal(token(block('[data-kitap-tema][data-kitap-efekt="kapali"]'), '--tane'), 'none');
});

test('appearance choice: four options, story clock by default, the clock only decides when it is chosen', () => {
  assert.deepEqual(tema.GORUNUM_SECENEKLERI.map((s) => s.etiket), ['Hikâyedeki saati izle', 'Gündüz', 'Gece', 'Karanlık']);
  assert.equal(tema.VARSAYILAN_GORUNUM, 'saat');
  assert.equal(tema.kitapTemasi('saat', 'gunduz'), 'gunduz');
  assert.equal(tema.kitapTemasi('saat', 'gece'), 'gece');
  for (const secim of ['gunduz', 'gece', 'karanlik']) {
    assert.equal(tema.kitapTemasi(secim, 'gunduz'), secim);
    assert.equal(tema.kitapTemasi(secim, 'gece'), secim);
  }
  assert.deepEqual(tema.EL_YAZISI_SECENEKLERI.map((s) => s.deger), ['a', 'b', 'c']);
  assert.equal(tema.VARSAYILAN_EL, 'b');
});

test('book shell: cloth, two pages, ribbon drawing, the narrow screen keeps only the chosen page', () => {
  const html = render(kitap.KitapKabugu, { tema: 'gece', sol: 'SOL', sag: 'SAG', darEkranSayfasi: 'sag' });
  assert.match(html, /data-kitap-tema="gece"/);
  assert.match(html, /class="kitap-cilt"/);
  assert.match(html, /kitap-sayfa kitap-sayfa-sol kitap-darda-gizli/);
  assert.match(html, /kitap-sayfa kitap-sayfa-sag"/);
  assert.match(html, /role="img" aria-label="Kurdele ayraç"/);
});

test('bookmark tabs: a Radix tab list with a name, the open tab is announced as selected', () => {
  const html = render(kitap.Ayraclar, { deger: 'karakter', degisince() {}, ayraclar: [
    { deger: 'hikaye', etiket: 'Hikâye' }, { deger: 'karakter', etiket: 'Karakter' }, { deger: 'canta', etiket: 'Çanta' }] });
  assert.match(html, /role="tablist"[^>]*aria-label="Defter ayraçları"|aria-label="Defter ayraçları"[^>]*role="tablist"/);
  assert.match(html, /aria-selected="true"[^>]*>Karakter</);
  assert.equal((html.match(/role="tab"/g) ?? []).length, 3);
});

test('choice groups (appearance, layout, hand, size) are named radio groups with the chosen one checked', () => {
  const html = render(ayar.ArayuzAyarlari, { deger: { gorunum: 'saat', duzen: 'iki-sayfa', el: 'b', boy: 'normal' }, degisince() {} });
  assert.match(html, />Arayüz</);
  for (const name of ['Görünüm', 'Sayfa düzeni', 'El yazısı', 'Yazı boyu']) assert.match(html, new RegExp(`aria-label="${name}"`));
  assert.equal((html.match(/role="radio"/g) ?? []).length, 4 + 2 + 3 + 2);
  assert.match(html, /aria-checked="true"[^>]*>Hikâyedeki saati izle</);
  assert.doesNotMatch(html, /Cihaz ayarını izle/);
});

test('base controls: names, disabled, error text tied to the field, the seal stamp marks the chosen card', () => {
  const sayac = render(kontrol.Sayac, { etiket: 'Şifa iksiri', deger: 0, min: 0, max: 3, degisince() {} });
  assert.match(sayac, /aria-label="Şifa iksiri azalt"[^>]*disabled|disabled[^>]*aria-label="Şifa iksiri azalt"/);
  assert.match(sayac, /aria-label="Şifa iksiri artır"/);
  assert.match(sayac, /aria-live="polite"/);

  const kutu = render(kontrol.SayiKutusu, { etiket: 'Kuvvet', deger: '21', hata: '3 ile 20 arası olmalı.', degisince() {} });
  assert.match(kutu, /aria-invalid="true"/);
  const describedBy = /aria-describedby="([^"]+)"/.exec(kutu)?.[1];
  assert.ok(describedBy && kutu.includes(`id="${describedBy}"`), 'error message is tied to the field');

  const kart = render(kontrol.SecimKartlari, { etiket: 'Tür', deger: 'ejderhasoyu', degisince() {}, secenekler: [
    { deger: 'insan', baslik: 'İnsan', aciklama: 'Becerikli.' }, { deger: 'ejderhasoyu', baslik: 'Ejderhasoyu', aciklama: 'Ejderha kanı.' }] });
  assert.match(kart, /role="radiogroup"/);
  assert.equal((kart.match(/aria-label="Seçildi"/g) ?? []).length, 1);

  assert.match(render(kontrol.OnayKutusu, { etiket: 'Zarları göster', isaretli: true, degisince() {} }), /role="checkbox"[^>]*aria-checked="true"|aria-checked="true"[^>]*role="checkbox"/);
  assert.match(render(kontrol.Anahtar, { etiket: 'Müzik', acik: false, degisince() {} }), /role="switch"/);
  assert.match(render(kontrol.AcilirListe, { etiket: 'Zar takımı', deger: 'kemik', degisince() {}, secenekler: [{ deger: 'kemik', etiket: 'Kemik' }] }), /role="combobox"/);
  assert.match(render(kontrol.KitapDugme, { tur: 'ana', disabled: true }, 'Gönder'), /<button[^>]*disabled/);
  assert.match(render(kontrol.BosSatirlar, { satir: 3, etiket: 'Henüz yazılmadı' }), /aria-label="Henüz yazılmadı"/);
  assert.match(render(kontrol.Yukleniyor, { etiket: 'Sayfa yazılıyor' }), /role="status"/);
  assert.match(render(kontrol.BolumBasligi, { duzey: 2 }, 'Açık işler'), /<h2[^>]*>Açık işler<\/h2>/);
});

test('writing line: pen nib, the hand face, three modes, the microphone sits left of Gönder and hides without support', () => {
  const html = render(yazma.YazmaAlani, { kip: 'yap', kipDegisince() {}, metin: '', metinDegisince() {}, gonder() {}, mikrofonDestegi: true });
  assert.match(html, /aria-label="Ne yapıyorsun\?"/);
  assert.match(html, /aria-label="Söyleyiş biçimi"/);
  for (const kip of ['yap', 'söyle', 'anlatıcıya sor']) assert.match(html, new RegExp(`role="radio"[^>]*>${kip}<`));
  assert.ok(html.indexOf('Sesle yaz') < html.indexOf('>Gönder<'), 'microphone before Gönder');
  const yok = render(yazma.YazmaAlani, { kip: 'yap', kipDegisince() {}, metin: '', metinDegisince() {}, gonder() {}, mikrofonDestegi: false });
  assert.doesNotMatch(yok, /Sesle yaz/);
});

/** Every file of the book set except the drawing folder (Kadir, 13 Nov 2026: drawing colours stay as drawn). */
function bookFiles() {
  const out = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const full = path.join(dir, name);
      if (statSync(full).isDirectory()) { if (name !== 'cizimler') walk(full); } else out.push(full);
    }
  };
  walk(path.join(root, 'components', 'kitap'));
  out.push(path.join(root, 'lib', 'kitap-tema.ts'), path.join(root, 'pages', 'kitap-galerisi.tsx'));
  return out;
}

test('no hand-written colour, raw select, checkbox, alert or full-page filter outside src/index.css and the drawing folder', () => {
  for (const file of bookFiles()) {
    const text = readFileSync(file, 'utf8');
    const rel = path.relative(root, file);
    assert.doesNotMatch(text, /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/, `${rel} has a colour code`);
    assert.doesNotMatch(text, /<select\b|type=["']checkbox["']|\balert\(/, `${rel} uses a raw browser control`);
    assert.doesNotMatch(text, /feTurbulence|(^|[;{\s])filter\s*:/m, `${rel} applies a filter`);
  }
});

test('drawing folder: the taken drawings and the two grain tiles exist, the pen nib takes --mum, a source note names each', () => {
  const dir = path.join(root, 'components', 'kitap', 'cizimler');
  for (const name of ['kalem-ucu.tsx', 'kurdele.tsx', 'secim-damgasi.tsx', 'kagit-tanesi-acik.png', 'kagit-tanesi-koyu.png', 'KAYNAK.md']) {
    assert.ok(statSync(path.join(dir, name)).isFile(), `${name} is missing`);
  }
  assert.match(readFileSync(path.join(dir, 'kalem-ucu.tsx'), 'utf8'), /var\(--mum\)/);
  const note = readFileSync(path.join(dir, 'KAYNAK.md'), 'utf8');
  for (const name of ['kalem-ucu.tsx', 'kurdele.tsx', 'secim-damgasi.tsx', 'kagit-tanesi-acik.png', 'kagit-tanesi-koyu.png']) assert.match(note, new RegExp(name.replace('.', '\\.')));
});

test('the gallery route exists only in development and is loaded lazily', () => {
  const shell = read('app-shell.tsx');
  assert.match(shell, /import\.meta\.env\.DEV/);
  assert.match(shell, /lazy\(\(\) => import\(["']\.\/pages\/kitap-galerisi["']\)\)/);
  assert.match(shell, /path="\/galeri"/);
});

test('the A1 book faces never swap in late: font-display optional, so story text cannot jump when a font arrives late', () => {
  const fontCss = read('fonts/fonts.css');
  const faces = [...fontCss.matchAll(/@font-face\s*\{([^}]*)\}/g)].map(([, body]) => ({
    family: /font-family:\s*'([^']+)'/.exec(body)?.[1], display: /font-display:\s*(\w+)/.exec(body)?.[1] }));
  const book = faces.filter((f) => ['Literata', 'Kalam', 'Charm', 'Bad Script'].includes(f.family));
  assert.equal(book.length, 12);
  for (const f of book) assert.equal(f.display, 'optional', `${f.family} must not swap`);
});

// Review fixes (separate-eye review of the A1 gallery, findings 1-8; Kadir: "1-8'i düzelt").
const kitapCss = () => read('components/kitap/kitap.css');
const kural = (text, selector) => {
  const bare = text.replace(/\/\*[\s\S]*?\*\//g, '');
  const at = bare.indexOf(`${selector} {`);
  assert.notEqual(at, -1, `${selector} is missing`);
  return bare.slice(at, bare.indexOf('}', at));
};

test('finding 1: the default hand and the body face are preloaded, and no hand falls back to the system cursive face', () => {
  const html = readFileSync(path.join(process.cwd(), 'index.html'), 'utf8');
  // latin and latin-ext: Turkish ş, ğ, İ live in latin-ext, so without it those letters fell back to Georgia (measured).
  for (const file of ['kalam/YA9dr0Wd4kDdMthROCc.woff2', 'kalam/YA9dr0Wd4kDdMthfOCfzsw.woff2',
    'literata/or3PQ6P12-iJxAIgLa78DkTtAoDhk0oVpaK3YLanFLHpPf2TbLi4J_HWTA.woff2', 'literata/or3PQ6P12-iJxAIgLa78DkTtAoDhk0oVpaK3YLanFLHpPf2TbLi4J__WTFCW.woff2',
    'literata/or3NQ6P12-iJxAIgLYT1PLs1a-t7PU0AbeE9KPxYzNiCp1OUedn8VrLmTkiS.woff2', 'literata/or3NQ6P12-iJxAIgLYT1PLs1a-t7PU0AbeE9KPxYzNiCp1OUedn8VrLmQEiSh8g.woff2']) {
    assert.match(html, new RegExp(`<link rel="preload" href="/src/fonts/${file.replace(/[.]/g, '\.')}" as="font" type="font/woff2" crossorigin`), `${file} is not preloaded`);
  }
  for (const selector of ['[data-kitap-tema]', '[data-kitap-el="a"]', '[data-kitap-el="b"]', '[data-kitap-el="c"]']) {
    const value = token(block(selector), '--el-aile') ?? '';
    assert.doesNotMatch(value, /cursive|Comic Sans/, `${selector} falls back to a system cursive face`);
    assert.match(value, /'Literata'/, `${selector} falls back to Literata`);
  }
});

test('finding 2: the writing field grows with its text, and on the phone Gönder is a 44px return key that keeps its name', () => {
  assert.doesNotMatch(kural(kitapCss(), '.kitap-yaz-girdi'), /(^|[;\s])height:\s*50px/);
  const html = render(yazma.YazmaAlani, { kip: 'yap', kipDegisince() {}, metin: '', metinDegisince() {}, gonder() {}, mikrofonDestegi: true });
  assert.match(html, /class="[^"]*kitap-gonder-simge[^"]*"/);
  assert.match(html, /<span class="kitap-gonder-metin">Gönder<\/span>/);
});

test('findings 3 and 4: the gallery story keeps one writing field and the hand-off rule lives in code', () => {
  assert.equal(tema.hikayeTekAkista('hikaye', false), false);
  assert.equal(tema.hikayeTekAkista('karakter', false), true);
  assert.equal(tema.hikayeTekAkista('hikaye', true), true);
  assert.equal(tema.hikayeTekAkista('canta', true), true);
});

test('finding 5: on wide screens the type grows with the book and the text column stays near 45 letters', () => {
  const base = block('[data-kitap-tema]');
  assert.match(token(base, '--buyume') ?? '', /^clamp\(0px,/);
  assert.equal(token(base, '--govde'), 'calc(19px + var(--buyume))');
  assert.equal(token(block('[data-kitap-boy="buyuk"]'), '--govde'), 'calc(21px + var(--buyume))');
  assert.match(kural(kitapCss(), '.kitap-satir'), /grid-template-columns:\s*minmax\(0,\s*var\(--sutun-metin\)\)/);
  assert.equal(token(base, '--sutun-metin'), '22em');
});

test('finding 6: the ribbon hangs below the book', () => {
  assert.match(kural(kitapCss(), '.kitap-kurdele'), /height:\s*calc\(100% \+ 40px\)/);
});

test('findings 7 and 8: a disabled checked box loses its fill; an error is a double rule with a referee note, a disabled field keeps the dashed rule', () => {
  const css = kitapCss();
  assert.match(kural(css, ".kitap-onay-kutu:disabled[data-state='checked']"), /background:\s*none/);
  assert.match(kural(css, ".kitap-sayi-girdi[aria-invalid='true']"), /border-bottom:\s*3px double/);
  assert.match(kural(css, '.kitap-alan-hata'), /color:\s*var\(--hakem\)/);
  assert.match(kural(css, '.kitap-sayi-girdi:disabled'), /dashed/);
});

test('finding 9: setting labels carry no explanation text in brackets (T12)', () => {
  assert.doesNotMatch(read('pages/kitap-galerisi.tsx'), /etiket="[^"]*\(/);
});

// Realism pass (Kadir, 14 Nov 2026, after approving f22bc5ba): cloth weave, page block, page bulge light, ink and
// depth come from tokens; effects off turns every added layer flat, and no layer is a filter.
test('realism layers are tokens, each one switched off with effects off', () => {
  const base = block('[data-kitap-tema]');
  for (const name of ['--cilt-dokuma', '--kabarma', '--murekkep-golge', '--golge-temas']) assert.ok(token(base, name), `${name} is missing`);
  const off = block('[data-kitap-tema][data-kitap-efekt="kapali"]');
  for (const name of ['--tane', '--cilt-dokuma', '--murekkep-golge']) assert.equal(token(off, name), 'none', `${name} stays on with effects off`);
  assert.equal(token(off, '--kabarma'), 'transparent');
  const css = kitapCss();
  assert.match(kural(css, '.kitap-cilt'), /var\(--cilt-dokuma\)/);
  assert.match(kural(css, '.kitap-p'), /text-shadow:\s*var\(--murekkep-golge\)/);
  assert.doesNotMatch(css, /(^|[;{\s])(filter|backdrop-filter)\s*:/m);
});

// Kadir, 14 Nov 2026: a far more realistic ribbon (a new design is allowed) and the reading lamp of the draft with
// realistic light. Lamp rules: lit at night only (T7: not by day), dark theme only when asked (G10 is Kadir's call).
test('ribbon: satin body with a woven rib, a headband at the spine top and a V-cut tail hanging below', () => {
  const html = render(kitap.KitapKabugu, { tema: 'gece', sol: 'SOL', sag: 'SAG' });
  assert.match(html, /role="img" aria-label="Kurdele ayraç"/);
  assert.match(html, /<pattern id="kurdele-dokuma-[^"]+"/);
  assert.match(html, /class="kitap-kurdele-uc"/);
  assert.match(html, /class="kitap-kapitalbant"/);
});

test('reading lamp: drawn at night, never by day, in the dark theme only when asked; its light lives in tokens', () => {
  const gece = render(kitap.KitapKabugu, { tema: 'gece', sol: 'SOL', sag: 'SAG' });
  assert.match(gece, /class="kitap-lamba"/);
  assert.match(gece, /aria-label="Okuma ışığı yanıyor"/);
  assert.match(gece, /class="kitap-lamba-hale"/);
  assert.doesNotMatch(render(kitap.KitapKabugu, { tema: 'gunduz', sol: 'SOL', sag: 'SAG' }), /class="kitap-lamba|Okuma ışığı/);
  assert.doesNotMatch(render(kitap.KitapKabugu, { tema: 'karanlik', sol: 'SOL', sag: 'SAG' }), /class="kitap-lamba|Okuma ışığı/);
  assert.match(render(kitap.KitapKabugu, { tema: 'karanlik', sol: 'SOL', sag: 'SAG', lambaKaranlikta: true }), /class="kitap-lamba"/);
  for (const name of ['--isik-cilt', '--lamba-hale', '--lamba-havuz']) assert.ok(token(block('[data-kitap-tema="gece"]'), name), `${name} is missing at night`);
  // Review 11 (Kadir, 14 Nov 2026): an electric bulb gives a still light; no breathing animation at all.
  assert.doesNotMatch(kural(kitapCss(), '.kitap-lamba-hale'), /animation/);
  assert.doesNotMatch(kitapCss(), /kitap-lamba-nefes/);
  const dir = path.join(root, 'components', 'kitap', 'cizimler');
  assert.ok(statSync(path.join(dir, 'okuma-lambasi.tsx')).isFile());
  assert.match(readFileSync(path.join(dir, 'KAYNAK.md'), 'utf8'), /okuma-lambasi\.tsx/);
});

// Two independent reviews (Opus, Fable) after 8c5ac10d; Kadir: fix all 15, the nice-to-haves included.
const kurdeleKod = () => read('components/kitap/cizimler/kurdele.tsx');
const medya = (css, sorgu) => {
  const at = css.indexOf(`@media ${sorgu} {`);
  assert.notEqual(at, -1, `@media ${sorgu} is missing`);
  let derinlik = 0;
  for (let i = css.indexOf('{', at); i < css.length; i++) {
    if (css[i] === '{') derinlik++;
    if (css[i] === '}' && --derinlik === 0) return css.slice(at, i);
  }
  return css.slice(at);
};

test('review 1, 5, 6, 12: phone ribbon is a short straight tail, the body curves wider, the headband has no red, the rib is soft', () => {
  const dar = medya(kitapCss(), '(max-width: 767px)');
  assert.match(dar, /\.kitap-kurdele-govde\s*\{\s*display:\s*none/);
  const kod = kurdeleKod();
  assert.match(kod, /const GENLIK = (\d+(\.\d+)?)/);
  assert.ok(Number(/const GENLIK = (\d+(?:\.\d+)?)/.exec(kod)[1]) >= 7, 'the S-curve swings at least 7 units');
  const bant = kod.slice(kod.indexOf('kitap-kapitalbant'));
  assert.doesNotMatch(bant, /#8E2A24|#A8332E|#B4443B/i, 'the headband carries a red stripe');
  assert.match(kod, /opacity="\.0[0-9]"[^>]*\/>\s*<rect[^>]*opacity="\.0[0-9]"/, 'rib lines are soft (opacity below .1)');
  assert.doesNotMatch(kod, /<g transform="rotate\(7/, 'the tail falls clearly to the side');
});

test('review 2, 10: the lamp leaves room for the tabs and scales with the book', () => {
  const orta = medya(kitapCss(), '(min-width: 768px) and (max-width: 1179px)');
  assert.match(orta, /\.kitap-lamba\s*\{\s*display:\s*none/);
  const base = block('[data-kitap-tema]');
  assert.match(token(base, '--lamba-en') ?? '', /calc\(64px \+ var\(--buyume\)/);
  assert.match(token(base, '--kurdele-en') ?? '', /calc\(40px \+ var\(--buyume\)/);
  assert.match(kural(kitapCss(), '.kitap-lamba'), /width:\s*var\(--lamba-en\)/);
});

test('review 3, 13, 14: the light falls on the pages, the halo sits under the shade, the dark-theme lamp lights its page', () => {
  const gece = block('[data-kitap-tema="gece"]');
  assert.match(token(gece, '--isik-sol') ?? '', /^radial-gradient\(ellipse 60% 44% at 100% 0%, rgba\(255, 226, 168, 0\.4/);
  assert.match(token(gece, '--lamba-havuz') ?? '', /rgba\(255, 190, 105, 0\.1\)/);
  assert.match(kural(kitapCss(), '.kitap-lamba-hale'), /border-radius:\s*50%/);
  assert.match(kural(kitapCss(), '.kitap-lamba-hale'), /top:\s*calc\(var\(--lamba-en\) \* 0\.9/);
  const karanlik = block('[data-kitap-tema="karanlik"][data-kitap-lamba="acik"]');
  assert.match(token(karanlik, '--isik-sol') ?? '', /rgba\(255, 214, 150, 0\.1[0-9]/);
});

test('review 7, 8: effects off flattens the lamp light and every added shadow; the cloth weave is irregular', () => {
  const off = block('[data-kitap-tema][data-kitap-efekt="kapali"]');
  for (const name of ['--lamba-havuz', '--isik-cilt', '--lamba-hale']) assert.equal(token(off, name), 'none', `${name} with effects off`);
  for (const name of ['--golge-temas', '--cilt-kenar-golge']) assert.equal(token(off, name), '0 0 0 transparent', `${name} with effects off`);
  assert.equal(token(off, '--sayfa-blok-golge'), 'transparent');
  const dokuma = token(block('[data-kitap-tema]'), '--cilt-dokuma') ?? '';
  assert.match(dokuma, /1px 3px/);
  assert.match(dokuma, /1px 4px/);
  assert.match(dokuma, /87deg/);
  assert.match(kural(kitapCss(), '.kitap-cilt::after'), /background-image:\s*var\(--tane\)/);
});

test('review 9: checkbox and switch rows and the number field are 44px touch targets', () => {
  const onay = render(kontrol.OnayKutusu, { etiket: 'Zarları göster', isaretli: true, degisince() {} });
  assert.match(onay, /^<label class="kitap-onay"[^>]*>.*role="checkbox".*<\/label>$/s);
  const anahtar = render(kontrol.Anahtar, { etiket: 'Müzik', acik: false, degisince() {} });
  assert.match(anahtar, /^<label class="kitap-onay"[^>]*>.*role="switch".*<\/label>$/s);
  assert.match(kural(kitapCss(), '.kitap-onay'), /min-height:\s*var\(--dokunma\)/);
  assert.match(kural(kitapCss(), '.kitap-sayi-girdi'), /height:\s*var\(--dokunma\)/);
});

test('review 15: in the gallery, a hand-picked look offers a way back to the story clock', () => {
  assert.match(read('pages/kitap-galerisi.tsx'), /Saate dön/);
});

test('narrow two-page books (768-1179px) put the margin note under its line, so the text column is not squeezed', () => {
  const orta = medya(kitapCss(), '(min-width: 768px) and (max-width: 1179px)');
  assert.match(orta, /\.kitap-satir\s*\{\s*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  assert.match(orta, /\.kitap-satir > \.kitap-kenar-metin\s*\{\s*padding-left:\s*26px/);
});

test('story lines never shrink in the scrolling page: a long story scrolls instead of hiding its first lines', () => {
  assert.match(kural(kitapCss(), '.kitap-akis > *'), /flex:\s*0 0 auto/);
});
