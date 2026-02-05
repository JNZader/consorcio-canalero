import type { User } from '@supabase/supabase-js';
import {
  Avatar,
  Box,
  Button,
  Divider,
  Group,
  Menu,
  Skeleton,
  Stack,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { signOut } from '../lib/auth';
import { useAuthLoading, useAuthStore } from '../stores/authStore';
import type { Usuario } from '../types';
import { IconChartBar, IconLogout, IconUser } from './ui/icons';

interface UserMenuProps {
  readonly variant: 'desktop' | 'mobile';
  readonly onMobileClose?: () => void;
}

// Role labels mapping
const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrador',
  operador: 'Operador',
};

// Helper to get role label
function getRoleLabel(rol: string | undefined): string {
  return ROLE_LABELS[rol ?? ''] ?? 'Usuario';
}

// Helper to get user initials
function getInitials(
  profile: { nombre?: string } | null,
  user: { email?: string } | null
): string {
  if (profile?.nombre) {
    return profile.nombre
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  }
  return user?.email?.charAt(0).toUpperCase() ?? 'U';
}

// Helper to get display name
function getDisplayName(
  profile: { nombre?: string } | null,
  user: { email?: string } | null
): string {
  return profile?.nombre ?? user?.email?.split('@')[0] ?? 'Usuario';
}

// Extracted: Loading skeleton for desktop
function DesktopLoadingSkeleton() {
  return (
    <Box style={{ minWidth: 120, display: 'flex', justifyContent: 'flex-end' }}>
      <Skeleton height={36} width={120} radius="sm" />
    </Box>
  );
}

// Extracted: Login button for desktop
function DesktopLoginButton() {
  return (
    <Box style={{ minWidth: 120, display: 'flex', justifyContent: 'flex-end' }}>
      <Button component="a" href="/login" style={{ minWidth: 120 }}>
        Iniciar Sesion
      </Button>
    </Box>
  );
}

// Extracted: Staff menu items
function StaffMenuItems() {
  return (
    <>
      <Menu.Item leftSection={<IconChartBar size={14} />} component="a" href="/admin">
        Panel de Control
      </Menu.Item>
      <Menu.Divider />
    </>
  );
}

// Desktop variant component
function DesktopUserMenu({
  user,
  profile,
  loading,
  isStaff,
  handleLogout,
}: Readonly<{
  user: User | null;
  profile: Usuario | null;
  loading: boolean;
  isStaff: boolean;
  handleLogout: () => Promise<void>;
}>) {
  if (loading) return <DesktopLoadingSkeleton />;
  if (!user) return <DesktopLoginButton />;

  return (
    <Box style={{ minWidth: 120, display: 'flex', justifyContent: 'flex-end' }}>
      <Menu shadow="md" width={200} position="bottom-end">
        <Menu.Target>
          <UnstyledButton aria-label="Menu de usuario">
            <Group gap="xs">
              <Avatar color="institucional" radius="xl" size="sm">
                {getInitials(profile, user)}
              </Avatar>
              <Text size="sm" visibleFrom="md">
                {getDisplayName(profile, user)}
              </Text>
            </Group>
          </UnstyledButton>
        </Menu.Target>

        <Menu.Dropdown>
          <Menu.Label>{getRoleLabel(profile?.rol)}</Menu.Label>

          {isStaff && <StaffMenuItems />}

          <Menu.Item leftSection={<IconUser size={14} />} component="a" href="/perfil">
            Mi Perfil
          </Menu.Item>

          <Menu.Divider />

          <Menu.Item color="red" leftSection={<IconLogout size={14} />} onClick={handleLogout}>
            Cerrar Sesion
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>
    </Box>
  );
}

// Extracted: Mobile staff buttons
function MobileStaffButtons({
  isStaff,
  onMobileClose,
}: Readonly<{
  isStaff: boolean;
  onMobileClose?: () => void;
}>) {
  if (!isStaff) return null;

  return (
    <Button
      component="a"
      href="/admin"
      variant="subtle"
      color="gray"
      fullWidth
      justify="flex-start"
      leftSection={<IconChartBar size={16} />}
      onClick={onMobileClose}
    >
      Panel de Control
    </Button>
  );
}

// Mobile variant component
function MobileUserMenu({
  user,
  profile,
  loading,
  isStaff,
  handleLogout,
  onMobileClose,
}: Readonly<{
  user: User | null;
  profile: Usuario | null;
  loading: boolean;
  isStaff: boolean;
  handleLogout: () => Promise<void>;
  onMobileClose?: () => void;
}>) {
  if (loading) {
    return <Skeleton height={36} radius="sm" />;
  }

  if (!user) {
    return (
      <Button component="a" href="/login" fullWidth onClick={onMobileClose}>
        Iniciar Sesion
      </Button>
    );
  }

  const handleLogoutClick = () => {
    onMobileClose?.();
    void handleLogout();
  };

  return (
    <>
      <Group gap="sm" px="sm" py="xs">
        <Avatar color="institucional" radius="xl" size="sm">
          {getInitials(profile, user)}
        </Avatar>
        <Box>
          <Text size="sm" fw={500}>
            {getDisplayName(profile, user)}
          </Text>
          <Text size="xs" c="gray.6">
            {getRoleLabel(profile?.rol)}
          </Text>
        </Box>
      </Group>

      <Divider my="sm" />

      <Stack gap="sm">
        <MobileStaffButtons isStaff={isStaff} onMobileClose={onMobileClose} />

        <Button
          component="a"
          href="/perfil"
          variant="subtle"
          color="gray"
          fullWidth
          justify="flex-start"
          leftSection={<IconUser size={16} />}
          onClick={onMobileClose}
        >
          Mi Perfil
        </Button>

        <Button
          variant="light"
          color="red"
          fullWidth
          leftSection={<IconLogout size={16} />}
          onClick={handleLogoutClick}
        >
          Cerrar Sesion
        </Button>
      </Stack>
    </>
  );
}

/**
 * UserMenu - Componente que maneja la UI de autenticacion.
 * Se carga de forma lazy para evitar cargar Supabase en el bundle inicial.
 *
 * Uses useAuthLoading hook which returns true when:
 * - Auth is still loading
 * - Auth store is not yet initialized
 * This prevents showing wrong state during hydration.
 */
export default function UserMenu({ variant, onMobileClose }: UserMenuProps) {
  const { user, profile } = useAuthStore();
  // Use the combined loading hook that checks both loading and initialized
  const loading = useAuthLoading();

  const isStaff = profile?.rol === 'admin' || profile?.rol === 'operador';

  const handleLogout = async () => {
    await signOut();
    globalThis.location.href = '/';
  };

  const commonProps = { user, profile, loading, isStaff, handleLogout };

  if (variant === 'desktop') {
    return <DesktopUserMenu {...commonProps} />;
  }

  return <MobileUserMenu {...commonProps} onMobileClose={onMobileClose} />;
}
