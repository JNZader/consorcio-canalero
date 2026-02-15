import {
  Avatar,
  Box,
  Button,
  Card,
  Container,
  Divider,
  Group,
  Loader,
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
import { updatePassword, useAuth } from '../lib/auth';
import { getSupabaseClient } from '../lib/supabase';
import { formatDate } from '../lib/formatters';
import { IconCheck, IconMail, IconPhone, IconUser } from './ui/icons';

interface ProfileFormValues {
  nombre: string;
  telefono: string;
}

interface PasswordFormValues {
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
}

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
      currentPassword: '',
      newPassword: '',
      confirmPassword: '',
    },
    validate: {
      newPassword: (value) =>
        value.length < 6 ? 'La contrasena debe tener al menos 6 caracteres' : null,
      confirmPassword: (value, values) =>
        value !== values.newPassword ? 'Las contrasenas no coinciden' : null,
    },
  });

  // Update form when profile loads
  if (profile && !profileForm.values.nombre && profile.nombre) {
    profileForm.setFieldValue('nombre', profile.nombre);
  }
  if (profile && !profileForm.values.telefono && profile.telefono) {
    profileForm.setFieldValue('telefono', profile.telefono);
  }

  const handleProfileSubmit = async (values: ProfileFormValues) => {
    if (!user) return;

    setSaving(true);
    try {
      const supabase = getSupabaseClient();
      const { error } = await supabase
        .from('perfiles')
        .update({
          nombre: values.nombre,
          telefono: values.telefono,
        })
        .eq('id', user.id);

      if (error) throw error;

      notifications.show({
        title: 'Perfil actualizado',
        message: 'Tus datos se guardaron correctamente',
        color: 'green',
        icon: <IconCheck size={16} />,
      });
    } catch (_error) {
      notifications.show({
        title: 'Error',
        message: 'No se pudo actualizar el perfil',
        color: 'red',
      });
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

      notifications.show({
        title: 'Contrasena actualizada',
        message: 'Tu contrasena se cambio correctamente',
        color: 'green',
        icon: <IconCheck size={16} />,
      });

      passwordForm.reset();
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: error instanceof Error ? error.message : 'No se pudo cambiar la contrasena',
        color: 'red',
      });
    } finally {
      setChangingPassword(false);
    }
  };

  if (loading) {
    return (
      <Container size="sm" py="xl">
        <Stack align="center" gap="md">
          <Loader size="lg" />
          <Text c="dimmed">Cargando perfil...</Text>
        </Stack>
      </Container>
    );
  }

  if (!user) {
    return (
      <Container size="sm" py="xl">
        <Paper p="xl" radius="md" withBorder>
          <Stack align="center" gap="md">
            <Text>Debes iniciar sesion para ver tu perfil</Text>
            <Button component="a" href="/login">
              Iniciar Sesion
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
        <Title order={1}>Mi Perfil</Title>

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
                label="Telefono"
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
          <form onSubmit={passwordForm.onSubmit(handlePasswordSubmit)}>
            <Stack gap="md">
              <Title order={3}>Cambiar Contrasena</Title>

              <PasswordInput
                label="Nueva contrasena"
                placeholder="Minimo 6 caracteres"
                {...passwordForm.getInputProps('newPassword')}
              />

              <PasswordInput
                label="Confirmar contrasena"
                placeholder="Repite la nueva contrasena"
                {...passwordForm.getInputProps('confirmPassword')}
              />

              <Group justify="flex-end">
                <Button type="submit" loading={changingPassword} variant="outline">
                  Cambiar Contrasena
                </Button>
              </Group>
            </Stack>
          </form>
        </Paper>

        <Divider />

        {/* Account Actions */}
        <Paper shadow="sm" p="lg" radius="md" withBorder>
          <Stack gap="md">
            <Title order={3}>Cuenta</Title>
            <Text size="sm" c="dimmed">
              Miembro desde: {formatDate(user.created_at)}
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
