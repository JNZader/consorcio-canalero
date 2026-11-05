import {
  Alert,
  Card,
  Center,
  Group,
  Loader,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
} from '@mantine/core';
import type { ReactNode } from 'react';
import { EmptyState } from './EmptyState';

interface LoadingStateProps {
  readonly message?: string;
  readonly fullScreen?: boolean;
  readonly variant?: 'spinner' | 'skeleton';
  readonly skeletonCount?: number;
  /** `loading` es el default. `empty` y `error` unifican el resto del patrón. */
  readonly status?: 'loading' | 'empty' | 'error';
  readonly title?: string;
  readonly description?: string;
  readonly action?: ReactNode;
  readonly icon?: ReactNode;
  /** Loader en línea (tablas y secciones), sin la altura de página. */
  readonly compact?: boolean;
}

// Generate stable skeleton identifiers based on count (SonarQube S6479 - no array index in keys)
function getSkeletonIds(count: number): string[] {
  return Array.from({ length: count }, (_, i) => `loading-skeleton-${i + 1}`);
}

export function LoadingState({
  message = 'Cargando...',
  fullScreen = false,
  variant = 'spinner',
  skeletonCount = 4,
  status = 'loading',
  title,
  description,
  action,
  icon,
  compact = false,
}: LoadingStateProps) {
  if (status === 'empty') {
    return (
      <EmptyState icon={icon} title={title ?? message} description={description} action={action} />
    );
  }

  if (status === 'error') {
    return (
      <Alert color="red" variant="light" title={title} role="alert">
        <Text size="sm">{description ?? message}</Text>
        {action}
      </Alert>
    );
  }

  if (variant === 'skeleton') {
    const skeletonIds = getSkeletonIds(skeletonCount);
    return (
      <Stack gap="lg" role="status" aria-live="polite" aria-busy="true" aria-label={message}>
        <Skeleton height={40} width={200} />
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="lg">
          {skeletonIds.map((id) => (
            <Card key={id} padding="lg" radius="lg" withBorder>
              <Skeleton height={20} width="60%" mb="sm" />
              <Skeleton height={32} width="40%" mb="xs" />
              <Skeleton height={16} width="80%" />
            </Card>
          ))}
        </SimpleGrid>
      </Stack>
    );
  }

  if (compact) {
    return (
      <Center py="xl" role="status" aria-live="polite" aria-busy="true" aria-label={message}>
        <Group align="center">
          <Loader aria-hidden="true" />
          <Text size="sm" c="dimmed">
            {message}
          </Text>
        </Group>
      </Center>
    );
  }

  return (
    <Center
      h={fullScreen ? '100vh' : 400}
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={message}
    >
      <Stack align="center" gap="md">
        <Loader size="lg" type="dots" aria-hidden="true" />
        <Text c="gray.6" size="sm">
          {message}
        </Text>
      </Stack>
    </Center>
  );
}
