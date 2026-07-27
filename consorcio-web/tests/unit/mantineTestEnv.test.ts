import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * `<MantineProvider env="test">` desactiva transiciones y portales.
 *
 * Sin eso, los tests que abren un Menu, un Modal o cualquier cosa con
 * transicion dependen del reloj: el dropdown queda con `display: none` hasta
 * que la animacion termina, y las queries por rol no ven elementos ocultos.
 * Local pasa siempre; en un runner mas lento falla de a ratos.
 *
 * Paso de verdad: `AdminLayout.test.tsx` fallo en CI con "Unable to find
 * role=menuitem" mientras la suite completa pasaba local (2762 tests), y el
 * mismo commit paso al re-correrlo sin tocar una linea. Un flaky dentro de un
 * check REQUERIDO es corrosivo: bloquea PRs al azar y te enseña a ignorar el
 * rojo — que es exactamente como la mutacion llego a ser teatro durante meses
 * en este repo.
 *
 * Este test existe para que el arreglo no se erosione: si alguien agrega un
 * `<MantineProvider>` pelado en un test nuevo, esto se pone rojo y explica por que.
 */
const TESTS_ROOT = join(import.meta.dirname, '..');

/** Este archivo se excluye: su propia documentacion nombra el patron que busca. */
const ESTE_ARCHIVO = 'mantineTestEnv.test.ts';

function archivosDeTest(): string[] {
  return readdirSync(TESTS_ROOT, { recursive: true, encoding: 'utf8' })
    .filter((rel) => /\.(test|spec)\.(ts|tsx)$/.test(rel) && !rel.endsWith(ESTE_ARCHIVO))
    .map((rel) => join(TESTS_ROOT, rel));
}

describe('MantineProvider en tests', () => {
  it('siempre se monta con env="test" para desactivar transiciones y portales', () => {
    const sinEnv = archivosDeTest()
      .filter((ruta) => /<MantineProvider(?!\s+env="test")/.test(readFileSync(ruta, 'utf8')))
      .map((ruta) => ruta.slice(TESTS_ROOT.length + 1));

    expect(sinEnv).toEqual([]);
  });

  it('encuentra archivos de test (si no, el guard de arriba seria vacuo)', () => {
    expect(archivosDeTest().length).toBeGreaterThan(100);
  });
});
