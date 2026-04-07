/**
 * MartinCatalogPanel — Panel de catalogo de capas vectoriales de Martin.
 *
 * Lista todas las capas tile publicadas automaticamente por Martin desde
 * vistas PostGIS. Cada capa muestra su URL template {z}/{x}/{y} y permite
 * copiarla al portapapeles con confirmacion visual.
 */

import { useState } from 'react';
import {
  ActionIcon,
  Alert,
  Badge,
  Center,
  Code,
  Group,
  Loader,
  Paper,
  Stack,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import {
  IconAlertTriangle,
  IconCheck,
  IconCopy,
  IconClipboardCheck,
  IconMapSearch,
  IconRefresh,
} from './ui/icons';
import { useMartinCatalog, type MartinCatalogItem } from '../hooks/useMartinCatalog';

// ===========================================
// CONSTANTS
// ===========================================

const GEOMETRY_TYPE_COLORS: Record<string, string> = {
  polygon: 'blue',
  multipolygon: 'blue',
  point: 'green',
  multipoint: 'green',
  linestring: 'orange',
  multilinestring: 'orange',
};

function getGeometryColor(geometryType: string): string {
  return GEOMETRY_TYPE_COLORS[geometryType.toLowerCase()] ?? 'gray';
}

// ===========================================
// LAYER CARD
// ===========================================

interface LayerCardProps {
  readonly layer: MartinCatalogItem;
}

function LayerCard({ layer }: LayerCardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(layer.tile_url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const label = layer.description || layer.id;

  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="xs">
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <Stack gap={4}>
            <Text fw={600} size="sm" lh={1.3}>
              {label}
            </Text>
            {layer.description && layer.description !== layer.id && (
              <Text size="xs" c="dimmed">
                {layer.id}
              </Text>
            )}
          </Stack>
          <Badge
            size="sm"
            variant="light"
            color={getGeometryColor(layer.geometry_type)}
            tt="capitalize"
          >
            {layer.geometry_type}
          </Badge>
        </Group>

        <Group gap="xs" wrap="nowrap" align="center">
          <Code
            style={{
              flex: 1,
              fontSize: 11,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              display: 'block',
            }}
          >
            {layer.tile_url}
          </Code>

          <Tooltip
            label={copied ? 'Copiado!' : 'Copiar URL'}
            withArrow
            position="top"
          >
            <ActionIcon
              size="sm"
              variant={copied ? 'filled' : 'light'}
              color={copied ? 'green' : 'blue'}
              onClick={handleCopy}
              aria-label={`Copiar URL de ${label}`}
            >
              {copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
            </ActionIcon>
          </Tooltip>
        </Group>
      </Stack>
    </Paper>
  );
}

// ===========================================
// MAIN PANEL
// ===========================================

export default function MartinCatalogPanel() {
  const { layers, isLoading, isError, error, reload } = useMartinCatalog();

  return (
    <Stack gap="md">
      {/* Header */}
      <Group justify="space-between" align="center">
        <div>
          <Title order={3}>Catalogo de Capas Vectoriales</Title>
          <Text c="dimmed" size="sm">
            Capas publicadas automaticamente por Martin desde vistas PostGIS.
          </Text>
        </div>

        <Tooltip label="Recargar catalogo">
          <ActionIcon
            variant="light"
            size="lg"
            onClick={() => reload()}
            loading={isLoading}
            aria-label="Recargar catalogo"
          >
            <IconRefresh size={18} />
          </ActionIcon>
        </Tooltip>
      </Group>

      {/* Error state */}
      {isError && (
        <Alert
          color="red"
          icon={<IconAlertTriangle size={18} />}
          title="Error al cargar el catalogo"
        >
          {error ?? 'Ocurrio un error inesperado. Intenta recargar.'}
        </Alert>
      )}

      {/* Loading state */}
      {isLoading && (
        <Center py="xl">
          <Stack align="center" gap="xs">
            <Loader size="md" />
            <Text c="dimmed" size="sm">
              Cargando catalogo de capas...
            </Text>
          </Stack>
        </Center>
      )}

      {/* Empty state */}
      {!isLoading && !isError && layers.length === 0 && (
        <Center py="xl">
          <Stack align="center" gap="xs">
            <IconMapSearch size={48} color="var(--mantine-color-dimmed)" />
            <Text c="dimmed" ta="center">
              No hay capas disponibles en el catalogo.
            </Text>
            <Text c="dimmed" size="xs" ta="center">
              Verifica que Martin este corriendo y que existan vistas PostGIS publicadas.
            </Text>
          </Stack>
        </Center>
      )}

      {/* Layer list */}
      {!isLoading && layers.length > 0 && (
        <Stack gap="sm">
          <Group gap="xs">
            <IconClipboardCheck size={16} color="var(--mantine-color-dimmed)" />
            <Text size="sm" c="dimmed">
              {layers.length} {layers.length === 1 ? 'capa disponible' : 'capas disponibles'}
            </Text>
          </Group>

          {layers.map((layer) => (
            <LayerCard key={layer.id} layer={layer} />
          ))}
        </Stack>
      )}
    </Stack>
  );
}
