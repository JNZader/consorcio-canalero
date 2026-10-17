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
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useEffect, useState } from 'react';
import { signInWithEmail, signInWithGoogle, signUpWithEmail } from '../lib/auth';
import { withBasePath } from '../lib/basePath';
import { logger } from '../lib/logger';
import { parseLoginSearch } from '../lib/loginSearch';
import { erroresUi } from '../lib/userFacingError';
import { MIN_PASSWORD_LENGTH, validateEmail, validatePassword } from '../lib/validators';
import { IconAlertCircle, IconCheck, IconMail, IconWaveSine } from './ui/icons';

const LOGIN_NAME_ERROR_ID = 'login-name-error';
const LOGIN_EMAIL_ERROR_ID = 'login-email-error';
const LOGIN_PASSWORD_ERROR_ID = 'login-password-error';
const LOGIN_CONFIRM_PASSWORD_ERROR_ID = 'login-confirm-password-error';

/**
 * LoginFormContent - Contenido interno del formulario de login.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 */
export function LoginFormContent() {
  const navigate = useNavigate();
  const rawSearch = useSearch({ strict: false });
  const urlMode =
    parseLoginSearch(rawSearch as Record<string, unknown>).modo === 'registro'
      ? 'register'
      : 'login';
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'login' | 'register'>(urlMode);
  const [showEmailConfirmation, setShowEmailConfirmation] = useState(false);

  useEffect(() => {
    setMode(urlMode);
  }, [urlMode]);

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
        if (mode === 'register') {
          // Shared strength rules (same as reset-password flow).
          return validatePassword(value);
        }
        // Login: only sanity-check length; strength was enforced at signup.
        return value.length < MIN_PASSWORD_LENGTH
          ? `La contraseña debe tener al menos ${MIN_PASSWORD_LENGTH} caracteres`
          : null;
      },
      confirmPassword: (value, values) => {
        if (mode !== 'register') return null;
        if (!value) return 'Confirmá la contraseña';
        return value !== values.password ? 'Las contraseñas no coinciden' : null;
      },
      nombre: (value) => (mode === 'register' && value.length < 2 ? 'Ingresá tu nombre' : null),
    },
  });

  const handleSubmit = async (values: typeof form.values) => {
    setLoading(true);
    setShowEmailConfirmation(false);

    try {
      if (mode === 'login') {
        // Iniciar sesion
        const result = await signInWithEmail(values.email, values.password);

        if (result.success) {
          notifications.show({
            title: 'Bienvenido',
            message: 'Inicio de sesión exitoso',
            color: 'green',
            icon: <IconCheck size={16} />,
          });
          // Redirigir al destino guardado (si existe y es seguro) o al admin
          const rawRedirect = sessionStorage.getItem('redirectAfterLogin');
          sessionStorage.removeItem('redirectAfterLogin');
          const isSafeRelative =
            rawRedirect && rawRedirect.startsWith('/') && !rawRedirect.startsWith('//');
          const destination = isSafeRelative ? rawRedirect : '/admin';
          globalThis.location.href = withBasePath(destination);
        } else {
          notifications.show({
            title: erroresUi.iniciarSesion.titulo,
            message: result.error || erroresUi.iniciarSesion.detalle,
            color: 'red',
            icon: <IconAlertCircle size={16} />,
          });
        }
      } else {
        // Registrar nuevo usuario
        const result = await signUpWithEmail(values.email, values.password, values.nombre);

        if (result.success) {
          if (result.needsEmailConfirmation) {
            // Mostrar mensaje de confirmacion de email
            setShowEmailConfirmation(true);
            notifications.show({
              title: 'Cuenta creada',
              message: 'Revisá tu email para confirmar tu cuenta',
              color: 'blue',
              icon: <IconMail size={16} />,
              autoClose: 10000,
            });
          } else {
            notifications.show({
              title: 'Cuenta creada',
              message: 'Tu cuenta fue creada exitosamente. Ya podés iniciar sesión.',
              color: 'green',
              icon: <IconCheck size={16} />,
            });
            setMode('login');
            form.reset();
          }
        } else {
          notifications.show({
            title: erroresUi.crearCuenta.titulo,
            message: result.error || erroresUi.crearCuenta.detalle,
            color: 'red',
            icon: <IconAlertCircle size={16} />,
          });
        }
      }
    } catch (error) {
      logger.error('Error en autenticación:', error);
      notifications.show({
        title: erroresUi.iniciarSesion.titulo,
        message: 'Ocurrió un error inesperado. Intentá de nuevo.',
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
          title: erroresUi.google.titulo,
          message: result.error || erroresUi.google.detalle,
          color: 'red',
          icon: <IconAlertCircle size={16} />,
        });
        setLoading(false);
      }
      // Si es exitoso, el backend redirigira automaticamente
    } catch (error) {
      logger.error(erroresUi.google.titulo, error);
      notifications.show({
        title: erroresUi.google.titulo,
        message: erroresUi.google.detalle,
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
    void navigate({
      to: '/login',
      search: newMode === 'register' ? { modo: 'registro' } : {},
      replace: false,
    });
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
            10 de Mayo - Departamento Unión
          </Text>
        </Box>

        <Title order={2} ta="center" mb="md">
          {mode === 'login' ? 'Iniciar Sesión' : 'Crear Cuenta'}
        </Title>

        {showEmailConfirmation && (
          <Alert color="blue" icon={<IconMail size={16} />} mb="md" title="Confirmá tu email">
            <Text size="sm">
              Te enviamos un email de confirmación a <strong>{form.values.email}</strong>. Revisá tu
              bandeja de entrada y hacé clic en el enlace para activar tu cuenta.
            </Text>
          </Alert>
        )}

        <form onSubmit={form.onSubmit(handleSubmit)} noValidate>
          <Stack gap="md">
            {mode === 'register' && (
              <TextInput
                label="Nombre"
                placeholder="Tu nombre"
                name="nombre"
                autoComplete="name"
                {...form.getInputProps('nombre')}
                required
                errorProps={{
                  id: LOGIN_NAME_ERROR_ID,
                  role: 'alert',
                  'aria-live': 'assertive',
                }}
              />
            )}

            <TextInput
              label="Email"
              placeholder="tu@email.com"
              name="email"
              type="email"
              autoComplete="email"
              autoCapitalize="none"
              {...form.getInputProps('email')}
              required
              errorProps={{
                id: LOGIN_EMAIL_ERROR_ID,
                role: 'alert',
                'aria-live': 'assertive',
              }}
            />

            <PasswordInput
              label="Contraseña"
              placeholder="Tu contraseña"
              name="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              visibilityToggleButtonProps={{ 'aria-label': 'Mostrar u ocultar contraseña' }}
              {...form.getInputProps('password')}
              required
              aria-invalid={form.errors.password ? 'true' : undefined}
              errorProps={{
                id: LOGIN_PASSWORD_ERROR_ID,
                role: 'alert',
                'aria-live': 'assertive',
              }}
            />

            {mode === 'register' && (
              <PasswordInput
                label="Confirmar contraseña"
                placeholder="Repetí tu contraseña"
                name="confirmPassword"
                autoComplete="new-password"
                visibilityToggleButtonProps={{ 'aria-label': 'Mostrar u ocultar contraseña' }}
                {...form.getInputProps('confirmPassword')}
                required
                aria-invalid={form.errors.confirmPassword ? 'true' : undefined}
                errorProps={{
                  id: LOGIN_CONFIRM_PASSWORD_ERROR_ID,
                  role: 'alert',
                  'aria-live': 'assertive',
                }}
              />
            )}

            {mode === 'login' && (
              <Anchor component="a" href={withBasePath('/forgot-password')} size="sm" ta="right">
                ¿Olvidaste tu contraseña?
              </Anchor>
            )}

            <Button type="submit" fullWidth loading={loading}>
              {mode === 'login' ? 'Iniciar Sesión' : 'Crear Cuenta'}
            </Button>
          </Stack>
        </form>

        <Divider label="o continuá con" labelPosition="center" my="lg" />

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
              ¿No tenés cuenta?{' '}
              <Anchor component="button" onClick={() => switchMode('register')}>
                Registrate
              </Anchor>
            </>
          ) : (
            <>
              ¿Ya tenés cuenta?{' '}
              <Anchor component="button" onClick={() => switchMode('login')}>
                Iniciá sesión
              </Anchor>
            </>
          )}
        </Text>
      </Paper>
    </Center>
  );
}

/**
 * LoginForm - Page component (MantineProvider is provided by main.tsx).
 */
export default function LoginForm() {
  return <LoginFormContent />;
}
