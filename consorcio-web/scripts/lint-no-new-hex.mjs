/**
 * Freno de hex nuevos en .ts/.tsx.
 *
 * El repo ya tiene cientos de hex en literales de string. Este script no los
 * reescribe: compara el conteo por archivo contra `hex-color-baseline.json`
 * y falla si un archivo tiene MÁS ocurrencias de un hex que las permitidas.
 *
 * Excepciones, en el fuente:
 *   - `hex-color-allow-file` en las primeras 20 líneas (paleta del tema,
 *     UI y mapa, en `theme.ts`).
 *   - `hex-color-allow` en la misma línea del literal o en la anterior.
 *
 * No mira tests, comentarios ni `.css`. Actualizar la línea de base, a mano
 * y solo cuando el hex nuevo es intencional:
 *   node scripts/lint-no-new-hex.mjs --update
 */

import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const BASELINE_PATH = join(ROOT, 'scripts/hex-color-baseline.json');
const HEX_SOURCE = '#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\\b';

const SCAN_ROOTS = ['src', 'vite.config.ts', 'vite.modulePreload.ts', 'vitest.config.ts'];

function walk(dir, acc) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name === 'dist' || entry.name === 'coverage') {
      continue;
    }
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full, acc);
      continue;
    }
    if (/\.tsx?$/.test(entry.name)) acc.push(full);
  }
  return acc;
}

function filesToScan() {
  const found = [];
  for (const root of SCAN_ROOTS) {
    const full = join(ROOT, root);
    let stat;
    try {
      stat = statSync(full);
    } catch {
      continue;
    }
    if (stat.isDirectory()) walk(full, found);
    else if (stat.isFile() && /\.tsx?$/.test(full)) found.push(full);
  }
  return found;
}

function isFileAllowed(text) {
  return text.split('\n').slice(0, 20).join('\n').includes('hex-color-allow-file');
}

function lineAllowed(lines, lineIndex) {
  const line = lines[lineIndex] ?? '';
  const previous = lines[lineIndex - 1] ?? '';
  return line.includes('hex-color-allow') || previous.includes('hex-color-allow');
}

/**
 * Literales de string (comillas, template). Ignora comentarios.
 * Dentro de un template, `${...}` se recorre como código.
 * @param {string} text
 * @returns {{ line: number, hex: string }[]}
 */
export function collectHexLiterals(_filename, text) {
  if (isFileAllowed(text)) return [];
  const hits = [];
  const lines = text.split('\n');
  const len = text.length;
  let i = 0;
  let line = 0;

  const consumeString = (quote, startLine) => {
    let value = '';
    i += 1;
    while (i < len) {
      const ch = text[i];
      if (ch === '\\') {
        value += ch + (text[i + 1] ?? '');
        if (text[i + 1] === '\n') line += 1;
        i += 2;
        continue;
      }
      if (ch === '\n') line += 1;
      if (quote === '`' && ch === '$' && text[i + 1] === '{') {
        i += 2;
        scanUntilTemplateEnd();
        continue;
      }
      if (ch === quote) {
        i += 1;
        break;
      }
      value += ch;
      i += 1;
    }
    if (!lineAllowed(lines, startLine)) {
      const matches = value.match(new RegExp(HEX_SOURCE, 'g'));
      if (matches) {
        for (const hex of matches) hits.push({ line: startLine + 1, hex });
      }
    }
  };

  const scanUntilTemplateEnd = () => {
    let depth = 1;
    while (i < len && depth > 0) {
      const ch = text[i];
      const next = text[i + 1];
      if (ch === '/' && next === '/') {
        while (i < len && text[i] !== '\n') i += 1;
        continue;
      }
      if (ch === '/' && next === '*') {
        i += 2;
        while (i < len && !(text[i] === '*' && text[i + 1] === '/')) {
          if (text[i] === '\n') line += 1;
          i += 1;
        }
        i += 2;
        continue;
      }
      if (ch === '"' || ch === "'" || ch === '`') {
        consumeString(ch, line);
        continue;
      }
      if (ch === '{') depth += 1;
      if (ch === '}') depth -= 1;
      if (ch === '\n') line += 1;
      if (depth > 0) i += 1;
    }
    if (depth === 0) i += 1;
  };

  while (i < len) {
    const ch = text[i];
    const next = text[i + 1];
    if (ch === '/' && next === '/') {
      while (i < len && text[i] !== '\n') i += 1;
      continue;
    }
    if (ch === '/' && next === '*') {
      i += 2;
      while (i < len && !(text[i] === '*' && text[i + 1] === '/')) {
        if (text[i] === '\n') line += 1;
        i += 1;
      }
      i += 2;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      consumeString(ch, line);
      continue;
    }
    if (ch === '\n') line += 1;
    i += 1;
  }

  return hits;
}

/** @param {{ line: number, hex: string }[]} hits */
export function tallyHexes(hits) {
  /** @type {Record<string, number>} */
  const tally = {};
  for (const hit of hits) {
    tally[hit.hex] = (tally[hit.hex] ?? 0) + 1;
  }
  return tally;
}

/**
 * @param {Record<string, Record<string, number>>} current
 * @param {Record<string, Record<string, number>>} baseline
 */
export function diffHexCounts(current, baseline) {
  /** @type {{ file: string, hex: string, count: number, allowed: number }[]} */
  const violations = [];
  for (const [file, tally] of Object.entries(current)) {
    const allowedForFile = baseline[file] ?? {};
    for (const [hex, count] of Object.entries(tally)) {
      const allowed = allowedForFile[hex] ?? 0;
      if (count > allowed) violations.push({ file, hex, count, allowed });
    }
  }
  return violations;
}

function scanRepo() {
  /** @type {Record<string, Record<string, number>>} */
  const current = {};
  for (const file of filesToScan()) {
    const text = readFileSync(file, 'utf8');
    const hits = collectHexLiterals(file, text);
    const tally = tallyHexes(hits);
    if (Object.keys(tally).length === 0) continue;
    const rel = relative(ROOT, file).split('\\').join('/');
    current[rel] = Object.fromEntries(Object.entries(tally).sort(([a], [b]) => a.localeCompare(b)));
  }
  return Object.fromEntries(Object.entries(current).sort(([a], [b]) => a.localeCompare(b)));
}

function readBaseline() {
  try {
    return JSON.parse(readFileSync(BASELINE_PATH, 'utf8'));
  } catch {
    return {};
  }
}

function main() {
  const current = scanRepo();
  if (process.argv.includes('--update')) {
    writeFileSync(BASELINE_PATH, `${JSON.stringify(current, null, 2)}\n`);
    console.log(`baseline actualizada: ${BASELINE_PATH}`);
    return;
  }
  const violations = diffHexCounts(current, readBaseline());
  if (violations.length === 0) {
    console.log('hex: sin literales nuevos');
    return;
  }
  console.error('Hex nuevo en .ts/.tsx. Usá un token, o un comentario de excepción:');
  console.error('  // hex-color-allow');
  console.error('  /* hex-color-allow-file */  (paleta del tema: UI y mapa)');
  for (const violation of violations) {
    console.error(
      `  ${violation.file}: ${violation.hex} ×${violation.count} (permitido ${violation.allowed})`
    );
  }
  process.exitCode = 1;
}

const isDirectRun = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isDirectRun) main();
