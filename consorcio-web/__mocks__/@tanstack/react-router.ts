/**
 * Manual mock for `@tanstack/react-router` (Vitest `__mocks__`, auto-applied
 * when a test file calls `vi.mock('@tanstack/react-router')` WITHOUT a factory).
 *
 * WHY: the router hooks require a live `RouterProvider` context. Unit tests
 * render map components in isolation, so any component (or hook) that calls
 * `useSearch` / `useNavigate` unconditionally crashes with
 * `Cannot read properties of null (reading 'stores')`. `useHazardUrlState`
 * (`src/hooks/useHazardUrlState.ts`) is exactly that shape: it calls
 * `useNavigate()` and `useSearch({ from: '/mapa' })` on every render, with no
 * escape hatch. As the hazard viewer gets wired into `MapaMapLibre` /
 * `MapaContent`, every suite that mounts those components inherits the
 * requirement.
 *
 * This mock supplies a deterministic default search (`{}`) and a spyable
 * `useNavigate`, which is the whole contract those consumers need in order to
 * render. The genuine URL parsing / validation / setter routing is a pure
 * function (`parseHazardUrlState` / `toHazardSearch`) and is covered
 * independently, so stubbing the transport here does NOT erase behavior the
 * component suites assert on (layout, media queries, login gates, link hrefs).
 *
 * Every other export is re-exported from the real module, so `Link`,
 * `RouterProvider`, `createRouter`, `createRootRoute`, … keep working for the
 * suites that only need the router to exist.
 *
 * NOTE — suites that already declare an INLINE `vi.mock('@tanstack/react-router', factory)`
 * (Header, Footer, NotFound, AdminLayout, ProtectedRoute) are untouched: a
 * factory always wins over the `__mocks__` file.
 */

import { vi } from 'vitest';

/**
 * One shared spy across the module, so a test can assert navigation without
 * having to reach through `getRouteApi`. `vi.clearAllMocks()` in a suite's
 * `beforeEach` resets it like any other spy.
 */
const navigate = vi.fn();

/**
 * The hooks main actually calls today (`useHazardUrlState`, `ProtectedRoute`).
 * `useSearch` ignores its `{ from }` argument on purpose: the harness models a
 * route with no search params, which is the default every consumer must handle.
 */
export const useNavigate = () => navigate;
export const useSearch = () => ({});
export const useParams = () => ({});
export const useMatch = () => ({ search: {} });
export const useRouter = () => ({ state: { status: 'idle' }, navigate });

/**
 * Kept even though nothing in `src/` uses it yet: the real `getRouteApi` would
 * otherwise leak through the `export *` below and blow up with the same null
 * context this file exists to prevent. Mirrors the hooks above.
 */
export const getRouteApi = () => ({
  useSearch: () => ({}),
  useNavigate: () => navigate,
  useParams: () => ({}),
  useLoaderData: () => undefined,
  useMatch: () => ({ search: {} }),
});

// Preserve every other export from the real module. Named exports declared
// above take precedence over the star re-export.
export * from '@tanstack/react-router';
