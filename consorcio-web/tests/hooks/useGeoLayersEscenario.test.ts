/**
 * Variantes de drenaje (natural / relevado / escenario) en las capas del DEM.
 *
 * El backend genera HAND, TWI, flow_acc y flow_dir en tres variantes que
 * comparten `tipo` y area, distinguidas SOLO por el prefijo del nombre. Sin
 * manejar eso, dos cosas se rompen en el visor:
 *  1. el dedup por (tipo, area) colapsa las tres en una -> se ve una sola;
 *  2. la etiqueta del dropdown sale igual -> no se sabe cual es natural, cual
 *     la actual y cual la simulacion.
 *
 * Estos tests fijan `enrichLayer`, donde vive toda la logica.
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
    variante: 'relevado',
    label: '',
  };
}

describe('enrichLayer — variantes', () => {
  it('relevado (sin prefijo) es el default, sin sufijo', () => {
    const r = enrichLayer(capa('flow_acc_zona_principal', 'flow_acc'));
    expect(r.variante).toBe('relevado');
    expect(r.label).toBe('Acumulacion de Flujo');
  });

  it('natural lleva prefijo natural_ y sufijo (natural)', () => {
    const r = enrichLayer(capa('natural_hand_zona_principal', 'hand'));
    expect(r.variante).toBe('natural');
    expect(r.label).toBe('Altura sobre Drenaje (HAND) (natural)');
  });

  it('escenario lleva prefijo escenario_ y sufijo (escenario)', () => {
    const r = enrichLayer(capa('escenario_twi_zona_principal', 'twi'));
    expect(r.variante).toBe('escenario');
    expect(r.label).toBe('Indice Humedad (TWI) (escenario)');
  });

  it('las tres variantes del mismo tipo tienen labels distintos', () => {
    const nat = enrichLayer(capa('natural_flow_acc_zona_principal', 'flow_acc'));
    const rel = enrichLayer(capa('flow_acc_zona_principal', 'flow_acc'));
    const esc = enrichLayer(capa('escenario_flow_acc_zona_principal', 'flow_acc'));
    // Mismo tipo...
    expect(new Set([nat.tipo, rel.tipo, esc.tipo]).size).toBe(1);
    // ...pero tres labels distintos: es lo unico que las separa en el dropdown.
    expect(new Set([nat.label, rel.label, esc.label]).size).toBe(3);
  });

  it('el prefijo tiene que estar al PRINCIPIO, no en el medio', () => {
    // "flow_acc_escenario_x" NO es escenario: el backend nunca nombra asi, y
    // el guard debe ser estricto (startsWith, no includes).
    expect(enrichLayer(capa('flow_acc_escenario_zona', 'flow_acc')).variante).toBe('relevado');
    expect(enrichLayer(capa('twi_natural_zona', 'twi')).variante).toBe('relevado');
  });

  it('un tipo sin etiqueta conocida cae al tipo crudo, respetando la variante', () => {
    expect(enrichLayer(capa('raro_zona', 'raro')).label).toBe('raro');
    expect(enrichLayer(capa('natural_raro_zona', 'raro')).label).toBe('raro (natural)');
  });
});
