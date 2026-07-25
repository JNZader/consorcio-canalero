import { useCallback, useEffect, useState } from 'react';
import { sugerenciasApi } from '../../lib/api';
import { logger } from '../../lib/logger';
import type { DrawnLineFeatureCollection } from '../map/LineDrawControl';
import { buildSugerenciaPayload, showSuggestionNotification } from './suggestionFormUtils';

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
    // El endpoint exige auth — si el usuario no verificó contacto/login
    // todavía, simplemente no consultamos el cupo (el backend rechazaría
    // con 401). El badge muestra `null` hasta que haya login real.
    if (!userEmail) return;

    try {
      const limit = await sugerenciasApi.checkLimit();
      setRemainingToday(limit.remaining);

      if (limit.remaining <= 0) {
        showSuggestionNotification(
          'Limite alcanzado',
          'Llegaste al limite de 5 sugerencias cada 24 horas. Volve mas tarde.',
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
          'Llegaste al limite de 5 sugerencias cada 24 horas',
          'orange'
        );
        return;
      }

      setEnviando(true);

      try {
        await sugerenciasApi.create(buildSugerenciaPayload(values, userEmail, userName, geometry));
        showSuggestionNotification(
          'Sugerencia enviada',
          'Tu propuesta fue recibida. La comisión la verá en su próxima reunión.',
          'green'
        );
        // Decrement locally — la base sigue siendo source of truth, pero
        // refrescar con un GET extra es desperdicio: el delta es siempre
        // -1. Si el usuario refresca la página, el badge se sincroniza
        // contra el endpoint real en el `useEffect` de abajo.
        setRemainingToday((prev) => (prev === null ? null : Math.max(0, prev - 1)));
        setEnviado(true);
        form.reset();
        setGeometry(null);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'No se pudo enviar la sugerencia';
        // 429 → backend dice "te quedaste sin cupo". Reflejamos en UI
        // forzando `remainingToday=0` para que el badge muestre "0
        // restantes" y el botón quede deshabilitado.
        if (
          message.includes('429') ||
          message.toLowerCase().includes('límite') ||
          message.toLowerCase().includes('limite')
        ) {
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
