/**
 * Auth adapter interface — abstracts authentication provider.
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
  session: AuthSession | null
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

  /** Clear stored tokens (for expired session handling) */
  clearTokens(): void;

  /**
   * Swap the stored access token without touching the cached user
   * profile. Used by the silent-refresh interceptor when the
   * backend issues a new access token via the refresh-cookie flow.
   */
  replaceAccessToken(token: string): Promise<void>;

  /** Subscribe to auth state changes */
  onAuthStateChange(callback: AuthStateChangeCallback): () => void;
}
