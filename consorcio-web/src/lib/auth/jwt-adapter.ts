/**
 * JWT auth adapter — authenticates against our FastAPI backend.
 */

// Resolve API URL without importing from api/core (avoids circular dependency)
const API_URL =
  import.meta.env.VITE_API_URL || import.meta.env.PUBLIC_API_URL || 'http://localhost:8000';
const AUTH_BASE = `${API_URL}/api/v2`;
import type {
  AuthAdapter,
  AuthSession,
  AuthStateChangeCallback,
  AuthUser,
  LoginCredentials,
  RegisterCredentials,
} from './types';
import {
  clearAuthStorage,
  getStoredAccessToken,
  getStoredAuthSession,
  persistAuthSession,
} from './storage';

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
    const response = await fetch(`${AUTH_BASE}/auth/google/authorize`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
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
    const token = getStoredAccessToken();

    if (token) {
      try {
        await fetch(`${AUTH_BASE}/auth/jwt/logout`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        });
      } catch {
        // Logout even if backend call fails
      }
    }

    this.clearStorage();
    this.notifyListeners('SIGNED_OUT', null);
  }

  clearTokens(): void {
    this.clearStorage();
    this.notifyListeners('SIGNED_OUT', null);
  }

  onAuthStateChange(callback: AuthStateChangeCallback): () => void {
    this.listeners.add(callback);
    return () => {
      this.listeners.delete(callback);
    };
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
