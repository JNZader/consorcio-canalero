import {
  Alert,
  Anchor,
  Box,
  Button,
  Center,
  Divider,
  Group,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';
import { signInWithEmail, signInWithGoogle, signUpWithEmail } from '../lib/auth';
import { logger } from '../lib/logger';
import { validateEmail } from '../lib/validators';
import MantineProvider from './MantineProvider';
import { IconAlertCircle, IconCheck, IconMail, IconWaveSine } from './ui/icons';

/**
 * LoginFormContent - Contenido interno del formulario de login sin MantineProvider.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 */
export function LoginFormContent() {
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [showEmailConfirmation, setShowEmailConfirmation] = useState(false);

  const form = useForm({
    initialValues: {
      email: '',
      password: '',
      confirmPassword: '',
      nombre: '',
    },
    validate: {
      email: validateEmail,
      password: (value) => {
        if (value.length < 8) {
          return 'La contrasena debe tener al menos 8 caracteres';
        }
        if (mode === 'register') {
          // Require at least one number and one letter for new registrations
          if (!/[0-9]/.test(value)) {
            return 'La contrasena debe incluir al menos un numero';
          }
          if (!/[a-zA-Z]/.test(value)) {
            return 'La contrasena debe incluir al menos una letra';
          }
        }
        return null;
      },
      confirmPassword: (value, values) =>
        mode === 'register' && value !== values.password ? 'Las contrasenas no coinciden' : null,
      nombre: (value) => (mode === 'register' && value.length < 2 ? 'Ingresa tu nombre' : null),
    },
  });

  const handleSubmit = async (values: typeof form.values) => {
    setLoading(true);
    setShowEmailConfirmation(false);

    try {
      if (mode === 'login') {
        // Iniciar sesion con Supabase
        const result = await signInWithEmail(values.email, values.password);

        if (result.success) {
          notifications.show({
            title: 'Bienvenido',
            message: 'Inicio de sesion exitoso',
            color: 'green',
            icon: <IconCheck size={16} />,
          });
          // Redirigir al admin
          globalThis.location.href = '/admin';
        } else {
          notifications.show({
            title: 'Error al iniciar sesion',
            message: result.error || 'Verifica tus credenciales',
            color: 'red',
            icon: <IconAlertCircle size={16} />,
          });
        }
      } else {
        // Registrar nuevo usuario con Supabase
        const result = await signUpWithEmail(values.email, values.password, values.nombre);

        if (result.success) {
          if (result.needsEmailConfirmation) {
            // Mostrar mensaje de confirmacion de email
            setShowEmailConfirmation(true);
            notifications.show({
              title: 'Cuenta creada',
              message: 'Revisa tu email para confirmar tu cuenta',
              color: 'blue',
              icon: <IconMail size={16} />,
              autoClose: 10000,
            });
          } else {
            notifications.show({
              title: 'Cuenta creada',
              message: 'Tu cuenta fue creada exitosamente. Ya puedes iniciar sesion.',
              color: 'green',
              icon: <IconCheck size={16} />,
            });
            setMode('login');
            form.reset();
          }
        } else {
          notifications.show({
            title: 'Error al crear cuenta',
            message: result.error || 'Intenta de nuevo',
            color: 'red',
            icon: <IconAlertCircle size={16} />,
          });
        }
      }
    } catch (error) {
      logger.error('Error en autenticacion:', error);
      notifications.show({
        title: 'Error',
        message: 'Ocurrio un error inesperado. Intenta de nuevo.',
        color: 'red',
        icon: <IconAlertCircle size={16} />,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setLoading(true);

    try {
      const result = await signInWithGoogle();

      if (!result.success) {
        notifications.show({
          title: 'Error con Google',
          message: result.error || 'No se pudo conectar con Google',
          color: 'red',
          icon: <IconAlertCircle size={16} />,
        });
        setLoading(false);
      }
      // Si es exitoso, Supabase redirigira automaticamente
    } catch (error) {
      logger.error('Error al conectar con Google:', error);
      notifications.show({
        title: 'Error',
        message: 'Ocurrio un error al conectar con Google',
        color: 'red',
        icon: <IconAlertCircle size={16} />,
      });
      setLoading(false);
    }
  };

  const switchMode = (newMode: 'login' | 'register') => {
    setMode(newMode);
    setShowEmailConfirmation(false);
    form.reset();
  };

  return (
    <Center mih="80vh">
      <Paper shadow="md" p="xl" radius="md" w={400}>
        <Box ta="center" mb="xl">
          <Group justify="center" gap="xs" mb="xs">
            <IconWaveSine size={24} color="var(--mantine-color-blue-6)" />
            <Text size="xl" fw={700} c="blue">
              Consorcio Canalero
            </Text>
          </Group>
          <Text c="gray.6" size="sm">
            10 de Mayo - Bell Ville
          </Text>
        </Box>

        <Title order={2} ta="center" mb="md">
          {mode === 'login' ? 'Iniciar Sesion' : 'Crear Cuenta'}
        </Title>

        {showEmailConfirmation && (
          <Alert color="blue" icon={<IconMail size={16} />} mb="md" title="Confirma tu email">
            <Text size="sm">
              Te enviamos un email de confirmacion a <strong>{form.values.email}</strong>. Revisa tu
              bandeja de entrada y haz clic en el enlace para activar tu cuenta.
            </Text>
          </Alert>
        )}

        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack gap="md">
            {mode === 'register' && (
              <TextInput
                label="Nombre"
                placeholder="Tu nombre"
                {...form.getInputProps('nombre')}
                required
              />
            )}

            <TextInput
              label="Email"
              placeholder="tu@email.com"
              {...form.getInputProps('email')}
              required
            />

            <PasswordInput
              label="Contrasena"
              placeholder="Tu contrasena"
              {...form.getInputProps('password')}
              required
            />

            {mode === 'register' && (
              <PasswordInput
                label="Confirmar contrasena"
                placeholder="Repite tu contrasena"
                {...form.getInputProps('confirmPassword')}
                required
              />
            )}

            <Button type="submit" fullWidth loading={loading}>
              {mode === 'login' ? 'Iniciar Sesion' : 'Crear Cuenta'}
            </Button>
          </Stack>
        </form>

        <Divider label="o continua con" labelPosition="center" my="lg" />

        <Button
          variant="default"
          fullWidth
          onClick={handleGoogleLogin}
          loading={loading}
          leftSection={
            <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="currentColor"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="currentColor"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="currentColor"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
          }
        >
          Google
        </Button>

        <Text ta="center" mt="md" size="sm">
          {mode === 'login' ? (
            <>
              No tienes cuenta?{' '}
              <Anchor component="button" onClick={() => switchMode('register')}>
                Registrate
              </Anchor>
            </>
          ) : (
            <>
              Ya tienes cuenta?{' '}
              <Anchor component="button" onClick={() => switchMode('login')}>
                Inicia sesion
              </Anchor>
            </>
          )}
        </Text>
      </Paper>
    </Center>
  );
}

/**
 * LoginForm - Standalone component with MantineProvider.
 */
export default function LoginForm() {
  return (
    <MantineProvider>
      <LoginFormContent />
    </MantineProvider>
  );
}
