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

      setEnviando(true);
      announce('Enviando denuncia...');

      try {
        // Two-step flow: create the denuncia FIRST, then attach the photo.
        // The previous order (upload then create) was impossible because
        // the upload endpoint needs the denuncia's id in the URL. Photo
        // failure is non-fatal — denuncia still saves.
        const result = await publicApi.createReport({
          tipo: values.tipo,
          descripcion: values.descripcion,
          latitud: ubicacion.lat,
          longitud: ubicacion.lng,
          contacto_email: userEmail,
          contacto_nombre: userName || undefined,
        });

        await uploadPhotoIfExists(result.id, values.foto, announce);

        showNotification(
          'Denuncia enviada',
          result.message || 'Tu denuncia fue registrada correctamente. Gracias por colaborar.',
          'green'
        );
        announce('Denuncia enviada exitosamente. Gracias por colaborar.');

        form.reset();
        setUbicacion(null);
        setFotoPreview(null);
      } catch (error) {
        logger.error('Error enviando denuncia:', error);
        const message =
          error instanceof Error
            ? error.message
            : 'No se pudo enviar la denuncia. Intenta nuevamente.';
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
      setEnviando,
      setFotoPreview,
      setUbicacion,
      ubicacion,
      userEmail,
      userName,
    ]
  );
}
