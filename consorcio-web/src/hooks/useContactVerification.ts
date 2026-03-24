/**
 * Hook para verificacion de contacto.
 *
 * Soporta:
 * - Google OAuth (1 click) via JWT adapter
 * - Magic Link (disabled — requires backend support)
 *
 * Simplified from the former Supabase-backed version.
 */

import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useState } from 'react';
import { useAuthStore } from '../stores/authStore';
import { authAdapter } from '../lib/auth/index';
import { signOut } from '../lib/auth';
import { logger } from '../lib/logger';
import { isValidEmail } from '../lib/validators';

export type VerificationMethod = 'google' | 'email';

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
  /** Metodo de verificacion seleccionado */
  metodoVerificacion: VerificationMethod;
  /** Cargando autenticacion */
  loading: boolean;
  /** Magic link fue enviado */
  magicLinkSent: boolean;
  /** Email al que se envio el magic link */
  magicLinkEmail: string | null;
}

export interface ContactVerificationActions {
  /** Cambiar metodo de verificacion */
  setMetodoVerificacion: (method: VerificationMethod) => void;
  /** Iniciar login con Google */
  loginWithGoogle: () => Promise<void>;
  /** Enviar magic link */
  sendMagicLink: (email: string) => Promise<void>;
  /** Cerrar sesion */
  logout: () => Promise<void>;
  /** Resetear estado */
  resetVerificacion: () => void;
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
  const [metodoVerificacion, setMetodoVerificacion] = useState<VerificationMethod>('google');
  const [loading, setLoading] = useState(false);
  const [magicLinkSent, setMagicLinkSent] = useState(false);
  const [magicLinkEmail, setMagicLinkEmail] = useState<string | null>(null);

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

  // Enviar magic link — not supported with JWT adapter
  const sendMagicLink = useCallback(async (email: string) => {
    if (!isValidEmail(email)) {
      notifications.show({
        title: 'Email invalido',
        message: 'Ingresa un email valido',
        color: 'red',
      });
      return;
    }

    notifications.show({
      title: 'No disponible',
      message: 'El acceso por magic link no esta disponible. Usa Google o crea una cuenta.',
      color: 'yellow',
    });
  }, []);

  // Logout
  const logout = useCallback(async () => {
    try {
      await signOut();
      notifications.show({
        title: 'Sesion cerrada',
        message: 'Has cerrado sesion correctamente',
        color: 'blue',
      });
    } catch (error) {
      logger.error('Error al cerrar sesion:', error);
    }
  }, []);

  // Reset
  const resetVerificacion = useCallback(() => {
    setMagicLinkSent(false);
    setMagicLinkEmail(null);
    setMetodoVerificacion('google');
  }, []);

  return {
    // Estado
    contactoVerificado,
    userEmail,
    userName,
    metodoVerificacion,
    loading: loading || authLoading,
    magicLinkSent,
    magicLinkEmail,

    // Acciones
    setMetodoVerificacion,
    loginWithGoogle,
    sendMagicLink,
    logout,
    resetVerificacion,
  };
}

export default useContactVerification;
