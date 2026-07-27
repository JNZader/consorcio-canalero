/**
 * Distincion escenario vs operativo en las capas del pipeline DEM.
 *
 * El backend nombra las capas de escenario con prefijo `escenario_`, pero les
 * pone el MISMO tipo que la operativa (ambas FLOW_ACC). Sin manejar eso, dos
 * cosas se rompen en el visor:
 *  1. el dedup por (tipo, area) colapsa las dos en una -> solo se ve una;
 *  2. la etiqueta del dropdown sale igual para ambas -> el usuario no sabe
 *     cual es simulacion y cual el drenaje real.
 *
 * Estos tests fijan la logica pura de `enrichLayer` (el dedup se prueba a
 * traves de el, con datos representativos).
 */

import { describe, expect, it } from 'vitest';
import { type GeoLayerInfo, enrichLayer } from '../../src/hooks/useGeoLayers';

function capa(nombre: string, tipo: string): GeoLayerInfo {
  return {
    id: `id-${nombre}`,
    nombre,
    tipo,
    fuente: 'dem_pipeline',
    formato: 'geotiff',
    area_id: 'zona_principal',
    created_at: '2026-07-27T18:43:00Z',
    // enrichLayer los completa; se ponen para satisfacer el tipo.
    esEscenario: false,
    label: '',
  };
}

describe('enrichLayer', () => {
  it('marca la capa operativa como NO escenario y le pone la etiqueta base', () => {
    const r = enrichLayer(capa('flow_acc_zona_principal', 'flow_acc'));
    expect(r.esEscenario).toBe(false);
    expect(r.label).toBe('Acumulacion de Flujo');
  });

  it('marca la capa de escenario y le agrega el sufijo (escenario)', () => {
    const r = enrichLayer(capa('escenario_flow_acc_zona_principal', 'flow_acc'));
    expect(r.esEscenario).toBe(true);
    expect(r.label).toBe('Acumulacion de Flujo (escenario)');
  });

  it('la distincion sale del NOMBRE, no del tipo: ambas comparten tipo', () => {
    const operativa = enrichLayer(capa('flow_acc_zona_principal', 'flow_acc'));
    const escenario = enrichLayer(capa('escenario_flow_acc_zona_principal', 'flow_acc'));
    // Mismo tipo...
    expect(operativa.tipo).toBe(escenario.tipo);
    // ...pero label distinto: es lo unico que las separa en el dropdown.
    expect(operativa.label).not.toBe(escenario.label);
  });

  it('un tipo sin etiqueta conocida cae al tipo crudo, con y sin escenario', () => {
    expect(enrichLayer(capa('raro_zona_principal', 'raro')).label).toBe('raro');
    expect(enrichLayer(capa('escenario_raro_zona_principal', 'raro')).label).toBe(
      'raro (escenario)'
    );
  });

  it('no confunde un nombre que solo CONTIENE la palabra escenario', () => {
    // El prefijo tiene que estar al principio; "flow_acc_escenario_x" NO es
    // una capa de escenario (el backend nunca la nombra asi, pero el guard
    // debe ser estricto).
    const r = enrichLayer(capa('flow_acc_escenario_zona', 'flow_acc'));
    expect(r.esEscenario).toBe(false);
  });
});
