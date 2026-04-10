import { Badge, Box, Button, Group, Paper, Skeleton, Stack, Text, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import type { ReactNode } from 'react';
import { IconCheck } from '../ui/icons';
import type { DrawnLineFeatureCollection } from '../map/LineDrawControl';

export function showSuggestionNotification(
  title: string,
  message: string,
  color: string,
  icon?: ReactNode
) {
  notifications.show({ title, message, color, icon });
}

export function getStepBackgroundColor(isComplete: boolean, isDisabled?: boolean): string {
  if (isComplete) return 'var(--mantine-color-green-6)';
  if (isDisabled) return 'var(--mantine-color-gray-4)';
  return 'var(--mantine-color-blue-6)';
}

export function getContactForRateLimit(email: string | null): { email?: string } {
  if (email) return { email };
  return {};
}

export function buildSugerenciaPayload(
  values: {
    titulo: string;
    descripcion: string;
    categoria: string;
  },
  userEmail: string | null,
  userName: string | null,
  geometry: DrawnLineFeatureCollection | null,
) {
  return {
    titulo: values.titulo,
    descripcion: values.descripcion,
    categoria: values.categoria || undefined,
    geometry: geometry ?? undefined,
    contacto_nombre: userName || undefined,
    contacto_email: userEmail || undefined,
    contacto_verificado: true,
  };
}

export function getStep2Badge(
  contactoVerificado: boolean,
  remainingToday: number | null
): ReactNode | undefined {
  if (!contactoVerificado) {
    return (
      <Badge color="gray" size="sm" variant="light">
        Verifica tu contacto primero
      </Badge>
    );
  }
  if (remainingToday === null) return undefined;
  return (
    <Badge color={remainingToday > 0 ? 'blue' : 'red'} size="sm" variant="light">
      {remainingToday} restantes hoy
    </Badge>
  );
}

export function SuccessScreen({
  remainingToday,
  onReset,
}: Readonly<{
  remainingToday: number | null;
  onReset: () => void;
}>) {
  const showRemainingBadge = remainingToday !== null && remainingToday > 0;

  return (
    <Paper shadow="md" p="xl" radius="md">
      <Stack align="center" gap="lg">
        <IconCheck size={64} color="var(--mantine-color-green-6)" />
        <Title order={2} ta="center">
          Gracias por tu sugerencia
        </Title>
        <Text c="gray.6" ta="center">
          Tu propuesta fue recibida y sera considerada en las proximas reuniones de la comision.
        </Text>
        {showRemainingBadge && (
          <Badge color="blue" size="lg">
            Puedes enviar {remainingToday} sugerencia{remainingToday > 1 ? 's' : ''} mas hoy
          </Badge>
        )}
        <Button onClick={onReset}>Enviar otra sugerencia</Button>
      </Stack>
    </Paper>
  );
}

export function GeometrySummary({
  geometry,
}: Readonly<{ geometry: DrawnLineFeatureCollection | null }>) {
  const features = geometry?.features ?? [];
  if (features.length === 0) {
    return (
      <Text size="xs" c="dimmed">
        Opcional: marcá un punto o dibujá una línea para indicar un canal faltante o una corrección.
      </Text>
    );
  }

  const points = features.filter((f) => f.geometry.type === 'Point').length;
  const lines = features.filter((f) => f.geometry.type === 'LineString').length;
  const parts: string[] = [];
  if (points > 0) parts.push(`${points} punto${points > 1 ? 's' : ''}`);
  if (lines > 0) parts.push(`${lines} línea${lines > 1 ? 's' : ''}`);

  return (
    <Badge color="blue" variant="light">
      {parts.join(' · ')}
    </Badge>
  );
}

export function FormFieldWithSkeleton({
  label,
  isVerified,
  skeletonHeight,
  children,
}: Readonly<{
  label: string;
  isVerified: boolean;
  skeletonHeight: number;
  children: ReactNode;
}>) {
  if (isVerified) {
    return <>{children}</>;
  }
  return (
    <Box>
      <Text size="sm" fw={500} mb="xs">
        {label}
      </Text>
      <Skeleton height={skeletonHeight} radius="sm" />
    </Box>
  );
}
