import { Box } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import type { Feature } from 'geojson';
import { memo, useCallback, useState } from 'react';
import { FICHA_IDLE_SELECTION_KEY } from '../../hooks/useFichaTerritorial';
import type { ConsorcioInfo } from '../../hooks/useCaminosColoreados';
import type { BpaEnrichedFile, BpaHistoryFile } from '../../types/pilarVerde';
import type { FichaResponse, FichaTipo } from '../../lib/api/ficha';
import type { FichaApiError } from '../../lib/api/ficha';
import { RasterLegend } from '../RasterLegend';
import { ExportPngModal } from './ExportPngModal';
import type { EtapaGate } from '../shared/canalesGrouping';
import type { CanalAnalysisMode } from './useFichaInteraction';
import { FichaTerritorialPanel, type FichaPanelTab } from './FichaTerritorialPanel';
import { InfoPanel } from './InfoPanel';
import {
  type CanalToggleEntry,
  LayerControlsPanel,
  type LayerFineControl,
} from './LayerControlsPanel';
import { LeyendaPanel } from './LeyendaPanel';
import { MapActionsPanel } from './MapActionsPanel';
import { type ViewMode, ViewModePanel } from './ViewModePanel';
import type { LayerHealth } from './layerHealth';
import type { LayerCategory } from './map2dDerived';
import type { ParcelaDisplayProps } from './useMapInteractionEffects';

interface LayerItem {
  id: string;
  label: string;
  category: LayerCategory;
}

interface DemOption {
  value: string;
  label: string;
}

interface LegendItem {
  color: string;
  label: string;
  type: string;
}

export interface MapUiPanelsProps {
  readonly baseLayer: 'osm' | 'satellite';
  readonly onBaseLayerChange: (value: 'osm' | 'satellite') => void;
  readonly viewMode: ViewMode;
  readonly onViewModeChange: (mode: ViewMode) => void;
  readonly hasSingleImage: boolean;
  readonly hasComparison: boolean;
  readonly singleImageInfo?: { sensor: string; date: string } | null;
  readonly comparisonInfo?: { leftDate: string; rightDate: string } | null;
  readonly layerItems: LayerItem[];
  readonly vectorVisibility: Record<string, boolean>;
  readonly onLayerVisibilityChange: (layerId: string, visible: boolean) => void;
  readonly showIGNOverlay: boolean;
  readonly onShowIGNOverlayChange: (visible: boolean) => void;
  readonly demEnabled: boolean;
  readonly showDemOverlay: boolean;
  readonly onShowDemOverlayChange: (visible: boolean) => void;
  readonly activeDemLayerId: string | null;
  readonly onActiveDemLayerIdChange: (value: string | null) => void;
  readonly demOptions: DemOption[];
  readonly canalesRelevadosItems?: readonly CanalToggleEntry[];
  readonly canalesPropuestosItems?: readonly CanalToggleEntry[];
  /** Etapas filter for the Canales badge (B4c/T3) — see `LayerControlsPanel`. */
  readonly etapaGate?: EtapaGate | null;
  /** Per-layer opacity + render-order controls (Fase 3 — Tanda B). */
  readonly layerFineControl?: LayerFineControl;
  /** Per-family load status + "Datos al …" lines (Batch 1 — "datos honestos"). */
  readonly layerHealth?: LayerHealth;
  readonly layerProvenance?: Partial<Record<LayerCategory, string>>;
  readonly hasApprovedZones: boolean;
  readonly onOpenExportPng: () => void;
  readonly onExportApprovedZonesPdf: () => void;
  /**
   * Optional — KMZ export handler produced by
   * `useMapExportHandlers.handleExportKmz`. When provided, the
   * `MapActionsPanel` renders the "Exportar KMZ" entry inside the
   * existing Export dropdown.
   */
  readonly onExportKmz?: () => void;
  /**
   * Fired when the Export dropdown opens. Threaded straight to
   * `MapActionsPanel` so the container can lazily start the KMZ-only catastro
   * GeoJSON fetch on export intent instead of on every mount.
   */
  readonly onExportMenuOpen?: () => void;
  readonly showLegend: boolean;
  readonly consorcios: ConsorcioInfo[];
  readonly activeLegendItems: LegendItem[];
  readonly visibleRasterLayers: Array<{ tipo: string }>;
  readonly hiddenClasses: Record<string, number[]>;
  readonly hiddenRanges: Record<string, number[]>;
  readonly onClassToggle: (layerType: string, classIndex: number, visible: boolean) => void;
  readonly onRangeToggle: (layerType: string, rangeIndex: number, visible: boolean) => void;
  /**
   * Phase 8 — array of all features returned by MapLibre at the click
   * point. InfoPanel renders one stacked section per feature in order
   * (top-most first).
   */
  readonly selectedFeatures: readonly Feature[];
  readonly onCloseInfoPanel: () => void;
  /**
   * Ficha territorial (A4) — the container owns the fetch (`useFichaTerritorial`)
   * and threads its state down here; `InfoPanel` stays pure. When
   * `fichaActive` is false the sibling panel renders nothing.
   */
  readonly fichaActive: boolean;
  readonly fichaTipo: FichaTipo;
  readonly fichaNroCuenta: string | null;
  /**
   * Identity of the analyzed target, computed by the container with
   * `fichaSelectionKey(request)` — the SAME derivation the query key uses.
   *
   * It is the reset trigger for the ficha's minimized state and for the bottom
   * sheet's stage, so it MUST come from the request and never from display
   * fields: `tipo|nroCuenta|canalNombre` collided for perfectly reachable
   * selections (two parcels without `nro_cuenta`, any two free-draw polygons,
   * two canals sharing a name), and a collision means the new analysis silently
   * stays minimized behind the previous selection's pill.
   *
   * Optional only so panel-level tests can mount without a container; omitted,
   * it degenerates to the constant idle key (no selection ever "changes").
   */
  readonly fichaSelectionKey?: string;
  readonly fichaParcelaProps?: ParcelaDisplayProps | null;
  /** Size of the multi-parcel selection (T4); drives the panel's count header. */
  readonly fichaParcelasCount?: number;
  /**
   * Drop specific parcels from the multi-parcel selection (T4 fix round). Wired
   * to the coordinator's `removeParcelas`; the ficha's error state uses it to
   * offer "Quitar faltantes" when the server 404s naming nomenclaturas that no
   * longer exist in the catastro — otherwise a single stale parcel forces the
   * user to rebuild the whole selection.
   */
  readonly onFichaRemoveParcelas?: (nomenclaturas: readonly string[]) => void;
  readonly fichaLoading: boolean;
  readonly fichaError: FichaApiError | Error | null;
  /** In-flight signal incl. retry-over-cached-data (threaded to the error alert). */
  readonly fichaFetching?: boolean;
  readonly fichaData: FichaResponse | undefined;
  readonly onCloseFicha: () => void;
  /** Re-runs the ficha query (`refetch`) from the panel's error state. */
  readonly onRetryFicha?: () => void;
  /**
   * On-map overlay toggle (A(b) slice 1) — the container owns the overlay query
   * + map paint; these thread its toggle state down to the ficha panel.
   */
  readonly fichaOverlayVisible?: boolean;
  readonly onToggleFichaOverlay?: (visible: boolean) => void;
  /**
   * Selected ficha dataset tab (T3b). ONE control now drives both the table the
   * panel shows and the dataset the overlay paints — the old separate
   * overlay-dataset picker is gone, so the two can no longer disagree.
   */
  readonly fichaTab?: FichaPanelTab;
  readonly onChangeFichaTab?: (tab: FichaPanelTab) => void;
  /** Classes of the selected dataset currently filtered OUT of the overlay. */
  readonly fichaHiddenClases?: readonly string[];
  readonly onToggleFichaClase?: (clase: string) => void;
  /**
   * Overlay fetch state (T3a, fix 4) — threaded from `useFichaOverlay` so the
   * ficha panel can show an inline spinner / failure line instead of leaving
   * "Ver recortado en el mapa" silent.
   */
  readonly fichaOverlayLoading?: boolean;
  readonly fichaOverlayError?: boolean;
  /**
   * Monotonic counter bumped by `useMapDragSignal` on every map `dragstart`
   * (T3a, fix 2). Each bump auto-minimizes any open panel to its pill so the
   * user pans a map instead of panning around a card. Restoring is always an
   * explicit tap on the pill — never automatic on dragend.
   */
  readonly mapDragSignal?: number;
  /**
   * Canal analysis control (A6 + A7). When the active ficha is a canal
   * (`canal_buffer` / `canal_cuenca`), these thread the canal name + analysis
   * mode + buffer distance down so `FichaTerritorialPanel` renders the control as
   * a header section INSIDE the card (replacing the old standalone floating
   * `CanalBufferControl`). Optional so non-canal fichas need no canal wiring.
   */
  readonly fichaCanalNombre?: string | null;
  readonly fichaCanalAnalysisMode?: CanalAnalysisMode;
  readonly onFichaCanalAnalysisModeChange?: (mode: CanalAnalysisMode) => void;
  readonly fichaCanalBufferM?: number;
  readonly fichaCanalMaxBufferM?: number;
  readonly onFichaCanalBufferChange?: (bufferM: number) => void;
  /**
   * Optional Pilar Verde enriched catastro data — when present, InfoPanel
   * will render `<BpaCard>` for any feature whose `nro_cuenta` matches a
   * parcel with a non-null `bpa_2025` record.
   */
  readonly bpaEnriched?: BpaEnrichedFile | null;
  /**
   * True while the lazy-loaded `bpa_enriched.json` is in flight (see
   * `usePilarVerde`). Forwarded to the ficha so its Pilar Verde row shows a
   * pending state instead of a premature "Sin vinculación".
   */
  readonly bpaLoading?: boolean;
  /** BPA group failure message (R4-001) — forwarded to the ficha badges. */
  readonly bpaError?: string | null;
  /** Optional Pilar Verde historical BPA lookup — powers the BpaCard histórico footer. */
  readonly bpaHistory?: BpaHistoryFile | null;
  readonly exportPngModalOpen: boolean;
  readonly onCloseExportPngModal: () => void;
  readonly exportTitle: string;
  readonly exportIncludeLegend: boolean;
  readonly exportIncludeMetadata: boolean;
  readonly onExportTitleChange: (value: string) => void;
  readonly onExportIncludeLegendChange: (value: boolean) => void;
  readonly onExportIncludeMetadataChange: (value: boolean) => void;
  readonly onExportPng: () => void;
  /**
   * When false, the layer selector and static legend are rendered by the parent
   * outside the map canvas. Overlay-only mode keeps quick actions, info panels
   * and modals inside the map.
   */
  readonly showEmbeddedMapControls?: boolean;
  /**
   * When false, the raster legend is NOT rendered inside the map canvas. The
   * parent is expected to render `<RasterLegend floating={false} />` somewhere
   * outside the map (typically in a bottom bar next to `LeyendaPanel`).
   * Defaults to `true` to preserve the floating bottom-right behavior.
   */
  readonly showEmbeddedRasterLegend?: boolean;
}

export const MapUiPanels = memo(function MapUiPanels({
  baseLayer,
  onBaseLayerChange,
  viewMode,
  onViewModeChange,
  hasSingleImage,
  hasComparison,
  singleImageInfo,
  comparisonInfo,
  layerItems,
  vectorVisibility,
  onLayerVisibilityChange,
  showIGNOverlay,
  onShowIGNOverlayChange,
  demEnabled,
  showDemOverlay,
  onShowDemOverlayChange,
  activeDemLayerId,
  onActiveDemLayerIdChange,
  demOptions,
  canalesRelevadosItems,
  canalesPropuestosItems,
  etapaGate = null,
  layerFineControl,
  layerHealth,
  layerProvenance,
  hasApprovedZones,
  onOpenExportPng,
  onExportApprovedZonesPdf,
  onExportKmz,
  onExportMenuOpen,
  showLegend,
  consorcios,
  activeLegendItems,
  visibleRasterLayers,
  hiddenClasses,
  hiddenRanges,
  onClassToggle,
  onRangeToggle,
  selectedFeatures,
  onCloseInfoPanel,
  fichaActive,
  fichaTipo,
  fichaNroCuenta,
  fichaSelectionKey = FICHA_IDLE_SELECTION_KEY,
  fichaParcelaProps,
  fichaParcelasCount,
  onFichaRemoveParcelas,
  fichaLoading,
  fichaError,
  fichaFetching,
  fichaData,
  onCloseFicha,
  onRetryFicha,
  fichaOverlayVisible,
  onToggleFichaOverlay,
  fichaTab,
  onChangeFichaTab,
  fichaHiddenClases,
  onToggleFichaClase,
  fichaOverlayLoading,
  fichaOverlayError,
  mapDragSignal = 0,
  fichaCanalNombre,
  fichaCanalAnalysisMode,
  onFichaCanalAnalysisModeChange,
  fichaCanalBufferM,
  fichaCanalMaxBufferM,
  onFichaCanalBufferChange,
  bpaEnriched,
  bpaLoading,
  bpaError,
  bpaHistory,
  exportPngModalOpen,
  onCloseExportPngModal,
  exportTitle,
  exportIncludeLegend,
  exportIncludeMetadata,
  onExportTitleChange,
  onExportIncludeLegendChange,
  onExportIncludeMetadataChange,
  onExportPng,
  showEmbeddedMapControls = true,
  showEmbeddedRasterLegend = true,
}: MapUiPanelsProps) {
  // A catastro click can open BOTH panels at once (ficha for the parcel +
  // InfoPanel for whatever canal / escuela / BPA / suelo feature sat under the
  // same click). Their solo max-heights overlap, so the InfoPanel would end up
  // buried under the ficha. The compact modifiers split the right-hand column
  // between them (InfoPanel top, ficha bottom) — see `map.module.css`.
  const bothPanelsOpen = selectedFeatures.length > 0 && fichaActive;

  // Narrow viewports (map-fluidity T2, fix 1). Same 62em breakpoint the CSS
  // module already uses, resolved synchronously on first render like
  // `MapWorkspace` does, so the panels never flash as floating cards on a phone.
  const isNarrow = useMediaQuery('(max-width: 62em)', false, {
    getInitialValueInEffect: false,
  });

  // BOTH-OPEN MODEL ON MOBILE — "the ficha wins, the InfoPanel queues".
  // Two stacked sheets would eat the whole canvas again, and merging both bodies
  // into one sheet would need a second header/scroll region inside a 45%-tall
  // box. So on a narrow viewport only ONE sheet renders: the ficha (the richer,
  // deliberately-requested analysis). The InfoPanel is NOT discarded — it is
  // driven by `selectedFeatures`, which the container keeps — so closing the
  // ficha immediately surfaces the InfoPanel sheet for the same click.
  const showInfoPanel = selectedFeatures.length > 0 && !(isNarrow && fichaActive);

  // The 45/55 desktop split is meaningless when only one sheet can be open.
  const compactPanels = bothPanelsOpen && !isNarrow;

  /* ── Minimize-to-pill state (T3a, fix 2) ────────────────────────────────── */
  // The state lives HERE, not inside `MapPanelShell`, because two different
  // actors drive it: the user (the minimize button / the pill) and the map (a
  // drag auto-minimizes). The panels stay presentational.
  const [infoMinimized, setInfoMinimized] = useState(false);
  const [fichaMinimized, setFichaMinimized] = useState(false);

  // A NEW selection always shows its content: minimizing is a statement about
  // the thing you were looking at, not a preference that should survive into the
  // next parcel you click. `selectedFeatures` is a fresh array per click and
  // `fichaSelectionKey` is the request's identity, so both are honest reset
  // signals. Re-selecting the SAME target keeps the key — and keeps the panel
  // minimized — which is the correct behavior: nothing new to show.
  // All three transitions below are state ADJUSTED DURING RENDER (React's
  // documented "resetting state when a prop changes" pattern) rather than in an
  // effect: the panel must never paint one frame minimized-from-the-last-click
  // before an effect corrects it, and the trigger values are compared by
  // identity, never read.
  const [lastInfoSelection, setLastInfoSelection] = useState<unknown>(selectedFeatures);
  if (lastInfoSelection !== selectedFeatures) {
    setLastInfoSelection(selectedFeatures);
    setInfoMinimized(false);
  }

  const [lastFichaSelection, setLastFichaSelection] = useState(fichaSelectionKey);
  if (lastFichaSelection !== fichaSelectionKey) {
    setLastFichaSelection(fichaSelectionKey);
    setFichaMinimized(false);
  }

  // Auto-minimize on map drag. The counter's INITIAL value is captured, so a
  // mount never minimizes a panel that was just opened — only a real bump does.
  const [lastDragSignal, setLastDragSignal] = useState(mapDragSignal);
  if (lastDragSignal !== mapDragSignal) {
    setLastDragSignal(mapDragSignal);
    setInfoMinimized(true);
    setFichaMinimized(true);
  }

  const toggleInfoMinimized = useCallback(() => {
    setInfoMinimized((value) => !value);
  }, []);
  const toggleFichaMinimized = useCallback(() => {
    setFichaMinimized((value) => !value);
  }, []);

  // A pill occupies almost nothing, so the moment either panel is minimized the
  // other one gets the whole column back — capping it at 45/55 would waste half
  // the height against a neighbour that is no longer there.
  const compactPanelsResolved = compactPanels && !infoMinimized && !fichaMinimized;

  return (
    <>
      {/*
        Side-by-side top-left stack (mirrors the 3D `TerrainLayerTogglesPanel`
        + `TerrainLegendsPanel` split):

          [LayerControlsPanel] [LeyendaPanel]

        Previously `LayerControlsPanel` lived at top-left and `LeyendaPanel`
        floated at bottom-left via the `.legendPanel` CSS class. When the
        layer list grew tall (many BPA toggles + DEM + attributions) the two
        panels visually collided. Bounding `LayerControlsPanel` with
        `maxHeight + overflow-y: auto` was not enough — the two panels still
        shared the same vertical column.

        The new layout owns positioning from this outer flex-row container
        (LeyendaPanel is rendered in `embedded` mode so its
        `.legendPanel` absolute-positioning class is NOT applied). Each
        panel keeps its own bounded `maxHeight` so neither overflows the
        viewport.

        RasterLegend (bottom-right) and InfoPanel (top-right) remain
        unchanged.
      */}
      {showEmbeddedMapControls && (
        <Box
          data-testid="map-2d-top-left-panels"
          style={{
            position: 'absolute',
            top: 12,
            left: 12,
            zIndex: 16,
            display: 'flex',
            flexDirection: 'row',
            alignItems: 'flex-start',
            gap: 8,
            maxHeight: 'calc(100vh - 180px)',
            overflowY: 'auto',
            overflowX: 'hidden',
          }}
        >
          <LayerControlsPanel
            baseLayer={baseLayer}
            onBaseLayerChange={onBaseLayerChange}
            viewModePanel={
              baseLayer === 'satellite' ? (
                <ViewModePanel
                  viewMode={viewMode}
                  onViewModeChange={onViewModeChange}
                  hasSingleImage={hasSingleImage}
                  hasComparison={hasComparison}
                  singleImageInfo={singleImageInfo}
                  comparisonInfo={comparisonInfo}
                />
              ) : null
            }
            layerItems={layerItems}
            vectorVisibility={vectorVisibility}
            onLayerVisibilityChange={onLayerVisibilityChange}
            showIGNOverlay={showIGNOverlay}
            onShowIGNOverlayChange={onShowIGNOverlayChange}
            demEnabled={demEnabled}
            showDemOverlay={showDemOverlay}
            onShowDemOverlayChange={onShowDemOverlayChange}
            activeDemLayerId={activeDemLayerId}
            onActiveDemLayerIdChange={onActiveDemLayerIdChange}
            demOptions={demOptions}
            canalesRelevadosItems={canalesRelevadosItems}
            canalesPropuestosItems={canalesPropuestosItems}
            etapaGate={etapaGate}
            layerFineControl={layerFineControl}
            layerHealth={layerHealth}
            layerProvenance={layerProvenance}
          />
          {showLegend && (
            <LeyendaPanel
              consorcios={consorcios}
              customItems={activeLegendItems}
              embedded
              width={260}
              data-testid="map-2d-leyenda-panel"
              style={{ maxHeight: 'calc(100vh - 180px)', overflowY: 'auto' }}
              pilarVerdeBpaHistoricoVisible={!!vectorVisibility.pilar_verde_bpa_historico}
              pilarVerdeAgroAceptadaVisible={!!vectorVisibility.pilar_verde_agro_aceptada}
              pilarVerdeAgroPresentadaVisible={!!vectorVisibility.pilar_verde_agro_presentada}
              pilarVerdeAgroZonasVisible={!!vectorVisibility.pilar_verde_agro_zonas}
              pilarVerdePorcentajeForestacionVisible={
                !!vectorVisibility.pilar_verde_porcentaje_forestacion
              }
              pilarAzulCanalesRelevadosVisible={!!vectorVisibility.canales_relevados}
              pilarAzulCanalesPropuestosVisible={!!vectorVisibility.canales_propuestos}
              pilarAzulEscuelasVisible={!!vectorVisibility.escuelas}
            />
          )}
        </Box>
      )}

      <MapActionsPanel
        hasApprovedZones={hasApprovedZones}
        onOpenExportPng={onOpenExportPng}
        onExportApprovedZonesPdf={onExportApprovedZonesPdf}
        onExportKmz={onExportKmz}
        onExportMenuOpen={onExportMenuOpen}
      />

      {showEmbeddedRasterLegend && visibleRasterLayers.length > 0 && (
        <RasterLegend
          layers={visibleRasterLayers}
          hiddenClasses={hiddenClasses}
          hiddenRanges={hiddenRanges}
          onClassToggle={onClassToggle}
          onRangeToggle={onRangeToggle}
        />
      )}

      {showInfoPanel && (
        <InfoPanel
          features={selectedFeatures}
          compact={compactPanelsResolved}
          sheet={isNarrow}
          onClose={onCloseInfoPanel}
          bpaEnriched={bpaEnriched}
          bpaHistory={bpaHistory}
          minimized={infoMinimized}
          onToggleMinimize={toggleInfoMinimized}
          resetKey={selectedFeatures}
        />
      )}

      <FichaTerritorialPanel
        active={fichaActive}
        compact={compactPanelsResolved}
        sheet={isNarrow}
        tipo={fichaTipo}
        nroCuenta={fichaNroCuenta}
        parcelaProps={fichaParcelaProps}
        parcelasCount={fichaParcelasCount}
        onRemoveParcelas={onFichaRemoveParcelas}
        bpaEnriched={bpaEnriched}
        bpaLoading={bpaLoading}
        bpaError={bpaError}
        isLoading={fichaLoading}
        isFetching={fichaFetching}
        isError={fichaError !== null}
        error={fichaError}
        data={fichaData}
        onClose={onCloseFicha}
        onRetry={onRetryFicha}
        overlayVisible={fichaOverlayVisible}
        onToggleOverlay={onToggleFichaOverlay}
        tab={fichaTab}
        onChangeTab={onChangeFichaTab}
        hiddenClases={fichaHiddenClases}
        onToggleClase={onToggleFichaClase}
        overlayLoading={fichaOverlayLoading}
        overlayError={fichaOverlayError}
        minimized={fichaMinimized}
        onToggleMinimize={toggleFichaMinimized}
        resetKey={fichaSelectionKey}
        canalNombre={fichaCanalNombre}
        canalAnalysisMode={fichaCanalAnalysisMode}
        onCanalAnalysisModeChange={onFichaCanalAnalysisModeChange}
        canalBufferM={fichaCanalBufferM}
        canalMaxBufferM={fichaCanalMaxBufferM}
        onCanalBufferChange={onFichaCanalBufferChange}
      />

      <ExportPngModal
        opened={exportPngModalOpen}
        onClose={onCloseExportPngModal}
        title={exportTitle}
        includeLegend={exportIncludeLegend}
        includeMetadata={exportIncludeMetadata}
        onTitleChange={onExportTitleChange}
        onIncludeLegendChange={onExportIncludeLegendChange}
        onIncludeMetadataChange={onExportIncludeMetadataChange}
        onExport={onExportPng}
      />
    </>
  );
});
