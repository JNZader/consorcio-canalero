import { type MantineColorSchemeManager, localStorageColorSchemeManager } from '@mantine/core';

// Extender globalThis para el estado compartido del tema
declare global {
  var __mantineColorSchemeState: {
    lastValue: string | null;
    pendingUpdate: number | null;
    isUpdating: boolean;
  } | undefined;
}

/**
 * Custom color scheme manager with optimized state sharing.
 *
 * Uses window to share state across components.
 * Avoids unnecessary re-renders through event deduplication.
 */
export function createSharedColorSchemeManager({
  key = 'mantine-color-scheme-value',
} = {}): MantineColorSchemeManager {
  const manager = localStorageColorSchemeManager({ key });

  // Estado compartido via globalThis para evitar duplicados entre bundles
  const getState = () => {
    if (globalThis.window === undefined) {
      return { lastValue: null, pendingUpdate: null, isUpdating: false };
    }
    // Use nullish coalescing assignment (S6606)
    globalThis.__mantineColorSchemeState ??= {
      lastValue: null,
      pendingUpdate: null,
      isUpdating: false,
    };
    return globalThis.__mantineColorSchemeState;
  };

  return {
    ...manager,
    set: (value) => {
      const state = getState();

      // Evitar sets duplicados o durante actualizacion
      if (state.lastValue === value || state.isUpdating) return;
      state.lastValue = value;

      manager.set(value);

      // Usar requestAnimationFrame para agrupar actualizaciones
      if (globalThis.window !== undefined) {
        if (state.pendingUpdate) {
          cancelAnimationFrame(state.pendingUpdate);
        }
        state.pendingUpdate = requestAnimationFrame(() => {
          state.isUpdating = true;
          globalThis.dispatchEvent(new CustomEvent('mantine-color-scheme-change', { detail: value }));
          state.isUpdating = false;
          state.pendingUpdate = null;
        });
      }
    },
    subscribe: (onUpdate) => {
      // Note: manager.subscribe returns void in Mantine, not an unsubscribe function
      manager.subscribe(onUpdate);
      const state = getState();

      const handleCustomEvent = (event: CustomEvent) => {
        // Solo actualizar si el valor realmente cambio
        if (event.detail !== state.lastValue) {
          state.lastValue = event.detail;
          onUpdate(event.detail);
        }
      };

      if (globalThis.window !== undefined) {
        globalThis.addEventListener('mantine-color-scheme-change', handleCustomEvent as EventListener);
      }

      return () => {
        if (globalThis.window !== undefined) {
          globalThis.removeEventListener(
            'mantine-color-scheme-change',
            handleCustomEvent as EventListener
          );
        }
      };
    },
  };
}

export const sharedColorSchemeManager = createSharedColorSchemeManager();
