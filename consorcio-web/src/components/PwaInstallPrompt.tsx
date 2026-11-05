import { Button, Group, Paper, Text } from '@mantine/core';
import { useEffect, useSyncExternalStore } from 'react';

import {
  dismissPwaInstall,
  getPwaInstallSnapshot,
  isStandaloneDisplay,
  runPwaInstallPrompt,
  subscribePwaInstall,
} from '../lib/pwaInstall';
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
 * Barra inferior, una sola vez por navegador. Descartarla no vuelve a
 * mostrarla; la instalación sigue en el menú mientras el evento viva.
 * Va abajo, con el safe area, para no tapar Inicio / Mapa / Participación.
 */
export function PwaInstallPrompt() {
  const { available, dismissed } = useInstallUi();
  const visible = available && !dismissed && !isStandaloneDisplay();

  useEffect(() => {
    if (!visible) return;
    const root = document.documentElement;
    root.style.setProperty('--cc-install-bar', 'calc(4rem + env(safe-area-inset-bottom, 0px))');
    root.style.setProperty(
      '--cc-install-offset',
      'calc(4rem + env(safe-area-inset-bottom, 0px) + 12px)'
    );
    return () => {
      root.style.removeProperty('--cc-install-bar');
      root.style.removeProperty('--cc-install-offset');
    };
  }, [visible]);

  if (!visible) return null;

  return (
    <Paper
      py="xs"
      px="md"
      radius={0}
      role="region"
      aria-label="Instalar la aplicación"
      data-testid="pwa-install-banner"
      className="cc-install-bar"
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
