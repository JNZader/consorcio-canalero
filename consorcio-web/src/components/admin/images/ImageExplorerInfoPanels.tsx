import { Badge, Button, Card, Group, Paper, SimpleGrid, Text, Title, Tooltip } from '@mantine/core';
import type { ImageComparison } from '../../../hooks/useImageComparison';
import type { SelectedImage } from '../../../hooks/useSelectedImage';

import {
  IconCalendar,
  IconCheck,
  IconGitCompare,
  IconPhoto,
  IconSatellite,
  IconX,
} from '../../ui/icons';
import {
  type ImageResultLike,
  type ImageSceneLike,
  type ImageSensor,
  isOpticalSensor,
  l7GapfillHelp,
} from './imageExplorerUtils';

interface ImageExplorerInfoPanelsProps {
  result: ImageResultLike | null;
  isCurrentImageSelected: boolean;
  comparison: ImageComparison | null;
  onSelectImage: () => void;
  onSetLeftImage: () => void;
  onSetRightImage: () => void;
  selectedImage: SelectedImage | null;
  onClearSelectedImage: () => void;
  comparisonReady: boolean;
  onClearComparison: () => void;
  sensor: ImageSensor;
  scenes: ImageSceneLike[];
  selectedSceneId: string | null;
  onSelectScene: (scene: ImageSceneLike) => void;
  compositionMode: 'scene' | 'composite';
  /** When true, skip imagen/par banners (publish tray owns that). */
  hidePublishBanners?: boolean;
}

export function ImageExplorerInfoPanels(props: ImageExplorerInfoPanelsProps) {
  const {
    result,
    isCurrentImageSelected,
    comparison,
    onSelectImage,
    onSetLeftImage,
    onSetRightImage,
    selectedImage,
    onClearSelectedImage,
    comparisonReady,
    onClearComparison,
    sensor,
    scenes,
    selectedSceneId,
    onSelectScene,
    compositionMode,
    hidePublishBanners = false,
  } = props;

  return (
    <>
      {result && (
        <Paper p="md" withBorder radius="md">
          <Group justify="space-between" wrap="wrap" gap="md">
            <Group gap="lg" wrap="wrap">
              {result.flood_info && (
                <Badge color="institucional" variant="light" size="lg">
                  {result.flood_info.name}
                </Badge>
              )}
              <Group gap={4}>
                <IconSatellite size={16} />
                <Text size="sm" fw={500}>
                  {result.sensor}
                </Text>
              </Group>
              <Group gap={4}>
                <IconCalendar size={16} />
                <Text size="sm" fw={500}>
                  {result.target_date}
                </Text>
              </Group>
              <Text size="sm" c="dimmed">
                {result.visualization_description}
              </Text>
              <Text size="xs" c="dimmed">
                {result.images_count} imagen{result.images_count !== 1 ? 'es' : ''} |{' '}
                {result.collection}
              </Text>
              {result.notes && (
                <Text size="xs" c="orange.7">
                  {result.notes}
                </Text>
              )}
            </Group>
            <Group gap="sm" wrap="wrap">
              <Button
                variant={isCurrentImageSelected ? 'light' : 'filled'}
                color={isCurrentImageSelected ? 'green' : 'blue'}
                leftSection={
                  isCurrentImageSelected ? <IconCheck size={16} /> : <IconPhoto size={16} />
                }
                onClick={onSelectImage}
                disabled={isCurrentImageSelected}
                size="sm"
              >
                {isCurrentImageSelected ? 'Seleccionada' : 'Usar esta imagen'}
              </Button>
              <Tooltip label="Usar como Antes (referencia / sin agua)">
                <Button
                  variant={comparison?.left?.tile_url === result?.tile_url ? 'light' : 'outline'}
                  size="sm"
                  onClick={onSetLeftImage}
                >
                  Antes
                </Button>
              </Tooltip>
              <Tooltip label="Usar como Después (crecida / detección)">
                <Button
                  variant={comparison?.right?.tile_url === result?.tile_url ? 'light' : 'outline'}
                  size="sm"
                  onClick={onSetRightImage}
                >
                  Después
                </Button>
              </Tooltip>
            </Group>
          </Group>
        </Paper>
      )}

      {scenes.length > 0 && (
        <Paper p="md" withBorder radius="md">
          <Group justify="space-between" mb="sm">
            <Title order={5}>Escenas individuales</Title>
            {sensor === 'landsat7' && (
              <Badge color={compositionMode === 'composite' ? 'green' : 'orange'} variant="light">
                {compositionMode === 'composite'
                  ? 'Vista actual: relleno SLC-off'
                  : 'Vista actual: escena con franjas'}
              </Badge>
            )}
          </Group>
          <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
            {scenes.map((scene) => (
              <Card key={scene.id} padding="sm" radius="md" withBorder>
                <Group justify="space-between" mb="xs">
                  <Text size="sm" fw={500} lineClamp={1}>
                    {scene.label}
                  </Text>
                  {selectedSceneId === scene.id && (
                    <Badge color="exito" size="sm">
                      activa
                    </Badge>
                  )}
                </Group>
                <Text size="xs" c="dimmed">
                  {scene.cloud_cover != null ? `Nubes: ${Math.round(scene.cloud_cover)}%` : ''}
                  {scene.path != null && scene.row != null ? ` · P${scene.path}/R${scene.row}` : ''}
                </Text>
                <Button
                  mt="sm"
                  size="xs"
                  variant={selectedSceneId === scene.id ? 'light' : 'outline'}
                  onClick={() => onSelectScene(scene)}
                  fullWidth
                >
                  Ver esta escena
                </Button>
              </Card>
            ))}
          </SimpleGrid>
          {sensor === 'landsat7' && (
            <Text size="xs" c="orange.7" mt="sm">
              {l7GapfillHelp(result)}
            </Text>
          )}
        </Paper>
      )}

      {!hidePublishBanners && selectedImage && (
        <Paper p="sm" withBorder radius="md" bg="exito.0">
          <Group justify="space-between">
            <Group gap="xs">
              <IconCheck size={18} color="var(--mantine-color-exito-7)" />
              <Text size="sm" fw={500} c="exito.7">
                Imagen activa en otras vistas:
              </Text>
              <Badge variant="light" color="exito">
                {selectedImage.sensor} - {selectedImage.target_date}
              </Badge>
              <Text size="sm" c="dimmed">
                ({selectedImage.visualization_description})
              </Text>
            </Group>
            <Button
              variant="subtle"
              color="alerta"
              size="xs"
              leftSection={<IconX size={14} />}
              onClick={onClearSelectedImage}
            >
              Quitar
            </Button>
          </Group>
        </Paper>
      )}

      {!hidePublishBanners && comparison && (
        <Paper p="sm" withBorder radius="md" bg="institucional.0">
          <Group justify="space-between">
            <Group gap="md">
              <IconGitCompare size={18} color="var(--mantine-color-institucional-7)" />
              <Text size="sm" fw={500} c="institucional.7">
                Par en bandeja:
              </Text>
              <Group gap="xs">
                <Badge variant="light" color="institucional">
                  Antes {comparison.left?.target_date || '—'}
                </Badge>
                <Text size="sm" c="dimmed">
                  vs
                </Text>
                <Badge variant="light" color="exito">
                  Después {comparison.right?.target_date || '—'}
                </Badge>
              </Group>
              {comparisonReady && (
                <Text size="xs" c="dimmed">
                  Usá Abrir en mapa arriba
                </Text>
              )}
            </Group>
            <Button
              variant="subtle"
              color="alerta"
              size="xs"
              leftSection={<IconX size={14} />}
              onClick={onClearComparison}
            >
              Quitar
            </Button>
          </Group>
        </Paper>
      )}

      <Paper p="sm" withBorder radius="md">
        <Group gap="lg" wrap="wrap">
          <Text size="sm" fw={500}>
            Visualizaciones:
          </Text>
          {isOpticalSensor(sensor) ? (
            <Text size="sm" c="dimmed">
              RGB = Color natural | Falso color = vegetacion en rojo | NDWI/MNDWI = Agua |
              Inundación = NDWI &gt; 0
              {sensor === 'landsat7' ? ' | Landsat 7 puede tener gaps SLC-off' : ''}
            </Text>
          ) : (
            <Text size="sm" c="dimmed">
              VV = Radar (oscuro=agua) | VV Flood = Deteccion de inundacion en cyan
            </Text>
          )}
        </Group>
      </Paper>
    </>
  );
}
