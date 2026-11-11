/**
 * Rendered contrast sweep (UI S4). A function that runs inside a real page: for every visible text node it
 * reads the computed text colour and composites the backgrounds of its ancestors, then reports the ratio.
 * Run it in each theme / contrast state and on each screen (tests/play-screen-ui-regression.test.mjs).
 *
 * What it sees: solid background colours (alpha ones and color-mix results too) are composited root to
 * element; a gradient adds one candidate background per colour stop (worst case, stops at full strength);
 * a url() image cannot be sampled and is reported with image: true. Fixed overlays that paint above the text
 * (the atmosphere veil) are modelled in tests/scene-atmosphere.test.mjs, not here. Disabled controls are
 * exempt (WCAG 1.4.3 inactive components), and so are screen-reader-only clips.
 */
function sweepRenderedContrast() {
  // Sample the settled page: no transition may hold a half-faded colour and no reveal a half-faded word.
  const settle = document.createElement('style');
  settle.textContent = '*, *::before, *::after { transition: none !important; animation: none !important; } .ink-fresh .ink-word { opacity: 1 !important; }';
  document.head.appendChild(settle);
  try {
    return sweepSettled();
  } finally {
    settle.remove();
  }
  function sweepSettled() {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const parse = (value) => {
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = '#000';
    ctx.fillStyle = value;
    ctx.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
    return { r, g, b, a: a / 255 };
  };
  // The canvas rounds alpha to 8 bits; recover the CSS alpha when it is spelled out.
  const cssAlpha = (value) => {
    const m = /^rgba?\(([^)]*)\)$/.exec(value.trim());
    if (m) { const parts = m[1].split(/[ ,/]+/).filter(Boolean); return parts.length > 3 ? Number(parts[3]) : 1; }
    const c = /\/\s*([0-9.]+%?)\s*\)$/.exec(value);
    if (c) return c[1].endsWith('%') ? Number(c[1].slice(0, -1)) / 100 : Number(c[1]);
    return null;
  };
  const colour = (value) => { const c = parse(value); const a = cssAlpha(value); return a === null ? c : { ...c, a }; };
  const over = (top, bottom) => {
    const a = top.a + bottom.a * (1 - top.a);
    if (a === 0) return { r: 0, g: 0, b: 0, a: 0 };
    const mix = (t, u) => (t * top.a + u * bottom.a * (1 - top.a)) / a;
    return { r: mix(top.r, bottom.r), g: mix(top.g, bottom.g), b: mix(top.b, bottom.b), a };
  };
  const lum = ({ r, g, b }) => {
    const f = (v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const ratio = (a, b) => { const x = lum(a); const y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const label = (el) => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
    + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.') : '');
  const stopColours = (image) => (image.match(/rgba?\([^)]*\)|#[0-9a-fA-F]{3,8}\b|color\([^)]*\)/g) || []).map(colour);
  const backdrop = (el) => {
    const chain = [];
    for (let node = el; node; node = node.parentElement) {
      const cs = getComputedStyle(node);
      const bg = colour(cs.backgroundColor);
      chain.push({ bg, image: cs.backgroundImage });
      if (bg.a === 1) break;
    }
    let candidates = [{ r: 255, g: 255, b: 255, a: 1 }];
    let unsampled = false;
    for (let i = chain.length - 1; i >= 0; i -= 1) {
      const { bg, image } = chain[i];
      if (bg.a > 0) candidates = candidates.map((c) => over(bg, c));
      if (image !== 'none') {
        if (/url\(/.test(image)) unsampled = true;
        const stops = stopColours(image);
        candidates = candidates.concat(candidates.flatMap((c) => stops.map((s) => over(s, c)))).slice(0, 64);
      }
    }
    return { candidates, image: unsampled };
  };
  const opacityOf = (el) => { let o = 1; for (let n = el; n; n = n.parentElement) o *= Number(getComputedStyle(n).opacity); return o; };
  const round = (n) => Math.round(n * 100) / 100;
  const results = [];
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let tn = walker.nextNode(); tn; tn = walker.nextNode()) {
    const text = tn.nodeValue.replace(/\s+/g, ' ').trim();
    const el = tn.parentElement;
    if (!text || !el || seen.has(el) || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'OPTION'].includes(el.tagName)) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 1 || rect.height <= 1) continue;
    if (el.closest('[disabled], [aria-disabled="true"], .sr-only')) continue;
    seen.add(el);
    const { candidates, image } = backdrop(el);
    const fg = colour(cs.color);
    const o = opacityOf(el);
    const worst = Math.min(...candidates.map((base) => ratio(over({ ...fg, a: fg.a * o }, base), base)));
    results.push({ sel: label(el), text: text.slice(0, 40), ratio: round(worst), body: Boolean(el.closest('.story-text')), image });
  }
  for (const el of document.querySelectorAll('input, textarea')) {
    if (!el.getAttribute('placeholder') || el.disabled || el.getBoundingClientRect().width <= 1) continue;
    const ph = getComputedStyle(el, '::placeholder');
    const { candidates, image } = backdrop(el);
    const worst = Math.min(...candidates.map((base) => ratio(over(colour(ph.color), base), base)));
    results.push({ sel: label(el) + '::placeholder', text: el.getAttribute('placeholder').slice(0, 40), ratio: round(worst), body: false, image });
  }
  return { checked: results.length, results };
  }
}

export const RENDERED_CONTRAST_SCRIPT = `(${sweepRenderedContrast.toString()})()`;

/** Offenders in a sweep result: below 4.5 anywhere, below 7 in the story text, or a url() box we could not sample. */
export function contrastOffenders(sweep) {
  return sweep.results.filter((row) => row.ratio < (row.body ? 7 : 4.5) || row.image);
}
