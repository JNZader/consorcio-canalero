import type { UseFormReturnType } from '@mantine/form';
import { useCallback, useEffect, useState } from 'react';
import type { Ubicacion } from './reportFormTypes';
import { handleGeoError, handleGeoSuccess, showNotification } from './reportFormUtils';

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

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('ubicacion') !== 'elegida') return;
    // `params.get` devuelve null si la key no está y `Number(null) === 0`,
    // que SÍ pasa `Number.isFinite` — sin este guard una URL con
    // `ubicacion=elegida` pero sin lat/lng prefilleaba Null Island
    // {lat: 0, lng: 0}. El string vacío tampoco es una coordenada.
    const latRaw = params.get('lat');
    const lngRaw = params.get('lng');
    if (!latRaw || !lngRaw) return;
    const lat = Number(latRaw);
    const lng = Number(lngRaw);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    // Coordenada fuera de rango = URL corrupta; mejor no prefilar nada
    // (lat=999 no existe en la Tierra).
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return;
    setUbicacion({ lat, lng });
    setMostrarInputManual(true);
  }, []);

  const obtenerUbicacionGPS = useCallback(() => {
    if (!navigator.geolocation) {
      showNotification('Error', 'Tu navegador no soporta geolocalizacion', 'red');
      announce('Tu navegador no soporta geolocalizacion', 'assertive');
      return;
    }

    setObteniendoUbicacion(true);
    announce('Obteniendo ubicación GPS...');
    navigator.geolocation.getCurrentPosition(
      (position) => handleGeoSuccess(position, setUbicacion, setObteniendoUbicacion, announce),
      () => handleGeoError(setObteniendoUbicacion, announce),
      { enableHighAccuracy: true }
    );
  }, [announce]);

  const handleLocationSelect = useCallback(
    (lat: number, lng: number) => {
      setUbicacion({ lat, lng });
      announce(`Ubicación seleccionada: latitud ${lat.toFixed(4)}, longitud ${lng.toFixed(4)}`);
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
