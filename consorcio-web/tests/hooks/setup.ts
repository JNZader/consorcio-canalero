/**
 * Hooks test setup - Provides mocks for:
 * - Zustand stores (useAuthStore)
 * - Auth adapter
 * - MapLibre-compatible map surface
 * - API client (apiFetch)
 * - GEE/API endpoints
 */

import { beforeEach, vi } from 'vitest';
import type { AuthSession, AuthUser } from '../../src/lib/auth/types';

// ============================================
// Mock Auth Types
// ============================================

export const mockAuthUser = (overrides?: Partial<AuthUser>): AuthUser => ({
  id: 'test-user-id',
  email: 'test@example.com',
  nombre: 'Test',
  apellido: 'User',
  telefono: '+543531234567',
  role: 'ciudadano',
  ...overrides,
});

export const mockAuthSession = (overrides?: Partial<AuthSession>): AuthSession => ({
  access_token: 'test-access-token',
  user: mockAuthUser(),
  ...overrides,
});

// ============================================
// Mock Zustand AuthStore
// ============================================

export interface MockAuthStoreState {
  user: AuthUser | null;
  session: AuthSession | null;
  profile: any | null;
  loading: boolean;
  error: string | null;
  initialized: boolean;
  initialize: () => Promise<void>;
  reset: () => void;
  setUser: (user: User | null) => void;
  setSession: (session: Session | null) => void;
  setProfile: (profile: any | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setInitialized: (initialized: boolean) => void;
}

export const createMockAuthStore = (initialState?: Partial<MockAuthStoreState>) => {
  const state: MockAuthStoreState = {
    user: null,
    session: null,
    profile: null,
    loading: false,
    error: null,
    initialized: false,
    initialize: vi.fn().mockResolvedValue(undefined),
    reset: vi.fn(),
    setUser: vi.fn((user) => {
      state.user = user;
    }),
    setSession: vi.fn((session) => {
      state.session = session;
    }),
    setProfile: vi.fn((profile) => {
      state.profile = profile;
    }),
    setLoading: vi.fn((loading) => {
      state.loading = loading;
    }),
    setError: vi.fn((error) => {
      state.error = error;
    }),
    setInitialized: vi.fn((initialized) => {
      state.initialized = initialized;
    }),
    ...initialState,
  };

  return state;
};

// ============================================
// Mock MapLibre-compatible Map
// ============================================

export const createMockMapLibreMap = () => ({
  invalidateSize: vi.fn(),
  getContainer: vi.fn().mockReturnValue(document.createElement('div')),
  on: vi.fn(),
  off: vi.fn(),
});

// ============================================
// Mock API Client
// ============================================

export const createMockApiClient = () => ({
  fetch: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
});

// ============================================
// Mock Auth Adapter
// ============================================

export const createMockAuthAdapter = (overrides?: Partial<Record<string, unknown>>) => ({
  getSession: vi.fn().mockResolvedValue(mockAuthSession()),
  getAccessToken: vi.fn().mockResolvedValue('test-access-token'),
  login: vi.fn().mockResolvedValue(mockAuthSession()),
  register: vi.fn().mockResolvedValue(mockAuthSession()),
  loginWithGoogle: vi.fn().mockResolvedValue(undefined),
  logout: vi.fn().mockResolvedValue(undefined),
  clearTokens: vi.fn(),
  onAuthStateChange: vi.fn(() => () => {}),
  ...overrides,
});

// ============================================
// Mock GEE Responses
// ============================================

export const createMockFeatureCollection = (features = 10) => ({
  type: 'FeatureCollection',
  features: Array.from({ length: features }, (_, i) => ({
    type: 'Feature',
    geometry: {
      type: 'Point',
      coordinates: [62.5 + i * 0.1, -32.5 + i * 0.1],
    },
    properties: {
      id: `feature-${i}`,
      name: `Feature ${i}`,
    },
  })),
});

export const createMockCaminosColoreados = () => ({
  type: 'FeatureCollection' as const,
  features: [
    {
      type: 'Feature' as const,
      geometry: {
        type: 'LineString' as const,
        coordinates: [
          [62.5, -32.5],
          [62.6, -32.6],
        ],
      },
      properties: {
        id: 'road-1',
        consorcio: 'Zona',
        color: '#FF0000',
      },
    },
  ],
  metadata: {
    total_tramos: 100,
    total_consorcios: 6,
    total_km: 500,
  },
  consorcios: [
    {
      nombre: 'Zona',
      codigo: 'ZON',
      color: '#FF0000',
      tramos: 50,
      longitud_km: 250,
    },
  ],
});

// ============================================
// Setup/Cleanup
// ============================================

export function setupHooksTests() {
  beforeEach(() => {
    // Clear all mocks before each test
    vi.clearAllMocks();

    // Reset localStorage
    localStorage.clear();

    // Reset window events
    vi.spyOn(window, 'addEventListener');
    vi.spyOn(window, 'removeEventListener');
    vi.spyOn(window, 'dispatchEvent');
  });
}

// ============================================
// Helper: Wait for async operations
// ============================================

export const waitFor = async (
  condition: () => boolean,
  timeout = 1000
): Promise<void> => {
  const startTime = Date.now();
  while (!condition()) {
    if (Date.now() - startTime > timeout) {
      throw new Error('Timeout waiting for condition');
    }
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
};

// ============================================
// Helper: Get all storage events for a key
// ============================================

export const createStorageEvent = (
  key: string,
  newValue: string | null,
  oldValue: string | null = null
): StorageEvent => {
  return new StorageEvent('storage', {
    key,
    newValue,
    oldValue,
    storageArea: localStorage,
    url: window.location.href,
  });
};
