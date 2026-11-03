/**
 * Herramientas — one menu for measure, analysis and export.
 *
 * Idle: a single "Herramientas" trigger in the right-hand control column.
 * Measuring: that trigger leaves the column and a small Deshacer / Guardar /
 * Cancelar bar is portaled onto the canvas.
 *
 * Analysis toggles (dibujar, canal, punto, selección múltiple) stay in the
 * menu until the tool is active, then a pressed button sits beside
 * Herramientas so the mode has a visible exit.
 */

import { Box, Menu, UnstyledButton } from '@mantine/core';
import { memo, type RefObject, useState } from 'react';
import { createPortal } from 'react-dom';
import { mapColorTokens } from '../../../lib/mapColorTokens';
import styles from '../../../styles/components/map.module.css';
import {
  IconLayers,
  IconMapPin,
  IconPolygon,
  IconRoute,
  IconRuler,
  IconTrash,
  IconVectorTriangle,
} from '../../ui/icons';
import { MapExportMenuItems } from '../MapActionsPanel';
import { MapShareQrModal } from '../MapShareLink';
import { MAP_CTRL_GLYPH_SIZE } from '../map2dConfig';
import type { MeasurementMode } from './useMeasurement';

export interface MeasurementToolbarProps {
  readonly mode: MeasurementMode;
  readonly hasMeasurements: boolean;
  /** Live km/m or ha while the user is still placing vertices. */
  readonly liveLabel?: string | null;
  readonly onStartDistance: () => void;
  readonly onStartArea: () => void;
  readonly onClear: () => void;
  readonly onUndo?: () => void;
  readonly onSavePersonal?: () => void;
  /**
   * Cancel the ACTIVE measurement without wiping saved ones. Omit it
   * (3D viewer / legacy callers) and Cancelar falls back to `onClear`.
   */
  readonly onCancel?: () => void;
  readonly fichaDrawActive?: boolean;
  readonly onToggleFichaDraw?: () => void;
  readonly onRedrawPolygon?: () => void;
  readonly onDeletePolygon?: () => void;
  readonly fichaCanalActive?: boolean;
  readonly onToggleFichaCanal?: () => void;
  readonly fichaMultiSelectActive?: boolean;
  readonly onToggleFichaMultiSelect?: () => void;
  readonly poiPlaceActive?: boolean;
  readonly onTogglePoiPlace?: () => void;
  readonly hasApprovedZones?: boolean;
  readonly onOpenExportPng?: () => void;
  readonly onExportApprovedZonesPdf?: () => void;
  readonly onExportKmz?: () => void;
  readonly onExportMenuOpen?: () => void;
  /** Canvas element that hosts the measuring bar. */
  readonly portalTarget?: RefObject<HTMLElement | null>;
}

function ToolsMenuDropdown({
  hasMeasurements,
  onStartDistance,
  onStartArea,
  onClear,
  onToggleFichaDraw,
  onToggleFichaCanal,
  onTogglePoiPlace,
  onToggleFichaMultiSelect,
  fichaMultiSelectActive,
  showExport,
  hasApprovedZones,
  onOpenExportPng,
  onExportApprovedZonesPdf,
  onExportKmz,
  onOpenQr,
}: Pick<
  MeasurementToolbarProps,
  | 'hasMeasurements'
  | 'onStartDistance'
  | 'onStartArea'
  | 'onClear'
  | 'onToggleFichaDraw'
  | 'onToggleFichaCanal'
  | 'onTogglePoiPlace'
  | 'onToggleFichaMultiSelect'
  | 'hasApprovedZones'
  | 'onOpenExportPng'
  | 'onExportApprovedZonesPdf'
  | 'onExportKmz'
> & {
  readonly fichaMultiSelectActive: boolean;
  readonly showExport: boolean;
  readonly hasApprovedZones: boolean;
  readonly onOpenQr: () => void;
}) {
  return (
    <Menu.Dropdown>
      <Menu.Label>Medir</Menu.Label>
      <Menu.Item leftSection={<IconRuler size={14} />} onClick={onStartDistance}>
        Medir distancia
      </Menu.Item>
      <Menu.Item leftSection={<IconPolygon size={14} />} onClick={onStartArea}>
        Medir área
      </Menu.Item>
      {hasMeasurements ? (
        <Menu.Item leftSection={<IconTrash size={14} />} onClick={onClear}>
          Limpiar mediciones
        </Menu.Item>
      ) : null}
      {onToggleFichaDraw ? (
        <Menu.Item
          leftSection={<IconVectorTriangle size={14} />}
          aria-label="Dibujar polígono"
          onClick={onToggleFichaDraw}
        >
          Dibujar polígono
        </Menu.Item>
      ) : null}
      {onToggleFichaCanal ? (
        <Menu.Item
          leftSection={<IconRoute size={14} />}
          aria-label="Seleccionar canal"
          onClick={onToggleFichaCanal}
        >
          Seleccionar canal
        </Menu.Item>
      ) : null}
      {onTogglePoiPlace ? (
        <Menu.Item
          leftSection={<IconMapPin size={14} />}
          aria-label="Marcar punto de interés"
          onClick={onTogglePoiPlace}
        >
          Marcar punto de interés
        </Menu.Item>
      ) : null}
      {onToggleFichaMultiSelect ? (
        <Menu.Item
          leftSection={<IconLayers size={14} />}
          aria-label="Selección múltiple de parcelas"
          aria-pressed={fichaMultiSelectActive ? 'true' : 'false'}
          data-testid="ficha-multi-select-toggle"
          onClick={onToggleFichaMultiSelect}
        >
          Selección múltiple
        </Menu.Item>
      ) : null}
      {showExport && onOpenExportPng && onExportApprovedZonesPdf ? (
        <>
          <Menu.Divider />
          <Menu.Label>Exportar</Menu.Label>
          <MapExportMenuItems
            hasApprovedZones={hasApprovedZones}
            onOpenExportPng={onOpenExportPng}
            onExportApprovedZonesPdf={onExportApprovedZonesPdf}
            onExportKmz={onExportKmz}
            onOpenQr={onOpenQr}
          />
        </>
      ) : null}
    </Menu.Dropdown>
  );
}

export const MeasurementToolbar = memo(function MeasurementToolbar({
  mode,
  hasMeasurements,
  liveLabel,
  onStartDistance,
  onStartArea,
  onClear,
  onCancel,
  onUndo,
  onSavePersonal,
  fichaDrawActive = false,
  onToggleFichaDraw,
  onRedrawPolygon,
  onDeletePolygon,
  fichaCanalActive = false,
  onToggleFichaCanal,
  fichaMultiSelectActive = false,
  onToggleFichaMultiSelect,
  poiPlaceActive = false,
  onTogglePoiPlace,
  hasApprovedZones = false,
  onOpenExportPng,
  onExportApprovedZonesPdf,
  onExportKmz,
  onExportMenuOpen,
  portalTarget,
}: MeasurementToolbarProps) {
  const [qrOpen, setQrOpen] = useState(false);
  const isMeasuring = mode === 'measuring-distance' || mode === 'measuring-area';
  const showExport = Boolean(onOpenExportPng && onExportApprovedZonesPdf);

  if (isMeasuring) {
    const bar = (
      <div
        className={styles.measurementActionBar}
        data-testid="measurement-action-bar"
        role="toolbar"
        aria-label="Medición en curso"
      >
        {liveLabel ? <span data-testid="measurement-live">{liveLabel}</span> : null}
        {onUndo ? (
          <button
            type="button"
            className={styles.measurementActionButton}
            aria-label="Deshacer vértice"
            onClick={onUndo}
          >
            Deshacer
          </button>
        ) : null}
        {onSavePersonal && hasMeasurements ? (
          <button
            type="button"
            className={styles.measurementActionButton}
            aria-label="Guardar medición"
            onClick={onSavePersonal}
          >
            Guardar
          </button>
        ) : null}
        <button
          type="button"
          className={styles.measurementActionButton}
          aria-label="Cancelar medición"
          onClick={onCancel ?? onClear}
        >
          Cancelar
        </button>
      </div>
    );
    if (portalTarget?.current) return createPortal(bar, portalTarget.current);
    return bar;
  }

  return (
    <Box className={`maplibregl-ctrl maplibregl-ctrl-group ${styles.mapActionsDock}`}>
      <Menu shadow="md" width={230} onOpen={onExportMenuOpen}>
        <Menu.Target>
          <UnstyledButton
            type="button"
            aria-label="Herramientas"
            aria-pressed={false}
            className={styles.mapCtrlButton}
            style={{ color: mapColorTokens.h333 }}
          >
            <IconRuler size={MAP_CTRL_GLYPH_SIZE} />
            <span className={styles.mapCtrlButtonLabel}>Herramientas</span>
          </UnstyledButton>
        </Menu.Target>
        <ToolsMenuDropdown
          hasMeasurements={hasMeasurements}
          onStartDistance={onStartDistance}
          onStartArea={onStartArea}
          onClear={onClear}
          onToggleFichaDraw={onToggleFichaDraw}
          onToggleFichaCanal={onToggleFichaCanal}
          onTogglePoiPlace={onTogglePoiPlace}
          onToggleFichaMultiSelect={onToggleFichaMultiSelect}
          fichaMultiSelectActive={fichaMultiSelectActive}
          showExport={showExport}
          hasApprovedZones={hasApprovedZones}
          onOpenExportPng={onOpenExportPng}
          onExportApprovedZonesPdf={onExportApprovedZonesPdf}
          onExportKmz={onExportKmz}
          onOpenQr={() => setQrOpen(true)}
        />
      </Menu>
      <MapShareQrModal opened={qrOpen} onClose={() => setQrOpen(false)} />

      {fichaDrawActive && onToggleFichaDraw ? (
        <UnstyledButton
          type="button"
          aria-label="Dibujar polígono"
          aria-pressed
          onClick={onToggleFichaDraw}
          className={styles.mapCtrlButton}
          style={{ background: mapColorTokens.hfb923c, color: mapColorTokens.hfff }}
        >
          <IconVectorTriangle size={MAP_CTRL_GLYPH_SIZE} />
          <span className={styles.mapCtrlButtonLabel}>Dibujar</span>
        </UnstyledButton>
      ) : null}
      {fichaDrawActive && onRedrawPolygon ? (
        <UnstyledButton
          type="button"
          aria-label="Dibujar otro polígono"
          onClick={onRedrawPolygon}
          className={styles.mapCtrlButton}
          data-testid="ficha-draw-new-polygon"
          style={{ color: mapColorTokens.h333 }}
        >
          <IconPolygon size={MAP_CTRL_GLYPH_SIZE} />
          <span className={styles.mapCtrlButtonLabel}>Otro</span>
        </UnstyledButton>
      ) : null}
      {fichaDrawActive && onDeletePolygon ? (
        <UnstyledButton
          type="button"
          aria-label="Borrar el polígono dibujado"
          onClick={onDeletePolygon}
          className={styles.mapCtrlButton}
          data-testid="ficha-draw-delete-polygon"
          style={{ color: mapColorTokens.hdc2626 }}
        >
          <IconTrash size={MAP_CTRL_GLYPH_SIZE} />
          <span className={styles.mapCtrlButtonLabel}>Borrar</span>
        </UnstyledButton>
      ) : null}
      {fichaCanalActive && onToggleFichaCanal ? (
        <UnstyledButton
          type="button"
          aria-label="Seleccionar canal"
          aria-pressed
          onClick={onToggleFichaCanal}
          className={styles.mapCtrlButton}
          style={{ background: mapColorTokens.h06b6d4, color: mapColorTokens.hfff }}
        >
          <IconRoute size={MAP_CTRL_GLYPH_SIZE} />
          <span className={styles.mapCtrlButtonLabel}>Canal</span>
        </UnstyledButton>
      ) : null}
      {poiPlaceActive && onTogglePoiPlace ? (
        <UnstyledButton
          type="button"
          aria-label="Marcar punto de interés"
          aria-pressed
          onClick={onTogglePoiPlace}
          className={styles.mapCtrlButton}
          style={{ background: mapColorTokens.hc45c26, color: mapColorTokens.hfff }}
        >
          <IconMapPin size={MAP_CTRL_GLYPH_SIZE} />
          <span className={styles.mapCtrlButtonLabel}>Punto</span>
        </UnstyledButton>
      ) : null}
      {fichaMultiSelectActive && onToggleFichaMultiSelect ? (
        <UnstyledButton
          type="button"
          aria-label="Selección múltiple de parcelas"
          aria-pressed
          onClick={onToggleFichaMultiSelect}
          className={styles.mapCtrlButton}
          data-testid="ficha-multi-select-toggle"
          style={{ background: mapColorTokens.hf59f00, color: mapColorTokens.hfff }}
        >
          <IconLayers size={MAP_CTRL_GLYPH_SIZE} />
          <span className={styles.mapCtrlButtonLabel}>Varias</span>
        </UnstyledButton>
      ) : null}
    </Box>
  );
});
