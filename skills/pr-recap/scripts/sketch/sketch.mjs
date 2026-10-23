#!/usr/bin/env bun
// usage: bun sketch.mjs <scene.json> <out.png>
// Renders the scene at 2x with resvg, writes <out.png>, and prints a JSON report.
// Exits 1 when the drawing breaks a layout rule, 2 on bad input or a render failure.
import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';

const fail = msg => { console.error(msg); process.exit(2); };
const [scenePath, outPath] = process.argv.slice(2);
if (!scenePath || !outPath) fail('usage: bun sketch.mjs <scene.json> <out.png>');
const here = dirname(fileURLToPath(import.meta.url));
const fontPath = join(here, 'vendor/Excalifont-Regular.ttf');

// Install the pinned packages on first use, and again when package.json or bun.lock changes.
// A sandbox that cannot write the skill folder gets them in a temporary folder instead.
const key = createHash('sha256').update(readFileSync(join(here, 'package.json'))).update('\0').update(readFileSync(join(here, 'bun.lock'))).digest('hex');
function installed(dir) {
  const keyPath = join(dir, 'node_modules/.pr-recap-sketch-install-key');
  if (existsSync(keyPath) && readFileSync(keyPath, 'utf8').trim() === key) return true;
  try {
    mkdirSync(join(dir, 'node_modules'), { recursive: true });
    if (dir !== here) for (const f of ['package.json', 'bun.lock']) copyFileSync(join(here, f), join(dir, f));
    const r = spawnSync(process.versions.bun ? process.execPath : 'bun', ['install', '--frozen-lockfile'], { cwd: dir, encoding: 'utf8' });
    if (r.status !== 0) { console.error(`bun install --frozen-lockfile failed in ${dir}:\n${r.stderr || r.error}`); return false; }
    writeFileSync(keyPath, `${key}\n`);
    return true;
  } catch (e) {
    console.error(`cannot install into ${dir}: ${e.message}`);
    return false;
  }
}
let depsDir = here;
if (!installed(here)) {
  try { depsDir = mkdtempSync(join(tmpdir(), 'pr-recap-sketch-')); }
  catch (e) { fail(`cannot create temporary dependency folder: ${e.message}`); }
  process.on('exit', () => rmSync(depsDir, { recursive: true, force: true }));
  for (const [sig, n] of [['SIGINT', 130], ['SIGTERM', 143], ['SIGHUP', 129]]) process.on(sig, () => process.exit(n));
  if (!installed(depsDir)) fail('could not install the sketch packages; see the messages above');
}

let scene;
try { scene = JSON.parse(readFileSync(scenePath, 'utf8')); } catch (e) { fail(`bad scene: ${e.message}`); }
if (!Number.isFinite(scene?.height) || !Array.isArray(scene.shapes)) fail('bad scene: needs "height" and "shapes"');
// Every field that reaches the SVG as an attribute must be a number or a known word.
const isPoint = v => Array.isArray(v) && v.length === 2 && v.every(Number.isFinite);
const fieldOk = {
  x: Number.isFinite, y: Number.isFinite, w: Number.isFinite, h: Number.isFinite,
  y0: Number.isFinite, y1: Number.isFinite, keyWidth: Number.isFinite, stack: Number.isFinite,
  from: isPoint, to: isPoint, bend: isPoint,
  anchor: v => ['start', 'middle', 'end'].includes(v),
  size: v => ['label', 'big', 'sub', 'note'].includes(v),
  tone: v => ['ink', 'gray', 'accent', 'faint'].includes(v),
};
scene.shapes.forEach((shape, i) => {
  if (!shape || typeof shape !== 'object') fail(`bad scene: shape ${i} is not an object`);
  for (const part of [shape, ...(Array.isArray(shape.bands) ? shape.bands : [])])
    for (const [k, ok] of Object.entries(fieldOk))
      if (part?.[k] !== undefined && !ok(part[k])) fail(`bad scene: shape ${i} has a bad "${k}": ${JSON.stringify(part[k])}`);
});

try {
  const require = createRequire(join(depsDir, 'package.json'));
  const opentype = require('opentype.js');
  const { Resvg } = require('@resvg/resvg-js');
  const rough = require('roughjs/bundled/rough.cjs.js');
  const { draw, W } = await import('./draw.mjs');
  const bytes = readFileSync(fontPath);
  const font = opentype.parse(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
  const { svg, report } = draw(scene, font, rough);
  const png = new Resvg(svg, {
    fitTo: { mode: 'width', value: W * 2 },
    font: { fontFiles: [fontPath], loadSystemFonts: false, defaultFontFamily: 'Excalifont' },
  }).render().asPng();
  writeFileSync(outPath, png);
  const problems = [];
  if (report.unknownKinds.length) problems.push(`unknown shape kinds: ${report.unknownKinds.join(', ')}`);
  if (report.minFont < 16) problems.push('text under 16 px');
  if (report.outside.length) problems.push(`text outside or touching the edge: ${report.outside.join(' | ')}`);
  if (report.notInBox.length) problems.push(`text does not fit its box: ${report.notInBox.join(' | ')}`);
  if (report.overlaps.length) problems.push(`overlapping text: ${report.overlaps.join(' | ')}`);
  if (report.lineThroughText.length) problems.push(`a line crosses text: ${report.lineThroughText.join(' | ')}`);
  if (report.missingGlyphs.length) problems.push(`characters the font cannot draw: ${report.missingGlyphs.join(' ')}`);
  if (report.jargon.length) problems.push(`identifier-style words, use plain words: ${report.jargon.join(', ')}`);
  for (const gap of report.storyGaps) problems.push(gap);
  if (report.glossWords > 12) problems.push(`${report.glossWords} gloss words, the limit is 12`);
  if (scene.height > 420) problems.push(`height ${scene.height}, the limit is 420`);
  console.log(JSON.stringify({ ...report, problems }, null, 1));
  process.exitCode = problems.length ? 1 : 0;
} catch (e) {
  fail(`render failed: ${e.message}`);
}
