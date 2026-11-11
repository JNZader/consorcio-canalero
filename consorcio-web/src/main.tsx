/**
 * Main entry point for the React SPA.
 *
 * All providers are consolidated here in a single React tree.
 */

import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import { createRouter, RouterProvider } from '@tanstack/react-router';
import { type ReactNode, StrictMode, useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { HelmetProvider } from 'react-helmet-async';

import { PwaInstallPrompt } from './components/PwaInstallPrompt';
import { UpdateBanner } from './components/UpdateBanner';
import { bootBrandFromStorage } from './lib/applyBrand';
import { sharedColorSchemeManager } from './lib/mantine';
import { installPwaPromptListener } from './lib/pwaInstall';
import { queryClient } from './lib/query';
import { cssVariablesResolver, mantineTheme } from './lib/theme';
import { Z_INDEX } from './lib/zIndex';
import { routeTree } from './routeTree.gen';
import { useAuthStore } from './stores/authStore';
import { useConfigStore } from './stores/configStore';

// Restore Theme Lab brand before first paint (localStorage preview only).
bootBrandFromStorage();

// Observability leaves the entry graph. Errors thrown before the idle
// callback are not captured; that is the tradeoff for a lighter first paint.
function scheduleIdle(task: () => void): void {
  if (typeof requestIdleCallback === 'function') {
    requestIdleCallback(() => task());
    return;
  }
  setTimeout(task, 1);
}

scheduleIdle(() => {
  void import('./lib/sentry').then((mod) => mod.initSentry());
  void import('./lib/logtail').then((mod) => mod.initLogtail());
});

installPwaPromptListener();

// Mantine styles first, then global overrides.
import './styles/mantine-imports';
import { RouterErrorFallback } from './components/RouterErrorFallback';
import './styles/global.css';

// Create the router instance
const basepath = import.meta.env.BASE_URL.replace(/\/$/, '') || '/';

const router = createRouter({
  routeTree,
  basepath,
  defaultPreload: 'intent',
  defaultPreloadStaleTime: 30_000,
  defaultErrorComponent: RouterErrorFallback,
});

// Recover once from stale lazy-chunk errors after a new deploy.
const CHUNK_RELOAD_GUARD = 'cc-chunk-reload-once';

function isChunkLoadError(reason: unknown): boolean {
  const message =
    typeof reason === 'string'
      ? reason
      : reason instanceof Error
        ? reason.message
        : typeof reason === 'object' && reason && 'message' in reason
          ? String((reason as { message?: unknown }).message)
          : '';

  return /dynamically imported module|module script failed|chunk/i.test(message);
}

function reloadOnceForStaleChunk(): void {
  if (sessionStorage.getItem(CHUNK_RELOAD_GUARD) === '1') return;
  sessionStorage.setItem(CHUNK_RELOAD_GUARD, '1');
  globalThis.location.reload();
}

globalThis.addEventListener('unhandledrejection', (event) => {
  if (!isChunkLoadError(event.reason)) return;
  reloadOnceForStaleChunk();
});

globalThis.addEventListener('vite:preloadError', (event) => {
  event.preventDefault();
  reloadOnceForStaleChunk();
});

globalThis.addEventListener('load', () => {
  sessionStorage.removeItem(CHUNK_RELOAD_GUARD);
});

// Prefetch system config on app init
useConfigStore.getState().fetchConfig();

// Register the router for type safety
declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

/**
 * Component that initializes authentication on app mount.
 */
function AuthInitializer({ children }: { children: ReactNode }) {
  const initialize = useAuthStore((state) => state.initialize);

  useEffect(() => {
    initialize();
  }, [initialize]);

  return <>{children}</>;
}

/**
 * Root application component with all providers.
 */
function App() {
  return (
    <HelmetProvider>
      <QueryClientProvider client={queryClient}>
        <MantineProvider
          theme={mantineTheme}
          cssVariablesResolver={cssVariablesResolver}
          defaultColorScheme="auto"
          colorSchemeManager={sharedColorSchemeManager}
        >
          <Notifications position="top-right" zIndex={Z_INDEX.toast} />
          <PwaInstallPrompt />
          <UpdateBanner />
          <AuthInitializer>
            <RouterProvider router={router} />
          </AuthInitializer>
        </MantineProvider>
      </QueryClientProvider>
    </HelmetProvider>
  );
}

// Mount the application
ReactDOM.createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
