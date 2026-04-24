import {
  Badge,
  Box,
  Button,
  CloseButton,
  Divider,
  Group,
  Paper,
  Select,
  Stack,
  Text,
  TextInput,
  Textarea,
} from '@mantine/core';
import { memo } from 'react';
import { IconDownload } from '../ui/icons';
import { SUGGESTED_ZONES_PANEL_ID } from './MapActionsPanel';

export interface SuggestedZonesPanelProps {
  readonly zones: Array<{
    id: string;
    defaultName: string;
    family?: string | null;
    basinCount: number;
    superficieHa: number;
  }>;
  readonly zoneNames: Record<string, string>;
  readonly onZoneNameChange: (zoneId: string, value: string) => void;
  readonly selectedBasinName: string | null;
  readonly selectedBasinZoneId: string | null;
  readonly destinationZoneId: string | null;
  readonly onDestinationZoneChange: (value: string | null) => void;
  readonly onApplyBasinMove: () => void;
  readonly hasApprovedZones: boolean;
  readonly approvedAt: string | null;
  readonly approvedVersion: number | null;
  readonly approvedZonesHistory: Array<{
    id: string;
    nombre: string;
    version: number;
    approvedAt: string;
    notes?: string | null;
    approvedByName?: string | null;
  }>;
  readonly approvalName: string;
  readonly approvalNotes: string;
  readonly onApprovalNameChange: (value: string) => void;
  readonly onApprovalNotesChange: (value: string) => void;
  readonly onClose: () => void;
  readonly onApproveZones: () => void;
  readonly onClearApprovedZones: () => void;
  readonly onRestoreVersion: (id: string) => void;
  readonly onExportApprovedZonesGeoJSON: () => void;
  readonly onExportApprovedZonesPdf: () => void;
}

export const SuggestedZonesPanel = memo(function SuggestedZonesPanel({
  zones,
  zoneNames,
  onZoneNameChange,
  selectedBasinName,
  selectedBasinZoneId,
  destinationZoneId,
  onDestinationZoneChange,
  onApplyBasinMove,
  hasApprovedZones,
  approvedAt,
  approvedVersion,
  approvedZonesHistory,
  approvalName,
  approvalNotes,
  onApprovalNameChange,
  onApprovalNotesChange,
  onClose,
  onApproveZones,
  onClearApprovedZones,
  onRestoreVersion,
  onExportApprovedZonesGeoJSON,
  onExportApprovedZonesPdf,
}: SuggestedZonesPanelProps) {
  if (zones.length === 0) return null;

  const zoneOptions = zones.map((zone) => ({
    value: zone.id,
    label: zoneNames[zone.id] ?? zone.defaultName,
  }));

  return (
    <Paper
      id={SUGGESTED_ZONES_PANEL_ID}
      aria-label="Panel de zonificación"
      shadow="md"
      p="sm"
      radius="md"
      style={{
        position: 'absolute',
        top: 64,
        left: 12,
        zIndex: 16,
        width: 340,
        maxHeight: 'calc(100% - 80px)',
        overflowY: 'auto',
        background: 'light-dark(rgba(255,255,255,0.96), rgba(36,36,36,0.96))',
        backdropFilter: 'blur(6px)',
      }}
    >
      <Stack gap="xs">
        <Box>
          <Group justify="space-between" align="flex-start" wrap="nowrap">
            <Box style={{ flex: 1 }}>
              <Text size="sm" fw={600}>
                {hasApprovedZones ? 'Zonificación aprobada' : 'Zonas sugeridas'}
              </Text>
            </Box>
            <CloseButton size="sm" onClick={onClose} aria-label="Cerrar panel de zonificación" />
          </Group>
        </Box>

        <Divider />

        {!hasApprovedZones && (
          <>
            <Box>
              <Text size="xs" fw={600} mb={4}>
                Reasignar subcuenca
              </Text>
              <Stack gap={6}>
                <Text size="xs">
                  Subcuenca seleccionada: <b>{selectedBasinName || 'Ninguna'}</b>
                </Text>
                <Text size="xs" c="dimmed">
                  Zona actual:{' '}
                  {selectedBasinZoneId
                    ? (zoneNames[selectedBasinZoneId] ?? selectedBasinZoneId)
                    : '-'}
                </Text>
                <Select
                  size="xs"
                  placeholder="Elegir zona destino"
                  data={zoneOptions}
                  value={destinationZoneId}
                  onChange={onDestinationZoneChange}
                  nothingFoundMessage="Sin zonas"
                />
                <Button
                  size="xs"
                  variant="light"
                  disabled={
                    !selectedBasinName ||
                    !destinationZoneId ||
                    destinationZoneId === selectedBasinZoneId
                  }
                  onClick={onApplyBasinMove}
                >
                  Mover subcuenca a esta zona
                </Button>
              </Stack>
            </Box>
            <Divider />
          </>
        )}

        <Box>
          <Group justify="space-between" align="center" mb={4}>
            <Text size="xs" fw={600}>
              Estado
            </Text>
            {hasApprovedZones ? (
              <Badge size="xs" color="green" variant="light">
                Aprobada
              </Badge>
            ) : (
              <Badge size="xs" color="yellow" variant="light">
                Draft
              </Badge>
            )}
          </Group>
          <Text size="xs" c="dimmed" mb={6}>
            {hasApprovedZones && approvedAt
              ? `Versión actual: v${approvedVersion ?? '-'} • Última aprobación: ${new Date(approvedAt).toLocaleString()}`
              : 'Todavía no hay una zonificación aprobada persistida.'}
          </Text>
          <Stack gap={6} mb={8}>
            <TextInput
              size="xs"
              label="Nombre de versión"
              placeholder="Ej. Zonificación operativa marzo 2026"
              value={approvalName}
              onChange={(event) => onApprovalNameChange(event.currentTarget.value)}
            />
            <Textarea
              size="xs"
              label="Comentario"
              placeholder="Resumen corto del cambio aprobado"
              minRows={2}
              autosize
              value={approvalNotes}
              onChange={(event) => onApprovalNotesChange(event.currentTarget.value)}
            />
          </Stack>
          <Group grow>
            <Button size="xs" color="green" onClick={onApproveZones}>
              Aprobar esta zonificación
            </Button>
            {hasApprovedZones && (
              <Button size="xs" variant="light" color="gray" onClick={onClearApprovedZones}>
                Limpiar aprobada
              </Button>
            )}
          </Group>
          {hasApprovedZones && (
            <Group grow mt={8}>
              <Button
                size="xs"
                variant="light"
                leftSection={<IconDownload size={14} />}
                onClick={onExportApprovedZonesGeoJSON}
              >
                GeoJSON
              </Button>
              <Button
                size="xs"
                variant="light"
                leftSection={<IconDownload size={14} />}
                onClick={onExportApprovedZonesPdf}
              >
                PDF
              </Button>
            </Group>
          )}
        </Box>

        {!hasApprovedZones && (
          <>
            <Divider />
            <Stack gap={6}>
              {zones.map((zone) => (
                <Paper key={zone.id} withBorder p="xs" radius="sm">
                  <Stack gap={4}>
                    <TextInput
                      size="xs"
                      label={zone.defaultName}
                      value={zoneNames[zone.id] ?? zone.defaultName}
                      onChange={(event) => onZoneNameChange(zone.id, event.currentTarget.value)}
                    />
                    <Text size="xs" c="dimmed">
                      Familia: {zone.family || '-'} • Subcuencas: {zone.basinCount} • Sup:{' '}
                      {zone.superficieHa.toFixed(1)} ha
                    </Text>
                  </Stack>
                </Paper>
              ))}
            </Stack>
          </>
        )}

        {approvedZonesHistory.length > 0 && (
          <>
            <Divider />
            <Box>
              <Text size="xs" fw={600} mb={6}>
                Historial de versiones
              </Text>
              <Stack gap={6}>
                {approvedZonesHistory.map((item) => (
                  <Paper key={item.id} withBorder p="xs" radius="sm">
                    <Group justify="space-between" align="flex-start" wrap="nowrap">
                      <Stack gap={2} style={{ flex: 1 }}>
                        <Text size="xs" fw={600}>
                          v{item.version} — {item.nombre}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {new Date(item.approvedAt).toLocaleString()}
                        </Text>
                        {item.approvedByName && (
                          <Text size="xs" c="dimmed">
                            Aprobó: {item.approvedByName}
                          </Text>
                        )}
                        {item.notes && (
                          <Text size="xs" c="dimmed">
                            {item.notes}
                          </Text>
                        )}
                      </Stack>
                      {approvedVersion !== item.version && (
                        <Button size="xs" variant="light" onClick={() => onRestoreVersion(item.id)}>
                          Restaurar
                        </Button>
                      )}
                    </Group>
                  </Paper>
                ))}
              </Stack>
            </Box>
          </>
        )}
      </Stack>
    </Paper>
  );
});
