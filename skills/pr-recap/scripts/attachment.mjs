#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export const START = '<!-- pstack-recap:start -->';
export const END = '<!-- pstack-recap:end -->';
const PLACEHOLDER = './sketch.png';
const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const RECORD_LINE = '<!-- pstack-recap:sketch sha256=([0-9a-f]{64}) url=(\\S+) -->';
const RECORD = new RegExp(`^${RECORD_LINE}$`, 'm');
const RECORD_AND_NEWLINE = new RegExp(`^${RECORD_LINE}\\n`, 'm');
const IMAGE_FORMS = [
  /!\[[^\]]*\]\(\s*<?([^\s)>]+)>?(?:\s+"[^"]*")?\s*\)/g,
  /<img\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']/gi,
];

export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

// GitHub's docs do not publish the attachment URL shape. This is the shape that github.com and a GHES
// instance returned for a native upload.
export function acceptedUrl(url, host) {
  const m = new RegExp(`^https://([^/]+)/user-attachments/assets/${UUID}$`).exec(url);
  return m !== null && m[1].toLowerCase() === host.toLowerCase();
}

export function imageUrls(text, host) {
  return IMAGE_FORMS.flatMap(form => [...text.matchAll(form)].map(m => m[1])).filter(url => acceptedUrl(url, host));
}

export function pastedUrl(text, host) {
  const bare = [...text.matchAll(/https:\/\/[^\s"'<>()]+/g)].map(m => m[0]);
  return [...imageUrls(text, host), ...bare].find(url => acceptedUrl(url, host));
}

export function readRecord(body) {
  const m = RECORD.exec(body);
  return m === null ? undefined : { sha256: m[1], url: m[2] };
}

export function stamp(body, png, host, url) {
  if (url !== undefined && !acceptedUrl(url, host)) throw new Error(`${url} is not a ${host} attachment URL`);
  const out = (url === undefined ? body : body.replaceAll(PLACEHOLDER, url)).replace(RECORD_AND_NEWLINE, '');
  const found = imageUrls(out, host)[0];
  if (found === undefined) throw new Error(`no ${host} attachment image in the body; pass the attachment URL to replace ${PLACEHOLDER}`);
  if (!out.startsWith(START)) throw new Error(`the body must start with ${START}`);
  const record = `<!-- pstack-recap:sketch sha256=${sha256(png)} url=${found} -->`;
  return `${START}\n${record}${out.slice(START.length)}`;
}

export function check(body, host, head) {
  const problems = [];
  if (!body.trimStart().startsWith(START)) problems.push(`the body does not start with ${START}`);
  if (!body.includes(END)) problems.push(`the body lacks ${END}`);
  if (head !== undefined && !body.includes(head)) problems.push(`the body lacks head SHA ${head}`);
  const urls = imageUrls(body, host);
  if (urls.length === 0) problems.push(`the body holds no ${host} attachment image`);
  const record = readRecord(body);
  if (record !== undefined && !urls.includes(record.url)) problems.push('the recorded URL is not the image URL');
  return { problems, url: urls[0] };
}

const readText = path => readFileSync(path, 'utf8').replaceAll('\r\n', '\n');

function main(argv) {
  const [command, ...rest] = argv;
  const opts = {};
  const args = [];
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === '--host' || rest[i] === '--head') opts[rest[i].slice(2)] = rest[++i];
    else args.push(rest[i]);
  }
  const fail = message => { console.error(message); process.exit(1); };
  if (opts.host === undefined) fail('usage: attachment.mjs <url|reuse|stamp|check> --host <host> ...');
  try {
    if (command === 'url') {
      const url = pastedUrl(readText(args[0]), opts.host);
      if (url === undefined) fail(`no https://${opts.host}/user-attachments/assets/<uuid> URL found`);
      console.log(url);
    } else if (command === 'reuse') {
      const record = readRecord(readText(args[1]));
      if (record === undefined || record.sha256 !== sha256(readFileSync(args[0])) || !acceptedUrl(record.url, opts.host)) fail('no reusable attachment');
      console.log(record.url);
    } else if (command === 'stamp') {
      process.stdout.write(stamp(readText(args[1]), readFileSync(args[0]), opts.host, args[2]));
    } else if (command === 'check') {
      const { problems, url } = check(readText(args[0]), opts.host, opts.head);
      if (problems.length > 0) fail(problems.join('\n'));
      console.log(url);
    } else {
      fail(`unknown command ${command}`);
    }
  } catch (e) {
    fail(e.message);
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main(process.argv.slice(2));
