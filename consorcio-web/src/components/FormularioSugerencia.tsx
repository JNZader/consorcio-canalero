import {
  Alert,
  Badge,
  Box,
  Button,
  Divider,
  Group,
  LoadingOverlay,
  Overlay,
  Paper,
  SegmentedControl,
  Select,
  Skeleton,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet';
import type { FeatureCollection } from 'geojson';
import { useContactVerification } from '../hooks/useContactVerification';
import { useWaterways } from '../hooks/useWaterways';
import { sugerenciasApi } from '../lib/api';
import { logger } from '../lib/logger';
import { MAX_LENGTHS, validators } from '../lib/validators';
import { LiveRegionProvider } from './ui/accessibility';
import { IconCheck } from './ui/icons';
import { ContactVerificationSection } from './verification';
import { MAP_CENTER } from '../constants';
import { TILE_LAYERS } from '../constants/mapStyles';
import LineDrawControl, { type DrawnLineFeatureCollection } from './map/LineDrawControl';
import 'leaflet/dist/leaflet.css';
import formStyles from '../styles/components/form.module.css';

const CATEGORIAS = [
  { value: 'infraestructura', label: 'Infraestructura (canales, caminos, alcantarillas)' },
  { value: 'servicios', label: 'Servicios del consorcio' },
  { value: 'administrativo', label: 'Temas administrativos' },
  { value: 'ambiental', label: 'Medio ambiente' },
  { value: 'otro', label: 'Otro' },
];

// Helper: Show notification
function showNotification(title: string, message: string, color: string, icon?: React.ReactNode) {
  notifications.show({ title, message, color, icon });
}

// Success screen component
function SuccessScreen({
  remainingToday,
  onReset,
}: Readonly<{
  remainingToday: number | null;
  onReset: () => void;
}>) {
  const showRemainingBadge = remainingToday !== null && remainingToday > 0;

  return (
    <Paper shadow="md" p="xl" radius="md">
      <Stack align="center" gap="lg">
        <IconCheck size={64} color="var(--mantine-color-green-6)" />
        <Title order={2} ta="center">
          Gracias por tu sugerencia
        </Title>
        <Text c="gray.6" ta="center">
          Tu propuesta fue recibida y sera considerada en las proximas reuniones de la comision.
        </Text>
        {showRemainingBadge && (
          <Badge color="blue" size="lg">
            Puedes enviar {remainingToday} sugerencia{remainingToday > 1 ? 's' : ''} mas hoy
          </Badge>
        )}
        <Button onClick={onReset}>Enviar otra sugerencia</Button>
      </Stack>
    </Paper>
  );
}

// Helper: Get step indicator background color
function getStepBackgroundColor(isComplete: boolean, isDisabled?: boolean): string {
  if (isComplete) return 'var(--mantine-color-green-6)';
  if (isDisabled) return 'var(--mantine-color-gray-4)';
  return 'var(--mantine-color-blue-6)';
}

// Step indicator component
function StepIndicator({
  step,
  isComplete,
  isDisabled,
  label,
  badge,
}: Readonly<{
  step: number | React.ReactNode;
  isComplete: boolean;
  isDisabled?: boolean;
  label: string;
  badge?: React.ReactNode;
}>) {
  return (
    <Group gap="xs" mb="md">
      <Box
        style={{
          width: 24,
          height: 24,
          borderRadius: '50%',
          backgroundColor: getStepBackgroundColor(isComplete, isDisabled),
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          fontSize: 12,
          fontWeight: 600,
        }}
      >
        {isComplete ? <IconCheck size={14} /> : step}
      </Box>
      <Text fw={600} size="sm" c={isDisabled ? 'dimmed' : undefined}>
        {label}
      </Text>
      {badge}
    </Group>
  );
}

// Form field with skeleton fallback
function FormFieldWithSkeleton({
  label,
  isVerified,
  skeletonHeight,
  children,
}: Readonly<{
  label: string;
  isVerified: boolean;
  skeletonHeight: number;
  children: React.ReactNode;
}>) {
  if (isVerified) {
    return <>{children}</>;
  }
  return (
    <Box>
      <Text size="sm" fw={500} mb="xs">
        {label}
      </Text>
      <Skeleton height={skeletonHeight} radius="sm" />
    </Box>
  );
}

// Helper: Get contact for rate limit check
function getContactForRateLimit(email: string | null): { email?: string } {
  if (email) return { email };
  return {};
}

// Helper: Build sugerencia payload
function buildSugerenciaPayload(
  values: {
    titulo: string;
    descripcion: string;
    categoria: string;
  },
  userEmail: string | null,
  userName: string | null,
  geometry: DrawnLineFeatureCollection | null,
) {
  return {
    titulo: values.titulo,
    descripcion: values.descripcion,
    categoria: values.categoria || undefined,
    geometry: geometry ?? undefined,
    contacto_nombre: userName || undefined,
    contacto_email: userEmail || undefined,
    contacto_verificado: true,
  };
}

function GeometrySummary({ geometry }: Readonly<{ geometry: DrawnLineFeatureCollection | null }>) {
  const totalLines = geometry?.features.length ?? 0;
  if (totalLines === 0) {
    return (
      <Text size="xs" c="dimmed">
        Opcional: dibuja una línea si querés marcar un canal faltante, una prolongación o una corrección.
      </Text>
    );
  }

  const totalVertices = geometry?.features.reduce(
    (acc, feature) => acc + feature.geometry.coordinates.length,
    0,
  ) ?? 0;

  return (
    <Badge color="blue" variant="light">
      {totalLines} línea{totalLines > 1 ? 's' : ''} · {totalVertices} vértices
    </Badge>
  );
}

function SuggestionMapReady() {
  const map = useMap();

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      map.invalidateSize();
    }, 100);
    return () => window.clearTimeout(timeoutId);
  }, [map]);

  return null;
}

function SuggestionGeometrySection({
  geometry,
  onChange,
}: Readonly<{
  geometry: DrawnLineFeatureCollection | null;
  onChange: (geometry: DrawnLineFeatureCollection | null) => void;
}>) {
  const { waterways } = useWaterways();
  const [baseLayer, setBaseLayer] = useState<'osm' | 'satellite'>('satellite');
  const existingChannels = useMemo(
    () => waterways.filter((layer) => layer.id === 'canales_existentes'),
    [waterways],
  );

  return (
    <Stack gap="xs">
      <Group justify="space-between" align="center">
        <Text size="sm" fw={500}>
          Canal en mapa
        </Text>
        <GeometrySummary geometry={geometry} />
      </Group>

      <SegmentedControl
        value={baseLayer}
        onChange={(value) => setBaseLayer(value as 'osm' | 'satellite')}
        data={[
          { label: 'Satelital', value: 'satellite' },
          { label: 'Mapa', value: 'osm' },
        ]}
        size="xs"
      />

      <Text size="xs" c="dimmed">
        Usa la herramienta de línea arriba a la izquierda del mapa. Podés dibujar, editar vértices o borrar.
      </Text>

      <Box className={formStyles.mapContainer} style={{ height: 360 }}>
        <MapContainer center={MAP_CENTER} zoom={12} style={{ width: '100%', height: '100%' }}>
          <TileLayer
            attribution={TILE_LAYERS[baseLayer].attribution}
            url={TILE_LAYERS[baseLayer].url}
          />
          <SuggestionMapReady />
          {existingChannels.map((layer) => (
            <GeoJSON key={layer.id} data={layer.data as FeatureCollection} style={layer.style} />
          ))}
          <LineDrawControl value={geometry} onChange={onChange} />
        </MapContainer>
      </Box>

      <Text size="xs" c="dimmed">
        Referencia visible: <b>Canales existentes</b> en azul oscuro. Lo que dibujes queda como sugerencia, no como canal oficial.
      </Text>
    </Stack>
  );
}

// Extracted: Step 2 badge helper
function getStep2Badge(
  contactoVerificado: boolean,
  remainingToday: number | null
): React.ReactNode | undefined {
  if (!contactoVerificado) {
    return (
      <Badge color="gray" size="sm" variant="light">
        Verifica tu contacto primero
      </Badge>
    );
  }
  if (remainingToday === null) return undefined;
  return (
    <Badge color={remainingToday > 0 ? 'blue' : 'red'} size="sm" variant="light">
      {remainingToday} restantes hoy
    </Badge>
  );
}

function FormularioContenido() {
  const [enviando, setEnviando] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const [remainingToday, setRemainingToday] = useState<number | null>(null);
  const [geometry, setGeometry] = useState<DrawnLineFeatureCollection | null>(null);

  const form = useForm({
    initialValues: {
      titulo: '',
      descripcion: '',
      categoria: '',
    },
    validate: {
      titulo: validators.titulo,
      descripcion: validators.descripcion,
    },
  });

  // Hook de verificacion de contacto (Google OAuth / Magic Link)
  const verification = useContactVerification({
    onVerified: () => {
      void checkRateLimit();
    },
  });

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
    resetVerificacion,
  } = verification;

  // Verificar limite cuando se verifica contacto
  const checkRateLimit = useCallback(async () => {
    const { email } = getContactForRateLimit(userEmail);

    if (!email) return;

    try {
      const limit = await sugerenciasApi.checkLimit(email);
      setRemainingToday(limit.remaining);

      if (limit.remaining <= 0) {
        showNotification(
          'Limite alcanzado',
          'Has alcanzado el limite de 3 sugerencias por dia. Intenta manana.',
          'orange'
        );
      }
    } catch (error) {
      logger.error('Error checking rate limit:', error);
    }
  }, [userEmail]);

  // Handler para cambiar de usuario
  const handleCambiarContacto = useCallback(() => {
    logout();
    resetVerificacion();
  }, [logout, resetVerificacion]);

  // Enviar sugerencia
  const handleSubmit = useCallback(
    async (values: typeof form.values) => {
      if (!contactoVerificado) {
        showNotification(
          'Contacto no verificado',
          'Debes verificar tu identidad antes de enviar',
          'orange'
        );
        return;
      }

      if (remainingToday !== null && remainingToday <= 0) {
        showNotification(
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
        showNotification('Sugerencia enviada', result.message, 'green', <IconCheck size={16} />);
        setRemainingToday(result.remaining_today);
        setEnviado(true);
        form.reset();
        setGeometry(null);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'No se pudo enviar la sugerencia';
        if (message.includes('limite')) {
          setRemainingToday(0);
        }
        showNotification('Error', message, 'red');
      } finally {
        setEnviando(false);
      }
    },
    [contactoVerificado, form, geometry, remainingToday, userEmail, userName]
  );

  // Pantalla de exito
  if (enviado) {
    return (
      <SuccessScreen
        remainingToday={remainingToday}
        onReset={() => {
          setEnviado(false);
          resetVerificacion();
        }}
      />
    );
  }

  return (
    <Paper shadow="md" p="xl" radius="md" pos="relative">
      <LoadingOverlay visible={enviando} />

      <Title order={2} mb="md">
        Enviar Sugerencia
      </Title>
      <Text c="gray.6" mb="xl">
        Propone temas o mejoras para que la comision las considere en sus proximas reuniones
      </Text>

      {/* Seccion 1: Verificacion de contacto */}
      <Box mb="xl">
        <StepIndicator
          step="1"
          isComplete={contactoVerificado}
          label="Verificar contacto"
          badge={
            contactoVerificado ? (
              <Badge color="green" size="sm" variant="light">
                Verificado
              </Badge>
            ) : undefined
          }
        />

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
          onLogout={handleCambiarContacto}
          verificationExplanation="Para evitar spam, necesitamos verificar tu identidad. Limite: 3 sugerencias por dia."
        />
      </Box>

      <Divider my="lg" />

      {/* Seccion 2: Formulario de sugerencia */}
      <Box pos="relative">
        <StepIndicator
          step="2"
          isComplete={false}
          isDisabled={!contactoVerificado}
          label="Completar sugerencia"
          badge={getStep2Badge(contactoVerificado, remainingToday)}
        />

        {/* Overlay cuando no esta verificado */}
        {!contactoVerificado && (
          <Overlay
            style={{ background: 'light-dark(rgba(255,255,255,0.6), rgba(36,36,36,0.6))' }}
            backgroundOpacity={0}
            blur={2}
            zIndex={5}
            radius="md"
          />
        )}

        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack gap="md">
            {remainingToday === 0 && contactoVerificado && (
              <Alert color="red" variant="light">
                Has alcanzado el limite de sugerencias por hoy. Vuelve manana.
              </Alert>
            )}

            {/* Titulo */}
            <FormFieldWithSkeleton
              label="Titulo de la sugerencia"
              isVerified={contactoVerificado}
              skeletonHeight={36}
            >
              <TextInput
                label="Titulo de la sugerencia"
                placeholder="Resume tu propuesta en una frase"
                required
                disabled={remainingToday === 0}
                maxLength={MAX_LENGTHS.TITULO}
                description={`Maximo ${MAX_LENGTHS.TITULO} caracteres`}
                {...form.getInputProps('titulo')}
              />
            </FormFieldWithSkeleton>

            {/* Categoria */}
            <FormFieldWithSkeleton
              label="Categoria"
              isVerified={contactoVerificado}
              skeletonHeight={36}
            >
              <Select
                label="Categoria"
                placeholder="Selecciona una categoria"
                data={CATEGORIAS}
                clearable
                disabled={remainingToday === 0}
                {...form.getInputProps('categoria')}
              />
            </FormFieldWithSkeleton>

            {/* Descripcion */}
            <FormFieldWithSkeleton
              label="Descripcion"
              isVerified={contactoVerificado}
              skeletonHeight={120}
            >
              <Textarea
                label="Descripcion"
                placeholder="Explica tu sugerencia con el mayor detalle posible..."
                minRows={5}
                required
                disabled={remainingToday === 0}
                maxLength={MAX_LENGTHS.DESCRIPCION}
                description={`Maximo ${MAX_LENGTHS.DESCRIPCION} caracteres`}
                {...form.getInputProps('descripcion')}
              />
            </FormFieldWithSkeleton>

            <FormFieldWithSkeleton
              label="Canal en mapa"
              isVerified={contactoVerificado}
              skeletonHeight={360}
            >
              <SuggestionGeometrySection geometry={geometry} onChange={setGeometry} />
            </FormFieldWithSkeleton>

            {/* Submit */}
            <FormFieldWithSkeleton label="" isVerified={contactoVerificado} skeletonHeight={42}>
              <Button type="submit" size="lg" fullWidth mt="md" disabled={remainingToday === 0}>
                Enviar Sugerencia
              </Button>
            </FormFieldWithSkeleton>
          </Stack>
        </form>
      </Box>
    </Paper>
  );
}

export { FormularioContenido as FormularioSugerenciaContent };

/**
 * FormularioSugerencia - Page component (MantineProvider is provided by main.tsx).
 */
export default function FormularioSugerencia() {
  return (
    <LiveRegionProvider>
      <FormularioContenido />
    </LiveRegionProvider>
  );
}
