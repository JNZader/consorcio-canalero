import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PwaInstallMenuButton, PwaInstallPrompt } from '../../src/components/PwaInstallPrompt';
import {
  type BeforeInstallPromptEvent,
  captureInstallPrompt,
  dismissPwaInstall,
  resetPwaInstallForTests,
  runPwaInstallPrompt,
} from '../../src/lib/pwaInstall';

function event(): BeforeInstallPromptEvent {
  return {
    preventDefault: vi.fn(),
    prompt: vi.fn(async () => undefined),
    userChoice: Promise.resolve({ outcome: 'accepted' as const }),
  } as unknown as BeforeInstallPromptEvent;
}

describe('pwa install prompt', () => {
  beforeEach(() => {
    resetPwaInstallForTests();
    localStorage.clear();
  });

  it('guarda el evento y llama prompt() una sola vez', async () => {
    const first = event();
    captureInstallPrompt(first);
    expect(first.preventDefault).toHaveBeenCalledOnce();

    await runPwaInstallPrompt();
    await runPwaInstallPrompt();
    expect(first.prompt).toHaveBeenCalledOnce();

    const second = event();
    captureInstallPrompt(second);
    await runPwaInstallPrompt();
    expect(second.prompt).not.toHaveBeenCalled();
  });

  it('muestra un aviso descartable y no lo vuelve a mostrar', async () => {
    const user = userEvent.setup();
    captureInstallPrompt(event());
    const view = render(
      <MantineProvider env="test">
        <PwaInstallPrompt />
        <PwaInstallMenuButton />
      </MantineProvider>
    );

    expect(screen.getByTestId('pwa-install-banner')).toBeInTheDocument();
    expect(screen.getByTestId('pwa-install-menu')).toBeInTheDocument();

    await user.click(screen.getByTestId('pwa-install-dismiss'));
    expect(screen.queryByTestId('pwa-install-banner')).not.toBeInTheDocument();
    expect(screen.getByTestId('pwa-install-menu')).toBeInTheDocument();
    expect(localStorage.setItem).toHaveBeenCalledWith('cc-pwa-install-dismissed', '1');

    view.unmount();
    dismissPwaInstall();
    render(
      <MantineProvider env="test">
        <PwaInstallPrompt />
      </MantineProvider>
    );
    expect(screen.queryByTestId('pwa-install-banner')).not.toBeInTheDocument();
  });

  it('el botón Instalar consume el evento', async () => {
    const user = userEvent.setup();
    const deferred = event();
    captureInstallPrompt(deferred);
    render(
      <MantineProvider env="test">
        <PwaInstallPrompt />
      </MantineProvider>
    );
    await user.click(screen.getByTestId('pwa-install-action'));
    expect(deferred.prompt).toHaveBeenCalledOnce();
    expect(screen.queryByTestId('pwa-install-banner')).not.toBeInTheDocument();
  });
});
