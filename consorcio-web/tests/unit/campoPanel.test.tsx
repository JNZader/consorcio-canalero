/**
 * Campo (PR 6, S6) — the bottom panel: neutral class copy (NO producer
 * phrases, PR 5 S11), boundary warning, tap line, offline chip, chips and
 * the Centrar button wiring.
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { PanelPosicion } from '@/components/campo/PanelPosicion';
import type { AnalisisPosicion } from '@/components/campo/geometriaCampo';
import type { PaqueteCampo } from '@/components/campo/tiposCampo';

const paquete: PaqueteCampo = {
  version: 1,
  nombre: 'Informe test',
  generado_el: '2026-11-19T12:00:00Z',
  area_ha: 100,
  limites: { seleccion: { type: 'Polygon', coordinates: [] }, subcuencas: [] },
  temas: {
    riesgo: { titulo: 'Riesgo hídrico', clases: [] },
    drenaje: { titulo: 'Necesidad de drenaje', clases: [] },
  },
  basemap: null,
  notas: [],
};

const analisis: AnalisisPosicion = {
  clase: { clase: 'Alto', color: '#fc8d59', geometrias: [] },
  enLimite: false,
  vecino: null,
  distanciaBordeM: 400,
};

function panel(overrides: Partial<Parameters<typeof PanelPosicion>[0]> = {}) {
  const props = {
    analisis,
    temaActivo: 'riesgo',
    paquete,
    sinSenal: false,
    gpsError: null,
    claseTocada: null,
    precisionM: 12,
    onCentrar: vi.fn(),
    onTema: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<PanelPosicion {...props} />) };
}

describe('PanelPosicion', () => {
  it('muestra la clase con copy neutral (S11 de PR 5: sin frases productivas)', () => {
    panel();
    expect(screen.getByTestId('campo-clase').textContent).toBe('Tu posición: clase Alto');
    // The gated phrase shape must NOT appear.
    expect(screen.getByTestId('campo-clase').textContent).not.toMatch(/sector|priorizá|revisá/i);
  });

  it('fuera del área: copy honesto', () => {
    panel({ analisis: { clase: null, enLimite: false, vecino: null, distanciaBordeM: Number.POSITIVE_INFINITY } });
    expect(screen.getByTestId('campo-clase').textContent).toBe('Fuera del área del informe');
  });

  it('aviso de límite con la clase vecina nombrada (S6)', () => {
    panel({
      analisis: {
        ...analisis,
        enLimite: true,
        vecino: { clase: 'Medio', color: '#fee08b', geometrias: [] },
      },
    });
    expect(screen.getByTestId('campo-limite').textContent).toBe(
      'Estás en el límite entre Alto y Medio'
    );
  });

  it('aviso de límite en el borde del área, sin vecino conocido', () => {
    panel({ analisis: { ...analisis, enLimite: true, vecino: null } });
    expect(screen.getByTestId('campo-limite').textContent).toContain('límite de la clase Alto');
  });

  it('error de GPS reemplaza la línea de clase (permiso denegado)', () => {
    panel({ gpsError: 'Permiso de ubicación denegado: activá la ubicación para ver tu clase.' });
    expect(screen.getByTestId('campo-gps-error')).toBeTruthy();
    expect(screen.queryByTestId('campo-clase')).toBeNull();
  });

  it('chip Sin señal cuando la carga vino de la cache (S6)', () => {
    panel({ sinSenal: true });
    expect(screen.getByTestId('campo-offline').textContent).toBe('Sin señal · funciona igual');
  });

  it('tap: línea En el punto tocado con la clase', () => {
    panel({ claseTocada: 'Medio' });
    expect(screen.getByTestId('campo-tap').textContent).toBe('En el punto tocado: clase Medio');
  });

  it('chips por tema + botón Centrar wired a los callbacks', () => {
    const { props } = panel();
    fireEvent.click(screen.getByTestId('campo-tema-drenaje'));
    expect(props.onTema).toHaveBeenCalledWith('drenaje');
    fireEvent.click(screen.getByTestId('campo-centrar'));
    expect(props.onCentrar).toHaveBeenCalled();
    expect(screen.getByTestId('campo-tema-riesgo').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('campo-tema-drenaje').getAttribute('aria-pressed')).toBe('false');
  });

  it('precisión visible redondeada', () => {
    panel({ precisionM: 12.4 });
    expect(screen.getByText('Precisión GPS ±12 m')).toBeTruthy();
  });

  it('sin fix GPS inicial muestra buscando ubicación y deshabilita Centrar en mí', () => {
    panel({
      precisionM: null,
      analisis: { clase: null, enLimite: false, vecino: null, distanciaBordeM: Number.POSITIVE_INFINITY },
    });
    expect(screen.getByTestId('campo-clase').textContent).toBe('Buscando ubicación GPS…');
    expect((screen.getByTestId('campo-centrar') as HTMLButtonElement).disabled).toBe(true);
  });

  it('renderiza paquete.notas y avisoCache cuando están presentes', () => {
    panel({
      avisoCache: 'No hay espacio suficiente para guardar el mapa sin señal.',
      paquete: {
        ...paquete,
        notas: ['Curado campaña 2025', 'Incluye caminos secundarios'],
      },
    });
    expect(screen.getByTestId('campo-aviso-cache').textContent).toContain('espacio suficiente');
    const notas = screen.getByTestId('campo-notas');
    expect(notas.textContent).toContain('Curado campaña 2025');
    expect(notas.textContent).toContain('Incluye caminos secundarios');
  });
});
