import { useCallback, useState } from 'react';
import type { UseFormReturnType } from '@mantine/form';
import { handleGeoError, handleGeoSuccess, showNotification } from './reportFormUtils';
import type { Ubicacion } from './reportFormTypes';

interface ReportFormValues {
  tipo: string;
  descripcion: string;
  foto: File | null;
}

interface UseReportLocationParams {
  announce: (msg: string, priority?: 'polite' | 'assertive') => void;
  form: UseFormReturnType<ReportFormValues>;
}

export function useReportLocation({ announce, form }: Readonly<UseReportLocationParams>) {
  const [ubicacion, setUbicacion] = useState<Ubicacion | null>(null);
  const [obteniendoUbicacion, setObteniendoUbicacion] = useState(false);
  const [mostrarInputManual, setMostrarInputManual] = useState(false);
  const [fotoPreview, setFotoPreview] = useState<string | null>(null);

  const obtenerUbicacionGPS = useCallback(() => {
    if (!navigator.geolocation) {
      showNotification('Error', 'Tu navegador no soporta geolocalizacion', 'red');
      announce('Tu navegador no soporta geolocalizacion', 'assertive');
      return;
    }

    setObteniendoUbicacion(true);
    announce('Obteniendo ubicacion GPS...');
    navigator.geolocation.getCurrentPosition(
      (position) => handleGeoSuccess(position, setUbicacion, setObteniendoUbicacion, announce),
      () => handleGeoError(setObteniendoUbicacion, announce),
      { enableHighAccuracy: true }
    );
  }, [announce]);

  const handleLocationSelect = useCallback(
    (lat: number, lng: number) => {
      setUbicacion({ lat, lng });
      announce(`Ubicacion seleccionada: latitud ${lat.toFixed(4)}, longitud ${lng.toFixed(4)}`);
    },
    [announce]
  );

  const handleCoordinatesChange = useCallback((lat: number, lng: number) => {
    setUbicacion({ lat, lng });
  }, []);

  const handleDrop = useCallback(
    (files: File[]) => {
      const file = files[0];
      if (!file) return;

      form.setFieldValue('foto', file);
      const reader = new FileReader();
      reader.onload = (e) => {
        const result = e.target?.result;
        if (typeof result === 'string') {
          setFotoPreview(result);
        }
      };
      reader.readAsDataURL(file);
      announce(`Foto seleccionada: ${file.name}`);
    },
    [announce, form]
  );

  const handleRemoveFoto = useCallback(() => {
    setFotoPreview(null);
    form.setFieldValue('foto', null);
    announce('Foto eliminada');
  }, [announce, form]);

  const handleToggleInputManual = useCallback(() => {
    setMostrarInputManual((prev) => !prev);
  }, []);

  const handleClearLocation = useCallback(() => {
    setUbicacion(null);
  }, []);

  return {
    fotoPreview,
    handleClearLocation,
    handleCoordinatesChange,
    handleDrop,
    handleLocationSelect,
    handleRemoveFoto,
    handleToggleInputManual,
    mostrarInputManual,
    obteniendoUbicacion,
    obtenerUbicacionGPS,
    setFotoPreview,
    setUbicacion,
    ubicacion,
  };
}
