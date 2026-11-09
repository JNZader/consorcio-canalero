import {
  AppShell,
  Avatar,
  Box,
  Burger,
  Container,
  Divider,
  Group,
  Menu,
  NavLink,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { Link, useNavigate } from '@tanstack/react-router';
import { useEffect, useState } from 'react';
import { signOut } from '../../lib/auth';
import { consumeLocalLogoutWarning } from '../../lib/auth/storage';
import { showError, showNotification } from '../../lib/notifications';
import { type UserRole, useAuthStore, useUserRole } from '../../stores/authStore';
import ThemeToggle from '../ThemeToggle';
import {
  IconArrowLeft,
  IconCalendar,
  IconChartBar,
  IconCoin,
  IconColorSwatch,
  IconHome,
  IconInbox,
  IconLogout,
  IconMap,
  IconMountain,
  IconPhoto,
  IconSettings,
  IconUser,
  IconUsers,
} from '../ui/icons';

interface NavItem {
  label: string;
  to: string;
  icon: typeof IconChartBar;
  roles?: ReadonlyArray<UserRole>;
}

interface NavSection {
  label: string;
  items: ReadonlyArray<NavItem>;
}

// Navigation sections
const NAV_SECTIONS: ReadonlyArray<NavSection> = [
  {
    label: 'Análisis Técnico',
    items: [
      { label: 'Dashboard', to: '/admin', icon: IconChartBar },
      { label: 'Explorador de Imágenes', to: '/admin/images', icon: IconPhoto },
      { label: 'DEM Pipeline', to: '/admin/dem-pipeline', icon: IconMountain },
      { label: 'Publicación de canales', to: '/admin/canales', icon: IconMap },
    ],
  },
  {
    label: 'Gestión',
    items: [
      { label: 'Participación', to: '/admin/participacion', icon: IconUsers },
      { label: 'Trámites', to: '/admin/tramites', icon: IconSettings },
      { label: 'Reuniones', to: '/admin/reuniones', icon: IconCalendar },
      { label: 'Padrón', to: '/admin/padron', icon: IconUser },
      { label: 'Finanzas', to: '/admin/finanzas', icon: IconCoin },
      // U8: the mailbox of legal consultations. Restricted to admin role matching ConocimientoPanel.
      {
        label: 'Consultas normativas',
        to: '/admin/conocimiento',
        icon: IconInbox,
        roles: ['admin'],
      },
      {
        label: 'Laboratorio de tema',
        to: '/admin/laboratorio-tema',
        icon: IconColorSwatch,
        roles: ['admin'],
      },
    ],
  },
];

export const ADMIN_ACCOUNT_MENU_ITEMS = {
  profile: { label: 'Perfil', to: '/perfil' },
  site: { label: 'Volver al sitio', to: '/' },
  logout: { label: 'Cerrar sesión', to: '/login' },
} as const;

interface AdminLayoutProps {
  readonly children: React.ReactNode;
  readonly currentPath?: string;
}

/**
 * AdminLayoutContent - Contenido interno del layout de admin.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 */
export function AdminLayoutContent({ children, currentPath = '/admin' }: AdminLayoutProps) {
  const [opened, setOpened] = useState(false);
  const navigate = useNavigate();
  const profile = useAuthStore((s) => s.profile);
  const userRole = useUserRole();
  const effectiveRole: UserRole = userRole ?? 'operador';
  const roleLabel =
    userRole === 'operador' ? 'Operador' : userRole === 'admin' ? 'Administrador' : 'Admin';
  const displayName = profile?.nombre || roleLabel;
  const avatarInitials = profile?.nombre
    ? profile.nombre
        .split(' ')
        .map((n) => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)
    : userRole === 'operador'
      ? 'O'
      : 'A';

  useEffect(() => {
    setOpened(false);
  }, [currentPath]);

  const handleLogout = async (): Promise<void> => {
    try {
      const result = await signOut();
      if (!result.success) {
        throw new Error(result.error || 'No se pudo cerrar la sesión.');
      }
      await navigate({ to: ADMIN_ACCOUNT_MENU_ITEMS.logout.to, replace: true });
      const warning = consumeLocalLogoutWarning() ?? result.warning;
      if (warning) {
        showNotification('Sesión cerrada localmente', warning, 'yellow');
      }
    } catch (error) {
      showError(
        'No se pudo cerrar la sesión',
        error instanceof Error ? error.message : 'Intentá nuevamente.'
      );
    }
  };

  return (
    <AppShell
      header={{ height: 64 }}
      navbar={{
        width: 260,
        breakpoint: 'sm',
        collapsed: { mobile: !opened },
      }}
      padding="lg"
    >
      {/* Header - mismo estilo que el header principal */}
      <AppShell.Header
        style={{
          backgroundColor: 'var(--mantine-color-body)',
          borderBottom: '1px solid var(--mantine-color-default-border)',
        }}
      >
        <Container size="xl" h="100%">
          <Group h="100%" justify="space-between" wrap="nowrap">
            <Group gap="sm" wrap="nowrap" style={{ minWidth: 0, overflow: 'hidden' }}>
              <Burger
                opened={opened}
                onClick={() => setOpened(!opened)}
                hiddenFrom="sm"
                size="sm"
                aria-label={opened ? 'Cerrar menú de navegación' : 'Abrir menú de navegación'}
                aria-expanded={opened}
              />
              <UnstyledButton component={Link} to="/admin" style={{ minWidth: 0 }}>
                <Group gap="xs" wrap="nowrap">
                  <Text size="xl" fw={700} truncate style={{ color: 'var(--cc-color-wordmark)' }}>
                    Consorcio Canalero
                  </Text>
                  <Text size="sm" c="dimmed" visibleFrom="sm">
                    {roleLabel}
                  </Text>
                </Group>
              </UnstyledButton>
            </Group>

            <Group gap="xs" wrap="nowrap" style={{ flexShrink: 0 }}>
              <ThemeToggle />

              <Menu shadow="lg" width={220} position="bottom-end">
                <Menu.Target>
                  <UnstyledButton
                    aria-label={
                      displayName ? `Cuenta ${roleLabel} - ${displayName}` : `Cuenta ${roleLabel}`
                    }
                    style={{
                      padding: 'var(--mantine-spacing-xs) var(--mantine-spacing-sm)',
                      borderRadius: 'var(--mantine-radius-md)',
                      transition: 'background-color 0.2s',
                    }}
                  >
                    <Group gap="xs">
                      <Avatar
                        radius="md"
                        size="sm"
                        variant="gradient"
                        gradient={{ from: 'blue.6', to: 'cyan.5', deg: 135 }}
                      >
                        {avatarInitials}
                      </Avatar>
                      <Box visibleFrom="sm">
                        <Text size="sm" fw={500}>
                          {displayName}
                        </Text>
                      </Box>
                    </Group>
                  </UnstyledButton>
                </Menu.Target>

                <Menu.Dropdown>
                  <Menu.Label>Cuenta</Menu.Label>
                  <Menu.Item
                    component={Link}
                    to={ADMIN_ACCOUNT_MENU_ITEMS.profile.to}
                    leftSection={<IconUser size={16} />}
                  >
                    {ADMIN_ACCOUNT_MENU_ITEMS.profile.label}
                  </Menu.Item>
                  <Menu.Divider />
                  <Menu.Item
                    component={Link}
                    to={ADMIN_ACCOUNT_MENU_ITEMS.site.to}
                    leftSection={<IconHome size={16} />}
                  >
                    {ADMIN_ACCOUNT_MENU_ITEMS.site.label}
                  </Menu.Item>
                  <Menu.Item
                    color="red"
                    onClick={() => {
                      void handleLogout().catch(() => undefined);
                    }}
                    leftSection={<IconLogout size={16} />}
                  >
                    {ADMIN_ACCOUNT_MENU_ITEMS.logout.label}
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </Group>
          </Group>
        </Container>
      </AppShell.Header>

      {/* Sidebar */}
      <AppShell.Navbar p="md">
        <AppShell.Section grow mt="xs" style={{ overflowY: 'auto' }}>
          {NAV_SECTIONS.map((section, sectionIdx) => (
            <Box key={section.label}>
              {sectionIdx > 0 && <Divider my="sm" />}
              <Text size="xs" fw={700} c="dimmed" tt="uppercase" px="sm" mb={4}>
                {section.label}
              </Text>
              {section.items
                .filter((item) => !item.roles || item.roles.includes(effectiveRole))
                .map((item) => (
                  <NavLink
                    key={item.to}
                    component={Link}
                    to={item.to}
                    label={
                      <Text size="sm" fw={currentPath === item.to ? 600 : 400}>
                        {item.label}
                      </Text>
                    }
                    leftSection={<item.icon size={20} />}
                    active={currentPath === item.to}
                    mb="xs"
                    style={{
                      borderRadius: 'var(--mantine-radius-md)',
                      transition: 'all 0.15s ease',
                    }}
                    variant={currentPath === item.to ? 'light' : 'subtle'}
                  />
                ))}
            </Box>
          ))}
        </AppShell.Section>

        <AppShell.Section>
          <Divider my="md" />
          <NavLink
            component={Link}
            to="/mapa"
            label={<Text size="sm">Ver Mapa</Text>}
            leftSection={<IconMap size={20} />}
            variant="subtle"
            mb="xs"
            style={{ borderRadius: 'var(--mantine-radius-md)' }}
          />
          <NavLink
            component={Link}
            to="/"
            label={<Text size="sm">Volver al sitio</Text>}
            leftSection={<IconArrowLeft size={20} />}
            variant="subtle"
            style={{ borderRadius: 'var(--mantine-radius-md)' }}
          />
        </AppShell.Section>
      </AppShell.Navbar>

      {/* Main content - div to prevent duplicate main landmark inside RootLayout */}
      <AppShell.Main
        component="div"
        style={{
          background: 'light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-8))',
          minHeight: '100vh',
        }}
      >
        {children}
      </AppShell.Main>
    </AppShell>
  );
}

/**
 * AdminLayout - Page component (MantineProvider is provided by main.tsx).
 */
export default function AdminLayout(props: AdminLayoutProps) {
  return <AdminLayoutContent {...props} />;
}
