/**
 * Main entry point for the React SPA.
 *
 * All providers are consolidated here in a single React tree.
 */

import React, { useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { RouterProvider, createRouter } from '@tanstack/react-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { HelmetProvider } from 'react-helmet-async';

import { routeTree } from './routeTree.gen';
import { queryClient } from './lib/query';
import { mantineTheme } from './lib/theme';
import { sharedColorSchemeManager } from './lib/mantine';
import { useAuthStore } from './stores/authStore';
import { useConfigStore } from './stores/configStore';

// Global styles
import './styles/global.css';
import './styles/mantine-imports';

// Create the router instance
const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
  defaultPreloadStaleTime: 30_000,
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
