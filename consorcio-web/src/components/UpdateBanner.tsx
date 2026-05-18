/**
 * UpdateBanner — bottom-center banner that appears when ``useVersionCheck``
 * detects a newer deployment. Click "Actualizar" → hard reload.
 *
 * Lives outside the router so it survives navigation between routes.
 * Renders absolutely-positioned via Portal so it sits above MapLibre
 * controls and dropdowns (z-index 10001, below Mantine notifications at
 * 10002 to stay polite about stacking).
 */
import { Button, Group, Paper, Portal, Text } from '@mantine/core';
import { memo } from 'react';

import { useVersionCheck } from '../hooks/useVersionCheck';

function UpdateBannerImpl() {
  const { updateAvailable, reload } = useVersionCheck();
  if (!updateAvailable) return null;
  return (
    <Portal>
      <Paper
        shadow="lg"
        radius="md"
        p="md"
        withBorder
        role="alert"
        aria-live="polite"
        data-testid="update-banner"
        style={{
          position: 'fixed',
          bottom: 24,
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 10001,
          minWidth: 320,
          maxWidth: 'calc(100vw - 32px)',
          background: 'light-dark(var(--mantine-color-white), var(--mantine-color-dark-6))',
          borderLeft: '4px solid var(--mantine-color-acento-5)',
        }}
      >
        <Group justify="space-between" wrap="nowrap" gap="md">
          <Text size="sm" fw={500}>
            Nueva versión disponible — recargá para actualizar.
          </Text>
          <Button size="xs" color="acento" c="dark.9" onClick={reload}>
            Actualizar
          </Button>
        </Group>
      </Paper>
    </Portal>
  );
}

export const UpdateBanner = memo(UpdateBannerImpl);
