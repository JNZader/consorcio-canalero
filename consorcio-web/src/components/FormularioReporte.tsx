import { Box, Divider, LoadingOverlay, Overlay, Paper, Stack, Text, Title } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useState } from 'react';
import type { ReactNode } from 'react';
import { MAP_CENTER, TIPOS_DENUNCIA as TIPOS_DENUNCIA_BASE } from '../constants';
import { useContactVerification } from '../hooks/useContactVerification';
import { useConfigStore } from '../stores/configStore';
import {
  DescripcionField,
  FotoField,
  SubmitButton,
  TipoProblemaField,
  UbicacionField,
} from './report-form/ReportFormFields';
import { StepHeader } from './report-form/StepHeader';
import { getErrorString } from './report-form/reportFormUtils';
import { useReportFormSubmission } from './report-form/useReportFormSubmission';
import { useReportLocation } from './report-form/useReportLocation';
import { LiveRegionProvider, useLiveRegion } from './ui/accessibility';
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
  });

  return (
    <Paper shadow="md" p="xl" radius="md" pos="relative">
      <LoadingOverlay visible={enviando} />

      <Title order={2} mb="md">
        Nuevo Reporte
      </Title>
      <Text c="gray.6" mb="xl">
        Reporta problemas en la red de canales y caminos rurales
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

      <Box pos="relative">
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
            <TipoProblemaField
              contactoVerificado={contactoVerificado}
              value={form.values.tipo}
              error={getErrorString(form.errors.tipo)}
              onChange={(value) => form.setFieldValue('tipo', value)}
              tiposDenuncia={TIPOS_DENUNCIA}
            />

            <DescripcionField
              contactoVerificado={contactoVerificado}
              error={getErrorString(form.errors.descripcion)}
              getInputProps={form.getInputProps}
            />

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

            <FotoField
              contactoVerificado={contactoVerificado}
              fotoPreview={fotoPreview}
              onDrop={handleDrop}
              onRemove={handleRemoveFoto}
            />

            <SubmitButton contactoVerificado={contactoVerificado} disabled={!ubicacion} />
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
