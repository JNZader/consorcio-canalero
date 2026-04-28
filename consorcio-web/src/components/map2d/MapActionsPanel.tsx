import { ActionIcon, Box, Menu, Tooltip } from '@mantine/core';
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
 * Floating "Exportar" trigger docked to the right edge of the map. The
 * button mimics the visual weight of the MapLibre native controls
 * (`NavigationControl`, `FullscreenControl`) — 29×29 white square with
 * the same subtle shadow — so the right-side toolbar reads as one
 * coherent column instead of a stack of mismatched widgets.
 *
 * Position: `top: 144, right: 10` puts it directly under the
 * FullscreenControl (which lands around 110–135px) and above the
 * MeasurementToolbar at `top: 180`.
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
        top: 144,
        right: 10,
        zIndex: 16,
      }}
    >
      <Menu shadow="md" width={200}>
        <Menu.Target>
          <Tooltip label="Exportar" position="left" withArrow>
            <ActionIcon
              aria-label="Exportar"
              size={29}
              radius={4}
              variant="default"
              style={{
                background: '#fff',
                color: '#333',
                boxShadow: '0 0 0 2px rgba(0,0,0,0.1)',
              }}
            >
              <IconDownload size={16} />
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
    </Box>
  );
});
