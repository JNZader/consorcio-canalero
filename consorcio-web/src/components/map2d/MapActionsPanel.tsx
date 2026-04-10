import { Box, Button, Group, Menu, Paper } from '@mantine/core';
import type { ReactNode } from 'react';
import { memo } from 'react';
import { IconDownload, IconLayers, IconMap, IconPhoto } from '../ui/icons';

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
              <Button size="xs" variant="light" leftSection={<IconDownload size={14} />}>
                Exportar
              </Button>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconPhoto size={14} />} onClick={onOpenExportPng}>
                Exportar PNG
              </Menu.Item>
              {hasApprovedZones && (
                <Menu.Item leftSection={<IconMap size={14} />} onClick={onExportApprovedZonesPdf}>
                  Exportar PDF zonificación
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
