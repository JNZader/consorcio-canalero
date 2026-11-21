/**
 * Freno de colores literales (hex y rgb/rgba) nuevos en .ts/.tsx/.css.
 *
 * El repo ya tiene cientos de literales históricos. Este script no los
 * reescribe: compara el conteo por archivo contra `hex-color-baseline.json`
 * y falla si un archivo tiene MÁS ocurrencias de un color que las permitidas.
 *
 * Excepciones, en el fuente:
 *   - `hex-color-allow-file` en las primeras 20 líneas (paleta del tema,
 *     UI y mapa, en `theme.ts`).
 *   - `hex-color-allow` en la misma línea del literal o en la anterior.
 *
 * No mira tests ni comentarios. Actualizar la línea de base, a mano
 * y solo cuando el color nuevo es intencional:
 *   node scripts/lint-no-new-hex.mjs --update
 */

import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const BASELINE_PATH = join(ROOT, 'scripts/hex-color-baseline.json');
const HEX_PATTERN = '#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\\b';
const RGB_COMMA_PATTERN =
  'rgba?\\(\\s*\\d{1,3}(?:\\s*,\\s*\\d{1,3}){2}(?:\\s*,\\s*(?:0?\\.\\d+|1(?:\\.0+)?|0))?\\s*\\)';
const RGB_SPACE_PATTERN =
  'rgba?\\(\\s*\\d{1,3}(?:\\s+\\d{1,3}){2}(?:\\s*\\/\\s*(?:0?\\.\\d+|1(?:\\.0+)?|0|\\d{1,3}%))?\\s*\\)';
const COLOR_SOURCE = `${HEX_PATTERN}|${RGB_COMMA_PATTERN}|${RGB_SPACE_PATTERN}`;
const FILE_EXT_RE = /\.(?:tsx?|css)$/;

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
    if (FILE_EXT_RE.test(entry.name)) acc.push(full);
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
    else if (stat.isFile() && FILE_EXT_RE.test(full)) found.push(full);
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

export function normalizeColorToken(raw) {
  if (raw.startsWith('#')) return raw;
  return raw
    .toLowerCase()
    .replace(/\(\s+/g, '(')
    .replace(/\s+\)/g, ')')
    .replace(/\s*,\s*/g, ', ')
    .replace(/\s*\/\s*/g, ' / ')
    .replace(/\s{2,}/g, ' ');
}

function neutralizeCssUrls(value) {
  return value.replace(/url\((?:[^)"']|"[^"]*"|'[^']*')*\)/gi, (match) =>
    match.replace(/[^\n]/g, ' ')
  );
}

function collectCssColorLiterals(text) {
  const hits = [];
  const lines = text.split('\n');
  const len = text.length;
  let line = 0;
  let declText = '';
  let declStartLine = 0;

  const flushDeclaration = () => {
    const raw = declText;
    const startLine = declStartLine;
    declText = '';
    if (!raw.trim()) return;

    let colonIndex = -1;
    let depth = 0;
    let quote = null;
    for (let k = 0; k < raw.length; k += 1) {
      const ch = raw[k];
      if (quote) {
        if (ch === '\\') {
          k += 1;
          continue;
        }
        if (ch === quote) quote = null;
        continue;
      }
      if (ch === '"' || ch === "'") {
        quote = ch;
        continue;
      }
      if (ch === '(') depth += 1;
      else if (ch === ')' && depth > 0) depth -= 1;
      else if (ch === ':' && depth === 0) {
        colonIndex = k;
        break;
      }
    }
    if (colonIndex === -1) return;

    const prefix = raw.slice(0, colonIndex + 1);
    const valueStartLine = startLine + (prefix.match(/\n/g) ?? []).length;
    const value = neutralizeCssUrls(raw.slice(colonIndex + 1));

    const regex = new RegExp(COLOR_SOURCE, 'gi');
    let match;
    while ((match = regex.exec(value)) !== null) {
      const preceding = value.slice(0, match.index);
      const matchLine = valueStartLine + (preceding.match(/\n/g) ?? []).length;
      if (!lineAllowed(lines, matchLine)) {
        hits.push({ line: matchLine + 1, hex: normalizeColorToken(match[0]) });
      }
    }
  };

  let i = 0;
  while (i < len) {
    const ch = text[i];
    const next = text[i + 1];
    if (ch === '/' && next === '*') {
      if (declText.length === 0) declStartLine = line;
      declText += ' ';
      i += 2;
      while (i < len && !(text[i] === '*' && text[i + 1] === '/')) {
        if (text[i] === '\n') {
          line += 1;
          declText += '\n';
        }
        i += 1;
      }
      i += 2;
      continue;
    }
    if (ch === '"' || ch === "'") {
      if (declText.length === 0) declStartLine = line;
      const quote = ch;
      declText += ch;
      i += 1;
      while (i < len) {
        const sCh = text[i];
        if (sCh === '\\') {
          declText += sCh + (text[i + 1] ?? '');
          if (text[i + 1] === '\n') line += 1;
          i += 2;
          continue;
        }
        if (sCh === '\n') line += 1;
        declText += sCh;
        i += 1;
        if (sCh === quote) break;
      }
      continue;
    }
    if (ch === '{') {
      declText = '';
      i += 1;
      continue;
    }
    if (ch === ';' || ch === '}') {
      flushDeclaration();
      i += 1;
      continue;
    }
    if (declText.length === 0) declStartLine = line;
    declText += ch;
    if (ch === '\n') line += 1;
    i += 1;
  }

  flushDeclaration();
  return hits;
}

/**
 * Literales de color en strings `.ts/.tsx` o declaraciones `.css`. Ignora comentarios.
 * Dentro de un template, `${...}` se recorre como código.
 * @param {string} filename
 * @param {string} text
 * @returns {{ line: number, hex: string }[]}
 */
export function collectHexLiterals(filename, text) {
  if (isFileAllowed(text)) return [];
  if (typeof filename === 'string' && filename.endsWith('.css')) {
    return collectCssColorLiterals(text);
  }
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
      const regex = new RegExp(COLOR_SOURCE, 'gi');
      let match;
      while ((match = regex.exec(value)) !== null) {
        const preceding = value.slice(0, match.index);
        const matchLine = startLine + (preceding.match(/\n/g) ?? []).length;
        if (!lineAllowed(lines, matchLine)) {
          hits.push({ line: matchLine + 1, hex: normalizeColorToken(match[0]) });
        }
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
  console.error('Color literal (hex o rgb/rgba) nuevo en .ts/.tsx/.css. Usá un token, o un comentario de excepción:');
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
