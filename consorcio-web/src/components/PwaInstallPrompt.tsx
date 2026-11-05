import { Button, Group, Paper, Text } from '@mantine/core';
import { useSyncExternalStore } from 'react';

import {
  dismissPwaInstall,
  getPwaInstallSnapshot,
  isStandaloneDisplay,
  runPwaInstallPrompt,
  subscribePwaInstall,
} from '../lib/pwaInstall';
import { Z_INDEX } from '../lib/zIndex';
import { IconDownload, IconX } from './ui/icons';

function useInstallUi(): { available: boolean; dismissed: boolean } {
  const snapshot = useSyncExternalStore(subscribePwaInstall, getPwaInstallSnapshot, () => '0:1');
  const [available, dismissed] = snapshot.split(':');
  return { available: available === '1', dismissed: dismissed === '1' };
}

/**
 * Ítem de menú. No es un aviso: solo aparece si el navegador ofreció
 * instalar y todavía no se llamó `prompt()`.
 */
export function PwaInstallMenuButton({
  onDone,
  fullWidth = false,
}: {
  readonly onDone?: () => void;
  readonly fullWidth?: boolean;
}) {
  const { available } = useInstallUi();
  if (!available || isStandaloneDisplay()) return null;

  return (
    <Button
      variant="subtle"
      fullWidth={fullWidth}
      justify="flex-start"
      leftSection={<IconDownload size={16} />}
      data-testid="pwa-install-menu"
      onClick={() => {
        void runPwaInstallPrompt();
        onDone?.();
      }}
    >
      Instalar aplicación
    </Button>
  );
}

/**
 * Aviso chico, una sola vez por navegador. Descartarlo no vuelve a mostrarlo;
 * la instalación sigue disponible en el menú mientras el evento viva.
 */
export function PwaInstallPrompt() {
  const { available, dismissed } = useInstallUi();
  if (!available || dismissed || isStandaloneDisplay()) return null;

  return (
    <Paper
      shadow="md"
      radius="md"
      p="sm"
      withBorder
      role="region"
      aria-label="Instalar la aplicación"
      data-testid="pwa-install-banner"
      style={{
        position: 'fixed',
        top: 'max(8px, env(safe-area-inset-top, 0px))',
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: Z_INDEX.popover,
        width: 'min(420px, calc(100vw - 24px))',
        background: 'light-dark(var(--mantine-color-white), var(--mantine-color-dark-6))',
      }}
    >
      <Group justify="space-between" wrap="nowrap" gap="xs" align="center">
        <Text size="sm" style={{ flex: 1, minWidth: 0 }}>
          Instalá la aplicación para abrirla desde el inicio.
        </Text>
        <Button
          size="compact-sm"
          data-testid="pwa-install-action"
          onClick={() => void runPwaInstallPrompt()}
        >
          Instalar
        </Button>
        <Button
          variant="subtle"
          color="gray"
          size="compact-sm"
          px={8}
          aria-label="Cerrar aviso de instalación"
          data-testid="pwa-install-dismiss"
          onClick={() => dismissPwaInstall()}
        >
          <IconX size={16} />
        </Button>
      </Group>
    </Paper>
  );
}
