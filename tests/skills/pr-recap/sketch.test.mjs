import { afterAll, describe, expect, test } from 'bun:test';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const skill = join(import.meta.dir, '../../../skills/pr-recap');
const tool = join(skill, 'scripts/sketch/sketch.mjs');
const examples = join(skill, 'references/examples');
const work = mkdtempSync(join(tmpdir(), 'pr-recap-sketch-test-'));
afterAll(() => rmSync(work, { recursive: true, force: true }));

function render(scene) {
  const scenePath = join(work, `scene-${Math.random().toString(36).slice(2)}.json`);
  const outPath = scenePath.replace(/\.json$/, '.png');
  writeFileSync(scenePath, typeof scene === 'string' ? scene : JSON.stringify(scene));
  const r = Bun.spawnSync([process.execPath, tool, scenePath, outPath]);
  const stdout = r.stdout.toString();
  return { code: r.exitCode, report: stdout ? JSON.parse(stdout) : null, outPath, stderr: r.stderr.toString() };
}

const example = name => JSON.parse(readFileSync(join(examples, `${name}.json`), 'utf8'));
const withShapes = (scene, ...shapes) => ({ ...scene, shapes: [...scene.shapes, ...shapes] });

describe('sketch tool', () => {
  for (const name of ['rewire', 'to-scale', 'flow', 'check', 'bars']) {
    test(`the ${name} example renders a PNG with no problems`, () => {
      const { code, report, outPath } = render(example(name));
      expect(report.problems).toEqual([]);
      expect(code).toBe(0);
      expect(readFileSync(outPath).subarray(1, 4).toString()).toBe('PNG');
    });
  }

  test('identifier-style words are problems, file names are not', () => {
    const { code, report } = render(withShapes(example('flow'),
      { kind: 'text', x: 30, y: 250, text: 'MIXED_FILES retryState', words: false },
      { kind: 'text', x: 400, y: 250, text: 'order-check.py', words: false }));
    expect(code).toBe(1);
    expect(report.jargon).toEqual(['MIXED_FILES', 'retryState']);
  });

  test('characters the font lacks are problems', () => {
    const { report } = render(withShapes(example('flow'), { kind: 'text', x: 30, y: 250, text: 'a → b', words: false }));
    expect(report.problems).toContain('characters the font cannot draw: →');
  });

  test('a scene without a story fails', () => {
    const { story, ...bare } = example('flow');
    expect(render(bare).report.problems).toContain('no "story" in the scene');
  });

  test.each([undefined, null, '', 'to-scale', 'scale', 'Flow', 42, ['flow']].map(drawing => [drawing]))('rejects an invalid story drawing: %j', drawing => {
    const scene = example('flow');
    scene.story.drawing = drawing;
    const { code, report } = render(scene);
    const gap = 'story "drawing" must be one of: rewire, to scale, flow, check, bars';
    expect(code).toBe(1);
    expect(report.storyGaps).toContain(gap);
    expect(report.problems).toContain(gap);
  });

  test('every story part must be drawn', () => {
    const scene = example('check');
    scene.story = { ...scene.story, symptom: 'pages went blank', added: ['order-check.py', 'rollback.sh'] };
    const { problems } = render(scene).report;
    expect(problems).toContain('symptom "pages went blank" is not drawn');
    expect(problems).toContain('added part "rollback.sh" is not drawn');
  });

  test('a story needs a quote from a record', () => {
    const scene = example('flow');
    delete scene.story.seen;
    expect(render(scene).report.problems).toContain('story has no "seen" quote from a record');
  });

  test('a to-scale drawing needs its limit line', () => {
    const scene = example('to-scale');
    scene.shapes = scene.shapes.filter(s => s.kind !== 'line');
    expect(render(scene).report.problems).toContain('a to-scale drawing needs the limit as a line and its "number"');
  });

  test('a drawing other than bars needs a ✕', () => {
    const scene = example('flow');
    scene.shapes = scene.shapes.filter(s => s.kind !== 'cross' && !s.crossed);
    expect(render(scene).report.problems).toContain('no ✕ on the old path');
  });

  test('a line through text is a problem', () => {
    const { report } = render(withShapes(example('flow'),
      { kind: 'text', x: 30, y: 280, text: 'crossed out', words: false },
      { kind: 'line', from: [20, 274], to: [200, 274] }));
    expect(report.lineThroughText).toEqual(['crossed out']);
  });

  test('bad input exits 2 without a report', () => {
    const { code, report } = render('{not json');
    expect(code).toBe(2);
    expect(report).toBeNull();
  });
});
