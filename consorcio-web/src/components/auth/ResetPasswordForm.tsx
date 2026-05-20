import {
  Alert,
  Anchor,
  Button,
  Center,
  Loader,
  Paper,
  PasswordInput,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useEffect, useState } from 'react';
import { exchangeCodeForToken, resetPasswordWithToken } from '../../lib/auth';
import { withBasePath } from '../../lib/basePath';
import { IconAlertCircle, IconCheck, IconLock } from '../ui/icons';

const RESET_PASSWORD_ERROR_ID = 'reset-password-error';
const RESET_CONFIRM_PASSWORD_ERROR_ID = 'reset-confirm-password-error';

interface ResetPasswordFormProps {
  /** Legacy: long JWT token embedded directly in the email URL.
   * Sent when the backend's ``USE_ONE_TIME_CODES`` is off. */
  token: string;
  /** F5-E: short SMTP-safe code that the SPA must exchange for the
   * real JWT via ``POST /auth/exchange-code``. Sent when the
   * backend ships the email with ``?code=`` instead of ``?token=``. */
  code?: string;
}

export default function ResetPasswordForm({ token, code }: ResetPasswordFormProps) {
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // F5-E: when the URL carries ``?code=`` instead of ``?token=``, hit
  // the exchange endpoint first to get the real JWT, then proceed as
  // before. ``effectiveToken`` is what the password-reset call uses.
  // ``exchanging`` gates the UI behind a loader so the user doesn't
  // see "Invalid link" while the network round-trip is in flight.
  const [exchanging, setExchanging] = useState<boolean>(!!code && !token);
  const [effectiveToken, setEffectiveToken] = useState<string>(token);

  useEffect(() => {
    let cancelled = false;
    if (!effectiveToken && code) {
      setExchanging(true);
      exchangeCodeForToken(code, 'reset')
        .then((resolved) => {
          if (cancelled) return;
          if (resolved) {
            setEffectiveToken(resolved);
          }
          setExchanging(false);
        })
        .catch(() => {
          if (cancelled) return;
          setExchanging(false);
        });
    }
    return () => {
      cancelled = true;
    };
  }, [code, effectiveToken]);

  const form = useForm({
    initialValues: {
      password: '',
      confirmPassword: '',
    },
    validate: {
      password: (value) => {
        if (value.length < 8) {
          return 'La contrasena debe tener al menos 8 caracteres';
        }
        if (!/[0-9]/.test(value)) {
          return 'La contrasena debe incluir al menos un numero';
        }
        if (!/[a-zA-Z]/.test(value)) {
          return 'La contrasena debe incluir al menos una letra';
        }
        return null;
      },
      confirmPassword: (value, values) =>
        value !== values.password ? 'Las contrasenas no coinciden' : null,
    },
  });

  const handleSubmit = async (values: typeof form.values) => {
    setLoading(true);
    setError(null);

    try {
      const result = await resetPasswordWithToken(effectiveToken, values.password);

      if (result.success) {
        setSuccess(true);
      } else {
        setError(result.error || 'Error al restablecer la contrasena.');
      }
    } catch {
      setError('Error inesperado. Intenta de nuevo.');
    } finally {
      setLoading(false);
    }
  };

  // F5-E: code is being exchanged for the real token. Show a loader
  // so the user doesn't see the "Invalid link" state during the
  // round-trip.
  if (exchanging) {
    return (
      <Center mih="80vh">
        <Paper shadow="md" p="xl" radius="md" w={400}>
          <Stack align="center" gap="md">
            <Loader />
            <Text size="sm" c="dimmed">
              Verificando el enlace…
            </Text>
          </Stack>
        </Paper>
      </Center>
    );
  }

  if (!effectiveToken) {
    return (
      <Center mih="80vh">
        <Paper shadow="md" p="xl" radius="md" w={400}>
          <Alert color="red" icon={<IconAlertCircle size={16} />} title="Enlace invalido">
            <Text size="sm">
              Este enlace de recuperacion es invalido o expiró. Solicita uno
              nuevo desde la pagina de login.
            </Text>
          </Alert>
          <Button
            variant="subtle"
            fullWidth
            mt="md"
            component="a"
            href={withBasePath('/forgot-password')}
          >
            Solicitar nuevo enlace
          </Button>
        </Paper>
      </Center>
    );
  }

  return (
    <Center mih="80vh">
      <Paper shadow="md" p="xl" radius="md" w={400}>
        <Title order={2} ta="center" mb="md">
          Nueva Contrasena
        </Title>

        {success ? (
          <Stack gap="md">
            <Alert color="green" icon={<IconCheck size={16} />} title="Contrasena actualizada">
              <Text size="sm">
                Tu contrasena fue restablecida exitosamente. Ya podes iniciar sesion con tu nueva
                contrasena.
              </Text>
            </Alert>
            <Button fullWidth component="a" href={withBasePath('/login')}>
              Iniciar Sesion
            </Button>
          </Stack>
        ) : (
          <>
            <Text c="dimmed" size="sm" ta="center" mb="lg">
              Ingresa tu nueva contrasena.
            </Text>

            {error && (
              <Alert color="red" icon={<IconAlertCircle size={16} />} mb="md">
                {error}
              </Alert>
            )}

            <form onSubmit={form.onSubmit(handleSubmit)} noValidate>
              <Stack gap="md">
                <PasswordInput
                  label="Nueva contrasena"
                  placeholder="Minimo 8 caracteres"
                  leftSection={<IconLock size={16} />}
                  {...form.getInputProps('password')}
                  required
                  aria-invalid={form.errors.password ? 'true' : undefined}
                  errorProps={{
                    id: RESET_PASSWORD_ERROR_ID,
                    role: 'alert',
                    'aria-live': 'assertive',
                  }}
                />

                <PasswordInput
                  label="Confirmar contrasena"
                  placeholder="Repite la nueva contrasena"
                  leftSection={<IconLock size={16} />}
                  {...form.getInputProps('confirmPassword')}
                  required
                  aria-invalid={form.errors.confirmPassword ? 'true' : undefined}
                  errorProps={{
                    id: RESET_CONFIRM_PASSWORD_ERROR_ID,
                    role: 'alert',
                    'aria-live': 'assertive',
                  }}
                />

                <Button type="submit" fullWidth loading={loading}>
                  Restablecer Contrasena
                </Button>
              </Stack>
            </form>

            <Text ta="center" mt="md" size="sm">
              <Anchor component="a" href={withBasePath('/login')}>
                Volver al login
              </Anchor>
            </Text>
          </>
        )}
      </Paper>
    </Center>
  );
}
