import {
  Alert,
  Anchor,
  Button,
  Center,
  Paper,
  PasswordInput,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useState } from 'react';
import { resetPasswordWithToken } from '../../lib/auth';
import { withBasePath } from '../../lib/basePath';
import { IconAlertCircle, IconCheck, IconLock } from '../ui/icons';

const RESET_PASSWORD_ERROR_ID = 'reset-password-error';
const RESET_CONFIRM_PASSWORD_ERROR_ID = 'reset-confirm-password-error';

interface ResetPasswordFormProps {
  token: string;
}

export default function ResetPasswordForm({ token }: ResetPasswordFormProps) {
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      const result = await resetPasswordWithToken(token, values.password);

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

  if (!token) {
    return (
      <Center mih="80vh">
        <Paper shadow="md" p="xl" radius="md" w={400}>
          <Alert color="red" icon={<IconAlertCircle size={16} />} title="Enlace invalido">
            <Text size="sm">
              Este enlace de recuperacion es invalido. Solicita uno nuevo desde la pagina de login.
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
