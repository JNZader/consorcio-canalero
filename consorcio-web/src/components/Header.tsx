import {
  Box,
  Burger,
  Button,
  Container,
  Divider,
  Drawer,
  Group,
  Skeleton,
  Stack,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Link } from '@tanstack/react-router';
import { Suspense, lazy, memo, useEffect, useRef } from 'react';
import styles from '../styles/components/header.module.css';
import ThemeToggle from './ThemeToggle';

// Lazy load UserMenu para evitar cargar Supabase (~58KB) en el bundle inicial
const UserMenu = lazy(() => import('./UserMenu'));

// Links publicos (visibles para todos)
const PUBLIC_LINKS = [
  { to: '/', label: 'Inicio' },
  { to: '/mapa', label: 'Mapa' },
  { to: '/reportes', label: 'Reportes' },
  { to: '/sugerencias', label: 'Sugerencias' },
] as const;

// Skeleton de carga para el UserMenu (desktop)
function UserMenuSkeleton() {
  return (
    <Box style={{ minWidth: 120, display: 'flex', justifyContent: 'flex-end' }}>
      <Skeleton height={36} width={120} radius="sm" />
    </Box>
  );
}

// Skeleton de carga para el UserMenu (mobile)
function MobileUserMenuSkeleton() {
  return <Skeleton height={36} radius="sm" />;
}

/**
 * HeaderContent - Contenido interno del header sin MantineProvider.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 * Memoizado para evitar re-renders innecesarios en cambios de tema.
 */
export const HeaderContent = memo(function HeaderContent() {
  const [opened, { toggle, close }] = useDisclosure(false);
  const drawerRef = useRef<HTMLDivElement>(null);

  // Focus trap para el drawer movil
  useEffect(() => {
    if (!opened || !drawerRef.current) return;

    const drawer = drawerRef.current;
    const focusableElements = drawer.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );

    if (focusableElements.length === 0) return;

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    // Enfocar el primer elemento al abrir
    setTimeout(() => firstElement.focus(), 100);

    const handleKeyDown = (e: KeyboardEvent) => {
      // Handle Escape key to close drawer
      if (e.key === 'Escape') {
        e.preventDefault();
        close();
        return;
      }

      if (e.key === 'Tab') {
        if (e.shiftKey) {
          // Shift + Tab
          if (document.activeElement === firstElement) {
            e.preventDefault();
            lastElement.focus();
          }
        } else if (document.activeElement === lastElement) {
          // Tab
          e.preventDefault();
          firstElement.focus();
        }
      }
    };

    drawer.addEventListener('keydown', handleKeyDown);

    return () => {
      drawer.removeEventListener('keydown', handleKeyDown);
    };
  }, [opened, close]);

  return (
    <Box component="header" className={styles.header}>
      <Container size="xl" py="sm">
        <Group justify="space-between">
          {/* Logo */}
          <UnstyledButton
            component={Link}
            to="/"
            aria-label="Consorcio Canalero 10 de Mayo - Ir a pagina de inicio"
          >
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
                10 de Mayo
              </Text>
            </Group>
          </UnstyledButton>

          {/* Desktop Navigation */}
          <nav aria-label="Navegacion principal" id="primary-nav">
            <Group gap="sm" visibleFrom="sm">
              {PUBLIC_LINKS.map((link) => (
                <Button
                  key={link.to}
                  component={Link}
                  to={link.to}
                  variant="subtle"
                  color="gray"
                >
                  {link.label}
                </Button>
              ))}

              <ThemeToggle />

              {/* UserMenu lazy loaded - auth code se carga solo cuando necesario */}
              <Suspense fallback={<UserMenuSkeleton />}>
                <UserMenu variant="desktop" />
              </Suspense>
            </Group>
          </nav>

          {/* Mobile - Theme + Burger */}
          <Group gap="xs" hiddenFrom="sm">
            <ThemeToggle />
            <Burger
              opened={opened}
              onClick={toggle}
              aria-label={opened ? 'Cerrar menu de navegacion' : 'Abrir menu de navegacion'}
              aria-expanded={opened}
              aria-controls="mobile-nav-drawer"
            />
          </Group>
        </Group>
      </Container>

      {/* Mobile Drawer */}
      <Drawer
        opened={opened}
        onClose={close}
        size="100%"
        padding="md"
        title="Menu"
        hiddenFrom="sm"
        zIndex={1000}
        id="mobile-nav-drawer"
        trapFocus
        returnFocus
      >
        <Box ref={drawerRef}>
          <nav aria-label="Navegacion movil">
            <Stack gap="sm">
              {PUBLIC_LINKS.map((link) => (
                <Button
                  key={link.to}
                  component={Link}
                  to={link.to}
                  variant="subtle"
                  color="gray"
                  fullWidth
                  justify="flex-start"
                  onClick={close}
                >
                  {link.label}
                </Button>
              ))}
            </Stack>
          </nav>

          <Divider my="sm" />

          {/* UserMenu lazy loaded - mobile variant */}
          <Suspense fallback={<MobileUserMenuSkeleton />}>
            <UserMenu variant="mobile" onMobileClose={close} />
          </Suspense>
        </Box>
      </Drawer>
    </Box>
  );
});

/**
 * Header - Componente principal del header.
 *
 * En la arquitectura SPA, el MantineProvider está en main.tsx,
 * por lo que exportamos HeaderContent directamente.
 */
export default HeaderContent;
