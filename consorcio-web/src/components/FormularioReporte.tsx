import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Collapse,
  Divider,
  Group,
  Image,
  LoadingOverlay,
  Overlay,
  Paper,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  Textarea,
  Title,
} from '@mantine/core';
import { Dropzone, IMAGE_MIME_TYPE } from '@mantine/dropzone';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import L from 'leaflet';
import { useCallback, useState } from 'react';
import type { ReactNode } from 'react';
import { MapContainer, Marker, TileLayer, useMapEvents } from 'react-leaflet';
import { MAP_CENTER, TIPOS_DENUNCIA as TIPOS_DENUNCIA_BASE } from '../constants';
import { useConfigStore } from '../stores/configStore';
import { useContactVerification } from '../hooks/useContactVerification';
import { publicApi } from '../lib/api';
import { logger } from '../lib/logger';
import {
  AccessibleRadioGroup,
  CoordinatesInput,
  LiveRegionProvider,
  useLiveRegion,
} from './ui/accessibility';
import {
  IconBuildingBridge,
  IconDroplet,
  IconFileDescription,
  IconRoad,
  IconShieldCheck,
} from './ui/icons';
import { ContactVerificationSection } from './verification';
import 'leaflet/dist/leaflet.css';
import formStyles from '../styles/components/form.module.css';

// Fix para el icono de Leaflet
const markerIcon = new L.Icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

// Icon mapping for report types (extends base TIPOS_DENUNCIA from constants)
const TIPO_ICONS: Record<string, ReactNode> = {
  alcantarilla_tapada: <IconBuildingBridge size={24} />,
  desborde: <IconDroplet size={24} />,
  camino_danado: <IconRoad size={24} />,
  otro: <IconFileDescription size={24} />,
};

// Extend base types with icons
const TIPOS_DENUNCIA = TIPOS_DENUNCIA_BASE.map((tipo) => ({
  ...tipo,
  icon: TIPO_ICONS[tipo.value] ?? <IconFileDescription size={24} />,
}));

interface Ubicacion {
  lat: number;
  lng: number;
}

// Helper: Show notification
function showNotification(title: string, message: string, color: string) {
  notifications.show({ title, message, color });
}

// Componente para seleccionar ubicacion en el mapa
function LocationPicker({
  onLocationSelect,
  currentLocation,
}: Readonly<{
  onLocationSelect: (lat: number, lng: number) => void;
  currentLocation: Ubicacion | null;
}>) {
  useMapEvents({
    click(e) {
      const { lat, lng } = e.latlng;
      onLocationSelect(lat, lng);
    },
  });

  if (!currentLocation) return null;
  return <Marker position={[currentLocation.lat, currentLocation.lng]} icon={markerIcon} />;
}

// Extracted: Location section
function LocationSection({
  ubicacion,
  mostrarInputManual,
  obteniendoUbicacion,
  onObtenerGPS,
  onToggleInputManual,
  onLocationSelect,
  onCoordinatesChange,
  onClearLocation,
  defaultCenter = MAP_CENTER,
  defaultZoom = 12,
}: Readonly<{
  ubicacion: Ubicacion | null;
  mostrarInputManual: boolean;
  obteniendoUbicacion: boolean;
  onObtenerGPS: () => void;
  onToggleInputManual: () => void;
  onLocationSelect: (lat: number, lng: number) => void;
  onCoordinatesChange: (lat: number, lng: number) => void;
  onClearLocation: () => void;
  defaultCenter?: [number, number];
  defaultZoom?: number;
}>) {
  return (
    <>
      <Group gap="sm" mb="sm">
        <Button
          onClick={onObtenerGPS}
          loading={obteniendoUbicacion}
          variant="light"
          size="sm"
          leftSection={<span aria-hidden="true">&#128205;</span>}
        >
          Usar mi ubicacion GPS
        </Button>
        <Button
          onClick={onToggleInputManual}
          variant="subtle"
          size="sm"
          aria-expanded={mostrarInputManual}
          aria-controls="input-coordenadas-manual"
        >
          {mostrarInputManual ? 'Ocultar entrada manual' : 'Ingresar coordenadas manualmente'}
        </Button>
        {ubicacion && (
          <Group gap="xs">
            <Badge color="green" variant="light">
              {ubicacion.lat.toFixed(5)}, {ubicacion.lng.toFixed(5)}
            </Badge>
            <Button size="xs" variant="subtle" color="red" onClick={onClearLocation}>
              Limpiar
            </Button>
          </Group>
        )}
      </Group>

      <Collapse in={mostrarInputManual}>
        <Box id="input-coordenadas-manual" mb="md">
          <CoordinatesInput
            onCoordinatesChange={onCoordinatesChange}
            currentLat={ubicacion?.lat}
            currentLng={ubicacion?.lng}
          />
        </Box>
      </Collapse>

      <Box
        className={formStyles.mapContainer}
        role="application"
        aria-label="Mapa interactivo para seleccionar ubicacion. Haz clic en el mapa para marcar la ubicacion del incidente. Alternativa: usa el boton 'Ingresar coordenadas manualmente' arriba."
      >
        <MapContainer
          center={ubicacion ? [ubicacion.lat, ubicacion.lng] : defaultCenter}
          zoom={defaultZoom}
          style={{ width: '100%', height: '100%' }}
          scrollWheelZoom={true}
        >
          <TileLayer
            attribution="&copy; OpenStreetMap"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <LocationPicker onLocationSelect={onLocationSelect} currentLocation={ubicacion} />
        </MapContainer>
      </Box>
      <Text size="xs" c="gray.6" mt="xs">
        Haz clic en el mapa para marcar la ubicacion exacta del incidente, o usa la opcion de
        ingreso manual de coordenadas.
      </Text>
    </>
  );
}

// Extracted: Photo upload section
function PhotoSection({
  fotoPreview,
  onDrop,
  onRemove,
}: Readonly<{
  fotoPreview: string | null;
  onDrop: (files: File[]) => void;
  onRemove: () => void;
}>) {
  if (fotoPreview) {
    return (
      <Box pos="relative">
        <Image
          src={fotoPreview}
          alt="Vista previa de la foto adjunta a la denuncia"
          radius="md"
          h={200}
          fit="cover"
        />
        <ActionIcon
          pos="absolute"
          top={8}
          right={8}
          color="red"
          variant="filled"
          onClick={onRemove}
          aria-label="Eliminar foto adjunta"
        >
          X
        </ActionIcon>
      </Box>
    );
  }

  return (
    <Dropzone
      onDrop={onDrop}
      accept={IMAGE_MIME_TYPE}
      maxSize={5 * 1024 * 1024}
      maxFiles={1}
      aria-labelledby="foto-label"
    >
      <Group justify="center" gap="xl" mih={120} style={{ pointerEvents: 'none' }}>
        <div>
          <Text size="xl" ta="center" aria-hidden="true">
            &#128247;
          </Text>
          <Text size="sm" c="gray.6" ta="center">
            Arrastra una foto o haz clic para seleccionar
          </Text>
          <Text size="xs" c="gray.6" ta="center">
            Max 5MB
          </Text>
        </div>
      </Group>
    </Dropzone>
  );
}

// Helper: Get badge variant based on state
function getBadgeVariant(isPrimary: boolean, isComplete: boolean): 'filled' | 'light' | 'outline' {
  if (isPrimary) return isComplete ? 'filled' : 'light';
  return isComplete ? 'light' : 'outline';
}

// Helper: Get badge color based on state
function getBadgeColor(isPrimary: boolean, isComplete: boolean): string {
  if (isPrimary) return isComplete ? 'green' : 'blue';
  return isComplete ? 'blue' : 'gray';
}

// Extracted: Step header badge component
function StepHeader({
  step,
  title,
  subtitle,
  isComplete,
  showCheckIcon,
  variant = 'primary',
}: Readonly<{
  step: number;
  title: string;
  subtitle: string;
  isComplete: boolean;
  showCheckIcon?: boolean;
  variant?: 'primary' | 'secondary';
}>) {
  const isPrimary = variant === 'primary';
  const badgeVariant = getBadgeVariant(isPrimary, isComplete);
  const badgeColor = getBadgeColor(isPrimary, isComplete);

  return (
    <Group gap="sm" mb="md">
      <Badge size="lg" radius="xl" variant={badgeVariant} color={badgeColor}>
        {step}
      </Badge>
      <Box>
        <Text fw={600} size="sm" c={!isPrimary && !isComplete ? 'dimmed' : undefined}>
          {title}
        </Text>
        <Text size="xs" c="gray.6">
          {subtitle}
        </Text>
      </Box>
      {showCheckIcon && <IconShieldCheck size={20} color="var(--mantine-color-green-6)" />}
    </Group>
  );
}

// Extracted: Tipo problema field - handles verified and skeleton states
function TipoProblemaField({
  contactoVerificado,
  value,
  error,
  onChange,
}: Readonly<{
  contactoVerificado: boolean;
  value: string;
  error?: string;
  onChange: (value: string) => void;
}>) {
  if (contactoVerificado) {
    return (
      <AccessibleRadioGroup
        name="tipo-denuncia"
        label="Tipo de problema"
        options={TIPOS_DENUNCIA}
        value={value}
        onChange={onChange}
        error={error}
        required
        columns={4}
      />
    );
  }

  return (
    <Box>
      <Text fw={500} size="sm" mb="xs">
        Tipo de problema *
      </Text>
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} height={70} radius="md" />
        ))}
      </SimpleGrid>
    </Box>
  );
}

// Extracted: Descripcion field - handles verified and skeleton states
function DescripcionField({
  contactoVerificado,
  error,
  getInputProps,
}: Readonly<{
  contactoVerificado: boolean;
  error?: string;
  getInputProps: (field: string) => object;
}>) {
  if (contactoVerificado) {
    return (
      <Box>
        <Textarea
          label="Descripcion"
          placeholder="Describe el problema con el mayor detalle posible..."
          minRows={4}
          {...getInputProps('descripcion')}
          required
          aria-describedby={error ? 'descripcion-error' : undefined}
        />
        {error && (
          <Text id="descripcion-error" size="xs" c="red" mt="xs" role="alert">
            {error}
          </Text>
        )}
      </Box>
    );
  }

  return (
    <Box>
      <Text size="sm" fw={500} mb="xs">
        Descripcion *
      </Text>
      <Skeleton height={100} radius="sm" />
    </Box>
  );
}

// Extracted: Ubicacion field - handles verified and skeleton states
function UbicacionField({
  contactoVerificado,
  ubicacion,
  mostrarInputManual,
  obteniendoUbicacion,
  onObtenerGPS,
  onToggleInputManual,
  onLocationSelect,
  onCoordinatesChange,
  onClearLocation,
  defaultCenter,
  defaultZoom,
}: Readonly<{
  contactoVerificado: boolean;
  ubicacion: Ubicacion | null;
  mostrarInputManual: boolean;
  obteniendoUbicacion: boolean;
  onObtenerGPS: () => void;
  onToggleInputManual: () => void;
  onLocationSelect: (lat: number, lng: number) => void;
  onCoordinatesChange: (lat: number, lng: number) => void;
  onClearLocation: () => void;
  defaultCenter?: [number, number];
  defaultZoom?: number;
}>) {
  return (
    <Box>
      <Text fw={500} size="sm" mb="xs" id="ubicacion-label">
        Ubicacion del incidente *
      </Text>
      {contactoVerificado ? (
        <LocationSection
          ubicacion={ubicacion}
          mostrarInputManual={mostrarInputManual}
          obteniendoUbicacion={obteniendoUbicacion}
          onObtenerGPS={onObtenerGPS}
          onToggleInputManual={onToggleInputManual}
          onLocationSelect={onLocationSelect}
          onCoordinatesChange={onCoordinatesChange}
          onClearLocation={onClearLocation}
          defaultCenter={defaultCenter}
          defaultZoom={defaultZoom}
        />
      ) : (
        <>
          <Skeleton height={36} width={180} radius="sm" mb="sm" />
          <Skeleton height={300} radius="md" />
        </>
      )}
    </Box>
  );
}

// Extracted: Foto field - handles verified and skeleton states
function FotoField({
  contactoVerificado,
  fotoPreview,
  onDrop,
  onRemove,
}: Readonly<{
  contactoVerificado: boolean;
  fotoPreview: string | null;
  onDrop: (files: File[]) => void;
  onRemove: () => void;
}>) {
  return (
    <Box>
      <Text fw={500} size="sm" mb="xs" id="foto-label">
        Foto (opcional)
      </Text>
      {contactoVerificado ? (
        <PhotoSection fotoPreview={fotoPreview} onDrop={onDrop} onRemove={onRemove} />
      ) : (
        <Skeleton height={120} radius="md" />
      )}
    </Box>
  );
}

// Extracted: Submit button - handles verified and skeleton states
function SubmitButton({
  contactoVerificado,
  disabled,
}: Readonly<{
  contactoVerificado: boolean;
  disabled: boolean;
}>) {
  if (contactoVerificado) {
    return (
      <Button type="submit" size="lg" fullWidth disabled={disabled}>
        Enviar Reporte
      </Button>
    );
  }
  return <Skeleton height={50} radius="md" />;
}

// Helper: Handle geolocation success
function handleGeoSuccess(
  position: GeolocationPosition,
  setUbicacion: (u: Ubicacion) => void,
  setObteniendoUbicacion: (b: boolean) => void,
  announce: (msg: string) => void
) {
  const { latitude, longitude } = position.coords;
  setUbicacion({ lat: latitude, lng: longitude });
  setObteniendoUbicacion(false);
  showNotification('Ubicacion obtenida', 'Se detecto tu ubicacion correctamente', 'green');
  announce(`Ubicacion obtenida: latitud ${latitude.toFixed(4)}, longitud ${longitude.toFixed(4)}`);
}

// Helper: Handle geolocation error
function handleGeoError(
  setObteniendoUbicacion: (b: boolean) => void,
  announce: (msg: string, priority?: 'polite' | 'assertive') => void
) {
  setObteniendoUbicacion(false);
  showNotification(
    'Error de ubicacion',
    'No se pudo obtener tu ubicacion. Selecciona en el mapa.',
    'red'
  );
  announce(
    'No se pudo obtener tu ubicacion. Usa el mapa o ingresa coordenadas manualmente.',
    'assertive'
  );
}

// Helper: Upload photo if exists
async function uploadPhotoIfExists(
  foto: File | null,
  _announce: (msg: string) => void
): Promise<string | undefined> {
  if (!foto) return undefined;

  try {
    const uploadResult = await publicApi.uploadPhoto(foto);
    return uploadResult.photo_url;
  } catch (error) {
    logger.error('Error subiendo foto:', error);
    showNotification(
      'Aviso',
      'No se pudo subir la foto, pero la denuncia se enviara sin ella.',
      'yellow'
    );
    return undefined;
  }
}

function FormularioContenido() {
  const config = useConfigStore((state) => state.config);

  const defaultCenter = config?.map.center
    ? ([config.map.center.lat, config.map.center.lng] as [number, number])
    : MAP_CENTER;
  const defaultZoom = config?.map.zoom ? config.map.zoom + 1 : 12;

  const [ubicacion, setUbicacion] = useState<Ubicacion | null>(null);
  const [obteniendoUbicacion, setObteniendoUbicacion] = useState(false);
  const [fotoPreview, setFotoPreview] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [mostrarInputManual, setMostrarInputManual] = useState(false);

  // Hook para anuncios de accesibilidad
  const { announce } = useLiveRegion();

  const form = useForm({
    initialValues: {
      tipo: '',
      descripcion: '',
      foto: null as File | null,
    },
    validate: {
      tipo: (value) => (!value ? 'Selecciona un tipo de denuncia' : null),
      descripcion: (value) =>
        value.length < 10 ? 'La descripcion debe tener al menos 10 caracteres' : null,
    },
  });

  // Hook de verificacion de contacto (Google OAuth + Magic Link)
  const {
    contactoVerificado,
    userEmail,
    userName,
    metodoVerificacion,
    loading,
    magicLinkSent,
    magicLinkEmail,
    setMetodoVerificacion,
    loginWithGoogle,
    sendMagicLink,
    logout,
  } = useContactVerification({
    onVerified: (email, name) => {
      const displayName = name || email;
      announce(`Identidad verificada como ${displayName}. Puedes continuar con la denuncia.`);
    },
  });

  const obtenerUbicacionGPS = () => {
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
  };

  const handleLocationSelect = (lat: number, lng: number) => {
    setUbicacion({ lat, lng });
    announce(`Ubicacion seleccionada: latitud ${lat.toFixed(4)}, longitud ${lng.toFixed(4)}`);
  };

  const handleCoordinatesChange = (lat: number, lng: number) => {
    setUbicacion({ lat, lng });
  };

  const handleDrop = (files: File[]) => {
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
  };

  const handleRemoveFoto = useCallback(() => {
    setFotoPreview(null);
    form.setFieldValue('foto', null);
    announce('Foto eliminada');
  }, [form, announce]);

  const handleToggleInputManual = useCallback(() => {
    setMostrarInputManual((prev) => !prev);
  }, []);

  const handleClearLocation = useCallback(() => {
    setUbicacion(null);
  }, []);

  const handleSubmit = useCallback(
    async (values: typeof form.values) => {
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

        // Reset form y estados
        form.reset();
        setUbicacion(null);
        setFotoPreview(null);
      } catch (error) {
        logger.error('Error enviando denuncia:', error);
        const message =
          error instanceof Error ? error.message : 'No se pudo enviar la denuncia. Intenta nuevamente.';
        showNotification('Error', message, 'red');
        announce('Error al enviar la denuncia. Intenta nuevamente.', 'assertive');
      } finally {
        setEnviando(false);
      }
    },
    [ubicacion, form, contactoVerificado, userEmail, userName, announce]
  );

  /**
   * Helper to safely extract error string from Mantine form errors.
   */
  function getErrorString(error: ReactNode): string | undefined {
    if (typeof error === 'string') {
      return error;
    }
    return undefined;
  }

  return (
    <Paper shadow="md" p="xl" radius="md" pos="relative">
      <LoadingOverlay visible={enviando} />

      <Title order={2} mb="md">
        Nuevo Reporte
      </Title>
      <Text c="gray.6" mb="xl">
        Reporta problemas en la red de canales y caminos rurales
      </Text>

      {/* SECCION 1: Verificacion de identidad */}
      <Box mb="xl">
        <StepHeader
          step={1}
          title="Verificar identidad"
          subtitle={contactoVerificado ? 'Verificado' : 'Obligatorio'}
          isComplete={contactoVerificado}
          showCheckIcon={contactoVerificado}
        />

        <Stack gap="md">
          <ContactVerificationSection
            contactoVerificado={contactoVerificado}
            userEmail={userEmail}
            userName={userName}
            metodoVerificacion={metodoVerificacion}
            loading={loading}
            magicLinkSent={magicLinkSent}
            magicLinkEmail={magicLinkEmail}
            onMetodoChange={setMetodoVerificacion}
            onLoginWithGoogle={loginWithGoogle}
            onSendMagicLink={sendMagicLink}
            onLogout={logout}
          />
        </Stack>
      </Box>

      <Divider my="xl" />

      {/* SECCION 2: Formulario de denuncia (siempre visible, bloqueado si no verificado) */}
      <Box pos="relative">
        {/* Overlay blur cuando no verificado */}
        {!contactoVerificado && (
          <Overlay
            style={{ background: 'light-dark(rgba(255,255,255,0.6), rgba(36,36,36,0.6))' }}
            backgroundOpacity={0}
            blur={2}
            zIndex={5}
            radius="md"
          />
        )}

        <StepHeader
          step={2}
          title="Completar reporte"
          subtitle="Detalles del incidente"
          isComplete={contactoVerificado}
          variant="secondary"
        />

        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack gap="lg">
            {/* Tipo de denuncia - usando AccessibleRadioGroup para navegacion por teclado WCAG 2.1.1 */}
            <TipoProblemaField
              contactoVerificado={contactoVerificado}
              value={form.values.tipo}
              error={getErrorString(form.errors.tipo)}
              onChange={(value) => form.setFieldValue('tipo', value)}
            />

            {/* Descripcion */}
            <DescripcionField
              contactoVerificado={contactoVerificado}
              error={getErrorString(form.errors.descripcion)}
              getInputProps={form.getInputProps}
            />

            {/* Ubicacion */}
            <UbicacionField
              contactoVerificado={contactoVerificado}
              ubicacion={ubicacion}
              mostrarInputManual={mostrarInputManual}
              obteniendoUbicacion={obteniendoUbicacion}
              onObtenerGPS={obtenerUbicacionGPS}
              onToggleInputManual={handleToggleInputManual}
              onLocationSelect={handleLocationSelect}
              onCoordinatesChange={handleCoordinatesChange}
              onClearLocation={handleClearLocation}
              defaultCenter={defaultCenter}
              defaultZoom={defaultZoom}
            />

            {/* Foto */}
            <FotoField
              contactoVerificado={contactoVerificado}
              fotoPreview={fotoPreview}
              onDrop={handleDrop}
              onRemove={handleRemoveFoto}
            />

            {/* Submit */}
            <SubmitButton contactoVerificado={contactoVerificado} disabled={!ubicacion} />
          </Stack>
        </form>
      </Box>
    </Paper>
  );
}

// Export internal component for use within other MantineProvider contexts
export { FormularioContenido };

export default function FormularioReporte() {
  return (
    <LiveRegionProvider>
      <FormularioContenido />
    </LiveRegionProvider>
  );
}
