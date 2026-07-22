import { Alert, Button, Center, Loader, Paper, Stack, Text, Title } from '@mantine/core';
import { useEffect, useState } from 'react';
import { exchangeCodeForToken, verifyEmailWithToken } from '../../lib/auth';
import { withBasePath } from '../../lib/basePath';
import { IconAlertCircle, IconCheck } from '../ui/icons';

interface VerifyEmailPageProps {
  /** Legacy verification token, accepted during the compatibility window. */
  token: string;
  /** Short one-time code emitted by the secure email flow. */
  code?: string;
}

type VerificationState = 'loading' | 'success' | 'error';

export default function VerifyEmailPage({ token, code }: VerifyEmailPageProps) {
  const [state, setState] = useState<VerificationState>('loading');
  const [error, setError] = useState('El enlace de verificación es inválido o expiró.');

  useEffect(() => {
    let active = true;

    async function verifyEmail() {
      let resolvedToken = token;
      if (!resolvedToken && code) {
        resolvedToken = (await exchangeCodeForToken(code, 'verify')) ?? '';
      }

      if (!resolvedToken) {
        if (active) setState('error');
        return;
      }

      const result = await verifyEmailWithToken(resolvedToken);
      if (!active) return;
      if (result.success) {
        setState('success');
      } else {
        setError(result.error || 'El enlace de verificación es inválido o expiró.');
        setState('error');
      }
    }

    void verifyEmail();
    return () => {
      active = false;
    };
  }, [code, token]);

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

        {state === 'error' && (
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
