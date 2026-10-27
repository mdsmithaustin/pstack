import { afterAll, describe, expect, test } from 'bun:test';
import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { delimiter, dirname, join } from 'node:path';

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

const copySketch = dir => {
  const renderer = join(dir, 'renderer');
  cpSync(join(skill, 'scripts/sketch'), renderer, {
    recursive: true,
    filter: path => !path.split(/[\\/]/).includes('node_modules'),
  });
  return join(renderer, 'sketch.mjs');
};

const example = name => JSON.parse(readFileSync(join(examples, `${name}.json`), 'utf8'));
const withShapes = (scene, ...shapes) => ({ ...scene, shapes: [...scene.shapes, ...shapes] });

describe('sketch tool', () => {
  test('fallback avoids forged dependencies and cleans up on every exit', () => {
    const fixture = mkdtempSync(join(work, 'fallback-'));
    const renderer = dirname(copySketch(fixture));
    writeFileSync(join(renderer, 'node_modules'), 'installation blocked');
    const temp = join(fixture, 'tmp');
    mkdirSync(temp);
    const key = createHash('sha256')
      .update(readFileSync(join(renderer, 'package.json'))).update('\0')
      .update(readFileSync(join(renderer, 'bun.lock'))).digest('hex');
    const poison = join(temp, `pr-recap-sketch-${key.slice(0, 12)}`, 'node_modules');
    mkdirSync(join(poison, 'opentype.js'), { recursive: true });
    writeFileSync(join(poison, '.pr-recap-sketch-install-key'), `${key}\n`);
    const executed = join(fixture, 'poison-executed');
    writeFileSync(join(poison, 'opentype.js/index.js'),
      `require('node:fs').writeFileSync(${JSON.stringify(executed)}, 'executed'); throw new Error('forged dependency');`);
    const originalEntries = readdirSync(temp);
    const outPath = join(fixture, 'sketch.png');
    const r = Bun.spawnSync([process.execPath, join(renderer, 'sketch.mjs'), join(examples, 'flow.json'), outPath], {
      env: { ...process.env, TMPDIR: temp, TMP: temp, TEMP: temp },
    });
    expect(existsSync(executed)).toBe(false);
    expect(r.exitCode).toBe(0);
    expect(JSON.parse(r.stdout.toString()).problems).toEqual([]);
    expect(readFileSync(outPath).subarray(1, 4).toString()).toBe('PNG');
    expect(readdirSync(temp)).toEqual(originalEntries);

    const rejected = example('flow');
    delete rejected.story;
    const scenePath = join(fixture, 'scene.json');
    for (const { scene, output, installFailure, message, code } of [
      { scene: JSON.stringify(rejected), output: outPath, code: 1 },
      { scene: '{not json', output: outPath, code: 2, message: 'bad scene:' },
      { scene: JSON.stringify(example('flow')), output: join(fixture, 'missing', 'sketch.png'), code: 2, message: 'render failed:' },
      { scene: JSON.stringify(example('flow')), output: outPath, installFailure: true, code: 2, message: 'could not install the sketch packages' },
    ]) {
      writeFileSync(scenePath, scene);
      if (installFailure) writeFileSync(join(renderer, 'bun.lock'), 'not a lockfile');
      const result = Bun.spawnSync([process.execPath, join(renderer, 'sketch.mjs'), scenePath, output], {
        env: { ...process.env, TMPDIR: temp, TMP: temp, TEMP: temp },
      });
      expect(result.exitCode).toBe(code);
      if (message) expect(result.stderr.toString()).toContain(message);
      expect(readdirSync(temp)).toEqual(originalEntries);
    }
  }, 30000);

  describe('Bun version check', () => {
    const flow = join(examples, 'flow.json');
    const npx = ['--allow-scripts=bun', 'bun@1.4.0'];
    const oddDir = prefix => realpathSync(mkdtempSync(join(work, `${prefix}-it's a $HOME \`dir\` `)));
    const bunAs = version => {
      const preload = join(work, `bun-${version}.mjs`);
      writeFileSync(preload, `Object.defineProperty(process.versions, 'bun', { value: '${version}' });`);
      return ['--preload', preload];
    };
    const printedArgs = (stderr, dir) => {
      const command = stderr.match(/^ {2}(npx .*)$/m)?.[1];
      expect(command).toBeDefined();
      const bin = join(dir, 'fake-npx');
      mkdirSync(bin, { recursive: true });
      const record = join(dir, 'npx-args');
      writeFileSync(join(bin, 'npx'), '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$NPX_ARGS"\n', { mode: 0o755 });
      const r = Bun.spawnSync(['/bin/sh', '-c', command], { env: { ...process.env, NPX_ARGS: record, PATH: `${bin}${delimiter}${process.env.PATH}` } });
      expect(r.exitCode).toBe(0);
      return readFileSync(record, 'utf8').split('\n').slice(0, -1);
    };

    for (const version of ['1.1.38', '1.3.9', '0.8.1']) {
      test(`Bun ${version} refuses before it installs anything and prints a command that runs`, () => {
        const dir = oddDir('old-bun');
        const renderer = copySketch(dir);
        const scene = join(dir, 'a scene.json');
        const out = join(dir, 'out.png');
        const r = Bun.spawnSync([process.execPath, ...bunAs(version), renderer, scene, out]);
        const stderr = r.stderr.toString();
        expect(r.exitCode).toBe(2);
        expect(stderr).toContain(`this is Bun ${version}`);
        expect(r.stdout.toString()).toBe('');
        expect(existsSync(out)).toBe(false);
        expect(existsSync(join(dirname(renderer), 'node_modules'))).toBe(false);
        expect(printedArgs(stderr, dir)).toEqual([...npx, renderer, scene, out]);
      });
    }

    test('the printed command turns relative scene and output paths into absolute ones', () => {
      const dir = oddDir('relative');
      const renderer = copySketch(dir);
      const r = Bun.spawnSync([process.execPath, ...bunAs('1.1.38'), renderer, 'scene.json', 'out.png'], { cwd: dir });
      expect(printedArgs(r.stderr.toString(), dir)).toEqual([...npx, renderer, join(dir, 'scene.json'), join(dir, 'out.png')]);
    });

    test('Bun 1.4.0 and later get past the check and render', () => {
      for (const version of ['1.4.0', '1.4.2', '1.10.0', '2.0.0', '1.4.0-canary.1']) {
        const out = join(work, `bun-${version}.png`);
        const r = Bun.spawnSync([process.execPath, ...bunAs(version), tool, flow, out]);
        expect(r.stderr.toString()).toBe('');
        expect(r.exitCode).toBe(0);
        expect(JSON.parse(r.stdout.toString()).problems).toEqual([]);
        expect(readFileSync(out).subarray(1, 4).toString()).toBe('PNG');
      }
    }, 30000);

    const node = Bun.which('node');
    const nodeMajor = node ? Number(Bun.spawnSync([node, '--version']).stdout.toString().match(/^v(\d+)/)?.[1]) : 0;
    const nodeTest = node && nodeMajor >= 20 && process.platform !== 'win32' ? test : test.skip;

    nodeTest('Node installs and renders when the Bun on PATH is current', () => {
      const dir = oddDir('current-bun');
      const renderer = copySketch(dir);
      const out = join(dir, 'sketch.png');
      const r = Bun.spawnSync([node, renderer, flow, out], {
        env: { ...process.env, PATH: `${dirname(process.execPath)}${delimiter}${process.env.PATH}` },
      });
      expect(r.exitCode).toBe(0);
      expect(JSON.parse(r.stdout.toString()).problems).toEqual([]);
      expect(readFileSync(out).subarray(1, 4).toString()).toBe('PNG');
      expect(existsSync(join(dirname(renderer), 'node_modules/.pr-recap-sketch-install-key'))).toBe(true);
    }, 30000);

    nodeTest('Node refuses when the Bun on PATH is older than 1.4.0', () => {
      const dir = oddDir('old-bun-path');
      const renderer = copySketch(dir);
      const bin = join(dir, 'bin');
      mkdirSync(bin);
      writeFileSync(join(bin, 'bun'), '#!/bin/sh\nif [ "$1" = "--version" ]; then echo 1.1.38; else echo "installed" > "$PWD/installed-by-old-bun"; fi\n', { mode: 0o755 });
      const scene = join(dir, 'scene.json');
      const out = join(dir, 'sketch.png');
      const r = Bun.spawnSync([node, renderer, scene, out], { env: { ...process.env, PATH: `${bin}${delimiter}${process.env.PATH}` } });
      const stderr = r.stderr.toString();
      expect(r.exitCode).toBe(2);
      expect(stderr).toContain('this is Bun 1.1.38');
      expect(existsSync(join(dirname(renderer), 'installed-by-old-bun'))).toBe(false);
      expect(existsSync(join(dirname(renderer), 'node_modules'))).toBe(false);
      expect(printedArgs(stderr, dir)).toEqual([...npx, renderer, scene, out]);
    });

    nodeTest('Node with no bun on PATH prints the npx command and installs nothing', () => {
      const dir = oddDir('no-bun');
      const renderer = copySketch(dir);
      const empty = join(dir, 'empty');
      const temp = join(dir, 'tmp');
      mkdirSync(empty);
      mkdirSync(temp);
      const scene = join(dir, 'scene.json');
      const out = join(dir, 'sketch.png');
      const r = Bun.spawnSync([node, renderer, scene, out], { env: { ...process.env, PATH: empty, TMPDIR: temp, TMP: temp, TEMP: temp } });
      const stderr = r.stderr.toString();
      expect(r.exitCode).toBe(2);
      expect(stderr).toContain('no working bun on PATH');
      expect(existsSync(join(dirname(renderer), 'node_modules'))).toBe(false);
      expect(readdirSync(temp)).toEqual([]);
      expect(printedArgs(stderr, dir)).toEqual([...npx, renderer, scene, out]);
    });

    for (const [name, versionLine] of [['prints nothing', ''], ['prints a current version', 'echo 1.4.0; ']]) {
      nodeTest(`Node refuses when a bun on PATH exits 1 and ${name}`, () => {
        const dir = oddDir('failing-bun');
        const renderer = copySketch(dir);
        const bin = join(dir, 'bin');
        const temp = join(dir, 'tmp');
        mkdirSync(bin);
        mkdirSync(temp);
        writeFileSync(join(bin, 'bun'), `#!/bin/sh\nif [ "$1" = "--version" ]; then ${versionLine}exit 1; fi\necho "$@" > "$PWD/installed-by-failing-bun"\nexit 1\n`, { mode: 0o755 });
        const scene = join(dir, 'scene.json');
        const out = join(dir, 'sketch.png');
        const r = Bun.spawnSync([node, renderer, scene, out], { cwd: dir, env: { ...process.env, PATH: bin, TMPDIR: temp, TMP: temp, TEMP: temp } });
        const stderr = r.stderr.toString();
        expect(r.exitCode).toBe(2);
        expect(stderr).toContain('no working bun on PATH');
        expect(existsSync(join(dir, 'installed-by-failing-bun'))).toBe(false);
        expect(existsSync(join(dirname(renderer), 'node_modules'))).toBe(false);
        expect(readdirSync(temp)).toEqual([]);
        expect(printedArgs(stderr, dir)).toEqual([...npx, renderer, scene, out]);
      });
    }
  });

  test('a scene that is not an object, or a field that is not a number or a known word, exits 2', () => {
    const flow = example('flow');
    for (const scene of [
      'null',
      withShapes(flow, null),
      withShapes(flow, { kind: 'text', x: 20, y: 300, text: 'ok', anchor: 'start"/><image href="/x.png' }),
      withShapes(flow, { kind: 'box', x: '20"/>', y: 10, w: 40, h: 40, label: 'a' }),
      withShapes(flow, { kind: 'arrow', from: [0, 0], to: [1] }),
      withShapes(flow, { kind: 'page', x: 10, y: 10, w: 80, h: 80, bands: [{ y0: 'a', y1: 20 }] }),
    ]) {
      const { code, stderr } = render(scene);
      expect(code).toBe(2);
      expect(stderr).toContain('bad scene:');
    }
  });

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
