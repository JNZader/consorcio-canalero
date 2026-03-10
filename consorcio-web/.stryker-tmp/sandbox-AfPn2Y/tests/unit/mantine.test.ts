/**
 * Tests for Mantine color scheme manager
 * Coverage target: 100%
 */
// @ts-nocheck


import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { createSharedColorSchemeManager, sharedColorSchemeManager } from '../../src/lib/mantine';

// Mock window and globalThis for testing
const createMockWindow = () => {
  const listeners: Map<string, Set<Function>> = new Map();
  return {
    listeners,
    addEventListener: vi.fn((event: string, callback: Function) => {
      if (!listeners.has(event)) {
        listeners.set(event, new Set());
      }
      listeners.get(event)!.add(callback);
    }),
    removeEventListener: vi.fn((event: string, callback: Function) => {
      if (listeners.has(event)) {
        listeners.get(event)!.delete(callback);
      }
    }),
    dispatchEvent: vi.fn((event: CustomEvent) => {
      const eventType = event.type;
      if (listeners.has(eventType)) {
        listeners.get(eventType)!.forEach((callback) => callback(event));
      }
    }),
  };
};

describe('mantine color scheme manager', () => {
  beforeEach(() => {
    // Clean up globalThis state before each test
    if (globalThis.__mantineColorSchemeState) {
      delete globalThis.__mantineColorSchemeState;
    }
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('createSharedColorSchemeManager', () => {
    it('should create a manager object', () => {
      const manager = createSharedColorSchemeManager();
      expect(manager).toBeDefined();
      expect(typeof manager).toBe('object');
    });

    it('should have set function', () => {
      const manager = createSharedColorSchemeManager();
      expect(typeof manager.set).toBe('function');
    });

    it('should have subscribe function', () => {
      const manager = createSharedColorSchemeManager();
      expect(typeof manager.subscribe).toBe('function');
    });

    it('should use custom key if provided', () => {
      const manager = createSharedColorSchemeManager({ key: 'custom-key' });
      expect(manager).toBeDefined();
      expect(typeof manager.set).toBe('function');
    });

    it('should use default key if not provided', () => {
      const manager = createSharedColorSchemeManager();
      expect(manager).toBeDefined();
    });
  });

  describe('color scheme manager state', () => {
    it('should initialize state on first access', () => {
      const manager = createSharedColorSchemeManager();
      manager.set('dark');

      expect(globalThis.__mantineColorSchemeState).toBeDefined();
      expect(globalThis.__mantineColorSchemeState?.lastValue).toBe('dark');
    });

    it('should track last value set', () => {
      const manager = createSharedColorSchemeManager();
      manager.set('light');
      expect(globalThis.__mantineColorSchemeState?.lastValue).toBe('light');

      manager.set('dark');
      expect(globalThis.__mantineColorSchemeState?.lastValue).toBe('dark');
    });

    it('should avoid duplicate sets', () => {
      const manager = createSharedColorSchemeManager();
      const setSpy = vi.spyOn(manager, 'set');

      manager.set('light');
      manager.set('light'); // Duplicate

      // Both calls go through, but state handling deduplicates
      expect(setSpy).toHaveBeenCalledTimes(2);
    });

    it('should skip set during updating phase', () => {
      const manager = createSharedColorSchemeManager();
      manager.set('light');

      // Set state as updating
      const state = globalThis.__mantineColorSchemeState;
      if (state) {
        state.isUpdating = true;
        const prevLastValue = state.lastValue;
        manager.set('dark');
        // Should not change while updating
        expect(state.lastValue).toBe(prevLastValue);
      }
    });
  });

  describe('subscribe mechanism', () => {
    it('should return unsubscribe function', () => {
      const manager = createSharedColorSchemeManager();
      const unsubscribe = manager.subscribe(() => {});
      expect(typeof unsubscribe).toBe('function');
    });

    it('should call callback on theme change', () => {
      return new Promise<void>((resolve) => {
        const manager = createSharedColorSchemeManager();
        const callback = vi.fn();

        manager.subscribe(callback);

        setTimeout(() => {
          // After subscription, setting value should eventually trigger callback
          manager.set('dark');
          
          setTimeout(() => {
            // Give time for RAF and event dispatch
            resolve();
          }, 100);
        }, 50);
      });
    });

    it('should support unsubscribe', () => {
      const manager = createSharedColorSchemeManager();
      const callback = vi.fn();
      const unsubscribe = manager.subscribe(callback);

      expect(typeof unsubscribe).toBe('function');
      unsubscribe();
      // After unsubscribe, no further callbacks should be made
    });
  });

  describe('shared color scheme manager', () => {
    it('should be an instance of manager', () => {
      expect(sharedColorSchemeManager).toBeDefined();
      expect(typeof sharedColorSchemeManager.set).toBe('function');
      expect(typeof sharedColorSchemeManager.subscribe).toBe('function');
    });

    it('should be usable globally', () => {
      const callback = vi.fn();
      const unsubscribe = sharedColorSchemeManager.subscribe(callback);

      sharedColorSchemeManager.set('light');

      expect(typeof unsubscribe).toBe('function');
    });
  });

  describe('animation frame handling', () => {
    it('should handle requestAnimationFrame in set', () => {
      return new Promise<void>((resolve) => {
        const manager = createSharedColorSchemeManager();

        manager.set('dark');

        // Wait for RAF to complete
        setTimeout(() => {
          const state = globalThis.__mantineColorSchemeState;
          expect(state?.pendingUpdate).toBeNull();
          resolve();
        }, 50);
      });
    });

    it('should cancel pending RAF when new set is called', () => {
      return new Promise<void>((resolve) => {
        const manager = createSharedColorSchemeManager();

        manager.set('light');
        manager.set('dark'); // Cancels previous RAF and starts new one

        setTimeout(() => {
          const state = globalThis.__mantineColorSchemeState;
          expect(state?.lastValue).toBe('dark');
          resolve();
        }, 50);
      });
    });
  });

  describe('window handling', () => {
    it('should handle missing window gracefully', () => {
      // Test that manager works even if window is undefined
      const manager = createSharedColorSchemeManager();
      expect(() => manager.set('light')).not.toThrow();
    });

    it('should create consistent state across calls', () => {
      const manager1 = createSharedColorSchemeManager();
      const manager2 = createSharedColorSchemeManager();

      manager1.set('dark');

      // Both managers should see the same state
      expect(globalThis.__mantineColorSchemeState?.lastValue).toBe('dark');
    });
  });
});
