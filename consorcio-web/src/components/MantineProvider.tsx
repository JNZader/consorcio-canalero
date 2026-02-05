/**
 * MantineProvider - Wrapper for Mantine theme.
 *
 * Configures Mantine theme and global styles.
 * Includes QueryClientProvider for data caching.
 *
 * NOTE: For a unified wrapper with more options, see AppProvider.tsx
 */

import { MantineProvider as Provider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import { useEffect } from 'react';
import { sharedColorSchemeManager } from '../lib/mantine';
import { queryClient } from '../lib/query';
import { mantineTheme } from '../lib/theme';
import { useAuthStore } from '../stores/authStore';
// CSS centralizado - ver src/styles/mantine-imports.ts
import '../styles/mantine-imports';

interface Props {
  readonly children: React.ReactNode;
}

function AuthInitializer({ children }: { children: React.ReactNode }) {
  const initialize = useAuthStore((state) => state.initialize);

  useEffect(() => {
    initialize();
  }, [initialize]);

  return <>{children}</>;
}

export default function MantineProvider({ children }: Props) {
  return (
    <QueryClientProvider client={queryClient}>
      <Provider
        theme={mantineTheme}
        defaultColorScheme="auto"
        colorSchemeManager={sharedColorSchemeManager}
      >
        <Notifications position="top-right" zIndex={10002} />
        <AuthInitializer>{children}</AuthInitializer>
      </Provider>
    </QueryClientProvider>
  );
}

// Re-exportar el tema para uso externo
export { mantineTheme as theme } from '../lib/theme';
