/**
 * Auth adapter interface — abstracts authentication provider.
 * Allows swapping between Supabase, JWT, or any other auth backend.
 */

export interface AuthUser {
  id: string;
  email: string;
  nombre: string;
  apellido: string;
  telefono: string;
  role: 'ciudadano' | 'operador' | 'admin';
}

export interface AuthSession {
  access_token: string;
  user: AuthUser;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterCredentials {
  email: string;
  password: string;
  nombre: string;
  apellido: string;
  telefono?: string;
}

export type AuthStateChangeCallback = (
  event: 'SIGNED_IN' | 'SIGNED_OUT' | 'TOKEN_REFRESHED',
  session: AuthSession | null,
) => void;

export interface AuthAdapter {
  /** Get current session (from storage or refresh) */
  getSession(): Promise<AuthSession | null>;

  /** Get current access token */
  getAccessToken(): Promise<string | null>;

  /** Login with email/password */
  login(credentials: LoginCredentials): Promise<AuthSession>;

  /** Register new user */
  register(credentials: RegisterCredentials): Promise<AuthSession>;

  /** Login with Google OAuth */
  loginWithGoogle(): Promise<void>;

  /** Logout */
  logout(): Promise<void>;

  /** Subscribe to auth state changes */
  onAuthStateChange(callback: AuthStateChangeCallback): () => void;
}
