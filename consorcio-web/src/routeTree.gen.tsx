/**
 * Route tree for TanStack Router.
 *
 * SIMPLIFIED VERSION - Core functionality only:
 * - Public: Home, Map, Reports (denuncias)
 * - Admin: Dashboard, Reports management, Image explorer
 *
 * Complex analysis features moved to GEE Code Editor / QGIS
 *
 * Performance: Uses lazy loading for all page components to reduce initial bundle size.
 */

import { createRoute, createRootRoute, redirect, Outlet, useLocation } from '@tanstack/react-router';
import { useEffect, useState, lazy, Suspense } from 'react';
import { Center, Loader, Text, Stack } from '@mantine/core';

import { RootLayout } from './components/RootLayout';
import { useAuthStore } from './stores/authStore';
import { getSupabaseClient } from './lib/supabase';
import { logger } from './lib/logger';

// Lazy load all page components for better performance
const HomePage = lazy(() => import('./components/HomePage'));
const LoginForm = lazy(() => import('./components/LoginForm'));
const MapaPage = lazy(() => import('./components/MapaPage'));
const ReportesPage = lazy(() => import('./components/ReportesPage'));
const ProfilePanel = lazy(() => import('./components/ProfilePanel'));
const SugerenciasPage = lazy(() => import('./components/SugerenciasPage'));
const NotFound = lazy(() => import('./components/NotFound'));

// Admin components - lazy load only the content, not the layout
const AdminDashboard = lazy(() => import('./components/admin/AdminDashboard'));
const ImageExplorerPanel = lazy(() => import('./components/admin/images/ImageExplorerPanel'));
const ReportsPanel = lazy(() => import('./components/admin/reports/ReportsPanel'));
const SugerenciasPanel = lazy(() => import('./components/admin/sugerencias/SugerenciasPanel'));
const TramitesPanel = lazy(() => import('./components/admin/management/TramitesPanel'));
const ReunionesPanel = lazy(() => import('./components/admin/management/ReunionesPanel'));
const PadronPanel = lazy(() => import('./components/admin/management/PadronPanel'));
const FinanzasPanel = lazy(() => import('./components/admin/management/FinanzasPanel'));

// Import admin layout directly (not lazy) to prevent flicker
import { AdminLayoutContent } from './components/admin/AdminLayout';

// Suspense fallback for lazy loaded components
const PageLoader = () => (
  <Center mih="50vh">
    <Loader size="lg" />
  </Center>
);

// Lighter loader for admin content (doesn't block the layout)
const AdminContentLoader = () => (
  <Center mih="300px">
    <Loader size="md" />
  </Center>
);

// Helper to wait for auth initialization
async function waitForAuth() {
  const state = useAuthStore.getState();
  if (!state.initialized) {
    await new Promise<void>((resolve) => {
      const unsubscribe = useAuthStore.subscribe((s) => {
        if (s.initialized) {
          unsubscribe();
          resolve();
        }
      });
    });
  }
}

const RootComponent = () => (
  <div
    className="min-h-screen flex flex-col transition-colors duration-200"
    style={{ backgroundColor: 'var(--mantine-color-body, #f8faf9)' }}
  >
    <Outlet />
  </div>
);

const NotFoundComponent = () => (
  <RootLayout title="Pagina no encontrada" description="La pagina que buscas no existe.">
    <Suspense fallback={<PageLoader />}>
      <NotFound />
    </Suspense>
  </RootLayout>
);

// Recreate root route with proper component
const rootRouteWithComponent = createRootRoute({
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
});

// ============================================
// PUBLIC ROUTES
// ============================================

const indexRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/',
  component: () => (
    <RootLayout
      title="Inicio"
      description="Bienvenido al Consorcio Canalero 10 de Mayo. Sistema integral de gestion y monitoreo de cuencas hidricas."
    >
      <Suspense fallback={<PageLoader />}>
        <HomePage />
      </Suspense>
    </RootLayout>
  ),
});

const loginRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/login',
  component: () => (
    <RootLayout
      title="Iniciar Sesion"
      description="Accede al sistema de administracion del Consorcio Canalero 10 de Mayo."
      noindex={true}
    >
      <Suspense fallback={<PageLoader />}>
        <LoginForm />
      </Suspense>
    </RootLayout>
  ),
});

const mapaRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/mapa',
  component: () => (
    <RootLayout
      title="Mapa Interactivo"
      description="Explora el mapa interactivo de las cuencas hidricas del Consorcio Canalero 10 de Mayo."
    >
      <Suspense fallback={<PageLoader />}>
        <MapaPage />
      </Suspense>
    </RootLayout>
  ),
});

const reportesRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/reportes',
  validateSearch: (search: Record<string, unknown>) => ({
    auth: (search.auth as string) || undefined,
  }),
  component: () => (
    <RootLayout
      title="Reportar Incidente"
      description="Reporta incidentes en los canales del Consorcio Canalero 10 de Mayo."
    >
      <Suspense fallback={<PageLoader />}>
        <ReportesPage />
      </Suspense>
    </RootLayout>
  ),
});

const sugerenciasRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/sugerencias',
  component: () => (
    <RootLayout
      title="Buzon de Sugerencias"
      description="Envia sugerencias y propuestas al Consorcio Canalero 10 de Mayo."
    >
      <Suspense fallback={<PageLoader />}>
        <SugerenciasPage />
      </Suspense>
    </RootLayout>
  ),
});

// ============================================
// AUTH CALLBACK ROUTE (OAuth redirect handler)
// ============================================

function AuthCallbackPage() {
  const [error, setError] = useState<string | null>(null);
  const [debugInfo, setDebugInfo] = useState<string>('Procesando...');

  useEffect(() => {
    const handleCallback = async () => {
      logger.debug('[AUTH CALLBACK] Starting callback handler');
      logger.debug('[AUTH CALLBACK] Current URL:', window.location.href);
      setDebugInfo(`URL: ${window.location.href}`);

      try {
        const supabase = getSupabaseClient();

        // Get the code from URL params (PKCE flow)
        const urlParams = new URLSearchParams(window.location.search);
        const code = urlParams.get('code');
        const errorParam = urlParams.get('error');
        const errorDescription = urlParams.get('error_description');

        logger.debug('[AUTH CALLBACK] URL params:', { code: code ? 'present' : 'missing', errorParam, errorDescription });

        if (errorParam) {
          const errorMsg = `OAuth Error: ${errorParam} - ${errorDescription || 'Sin descripcion'}`;
          logger.error('[AUTH CALLBACK]', errorMsg);
          setError(errorMsg);
          setDebugInfo(`Error de Supabase/Google: ${errorParam}\nDescripcion: ${errorDescription || 'N/A'}\n\nRevisa la configuracion de OAuth en Supabase Dashboard.`);
          return; // No redirigir, mostrar error
        }

        if (code) {
          // Exchange the code for a session (PKCE flow)
          logger.debug('[AUTH CALLBACK] Exchanging code for session...');
          const { data, error } = await supabase.auth.exchangeCodeForSession(code);

          logger.debug('[AUTH CALLBACK] Exchange result:', {
            hasSession: !!data?.session,
            hasUser: !!data?.user,
            error: error?.message
          });

          if (error) {
            logger.error('[AUTH CALLBACK] Exchange error:', error);
            window.location.href = '/login?error=exchange_failed';
            return;
          }

          if (data.session) {
            logger.debug('[AUTH CALLBACK] Session established, checking profile...');
            // Successfully authenticated - check role
            const { data: profile } = await supabase
              .from('perfiles')
              .select('rol')
              .eq('id', data.session.user.id)
              .single();

            logger.debug('[AUTH CALLBACK] Profile:', { rol: profile?.rol });

            const role = profile?.rol;
            if (role === 'admin' || role === 'operador') {
              window.location.href = '/admin';
            } else {
              window.location.href = '/';
            }
            return;
          }
        }

        // Fallback: try to get existing session
        logger.debug('[AUTH CALLBACK] No code, checking existing session...');
        const { data: sessionData } = await supabase.auth.getSession();

        if (sessionData?.session) {
          logger.debug('[AUTH CALLBACK] Found existing session');
          window.location.href = '/';
        } else {
          logger.debug('[AUTH CALLBACK] No session found, redirecting to login');
          window.location.href = '/login';
        }
      } catch (err) {
        logger.error('[AUTH CALLBACK] Exception:', err);
        window.location.href = '/login?error=auth_failed';
      }
    };

    handleCallback();
  }, []);

  if (error) {
    return (
      <Center mih="100vh">
        <Stack align="center" gap="md" style={{ maxWidth: 600, padding: 20 }}>
          <Text size="xl" fw={700} c="red">Error de Autenticacion</Text>
          <Text c="dimmed" style={{ whiteSpace: 'pre-wrap', textAlign: 'center' }}>{debugInfo}</Text>
          <Text size="sm" c="blue" component="a" href="/login">Volver al login</Text>
        </Stack>
      </Center>
    );
  }

  return (
    <Center mih="100vh">
      <Stack align="center" gap="md">
        <Loader size="lg" />
        <Text c="dimmed">Autenticando...</Text>
        <Text size="xs" c="gray">{debugInfo}</Text>
      </Stack>
    </Center>
  );
}

const authCallbackRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/auth/callback',
  component: AuthCallbackPage,
});

// ============================================
// PROTECTED ROUTES (authenticated users)
// ============================================

// Dashboard route redirects to /admin for authorized users
const dashboardRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/dashboard',
  beforeLoad: async () => {
    await waitForAuth();
    const { user, profile } = useAuthStore.getState();
    if (!user) {
      throw redirect({ to: '/login' });
    }
    // Redirect to admin for commission members, otherwise to home
    const role = profile?.rol;
    if (role === 'admin' || role === 'operador') {
      throw redirect({ to: '/admin' });
    }
    throw redirect({ to: '/' });
  },
  component: () => null, // Never rendered, always redirects
});

const perfilRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/perfil',
  beforeLoad: async () => {
    await waitForAuth();
    const { user } = useAuthStore.getState();
    if (!user) {
      throw redirect({ to: '/login' });
    }
  },
  component: () => (
    <RootLayout
      title="Mi Perfil"
      description="Gestiona tu perfil de usuario."
    >
      <Suspense fallback={<PageLoader />}>
        <ProfilePanel />
      </Suspense>
    </RootLayout>
  ),
});

// ============================================
// ADMIN ROUTES (admin/operador only)
// ============================================

async function adminGuard() {
  await waitForAuth();
  const { user, profile } = useAuthStore.getState();
  if (!user) {
    throw redirect({ to: '/login' });
  }
  const role = profile?.rol;
  if (role !== 'admin' && role !== 'operador') {
    throw redirect({ to: '/' });
  }
}

// Admin layout component that uses Outlet for nested routes
// This stays mounted when navigating between admin pages, preventing flicker
function AdminLayoutWrapper() {
  const location = useLocation();

  return (
    <RootLayout title="Admin" noindex={true} hideHeader={true} hideFooter={true}>
      <AdminLayoutContent currentPath={location.pathname}>
        <Suspense fallback={<AdminContentLoader />}>
          <Outlet />
        </Suspense>
      </AdminLayoutContent>
    </RootLayout>
  );
}

// Parent admin route - layout stays mounted when navigating between child routes
const adminLayoutRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/admin',
  beforeLoad: adminGuard,
  component: AdminLayoutWrapper,
});

// Admin child routes - only the content changes when navigating
const adminIndexRoute = createRoute({
  getParentRoute: () => adminLayoutRoute,
  path: '/',
  component: () => <AdminDashboard />,
});

const adminImagesRoute = createRoute({
  getParentRoute: () => adminLayoutRoute,
  path: '/images',
  component: () => <ImageExplorerPanel />,
});

const adminReportsRoute = createRoute({
  getParentRoute: () => adminLayoutRoute,
  path: '/reports',
  component: () => <ReportsPanel />,
});

const adminSugerenciasRoute = createRoute({
  getParentRoute: () => adminLayoutRoute,
  path: '/sugerencias',
  component: () => <SugerenciasPanel />,
});

const adminTramitesRoute = createRoute({
  getParentRoute: () => adminLayoutRoute,
  path: '/tramites',
  component: () => <TramitesPanel />,
});

const adminReunionesRoute = createRoute({
  getParentRoute: () => adminLayoutRoute,
  path: '/reuniones',
  component: () => <ReunionesPanel />,
});

const adminPadronRoute = createRoute({
  getParentRoute: () => adminLayoutRoute,
  path: '/padron',
  component: () => <PadronPanel />,
});

const adminFinanzasRoute = createRoute({
  getParentRoute: () => adminLayoutRoute,
  path: '/finanzas',
  component: () => <FinanzasPanel />,
});

// ============================================
// ROUTE TREE
// ============================================

// Build admin route tree with nested children
const adminRouteTree = adminLayoutRoute.addChildren([
  adminIndexRoute,
  adminImagesRoute,
  adminReportsRoute,
  adminSugerenciasRoute,
  adminTramitesRoute,
  adminReunionesRoute,
  adminPadronRoute,
  adminFinanzasRoute,
]);

export const routeTree = rootRouteWithComponent.addChildren([
  // Public
  indexRoute,
  loginRoute,
  mapaRoute,
  reportesRoute,
  sugerenciasRoute,
  // Auth
  authCallbackRoute,
  // Protected
  dashboardRoute,
  perfilRoute,
  // Admin (nested routes)
  adminRouteTree,
]);
