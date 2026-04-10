import { Badge, Button, Card, Group, Paper, SimpleGrid, Text, Title, Tooltip } from '@mantine/core';
import type { SelectedImage } from '../../../hooks/useSelectedImage';
import type { ImageComparison } from '../../../hooks/useImageComparison';

import type { ImageResultLike } from './imageExplorerUtils';
import { IconCheck, IconGitCompare, IconPhoto, IconSatellite, IconX, IconCalendar } from '../../ui/icons';

interface HistoricFlood {
  id: string;
  name: string;
  date: string;
  description: string;
  severity: string;
}

interface ImageExplorerInfoPanelsProps {
  result: ImageResultLike | null;
  isCurrentImageSelected: boolean;
  comparison: ImageComparison | null;
  onSelectImage: () => void;
  onSetLeftImage: () => void;
  onSetRightImage: () => void;
  historicFloods: HistoricFlood[];
  onLoadHistoricFlood: (floodId: string) => void;
  selectedImage: SelectedImage | null;
  onClearSelectedImage: () => void;
  comparisonReady: boolean;
  onClearComparison: () => void;
  sensor: 'sentinel2' | 'sentinel1';
}

export function ImageExplorerInfoPanels(props: ImageExplorerInfoPanelsProps) {
  const {
    result, isCurrentImageSelected, comparison, onSelectImage, onSetLeftImage, onSetRightImage,
    historicFloods, onLoadHistoricFlood, selectedImage, onClearSelectedImage, comparisonReady,
    onClearComparison, sensor,
  } = props;

  return (
    <>
      {result && (
        <Paper p="md" withBorder radius="md">
          <Group justify="space-between" wrap="wrap" gap="md">
            <Group gap="lg" wrap="wrap">
              {result.flood_info && <Badge color="blue" variant="light" size="lg">{result.flood_info.name}</Badge>}
              <Group gap={4}><IconSatellite size={16} /><Text size="sm" fw={500}>{result.sensor}</Text></Group>
              <Group gap={4}><IconCalendar size={16} /><Text size="sm" fw={500}>{result.target_date}</Text></Group>
              <Text size="sm" c="dimmed">{result.visualization_description}</Text>
              <Text size="xs" c="dimmed">{result.images_count} imagen{result.images_count !== 1 ? 'es' : ''} | {result.collection}</Text>
            </Group>
            <Group gap="sm" wrap="wrap">
              <Button variant={isCurrentImageSelected ? 'light' : 'filled'} color={isCurrentImageSelected ? 'green' : 'blue'} leftSection={isCurrentImageSelected ? <IconCheck size={16} /> : <IconPhoto size={16} />} onClick={onSelectImage} disabled={isCurrentImageSelected} size="sm">
                {isCurrentImageSelected ? 'Seleccionada' : 'Usar esta imagen'}
              </Button>
              <Tooltip label="Comparar: imagen izquierda (antes)"><Button variant={comparison?.left?.tile_url === result?.tile_url ? 'light' : 'outline'} color="blue" size="sm" onClick={onSetLeftImage}>Izquierda</Button></Tooltip>
              <Tooltip label="Comparar: imagen derecha (despues)"><Button variant={comparison?.right?.tile_url === result?.tile_url ? 'light' : 'outline'} color="green" size="sm" onClick={onSetRightImage}>Derecha</Button></Tooltip>
            </Group>
          </Group>
        </Paper>
      )}

      {historicFloods.length > 0 && (
        <Paper p="md" withBorder radius="md">
          <Title order={5} mb="sm"><Group gap="xs"><IconPhoto size={20} />Escenas Historicas</Group></Title>
          <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
            {historicFloods.map((flood) => (
              <Card key={flood.id} padding="sm" radius="md" withBorder style={{ cursor: 'pointer' }} onClick={() => onLoadHistoricFlood(flood.id)}>
                <Group justify="space-between" mb="xs">
                  <Text fw={500}>{flood.name}</Text>
                  <Badge color={flood.severity === 'alta' ? 'red' : flood.severity === 'media' ? 'orange' : 'yellow'} size="sm">{flood.severity}</Badge>
                </Group>
                <Text size="sm" c="dimmed">{flood.description}</Text>
                <Text size="xs" c="dimmed" mt="xs">{flood.date}</Text>
              </Card>
            ))}
          </SimpleGrid>
        </Paper>
      )}

      {selectedImage && (
        <Paper p="sm" withBorder radius="md" bg="green.0">
          <Group justify="space-between">
            <Group gap="xs">
              <IconCheck size={18} color="var(--mantine-color-green-7)" />
              <Text size="sm" fw={500} c="green.7">Imagen activa en otras vistas:</Text>
              <Badge variant="light" color="green">{selectedImage.sensor} - {selectedImage.target_date}</Badge>
              <Text size="sm" c="dimmed">({selectedImage.visualization_description})</Text>
            </Group>
            <Button variant="subtle" color="red" size="xs" leftSection={<IconX size={14} />} onClick={onClearSelectedImage}>Quitar</Button>
          </Group>
        </Paper>
      )}

      {comparison && (
        <Paper p="sm" withBorder radius="md" bg="blue.0">
          <Group justify="space-between">
            <Group gap="md">
              <IconGitCompare size={18} color="var(--mantine-color-blue-7)" />
              <Text size="sm" fw={500} c="blue.7">Comparacion activa:</Text>
              <Group gap="xs">
                <Badge variant="light" color="blue">{comparison.left?.target_date || 'Sin seleccionar'}</Badge>
                <Text size="sm" c="dimmed">vs</Text>
                <Badge variant="light" color="green">{comparison.right?.target_date || 'Sin seleccionar'}</Badge>
              </Group>
              {comparisonReady && <Text size="xs" c="dimmed">(Ve al Mapa para ver la comparacion)</Text>}
            </Group>
            <Button variant="subtle" color="red" size="xs" leftSection={<IconX size={14} />} onClick={onClearComparison}>Quitar</Button>
          </Group>
        </Paper>
      )}

      <Paper p="sm" withBorder radius="md">
        <Group gap="lg" wrap="wrap">
          <Text size="sm" fw={500}>Visualizaciones:</Text>
          {sensor === 'sentinel2'
            ? <Text size="sm" c="dimmed">RGB = Color natural | NDWI/MNDWI = Agua en azul | NDVI = Vegetacion en verde | Inundacion = Agua detectada</Text>
            : <Text size="sm" c="dimmed">VV = Radar (oscuro=agua) | VV Flood = Deteccion de inundacion en cyan</Text>}
        </Group>
      </Paper>
    </>
  );
}
