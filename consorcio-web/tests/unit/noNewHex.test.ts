import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';

import { collectHexLiterals, diffHexCounts } from '../../scripts/lint-no-new-hex.mjs';

describe('lint de hex nuevos', () => {
  it('ignora comentarios y honra hex-color-allow', () => {
    const hits = collectHexLiterals(
      'x.ts',
      `
      const kept = '#ff0000';
      // #00ff00 queda en un comentario
      const allowed = '#00ff00'; // hex-color-allow
      /* bloque #112233 */
      const second = "#0000ff";
      const template = \`#abc\`;
    `
    );
    expect(hits.map((hit) => hit.hex)).toEqual(['#ff0000', '#0000ff', '#abc']);
  });

  it('acepta el comentario en la línea anterior y el allow de archivo', () => {
    const previous = collectHexLiterals(
      'x.ts',
      '// hex-color-allow: leyenda\nconst a = "#aabbcc";'
    );
    expect(previous).toEqual([]);
    const file = collectHexLiterals('x.ts', '/* hex-color-allow-file */\nconst a = "#ff0000";');
    expect(file).toEqual([]);
  });

  it('encuentra un hex dentro de un template con expresión', () => {
    const sample = 'const a = `color: $' + '{"#123456"}`;';
    const hits = collectHexLiterals('x.ts', sample);
    expect(hits.map((hit) => hit.hex)).toEqual(['#123456']);
  });

  it('solo marca conteos por encima de la línea de base', () => {
    expect(diffHexCounts({ 'a.ts': { '#fff': 2, '#000': 1 } }, { 'a.ts': { '#fff': 1 } })).toEqual([
      { file: 'a.ts', hex: '#fff', count: 2, allowed: 1 },
      { file: 'a.ts', hex: '#000', count: 1, allowed: 0 },
    ]);
    expect(diffHexCounts({ 'a.ts': { '#fff': 1 } }, { 'a.ts': { '#fff': 1, '#000': 4 } })).toEqual(
      []
    );
  });

  it('el árbol actual no agrega hex', () => {
    expect(() =>
      execFileSync('node', ['scripts/lint-no-new-hex.mjs'], { encoding: 'utf8' })
    ).not.toThrow();
  });

  it('escanea archivos .css ignorando selectores, comentarios y url(#id)', () => {
    const hits = collectHexLiterals(
      'styles.css',
      `
      #cafe {
        color: #fff;
        background: /* #123456 */ #112233;
        clip-path: url(#mi-gradiente);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
        border-color: rgb(255 0 0 / 50%);
      }
      @media (max-width: 48em) {
        .box {
          color: #aabbcc; /* hex-color-allow */
          /* hex-color-allow */
          background: rgba(1, 2, 3, 0.4);
        }
      }
      `
    );
    expect(hits.map((hit) => hit.hex)).toEqual([
      '#fff',
      '#112233',
      'rgba(0, 0, 0, 0.5)',
      'rgb(255 0 0 / 50%)',
    ]);
  });

  it('respeta hex-color-allow-file en .css y detecta rgb/rgba en .ts sin falsos positivos de texto libre', () => {
    expect(collectHexLiterals('tokens.css', '/* hex-color-allow-file */\n.a { color: #ff0000; }')).toEqual([]);

    const tsHits = collectHexLiterals(
      'x.ts',
      `
      const label = 'No uses rgba() hardcodeado';
      const shadow = '0 1px 2px rgba(0,0,0,0.2)';
      const ok = '0 1px 2px rgba(0, 0, 0, 0.3)'; // hex-color-allow
      `
    );
    expect(tsHits.map((hit) => hit.hex)).toEqual(['rgba(0, 0, 0, 0.2)']);
  });
});
