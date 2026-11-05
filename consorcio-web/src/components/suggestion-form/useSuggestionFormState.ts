import { useCallback, useEffect, useRef, useState } from 'react';
import { sugerenciasApi } from '../../lib/api';
import { clearSuggestionDraft, saveSuggestionDraft } from '../../lib/formDrafts';
import { logger } from '../../lib/logger';
import { isOfflineSubmitError } from '../../lib/offlineSubmit';
import type { DrawnLineFeatureCollection } from '../map/LineDrawControl';
import {
  buildSugerenciaPayload,
  OFFLINE_SUBMIT_MESSAGE,
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
  logout: () => void;
  form: { reset: () => void };
  pendingRateLimitCheck?: boolean;
  onRateLimitChecked?: () => void;
  announce?: (msg: string, priority?: 'polite' | 'assertive') => void;
  /** POST offline (503 del service worker o fallo de red). El form no se vacía. */
  onOfflineFailure?: () => void;
  /** Otro error de envío: cierra el aviso de sin conexión si estaba abierto. */
  onOtherFailure?: () => void;
  /** Arranque real del POST. El formulario esconde el toast de reintento. */
  onAttemptStart?: () => void;
  /** Tras un create exitoso, además del decremento local. */
  onSubmitSuccess?: () => void;
}

export function useSuggestionFormState({
  contactoVerificado,
  userEmail,
  userName,
  logout,
  form,
  pendingRateLimitCheck = false,
  onRateLimitChecked,
  announce,
  onOfflineFailure,
  onOtherFailure,
  onAttemptStart,
  onSubmitSuccess,
}: Readonly<UseSuggestionFormStateParams>) {
  const [enviando, setEnviando] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const [remainingToday, setRemainingToday] = useState<number | null>(null);
  const [geometry, setGeometry] = useState<DrawnLineFeatureCollection | null>(null);
  // `enviando` en estado no alcanza: el segundo tap (doble clic o el toast)
  // reusa el callback que todavía ve `false`. El ref se toma en el mismo
  // turno, antes de cualquier await.
  const inFlightRef = useRef(false);

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
          'Límite alcanzado',
          'Llegaste al límite de 5 sugerencias cada 24 horas. Volvé más tarde.',
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
  }, [logout]);

  const handleSubmit = useCallback(
    async (values: SuggestionValues) => {
      if (!contactoVerificado) {
        saveSuggestionDraft({
          titulo: values.titulo,
          descripcion: values.descripcion,
          categoria: values.categoria,
          geometry,
        });
        showSuggestionNotification(
          'Contacto no verificado',
          'Guardamos el borrador. Verificá tu identidad con Google o creá una cuenta para enviar.',
          'orange'
        );
        return;
      }

      if (remainingToday !== null && remainingToday <= 0) {
        showSuggestionNotification(
          'Límite alcanzado',
          'Llegaste al límite de 5 sugerencias cada 24 horas',
          'orange'
        );
        return;
      }

      if (inFlightRef.current) return;
      inFlightRef.current = true;
      setEnviando(true);

      try {
        onAttemptStart?.();
        await sugerenciasApi.create(buildSugerenciaPayload(values, userEmail, userName, geometry));
        showSuggestionNotification(
          'Sugerencia enviada',
          'Tu propuesta fue recibida. La comisión la verá en su próxima reunión.',
          'green'
        );
        announce?.('Sugerencia enviada. La comisión la verá en su próxima reunión.');
        // Decrement locally — la base sigue siendo source of truth, pero
        // refrescar con un GET extra es desperdicio: el delta es siempre
        // -1. Si el usuario refresca la página, el badge se sincroniza
        // contra el endpoint real en el `useEffect` de abajo.
        setRemainingToday((prev) => (prev === null ? null : Math.max(0, prev - 1)));
        setEnviado(true);
        clearSuggestionDraft();
        onSubmitSuccess?.();
        form.reset();
        setGeometry(null);
      } catch (error) {
        if (isOfflineSubmitError(error)) {
          saveSuggestionDraft({
            titulo: values.titulo,
            descripcion: values.descripcion,
            categoria: values.categoria,
            geometry,
          });
          onOfflineFailure?.();
          announce?.(`${OFFLINE_SUBMIT_MESSAGE} Podés reintentar.`, 'assertive');
          return;
        }
        onOtherFailure?.();
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
        inFlightRef.current = false;
        setEnviando(false);
      }
    },
    [
      announce,
      contactoVerificado,
      form,
      geometry,
      onAttemptStart,
      onOfflineFailure,
      onOtherFailure,
      onSubmitSuccess,
      remainingToday,
      userEmail,
      userName,
    ]
  );

  const resetSuccess = useCallback(() => {
    setEnviado(false);
  }, []);

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
