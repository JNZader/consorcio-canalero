/**
 * Shared test utilities.
 * Provides QueryClient wrapper for hooks that use @tanstack/react-query.
 */

import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

/**
 * Creates a fresh QueryClient configured for testing (no retries, no GC delay).
 */
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

/**
 * Wrapper factory for renderHook that provides a QueryClientProvider.
 * Usage: renderHook(() => useMyHook(), { wrapper: createQueryWrapper() })
 */
export function createQueryWrapper() {
  const queryClient = createTestQueryClient();
  return function QueryWrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  };
}
