/**
 * Hook para verificacion de contacto.
 *
 * Soporta:
 * - Google OAuth (1 click) via JWT adapter
 *
 */

import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useState } from 'react';
import { signOut } from '../lib/auth';
import { authAdapter } from '../lib/auth/index';
import { consumeLocalLogoutWarning } from '../lib/auth/storage';
import { logger } from '../lib/logger';
import { useAuthStore } from '../stores/authStore';

export interface UseContactVerificationOptions {
  /**
   * Callback cuando la verificacion es exitosa.
   */
  onVerified?: (email: string, name?: string) => void;
}

export interface ContactVerificationState {
  /** Usuario esta verificado (autenticado) */
  contactoVerificado: boolean;
  /** Email del usuario verificado */
  userEmail: string | null;
  /** Nombre del usuario (si disponible) */
  userName: string | null;
  /** Cargando autenticacion */
  loading: boolean;
}

export interface ContactVerificationActions {
  /** Iniciar login con Google */
  loginWithGoogle: () => Promise<void>;
  /** Cerrar sesion */
  logout: () => Promise<void>;
}

export type UseContactVerificationReturn = ContactVerificationState & ContactVerificationActions;

export function useContactVerification(
  options: UseContactVerificationOptions = {}
): UseContactVerificationReturn {
  const { onVerified } = options;

  // Estado del auth store
  const user = useAuthStore((state) => state.user);
  const profile = useAuthStore((state) => state.profile);
  const initialized = useAuthStore((state) => state.initialized);
  const authLoading = useAuthStore((state) => state.loading);

  // Estado local
  const [loading, setLoading] = useState(false);

  // Derivar estado de verificacion del auth store
  const contactoVerificado = !!user && initialized;
  const userEmail = user?.email || null;
  const userName = profile?.nombre || null;

  // Notificar cuando se verifica
  useEffect(() => {
    if (contactoVerificado && userEmail && onVerified) {
      onVerified(userEmail, userName || undefined);
    }
  }, [contactoVerificado, userEmail, userName, onVerified]);

  // Login con Google OAuth via JWT adapter
  const loginWithGoogle = useCallback(async () => {
    setLoading(true);
    try {
      await authAdapter.loginWithGoogle();
      // El redirect sucede automaticamente
    } catch (error) {
      logger.error('Error en login con Google:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudo iniciar sesion con Google',
        color: 'red',
      });
      setLoading(false);
    }
  }, []);

  // Logout
  const logout = useCallback(async () => {
    try {
      const result = await signOut();
      const warning = result?.warning ? (consumeLocalLogoutWarning() ?? result.warning) : null;
      notifications.show(
        warning
          ? {
              title: 'Sesión cerrada localmente',
              message: warning,
              color: 'yellow',
            }
          : {
              title: 'Sesion cerrada',
              message: 'Has cerrado sesion correctamente',
              color: 'blue',
            }
      );
    } catch (error) {
      logger.error('Error al cerrar sesion:', error);
    }
  }, []);

  return {
    // Estado
    contactoVerificado,
    userEmail,
    userName,
    loading: loading || authLoading,

    // Acciones
    loginWithGoogle,
    logout,
  };
}

export default useContactVerification;
