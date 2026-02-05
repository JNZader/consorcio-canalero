import { Box, Button, Center, Group, Loader, Paper, Stack, Text, ThemeIcon } from '@mantine/core';
import { useEffect, useState } from 'react';
import { useAuth, type UserRole } from '../../hooks/useAuth';
import MantineProvider from '../MantineProvider';
import { IconArrowLeft, IconLock } from '../ui/icons';

/**
 * Props para el componente ProtectedRoute
 */
interface ProtectedRouteProps {
  /** Contenido a renderizar si la autenticacion es exitosa */
  readonly children: React.ReactNode;
  /** Roles permitidos para acceder a esta ruta */
  readonly allowedRoles?: UserRole[];
  /** URL a la que redirigir si no esta autenticado */
  readonly loginUrl?: string;
  /** URL a la que redirigir si no tiene permisos */
  readonly unauthorizedUrl?: string;
  /** Mensaje personalizado cuando no tiene permisos */
  readonly unauthorizedMessage?: string;
}

/**
 * Componente de carga mientras se verifica la autenticacion
 */
function LoadingState() {
  return (
    <Center mih="100vh">
      <Stack align="center" gap="md">
        <Loader size="lg" type="dots" />
        <Text c="gray.6" size="sm">
          Verificando sesion...
        </Text>
      </Stack>
    </Center>
  );
}

/**
 * Componente que se muestra cuando el usuario no tiene permisos
 */
function UnauthorizedState({
  message,
  onGoBack,
  onGoHome,
}: Readonly<{
  message: string;
  onGoBack: () => void;
  onGoHome: () => void;
}>) {
  return (
    <Center mih="100vh">
      <Paper shadow="md" p="xl" radius="md" w={400}>
        <Stack align="center" gap="lg">
          <ThemeIcon size={64} radius="xl" color="red" variant="light">
            <IconLock size={32} />
          </ThemeIcon>

          <Box ta="center">
            <Text size="xl" fw={600} mb="xs">
              Acceso Denegado
            </Text>
            <Text c="gray.6" size="sm">
              {message}
            </Text>
          </Box>

          <Group justify="center" gap="md">
            <Button variant="light" leftSection={<IconArrowLeft size={16} />} onClick={onGoBack}>
              Volver
            </Button>
            <Button onClick={onGoHome}>Ir al Inicio</Button>
          </Group>
        </Stack>
      </Paper>
    </Center>
  );
}

/**
 * Componente que se muestra cuando no hay sesion activa
 */
function NotAuthenticatedState({ loginUrl }: Readonly<{ loginUrl: string }>) {
  useEffect(() => {
    // Guardar la URL actual para redirigir despues del login
    const currentUrl = globalThis.location.pathname + globalThis.location.search;
    sessionStorage.setItem('redirectAfterLogin', currentUrl);

    // Redirigir al login
    globalThis.location.href = loginUrl;
  }, [loginUrl]);

  return (
    <Center mih="100vh">
      <Stack align="center" gap="md">
        <Loader size="lg" type="dots" />
        <Text c="gray.6" size="sm">
          Redirigiendo al inicio de sesion...
        </Text>
      </Stack>
    </Center>
  );
}

/**
 * ProtectedRouteContent - Contenido principal del ProtectedRoute sin MantineProvider.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 */
export function ProtectedRouteContent({
  children,
  allowedRoles = ['admin', 'operador'],
  loginUrl = '/login',
  unauthorizedUrl,
  unauthorizedMessage = 'No tienes permisos para acceder a esta seccion.',
}: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, profile, canAccess } = useAuth();
  const [authState, setAuthState] = useState<
    'loading' | 'authenticated' | 'not-authenticated' | 'unauthorized'
  >('loading');

  useEffect(() => {
    if (isLoading) {
      setAuthState('loading');
      return;
    }

    if (!isAuthenticated) {
      setAuthState('not-authenticated');
      return;
    }

    // Verify role if allowed roles are specified
    if (allowedRoles.length > 0 && profile) {
      const hasPermission = canAccess(allowedRoles);
      setAuthState(hasPermission ? 'authenticated' : 'unauthorized');
    } else if (profile) {
      // If no roles specified, any authenticated user can access
      setAuthState('authenticated');
    } else {
      // Still loading profile
      setAuthState('loading');
    }
  }, [isAuthenticated, profile, isLoading, allowedRoles, canAccess]);

  // Estado de carga
  if (authState === 'loading') {
    return <LoadingState />;
  }

  // No autenticado - redirigir al login
  if (authState === 'not-authenticated') {
    return <NotAuthenticatedState loginUrl={loginUrl} />;
  }

  // Sin permisos
  if (authState === 'unauthorized') {
    // Si hay URL de redireccion, redirigir
    if (unauthorizedUrl) {
      globalThis.location.href = unauthorizedUrl;
      return <LoadingState />;
    }

    // Mostrar mensaje de acceso denegado
    return (
      <UnauthorizedState
        message={unauthorizedMessage}
        onGoBack={() => globalThis.history.back()}
        onGoHome={() => {
          globalThis.location.href = '/';
        }}
      />
    );
  }

  // Autenticado y con permisos - renderizar contenido
  return <>{children}</>;
}

/**
 * Componente ProtectedRoute
 *
 * Protege rutas verificando:
 * 1. Que el usuario tenga una sesion activa
 * 2. Que el usuario tenga el rol requerido (admin/operador)
 *
 * @example
 * ```tsx
 * <ProtectedRoute allowedRoles={['admin']}>
 *   <AdminDashboard />
 * </ProtectedRoute>
 * ```
 *
 * @example
 * ```tsx
 * // Solo requiere autenticacion, cualquier rol
 * <ProtectedRoute allowedRoles={[]}>
 *   <UserProfile />
 * </ProtectedRoute>
 * ```
 */
export default function ProtectedRoute(props: ProtectedRouteProps) {
  return (
    <MantineProvider>
      <ProtectedRouteContent {...props} />
    </MantineProvider>
  );
}

/**
 * HOC to protect page components.
 *
 * @example
 * ```tsx
 * const ProtectedAdminPage = withAuth(AdminDashboard, {
 *   allowedRoles: ['admin'],
 * });
 * ```
 */
export function withAuth<P extends object>(
  Component: React.ComponentType<P>,
  options: Omit<ProtectedRouteProps, 'children'> = {}
) {
  return function ProtectedComponent(props: P) {
    return (
      <ProtectedRoute {...options}>
        <Component {...props} />
      </ProtectedRoute>
    );
  };
}

/**
 * Hook para verificar permisos en componentes
 * Util cuando necesitas verificar permisos sin redirigir
 *
 * @deprecated Use the useAuth hook instead for a cleaner API:
 * ```tsx
 * const { isAuthenticated, isLoading, role, canAccess } = useAuth();
 * const hasAccess = canAccess(['admin', 'operador']);
 * ```
 *
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { canAccess, isLoading } = usePermissions(['admin']);
 *
 *   if (isLoading) return <Loader />;
 *   if (!canAccess) return <Text>Sin permisos</Text>;
 *
 *   return <AdminContent />;
 * }
 * ```
 */
export function usePermissions(allowedRoles: UserRole[] = ['admin', 'operador']) {
  const { isAuthenticated, isLoading, role, canAccess } = useAuth();

  return {
    canAccess: canAccess(allowedRoles),
    isLoading,
    isAuthenticated,
    userRole: role,
  };
}
