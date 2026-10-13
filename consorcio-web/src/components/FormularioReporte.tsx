import {
  Alert,
  Badge,
  Box,
  Divider,
  Group,
  LoadingOverlay,
  Paper,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import type { ReactNode } from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { MAP_CENTER, TIPOS_DENUNCIA as TIPOS_DENUNCIA_BASE } from '../constants';
import { useContactVerification } from '../hooks/useContactVerification';
import { publicApi } from '../lib/api';
import { loadReportDraft } from '../lib/formDrafts';
import { logger } from '../lib/logger';
import { useConfigStore } from '../stores/configStore';
import {
  DescripcionField,
  FotoField,
  SubmitButton,
  TipoProblemaField,
  UbicacionField,
} from './report-form/ReportFormFields';
import { getErrorString } from './report-form/reportFormUtils';
import { StepHeader } from './report-form/StepHeader';
import { useReportFormSubmission } from './report-form/useReportFormSubmission';
import { useReportLocation } from './report-form/useReportLocation';
import { LiveRegionProvider, useLiveRegion, VisuallyHidden } from './ui/accessibility';
import { IconBuildingBridge, IconDroplet, IconFileDescription, IconRoad } from './ui/icons';
import { ContactVerificationSection } from './verification';

const TIPO_ICONS: Record<string, ReactNode> = {
  alcantarilla_tapada: <IconBuildingBridge size={24} />,
  desborde: <IconDroplet size={24} />,
  camino_danado: <IconRoad size={24} />,
  otro: <IconFileDescription size={24} />,
};

const TIPOS_DENUNCIA = TIPOS_DENUNCIA_BASE.map((tipo) => ({
  ...tipo,
  icon: TIPO_ICONS[tipo.value] ?? <IconFileDescription size={24} />,
}));

function FormularioContenido() {
  const config = useConfigStore((state) => state.config);
  const defaultCenter = config?.map.center
    ? ([config.map.center.lat, config.map.center.lng] as [number, number])
    : MAP_CENTER;
  const defaultZoom = config?.map.zoom ? config.map.zoom + 1 : 12;
  const [enviando, setEnviando] = useState(false);
  // `null` = no consultado todavía (sin login). El backend rechazaría
  // /denuncias/rate-limit con 401 — sólo pegamos cuando hay JWT.
  const [remainingToday, setRemainingToday] = useState<number | null>(null);
  const { announce } = useLiveRegion();

  const form = useForm({
    initialValues: {
      tipo: '',
      descripcion: '',
      foto: null as File | null,
    },
    validate: {
      tipo: (value) => (!value ? 'Seleccioná un tipo de denuncia' : null),
      descripcion: (value) =>
        value.length < 10 ? 'La descripción debe tener al menos 10 caracteres' : null,
    },
  });

  const {
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
  } = useReportLocation({ announce, form });

  const { contactoVerificado, userEmail, userName, loading, loginWithGoogle, logout } =
    useContactVerification({
      onVerified: (email, name) => {
        const displayName = name || email;
        announce(`Identidad verificada como ${displayName}. Podés continuar con la denuncia.`);
      },
    });

  // Pull initial quota when the user logs in. Espejo del flujo de
  // sugerencias — `null` mientras no haya JWT, número real luego.
  useEffect(() => {
    if (!userEmail) return;
    let cancelled = false;
    (async () => {
      try {
        const limit = await publicApi.checkLimit();
        if (!cancelled) setRemainingToday(limit.remaining);
      } catch (error) {
        logger.error('Error checking report rate limit:', error);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [userEmail]);

  const handleSubmitSuccess = useCallback(() => {
    setRemainingToday((prev) => (prev === null ? null : Math.max(0, prev - 1)));
  }, []);

  const handleLimitReached = useCallback(() => {
    setRemainingToday(0);
  }, []);

  const restoredDraft = useRef(false);
  useEffect(() => {
    if (restoredDraft.current) return;
    restoredDraft.current = true;
    const draft = loadReportDraft();
    if (!draft) return;
    form.setFieldValue('tipo', draft.tipo);
    form.setFieldValue('descripcion', draft.descripcion);
    if (typeof draft.lat === 'number' && typeof draft.lng === 'number') {
      setUbicacion({ lat: draft.lat, lng: draft.lng });
    }
  }, [form, setUbicacion]);

  const handleSubmit = useReportFormSubmission({
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
    onSubmitSuccess: handleSubmitSuccess,
    onLimitReached: handleLimitReached,
  });

  return (
    <Paper shadow="md" p="xl" radius="md" pos="relative">
      <LoadingOverlay visible={enviando} />
      {enviando && (
        <VisuallyHidden as="p" role="status" aria-live="polite">
          Enviando reporte, por favor esperá.
        </VisuallyHidden>
      )}

      <Title order={2} mb="md">
        Nuevo Reporte
      </Title>
      <Text c="gray.6" mb="xl">
        Reportá problemas en la red de canales y caminos rurales
      </Text>

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
            loading={loading}
            onLoginWithGoogle={loginWithGoogle}
            onLogout={logout}
          />
        </Stack>
      </Box>

      <Divider my="xl" />

      <Box pos="relative">
        <StepHeader
          step={2}
          title="Completar reporte"
          subtitle="Detalles del incidente"
          isComplete={false}
          variant="secondary"
        />

        {!contactoVerificado && (
          <Alert color="blue" variant="light" mb="md">
            Podés completar el reporte ahora. Al enviarlo te pedimos verificar la identidad para
            evitar spam. Guardamos el texto y la ubicación; la foto hay que volver a adjuntarla.
          </Alert>
        )}

        {contactoVerificado && remainingToday !== null && (
          <Group justify="flex-end" mb="xs">
            <Badge color={remainingToday > 0 ? 'blue' : 'red'} size="sm" variant="light">
              {remainingToday} {remainingToday === 1 ? 'restante' : 'restantes'}
            </Badge>
          </Group>
        )}

        {remainingToday === 0 && contactoVerificado && (
          <Alert color="red" variant="light" mb="md" role="alert" aria-live="assertive">
            Llegaste al límite de 5 reportes cada 24 horas. Volvé más tarde.
          </Alert>
        )}

        <form onSubmit={form.onSubmit(handleSubmit)} noValidate>
          <Stack gap="lg">
            <TipoProblemaField
              value={form.values.tipo}
              error={getErrorString(form.errors.tipo)}
              onChange={(value) => form.setFieldValue('tipo', value)}
              tiposDenuncia={TIPOS_DENUNCIA}
            />

            <DescripcionField
              error={getErrorString(form.errors.descripcion)}
              getInputProps={form.getInputProps}
            />

            <UbicacionField
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

            <FotoField fotoPreview={fotoPreview} onDrop={handleDrop} onRemove={handleRemoveFoto} />

            <SubmitButton disabled={remainingToday === 0} />
          </Stack>
        </form>
      </Box>
    </Paper>
  );
}

export { FormularioContenido };

export default function FormularioReporte() {
  return (
    <LiveRegionProvider>
      <FormularioContenido />
    </LiveRegionProvider>
  );
}
