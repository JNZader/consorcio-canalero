import {
  Alert,
  Badge,
  Box,
  Button,
  Divider,
  Group,
  LoadingOverlay,
  Paper,
  Stack,
  Text,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import type { ReactNode } from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { MAP_CENTER, TIPOS_DENUNCIA as TIPOS_DENUNCIA_BASE } from '../constants';
import { useContactVerification } from '../hooks/useContactVerification';
import { publicApi } from '../lib/api';
import {
  draftDataUrlToFile,
  fileToDraftDataUrl,
  loadReportDraft,
  MAX_DRAFT_PHOTO_BYTES,
  saveReportDraft,
} from '../lib/formDrafts';
import { logger } from '../lib/logger';
import { hideToast, showToast } from '../lib/notifications';
import { semanticColor } from '../lib/semanticColors';
import { useConfigStore } from '../stores/configStore';
import formStyles from '../styles/components/form.module.css';
import {
  DescripcionField,
  FotoField,
  SubmitButton,
  TipoProblemaField,
  UbicacionField,
} from './report-form/ReportFormFields';
import {
  getErrorString,
  OFFLINE_SUBMIT_MESSAGE,
  OFFLINE_SUBMIT_TITLE,
} from './report-form/reportFormUtils';

const REPORTE_OFFLINE_TOAST_ID = 'reporte-sin-conexion';

import { StepHeader } from './report-form/StepHeader';
import { useReportFormSubmission } from './report-form/useReportFormSubmission';
import { useReportLocation } from './report-form/useReportLocation';
import { LiveRegionProvider, useLiveRegion, VisuallyHidden } from './ui/accessibility';
import { IconBuildingBridge, IconDroplet, IconFileDescription, IconRoad } from './ui/icons';
import { PageHeader } from './ui/PageHeader';
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

function showOfflineToast(onRetry: () => void) {
  showToast({
    id: REPORTE_OFFLINE_TOAST_ID,
    title: OFFLINE_SUBMIT_TITLE,
    color: semanticColor.warning,
    autoClose: false,
    message: (
      <Stack gap="xs">
        <Text size="sm">{OFFLINE_SUBMIT_MESSAGE}</Text>
        <Button
          type="button"
          size="sm"
          variant="light"
          color={semanticColor.warning}
          onClick={onRetry}
        >
          Reintentar
        </Button>
      </Stack>
    ),
  });
}

function clearOfflineToast() {
  hideToast(REPORTE_OFFLINE_TOAST_ID);
}

function FormularioContenido() {
  const config = useConfigStore((state) => state.config);
  const defaultCenter = config?.map.center
    ? ([config.map.center.lat, config.map.center.lng] as [number, number])
    : MAP_CENTER;
  const defaultZoom = config?.map.zoom ? config.map.zoom + 1 : 12;
  const [enviando, setEnviando] = useState(false);
  const [envioOffline, setEnvioOffline] = useState(false);
  const retryRef = useRef<() => void>(() => {});
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
    setEnvioOffline(false);
    clearOfflineToast();
  }, []);

  const handleLimitReached = useCallback(() => {
    setRemainingToday(0);
  }, []);

  const handleOfflineFailure = useCallback(() => {
    setEnvioOffline(true);
    showOfflineToast(() => retryRef.current());
  }, []);

  const handleOtherFailure = useCallback(() => {
    setEnvioOffline(false);
    clearOfflineToast();
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
    if (draft.fotoDataUrl) {
      const restoredFile = draftDataUrlToFile(draft.fotoDataUrl, draft.fotoName, draft.fotoType);
      if (restoredFile) {
        form.setFieldValue('foto', restoredFile);
      }
      setFotoPreview(draft.fotoDataUrl);
    }
  }, [form, setFotoPreview, setUbicacion]);

  const handleLoginWithGoogle = useCallback(async () => {
    const hasDraftContent = Boolean(
      form.values.tipo || form.values.descripcion || ubicacion || form.values.foto
    );
    if (hasDraftContent) {
      let fotoDataUrl =
        form.values.foto &&
        form.values.foto.size <= MAX_DRAFT_PHOTO_BYTES &&
        fotoPreview?.startsWith('data:')
          ? fotoPreview
          : undefined;

      if (!fotoDataUrl && form.values.foto && form.values.foto.size <= MAX_DRAFT_PHOTO_BYTES) {
        fotoDataUrl = (await fileToDraftDataUrl(form.values.foto)) ?? undefined;
      }

      saveReportDraft({
        tipo: form.values.tipo,
        descripcion: form.values.descripcion,
        lat: ubicacion?.lat,
        lng: ubicacion?.lng,
        ...(fotoDataUrl
          ? {
              fotoDataUrl,
              fotoName: form.values.foto?.name,
              fotoType: form.values.foto?.type,
            }
          : {}),
      });
    }
    loginWithGoogle();
  }, [
    form.values.descripcion,
    form.values.foto,
    form.values.tipo,
    fotoPreview,
    loginWithGoogle,
    ubicacion,
  ]);

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
    onOfflineFailure: handleOfflineFailure,
    onOtherFailure: handleOtherFailure,
    onAttemptStart: clearOfflineToast,
  });

  useEffect(() => {
    retryRef.current = () => {
      void form.onSubmit(handleSubmit)();
    };
  }, [form, handleSubmit]);

  return (
    <Paper shadow="md" p="xl" radius="md" pos="relative">
      <LoadingOverlay visible={enviando} />
      {enviando && (
        <VisuallyHidden as="p" role="status" aria-live="polite">
          Enviando reporte, por favor esperá.
        </VisuallyHidden>
      )}

      <PageHeader
        title="Nuevo Reporte"
        subtitle="Reportá problemas en la red de canales y caminos rurales"
        order={2}
        size="h2"
        mb="xl"
      />

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
            onLoginWithGoogle={handleLoginWithGoogle}
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
          <Alert color="institucional" variant="light" mb="md">
            Podés completar el reporte ahora. Al enviarlo te pedimos verificar la identidad para
            evitar spam. Guardamos el texto, la ubicación y fotos de hasta 2 MB en tu sesión.
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
          <Alert color="alerta" variant="light" mb="md" role="alert" aria-live="assertive">
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

            <Box className={formStyles.submitBar}>
              {envioOffline && (
                <Alert
                  color="orange"
                  variant="light"
                  role="alert"
                  aria-live="assertive"
                  title={OFFLINE_SUBMIT_TITLE}
                  mb="sm"
                >
                  <Text size="sm">{OFFLINE_SUBMIT_MESSAGE}</Text>
                  <Button
                    type="button"
                    mt="sm"
                    variant="light"
                    color="orange"
                    disabled={enviando}
                    onClick={() => retryRef.current()}
                  >
                    Reintentar envío
                  </Button>
                </Alert>
              )}
              <SubmitButton disabled={remainingToday === 0} loading={enviando} />
            </Box>
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
