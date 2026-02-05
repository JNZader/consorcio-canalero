import { Card, Center, Loader, SimpleGrid, Skeleton, Stack, Text } from '@mantine/core';

interface LoadingStateProps {
  readonly message?: string;
  readonly fullScreen?: boolean;
  readonly variant?: 'spinner' | 'skeleton';
  readonly skeletonCount?: number;
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
}: LoadingStateProps) {
  if (variant === 'skeleton') {
    const skeletonIds = getSkeletonIds(skeletonCount);
    return (
      <Stack gap="lg" aria-live="polite" aria-busy="true" aria-label={message}>
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

  return (
    <Center h={fullScreen ? '100vh' : 400} aria-live="polite" aria-busy="true" aria-label={message}>
      <Stack align="center" gap="md">
        <Loader size="lg" type="dots" aria-hidden="true" />
        <Text c="gray.6" size="sm">
          {message}
        </Text>
      </Stack>
    </Center>
  );
}
