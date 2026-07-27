/**
 * MapWorkspace.test.tsx
 *
 * The responsive controls shell (change `rediseno-ux-mapa`, task 1.2).
 * - Desktop (viewport >= 48em): renders a collapsible sidebar + the canvas,
 *   both fed by the SAME `controls`/`canvas` nodes.
 * - Mobile (viewport < 48em): renders the canvas full-width + a ☰ burger that
 *   opens a full-screen Drawer; the Drawer (and its controls) is closed until
 *   the burger is pressed.
 *
 * SINGLE-TREE INVARIANT (FIX 1): `{canvas}` is ALWAYS child index 0 in the SAME
 * wrapper across both modes, so crossing the 48em breakpoint at runtime never
 * remounts the canvas fiber (MapLibre keeps its WebGL context).
 */

import { MantineProvider } from '@mantine/core';
import { act, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MapWorkspace } from '../../src/components/map2d/MapWorkspace';
import { useMapWorkspaceStore } from '../../src/stores/mapWorkspaceStore';

function mockViewport(isDesktop: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      // '(min-width: 48em)' matches on desktop only.
      matches: isDesktop,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

/**
 * A controllable `matchMedia` mock: captures the `change` listeners that
 * `useMediaQuery` attaches, so a test can flip the viewport at RUNTIME
 * (desktop ⇄ mobile) and drive the hook the way a real resize would.
 */
function installControllableViewport(initialDesktop: boolean) {
  const state = { desktop: initialDesktop };
  const listeners = new Set<(e: { matches: boolean }) => void>();

  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      get matches() {
        return state.desktop;
      },
      media: query,
      onchange: null,
      addListener: (cb: (e: { matches: boolean }) => void) => listeners.add(cb),
      removeListener: (cb: (e: { matches: boolean }) => void) => listeners.delete(cb),
      addEventListener: (_type: string, cb: (e: { matches: boolean }) => void) =>
        listeners.add(cb),
      removeEventListener: (_type: string, cb: (e: { matches: boolean }) => void) =>
        listeners.delete(cb),
      dispatchEvent: vi.fn(),
    })),
  });

  return {
    /** Flip the viewport and notify every attached `useMediaQuery` listener. */
    set(desktop: boolean) {
      state.desktop = desktop;
      act(() => {
        listeners.forEach((cb) => cb({ matches: desktop }));
      });
    },
  };
}

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const canvas = <div data-testid="canvas-marker">CANVAS</div>;
const controls = <div data-testid="controls-marker">CONTROLS</div>;

beforeEach(() => {
  // Reset persisted collapse preference to a known baseline.
  useMapWorkspaceStore.setState({ sidebarCollapsed: false });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('<MapWorkspace />', () => {
  it('desktop: renders sidebar + canvas with the same controls', () => {
    mockViewport(true);
    renderWithMantine(
      <MapWorkspace canvas={canvas} controls={controls} activeLayerCount={3} />,
    );

    expect(screen.getByTestId('map-workspace-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('map-workspace-canvas')).toBeInTheDocument();
    expect(screen.getByTestId('canvas-marker')).toBeInTheDocument();
    expect(screen.getByTestId('controls-marker')).toBeInTheDocument();
    // No mobile burger on desktop.
    expect(screen.queryByTestId('map-workspace-burger')).not.toBeInTheDocument();
  });

  it('desktop: collapse button toggles the persisted sidebar state', () => {
    mockViewport(true);
    renderWithMantine(
      <MapWorkspace canvas={canvas} controls={controls} activeLayerCount={0} />,
    );

    expect(useMapWorkspaceStore.getState().sidebarCollapsed).toBe(false);
    fireEvent.click(screen.getByTestId('map-workspace-collapse'));
    expect(useMapWorkspaceStore.getState().sidebarCollapsed).toBe(true);
  });

  it('mobile: renders canvas + burger, Drawer (controls) closed until opened', () => {
    mockViewport(false);
    renderWithMantine(
      <MapWorkspace canvas={canvas} controls={controls} activeLayerCount={2} />,
    );

    expect(screen.getByTestId('map-workspace-canvas')).toBeInTheDocument();
    expect(screen.getByTestId('canvas-marker')).toBeInTheDocument();
    expect(screen.getByTestId('map-workspace-burger')).toBeInTheDocument();
    // No desktop sidebar on mobile.
    expect(screen.queryByTestId('map-workspace-sidebar')).not.toBeInTheDocument();
    // Drawer closed → controls not mounted yet.
    expect(screen.queryByTestId('controls-marker')).not.toBeInTheDocument();
  });

  it('mobile: pressing the burger opens the Drawer with the controls', async () => {
    mockViewport(false);
    renderWithMantine(
      <MapWorkspace canvas={canvas} controls={controls} activeLayerCount={2} />,
    );

    fireEvent.click(screen.getByTestId('map-workspace-burger'));
    // Drawer content mounts through Mantine's open transition.
    expect(await screen.findByTestId('controls-marker')).toBeInTheDocument();
  });

  it('FIX 1: the canvas node is NEVER remounted across the 48em breakpoint', () => {
    const viewport = installControllableViewport(true); // start desktop
    renderWithMantine(
      <MapWorkspace canvas={canvas} controls={controls} activeLayerCount={1} />,
    );

    // Capture the exact DOM node backing the canvas subtree.
    const canvasNode = screen.getByTestId('canvas-marker');
    expect(screen.getByTestId('map-workspace-sidebar')).toBeInTheDocument();

    // Desktop → mobile: the sidebar is replaced by the burger, but the canvas
    // (child index 0) must be the SAME node — not recreated.
    viewport.set(false);
    expect(screen.getByTestId('map-workspace-burger')).toBeInTheDocument();
    expect(screen.queryByTestId('map-workspace-sidebar')).not.toBeInTheDocument();
    expect(screen.getByTestId('canvas-marker')).toBe(canvasNode);

    // Mobile → desktop: same guarantee on the way back.
    viewport.set(true);
    expect(screen.getByTestId('map-workspace-sidebar')).toBeInTheDocument();
    expect(screen.queryByTestId('map-workspace-burger')).not.toBeInTheDocument();
    expect(screen.getByTestId('canvas-marker')).toBe(canvasNode);
  });

  it('FIX 2: collapsing the sidebar keeps controls MOUNTED (local state survives)', () => {
    mockViewport(true);
    renderWithMantine(
      <MapWorkspace canvas={canvas} controls={controls} activeLayerCount={4} />,
    );

    // Same node identity before and after collapse → not conditionally unmounted.
    const controlsNode = screen.getByTestId('controls-marker');
    act(() => {
      useMapWorkspaceStore.setState({ sidebarCollapsed: true });
    });
    expect(useMapWorkspaceStore.getState().sidebarCollapsed).toBe(true);
    expect(screen.getByTestId('controls-marker')).toBe(controlsNode);
  });

  it('FIX 3: an open mobile Drawer does not survive a desktop round-trip', async () => {
    const viewport = installControllableViewport(false); // start mobile
    renderWithMantine(
      <MapWorkspace canvas={canvas} controls={controls} activeLayerCount={2} />,
    );

    // Open the Drawer on mobile.
    fireEvent.click(screen.getByTestId('map-workspace-burger'));
    expect(await screen.findByTestId('controls-marker')).toBeInTheDocument();

    // Cross into desktop (the effect closes the Drawer) …
    viewport.set(true);
    expect(screen.getByTestId('map-workspace-sidebar')).toBeInTheDocument();

    // … then back to mobile: the Drawer must be CLOSED (its controls unmounted),
    // never re-surfaced on its own.
    viewport.set(false);
    expect(screen.getByTestId('map-workspace-burger')).toBeInTheDocument();
    expect(screen.queryByTestId('controls-marker')).not.toBeInTheDocument();
  });
});
