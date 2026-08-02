import { Box, Menu, Tooltip, UnstyledButton } from '@mantine/core';
import { memo } from 'react';
import { IconDownload, IconFileZip, IconMap, IconPhoto } from '../ui/icons';

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
  /**
   * Fired when the Export dropdown OPENS — i.e. the first observable signal of
   * export INTENT, before the user picks a format. The container uses it to
   * kick off the heavy catastro GeoJSON fetch that only the KMZ export needs,
   * so a plain map visitor never pays for it.
   */
  readonly onExportMenuOpen?: () => void;
}

/**
 * Floating "Exportar" trigger docked to the right edge of the map.
 *
 * The wrapper reuses MapLibre's own `maplibregl-ctrl maplibregl-ctrl-group`
 * CSS classes so the button inherits the EXACT visual treatment of
 * `NavigationControl` and `FullscreenControl` (29×29 white square, 4px
 * radius, the same `0 0 0 2px rgba(0,0,0,.1)` shadow). That guarantees the
 * right-side toolbar reads as one coherent column without us having to
 * keep our hand-rolled style in sync with upstream MapLibre changes.
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
  onExportMenuOpen,
}: MapActionsPanelProps) {
  return (
    <Box
      className="maplibregl-ctrl maplibregl-ctrl-group"
      style={{
        position: 'absolute',
        top: 144,
        right: 10,
        zIndex: 16,
        margin: 0,
      }}
    >
      <Menu shadow="md" width={200} onOpen={onExportMenuOpen}>
        <Menu.Target>
          <Tooltip label="Exportar" position="left" withArrow>
            <UnstyledButton
              type="button"
              aria-label="Exportar"
              style={{
                width: 29,
                height: 29,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                color: '#333',
              }}
            >
              <IconDownload size={16} />
            </UnstyledButton>
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
