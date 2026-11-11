#!/usr/bin/env node
// Build games/camera/dist for /play/.
// - Copies src/ as-is (vanilla ES modules, relative URLs only).
// - Copies the pinned MediaPipe runtime from node_modules after sha256 checks.
// - Downloads the pinned gesture model at BUILD time (cached in .cache/), verifies
//   size + sha256, and serves it locally. The browser never contacts a third party.
// Offline builds: set TEREBI_GESTURE_MODEL=/path/to/gesture_recognizer.task
// (still checksum-verified).

import { createHash } from 'node:crypto';
import { cp, mkdir, readFile, readdir, rename, rm, stat, writeFile } from 'node:fs/promises';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SRC = join(ROOT, 'src');
const DIST = join(ROOT, 'dist');
const CACHE = join(ROOT, '.cache');
const manifest = JSON.parse(await readFile(join(ROOT, 'assets.manifest.json'), 'utf8'));

const sha256 = (buf) => createHash('sha256').update(buf).digest('hex');
const fail = (msg) => {
  console.error(`build: ${msg}`);
  process.exit(1);
};

async function exists(p) {
  try {
    await stat(p);
    return true;
  } catch {
    return false;
  }
}

async function verifiedRuntimeFiles() {
  const pkgDir = join(ROOT, 'node_modules', ...manifest.runtime.package.split('/'));
  const pkg = JSON.parse(await readFile(join(pkgDir, 'package.json'), 'utf8')).version;
  if (pkg !== manifest.runtime.version) fail(`${manifest.runtime.package} is ${pkg}, manifest pins ${manifest.runtime.version}. Run npm ci.`);
  const out = [];
  for (const f of manifest.runtime.files) {
    const buf = await readFile(join(pkgDir, f.from));
    const got = sha256(buf);
    if (got !== f.sha256) fail(`checksum mismatch for ${f.from}: ${got}`);
    out.push({ to: f.to, buf });
  }
  return out;
}

async function fetchModel(model) {
  const override = process.env.TEREBI_GESTURE_MODEL;
  const cached = join(CACHE, 'models', `${model.sha256}.task`);
  const check = (buf, where) => {
    if (buf.length !== model.bytes) fail(`${where}: expected ${model.bytes} bytes, got ${buf.length}`);
    const got = sha256(buf);
    if (got !== model.sha256) fail(`${where}: sha256 ${got} != pinned ${model.sha256}`);
    return buf;
  };
  if (override) return check(await readFile(override), override);
  if (await exists(cached)) return check(await readFile(cached), cached);
  console.log(`build: downloading ${model.url}`);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 120_000);
  let res;
  try {
    res = await fetch(model.url, { signal: ctrl.signal, redirect: 'error' });
  } catch (err) {
    fail(`model download failed: ${err.message}`);
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) fail(`model download HTTP ${res.status}`);
  const buf = check(Buffer.from(await res.arrayBuffer()), model.url);
  await mkdir(dirname(cached), { recursive: true });
  const tmp = `${cached}.${process.pid}.tmp`;
  await writeFile(tmp, buf);
  await rename(tmp, cached);
  return buf;
}

async function walk(dir) {
  const out = [];
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out.push(...(await walk(p)));
    else out.push(p);
  }
  return out;
}

// Our own code must not reference any absolute/remote URL.
async function assertNoRemoteUrls() {
  for (const file of await walk(SRC)) {
    const text = await readFile(file, 'utf8');
    const m = text.match(/\b(?:https?:)?\/\/[a-z0-9.-]+\.[a-z]{2,}/i);
    if (m) fail(`${relative(ROOT, file)} references a remote URL (${m[0]}); /play/ must be self-contained.`);
  }
}

await assertNoRemoteUrls();
const runtime = await verifiedRuntimeFiles();
const models = [];
for (const m of manifest.models) models.push({ to: m.to, buf: await fetchModel(m) });

await rm(DIST, { recursive: true, force: true });
await cp(SRC, DIST, { recursive: true });
for (const f of [...runtime, ...models]) {
  await mkdir(dirname(join(DIST, f.to)), { recursive: true });
  await writeFile(join(DIST, f.to), f.buf);
}
await writeFile(
  join(DIST, 'vendor', 'NOTICE.txt'),
  [
    `${manifest.runtime.package}@${manifest.runtime.version} — ${manifest.runtime.license}`,
    'Copyright Google LLC / The MediaPipe Authors.',
    ...manifest.models.map((m) => `${m.to}: ${m.name} from ${m.url} (sha256 ${m.sha256}). License: ${m.license}`),
    '',
  ].join('\n'),
);
const files = (await walk(DIST)).map((p) => relative(DIST, p)).sort();
await writeFile(join(DIST, 'build-manifest.json'), `${JSON.stringify({ runtime: `${manifest.runtime.package}@${manifest.runtime.version}`, files }, null, 2)}\n`);
console.log(`build: wrote ${files.length + 1} files to ${relative(process.cwd(), DIST) || 'dist'}`);
