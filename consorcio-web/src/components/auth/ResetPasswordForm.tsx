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
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  type EmailCodeExchangeHandle,
  completeEmailCodeExchange,
  exchangeEmailCode,
  resetPasswordWithToken,
} from '../../lib/auth';
import { withBasePath } from '../../lib/basePath';
import { validatePassword } from '../../lib/validators';
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

type CodeExchangeState = 'idle' | 'loading' | 'retryable-error' | 'terminal-error';

export default function ResetPasswordForm({ token, code }: ResetPasswordFormProps) {
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exchangeState, setExchangeState] = useState<CodeExchangeState>(
    code && !token ? 'loading' : 'idle'
  );
  const [effectiveToken, setEffectiveToken] = useState<string>(token);
  const [exchangeHandle, setExchangeHandle] = useState<EmailCodeExchangeHandle | null>(null);
  const mountedRef = useRef(true);
  const exchangeInFlightRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const exchangeCode = useCallback(async () => {
    if (!code || token || exchangeInFlightRef.current) return;

    exchangeInFlightRef.current = true;
    if (mountedRef.current) setExchangeState('loading');

    try {
      const exchange = await exchangeEmailCode(code, 'reset');
      if (!mountedRef.current) return;

      if (exchange.status === 'success') {
        setEffectiveToken(exchange.token);
        setExchangeHandle(exchange.handle);
        setExchangeState('idle');
      } else if (exchange.status === 'terminal-error') {
        setExchangeState('terminal-error');
      } else {
        setExchangeState('retryable-error');
      }
    } catch {
      if (mountedRef.current) setExchangeState('retryable-error');
    } finally {
      exchangeInFlightRef.current = false;
    }
  }, [code, token]);

  useEffect(() => {
    if (token) {
      setEffectiveToken(token);
      setExchangeHandle(null);
      setExchangeState('idle');
      return;
    }

    if (code && !effectiveToken) {
      void exchangeCode();
    }
  }, [code, effectiveToken, exchangeCode, token]);

  const form = useForm({
    initialValues: {
      password: '',
      confirmPassword: '',
    },
    validate: {
      // Shared strength rules (same as register flow) — see lib/validators.ts
      password: validatePassword,
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
        if (code && !token && exchangeHandle) {
          completeEmailCodeExchange(exchangeHandle);
        }
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

  if (exchangeState === 'loading') {
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

  if (exchangeState === 'retryable-error') {
    return (
      <Center mih="80vh">
        <Paper shadow="md" p="xl" radius="md" w={400}>
          <Stack gap="md">
            <Alert
              color="yellow"
              icon={<IconAlertCircle size={16} />}
              title="No pudimos verificar el enlace"
            >
              Hubo un problema temporal de conexión. El enlace sigue disponible para reintentar.
            </Alert>
            <Button type="button" fullWidth onClick={exchangeCode}>
              Reintentar verificación
            </Button>
            <Button
              variant="subtle"
              fullWidth
              component="a"
              href={withBasePath('/forgot-password')}
            >
              Solicitar nuevo enlace
            </Button>
          </Stack>
        </Paper>
      </Center>
    );
  }

  if (exchangeState === 'terminal-error' || !effectiveToken) {
    return (
      <Center mih="80vh">
        <Paper shadow="md" p="xl" radius="md" w={400}>
          <Alert color="red" icon={<IconAlertCircle size={16} />} title="Enlace invalido">
            <Text size="sm">
              Este enlace de recuperacion es invalido o expiró. Solicita uno nuevo desde la pagina
              de login.
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
