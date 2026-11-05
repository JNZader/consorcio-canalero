import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const DIR = join(dirname(fileURLToPath(import.meta.url)), '../../src/styles/components/map');

/** CSS del mapa en el orden de `map.css`, que es el de la cascada. */
export function readMapCss(): string {
  const barrel = readFileSync(join(DIR, 'map.css'), 'utf8');
  const files = [...barrel.matchAll(/@import '\.\/([^']+)';/g)].map((match) => match[1]);
  if (files.length === 0) throw new Error('map.css no importa hojas');
  return files.map((file) => readFileSync(join(DIR, file), 'utf8')).join('');
}

/**
 * Une cada `@media (pointer: coarse)` sin más condiciones. El piso táctil
 * está partido en varias hojas; un `indexOf` del primero se quedaría corto.
 */
export function coarsePointerBlocks(css: string): string {
  const marker = '@media (pointer: coarse) {';
  const parts: string[] = [];
  let from = 0;
  for (;;) {
    const start = css.indexOf(marker, from);
    if (start === -1) break;
    let depth = 0;
    for (let i = css.indexOf('{', start); i < css.length; i += 1) {
      if (css[i] === '{') depth += 1;
      if (css[i] === '}') {
        depth -= 1;
        if (depth === 0) {
          parts.push(css.slice(start, i + 1));
          from = i + 1;
          break;
        }
      }
    }
  }
  if (parts.length === 0) throw new Error('sin bloque @media (pointer: coarse)');
  return parts.join('\n');
}
