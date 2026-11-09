import {
  Avatar,
  Box,
  Button,
  Card,
  Container,
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
import { useEffect, useState } from 'react';
import { apiFetch } from '../lib/api';
import { updatePassword, useAuth } from '../lib/auth';
import { withBasePath } from '../lib/basePath';
import { showError, showSuccess } from '../lib/notifications';
import { MyReportsSection } from './profile/MyReportsSection';
import { MySuggestionsSection } from './profile/MySuggestionsSection';
import { IconCheck, IconMail, IconPhone, IconUser } from './ui/icons';
import { LoadingState } from './ui/LoadingState';
import { PageHeader } from './ui/PageHeader';

interface ProfileFormValues {
  nombre: string;
  telefono: string;
}

interface PasswordFormValues {
  newPassword: string;
  confirmPassword: string;
}

const PROFILE_NEW_PASSWORD_ERROR_ID = 'profile-new-password-error';
const PROFILE_CONFIRM_PASSWORD_ERROR_ID = 'profile-confirm-password-error';

function ProfileContent() {
  const { user, profile, loading } = useAuth();
  const [saving, setSaving] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);

  const profileForm = useForm<ProfileFormValues>({
    initialValues: {
      nombre: profile?.nombre || '',
      telefono: profile?.telefono || '',
    },
  });

  const passwordForm = useForm<PasswordFormValues>({
    initialValues: {
      newPassword: '',
      confirmPassword: '',
    },
    validate: {
      newPassword: (value) =>
        value.length < 6 ? 'La contraseña debe tener al menos 6 caracteres' : null,
      confirmPassword: (value, values) => {
        if (!value) return 'Confirmá la contraseña';
        return value !== values.newPassword ? 'Las contraseñas no coinciden' : null;
      },
    },
  });

  const profileId = (profile as { id?: string } | null)?.id;
  const profileNombre = profile?.nombre ?? '';
  const profileTelefono = profile?.telefono ?? '';

  // Initialize form when profile loads without mutating state during render
  useEffect(() => {
    if (profile) {
      profileForm.setValues({
        nombre: profileNombre,
        telefono: profileTelefono,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileId, profileNombre, profileTelefono]);

  const handleProfileSubmit = async (values: ProfileFormValues) => {
    if (!user) return;

    setSaving(true);
    try {
      await apiFetch('/users/me', {
        method: 'PATCH',
        body: JSON.stringify({
          nombre: values.nombre,
          telefono: values.telefono,
        }),
      });

      showSuccess('Perfil actualizado', 'Tus datos se guardaron correctamente', {
        icon: <IconCheck size={16} />,
      });
    } catch (_error) {
      showError('Error', 'No se pudo actualizar el perfil');
    } finally {
      setSaving(false);
    }
  };

  const handlePasswordSubmit = async (values: PasswordFormValues) => {
    setChangingPassword(true);
    try {
      const result = await updatePassword(values.newPassword);

      if (!result.success) {
        throw new Error(result.error);
      }

      showSuccess('Contraseña actualizada', 'Tu contraseña se cambió correctamente', {
        icon: <IconCheck size={16} />,
      });

      passwordForm.reset();
    } catch (error) {
      showError(
        'Error',
        error instanceof Error ? error.message : 'No se pudo cambiar la contraseña'
      );
    } finally {
      setChangingPassword(false);
    }
  };

  if (loading) {
    return (
      <Container size="sm" py="xl">
        <LoadingState compact message="Cargando perfil..." />
      </Container>
    );
  }

  if (!user) {
    return (
      <Container size="sm" py="xl">
        <Paper p="xl" radius="md" withBorder>
          <Stack align="center" gap="md">
            <Text>Tenés que iniciar sesión para ver tu perfil</Text>
            <Button component="a" href={withBasePath('/login')}>
              Iniciar Sesión
            </Button>
          </Stack>
        </Paper>
      </Container>
    );
  }

  const initials = profile?.nombre
    ? profile.nombre
        .split(' ')
        .map((n) => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)
    : user.email?.charAt(0).toUpperCase() || 'U';

  const roleLabels: Record<string, string> = {
    admin: 'Administrador',
    operador: 'Operador',
    ciudadano: 'Ciudadano',
  };

  return (
    <Container size="sm" py="xl">
      <Stack gap="xl">
        <PageHeader title="Mi Perfil" mb={0} />

        {/* User Info Card */}
        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Group>
            <Avatar size="xl" radius="xl" color="institucional">
              {initials}
            </Avatar>
            <Box>
              <Text size="xl" fw={600}>
                {profile?.nombre || 'Sin nombre'}
              </Text>
              <Text c="dimmed" size="sm">
                {user.email}
              </Text>
              <Text size="sm" c="institucional" fw={500}>
                {roleLabels[profile?.rol || 'ciudadano']}
              </Text>
            </Box>
          </Group>
        </Card>

        {/* Edit Profile Form */}
        <Paper shadow="sm" p="lg" radius="md" withBorder>
          <form onSubmit={profileForm.onSubmit(handleProfileSubmit)}>
            <Stack gap="md">
              <Title order={3}>Editar Datos</Title>

              <TextInput
                label="Nombre completo"
                placeholder="Tu nombre"
                leftSection={<IconUser size={16} />}
                {...profileForm.getInputProps('nombre')}
              />

              <TextInput
                label="Email"
                value={user.email || ''}
                disabled
                leftSection={<IconMail size={16} />}
                description="El email no se puede cambiar"
              />

              <TextInput
                label="Teléfono"
                placeholder="+54 9 11 1234-5678"
                leftSection={<IconPhone size={16} />}
                {...profileForm.getInputProps('telefono')}
              />

              <Group justify="flex-end">
                <Button type="submit" loading={saving}>
                  Guardar Cambios
                </Button>
              </Group>
            </Stack>
          </form>
        </Paper>

        {/* Change Password Form */}
        <Paper shadow="sm" p="lg" radius="md" withBorder>
          <form onSubmit={passwordForm.onSubmit(handlePasswordSubmit)} noValidate>
            <Stack gap="md">
              <Title order={3}>Cambiar Contraseña</Title>

              <PasswordInput
                label="Nueva contraseña"
                placeholder="Mínimo 6 caracteres"
                name="newPassword"
                autoComplete="new-password"
                visibilityToggleButtonProps={{ 'aria-label': 'Mostrar u ocultar contraseña' }}
                {...passwordForm.getInputProps('newPassword')}
                aria-invalid={passwordForm.errors.newPassword ? 'true' : undefined}
                errorProps={{
                  id: PROFILE_NEW_PASSWORD_ERROR_ID,
                  role: 'alert',
                  'aria-live': 'assertive',
                }}
              />

              <PasswordInput
                label="Confirmar contraseña"
                placeholder="Repetí la nueva contraseña"
                name="confirmPassword"
                autoComplete="new-password"
                visibilityToggleButtonProps={{ 'aria-label': 'Mostrar u ocultar contraseña' }}
                {...passwordForm.getInputProps('confirmPassword')}
                aria-invalid={passwordForm.errors.confirmPassword ? 'true' : undefined}
                errorProps={{
                  id: PROFILE_CONFIRM_PASSWORD_ERROR_ID,
                  role: 'alert',
                  'aria-live': 'assertive',
                }}
              />

              <Group justify="flex-end">
                <Button type="submit" loading={changingPassword} variant="outline">
                  Cambiar Contraseña
                </Button>
              </Group>
            </Stack>
          </form>
        </Paper>

        <Divider />

        <MyReportsSection />

        <MySuggestionsSection />

        {/* Account Actions */}
        <Paper shadow="sm" p="lg" radius="md" withBorder>
          <Stack gap="md">
            <Title order={3}>Cuenta</Title>
            <Text size="sm" c="dimmed">
              Cuenta activa
            </Text>
          </Stack>
        </Paper>
      </Stack>
    </Container>
  );
}

/**
 * ProfilePanel - Page component (MantineProvider is provided by main.tsx).
 */
export default function ProfilePanel() {
  return <ProfileContent />;
}
