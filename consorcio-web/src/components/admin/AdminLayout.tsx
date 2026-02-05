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
import { useState } from 'react';
import { Link } from '@tanstack/react-router';
import MantineProvider from '../MantineProvider';
import ThemeToggle from '../ThemeToggle';
import {
  IconArrowLeft,
  IconCalendar,
  IconChartBar,
  IconClipboardList,
  IconCoin,
  IconHome,
  IconLightbulb,
  IconLogout,
  IconMap,
  IconPhoto,
  IconSettings,
  IconUser,
} from '../ui/icons';

// Simplified navigation - core features only
const NAV_ITEMS = [
  { label: 'Dashboard', to: '/admin', icon: IconChartBar },
  { label: 'Explorador de Imagenes', to: '/admin/images', icon: IconPhoto },
  { label: 'Reportes', to: '/admin/reports', icon: IconClipboardList },
  { label: 'Sugerencias', to: '/admin/sugerencias', icon: IconLightbulb },
  { label: 'Trámites', to: '/admin/tramites', icon: IconSettings },
  { label: 'Reuniones', to: '/admin/reuniones', icon: IconCalendar },
  { label: 'Padrón', to: '/admin/padron', icon: IconUser },
  { label: 'Finanzas', to: '/admin/finanzas', icon: IconCoin },
];
  

interface AdminLayoutProps {
  readonly children: React.ReactNode;
  readonly currentPath?: string;
}

/**
 * AdminLayoutContent - Contenido interno del layout de admin sin MantineProvider.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 */
export function AdminLayoutContent({ children, currentPath = '/admin' }: AdminLayoutProps) {
  const [opened, setOpened] = useState(false);

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
          <Group h="100%" justify="space-between">
            <Group gap="md">
              <Burger
                opened={opened}
                onClick={() => setOpened(!opened)}
                hiddenFrom="sm"
                size="sm"
                aria-label="Abrir menu de navegacion"
              />
              <UnstyledButton component={Link} to="/admin">
                <Group gap="xs">
                  <Text
                    size="xl"
                    fw={700}
                    variant="gradient"
                    gradient={{ from: 'institucional.8', to: 'acento.5', deg: 45 }}
                  >
                    Consorcio Canalero
                  </Text>
                  <Text size="xs" c="gray.6" visibleFrom="sm">
                    Admin
                  </Text>
                </Group>
              </UnstyledButton>
            </Group>

            <Group gap="sm">
              <ThemeToggle />

              <Menu shadow="lg" width={220} position="bottom-end">
                <Menu.Target>
                  <UnstyledButton
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
                        A
                      </Avatar>
                      <Box visibleFrom="sm">
                        <Text size="sm" fw={500}>
                          Admin
                        </Text>
                      </Box>
                    </Group>
                  </UnstyledButton>
                </Menu.Target>

                <Menu.Dropdown>
                  <Menu.Label>Cuenta</Menu.Label>
                  <Menu.Item component={Link} to="/perfil" leftSection={<IconUser size={16} />}>Perfil</Menu.Item>
                  <Menu.Item leftSection={<IconSettings size={16} />}>Configuracion</Menu.Item>
                  <Menu.Divider />
                  <Menu.Item component={Link} to="/" leftSection={<IconHome size={16} />}>
                    Volver al sitio
                  </Menu.Item>
                  <Menu.Item
                    color="red"
                    component={Link}
                    to="/login"
                    leftSection={<IconLogout size={16} />}
                  >
                    Cerrar sesion
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </Group>
          </Group>
        </Container>
      </AppShell.Header>

      {/* Sidebar */}
      <AppShell.Navbar p="md">
        <AppShell.Section grow mt="xs">
          {NAV_ITEMS.map((item) => (
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

      {/* Main content */}
      <AppShell.Main
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
 * AdminLayout - Standalone component with MantineProvider.
 */
export default function AdminLayout(props: AdminLayoutProps) {
  return (
    <MantineProvider>
      <AdminLayoutContent {...props} />
    </MantineProvider>
  );
}
