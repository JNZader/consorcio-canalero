/**
 * Contrato entre las capas que el frontend pide y las que Martin publica.
 *
 * Martin corre con `auto_publish: false` y una lista EXPLICITA de vistas
 * saneadas (`martin/config.yaml`). Esa decision no es cosmetica: el hostname
 * de Martin es publico y cada columna de la tabla se convierte en propiedad
 * del vector tile, asi que publicar una tabla cruda expone todo lo que tenga.
 *
 * Paso de verdad (2026-07-27): el frontend pedia `puntos_conflicto` -la tabla-
 * mientras Martin solo publicaba `vt_puntos_conflicto` -la vista-. La capa
 * devolvia 404 en produccion. No lo noto nadie porque viene apagada por
 * defecto y la vista esta vacia; con datos cargados habria sido una capa que
 * simplemente no aparece, sin ningun error visible.
 *
 * El desfasaje es facil de reintroducir: el nombre de la fuente vive en un
 * .ts y la lista de publicacion en un .yaml, y nada los ata. Esto los ata.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { MARTIN_SOURCES } from '../../src/hooks/useMartinLayers';

const REPO_ROOT = join(import.meta.dirname, '..', '..', '..');
const MARTIN_CONFIG = join(REPO_ROOT, 'martin', 'config.yaml');

/** Nombres de fuente bajo la clave `tables:` del config de Martin. */
function fuentesPublicadas(): string[] {
  const yaml = readFileSync(MARTIN_CONFIG, 'utf8');
  const bloque = yaml.split(/^\s*tables:\s*$/m)[1] ?? '';
  return [...bloque.matchAll(/^ {4}([a-z_][a-z_0-9]*):\s*$/gm)].map((m) => m[1]);
}

describe('fuentes de Martin', () => {
  it('publica al menos una fuente (si no, el contrato de abajo seria vacuo)', () => {
    expect(fuentesPublicadas().length).toBeGreaterThan(0);
  });

  it('cada capa que el frontend pide esta efectivamente publicada', () => {
    const publicadas = fuentesPublicadas();
    const pedidas = Object.values(MARTIN_SOURCES).map((s) => s.table);

    expect(pedidas.length).toBeGreaterThan(0);
    const faltantes = pedidas.filter((t) => !publicadas.includes(t));
    expect(faltantes).toEqual([]);
  });

  it('el frontend NO pide tablas crudas: solo proyecciones vt_*', () => {
    // Una tabla cruda publicada seria un agujero de datos, no solo un 404.
    // Fijarlo del lado del frontend hace que el error se vea en el PR y no
    // en produccion.
    for (const fuente of Object.values(MARTIN_SOURCES)) {
      expect(fuente.table.startsWith('vt_')).toBe(true);
    }
  });
});
