import { afterAll, describe, expect, test } from 'bun:test';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const tool = join(import.meta.dir, '../../../skills/pr-recap/scripts/attachment.mjs');
const { acceptedUrl, check, imageUrls, pastedUrl, readRecord, sha256, stamp, START, END } = await import(tool);

const work = mkdtempSync(join(tmpdir(), 'pr-recap-attachment-test-'));
afterAll(() => rmSync(work, { recursive: true, force: true }));

const UUID = 'e3629061-0b4a-41f5-a255-07b1eaf1d86b';
const DOTCOM = `https://github.com/user-attachments/assets/${UUID}`;
const GHES = `https://git.example.test/user-attachments/assets/${UUID}`;
const png = Buffer.from('not really a png');
const editorImg = url => `<img width="782" height="250" alt="Image" src="${url}" />`;
const body = (image, extra = '') => `${START}\n${extra}Story.\n\n${image}\n\n**Not covered.** x\n${END}\n`;

function run(args, files = {}) {
  const paths = Object.fromEntries(Object.entries(files).map(([name, content]) => {
    const path = join(work, `${Math.random().toString(36).slice(2)}-${name}`);
    writeFileSync(path, content);
    return [name, path];
  }));
  const r = Bun.spawnSync([process.execPath, tool, ...args(paths)]);
  return { code: r.exitCode, out: r.stdout.toString(), err: r.stderr.toString() };
}

describe('accepted attachment URLs', () => {
  test('accepts the github.com and GHES forms for their own host', () => {
    expect(acceptedUrl(DOTCOM, 'github.com')).toBe(true);
    expect(acceptedUrl(GHES, 'git.example.test')).toBe(true);
    expect(acceptedUrl(GHES, 'GIT.example.test')).toBe(true);
  });

  test('rejects another host, another path, http, a query, and a non-uuid id', () => {
    expect(acceptedUrl(GHES, 'github.com')).toBe(false);
    expect(acceptedUrl(DOTCOM, 'git.example.test')).toBe(false);
    expect(acceptedUrl(`https://git.example.test.evil.test/user-attachments/assets/${UUID}`, 'git.example.test')).toBe(false);
    expect(acceptedUrl(`https://git.example.test/user-attachments/files/${UUID}`, 'git.example.test')).toBe(false);
    expect(acceptedUrl(GHES.replace('https', 'http'), 'git.example.test')).toBe(false);
    expect(acceptedUrl(`${GHES}?x=1`, 'git.example.test')).toBe(false);
    expect(acceptedUrl('https://git.example.test/user-attachments/assets/abc', 'git.example.test')).toBe(false);
  });

  test('finds the URL in markdown image form and in the editor img form', () => {
    expect(imageUrls(`![alt text](${GHES})`, 'git.example.test')).toEqual([GHES]);
    expect(imageUrls(`![alt](<${GHES}> "title")`, 'git.example.test')).toEqual([GHES]);
    expect(imageUrls(editorImg(GHES), 'git.example.test')).toEqual([GHES]);
    expect(imageUrls(`<img src='${GHES}'>`, 'git.example.test')).toEqual([GHES]);
    expect(imageUrls(`[a link](${GHES})`, 'git.example.test')).toEqual([]);
    expect(imageUrls(`![alt](${DOTCOM})`, 'git.example.test')).toEqual([]);
  });

  test('a pasted bare URL, markdown, or img markup normalizes to the URL', () => {
    for (const pasted of [GHES, `\n  ${GHES}\n`, `![Image](${GHES})`, editorImg(GHES), `see ${GHES} now`]) {
      expect(pastedUrl(pasted, 'git.example.test')).toBe(GHES);
    }
    expect(pastedUrl(`https://elsewhere.test/a.png and ${DOTCOM}`, 'git.example.test')).toBeUndefined();
  });
});

describe('record, stamp, and check', () => {
  test('stamp puts the record on the line after the start marker and keeps the marker first', () => {
    const stamped = stamp(body('![alt](./sketch.png)'), png, 'git.example.test', GHES);
    expect(stamped.startsWith(`${START}\n<!-- pstack-recap:sketch sha256=${sha256(png)} url=${GHES} -->\nStory.`)).toBe(true);
    expect(stamped).toContain(`![alt](${GHES})`);
    expect(readRecord(stamped)).toEqual({ sha256: sha256(png), url: GHES });
  });

  test('stamping a stamped body replaces the record instead of stacking a second one', () => {
    const once = stamp(body(editorImg(GHES)), png, 'git.example.test');
    const other = Buffer.from('a different sketch');
    const twice = stamp(once, other, 'git.example.test');
    expect(twice.match(/pstack-recap:sketch/g)).toHaveLength(1);
    expect(readRecord(twice).sha256).toBe(sha256(other));
    expect(twice.startsWith(`${START}\n`)).toBe(true);
  });

  test('stamp refuses a body with no attachment image, a foreign URL, or a missing start marker', () => {
    expect(() => stamp(body('![alt](./sketch.png)'), png, 'git.example.test')).toThrow('no git.example.test attachment image');
    expect(() => stamp(body('![alt](./sketch.png)'), png, 'git.example.test', DOTCOM)).toThrow('not a git.example.test attachment URL');
    expect(() => stamp(`intro\n${body(editorImg(GHES))}`, png, 'git.example.test')).toThrow('must start with');
  });

  test('check passes both image forms and reports each failure on its own line', () => {
    const head = 'abcd1234';
    for (const image of [`![alt](${GHES})`, editorImg(GHES)]) {
      expect(check(body(image, `${head}\n`), 'git.example.test', head)).toEqual({ problems: [], url: GHES });
    }
    const bad = check(`intro\n${START}\nStory.\n![alt](${DOTCOM})\n`, 'git.example.test', head);
    expect(bad.problems).toHaveLength(4);
    const mismatch = body(editorImg(GHES), `<!-- pstack-recap:sketch sha256=${sha256(png)} url=${DOTCOM} -->\n`);
    expect(check(mismatch, 'git.example.test').problems).toEqual(['the recorded URL is not the image URL']);
  });
});

describe('command line', () => {
  test('check --no-image accepts a recap posted without a sketch and still demands the markers and head SHA', () => {
    const head = 'abcd1234';
    const bare = `${START}\nStory.\n\n**Not covered.** x\n${head}\n${END}\n`;
    expect(check(bare, 'git.example.test', head, false)).toEqual({ problems: [], url: undefined });
    expect(check(bare, 'git.example.test', head).problems).toEqual(['the body holds no git.example.test attachment image']);
    const ok = run(f => ['check', '--host', 'git.example.test', '--head', head, '--no-image', f.body], { body: bare });
    expect([ok.code, ok.out]).toEqual([0, '']);
    const noHead = run(f => ['check', '--host', 'git.example.test', '--head', 'ffffffff', '--no-image', f.body], { body: bare });
    expect(noHead.code).toBe(1);
    expect(noHead.err).toContain('the body lacks head SHA ffffffff');
    const noMarkers = run(f => ['check', '--host', 'git.example.test', '--no-image', f.body], { body: 'just text' });
    expect(noMarkers.code).toBe(1);
  });

  test('check --no-image fails on a missing start marker, a missing end marker, and a record URL the body lacks', () => {
    const head = 'abcd1234';
    const record = url => `<!-- pstack-recap:sketch sha256=${sha256(png)} url=${url} -->\n`;
    const cases = [
      ['start marker', `Story.\n\n**Not covered.** x\n${head}\n${END}\n`, `the body does not start with ${START}`],
      ['end marker', `${START}\nStory.\n\n**Not covered.** x\n${head}\n`, `the body lacks ${END}`],
      ['record URL', `${START}\n${record(GHES)}Story.\n\n**Not covered.** x\n${head}\n${END}\n`, 'the recorded URL is not the image URL'],
    ];
    for (const [name, text, problem] of cases) {
      expect(check(text, 'git.example.test', head, false).problems).toEqual([problem]);
      const r = run(f => ['check', '--host', 'git.example.test', '--head', head, '--no-image', f.body], { body: text });
      expect([name, r.code, r.err]).toEqual([name, 1, `${problem}\n`]);
    }
    const sketched = `${START}\n${record(GHES)}Story.\n\n${editorImg(GHES)}\n${head}\n${END}\n`;
    const ok = run(f => ['check', '--host', 'git.example.test', '--head', head, '--no-image', f.body], { body: sketched });
    expect([ok.code, ok.out]).toEqual([0, `${GHES}\n`]);
  });

  test('url prints the normalized URL from pasted markup and exits 1 on a foreign one', () => {
    const ok = run(f => ['url', '--host', 'git.example.test', f.paste], { paste: editorImg(GHES) });
    expect([ok.code, ok.out]).toEqual([0, `${GHES}\n`]);
    const bad = run(f => ['url', '--host', 'git.example.test', f.paste], { paste: editorImg(DOTCOM) });
    expect(bad.code).toBe(1);
    expect(bad.err).toContain('no https://git.example.test/user-attachments/assets/<uuid> URL found');
  });

  test('reuse prints the recorded URL only when the sketch hash is unchanged', () => {
    const recorded = stamp(body('![alt](./sketch.png)'), png, 'git.example.test', GHES);
    const same = run(f => ['reuse', '--host', 'git.example.test', f.png, f.body], { png, body: recorded });
    expect([same.code, same.out]).toEqual([0, `${GHES}\n`]);
    const changed = run(f => ['reuse', '--host', 'git.example.test', f.png, f.body], { png: 'redrawn', body: recorded });
    expect(changed.code).toBe(1);
    const noRecord = run(f => ['reuse', '--host', 'git.example.test', f.png, f.body], { png, body: body(editorImg(GHES)) });
    expect(noRecord.code).toBe(1);
  });

  test('stamp and check handle a body that the web editor saved with CRLF line endings', () => {
    const recorded = stamp(body('![alt](./sketch.png)'), png, 'git.example.test', GHES).replaceAll('\n', '\r\n');
    const reuse = run(f => ['reuse', '--host', 'git.example.test', f.png, f.body], { png, body: recorded });
    expect([reuse.code, reuse.out]).toEqual([0, `${GHES}\n`]);
    const read = run(f => ['check', '--host', 'git.example.test', f.body], { body: recorded });
    expect([read.code, read.out]).toEqual([0, `${GHES}\n`]);
    const restamp = run(f => ['stamp', '--host', 'git.example.test', f.png, f.body], { png, body: recorded });
    expect(restamp.code).toBe(0);
    expect(restamp.out).not.toContain('\r');
  });

  test('stamp substitutes the pasted URL for the local image reference', () => {
    const r = run(f => ['stamp', '--host', 'git.example.test', f.png, f.body, GHES], { png, body: body('![alt](./sketch.png)') });
    expect(r.code).toBe(0);
    expect(readRecord(r.out)).toEqual({ sha256: sha256(png), url: GHES });
  });

  test('a command without --host or with an unknown name exits 1', () => {
    expect(run(() => ['check']).code).toBe(1);
    expect(run(() => ['nope', '--host', 'github.com']).code).toBe(1);
  });
});
