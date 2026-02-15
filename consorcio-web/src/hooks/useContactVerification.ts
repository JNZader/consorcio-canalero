/**
 * Hook para verificacion de contacto usando Supabase Auth.
 *
 * Soporta:
 * - Google OAuth (1 click)
 * - Magic Link (cualquier email)
 *
 * Simplificado de la version anterior que usaba WhatsApp.
 */

import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useState } from 'react';
import { useAuthStore } from '../stores/authStore';
import { getSupabaseClient } from '../lib/supabase';
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
  const userName = profile?.nombre || user?.user_metadata?.full_name || user?.user_metadata?.name || null;

  // Notificar cuando se verifica
  useEffect(() => {
    if (contactoVerificado && userEmail && onVerified) {
      onVerified(userEmail, userName || undefined);
    }
  }, [contactoVerificado, userEmail, userName, onVerified]);

  // Login con Google OAuth
  const loginWithGoogle = useCallback(async () => {
    setLoading(true);
    try {
      const supabase = getSupabaseClient();
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}${window.location.pathname}?auth=success`,
          queryParams: {
            access_type: 'offline',
            prompt: 'consent',
          },
        },
      });

      if (error) {
        throw error;
      }
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

  // Enviar magic link
  const sendMagicLink = useCallback(async (email: string) => {
    // Validacion usando validador centralizado
    if (!isValidEmail(email)) {
      notifications.show({
        title: 'Email invalido',
        message: 'Ingresa un email valido',
        color: 'red',
      });
      return;
    }

    setLoading(true);
    try {
      const supabase = getSupabaseClient();
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: {
          emailRedirectTo: `${window.location.origin}${window.location.pathname}?auth=success`,
        },
      });

      if (error) {
        throw error;
      }

      setMagicLinkSent(true);
      setMagicLinkEmail(email);
      notifications.show({
        title: 'Link enviado',
        message: `Revisa tu email ${email}`,
        color: 'green',
      });
    } catch (error) {
      logger.error('Error enviando magic link:', error);
      const message = error instanceof Error ? error.message : 'No se pudo enviar el email';
      notifications.show({
        title: 'Error',
        message,
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  }, []);

  // Logout
  const logout = useCallback(async () => {
    try {
      const supabase = getSupabaseClient();
      await supabase.auth.signOut();
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
