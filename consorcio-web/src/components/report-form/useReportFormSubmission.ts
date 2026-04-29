import { useCallback } from 'react';
import { publicApi } from '../../lib/api';
import { logger } from '../../lib/logger';
import type { Ubicacion } from './reportFormTypes';
import { showNotification, uploadPhotoIfExists } from './reportFormUtils';

interface ReportFormValues {
  tipo: string;
  descripcion: string;
  foto: File | null;
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
}: Readonly<UseReportFormSubmissionParams>) {
  return useCallback(
    async (values: ReportFormValues) => {
      if (!contactoVerificado || !userEmail) {
        showNotification(
          'Identidad no verificada',
          'Debes verificar tu identidad antes de enviar la denuncia',
          'orange'
        );
        announce('Debes verificar tu identidad antes de enviar la denuncia', 'assertive');
        return;
      }

      if (!ubicacion) {
        showNotification(
          'Ubicacion requerida',
          'Debes seleccionar una ubicacion en el mapa',
          'orange'
        );
        announce('Debes seleccionar una ubicacion para la denuncia', 'assertive');
        return;
      }

      // Frontend gate ANTES de pegarle al backend — el server enforce
      // el mismo límite (HTTPException 429), pero evitar el round-trip
      // hace la UX mucho más rápida y permite mostrar mensajes claros.
      if (remainingToday !== null && remainingToday <= 0) {
        showNotification(
          'Limite alcanzado',
          'Llegaste al limite de 5 reportes cada 24 horas. Volve mas tarde.',
          'orange'
        );
        announce('Llegaste al limite de reportes por 24 horas', 'assertive');
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
        onSubmitSuccess();

        form.reset();
        setUbicacion(null);
        setFotoPreview(null);
      } catch (error) {
        logger.error('Error enviando denuncia:', error);
        const message =
          error instanceof Error
            ? error.message
            : 'No se pudo enviar la denuncia. Intenta nuevamente.';
        // 429 → backend dice que llegaste al límite. Sincronizamos UI.
        if (
          message.includes('429') ||
          message.toLowerCase().includes('límite') ||
          message.toLowerCase().includes('limite')
        ) {
          onLimitReached();
        }
        showNotification('Error', message, 'red');
        announce('Error al enviar la denuncia. Intenta nuevamente.', 'assertive');
      } finally {
        setEnviando(false);
      }
    },
    [
      announce,
      contactoVerificado,
      form,
      onLimitReached,
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
