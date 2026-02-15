/**
 * Complete contact verification section component.
 * Uses Google OAuth (1-click) and Magic Link (any email) for verification.
 */

import {
  Alert,
  Button,
  Divider,
  Group,
  Loader,
  Paper,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { validateEmail } from '../../lib/validators';
import { IconCheck, IconMail, IconShieldCheck } from '../ui/icons';
import type { VerificationMethod } from './types';

export interface ContactVerificationSectionProps {
  /** Usuario esta verificado (autenticado) */
  readonly contactoVerificado: boolean;
  /** Email del usuario verificado */
  readonly userEmail: string | null;
  /** Nombre del usuario (si disponible) */
  readonly userName: string | null;
  /** Metodo de verificacion seleccionado */
  readonly metodoVerificacion: VerificationMethod;
  /** Cargando autenticacion */
  readonly loading: boolean;
  /** Magic link fue enviado */
  readonly magicLinkSent: boolean;
  /** Email al que se envio el magic link */
  readonly magicLinkEmail: string | null;
  /** Cambiar metodo de verificacion */
  readonly onMetodoChange: (method: VerificationMethod) => void;
  /** Iniciar login con Google */
  readonly onLoginWithGoogle: () => void;
  /** Enviar magic link */
  readonly onSendMagicLink: (email: string) => void;
  /** Cerrar sesion / cambiar usuario */
  readonly onLogout: () => void;
  /** Optional: Custom verification explanation text */
  readonly verificationExplanation?: string;
}

// Google logo SVG component
function GoogleLogo() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24">
      <title>Google logo</title>
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  );
}

export function ContactVerificationSection({
  contactoVerificado,
  userEmail,
  userName,
  metodoVerificacion: _metodoVerificacion,
  loading,
  magicLinkSent,
  magicLinkEmail,
  onMetodoChange,
  onLoginWithGoogle,
  onSendMagicLink,
  onLogout,
  verificationExplanation = 'Para enviar tu reporte, necesitamos verificar tu identidad.',
}: ContactVerificationSectionProps) {
  const _form = useForm({
    initialValues: {
      email: '',
    },
    validate: {
      email: validateEmail,
    },
  });

  const handleMagicLinkSubmit = (values: { email: string }) => {
    onSendMagicLink(values.email);
  };

  // Estado verificado
  if (contactoVerificado) {
    return (
      <Alert color="green" icon={<IconShieldCheck size={20} />} title="Identidad verificada">
        <Group justify="space-between" align="center">
          <Stack gap={4}>
            {userName && <Text size="sm" fw={500}>{userName}</Text>}
            <Text size="sm" c="dimmed">{userEmail}</Text>
          </Stack>
          <Button size="xs" variant="subtle" onClick={onLogout}>
            Cambiar
          </Button>
        </Group>
      </Alert>
    );
  }

  // Estado de carga
  if (loading) {
    return (
      <Stack align="center" py="xl">
        <Loader size="lg" />
        <Text c="dimmed">Procesando...</Text>
      </Stack>
    );
  }

  // Magic link enviado
  if (magicLinkSent && magicLinkEmail) {
    return (
      <Stack align="center" gap="md" py="md">
        <Paper p="md" radius="md" bg="green.0" c="green.9">
          <IconCheck size={48} />
        </Paper>
        <Title order={4}>Revisa tu email</Title>
        <Text ta="center" c="dimmed">
          Enviamos un link de acceso a:
        </Text>
        <Text fw={600}>{magicLinkEmail}</Text>
        <Alert color="blue" title="Siguiente paso">
          <Text size="sm">
            Haz click en el link del email para verificar tu identidad.
            Despues podras completar tu reporte.
          </Text>
        </Alert>
        <Button variant="subtle" onClick={() => onMetodoChange('google')}>
          Usar otro metodo
        </Button>
      </Stack>
    );
  }

  // Seleccion de metodo
  return (
    <Stack gap="md">
      <Alert color="blue" variant="light">
        <Text size="sm">{verificationExplanation}</Text>
      </Alert>

      {/* Google OAuth - opcion principal */}
      <Button
        size="lg"
        variant="default"
        leftSection={<GoogleLogo />}
        onClick={onLoginWithGoogle}
        fullWidth
      >
        Continuar con Google
      </Button>

      <Divider label="o usa tu email" labelPosition="center" />

      {/* Magic Link */}
      <form onSubmit={_form.onSubmit(handleMagicLinkSubmit)}>
        <Stack gap="sm">
          <TextInput
            placeholder="tu@email.com"
            leftSection={<IconMail size={16} />}
            {..._form.getInputProps('email')}
            size="md"
          />
          <Button type="submit" variant="light" fullWidth>
            Enviar link de acceso
          </Button>
        </Stack>
      </form>

      <Text size="xs" c="dimmed" ta="center">
        Solo usamos tu email para identificarte y notificarte sobre tu reporte.
      </Text>
    </Stack>
  );
}
