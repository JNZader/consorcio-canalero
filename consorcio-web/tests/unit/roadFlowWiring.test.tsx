/**
 * roadFlowWiring.test.tsx — the ENTRY POINT of the cruces capability
 * (flujo-caminos, S4 wiring).
 *
 * Slice 4 shipped five components and none of them were reachable: nothing
 * mounted the ranked list, nothing mounted the survey sheet, nothing called the
 * layer sync. This file pins the decision that closed it:
 *
 *   · ticking the `road_flow` layer OPENS the panel; unticking it CLOSES it —
 *     one control, so the panel can never disagree with what the map paints;
 *   · a list row RECENTRES the map on that crossing;
 *   · a crossing on the MAP (the only feature in this app carrying a
 *     `tramo_ref`) opens the survey sheet for its segment, and so does the
 *     row's explicit "Relevar" button;
 *   · the layer is OFFERED only to staff, because both routes behind it are
 *     `require_admin_or_operator`.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { MapUiPanels, type MapUiPanelsProps } from '../../src/components/map2d/MapUiPanels';
import { MAP_VIEW_MODE } from '../../src/components/map2d/ViewModePanel';
import { buildVectorLayerItems } from '../../src/components/map2d/map2dDerived';
import { readTramoRef } from '../../src/components/map2d/useRoadFlowInteraction';
import {
  ROAD_FLOW_KIND_FILTER,
  kindFilterToVisibility,
  visibilityToKindFilter,
} from '../../src/components/map2d/RoadFlowPanel';
import { ROAD_FLOW_ALL_KINDS_VISIBLE } from '../../src/components/map2d/roadFlowLayers';
import type { UseRoadFlowCrossingsResult } from '../../src/hooks/useRoadFlowCrossings';
import type { CoberturaResponse, TramoRelevamientoDetalle } from '../../src/lib/api/relevamiento';
import type { RoadFlowCrossingsResponse } from '../../src/lib/api/roadFlow';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

/** Desktop viewport: floating cards, not sheets. */
function mockViewport(narrow: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('max-width') ? narrow : !narrow,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

const CROSSINGS: RoadFlowCrossingsResponse = {
  area_id: 'zona_principal',
  calculada_en: '2026-08-22T14:03:00Z',
  desactualizado: false,
  // M is the run's own counter, never the row count (Law 7).
  total_flujo_natural: 2,
  total_canal: 1,
  features: {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [-62.68, -32.62] },
        properties: {
          id: 'c1',
          tipo: 'flujo_natural',
          tramo_ref: 'RV-0001',
          canal_ref: null,
          direccion_flujo_deg: 90,
          rumbo_camino_deg: 0,
          lado_cruce: 'norte',
          area_aporte_ha: 12.5,
          orden_ranking: 1,
          confianza: 'alta',
          nota: null,
        },
      },
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [-62.7, -32.6] },
        properties: {
          id: 'c2',
          tipo: 'canal',
          tramo_ref: 'RV-0002',
          canal_ref: 'CN-9',
          direccion_flujo_deg: 45,
          rumbo_camino_deg: 10,
          lado_cruce: null,
          area_aporte_ha: null,
          orden_ranking: null,
          confianza: 'alta',
          nota: null,
        },
      },
    ],
  },
  excluidos: [],
  parametros: {},
  variante: null,
  segmentos_parcialmente_cubiertos: 0,
};

const CROSSINGS_RESULT: UseRoadFlowCrossingsResult = {
  data: CROSSINGS,
  isLoading: false,
  isError: false,
  error: null,
  sinCobertura: false,
};

const COBERTURA: CoberturaResponse = {
  area_id: 'zona_principal',
  relevados: 3,
  solo_candidato: 4,
  sin_datos: 5,
  total_activos: 12,
};

const DETALLE: TramoRelevamientoDetalle = {
  tramo_ref: 'RV-0001',
  vigente: null,
  historial: [],
  candidata: null,
};

function panelProps(overrides: Partial<MapUiPanelsProps> = {}): MapUiPanelsProps {
  return {
    baseLayer: 'osm',
    onBaseLayerChange: () => {},
    viewMode: MAP_VIEW_MODE.BASE,
    onViewModeChange: () => {},
    hasSingleImage: false,
    hasComparison: false,
    singleImageInfo: null,
    comparisonInfo: null,
    layerItems: [],
    vectorVisibility: {},
    onLayerVisibilityChange: () => {},
    showIGNOverlay: false,
    onShowIGNOverlayChange: () => {},
    demEnabled: false,
    showDemOverlay: false,
    onShowDemOverlayChange: () => {},
    activeDemLayerId: null,
    onActiveDemLayerIdChange: () => {},
    demOptions: [],
    hasApprovedZones: false,
    onOpenExportPng: () => {},
    onExportApprovedZonesPdf: () => {},
    showLegend: false,
    consorcios: [],
    activeLegendItems: [],
    visibleRasterLayers: [],
    hiddenClasses: {},
    hiddenRanges: {},
    onClassToggle: () => {},
    onRangeToggle: () => {},
    selectedFeatures: [],
    onCloseInfoPanel: () => {},
    fichaActive: false,
    fichaTipo: 'parcela',
    fichaNroCuenta: null,
    fichaLoading: false,
    fichaError: null,
    fichaData: undefined,
    onCloseFicha: () => {},
    exportPngModalOpen: false,
    onCloseExportPngModal: () => {},
    exportTitle: 'Mapa',
    exportIncludeLegend: true,
    exportIncludeMetadata: true,
    onExportTitleChange: () => {},
    onExportIncludeLegendChange: () => {},
    onExportIncludeMetadataChange: () => {},
    onExportPng: () => {},
    ...overrides,
  };
}

function roadFlowProps(overrides: Partial<MapUiPanelsProps> = {}): MapUiPanelsProps {
  return panelProps({
    roadFlowActive: true,
    roadFlowCrossings: CROSSINGS_RESULT,
    roadFlowCobertura: COBERTURA,
    roadFlowKinds: ROAD_FLOW_ALL_KINDS_VISIBLE,
    onRoadFlowKindsChange: () => {},
    onSelectRoadFlowCrossing: () => {},
    onSurveyTramo: () => {},
    onCloseRoadFlow: () => {},
    ...overrides,
  });
}

describe('cruces de camino · el toggle de la capa es el ciclo de vida', () => {
  it('la capa activa monta el panel con la lista y los tres contadores', () => {
    mockViewport(false);
    renderWithMantine(<MapUiPanels {...roadFlowProps()} />);

    expect(screen.getByTestId('road-flow-panel')).toBeInTheDocument();
    expect(screen.getByTestId('road-flow-ranked-list')).toBeInTheDocument();
    // The disclaimer travels with the list — never behind a fold (RFA-R4).
    expect(screen.getByTestId('road-flow-disclaimer-lista')).toBeInTheDocument();
    expect(screen.getByTestId('relevamiento-cobertura')).toBeInTheDocument();
  });

  it('apagar la capa desmonta el panel entero', () => {
    mockViewport(false);
    const { rerender } = renderWithMantine(<MapUiPanels {...roadFlowProps()} />);
    expect(screen.getByTestId('road-flow-panel')).toBeInTheDocument();

    rerender(
      <MantineProvider env="test">
        <MapUiPanels {...roadFlowProps({ roadFlowActive: false })} />
      </MantineProvider>
    );

    expect(screen.queryByTestId('road-flow-panel')).toBeNull();
    expect(screen.queryByTestId('road-flow-ranked-list')).toBeNull();
  });

  it('cerrar la hoja apaga la capa (una sola acción)', () => {
    // Sheet shape: `MapPanelShell` owns the close control there, so this
    // exercises the real button rather than the prop.
    mockViewport(true);
    const onCloseRoadFlow = vi.fn();
    renderWithMantine(<MapUiPanels {...roadFlowProps({ onCloseRoadFlow })} />);

    fireEvent.click(screen.getByTestId('road-flow-panel-sheet-close'));

    expect(onCloseRoadFlow).toHaveBeenCalledTimes(1);
  });

  it('en pantalla angosta la hoja de relevamiento reemplaza al panel, y volver la restituye', () => {
    mockViewport(true);
    const { rerender } = renderWithMantine(
      <MapUiPanels
        {...roadFlowProps({
          tramoSurveyDetalle: DETALLE,
          onSubmitTramoSurvey: async () => undefined,
          onCloseTramoSurvey: () => {},
        })}
      />
    );

    // Two sheets anchored to the same bottom edge would eat the canvas; the
    // form the operator just asked for wins.
    expect(screen.getByTestId('tramo-survey-sheet')).toBeInTheDocument();
    expect(screen.queryByTestId('road-flow-panel')).toBeNull();

    rerender(
      <MantineProvider env="test">
        <MapUiPanels {...roadFlowProps({ tramoSurveyDetalle: null })} />
      </MantineProvider>
    );

    // Closing the sheet changed nothing about the layer, so the list is back.
    expect(screen.queryByTestId('tramo-survey-sheet')).toBeNull();
    expect(screen.getByTestId('road-flow-panel')).toBeInTheDocument();
  });
});

describe('cruces de camino · selección', () => {
  it('tocar una fila pide centrar el mapa en ESE cruce', () => {
    mockViewport(false);
    const onSelectRoadFlowCrossing = vi.fn();
    renderWithMantine(<MapUiPanels {...roadFlowProps({ onSelectRoadFlowCrossing })} />);

    fireEvent.click(screen.getByTestId('road-flow-rank-c1'));

    expect(onSelectRoadFlowCrossing).toHaveBeenCalledTimes(1);
    expect(onSelectRoadFlowCrossing.mock.calls[0][0].properties.id).toBe('c1');
  });

  it('el botón "Relevar" abre el relevamiento del tramo, no el centrado', () => {
    mockViewport(false);
    const onSurveyTramo = vi.fn();
    const onSelectRoadFlowCrossing = vi.fn();
    renderWithMantine(
      <MapUiPanels {...roadFlowProps({ onSurveyTramo, onSelectRoadFlowCrossing })} />
    );

    fireEvent.click(screen.getByTestId('road-flow-relevar-RV-0001'));

    expect(onSurveyTramo).toHaveBeenCalledWith('RV-0001');
    // Two different acts: recentring must NOT also fire.
    expect(onSelectRoadFlowCrossing).not.toHaveBeenCalled();
  });

  it('un tramo seleccionado monta la hoja de relevamiento', () => {
    mockViewport(false);
    renderWithMantine(
      <MapUiPanels
        {...roadFlowProps({
          tramoSurveyDetalle: DETALLE,
          onSubmitTramoSurvey: async () => undefined,
          onCloseTramoSurvey: () => {},
        })}
      />
    );

    expect(screen.getByTestId('tramo-survey-sheet')).toBeInTheDocument();
    expect(screen.getByTestId('tramo-survey-nivel')).toBeInTheDocument();
    expect(screen.getByTestId('tramo-survey-save')).toBeInTheDocument();
  });

  it('sin tramo seleccionado no hay hoja', () => {
    mockViewport(false);
    renderWithMantine(<MapUiPanels {...roadFlowProps()} />);
    expect(screen.queryByTestId('tramo-survey-sheet')).toBeNull();
  });
});

describe('cruces de camino · identidad del tramo desde el mapa', () => {
  it('lee el tramo_ref de la feature clickeada', () => {
    expect(readTramoRef({ properties: { tramo_ref: 'RV-0007' } })).toBe('RV-0007');
  });

  it('una feature sin tramo_ref no selecciona nada', () => {
    expect(readTramoRef({ properties: {} })).toBeNull();
    expect(readTramoRef(null)).toBeNull();
    expect(readTramoRef({ properties: { tramo_ref: '' } })).toBeNull();
  });
});

describe('cruces de camino · filtro de tipo', () => {
  it('cada posición del filtro deja el otro tipo montado o lo oculta, nunca lo borra', () => {
    expect(kindFilterToVisibility(ROAD_FLOW_KIND_FILTER.AMBOS)).toEqual({
      flujo_natural: true,
      canal: true,
    });
    expect(kindFilterToVisibility(ROAD_FLOW_KIND_FILTER.FLUJO)).toEqual({
      flujo_natural: true,
      canal: false,
    });
    expect(kindFilterToVisibility(ROAD_FLOW_KIND_FILTER.CANAL)).toEqual({
      flujo_natural: false,
      canal: true,
    });
  });

  it('la posición del control se deriva del estado, sin una segunda copia', () => {
    expect(visibilityToKindFilter({ flujo_natural: true, canal: true })).toBe(
      ROAD_FLOW_KIND_FILTER.AMBOS
    );
    expect(visibilityToKindFilter({ flujo_natural: true, canal: false })).toBe(
      ROAD_FLOW_KIND_FILTER.FLUJO
    );
    expect(visibilityToKindFilter({ flujo_natural: false, canal: true })).toBe(
      ROAD_FLOW_KIND_FILTER.CANAL
    );
  });

  it('ocultar un tipo NO desmonta la lista del otro', () => {
    mockViewport(false);
    renderWithMantine(
      <MapUiPanels {...roadFlowProps({ roadFlowKinds: { flujo_natural: true, canal: false } })} />
    );

    // The kind filter is a map `setFilter`; the panel keeps rendering both sets,
    // which is what stops the reader from losing one kind entirely (RFA-R3).
    expect(screen.getByTestId('road-flow-ranked-section')).toBeInTheDocument();
    expect(screen.getByTestId('road-flow-canal-section')).toBeInTheDocument();
  });
});

describe('cruces de camino · la entrada es operator-only', () => {
  const base = {
    basins: null,
    approvedZonesCollection: null,
    roadsCollection: null,
    intersectionsLength: 0,
  };

  it('sin sesión de staff la capa no se ofrece', () => {
    const ids = buildVectorLayerItems(base).map((item) => item.id);
    expect(ids).not.toContain('road_flow');
  });

  it('con sesión de staff aparece una sola vez, en Análisis', () => {
    const items = buildVectorLayerItems({ ...base, showRoadFlow: true });
    const entries = items.filter((item) => item.id === 'road_flow');
    expect(entries).toHaveLength(1);
    expect(entries[0].label).toBe('Cruces de camino');
    expect(entries[0].category).toBe('analisis');
  });
});
