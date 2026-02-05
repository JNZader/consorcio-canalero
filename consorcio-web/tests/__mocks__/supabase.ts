/**
 * Mock completo del cliente Supabase para tests.
 * Cubre autenticacion, queries y subscripciones.
 */

import type { AuthError, Session, SupabaseClient, User } from '@supabase/supabase-js';
import { vi } from 'vitest';

// Mock User
export const mockUser: User = {
  id: 'test-user-id-123',
  email: 'test@example.com',
  app_metadata: {},
  user_metadata: {
    full_name: 'Test User',
  },
  aud: 'authenticated',
  created_at: '2024-01-01T00:00:00Z',
};

// Mock Session
export const mockSession: Session = {
  access_token: 'mock-access-token',
  refresh_token: 'mock-refresh-token',
  expires_in: 3600,
  token_type: 'bearer',
  user: mockUser,
};

// Mock Usuario (perfil de la app)
export const mockUsuario = {
  id: mockUser.id,
  email: mockUser.email,
  nombre: 'Test User',
  rol: 'ciudadano' as const,
};

// Mock para errores de auth
export const createAuthError = (message: string, code?: string): AuthError =>
  ({
    message,
    status: 400,
    name: 'AuthError',
    code,
    __isAuthError: true,
  }) as unknown as AuthError;

// Factory para crear respuestas de query
export const createQueryResponse = <T>(data: T | null, error: Error | null = null) => ({
  data,
  error,
  count: null,
  status: error ? 400 : 200,
  statusText: error ? 'Bad Request' : 'OK',
});

// Mock para el query builder
export const createMockQueryBuilder = () => {
  const builder = {
    select: vi.fn().mockReturnThis(),
    insert: vi.fn().mockReturnThis(),
    update: vi.fn().mockReturnThis(),
    delete: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    neq: vi.fn().mockReturnThis(),
    gt: vi.fn().mockReturnThis(),
    gte: vi.fn().mockReturnThis(),
    lt: vi.fn().mockReturnThis(),
    lte: vi.fn().mockReturnThis(),
    like: vi.fn().mockReturnThis(),
    ilike: vi.fn().mockReturnThis(),
    is: vi.fn().mockReturnThis(),
    in: vi.fn().mockReturnThis(),
    contains: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    limit: vi.fn().mockReturnThis(),
    range: vi.fn().mockReturnThis(),
    single: vi.fn().mockResolvedValue(createQueryResponse(mockUsuario)),
    maybeSingle: vi.fn().mockResolvedValue(createQueryResponse(mockUsuario)),
    // 'then' property removed due to lint rule - use promise chain instead
  };
  return builder;
};

// Subscription mock
const mockSubscription = {
  unsubscribe: vi.fn(),
};

// Auth state change callback storage
let authStateCallback: ((event: string, session: Session | null) => void) | null = null;

// Mock Auth
export const mockAuth = {
  getSession: vi.fn().mockResolvedValue({
    data: { session: mockSession },
    error: null,
  }),
  getUser: vi.fn().mockResolvedValue({
    data: { user: mockUser },
    error: null,
  }),
  signInWithPassword: vi.fn().mockResolvedValue({
    data: { user: mockUser, session: mockSession },
    error: null,
  }),
  signUp: vi.fn().mockResolvedValue({
    data: { user: mockUser, session: mockSession },
    error: null,
  }),
  signInWithOAuth: vi.fn().mockResolvedValue({
    data: { provider: 'google', url: 'https://google.com/oauth' },
    error: null,
  }),
  signOut: vi.fn().mockResolvedValue({
    error: null,
  }),
  resetPasswordForEmail: vi.fn().mockResolvedValue({
    data: {},
    error: null,
  }),
  updateUser: vi.fn().mockResolvedValue({
    data: { user: mockUser },
    error: null,
  }),
  onAuthStateChange: vi.fn().mockImplementation((callback) => {
    authStateCallback = callback;
    return { data: { subscription: mockSubscription } };
  }),
  // Helper para tests: simular cambio de estado de auth
  __simulateAuthChange: (event: string, session: Session | null = mockSession) => {
    if (authStateCallback) {
      authStateCallback(event, session);
    }
  },
};

// Mock Supabase Client
export const mockSupabaseClient = {
  auth: mockAuth,
  from: vi.fn().mockImplementation(() => createMockQueryBuilder()),
  storage: {
    from: vi.fn().mockReturnValue({
      upload: vi.fn().mockResolvedValue({ data: { path: 'test-path' }, error: null }),
      download: vi.fn().mockResolvedValue({ data: new Blob(), error: null }),
      getPublicUrl: vi
        .fn()
        .mockReturnValue({ data: { publicUrl: 'https://example.com/test.jpg' } }),
      remove: vi.fn().mockResolvedValue({ data: [], error: null }),
    }),
  },
  channel: vi.fn().mockReturnValue({
    on: vi.fn().mockReturnThis(),
    subscribe: vi.fn().mockReturnThis(),
    unsubscribe: vi.fn(),
  }),
  removeChannel: vi.fn(),
} as unknown as SupabaseClient;

// Mock del modulo supabase
export const getSupabaseClient = vi.fn().mockReturnValue(mockSupabaseClient);
export const supabase = mockSupabaseClient;

// Helper para resetear todos los mocks
export const resetSupabaseMocks = () => {
  vi.clearAllMocks();
  authStateCallback = null;

  // Resetear respuestas por defecto
  mockAuth.getSession.mockResolvedValue({
    data: { session: mockSession },
    error: null,
  });
  mockAuth.signInWithPassword.mockResolvedValue({
    data: { user: mockUser, session: mockSession },
    error: null,
  });
  mockAuth.signUp.mockResolvedValue({
    data: { user: mockUser, session: mockSession },
    error: null,
  });
  mockAuth.signOut.mockResolvedValue({ error: null });
};

// Helper para simular usuario no autenticado
export const simulateUnauthenticated = () => {
  mockAuth.getSession.mockResolvedValue({
    data: { session: null },
    error: null,
  });
  mockAuth.getUser.mockResolvedValue({
    data: { user: null },
    error: null,
  });
};

// Helper para simular error de login
export const simulateLoginError = (message = 'Invalid login credentials') => {
  mockAuth.signInWithPassword.mockResolvedValue({
    data: { user: null, session: null },
    error: createAuthError(message),
  });
};

// Helper para simular usuario admin
export const simulateAdminUser = () => {
  const adminUser = { ...mockUsuario, rol: 'admin' as const };
  const queryBuilder = createMockQueryBuilder();
  queryBuilder.single.mockResolvedValue(createQueryResponse(adminUser));
  mockSupabaseClient.from = vi.fn().mockReturnValue(queryBuilder);
};
