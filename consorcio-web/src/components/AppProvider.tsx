/**
 * AppProvider - Unified wrapper for MantineProvider.
 *
 * This component is the single entry point for Mantine in the application.
 * Consolidates theme configuration and avoids provider duplication.
 *
 * Components that use Mantine should export their internal content
 * (e.g., HeaderContent) without MantineProvider.
 */

import { MantineProvider as Provider } from '@mantine/core';
import { notifications, Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import { useCallback, useEffect } from 'react';
import { sharedColorSchemeManager } from '../lib/mantine';
import { queryClient } from '../lib/query';
import { mantineTheme } from '../lib/theme';
import { useAuthStore } from '../stores/authStore';
import { useConfigStore } from '../stores/configStore';
// CSS centralizado - ver src/styles/mantine-imports.ts
import '../styles/mantine-imports';

// ===========================================
// INITIALIZERS
// ===========================================

function AuthInitializer({ children }: { children: React.ReactNode }) {
  const initialize = useAuthStore((state) => state.initialize);

  useEffect(() => {
    initialize();
  }, [initialize]);

  return <>{children}</>;
}

function ConfigInitializer({ children }: { children: React.ReactNode }) {
  const fetchConfig = useConfigStore((state) => state.fetchConfig);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  return <>{children}</>;
}

function AuthExpiredHandler({ children }: { children: React.ReactNode }) {
  const reset = useAuthStore((state) => state.reset);

  const handleExpired = useCallback(() => {
    reset();
    notifications.show({
      title: 'Sesion expirada',
      message: 'Tu sesion ha expirado. Por favor inicia sesion nuevamente.',
      color: 'red',
      autoClose: 5000,
    });
    // Redirect to login after a brief delay for the toast to show
    setTimeout(() => {
      window.location.href = '/login';
    }, 1500);
  }, [reset]);

  useEffect(() => {
    window.addEventListener('auth:expired', handleExpired);
    return () => window.removeEventListener('auth:expired', handleExpired);
  }, [handleExpired]);

  return <>{children}</>;
}

// ===========================================
// COMPONENTE PRINCIPAL
// ===========================================

interface AppProviderProps {
  readonly children: React.ReactNode;
  /**
   * Si es true, incluye QueryClientProvider para caching de datos.
   * Default: true
   */
  readonly withQuery?: boolean;
}

/**
 * AppProvider - Wrapper consolidado para Mantine y TanStack Query.
 *
 * Uso basico:
 * ```tsx
 * <AppProvider>
 *   <MyComponent />
 * </AppProvider>
 * ```
 *
 * Sin Query (para componentes que no necesitan data fetching):
 * ```tsx
 * <AppProvider withQuery={false}>
 *   <MyComponent />
 * </AppProvider>
 * ```
 */
export default function AppProvider({ children, withQuery = true }: AppProviderProps) {
  const content = (
    <Provider
      theme={mantineTheme}
      defaultColorScheme="auto"
      colorSchemeManager={sharedColorSchemeManager}
    >
      <Notifications position="top-right" zIndex={10002} />
      <ConfigInitializer>
        <AuthInitializer>
          <AuthExpiredHandler>{children}</AuthExpiredHandler>
        </AuthInitializer>
      </ConfigInitializer>
    </Provider>
  );

  if (withQuery) {
    return <QueryClientProvider client={queryClient}>{content}</QueryClientProvider>;
  }

  return content;
}

// Re-exportar el tema para uso externo si es necesario
export { mantineTheme as theme } from '../lib/theme';
