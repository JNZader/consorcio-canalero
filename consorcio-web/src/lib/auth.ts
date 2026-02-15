import type { AuthError } from '@supabase/supabase-js';
import { getSupabaseClient } from './supabase';
import { logger } from './logger';
import { safeGetUserRole } from './typeGuards';
import { useAuthStore, type UserRole } from '../stores/authStore';

// Helper para obtener cliente de forma segura
const getClient = () => getSupabaseClient();

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
    const { data, error } = await getClient().auth.signInWithPassword({
      email,
      password,
    });

    if (error) {
      return {
        success: false,
        error: translateAuthError(error),
      };
    }

    return {
      success: true,
      user: data.user ?? undefined,
    };
  } catch (err) {
    logger.error('Error inesperado al iniciar sesion:', err);
    return {
      success: false,
      error: 'Error inesperado al iniciar sesion',
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
    const { data, error } = await getClient().auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: nombre,
        },
      },
    });

    if (error) {
      return {
        success: false,
        error: translateAuthError(error),
      };
    }

    // Verificar si necesita confirmacion de email
    // data.user existe pero data.session es null cuando requiere confirmacion
    const needsEmailConfirmation = Boolean(data.user && !data.session);

    return {
      success: true,
      user: data.user ?? undefined,
      needsEmailConfirmation,
    };
  } catch (err) {
    logger.error('Error inesperado al crear cuenta:', err);
    return {
      success: false,
      error: 'Error inesperado al crear cuenta',
    };
  }
}

/**
 * Iniciar sesion con Google OAuth
 */
export async function signInWithGoogle(): Promise<AuthResult> {
  logger.debug('[AUTH] signInWithGoogle called');
  try {
    const client = getClient();
    const redirectUrl = `${globalThis.location.origin}/auth/callback`;
    logger.debug('[AUTH] Redirect URL:', redirectUrl);

    const { data, error } = await client.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: redirectUrl,
      },
    });

    logger.debug('[AUTH] signInWithOAuth response:', { hasData: !!data, hasError: !!error });

    if (error) {
      logger.warn('[AUTH] OAuth error:', error.message);
      return {
        success: false,
        error: translateAuthError(error),
      };
    }

    // OAuth redirige automaticamente, no retorna usuario directamente
    return {
      success: true,
    };
  } catch (err) {
    logger.error('Error inesperado al conectar con Google:', err);
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
    const { error } = await getClient().auth.signOut();

    if (error) {
      return {
        success: false,
        error: translateAuthError(error),
      };
    }

    // Limpiar estado del store y localStorage
    useAuthStore.getState().reset();

    // Limpiar localStorage de auth persistido
    if (typeof window !== 'undefined') {
      localStorage.removeItem('cc-auth-storage');
    }

    return {
      success: true,
    };
  } catch (err) {
    logger.error('Error inesperado al cerrar sesion:', err);
    return {
      success: false,
      error: 'Error inesperado al cerrar sesion',
    };
  }
}

/**
 * Obtener el rol del usuario actual con validacion en tiempo de ejecucion
 */
export async function getUserRole(userId: string): Promise<UserRole | null> {
  try {
    const { data, error } = await getClient()
      .from('perfiles')
      .select('rol')
      .eq('id', userId)
      .single();

    if (error) {
      logger.error('Error al obtener rol:', error);
      return null;
    }

    // Validate the role at runtime instead of blindly asserting
    const role = safeGetUserRole(data?.rol);
    if (!role) {
      logger.warn('Invalid role received from API:', data?.rol);
    }
    return role;
  } catch (err) {
    logger.error('Error al obtener rol:', err);
    return null;
  }
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
 * Traducir errores de autenticacion de Supabase a espanol
 */
function translateAuthError(error: AuthError): string {
  const errorMessages: Record<string, string> = {
    'Invalid login credentials': 'Email o contrasena incorrectos',
    'Email not confirmed': 'Debes confirmar tu email antes de iniciar sesion',
    'User already registered': 'Este email ya esta registrado',
    'Password should be at least 6 characters': 'La contrasena debe tener al menos 6 caracteres',
    'Unable to validate email address: invalid format': 'Formato de email invalido',
    'Signup requires a valid password': 'Se requiere una contrasena valida',
    'User not found': 'Usuario no encontrado',
    'Email rate limit exceeded': 'Demasiados intentos. Intenta de nuevo mas tarde',
    'For security purposes, you can only request this once every 60 seconds':
      'Por seguridad, solo puedes intentar esto una vez cada 60 segundos',
    'New password should be different from the old password':
      'La nueva contrasena debe ser diferente a la anterior',
  };

  // Buscar traduccion exacta
  if (errorMessages[error.message]) {
    return errorMessages[error.message];
  }

  // Buscar traduccion parcial
  for (const [key, value] of Object.entries(errorMessages)) {
    if (error.message.toLowerCase().includes(key.toLowerCase())) {
      return value;
    }
  }

  // Retornar mensaje original si no hay traduccion
  return error.message || 'Error de autenticacion';
}

/**
 * Enviar email para restablecer contrasena
 */
export async function resetPassword(email: string): Promise<AuthResult> {
  try {
    const { error } = await getClient().auth.resetPasswordForEmail(email, {
      redirectTo: `${globalThis.location.origin}/auth/reset-password`,
    });

    if (error) {
      return {
        success: false,
        error: translateAuthError(error),
      };
    }

    return {
      success: true,
    };
  } catch (err) {
    logger.error('Error inesperado al enviar email de recuperacion:', err);
    return {
      success: false,
      error: 'Error inesperado al enviar email de recuperacion',
    };
  }
}

/**
 * Actualizar contrasena del usuario
 */
export async function updatePassword(newPassword: string): Promise<AuthResult> {
  try {
    const { error } = await getClient().auth.updateUser({
      password: newPassword,
    });

    if (error) {
      return {
        success: false,
        error: translateAuthError(error),
      };
    }

    return {
      success: true,
    };
  } catch (err) {
    logger.error('Error inesperado al actualizar contrasena:', err);
    return {
      success: false,
      error: 'Error inesperado al actualizar contrasena',
    };
  }
}
