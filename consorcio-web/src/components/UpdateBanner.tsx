// eslint-disable-next-line import/no-unresolved -- virtual module from vite-plugin-pwa
import { useRegisterSW } from 'virtual:pwa-register/react';
/**
 * UpdateBanner — bottom-center banner shown when a new deploy is detected.
 *
 * Hybrid update strategy:
 *
 *   - ``useVersionCheck`` polls ``/version.json`` every 5 minutes (and on
 *     tab focus) so we notice a new deploy quickly. This is the
 *     "trigger": when it sees a SHA that differs from the one this tab
 *     was loaded with, we know a deploy happened.
 *
 *   - ``useRegisterSW`` (from ``virtual:pwa-register/react``) drives the
 *     actual service-worker lifecycle. When the trigger fires we ask the
 *     registration to ``update()``, and the click on "Actualizar" calls
 *     ``updateServiceWorker(true)`` — the officially-supported one-liner
 *     that posts ``SKIP_WAITING``, waits for ``controllerchange`` and
 *     reloads the page. That replaces the hand-rolled ``forceUpdate``
 *     that left some users still needing Ctrl+Shift+R.
 *
 *   - Either source of truth can flip the banner on: the SW's own
 *     ``needRefresh`` (when the precache manifest changes) OR our
 *     external version-check.
 *
 * Rendered once at the app root (next to ``<Notifications>``).
 */
import { ActionIcon, Button, Group, Paper, Portal, Text } from '@mantine/core';
import { useEffect, useState } from 'react';

import { useVersionCheck } from '../hooks/useVersionCheck';
import { logger } from '../lib/logger';

const SW_UPDATE_POLL_MS = 60 * 1000; // 1 minute

export function UpdateBanner() {
  const { updateAvailable, latestSha } = useVersionCheck();
  // Tracks the click → reload window. Without this the button has no
  // affordance during the ~1–3 s SKIP_WAITING + controllerchange dance
  // and the user thinks it's broken before the page actually reloads.
  const [isUpdating, setIsUpdating] = useState(false);
  // Dismiss per deploy: without it the banner covers map/panel content with
  // no way out other than updating right now. Stores the dismissed SHA (not a
  // boolean) so a NEWER deploy landing later in this tab re-arms the banner.
  const [dismissedSha, setDismissedSha] = useState<string | null>(null);
  const dismissed = dismissedSha !== null && dismissedSha === (latestSha ?? dismissedSha);
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_swUrl, registration) {
      // Periodic background check for a fresher ``sw.js``. Without this
      // the browser may not probe for a new SW until the user navigates,
      // which can be hours after a deploy.
      if (registration) {
        setInterval(() => {
          registration
            .update()
            .catch((err) => logger.debug('[update-banner] periodic SW update failed', err));
        }, SW_UPDATE_POLL_MS);
      }
    },
    onRegisterError(error) {
      logger.warn('[update-banner] service worker register error', error);
    },
  });

  // When our external version-check sees a new deploy, ask the SW to
  // re-check immediately so ``updateServiceWorker(true)`` has a waiting
  // SW to activate when the user clicks.
  useEffect(() => {
    if (!updateAvailable) return;
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
    navigator.serviceWorker
      .getRegistration()
      .then((r) => r?.update())
      .catch((err) => logger.debug('[update-banner] reg.update() failed', err));
  }, [updateAvailable]);

  const shouldShow = (needRefresh || updateAvailable) && !dismissed;
  if (!shouldShow) return null;

  return (
    <Portal>
      <Paper
        shadow="lg"
        radius="md"
        p="sm"
        withBorder
        role="alert"
        aria-live="polite"
        data-testid="update-banner"
        style={{
          // ``position: fixed`` + ``bottom`` + a translate-anchored centre
          // works fine on desktop, but on phones the safe-area inset eats
          // bottom space (especially in PWA-installed mode), so we anchor
          // a few extra pixels up and let the maxWidth shrink with the
          // viewport so the banner never overflows.
          position: 'fixed',
          bottom: 'max(16px, env(safe-area-inset-bottom, 0px) + 16px)',
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 10001,
          width: 'min(440px, calc(100vw - 24px))',
          background: 'light-dark(var(--mantine-color-white), var(--mantine-color-dark-6))',
          borderLeft: '4px solid var(--mantine-color-acento-5)',
        }}
      >
        <Group justify="space-between" wrap="nowrap" gap="xs" align="center">
          <Text size="sm" fw={500} style={{ flex: 1, minWidth: 0 }}>
            {isUpdating ? 'Actualizando…' : 'Nueva versión disponible'}
          </Text>
          <Button
            size="compact-sm"
            color="acento"
            c="dark.9"
            loading={isUpdating}
            disabled={isUpdating}
            onClick={() => {
              setIsUpdating(true);
              // Reset the SW's needRefresh flag so the banner closes
              // immediately while ``updateServiceWorker`` does its
              // skipWaiting + controllerchange + reload dance.
              setNeedRefresh(false);
              updateServiceWorker(true).catch((err) => {
                logger.warn('[update-banner] updateServiceWorker failed', err);
                // Fall back to a plain reload — better than leaving the
                // user stuck on a perpetually-loading button.
                window.location.reload();
              });
            }}
          >
            {isUpdating ? 'Actualizando' : 'Actualizar'}
          </Button>
          <ActionIcon
            variant="subtle"
            color="gray"
            size="sm"
            aria-label="Cerrar aviso de actualización"
            disabled={isUpdating}
            onClick={() => setDismissedSha(latestSha ?? 'sw-refresh')}
          >
            ✕
          </ActionIcon>
        </Group>
      </Paper>
    </Portal>
  );
}
