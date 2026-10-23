// Draws a scene (see ../../references/sketch.md) as a hand-drawn SVG string and reports layout problems.

export const W = 782;
const TONE = { ink: '#1e1e1e', gray: '#868e96', accent: '#1971c2', faint: '#ced4da' };
const SIZE = { label: 21, big: 23, sub: 17, note: 18 };
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

export function draw(scene, font, rough) {
  const H = scene.height;
  const gen = rough.generator();
  const out = [];
  const strokes = [];   // sampled points of every drawn line, for the text-crossing check
  const texts = [];
  const crosses = [];
  let seed = 1;
  const opt = (tone = 'ink', width = 1.6, extra = {}) =>
    Object.assign({ roughness: 1.1, bowing: 1, strokeWidth: width, stroke: TONE[tone], seed: seed++ }, extra);
  const add = drawable => {
    const dash = drawable.options.strokeLineDash;
    for (const p of gen.toPaths(drawable))
      out.push(`<path d="${p.d}" stroke="${p.stroke}" stroke-width="${p.strokeWidth}" fill="${p.fill || 'none'}" stroke-linecap="round"${dash && p.stroke !== 'none' ? ` stroke-dasharray="${dash.join(' ')}"` : ''}/>`);
  };
  const seg = (x1, y1, x2, y2, n = 24) => Array.from({ length: n + 1 }, (_, i) => [x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n]);
  const quad = (a, c, b, n = 32) => Array.from({ length: n + 1 }, (_, i) => {
    const t = i / n, u = 1 - t;
    return [u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]];
  });
  const scale = font.unitsPerEm;
  function text(x, y, str, { size = 'label', tone = 'ink', anchor = 'start', words = false, inside = null } = {}) {
    const px = SIZE[size] || Number(size);
    const w = font.getAdvanceWidth(String(str), px);
    const x0 = anchor === 'middle' ? x - w / 2 : anchor === 'end' ? x - w : x;
    texts.push({ s: String(str), words, inside, size: px, x0, x1: x0 + w, y0: y - font.ascender / scale * px, y1: y - font.descender / scale * px });
    out.push(`<text x="${x}" y="${y}" font-size="${px}" fill="${TONE[tone]}" text-anchor="${anchor}">${esc(str)}</text>`);
  }
  function cross(x, y, r = 12) {
    crosses.push([x, y]);
    add(gen.line(x - r, y - r, x + r, y + r, opt('ink', 2.6)));
    add(gen.line(x - r, y + r, x + r, y - r, opt('ink', 2.6)));
  }

  const kinds = {
    box(s) {
      const tone = s.tone || 'ink';
      for (let i = (s.stack || 1) - 1; i >= 0; i--)
        add(gen.rectangle(s.x + i * 8, s.y - i * 8, s.w, s.h, opt(tone, tone === 'accent' ? 2.6 : 1.6, { fill: '#fff', fillStyle: 'solid' })));
      const cy = s.y + s.h / 2 + (s.sub ? -6 : 7);
      const box = [s.x, s.y, s.w, s.h];
      if (s.label) text(s.x + s.w / 2, cy, s.label, { size: s.size || 'label', tone: tone === 'accent' ? 'ink' : tone, anchor: 'middle', inside: box });
      if (s.sub) text(s.x + s.w / 2, cy + 28, s.sub, { size: 'sub', tone: 'gray', anchor: 'middle', inside: box });
    },
    page(s) {
      const tone = s.tone || 'ink';
      add(gen.rectangle(s.x, s.y, s.w, s.h, opt(tone)));
      if (s.title) text(s.x, s.y - 16, s.title, { size: 'note', tone });
      if (s.label) text(s.x + s.w / 2, s.y + s.h / 2 + 7, s.label, { tone, anchor: 'middle', inside: [s.x, s.y, s.w, s.h] });
      const bands = s.bands || [];
      for (const b of bands) {
        const bt = b.tone || 'ink';
        add(gen.rectangle(s.x + 10, s.y + b.y0, s.w - 20, b.y1 - b.y0, opt(bt, bt === 'accent' ? 2.6 : 1.6)));
        if (b.label) text(s.x + s.w / 2, s.y + (b.y0 + b.y1) / 2 + 7, b.label, { tone: bt === 'accent' ? 'ink' : bt, anchor: 'middle', inside: [s.x + 10, s.y + b.y0, s.w - 20, b.y1 - b.y0] });
      }
      if (s.lines !== false) {
        let i = 0;
        for (let y = s.y + 18; y < s.y + s.h - 10; y += 15, i++) {
          if (bands.some(b => y > s.y + b.y0 - 8 && y < s.y + b.y1 + 8)) continue;
          add(gen.line(s.x + 16, y, s.x + s.w - 22 - (i % 3) * 18, y, opt('faint', 1, { roughness: 0.8 })));
        }
      }
    },
    arrow(s) {
      const tone = s.tone || 'ink', w = tone === 'gray' ? 1.5 : 2.4;
      const a = s.from, b = s.to, c = s.bend || [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      add(gen.path(`M${a[0]},${a[1]} Q${c[0]},${c[1]} ${b[0]},${b[1]}`, opt(tone, w)));
      strokes.push(quad(a, c, b));
      if (s.head !== false) {
        const ang = Math.atan2(b[1] - c[1], b[0] - c[0]), L = 13, sp = 0.45;
        add(gen.line(b[0], b[1], b[0] - L * Math.cos(ang - sp), b[1] - L * Math.sin(ang - sp), opt(tone, w)));
        add(gen.line(b[0], b[1], b[0] - L * Math.cos(ang + sp), b[1] - L * Math.sin(ang + sp), opt(tone, w)));
      }
      if (s.crossed) { const m = quad(a, c, b, 2)[1]; cross(m[0], m[1]); }
    },
    line(s) {
      add(gen.line(s.from[0], s.from[1], s.to[0], s.to[1], opt(s.tone || 'ink', 1.8, s.dashed ? { strokeLineDash: [9, 7] } : {})));
      strokes.push(seg(s.from[0], s.from[1], s.to[0], s.to[1], 48));
    },
    brace(s) {
      const { x, y0, y1 } = s, m = (y0 + y1) / 2, tone = s.tone || 'accent';
      add(gen.path(`M${x + 10},${y0} Q${x},${y0} ${x},${y0 + 14} L${x},${m - 12} Q${x},${m} ${x - 12},${m} Q${x},${m} ${x},${m + 12} L${x},${y1 - 14} Q${x},${y1} ${x + 10},${y1}`, opt(tone, 1.8)));
      strokes.push(seg(x, y0, x, y1));
      const rows = s.rows || [], step = (y1 - y0) / Math.max(rows.length, 1);
      rows.forEach(([k, v, vt], i) => {
        const y = y0 + step * (i + 0.5) + 6;
        text(x + 22, y, k, { size: 'sub', tone: 'gray' });
        text(x + 22 + (s.keyWidth || 116), y, v, { size: 'note', tone: vt || 'ink' });
      });
    },
    cross(s) { cross(s.x, s.y); },
    text(s) { text(s.x, s.y, s.text, { size: s.size || 'note', tone: s.tone || 'ink', anchor: s.anchor || 'start', words: s.words !== false }); },
    underline(s) { add(gen.line(s.from[0], s.from[1], s.to[0], s.to[1], opt(s.tone || 'accent', 1.4))); },
  };

  const unknownKinds = [];
  for (const s of scene.shapes) (kinds[s.kind] || (() => unknownKinds.push(s.kind)))(s);

  // Text sits above every stroke, so the drawing order is strokes first.
  const paths = out.filter(l => l.startsWith('<path')), labels = out.filter(l => l.startsWith('<text'));
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><rect width="${W}" height="${H}" fill="#fff"/><g>${paths.join('')}</g><g font-family="Excalifont">${labels.join('')}</g></svg>`;

  const overlaps = [];
  for (let i = 0; i < texts.length; i++) for (let j = i + 1; j < texts.length; j++) {
    const A = texts[i], B = texts[j];
    if (Math.min(A.x1, B.x1) - Math.max(A.x0, B.x0) > 1 && Math.min(A.y1, B.y1) - Math.max(A.y0, B.y0) > 2) overlaps.push(`${A.s} / ${B.s}`);
  }
  const lineThroughText = texts.filter(t => strokes.some(pts => pts.some(([x, y]) => x > t.x0 + 2 && x < t.x1 - 2 && y > t.y0 + 4 && y < t.y1 - 3))).map(t => t.s);
  const gloss = texts.filter(t => t.words).map(t => t.s);
  // Identifier-style words: snake_case, SCREAMING caps, camelCase. File names with an extension pass.
  const jargon = [...new Set(texts.flatMap(t => t.s.split(/[\s,;:()+=]+/)).filter(w =>
    !/\.[a-z0-9]{1,5}$/i.test(w) && (/[a-z0-9]_[a-z0-9]/i.test(w) || /^[A-Z]{4,}$/.test(w) || /^[a-z]+[A-Z]/.test(w))))];
  const missingGlyphs = [...new Set(texts.flatMap(t => [...t.s]).filter(c => c.trim() && font.charToGlyphIndex(c) === 0))];
  const story = scene.story || null;
  const all = texts.map(t => t.s).join('\n');
  const storyGaps = [];
  if (!story) storyGaps.push('no "story" in the scene');
  else {
    if (!['rewire', 'to scale', 'flow', 'check', 'bars'].includes(story.drawing)) storyGaps.push('story "drawing" must be one of: rewire, to scale, flow, check, bars');
    const sym = story.symptom && texts.find(t => t.s.includes(story.symptom));
    if (!story.seen) storyGaps.push('story has no "seen" quote from a record');
    if (!story.symptom) storyGaps.push('story has no "symptom"');
    else if (!sym) storyGaps.push(`symptom "${story.symptom}" is not drawn`);
    if (story.drawing === 'to scale' && !(story.number && scene.shapes.some(s => s.kind === 'line'))) storyGaps.push('a to-scale drawing needs the limit as a line and its "number"');
    if (story.drawing !== 'bars' && !crosses.length) storyGaps.push('no ✕ on the old path');
    if (story.number && !all.includes(story.number)) storyGaps.push(`number "${story.number}" is not drawn`);
    for (const name of story.added || []) if (!all.includes(name)) storyGaps.push(`added part "${name}" is not drawn`);
  }
  return {
    svg,
    report: {
      size: [W, H],
      unknownKinds,
      minFont: Math.min(...texts.map(t => t.size)),
      notInBox: texts.filter(t => t.inside && (t.x0 < t.inside[0] + 8 || t.x1 > t.inside[0] + t.inside[2] - 8 || t.y0 < t.inside[1] + 3 || t.y1 > t.inside[1] + t.inside[3] - 3)).map(t => t.s),
      outside: texts.filter(t => t.x0 < 4 || t.x1 > W - 4 || t.y0 < 2 || t.y1 > H - 2).map(t => t.s),
      overlaps,
      lineThroughText,
      jargon,
      missingGlyphs,
      storyGaps,
      glossWords: gloss.join(' ').split(/\s+/).filter(Boolean).length,
      gloss,
    },
  };
}
