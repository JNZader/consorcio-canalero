/**
 * JWT auth adapter — authenticates against our FastAPI backend.
 */

import { API_URL, API_PREFIX } from '../api/core';

const AUTH_BASE = `${API_URL}${API_PREFIX}`;
import type {
  AuthAdapter,
  AuthSession,
  AuthStateChangeCallback,
  AuthUser,
  LoginCredentials,
  RegisterCredentials,
} from './types';

const TOKEN_KEY = 'consorcio_auth_token';
const USER_KEY = 'consorcio_auth_user';

export class JWTAuthAdapter implements AuthAdapter {
  private listeners: Set<AuthStateChangeCallback> = new Set();

  async getSession(): Promise<AuthSession | null> {
    const token = localStorage.getItem(TOKEN_KEY);
    const userJson = localStorage.getItem(USER_KEY);

    if (!token || !userJson) return null;

    try {
      const user: AuthUser = JSON.parse(userJson);
      return { access_token: token, user };
    } catch {
      this.clearStorage();
      return null;
    }
  }

  async getAccessToken(): Promise<string | null> {
    return localStorage.getItem(TOKEN_KEY);
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
    // Redirect to backend Google OAuth endpoint
    window.location.href = `${AUTH_BASE}/auth/google/authorize`;
  }

  async logout(): Promise<void> {
    const token = localStorage.getItem(TOKEN_KEY);

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
    localStorage.setItem(TOKEN_KEY, session.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(session.user));
  }

  private clearStorage(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  private notifyListeners(
    event: 'SIGNED_IN' | 'SIGNED_OUT' | 'TOKEN_REFRESHED',
    session: AuthSession | null,
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
