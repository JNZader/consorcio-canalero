/**
 * Hooks test setup - Provides mocks for:
 * - Zustand stores (useAuthStore)
 * - Supabase client
 * - Leaflet map
 * - API client (apiFetch)
 * - GEE/API endpoints
 */
// @ts-nocheck


import { beforeEach, vi } from 'vitest';
import type { Session, User } from '@supabase/supabase-js';
import type { Map } from 'leaflet';

// ============================================
// Mock Supabase Auth Types
// ============================================

export const mockSupabaseUser = (overrides?: Partial<User>): User => ({
  id: 'test-user-id',
  aud: 'authenticated',
  role: 'authenticated',
  email: 'test@example.com',
  email_confirmed_at: new Date().toISOString(),
  phone: null,
  confirmed_at: new Date().toISOString(),
  last_sign_in_at: new Date().toISOString(),
  app_metadata: { provider: 'email' },
  user_metadata: {
    full_name: 'Test User',
    name: 'Test User',
  },
  identities: [],
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  is_anonymous: false,
  ...overrides,
});

export const mockSupabaseSession = (overrides?: Partial<Session>): Session => ({
  access_token: 'test-access-token',
  token_type: 'bearer',
  expires_in: 3600,
  expires_at: Math.floor(Date.now() / 1000) + 3600,
  refresh_token: 'test-refresh-token',
  user: mockSupabaseUser(),
  ...overrides,
});

// ============================================
// Mock Zustand AuthStore
// ============================================

export interface MockAuthStoreState {
  user: User | null;
  session: Session | null;
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
// Mock Leaflet Map
// ============================================

export const createMockLeafletMap = (): Partial<Map> => ({
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
// Mock Supabase Client
// ============================================

export const createMockSupabaseClient = (overrides?: any) => ({
  auth: {
    onAuthStateChange: vi.fn((callback) => {
      return () => {}; // unsubscribe function
    }),
    getSession: vi.fn().mockResolvedValue({
      data: { session: mockSupabaseSession() },
    }),
    signInWithEmail: vi.fn().mockResolvedValue({
      data: { user: mockSupabaseUser(), session: mockSupabaseSession() },
    }),
    signInWithPassword: vi.fn().mockResolvedValue({
      data: { user: mockSupabaseUser(), session: mockSupabaseSession() },
    }),
    signUp: vi.fn().mockResolvedValue({
      data: { user: mockSupabaseUser(), session: mockSupabaseSession() },
    }),
    signOut: vi.fn().mockResolvedValue({ error: null }),
    signInWithOAuth: vi.fn().mockResolvedValue({ error: null }),
    signInWithOtp: vi.fn().mockResolvedValue({ error: null }),
    ...overrides?.auth,
  },
  from: vi.fn((table: string) => ({
    select: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    single: vi.fn().mockResolvedValue({ data: null, error: null }),
    ...overrides?.from?.[table],
  })),
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
