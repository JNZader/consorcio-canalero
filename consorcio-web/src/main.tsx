/**
 * Main entry point for the React SPA.
 *
 * All providers are consolidated here in a single React tree.
 */

import { MantineProvider } from '@mantine/core';
import { DatesProvider } from '@mantine/dates';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createRouter } from '@tanstack/react-router';
import dayjs from 'dayjs';
import 'dayjs/locale/es';
import { type ReactNode, StrictMode, useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { HelmetProvider } from 'react-helmet-async';

// Configure dayjs (used by @mantine/dates) with Spanish locale + Argentina
// timezone-friendly defaults so DatePickerInputs across the app render
// "Lunes / Martes / ..." and accept dd/mm/yyyy without per-component setup.
dayjs.locale('es');

import { UpdateBanner } from './components/UpdateBanner';
import { initLogtail } from './lib/logtail';
import { sharedColorSchemeManager } from './lib/mantine';
import { queryClient } from './lib/query';
import { initSentry } from './lib/sentry';
import { mantineTheme } from './lib/theme';
import { routeTree } from './routeTree.gen';
import { useAuthStore } from './stores/authStore';
import { useConfigStore } from './stores/configStore';

// Initialise observability as early as possible (before the router or
// any other module-load code can throw). Both are silent no-ops when
// the respective env vars are unset.
initSentry();
initLogtail();

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
          defaultColorScheme="auto"
          colorSchemeManager={sharedColorSchemeManager}
        >
          <DatesProvider settings={{ locale: 'es', firstDayOfWeek: 1 }}>
            <Notifications position="top-right" zIndex={10002} />
            <UpdateBanner />
            <AuthInitializer>
              <RouterProvider router={router} />
            </AuthInitializer>
          </DatesProvider>
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
