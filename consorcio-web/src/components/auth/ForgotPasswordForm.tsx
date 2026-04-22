import { Alert, Anchor, Button, Center, Paper, Stack, Text, TextInput, Title } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useState } from 'react';
import { resetPassword } from '../../lib/auth';
import { withBasePath } from '../../lib/basePath';
import { validateEmail } from '../../lib/validators';
import { IconAlertCircle, IconArrowLeft, IconCheck, IconMail } from '../ui/icons';

export default function ForgotPasswordForm() {
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const form = useForm({
    initialValues: { email: '' },
    validate: { email: validateEmail },
  });

  const handleSubmit = async (values: typeof form.values) => {
    setLoading(true);
    setError(null);

    try {
      const result = await resetPassword(values.email);

      if (result.success) {
        setSent(true);
      } else {
        setError(result.error || 'Error al enviar el email de recuperacion.');
      }
    } catch {
      setError('Error inesperado. Intenta de nuevo.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Center mih="80vh">
      <Paper shadow="md" p="xl" radius="md" w={400}>
        <Title order={2} ta="center" mb="md">
          Recuperar Contrasena
        </Title>

        {sent ? (
          <Stack gap="md">
            <Alert color="green" icon={<IconCheck size={16} />} title="Email enviado">
              <Text size="sm">
                Si existe una cuenta con el email <strong>{form.values.email}</strong>, recibiras un
                enlace para restablecer tu contrasena. Revisa tu bandeja de entrada y la carpeta de
                spam.
              </Text>
            </Alert>

            <Button
              variant="subtle"
              fullWidth
              component="a"
              href={withBasePath('/login')}
              leftSection={<IconArrowLeft size={16} />}
            >
              Volver al login
            </Button>
          </Stack>
        ) : (
          <>
            <Text c="dimmed" size="sm" ta="center" mb="lg">
              Ingresa tu email y te enviaremos un enlace para restablecer tu contrasena.
            </Text>

            {error && (
              <Alert color="red" icon={<IconAlertCircle size={16} />} mb="md">
                {error}
              </Alert>
            )}

            <form onSubmit={form.onSubmit(handleSubmit)}>
              <Stack gap="md">
                <TextInput
                  label="Email"
                  placeholder="tu@email.com"
                  leftSection={<IconMail size={16} />}
                  {...form.getInputProps('email')}
                  required
                />

                <Button type="submit" fullWidth loading={loading}>
                  Enviar enlace de recuperacion
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
