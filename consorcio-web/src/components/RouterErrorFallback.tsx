import { Alert, Button, Container, Group, Paper, Stack, Text } from '@mantine/core';
import { Link } from '@tanstack/react-router';
import { erroresUi } from '../lib/userFacingError';

export interface RouterErrorFallbackProps {
  readonly error?: unknown;
  readonly reset?: () => void;
}

export function RouterErrorFallback({ error, reset }: RouterErrorFallbackProps) {
  return (
    <Container size="sm" py="xl">
      <Paper shadow="md" p="xl" radius="md" withBorder role="alert">
        <Stack gap="md">
          <Alert color="alerta" title={erroresUi.seccion.titulo} variant="light">
            <Text size="sm">{erroresUi.seccion.detalle}</Text>
          </Alert>

          {import.meta.env.DEV && error instanceof Error && (
            <Text size="xs" c="dimmed" ff="monospace" style={{ wordBreak: 'break-all' }}>
              {error.message}
            </Text>
          )}

          <Group justify="flex-start" mt="sm">
            {reset && (
              <Button onClick={() => reset()} variant="light" color="alerta">
                Reintentar
              </Button>
            )}
            <Button component={Link} to="/" variant="subtle">
              Volver al inicio
            </Button>
          </Group>
        </Stack>
      </Paper>
    </Container>
  );
}
