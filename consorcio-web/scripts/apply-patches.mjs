/**
 * Apply `patches/*.patch` after install.
 *
 * Replaces `patch-package`. That package pulls `find-yarn-workspace-root` →
 * `micromatch` → `braces`, and braces ≤3.0.3 has no patched release
 * (GHSA-vfj7-8cjw-p6xm). This repo is not a Yarn workspace, so the only
 * thing we needed from patch-package was applying the unified diffs.
 *
 * Zero dependencies: Node's fs plus a small unified-diff applier. Idempotent
 * — a second run sees the added lines already present and skips the file.
 */
import { readdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const patchesDir = join(root, 'patches');

const HUNK_HEADER = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/;

function parsePatch(text) {
  const lines = text.split('\n');
  if (lines.at(-1) === '') lines.pop();
  const files = [];
  let index = 0;

  while (index < lines.length) {
    if (lines[index].startsWith('diff --git ') || lines[index].startsWith('index ')) {
      index += 1;
      continue;
    }
    if (!lines[index].startsWith('--- ')) {
      index += 1;
      continue;
    }
    const oldPath = lines[index].slice(4).trim();
    index += 1;
    if (index >= lines.length || !lines[index].startsWith('+++ ')) {
      throw new Error(`Parche sin cabecera +++ después de ${oldPath}`);
    }
    const newPath = lines[index].slice(4).trim().replace(/^b\//, '');
    index += 1;
    const hunks = [];
    while (index < lines.length && lines[index].startsWith('@@')) {
      const header = HUNK_HEADER.exec(lines[index]);
      if (!header) throw new Error(`Hunk ilegible: ${lines[index]}`);
      const oldStart = Number(header[1]);
      const oldCount = header[2] === undefined ? 1 : Number(header[2]);
      index += 1;
      const body = [];
      let seen = 0;
      while (seen < oldCount) {
        if (index >= lines.length) throw new Error(`Hunk truncado en ${newPath}`);
        const line = lines[index];
        index += 1;
        if (line.startsWith('\\')) continue;
        const prefix = line[0];
        if (prefix !== ' ' && prefix !== '-' && prefix !== '+') {
          throw new Error(`Línea de hunk inesperada en ${newPath}: ${line}`);
        }
        body.push(line);
        if (prefix === ' ' || prefix === '-') seen += 1;
      }
      hunks.push({ oldStart, body });
    }
    if (oldPath !== '/dev/null') files.push({ path: newPath, hunks });
  }
  return files;
}

function alreadyApplied(original, hunks) {
  const text = original.join('\n');
  const added = [];
  for (const hunk of hunks) {
    for (const line of hunk.body) {
      if (line.startsWith('+')) added.push(line.slice(1));
    }
  }
  return added.length > 0 && added.every((line) => text.includes(line));
}

function applyHunks(original, hunks) {
  const result = [];
  let cursor = 0;
  for (const hunk of hunks) {
    const start = hunk.oldStart - 1;
    if (start < cursor) throw new Error('Los hunks se solapan');
    while (cursor < start) {
      result.push(original[cursor]);
      cursor += 1;
    }
    for (const line of hunk.body) {
      const prefix = line[0];
      const content = line.slice(1);
      if (prefix === ' ') {
        if (original[cursor] !== content) {
          throw new Error(
            `Contexto distinto en la línea ${cursor + 1}: se esperaba ${JSON.stringify(content)} y está ${JSON.stringify(original[cursor])}`,
          );
        }
        result.push(original[cursor]);
        cursor += 1;
      } else if (prefix === '-') {
        if (original[cursor] !== content) {
          throw new Error(
            `Línea a quitar distinta en ${cursor + 1}: se esperaba ${JSON.stringify(content)} y está ${JSON.stringify(original[cursor])}`,
          );
        }
        cursor += 1;
      } else if (prefix === '+') {
        result.push(content);
      }
    }
  }
  while (cursor < original.length) {
    result.push(original[cursor]);
    cursor += 1;
  }
  return result;
}

function installedPackageDir(relativePath) {
  const parts = relativePath.split('/');
  if (parts[0] !== 'node_modules' || parts.length < 2) return null;
  const depth = parts[1].startsWith('@') ? 3 : 2;
  if (parts.length < depth) return null;
  return join(root, parts.slice(0, depth).join('/'));
}

function applyFile(relativePath, hunks) {
  const absolute = join(root, relativePath);
  if (!existsSync(absolute)) {
    // patch-package skipped dev-only patches when NODE_ENV=production omitted
    // the package (Cloudflare Pages sets that). A missing file inside an
    // installed package is still a stale patch and must fail.
    const pkgDir = installedPackageDir(relativePath);
    if (pkgDir && !existsSync(pkgDir)) {
      console.log(`omitido (devDependency no instalada): ${relativePath}`);
      return;
    }
    throw new Error(`No existe ${relativePath}. ¿Falta npm install?`);
  }
  const originalText = readFileSync(absolute, 'utf8');
  const hadTrailingNewline = originalText.endsWith('\n');
  const original = originalText.split('\n');
  if (hadTrailingNewline) original.pop();

  if (alreadyApplied(original, hunks)) {
    console.log(`ya aplicado: ${relativePath}`);
    return;
  }

  let next;
  try {
    next = applyHunks(original, hunks);
  } catch (error) {
    if (alreadyApplied(original, hunks)) {
      console.log(`ya aplicado: ${relativePath}`);
      return;
    }
    throw new Error(`${relativePath}: ${error instanceof Error ? error.message : error}`);
  }
  const body = next.join('\n');
  writeFileSync(absolute, hadTrailingNewline ? `${body}\n` : body);
  console.log(`aplicado: ${relativePath}`);
}

function main() {
  if (!existsSync(patchesDir)) return;
  const patches = readdirSync(patchesDir)
    .filter((name) => name.endsWith('.patch'))
    .sort();
  if (patches.length === 0) return;
  for (const name of patches) {
    const parsed = parsePatch(readFileSync(join(patchesDir, name), 'utf8'));
    if (parsed.length === 0) throw new Error(`${name} no contiene archivos`);
    for (const file of parsed) applyFile(file.path, file.hunks);
  }
}

main();
