import { ActionIcon, Box, Button, Group, Menu, Paper, Tooltip } from '@mantine/core';
import type { ReactNode } from 'react';
import { memo } from 'react';
import { IconDownload, IconFileZip, IconLayers, IconMap, IconPhoto } from '../ui/icons';

export const SUGGESTED_ZONES_PANEL_ID = 'map-suggested-zones-panel';

interface MapActionsPanelProps {
  readonly isOperator: boolean;
  readonly markingMode: boolean;
  readonly onToggleMarkingMode: () => void;
  readonly canManageZoning: boolean;
  readonly showSuggestedZonesPanel: boolean;
  readonly hasApprovedZones: boolean;
  readonly onToggleSuggestedZonesPanel: () => void;
  readonly onOpenExportPng: () => void;
  readonly onExportApprovedZonesPdf: () => void;
  /**
   * Optional — when provided, renders a new "Exportar KMZ" entry in
   * the Export dropdown (sibling of "Exportar PNG" / "Exportar PDF").
   * Mirrors the gating style of
   * `onExportApprovedZonesPdf` (entry is conditionally rendered based
   * on the capability being available).
   *
   * KMZ is NEVER truly empty because the builder keeps the YPF layer
   * as an always-on floor; the on-empty UX is handled inside the
   * handler itself (try/catch + red notification). That's why we do
   * NOT disable the entry based on `visibleVectors`.
   */
  readonly onExportKmz?: () => void;
  readonly children?: ReactNode;
}

export const MapActionsPanel = memo(function MapActionsPanel({
  isOperator,
  markingMode,
  onToggleMarkingMode,
  canManageZoning,
  showSuggestedZonesPanel,
  hasApprovedZones,
  onToggleSuggestedZonesPanel,
  onOpenExportPng,
  onExportApprovedZonesPdf,
  onExportKmz,
  children,
}: MapActionsPanelProps) {
  return (
    <Box
      style={{
        position: 'absolute',
        top: 12,
        right: 48,
        zIndex: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        alignItems: 'flex-end',
      }}
    >
      <Paper
        shadow="md"
        p="xs"
        radius="md"
        style={{
          background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
          backdropFilter: 'blur(6px)',
        }}
      >
        <Group gap="xs">
          <Menu shadow="md" width={200}>
            <Menu.Target>
              <Tooltip label="Exportar" position="bottom" withArrow>
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

          {isOperator && (
            <Button
              size="xs"
              variant={markingMode ? 'filled' : 'light'}
              color={markingMode ? 'red' : undefined}
              onClick={onToggleMarkingMode}
              aria-pressed={markingMode}
            >
              {markingMode ? 'Cancelar marcado' : 'Marcar punto'}
            </Button>
          )}

          {canManageZoning && (
            <Button
              size="xs"
              variant="light"
              leftSection={<IconLayers size={14} />}
              onClick={onToggleSuggestedZonesPanel}
              aria-expanded={showSuggestedZonesPanel}
              aria-controls={SUGGESTED_ZONES_PANEL_ID}
            >
              {showSuggestedZonesPanel
                ? 'Ocultar zonificación'
                : hasApprovedZones
                  ? 'Ver zonificación'
                  : 'Zonas sugeridas'}
            </Button>
          )}
        </Group>
      </Paper>

      {children}
    </Box>
  );
});
