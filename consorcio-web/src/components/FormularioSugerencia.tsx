import {
  Alert,
  Badge,
  Box,
  Button,
  Divider,
  LoadingOverlay,
  Overlay,
  Paper,
  Select,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useState } from 'react';
import { useContactVerification } from '../hooks/useContactVerification';
import { MAX_LENGTHS, validators } from '../lib/validators';
import { LiveRegionProvider } from './ui/accessibility';
import { ContactVerificationSection } from './verification';
import { CATEGORIAS } from './suggestion-form/suggestionFormConstants';
import { SuggestionGeometrySection } from './suggestion-form/SuggestionGeometrySection';
import { SuggestionStepIndicator } from './suggestion-form/SuggestionStepIndicator';
import {
  FormFieldWithSkeleton,
  getStep2Badge,
  SuccessScreen,
} from './suggestion-form/suggestionFormUtils';
import { useSuggestionFormState } from './suggestion-form/useSuggestionFormState';

function FormularioContenido() {
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

  const [pendingRateLimitCheck, setPendingRateLimitCheck] = useState(false);

  const verification = useContactVerification({
    onVerified: () => {
      setPendingRateLimitCheck(true);
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

  const suggestionState = useSuggestionFormState({
    contactoVerificado,
    userEmail,
    userName,
    resetVerificacion,
    logout,
    form,
    pendingRateLimitCheck,
    onRateLimitChecked: () => setPendingRateLimitCheck(false),
  });

  const {
    enviando,
    enviado,
    geometry,
    handleCambiarContacto,
    handleSubmit,
    remainingToday,
    resetSuccess,
    setGeometry,
  } = suggestionState;

  if (enviado) {
    return <SuccessScreen remainingToday={remainingToday} onReset={resetSuccess} />;
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

      <Box mb="xl">
        <SuggestionStepIndicator
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

      <Box pos="relative">
        <SuggestionStepIndicator
          step="2"
          isComplete={false}
          isDisabled={!contactoVerificado}
          label="Completar sugerencia"
          badge={getStep2Badge(contactoVerificado, remainingToday)}
        />

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

            <FormFieldWithSkeleton label="Categoria" isVerified={contactoVerificado} skeletonHeight={36}>
              <Select
                label="Categoria"
                placeholder="Selecciona una categoria"
                data={CATEGORIAS}
                clearable
                disabled={remainingToday === 0}
                {...form.getInputProps('categoria')}
              />
            </FormFieldWithSkeleton>

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

export default function FormularioSugerencia() {
  return (
    <LiveRegionProvider>
      <FormularioContenido />
    </LiveRegionProvider>
  );
}
