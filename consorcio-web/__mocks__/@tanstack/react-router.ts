/**
 * Manual mock for `@tanstack/react-router` (Vitest `__mocks__`, auto-applied
 * when a test file calls `vi.mock('@tanstack/react-router')` without a factory).
 *
 * WHY: The production map components (`MapaMapLibre`, `MapaPage`/`MapaContent`,
 * `useHazardMapState` → `useHazardUrlState`) call `getRouteApi('/mapa').useSearch()`
 * and `useNavigate({ from: '/mapa' })`. Those hooks require a TanStack Router
 * context. In production the whole app is wrapped in a `RouterProvider`, but the
 * unit tests render the components in isolation, so they crashed with
 * `Cannot read properties of null (reading 'stores')` after the Rules-of-Hooks
 * repair made the router hooks unconditional.
 *
 * This mock returns a deterministic default search (`{}`) and a spyable
 * `useNavigate` — exactly the contract the components need to render. Every
 * other export is preserved from the real module, so nothing else regresses.
 * The genuine URL parsing / validation / setter routing is covered
 * exhaustively by `tests/unit/useHazardUrlState.test.ts`, so this does NOT erase
 * the behavior the component suites assert on (layout, media queries, login
 * gates, link hrefs).
 */

import { vi } from 'vitest';

const navigate = vi.fn();

export const getRouteApi = () => ({
  useSearch: () => ({}),
  useNavigate: () => navigate,
  useParams: () => ({}),
  useLoaderData: () => undefined,
  useMatch: () => ({ search: {} }),
});

export const useNavigate = () => navigate;
export const useRouter = () => ({ state: { status: 'idle' } });
export const useSearch = () => ({});
export const useParams = () => ({});
export const useMatch = () => ({ search: {} });

// Preserve every other export from the real module (Link, RouterProvider,
// createRootRoute, createRouter, etc.) so unrelated usages keep working.
export * from '@tanstack/react-router';
