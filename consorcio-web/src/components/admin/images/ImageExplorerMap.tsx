import { Alert, Button, Card, Loader, Paper, Stack, Text } from '@mantine/core';

import { IconAlertTriangle, IconSatellite } from '../../ui/icons';

/** Header + sensor bar + page padding. The map card fills what remains. */
export const EXPLORER_WORKSPACE_MIN_HEIGHT = 'calc(100dvh - 220px)';

interface ImageExplorerMapProps {
  mapRef: React.RefObject<HTMLDivElement | null>;
  loading: boolean;
  resultExists: boolean;
  error: string | null;
  onFitZona: () => void;
}

export function ImageExplorerMap({
  mapRef,
  loading,
  resultExists,
  error,
  onFitZona,
}: ImageExplorerMapProps) {
  return (
    <>
      {error && (
        <Alert color="red" icon={<IconAlertTriangle />} title="Error">
          {error}
        </Alert>
      )}
      <Card
        padding={0}
        radius="md"
        withBorder
        style={{ minHeight: 450, position: 'relative', flex: '1 1 auto' }}
      >
        <div
          ref={mapRef}
          data-testid="explorer-map-canvas"
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            borderRadius: 'var(--mantine-radius-md)',
          }}
        />
        <Button
          size="xs"
          variant="default"
          onClick={onFitZona}
          style={{ position: 'absolute', top: 10, left: 10 }}
        >
          Ver zona completa
        </Button>
        {loading && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'rgba(255,255,255,0.8)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 'var(--mantine-radius-md)',
            }}
          >
            <Stack align="center">
              <Loader size="lg" />
              <Text>Cargando imagen satelital...</Text>
            </Stack>
          </div>
        )}
        {!resultExists && !loading && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              pointerEvents: 'none',
            }}
          >
            <Paper
              p="lg"
              radius="md"
              shadow="sm"
              style={{ pointerEvents: 'auto', textAlign: 'center' }}
            >
              <IconSatellite size={32} style={{ opacity: 0.4, marginBottom: 8 }} />
              <Text c="dimmed" size="sm">
                Selecciona un dia con imagenes
              </Text>
              <Text c="dimmed" size="xs">
                del calendario para previsualizar
              </Text>
            </Paper>
          </div>
        )}
      </Card>
    </>
  );
}
