import { useCallback, useEffect, useState } from 'react';
import { sugerenciasApi } from '../../lib/api';
import { logger } from '../../lib/logger';
import type { DrawnLineFeatureCollection } from '../map/LineDrawControl';
import {
  buildSugerenciaPayload,
  getContactForRateLimit,
  showSuggestionNotification,
} from './suggestionFormUtils';

interface SuggestionValues {
  titulo: string;
  descripcion: string;
  categoria: string;
}

interface UseSuggestionFormStateParams {
  contactoVerificado: boolean;
  userEmail: string | null;
  userName: string | null;
  resetVerificacion: () => void;
  logout: () => void;
  form: { reset: () => void };
  pendingRateLimitCheck?: boolean;
  onRateLimitChecked?: () => void;
}

export function useSuggestionFormState({
  contactoVerificado,
  userEmail,
  userName,
  resetVerificacion,
  logout,
  form,
  pendingRateLimitCheck = false,
  onRateLimitChecked,
}: Readonly<UseSuggestionFormStateParams>) {
  const [enviando, setEnviando] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const [remainingToday, setRemainingToday] = useState<number | null>(null);
  const [geometry, setGeometry] = useState<DrawnLineFeatureCollection | null>(null);

  const checkRateLimit = useCallback(async () => {
    const { email } = getContactForRateLimit(userEmail);
    if (!email) return;

    try {
      const limit = await sugerenciasApi.checkLimit(email);
      setRemainingToday(limit.remaining);

      if (limit.remaining <= 0) {
        showSuggestionNotification(
          'Limite alcanzado',
          'Has alcanzado el limite de 3 sugerencias por dia. Intenta manana.',
          'orange'
        );
      }
    } catch (error) {
      logger.error('Error checking rate limit:', error);
    }
  }, [userEmail]);

  useEffect(() => {
    if (!pendingRateLimitCheck || !contactoVerificado) return;
    void checkRateLimit().finally(() => {
      onRateLimitChecked?.();
    });
  }, [checkRateLimit, contactoVerificado, onRateLimitChecked, pendingRateLimitCheck]);

  const handleCambiarContacto = useCallback(() => {
    logout();
    resetVerificacion();
  }, [logout, resetVerificacion]);

  const handleSubmit = useCallback(
    async (values: SuggestionValues) => {
      if (!contactoVerificado) {
        showSuggestionNotification(
          'Contacto no verificado',
          'Debes verificar tu identidad antes de enviar',
          'orange'
        );
        return;
      }

      if (remainingToday !== null && remainingToday <= 0) {
        showSuggestionNotification(
          'Limite alcanzado',
          'Has alcanzado el limite de sugerencias por dia',
          'orange'
        );
        return;
      }

      setEnviando(true);

      try {
        const result = await sugerenciasApi.createPublic(
          buildSugerenciaPayload(values, userEmail, userName, geometry)
        );
        showSuggestionNotification('Sugerencia enviada', result.message, 'green');
        setRemainingToday(result.remaining_today);
        setEnviado(true);
        form.reset();
        setGeometry(null);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'No se pudo enviar la sugerencia';
        if (message.includes('limite')) {
          setRemainingToday(0);
        }
        showSuggestionNotification('Error', message, 'red');
      } finally {
        setEnviando(false);
      }
    },
    [contactoVerificado, form, geometry, remainingToday, userEmail, userName]
  );

  const resetSuccess = useCallback(() => {
    setEnviado(false);
    resetVerificacion();
  }, [resetVerificacion]);

  return {
    checkRateLimit,
    enviando,
    enviado,
    geometry,
    handleCambiarContacto,
    handleSubmit,
    remainingToday,
    resetSuccess,
    setGeometry,
  };
}
