import {
  Alert,
  Badge,
  Box,
  Button,
  Divider,
  LoadingOverlay,
  Paper,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useContactVerification } from '../hooks/useContactVerification';
import { loadSuggestionDraft } from '../lib/formDrafts';
import { MAX_LENGTHS, validators } from '../lib/validators';
import type { DrawnLineFeatureCollection } from './map/LineDrawControl';
import { SuggestionGeometrySection } from './suggestion-form/SuggestionGeometrySection';
import { SuggestionStepIndicator } from './suggestion-form/SuggestionStepIndicator';
import { CATEGORIAS } from './suggestion-form/suggestionFormConstants';
import { getStep2Badge, SuccessScreen } from './suggestion-form/suggestionFormUtils';
import { useSuggestionFormState } from './suggestion-form/useSuggestionFormState';
import { LiveRegionProvider, VisuallyHidden } from './ui/accessibility';
import { ContactVerificationSection } from './verification';

const SUGGESTION_TITLE_ERROR_ID = 'suggestion-title-error';
const SUGGESTION_DESCRIPTION_ERROR_ID = 'suggestion-description-error';

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

  // useCallback both callbacks because they're consumed by `useEffect`
  // dep arrays inside `useContactVerification` and `useSuggestionFormState`.
  // Inline arrow functions get a fresh reference EVERY render — those
  // hooks's effects then run on every render, hitting setState calls
  // that trigger more renders. The page would lock up Firefox while the
  // map's WebGL canvas got destroyed and rebuilt repeatedly.
  const handleVerified = useCallback(() => {
    setPendingRateLimitCheck(true);
  }, []);

  const handleRateLimitChecked = useCallback(() => {
    setPendingRateLimitCheck(false);
  }, []);

  const verification = useContactVerification({
    onVerified: handleVerified,
  });

  const { contactoVerificado, userEmail, userName, loading, loginWithGoogle, logout } =
    verification;

  const suggestionState = useSuggestionFormState({
    contactoVerificado,
    userEmail,
    userName,
    logout,
    form,
    pendingRateLimitCheck,
    onRateLimitChecked: handleRateLimitChecked,
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

  const restoredDraft = useRef(false);
  useEffect(() => {
    if (restoredDraft.current) return;
    restoredDraft.current = true;
    const draft = loadSuggestionDraft();
    if (!draft) return;
    form.setValues({
      titulo: draft.titulo,
      descripcion: draft.descripcion,
      categoria: draft.categoria,
    });
    if (draft.geometry) {
      setGeometry(draft.geometry as DrawnLineFeatureCollection);
    }
  }, [form, setGeometry]);

  if (enviado) {
    return <SuccessScreen remainingToday={remainingToday} onReset={resetSuccess} />;
  }

  return (
    <Paper shadow="md" p="xl" radius="md" pos="relative">
      <LoadingOverlay visible={enviando} />
      {enviando && (
        <VisuallyHidden as="p" role="status" aria-live="polite">
          Enviando sugerencia, por favor esperá.
        </VisuallyHidden>
      )}

      <Title order={2} mb="md">
        Enviar Sugerencia
      </Title>
      <Text c="gray.6" mb="xl">
        Proponé temas o mejoras para que la comisión las considere en sus próximas reuniones
      </Text>

      <Box mb="xl">
        <SuggestionStepIndicator
          step="1"
          isComplete={contactoVerificado}
          label="Verificar identidad"
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
          loading={loading}
          onLoginWithGoogle={loginWithGoogle}
          onLogout={handleCambiarContacto}
          verificationExplanation="Para evitar spam, necesitamos verificar tu identidad. Límite: 5 sugerencias cada 24 horas."
          privacyNote="Solo usamos tu email para identificarte y notificarte sobre tu sugerencia."
        />
      </Box>

      <Divider my="lg" />

      <Box pos="relative">
        <SuggestionStepIndicator
          step="2"
          isComplete={false}
          label="Completar sugerencia"
          badge={getStep2Badge(contactoVerificado, remainingToday)}
        />

        {!contactoVerificado && (
          <Alert color="blue" variant="light" mb="md">
            Podés completar la sugerencia ahora. Al enviarla te pedimos verificar la identidad para
            evitar spam.
          </Alert>
        )}

        <form onSubmit={form.onSubmit(handleSubmit)} noValidate>
          <Stack gap="md">
            {remainingToday === 0 && contactoVerificado && (
              <Alert color="red" variant="light" role="alert" aria-live="assertive">
                Llegaste al límite de 5 sugerencias cada 24 horas. Volvé más tarde.
              </Alert>
            )}

            <TextInput
              label="Título de la sugerencia"
              placeholder="Resumí tu propuesta en una frase"
              required
              disabled={remainingToday === 0}
              maxLength={MAX_LENGTHS.TITULO}
              description={`Máximo ${MAX_LENGTHS.TITULO} caracteres`}
              {...form.getInputProps('titulo')}
              errorProps={{
                id: SUGGESTION_TITLE_ERROR_ID,
                role: 'alert',
                'aria-live': 'assertive',
              }}
            />

            <Select
              label="Categoría"
              placeholder="Seleccioná una categoría"
              data={CATEGORIAS}
              clearable
              disabled={remainingToday === 0}
              {...form.getInputProps('categoria')}
            />

            <Textarea
              label="Descripción"
              placeholder="Explicá tu sugerencia con el mayor detalle posible..."
              minRows={5}
              required
              disabled={remainingToday === 0}
              maxLength={MAX_LENGTHS.DESCRIPCION}
              description={`Máximo ${MAX_LENGTHS.DESCRIPCION} caracteres`}
              {...form.getInputProps('descripcion')}
              errorProps={{
                id: SUGGESTION_DESCRIPTION_ERROR_ID,
                role: 'alert',
                'aria-live': 'assertive',
              }}
            />

            <SuggestionGeometrySection geometry={geometry} onChange={setGeometry} />

            <Button type="submit" size="lg" fullWidth mt="md" disabled={remainingToday === 0}>
              Enviar Sugerencia
            </Button>
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
