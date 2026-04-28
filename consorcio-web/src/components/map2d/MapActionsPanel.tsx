import { ActionIcon, Box, Menu, Paper, Tooltip } from '@mantine/core';
import { memo } from 'react';
import { IconDownload, IconFileZip, IconMap, IconPhoto } from '../ui/icons';

/**
 * Identifier kept for backwards compatibility with the SuggestedZonesPanel
 * (`aria-controls` reference). The "Ver zonificación" button that used to
 * toggle this panel was retired on 2026-04-28 — the panel + workflow stay
 * intact so they can be reconnected by re-introducing the button.
 */
export const SUGGESTED_ZONES_PANEL_ID = 'map-suggested-zones-panel';

interface MapActionsPanelProps {
  /** Gates the "Exportar PDF" entry. PDF needs an approved zoning to render. */
  readonly hasApprovedZones: boolean;
  readonly onOpenExportPng: () => void;
  readonly onExportApprovedZonesPdf: () => void;
  /**
   * Optional — when provided, renders an "Exportar KMZ" entry in the
   * dropdown (sibling of "Exportar PNG" / "Exportar PDF"). The KMZ is
   * NEVER truly empty because the builder keeps the YPF layer as an
   * always-on floor; the on-empty UX is handled inside the handler
   * itself (try/catch + red notification).
   */
  readonly onExportKmz?: () => void;
}

/**
 * Tiny floating panel that exposes the "Exportar" dropdown (PNG/PDF/KMZ).
 *
 * Position: docked to the right edge of the map, between the MapLibre
 * `FullscreenControl` (~top 140px) and the `MeasurementToolbar` (top 220px),
 * so it visually belongs to the right-side toolbar column instead of
 * floating in the corner. The "Ver zonificación" button + the
 * `<LineDrawControl>` were retired in the 2026-04-28 cleanup pass.
 */
export const MapActionsPanel = memo(function MapActionsPanel({
  hasApprovedZones,
  onOpenExportPng,
  onExportApprovedZonesPdf,
  onExportKmz,
}: MapActionsPanelProps) {
  return (
    <Box
      style={{
        position: 'absolute',
        top: 175,
        right: 10,
        zIndex: 16,
      }}
    >
      <Paper
        shadow="md"
        p={4}
        radius="md"
        style={{
          background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
          backdropFilter: 'blur(6px)',
        }}
      >
        <Menu shadow="md" width={200}>
          <Menu.Target>
            <Tooltip label="Exportar" position="left" withArrow>
              <ActionIcon aria-label="Exportar" size="md" variant="light">
                <IconDownload size={14} />
              </ActionIcon>
            </Tooltip>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item leftSection={<IconPhoto size={14} />} onClick={onOpenExportPng}>
              Exportar PNG
            </Menu.Item>
            {hasApprovedZones && (
              <Menu.Item leftSection={<IconMap size={14} />} onClick={onExportApprovedZonesPdf}>
                Exportar PDF
              </Menu.Item>
            )}
            {onExportKmz && (
              <Menu.Item leftSection={<IconFileZip size={14} />} onClick={onExportKmz}>
                Exportar KMZ
              </Menu.Item>
            )}
          </Menu.Dropdown>
        </Menu>
      </Paper>
    </Box>
  );
});
