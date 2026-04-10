import { useCallback } from 'react';
import { publicApi } from '../../lib/api';
import { logger } from '../../lib/logger';
import { showNotification, uploadPhotoIfExists } from './reportFormUtils';
import type { Ubicacion } from './reportFormTypes';

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
        const fotoUrl = await uploadPhotoIfExists(values.foto, announce);

        const result = await publicApi.createReport({
          tipo: values.tipo,
          descripcion: values.descripcion,
          latitud: ubicacion.lat,
          longitud: ubicacion.lng,
          foto_url: fotoUrl,
          contacto_email: userEmail,
          contacto_nombre: userName || undefined,
        });

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
