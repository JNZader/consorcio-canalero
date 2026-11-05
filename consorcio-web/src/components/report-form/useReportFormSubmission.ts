import { useCallback } from 'react';
import { publicApi } from '../../lib/api';
import {
  clearReportDraft,
  fileToDraftDataUrl,
  MAX_DRAFT_PHOTO_BYTES,
  saveReportDraft,
} from '../../lib/formDrafts';
import { logger } from '../../lib/logger';
import { erroresUi, textoError } from '../../lib/userFacingError';
import type { Ubicacion } from './reportFormTypes';
import {
  isOfflineSubmitError,
  OFFLINE_SUBMIT_MESSAGE,
  showNotification,
  uploadPhotoIfExists,
} from './reportFormUtils';

interface ReportFormValues {
  tipo: string;
  descripcion: string;
  foto: File | null;
}

interface SubmitFailureHandlers {
  announce: (msg: string, priority?: 'polite' | 'assertive') => void;
  onLimitReached: () => void;
  onOfflineFailure?: () => void;
  onOtherFailure?: () => void;
}

/** Deja el intento en sessionStorage por si la página se recarga sin red. */
async function rememberReportDraft(values: ReportFormValues, ubicacion: Ubicacion | null) {
  let fotoDataUrl: string | undefined;
  if (values.foto && values.foto.size <= MAX_DRAFT_PHOTO_BYTES) {
    fotoDataUrl = (await fileToDraftDataUrl(values.foto)) ?? undefined;
  }
  saveReportDraft({
    tipo: values.tipo,
    descripcion: values.descripcion,
    lat: ubicacion?.lat,
    lng: ubicacion?.lng,
    ...(fotoDataUrl
      ? {
          fotoDataUrl,
          fotoName: values.foto?.name,
          fotoType: values.foto?.type,
        }
      : {}),
  });
}

async function reportSubmitFailure(
  error: unknown,
  values: ReportFormValues,
  ubicacion: Ubicacion | null,
  handlers: SubmitFailureHandlers
) {
  logger.error('Error enviando denuncia:', error);
  if (isOfflineSubmitError(error)) {
    await rememberReportDraft(values, ubicacion);
    handlers.onOfflineFailure?.();
    handlers.announce(`${OFFLINE_SUBMIT_MESSAGE} Podés reintentar.`, 'assertive');
    return;
  }
  handlers.onOtherFailure?.();
  const message =
    error instanceof Error ? error.message : 'No se pudo enviar la denuncia. Intentá nuevamente.';
  // 429 → backend dice que llegaste al límite. Sincronizamos UI.
  if (
    message.includes('429') ||
    message.toLowerCase().includes('límite') ||
    message.toLowerCase().includes('limite')
  ) {
    handlers.onLimitReached();
  }
  showNotification('Error', message, 'red');
  handlers.announce(textoError(erroresUi.enviarDenuncia), 'assertive');
}

interface UseReportFormSubmissionParams {
  contactoVerificado: boolean;
  userEmail: string | null;
  userName: string | null;
  ubicacion: Ubicacion | null;
  announce: (msg: string, priority?: 'polite' | 'assertive') => void;
  form: {
    values: ReportFormValues;
    reset: () => void;
  };
  setEnviando: (value: boolean) => void;
  setUbicacion: (value: Ubicacion | null) => void;
  setFotoPreview: (value: string | null) => void;
  /** Cupo restante del usuario (`null` = no consultado todavía). */
  remainingToday: number | null;
  /** Llamado tras un create exitoso — decremento local. */
  onSubmitSuccess: () => void;
  /** Llamado si el server devuelve 429 — fija remaining=0. */
  onLimitReached: () => void;
  /** POST offline (503 del service worker o fallo de red). El form no se vacía. */
  onOfflineFailure?: () => void;
  /** Otro error de envío: cierra el aviso de sin conexión si estaba abierto. */
  onOtherFailure?: () => void;
}

export function useReportFormSubmission({
  contactoVerificado,
  userEmail,
  userName,
  ubicacion,
  announce,
  form,
  setEnviando,
  setUbicacion,
  setFotoPreview,
  remainingToday,
  onSubmitSuccess,
  onLimitReached,
  onOfflineFailure,
  onOtherFailure,
}: Readonly<UseReportFormSubmissionParams>) {
  return useCallback(
    async (values: ReportFormValues) => {
      if (!contactoVerificado || !userEmail) {
        let fotoDataUrl: string | undefined;
        let fotoOversized = false;

        if (values.foto) {
          if (values.foto.size > MAX_DRAFT_PHOTO_BYTES) {
            fotoOversized = true;
          } else {
            fotoDataUrl = (await fileToDraftDataUrl(values.foto)) ?? undefined;
          }
        }

        saveReportDraft({
          tipo: values.tipo,
          descripcion: values.descripcion,
          lat: ubicacion?.lat,
          lng: ubicacion?.lng,
          ...(fotoDataUrl
            ? {
                fotoDataUrl,
                fotoName: values.foto?.name,
                fotoType: values.foto?.type,
              }
            : {}),
        });

        if (fotoOversized) {
          showNotification(
            'Identidad no verificada',
            'Guardamos el borrador, pero la foto supera 2 MB y deberás volver a adjuntarla tras iniciar sesión.',
            'orange'
          );
        } else {
          showNotification(
            'Identidad no verificada',
            fotoDataUrl
              ? 'Guardamos el borrador y la foto adjunta. Verificá tu identidad con Google o creá una cuenta para enviar.'
              : 'Guardamos el borrador. Verificá tu identidad con Google o creá una cuenta para enviar.',
            'orange'
          );
        }
        announce('Debés verificar tu identidad antes de enviar la denuncia', 'assertive');
        return;
      }

      if (!ubicacion) {
        showNotification(
          'Ubicación requerida',
          'Debés seleccionar una ubicación en el mapa',
          'orange'
        );
        announce('Debés seleccionar una ubicación para la denuncia', 'assertive');
        return;
      }

      // Frontend gate ANTES de pegarle al backend — el server enforce
      // el mismo límite (HTTPException 429), pero evitar el round-trip
      // hace la UX mucho más rápida y permite mostrar mensajes claros.
      if (remainingToday !== null && remainingToday <= 0) {
        showNotification(
          'Límite alcanzado',
          'Llegaste al límite de 5 reportes cada 24 horas. Volvé más tarde.',
          'orange'
        );
        announce('Llegaste al límite de reportes por 24 horas', 'assertive');
        return;
      }

      setEnviando(true);
      announce('Enviando denuncia...');

      try {
        // Two-step flow: create the denuncia FIRST, then attach the photo.
        // The endpoint needs the denuncia's id in the URL for step 2.
        // The server fills `user_id` + `contacto_email` from the JWT —
        // we only pass the form fields. Photo failure is non-fatal.
        const result = await publicApi.createReport({
          tipo: values.tipo,
          descripcion: values.descripcion,
          latitud: ubicacion.lat,
          longitud: ubicacion.lng,
        });

        await uploadPhotoIfExists(result.id, values.foto, announce);

        showNotification(
          'Denuncia enviada',
          result.message || 'Tu denuncia fue registrada correctamente. Gracias por colaborar.',
          'green'
        );
        announce('Denuncia enviada exitosamente. Gracias por colaborar.');
        clearReportDraft();
        onSubmitSuccess();

        form.reset();
        setUbicacion(null);
        setFotoPreview(null);
      } catch (error) {
        await reportSubmitFailure(error, values, ubicacion, {
          announce,
          onLimitReached,
          onOfflineFailure,
          onOtherFailure,
        });
      } finally {
        setEnviando(false);
      }
    },
    [
      announce,
      contactoVerificado,
      form,
      onLimitReached,
      onOfflineFailure,
      onOtherFailure,
      onSubmitSuccess,
      remainingToday,
      setEnviando,
      setFotoPreview,
      setUbicacion,
      ubicacion,
      userEmail,
      userName,
    ]
  );
}
