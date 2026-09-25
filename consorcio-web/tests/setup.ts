/**
 * Vitest setup file
 * Configures testing environment and global mocks
 */

import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, vi } from 'vitest';

// Cleanup after each test
afterEach(() => {
  cleanup();
});

// Mock window.matchMedia
beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

// Mantine 9 Textarea autosize listens to FontFaceSet "loadingdone".
// happy-dom does not provide document.fonts. Prefer disabling autosize via
// NODE_ENV=test (patched getEnv); this mock is defense-in-depth for any path
// that still mounts Autosize.
beforeEach(() => {
  Object.defineProperty(document, 'fonts', {
    configurable: true,
    writable: true,
    value: {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      ready: Promise.resolve(),
    },
  });
});

// Mock ResizeObserver
beforeAll(() => {
  class ResizeObserverMock {
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();
  }

  global.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;
});

// Mock IntersectionObserver
beforeAll(() => {
  class IntersectionObserverMock {
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();
    root = null;
    rootMargin = '';
    thresholds: number[] = [];
  }

  global.IntersectionObserver = IntersectionObserverMock as unknown as typeof IntersectionObserver;
});

// Mock fetch globally
beforeAll(() => {
  global.fetch = vi.fn();
});

// Mock localStorage
beforeAll(() => {
  const localStorageMock = {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
    length: 0,
    key: vi.fn(),
  };
  Object.defineProperty(window, 'localStorage', {
    value: localStorageMock,
  });
});

// Mock scrollTo
beforeAll(() => {
  window.scrollTo = vi.fn();
});

// Mock navigator.geolocation
beforeAll(() => {
  const geolocationMock = {
    getCurrentPosition: vi.fn((success) =>
      success({
        coords: {
          latitude: -32.63,
          longitude: -62.68,
          accuracy: 100,
          altitude: null,
          altitudeAccuracy: null,
          heading: null,
          speed: null,
        },
        timestamp: Date.now(),
      })
    ),
    watchPosition: vi.fn(),
    clearWatch: vi.fn(),
  };
  Object.defineProperty(navigator, 'geolocation', {
    value: geolocationMock,
    writable: true,
  });
});

// Mock import.meta.env for Vite environment variables
beforeAll(() => {
  vi.stubGlobal('import', {
    meta: {
      env: {
        PUBLIC_API_URL: 'http://localhost:8000',
        DEV: true,
        PROD: false,
        MODE: 'test',
      },
    },
  });
});

// Suppress console errors during tests (optional, remove if you want to see them)
// beforeAll(() => {
//   vi.spyOn(console, 'error').mockImplementation(() => {});
// });
