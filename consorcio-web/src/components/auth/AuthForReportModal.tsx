/**
 * Modal de autenticación para reportes públicos.
 * Ofrece Google OAuth (1 click) y Magic Link (cualquier email).
 */

import {
  Alert,
  Button,
  Divider,
  Loader,
  Modal,
  Paper,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { useCallback, useState } from 'react';
import { getSupabaseClient } from '../../lib/supabase';
import { logger } from '../../lib/logger';
import { IconCheck, IconMail } from '../ui/icons';

export interface AuthForReportModalProps {
  opened: boolean;
  onClose: () => void;
  onAuthenticated: (email: string, name?: string) => void;
  title?: string;
  description?: string;
}

type AuthStep = 'choose' | 'magic-link-sent' | 'loading';

export function AuthForReportModal({
  opened,
  onClose,
  onAuthenticated,
  title = 'Verificar identidad',
  description = 'Para enviar tu reporte, necesitamos verificar tu identidad.',
}: AuthForReportModalProps) {
  const [step, setStep] = useState<AuthStep>('choose');
  const [sentEmail, setSentEmail] = useState('');

  const form = useForm({
    initialValues: {
      email: '',
    },
    validate: {
      email: (value) => {
        if (!value) return 'El email es requerido';
        if (value.length > 254) return 'Email demasiado largo';
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return 'Email invalido';
        return null;
      },
    },
  });

  const handleGoogleLogin = useCallback(async () => {
    setStep('loading');
    try {
      const supabase = getSupabaseClient();
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/reportes?auth=success`,
          queryParams: {
            access_type: 'offline',
            prompt: 'consent',
          },
        },
      });

      if (error) {
        throw error;
      }
      // El redirect sucede automaticamente
    } catch (error) {
      logger.error('Error en login con Google:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudo iniciar sesion con Google. Intenta con email.',
        color: 'red',
      });
      setStep('choose');
    }
  }, []);

  const handleMagicLink = useCallback(async (values: { email: string }) => {
    setStep('loading');
    try {
      const supabase = getSupabaseClient();
      const { error } = await supabase.auth.signInWithOtp({
        email: values.email,
        options: {
          emailRedirectTo: `${window.location.origin}/reportes?auth=success`,
        },
      });

      if (error) {
        throw error;
      }

      setSentEmail(values.email);
      setStep('magic-link-sent');
      notifications.show({
        title: 'Link enviado',
        message: `Revisa tu email ${values.email}`,
        color: 'green',
        icon: <IconCheck size={16} />,
      });
    } catch (error) {
      logger.error('Error enviando magic link:', error);
      const message = error instanceof Error ? error.message : 'No se pudo enviar el email';
      notifications.show({
        title: 'Error',
        message,
        color: 'red',
      });
      setStep('choose');
    }
  }, []);

  const handleClose = useCallback(() => {
    setStep('choose');
    setSentEmail('');
    form.reset();
    onClose();
  }, [onClose, form]);

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={<Title order={3}>{title}</Title>}
      centered
      size="sm"
    >
      {step === 'loading' && (
        <Stack align="center" py="xl">
          <Loader size="lg" />
          <Text c="dimmed">Procesando...</Text>
        </Stack>
      )}

      {step === 'choose' && (
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            {description}
          </Text>

          {/* Google OAuth - opcion principal */}
          <Button
            size="lg"
            variant="default"
            leftSection={
              <svg width="20" height="20" viewBox="0 0 24 24">
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
            }
            onClick={handleGoogleLogin}
            fullWidth
          >
            Continuar con Google
          </Button>

          <Divider label="o usa tu email" labelPosition="center" />

          {/* Magic Link */}
          <form onSubmit={form.onSubmit(handleMagicLink)}>
            <Stack gap="sm">
              <TextInput
                placeholder="tu@email.com"
                leftSection={<IconMail size={16} />}
                {...form.getInputProps('email')}
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
      )}

      {step === 'magic-link-sent' && (
        <Stack align="center" gap="md" py="md">
          <Paper p="md" radius="md" bg="green.0" c="green.9">
            <IconCheck size={48} />
          </Paper>
          <Title order={4}>Revisa tu email</Title>
          <Text ta="center" c="dimmed">
            Enviamos un link de acceso a:
          </Text>
          <Text fw={600}>{sentEmail}</Text>
          <Alert color="blue" title="Siguiente paso">
            <Text size="sm">
              Haz click en el link del email para verificar tu identidad.
              Despues podras completar tu reporte.
            </Text>
          </Alert>
          <Button variant="subtle" onClick={() => setStep('choose')}>
            Usar otro email
          </Button>
        </Stack>
      )}
    </Modal>
  );
}

export default AuthForReportModal;
