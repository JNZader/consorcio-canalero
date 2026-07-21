/**
 * JWT auth adapter — authenticates against our FastAPI backend.
 */

// Resolve API URL without importing from api/core (avoids circular dependency)
const API_URL =
  import.meta.env.VITE_API_URL || import.meta.env.PUBLIC_API_URL || 'http://localhost:8000';
const AUTH_BASE = `${API_URL}/api/v2`;
import {
  clearApiServiceWorkerCaches,
  clearAuthStorage,
  getStoredAccessToken,
  getStoredAuthSession,
  persistAuthSession,
} from './storage';
import type {
  AuthAdapter,
  AuthSession,
  AuthStateChangeCallback,
  AuthUser,
  LoginCredentials,
  RegisterCredentials,
} from './types';

export class JWTAuthAdapter implements AuthAdapter {
  private listeners: Set<AuthStateChangeCallback> = new Set();

  async getSession(): Promise<AuthSession | null> {
    return getStoredAuthSession();
  }

  async getAccessToken(): Promise<string | null> {
    return getStoredAccessToken();
  }

  async login(credentials: LoginCredentials): Promise<AuthSession> {
    // fastapi-users expects OAuth2 form data for login
    const formData = new URLSearchParams();
    formData.append('username', credentials.email);
    formData.append('password', credentials.password);

    const response = await fetch(`${AUTH_BASE}/auth/jwt/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Error al iniciar sesión');
    }

    const data = await response.json();
    const token = data.access_token;

    // Fetch user profile
    const user = await this.fetchCurrentUser(token);

    const session: AuthSession = { access_token: token, user };
    this.persistSession(session);
    this.notifyListeners('SIGNED_IN', session);

    // Phase 2 / F2-K: stamp the refresh-token cookie immediately
    // after a successful login so the silent-refresh interceptor has
    // a cookie to trade. Best-effort — if the call fails the user
    // can still work until their access token expires.
    void fetch(`${AUTH_BASE}/auth/jwt/login-with-refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {
      /* noop — caller already has a valid access token */
    });

    return session;
  }

  async register(credentials: RegisterCredentials): Promise<AuthSession> {
    const response = await fetch(`${AUTH_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: credentials.email,
        password: credentials.password,
        nombre: credentials.nombre,
        apellido: credentials.apellido,
        telefono: credentials.telefono || '',
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Error al registrarse');
    }

    // Auto-login after registration
    return this.login({ email: credentials.email, password: credentials.password });
  }

  async loginWithGoogle(): Promise<void> {
    // Fetch the Google OAuth authorization URL from the backend.
    // fastapi-users returns {"authorization_url": "https://accounts.google.com/..."}
    // ``credentials: 'include'`` is required so the browser stores the
    // backend's ``oauth_state`` cookie (anti-CSRF nonce). Without it the
    // callback will always 401 on cross-origin deploys (Cloudflare Pages
    // frontend + Hetzner backend on a different domain). No request body
    // and no custom headers → stays a "simple" CORS GET and avoids an
    // unnecessary preflight.
    const response = await fetch(`${AUTH_BASE}/auth/google/authorize`, {
      method: 'GET',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error('No se pudo iniciar la autenticacion con Google');
    }

    const data = await response.json();
    const authUrl = data.authorization_url;

    if (!authUrl) {
      throw new Error('No se recibio la URL de autorizacion de Google');
    }

    // Redirect the browser to Google's OAuth consent page
    window.location.href = authUrl;
  }

  async logout(): Promise<void> {
    let token = getStoredAccessToken();

    if (!token) {
      token = await this.refreshAccessTokenForLogout();
    }

    let response = await this.revokeRefreshSessions(token);
    if (response.status === 401) {
      token = await this.refreshAccessTokenForLogout();
      response = await this.revokeRefreshSessions(token);
    }

    if (!response.ok) {
      throw new Error('No se pudo cerrar la sesión en el servidor.');
    }

    this.clearStorage();
    this.notifyListeners('SIGNED_OUT', null);
  }

  clearTokens(): void {
    this.clearStorage();
    this.notifyListeners('SIGNED_OUT', null);
  }

  async replaceAccessToken(token: string): Promise<void> {
    // Keep the previously cached user; only the access token rotates.
    const current = await this.getSession();
    if (current?.user) {
      this.persistSession({ access_token: token, user: current.user });
      this.notifyListeners('TOKEN_REFRESHED', {
        access_token: token,
        user: current.user,
      });
      return;
    }
    // No cached user yet (cold load after the SPA bootstrapped on a
    // refresh-only response). Hydrate from /users/me with the fresh
    // token so the storage stays consistent.
    const user = await this.fetchCurrentUser(token);
    this.persistSession({ access_token: token, user });
    this.notifyListeners('TOKEN_REFRESHED', { access_token: token, user });
  }

  onAuthStateChange(callback: AuthStateChangeCallback): () => void {
    this.listeners.add(callback);
    return () => {
      this.listeners.delete(callback);
    };
  }

  private async refreshAccessTokenForLogout(): Promise<string> {
    const response = await fetch(`${AUTH_BASE}/auth/jwt/refresh`, {
      method: 'POST',
      credentials: 'include',
    });
    if (!response.ok) {
      throw new Error('No se pudo renovar la sesión para cerrarla.');
    }

    const payload: unknown = await response.json().catch(() => null);
    if (
      typeof payload !== 'object' ||
      payload === null ||
      typeof (payload as { access_token?: unknown }).access_token !== 'string' ||
      !(payload as { access_token: string }).access_token
    ) {
      throw new Error('El servidor no devolvió una sesión válida para cerrarla.');
    }
    return (payload as { access_token: string }).access_token;
  }

  private revokeRefreshSessions(token: string): Promise<Response> {
    return fetch(`${AUTH_BASE}/auth/jwt/logout-all`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
  }

  private async fetchCurrentUser(token: string): Promise<AuthUser> {
    const response = await fetch(`${AUTH_BASE}/users/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
      throw new Error('Error al obtener el perfil del usuario');
    }

    const data = await response.json();
    return {
      id: data.id,
      email: data.email,
      nombre: data.nombre || '',
      apellido: data.apellido || '',
      telefono: data.telefono || '',
      role: data.role || 'ciudadano',
    };
  }

  private persistSession(session: AuthSession): void {
    persistAuthSession(session);
  }

  private clearStorage(): void {
    clearAuthStorage();
    // Drop service-worker API caches in the background so the next
    // user of a shared device can't pop PII out of the SW cache.
    // Fire-and-forget; logout already completed regardless of result.
    void clearApiServiceWorkerCaches();
  }

  private notifyListeners(
    event: 'SIGNED_IN' | 'SIGNED_OUT' | 'TOKEN_REFRESHED',
    session: AuthSession | null
  ): void {
    for (const listener of this.listeners) {
      try {
        listener(event, session);
      } catch {
        // Don't let a failing listener break others
      }
    }
  }
}
