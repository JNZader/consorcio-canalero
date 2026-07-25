import { Alert, Button, Center, Loader, Paper, Stack, Text, Title } from '@mantine/core';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  type EmailCodeExchangeResult,
  completeEmailCodeExchange,
  exchangeEmailCode,
  verifyEmailWithToken,
} from '../../lib/auth';
import { withBasePath } from '../../lib/basePath';
import { IconAlertCircle, IconCheck } from '../ui/icons';

interface VerifyEmailPageProps {
  /** Legacy verification token, accepted during the compatibility window. */
  token: string;
  /** Short one-time code emitted by the secure email flow. */
  code?: string;
}

type VerificationState = 'loading' | 'success' | 'terminal-error' | 'retryable-error';

interface LegacyVerificationTokenResult {
  status: 'success';
  token: string;
  handle: null;
}

type VerificationTokenResult = EmailCodeExchangeResult | LegacyVerificationTokenResult;

const INVALID_LINK_MESSAGE = 'El enlace de verificación es inválido o expiró.';

function resolveVerificationToken(
  token: string,
  code?: string
): Promise<VerificationTokenResult> | VerificationTokenResult {
  if (token) return { status: 'success', token, handle: null };
  if (!code) return { status: 'terminal-error', reason: 'invalid-or-expired' };
  return exchangeEmailCode(code, 'verify');
}

export default function VerifyEmailPage({ token, code }: VerifyEmailPageProps) {
  const [state, setState] = useState<VerificationState>('loading');
  const [error, setError] = useState(INVALID_LINK_MESSAGE);
  const mountedRef = useRef(true);
  const inFlightRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const verifyEmail = useCallback(async () => {
    if (inFlightRef.current) return;

    inFlightRef.current = true;
    if (mountedRef.current) {
      setState('loading');
      setError(INVALID_LINK_MESSAGE);
    }

    try {
      const exchange = await resolveVerificationToken(token, code);
      if (!mountedRef.current) return;

      if (exchange.status === 'retryable-error') {
        setState('retryable-error');
        return;
      }
      if (exchange.status === 'terminal-error') {
        setState('terminal-error');
        return;
      }

      const result = await verifyEmailWithToken(exchange.token);
      if (!mountedRef.current) return;

      if (result.success) {
        if (exchange.handle) {
          completeEmailCodeExchange(exchange.handle);
        }
        setState('success');
      } else {
        setError(result.error || INVALID_LINK_MESSAGE);
        setState('terminal-error');
      }
    } catch {
      if (mountedRef.current) setState('retryable-error');
    } finally {
      inFlightRef.current = false;
    }
  }, [code, token]);

  useEffect(() => {
    void verifyEmail();
  }, [verifyEmail]);

  return (
    <Center mih="80vh">
      <Paper shadow="md" p="xl" radius="md" w={420}>
        {state === 'loading' && (
          <Stack align="center" gap="md">
            <Loader />
            <Text size="sm" c="dimmed">
              Verificando tu correo…
            </Text>
          </Stack>
        )}

        {state === 'success' && (
          <Stack gap="md">
            <Title order={2} ta="center">
              Correo verificado
            </Title>
            <Alert color="green" icon={<IconCheck size={16} />}>
              Tu cuenta ya está activa. Podés iniciar sesión.
            </Alert>
            <Button component="a" href={withBasePath('/login')} fullWidth>
              Iniciar sesión
            </Button>
          </Stack>
        )}

        {state === 'retryable-error' && (
          <Stack gap="md">
            <Alert
              color="yellow"
              icon={<IconAlertCircle size={16} />}
              title="No pudimos verificar el enlace"
            >
              Hubo un problema temporal de conexión. El enlace sigue disponible para reintentar.
            </Alert>
            <Button type="button" fullWidth onClick={verifyEmail}>
              Reintentar verificación
            </Button>
            <Button component="a" href={withBasePath('/login')} variant="subtle" fullWidth>
              Volver al inicio de sesión
            </Button>
          </Stack>
        )}

        {state === 'terminal-error' && (
          <Stack gap="md">
            <Alert color="red" icon={<IconAlertCircle size={16} />} title="Enlace inválido">
              {error}
            </Alert>
            <Button component="a" href={withBasePath('/login')} variant="subtle" fullWidth>
              Volver al inicio de sesión
            </Button>
          </Stack>
        )}
      </Paper>
    </Center>
  );
}
