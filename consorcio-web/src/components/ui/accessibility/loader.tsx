import { Box, Stack, Text } from '@mantine/core';
import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { useLiveRegion } from './liveRegion';

interface AccessibleLoaderProps {
  readonly loading: boolean;
  readonly loadingText?: string;
  readonly children: ReactNode;
  readonly announcement?: boolean;
}

export function AccessibleLoader({
  loading,
  loadingText = 'Cargando contenido',
  children,
  announcement = true,
}: AccessibleLoaderProps) {
  const { announce } = useLiveRegion();

  useEffect(() => {
    if (!announcement) return;
    if (loading) announce(loadingText);
    else announce('Contenido cargado');
  }, [loading, loadingText, announcement, announce]);

  if (loading) {
    return (
      <Box py="xl" aria-live="polite" aria-busy="true">
        <Stack align="center" gap="md">
          <Box
            style={{
              width: 40,
              height: 40,
              border: '3px solid var(--mantine-color-gray-3)',
              borderTopColor: 'var(--mantine-color-blue-6)',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite',
            }}
            aria-hidden="true"
          />
          <Text size="sm" c="gray.6">
            {loadingText}...
          </Text>
        </Stack>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </Box>
    );
  }

  return <>{children}</>;
}
