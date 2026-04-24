/**
 * Main entry point for the React SPA.
 *
 * All providers are consolidated here in a single React tree.
 */

import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createRouter } from '@tanstack/react-router';
import React, { useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { HelmetProvider } from 'react-helmet-async';

import { sharedColorSchemeManager } from './lib/mantine';
import { queryClient } from './lib/query';
import { mantineTheme } from './lib/theme';
import { routeTree } from './routeTree.gen';
import { useAuthStore } from './stores/authStore';
import { useConfigStore } from './stores/configStore';

// Mantine styles first, then global overrides.
import './styles/mantine-imports';
import './styles/global.css';

// Create the router instance
const basepath = import.meta.env.BASE_URL.replace(/\/$/, '') || '/';

const router = createRouter({
  routeTree,
  basepath,
  defaultPreload: 'intent',
  defaultPreloadStaleTime: 30_000,
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

globalThis.addEventListener('unhandledrejection', (event) => {
  if (!isChunkLoadError(event.reason)) return;

  const alreadyReloaded = sessionStorage.getItem(CHUNK_RELOAD_GUARD) === '1';
  if (alreadyReloaded) return;

  sessionStorage.setItem(CHUNK_RELOAD_GUARD, '1');
  globalThis.location.reload();
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
function AuthInitializer({ children }: { children: React.ReactNode }) {
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
          defaultColorScheme="auto"
          colorSchemeManager={sharedColorSchemeManager}
        >
          <Notifications position="top-right" zIndex={10002} />
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
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
