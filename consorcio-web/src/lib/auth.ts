/**
 * Authentication helper functions.
 */

import { type UserRole, useAuthStore } from '../stores/authStore';
import { authAdapter } from './auth/index';
import { logger } from './logger';
import { safeGetUserRole } from './typeGuards';

// Re-export types from store for backwards compatibility
export type { UserRole };

/**
 * Resultado de operaciones de autenticacion
 */
export interface AuthResult {
  success: boolean;
  error?: string;
  user?: { id: string; email?: string };
  needsEmailConfirmation?: boolean;
}

/**
 * Hook para manejar el estado de autenticacion.
 * NOTA: Este hook ahora usa Zustand internamente para compartir estado global.
 * El store se inicializa automaticamente en AppProvider/MantineProvider.
 */
export function useAuth() {
  const { user, session, profile, loading, error } = useAuthStore();
  return { user, session, profile, loading, error };
}

/**
 * Iniciar sesion con email y contrasena
 */
export async function signInWithEmail(email: string, password: string): Promise<AuthResult> {
  try {
    const session = await authAdapter.login({ email, password });

    return {
      success: true,
      user: { id: session.user.id, email: session.user.email },
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Error inesperado al iniciar sesion';
    logger.error('Error al iniciar sesion:', err);
    return {
      success: false,
      error: translateAuthError(message),
    };
  }
}

/**
 * Registrar nuevo usuario con email y contrasena
 */
export async function signUpWithEmail(
  email: string,
  password: string,
  nombre?: string
): Promise<AuthResult> {
  try {
    const session = await authAdapter.register({
      email,
      password,
      nombre: nombre || '',
      apellido: '',
    });

    return {
      success: true,
      user: { id: session.user.id, email: session.user.email },
      needsEmailConfirmation: false,
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Error inesperado al crear cuenta';
    logger.error('Error al crear cuenta:', err);
    return {
      success: false,
      error: translateAuthError(message),
    };
  }
}

/**
 * Iniciar sesion con Google OAuth
 */
export async function signInWithGoogle(): Promise<AuthResult> {
  logger.debug('[AUTH] signInWithGoogle called');
  try {
    await authAdapter.loginWithGoogle();
    // OAuth redirects automatically, won't return a user directly
    return { success: true };
  } catch (err) {
    logger.error('Error al conectar con Google:', err);
    return {
      success: false,
      error: 'Error inesperado al conectar con Google',
    };
  }
}

/**
 * Cerrar sesion
 */
export async function signOut(): Promise<AuthResult> {
  try {
    await authAdapter.logout();

    // Limpiar estado del store y localStorage
    useAuthStore.getState().reset();

    // Limpiar localStorage de auth persistido
    if (typeof window !== 'undefined') {
      localStorage.removeItem('cc-auth-storage');
    }

    return { success: true };
  } catch (err) {
    logger.error('Error al cerrar sesion:', err);

    // Fallback defensivo: limpiar estado local aunque falle el backend
    useAuthStore.getState().reset();
    if (typeof window !== 'undefined') {
      localStorage.removeItem('cc-auth-storage');
    }

    return { success: true };
  }
}

/**
 * Obtener el rol del usuario actual con validacion en tiempo de ejecucion.
 */
export async function getUserRole(_userId: string): Promise<UserRole | null> {
  const profile = useAuthStore.getState().profile;
  return safeGetUserRole(profile?.rol);
}

/**
 * Verificar si el usuario tiene un rol especifico
 */
export async function hasRole(userId: string, allowedRoles: UserRole[]): Promise<boolean> {
  const role = await getUserRole(userId);
  return role !== null && allowedRoles.includes(role);
}

/**
 * Verificar si el usuario es admin
 */
export async function isAdmin(userId: string): Promise<boolean> {
  return hasRole(userId, ['admin']);
}

/**
 * Verificar si el usuario es operador o admin
 */
export async function isOperadorOrAdmin(userId: string): Promise<boolean> {
  return hasRole(userId, ['operador', 'admin']);
}

/**
 * Traducir errores de autenticacion a espanol
 */
function translateAuthError(message: string): string {
  const errorMessages: Record<string, string> = {
    'Invalid login credentials': 'Email o contrasena incorrectos',
    LOGIN_BAD_CREDENTIALS: 'Email o contrasena incorrectos',
    'Email not confirmed': 'Debes confirmar tu email antes de iniciar sesion',
    'User already registered': 'Este email ya esta registrado',
    REGISTER_USER_ALREADY_EXISTS: 'Este email ya esta registrado',
    'Password should be at least 6 characters': 'La contrasena debe tener al menos 6 caracteres',
    'Unable to validate email address: invalid format': 'Formato de email invalido',
    'Signup requires a valid password': 'Se requiere una contrasena valida',
    'User not found': 'Usuario no encontrado',
    'Email rate limit exceeded': 'Demasiados intentos. Intenta de nuevo mas tarde',
    'Error al iniciar sesion': 'Email o contrasena incorrectos',
    'Error al registrarse': 'Error al crear la cuenta',
    RESET_PASSWORD_BAD_TOKEN: 'El enlace de recuperacion es invalido o ya expiro.',
    RESET_PASSWORD_INVALID_PASSWORD: 'La contrasena no cumple los requisitos minimos de seguridad.',
  };

  // Buscar traduccion exacta
  if (errorMessages[message]) {
    return errorMessages[message];
  }

  // Buscar traduccion parcial
  for (const [key, value] of Object.entries(errorMessages)) {
    if (message.toLowerCase().includes(key.toLowerCase())) {
      return value;
    }
  }

  // Retornar mensaje original si no hay traduccion
  return message || 'Error de autenticacion';
}

/**
 * Enviar email para restablecer contrasena.
 * Calls POST /api/v2/auth/forgot-password.
 * fastapi-users always returns 202 to prevent email enumeration.
 */
export async function resetPassword(email: string): Promise<AuthResult> {
  try {
    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    await fetch(`${API_URL}/api/v2/auth/forgot-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    // fastapi-users always returns 202 to prevent email enumeration
    return { success: true };
  } catch (err) {
    logger.error('Error al solicitar reset de password:', err);
    return { success: false, error: 'Error al enviar el email de recuperacion.' };
  }
}

/**
 * Actualizar contrasena del usuario autenticado.
 * Uses PATCH /users/me from fastapi-users.
 */
export async function updatePassword(newPassword: string): Promise<AuthResult> {
  try {
    const { apiFetch } = await import('./api/core');
    await apiFetch('/users/me', {
      method: 'PATCH',
      body: JSON.stringify({ password: newPassword }),
    });
    return { success: true };
  } catch (err) {
    logger.error('Error al actualizar password:', err);
    return { success: false, error: 'Error al cambiar la contrasena.' };
  }
}

/**
 * Phase 5 / F5-E: trade a short SMTP-body code for the real verify
 * / reset JWT token.
 *
 * The backend stopped putting the long verify/reset JWT in email
 * bodies (provider logs retain those for 30+ days, leaking valid
 * one-shot credentials). Emails now carry an 8-char alphanumeric
 * code that the SPA exchanges for the original token via this
 * endpoint. The token is then fed to the existing fastapi-users
 * ``reset-password`` / ``verify`` endpoints as before.
 *
 * Returns the original token on success, or ``null`` on any failure
 * (unknown / wrong purpose / expired / already consumed). The
 * backend collapses all failure modes to HTTP 400 so the caller
 * can't enumerate codes by status — we mirror that and surface a
 * single user-facing error message at the call site.
 *
 * Backwards compat: while ``USE_ONE_TIME_CODES`` is off on the
 * backend, emails still embed the long token directly in the URL
 * and the code-exchange endpoint isn't hit. Callers should accept
 * BOTH ``?token=`` and ``?code=`` query parameters and only fire
 * this helper when ``?code=`` is present.
 */
export async function exchangeCodeForToken(
  code: string,
  purpose: 'verify' | 'reset'
): Promise<string | null> {
  try {
    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const res = await fetch(`${API_URL}/api/v2/auth/exchange-code`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, purpose }),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { token?: string };
    return data.token ?? null;
  } catch (err) {
    logger.error('Error al intercambiar código:', err);
    return null;
  }
}

/** Verify an email with the token resolved from an email code. */
export async function verifyEmailWithToken(token: string): Promise<AuthResult> {
  try {
    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const res = await fetch(`${API_URL}/api/v2/auth/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });

    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      throw new Error(error.detail || 'VERIFY_USER_BAD_TOKEN');
    }

    return { success: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Error al verificar el correo.';
    logger.error('Error al verificar correo con token:', err);
    return { success: false, error: translateAuthError(message) };
  }
}

/**
 * Restablecer contrasena usando token de reset (desde enlace de email).
 * Calls POST /api/v2/auth/reset-password with the token and new password.
 */
export async function resetPasswordWithToken(
  token: string,
  newPassword: string
): Promise<AuthResult> {
  try {
    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const res = await fetch(`${API_URL}/api/v2/auth/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, password: newPassword }),
    });

    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      const detail = error.detail || 'RESET_PASSWORD_BAD_TOKEN';
      throw new Error(detail);
    }

    return { success: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Error al restablecer la contrasena.';
    logger.error('Error al restablecer password con token:', err);
    return { success: false, error: translateAuthError(message) };
  }
}
