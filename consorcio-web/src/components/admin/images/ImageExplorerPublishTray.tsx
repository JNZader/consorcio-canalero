/**
 * Persistent publish tray: what will appear on /mapa, plus Abrir en mapa CTA.
 */
import { Badge, Button, Group, Paper, Stack, Text } from '@mantine/core';
import { useNavigate } from '@tanstack/react-router';

import type { ImageComparison } from '../../../hooks/useImageComparison';
import type { SelectedImage } from '../../../hooks/useSelectedImage';
import { setMapPreferredView } from '../../../lib/mapPreferredView';
import { IconGitCompare, IconPhoto, IconX } from '../../ui/icons';

export interface ImageExplorerPublishTrayProps {
  selectedImage: SelectedImage | null;
  comparison: ImageComparison | null;
  comparisonReady: boolean;
  onClearSelectedImage: () => void;
  onClearComparison: () => void;
}

export function ImageExplorerPublishTray({
  selectedImage,
  comparison,
  comparisonReady,
  onClearSelectedImage,
  onClearComparison,
}: ImageExplorerPublishTrayProps) {
  const navigate = useNavigate();
  const hasSingle = !!selectedImage;
  const hasPair = !!comparisonReady && !!comparison?.left && !!comparison?.right;
  const canOpen = hasSingle || hasPair;

  function openMap() {
    if (hasPair) {
      setMapPreferredView('comparison');
    } else if (hasSingle) {
      setMapPreferredView('single');
    }
    void navigate({ to: '/mapa' });
  }

  return (
    <Paper p="sm" withBorder radius="md" data-testid="image-explorer-publish-tray">
      <Group justify="space-between" align="flex-start" wrap="wrap" gap="sm">
        <Stack gap={6} style={{ flex: 1, minWidth: 200 }}>
          <Text size="xs" fw={600} c="dimmed" tt="uppercase">
            Listo para el mapa
          </Text>
          {hasSingle ? (
            <Group gap="xs" wrap="wrap">
              <IconPhoto size={16} />
              <Text size="sm" fw={500}>
                Imagen
              </Text>
              <Badge variant="light" color="exito">
                {selectedImage.sensor} · {selectedImage.target_date}
              </Badge>
              <Button
                variant="subtle"
                color="alerta"
                size="compact-xs"
                leftSection={<IconX size={12} />}
                onClick={onClearSelectedImage}
              >
                Quitar
              </Button>
            </Group>
          ) : (
            <Text size="sm" c="dimmed">
              Sin imagen publicada
            </Text>
          )}
          {hasPair ? (
            <Group gap="xs" wrap="wrap">
              <IconGitCompare size={16} />
              <Text size="sm" fw={500}>
                Par
              </Text>
              <Badge variant="light" color="institucional">
                Antes {comparison?.left?.target_date}
              </Badge>
              <Text size="xs" c="dimmed">
                vs
              </Text>
              <Badge variant="light" color="exito">
                Después {comparison?.right?.target_date}
              </Badge>
              <Button
                variant="subtle"
                color="alerta"
                size="compact-xs"
                leftSection={<IconX size={12} />}
                onClick={onClearComparison}
              >
                Quitar
              </Button>
            </Group>
          ) : comparison?.left || comparison?.right ? (
            <Text size="sm" c="dimmed">
              Par incompleto (faltan Antes o Después)
            </Text>
          ) : (
            <Text size="sm" c="dimmed">
              Sin par de comparación
            </Text>
          )}
        </Stack>
        <Button size="sm" disabled={!canOpen} onClick={openMap} data-testid="open-in-map-cta">
          Abrir en mapa
        </Button>
      </Group>
    </Paper>
  );
}
