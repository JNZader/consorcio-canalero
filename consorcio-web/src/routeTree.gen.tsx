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

import {
  createRoute,
  createRootRoute,
  redirect,
  Outlet,
  useLocation,
} from '@tanstack/react-router';
import { useEffect, useState, lazy, Suspense } from 'react';
import { Center, Loader, Text, Stack } from '@mantine/core';

import { RootLayout } from './components/RootLayout';
import { useAuthStore } from './stores/authStore';
import { withBasePath } from './lib/basePath';
import { authAdapter } from './lib/auth/index';
import { clearLocalLogoutTombstone, persistAuthSession } from './lib/auth/storage';
import { logger } from './lib/logger';

// PERF — ``HomePage`` is the ONLY page loaded eagerly. It is the landing
// route: lazy-loading it bought ~1.4 KB (brotli) of deferred bytes and cost a
// full extra round trip that could not even START until the entry bundle had
// finished parsing and executing — squarely inside the LCP window. Every other
// page stays lazy, because none of them is what a cold visitor lands on.
//
// NOTE: despite the ``.gen`` suffix this file is hand-maintained (no TanStack
// Router codegen plugin is configured), so this edit survives a build.
import HomePage from './components/HomePage';

// Lazy load the remaining page components for better performance
const LoginForm = lazy(() => import('./components/LoginForm'));
const MapaPage = lazy(() => import('./components/MapaPage'));
const ParticipacionPage = lazy(() => import('./components/ParticipacionPage'));
const ProfilePanel = lazy(() => import('./components/ProfilePanel'));
const ForgotPasswordForm = lazy(() => import('./components/auth/ForgotPasswordForm'));
const ResetPasswordForm = lazy(() => import('./components/auth/ResetPasswordForm'));
const VerifyEmailPage = lazy(() => import('./components/auth/VerifyEmailPage'));
const PrivacyPolicyPage = lazy(() => import('./components/PrivacyPolicyPage'));
const NotFound = lazy(() => import('./components/NotFound'));

// Admin components - lazy load only the content, not the layout
const AdminDashboard = lazy(() => import('./components/admin/AdminDashboard'));
const ImageExplorerPanel = lazy(() => import('./components/admin/images/ImageExplorerPanel'));
const ParticipacionPanel = lazy(
  () => import('./components/admin/participacion/ParticipacionPanel')
);
const TramitesPanel = lazy(() => import('./components/admin/management/TramitesPanel'));
const ReunionesPanel = lazy(() => import('./components/admin/management/ReunionesPanel'));
const PadronPanel = lazy(() => import('./components/admin/management/PadronPanel'));
const FinanzasPanel = lazy(() => import('./components/admin/management/FinanzasPanel'));
const DemPipelinePanel = lazy(() => import('./components/admin/DemPipelinePanel'));

// Import admin layout directly (not lazy) to prevent flicker
import { AdminLayoutContent } from './components/admin/AdminLayout';

// Suspense fallback for lazy loaded components.
// 100dvh, not 50vh: with a half-viewport fallback the (static, full-height)
// footer painted INSIDE the first viewport and was shoved off-screen when the
// lazy route chunk arrived — a 0.41 CLS hit on every route. A full-viewport
// reserve keeps the footer below the fold on first paint, so its later move
// never counts as layout shift.
const PageLoader = () => (
  <Center mih="100dvh">
    <Loader size="lg" />
  </Center>
);

// Lighter loader for admin content (doesn't block the layout)
const AdminContentLoader = () => (
  <Center mih="300px">
    <Loader size="md" />
  </Center>
);

// Helper to wait for auth initialization with timeout
async function waitForAuth(timeoutMs = 10_000) {
  const state = useAuthStore.getState();
  if (state.initialized) return;

  await Promise.race([
    new Promise<void>((resolve) => {
      const unsubscribe = useAuthStore.subscribe((s) => {
        if (s.initialized) {
          unsubscribe();
          resolve();
        }
      });
    }),
    new Promise<void>((_, reject) =>
      setTimeout(() => reject(new Error('Auth initialization timeout')), timeoutMs)
    ),
  ]);
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

const privacyPolicyRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/privacidad',
  component: () => (
    <RootLayout
      title="Política de privacidad"
      description="Política de protección de datos personales del Consorcio Canalero 10 de Mayo (Ley 25.326)."
    >
      <Suspense fallback={<PageLoader />}>
        <PrivacyPolicyPage />
      </Suspense>
    </RootLayout>
  ),
});

const forgotPasswordRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/forgot-password',
  component: () => (
    <RootLayout
      title="Recuperar Contrasena"
      description="Recupera el acceso a tu cuenta del Consorcio Canalero 10 de Mayo."
      noindex={true}
    >
      <Suspense fallback={<PageLoader />}>
        <ForgotPasswordForm />
      </Suspense>
    </RootLayout>
  ),
});

const resetPasswordRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/reset-password',
  // F5-E: accept BOTH ``?token=`` (legacy path: email URL embeds the
  // long JWT directly) and ``?code=`` (new path: email URL carries
  // the short SMTP-safe code, SPA exchanges via /auth/exchange-code).
  // The component handles the exchange transparently so the user
  // sees the same UX in both modes.
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search.token as string) || '',
    code: (search.code as string) || '',
  }),
  component: () => {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const { token, code } = resetPasswordRoute.useSearch();
    return (
      <RootLayout
        title="Nueva Contrasena"
        description="Restablece tu contrasena del Consorcio Canalero 10 de Mayo."
        noindex={true}
      >
        <Suspense fallback={<PageLoader />}>
          <ResetPasswordForm token={token} code={code} />
        </Suspense>
      </RootLayout>
    );
  },
});

const verifyEmailRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/verify-email',
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search.token as string) || '',
    code: (search.code as string) || '',
  }),
  component: () => {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const { token, code } = verifyEmailRoute.useSearch();
    return (
      <RootLayout
        title="Verificar Correo"
        description="Verifica tu correo para activar tu cuenta del Consorcio Canalero 10 de Mayo."
        noindex={true}
      >
        <Suspense fallback={<PageLoader />}>
          <VerifyEmailPage token={token} code={code} />
        </Suspense>
      </RootLayout>
    );
  },
});

const mapaRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/mapa',
  validateSearch: (search: Record<string, unknown>) => {
    const riskClasses = Array.isArray(search.riskClasses)
      ? search.riskClasses.flatMap((value) => (typeof value === 'string' ? value.split(',') : []))
      : typeof search.riskClasses === 'string'
        ? search.riskClasses.split(',')
        : [];
    return {
      ...(search.hazard === '1' || search.hazard === true ? { hazard: '1' } : {}),
      ...(typeof search.basin === 'string' && search.basin.trim() ? { basin: search.basin.trim() } : {}),
      ...(riskClasses.length > 0 ? { riskClasses } : {}),
      ...(typeof search.precipMonth === 'string' ? { precipMonth: search.precipMonth } : {}),
    };
  },
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

// Vista publica unificada: reportar un problema y proponer una mejora
// conviven en tabs bajo un solo header (`ParticipacionPage`), en vez de dos
// paginas con dos entradas en el navbar.
const participacionRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/participacion',
  // `?tab=` permite deep-linkear una pestana concreta; lo usa el redirect
  // de `/sugerencias` para que el marcador viejo aterrice en SU tab.
  validateSearch: (search: Record<string, unknown>): { tab?: 'sugerencias' } =>
    search.tab === 'sugerencias' ? { tab: 'sugerencias' } : {},
  component: () => (
    <RootLayout
      title="Participacion"
      description="Reporta incidentes en los canales o propone mejoras al Consorcio Canalero 10 de Mayo."
    >
      <Suspense fallback={<PageLoader />}>
        <ParticipacionPage />
      </Suspense>
    </RootLayout>
  ),
});

// `/reportes` y `/sugerencias` sobreviven como redirects: son URLs que los
// vecinos tienen en marcadores, en carteleria y circulando por WhatsApp. Se
// resuelven antes de montar nada, sin flash de UI.
const reportesRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/reportes',
  beforeLoad: () => {
    throw redirect({ to: '/participacion' });
  },
  component: () => null,
});

const sugerenciasRoute = createRoute({
  getParentRoute: () => rootRouteWithComponent,
  path: '/sugerencias',
  beforeLoad: () => {
    // Con `tab=sugerencias`: preservar la URL sin preservar el DESTINO
    // dejaria al vecino en la pestana de reportes que no pidio.
    throw redirect({ to: '/participacion', search: { tab: 'sugerencias' } });
  },
  component: () => null,
});

// ============================================
// AUTH CALLBACK ROUTE (OAuth redirect handler)
// ============================================

function redactAuthCallbackUrl(rawUrl: string): string {
  try {
    const url = new URL(rawUrl);

    for (const params of [url.searchParams, new URLSearchParams(url.hash.replace(/^#/, ''))]) {
      for (const key of ['token', 'access_token']) {
        if (params.has(key)) {
          params.set(key, 'present');
        }
      }

      if (params !== url.searchParams) {
        const redactedHash = params.toString();
        url.hash = redactedHash ? `#${redactedHash}` : '';
      }
    }

    return url.toString();
  } catch {
    return 'URL de callback invalida';
  }
}

function clearAuthCallbackUrl() {
  window.history.replaceState(null, document.title, withBasePath('/auth/callback'));
}

function AuthCallbackPage() {
  const [error, setError] = useState<string | null>(null);
  const [debugInfo, setDebugInfo] = useState<string>('Procesando...');

  useEffect(() => {
    const handleCallback = async () => {
      logger.debug('[AUTH CALLBACK] Starting callback handler');
      const redactedCallbackUrl = redactAuthCallbackUrl(window.location.href);
      logger.debug('[AUTH CALLBACK] Current URL:', redactedCallbackUrl);
      setDebugInfo(`URL: ${redactedCallbackUrl}`);

      try {
        // Get params from URL (backend Google OAuth callback)
        const urlParams = new URLSearchParams(window.location.search);
        const errorParam = urlParams.get('error');
        const errorDescription = urlParams.get('error_description');

        // Preferred path (post Phase 2 / F2-L): the backend sets the
        // JWT in a single-use HttpOnly cookie and redirects with
        // ``?via=cookie`` (no token in URL). The SPA exchanges the
        // cookie for the actual token via a JSON endpoint.
        const apiBase =
          import.meta.env.VITE_API_URL ||
          import.meta.env.PUBLIC_API_URL ||
          'http://localhost:8000';
        let token: string | null = null;
        if (urlParams.get('via') === 'cookie') {
          logger.debug('[AUTH CALLBACK] Exchanging OAuth cookie for token');
          try {
            const exchange = await fetch(`${apiBase}/api/v2/auth/jwt/exchange-cookie`, {
              method: 'POST',
              credentials: 'include',
            });
            if (exchange.ok) {
              const body = await exchange.json();
              token = body?.access_token ?? null;
            } else {
              logger.error('[AUTH CALLBACK] Cookie exchange failed:', exchange.status);
            }
          } catch (e) {
            logger.error('[AUTH CALLBACK] Cookie exchange threw:', e);
          }
        }

        // Session-fixation hardening: the legacy fragment/query token
        // fallback (?token= / #access_token=) was REMOVED. The only
        // accepted path is ``?via=cookie`` + exchange-cookie above —
        // a token planted in the URL by an attacker is never persisted.

        logger.debug('[AUTH CALLBACK] URL params:', {
          token: token ? 'present' : 'missing',
          errorParam,
          errorDescription,
        });

        if (errorParam) {
          const errorMsg = `OAuth Error: ${errorParam} - ${errorDescription || 'Sin descripcion'}`;
          logger.error('[AUTH CALLBACK]', errorMsg);
          setError(errorMsg);
          setDebugInfo(
            `Error de Google OAuth: ${errorParam}\nDescripcion: ${errorDescription || 'N/A'}\n\nRevisa la configuracion de OAuth en el backend.`
          );
          return; // No redirigir, mostrar error
        }

        if (token) {
          // Store the token and fetch user profile from /users/me
          logger.debug('[AUTH CALLBACK] Got token, fetching user profile...');
          clearAuthCallbackUrl();

          const profileRes = await fetch(`${apiBase}/api/v2/users/me`, {
            headers: { Authorization: `Bearer ${token}` },
          });

          if (profileRes.ok) {
            const userData = await profileRes.json();
            const user = {
              id: userData.id,
              email: userData.email,
              nombre: userData.nombre || '',
              apellido: userData.apellido || '',
              telefono: userData.telefono || '',
              role: userData.role || 'ciudadano',
            };
            // Cookie exchange + profile success completes an explicit OAuth login.
            clearLocalLogoutTombstone();
            persistAuthSession({ access_token: token, user });
            logger.debug('[AUTH CALLBACK] Profile saved:', { role: user.role });

            // Re-initialize auth store
            const store = useAuthStore.getState();
            store.reset();
            await store.initialize();

            if (user.role === 'admin' || user.role === 'operador') {
              window.location.href = withBasePath('/admin');
            } else {
              window.location.href = withBasePath('/');
            }
            return;
          }
          logger.error('[AUTH CALLBACK] Failed to fetch profile:', profileRes.status);
          setError(`Error al obtener perfil: ${profileRes.status}`);
          return;
        }

        // Fallback: check existing session
        logger.debug('[AUTH CALLBACK] No token from cookie exchange, checking existing session...');
        const existingSession = await authAdapter.getSession();

        if (existingSession) {
          logger.debug('[AUTH CALLBACK] Found existing session');
          window.location.href = withBasePath('/');
        } else {
          logger.debug('[AUTH CALLBACK] No session found, redirecting to login');
          window.location.href = withBasePath('/login');
        }
      } catch (err) {
        logger.error('[AUTH CALLBACK] Exception:', err);
        window.location.href = withBasePath('/login?error=auth_failed');
      }
    };

    handleCallback();
  }, []);

  if (error) {
    return (
      <Center mih="100vh">
        <Stack align="center" gap="md" style={{ maxWidth: 600, padding: 20 }}>
          <Text size="xl" fw={700} c="red">
            Error de Autenticacion
          </Text>
          <Text c="dimmed" style={{ whiteSpace: 'pre-wrap', textAlign: 'center' }}>
            {debugInfo}
          </Text>
          <Text size="sm" c="blue" component="a" href={withBasePath('/login')}>
            Volver al login
          </Text>
        </Stack>
      </Center>
    );
  }

  return (
    <Center mih="100vh">
      <Stack align="center" gap="md">
        <Loader size="lg" />
        <Text c="dimmed">Autenticando...</Text>
        <Text size="xs" c="gray">
          {debugInfo}
        </Text>
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
    <RootLayout title="Mi Perfil" description="Gestiona tu perfil de usuario.">
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

// Vista unificada: denuncias y sugerencias conviven en tabs bajo un solo
// header (`ParticipacionPanel`).
const adminParticipacionRoute = createRoute({
  getParentRoute: () => adminLayoutRoute,
  path: '/participacion',
  // `?tab=` permite deep-linkear una pestana concreta; lo usa el redirect
  // de `/admin/sugerencias` para que el marcador viejo aterrice en SU tab.
  validateSearch: (search: Record<string, unknown>): { tab?: 'sugerencias' } =>
    search.tab === 'sugerencias' ? { tab: 'sugerencias' } : {},
  component: () => <ParticipacionPanel />,
});

// `/admin/reports` y `/admin/sugerencias` sobreviven como redirects: son
// URLs que los operadores tienen guardadas en marcadores y circulando en
// mails internos. Se resuelven antes de montar nada, sin flash de UI.
const adminReportsRoute = createRoute({
  getParentRoute: () => adminLayoutRoute,
  path: '/reports',
  beforeLoad: () => {
    throw redirect({ to: '/admin/participacion' });
  },
  component: () => null,
});

const adminSugerenciasRoute = createRoute({
  getParentRoute: () => adminLayoutRoute,
  path: '/sugerencias',
  beforeLoad: () => {
    // Con `tab=sugerencias`: preservar la URL sin preservar el DESTINO
    // dejaria al operador en la pestana Reportes que no pidio.
    throw redirect({ to: '/admin/participacion', search: { tab: 'sugerencias' } });
  },
  component: () => null,
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

const adminDemPipelineRoute = createRoute({
  getParentRoute: () => adminLayoutRoute,
  path: '/dem-pipeline',
  component: () => <DemPipelinePanel />,
});

// ============================================
// ROUTE TREE
// ============================================

// Build admin route tree with nested children
const adminRouteTree = adminLayoutRoute.addChildren([
  adminIndexRoute,
  adminImagesRoute,
  adminDemPipelineRoute,
  adminParticipacionRoute,
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
  privacyPolicyRoute,
  forgotPasswordRoute,
  resetPasswordRoute,
  verifyEmailRoute,
  mapaRoute,
  participacionRoute,
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
