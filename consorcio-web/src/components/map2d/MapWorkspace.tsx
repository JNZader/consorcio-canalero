import { ActionIcon, Badge, Box, Burger, Drawer, Group, Text, Tooltip } from '@mantine/core';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
import { useEffect } from 'react';
import type { ReactNode } from 'react';

import { useDrawerHistoryClose } from '../../hooks/useDrawerHistoryClose';
import { useMapWorkspaceStore } from '../../stores/mapWorkspaceStore';
import styles from '../../styles/components/map.module.css';
import { IconArrowLeft, IconArrowRight, IconLayers } from '../ui/icons';

/**
 * Width of the mobile layers Drawer. Deliberately NOT 100%: see the Drawer
 * comment below (map-fluidity T2, fix 5). Exported so the test asserts the
 * contract instead of a magic string.
 */
export const MOBILE_DRAWER_SIZE = '75%';

interface MapWorkspaceProps {
  /** The map canvas node (MapLibre container + its floating overlays). */
  canvas: ReactNode;
  /** The controls tree (layer toggles + legend). ONE tree feeds both modes. */
  controls: ReactNode;
  /** "N capas activas" indicator. Optional — omitted hides the badge. */
  activeLayerCount?: number;
}

/**
 * Responsive controls shell for the 2D map (change `rediseno-ux-mapa`).
 *
 * A SINGLE `controls` tree is placed either in a collapsible left sidebar
 * (desktop) or in a full-screen `Drawer` opened by a ☰ burger (mobile). The
 * breakpoint is derived with `useMediaQuery` — NOT with patched desktop styles
 * — mirroring `Header.tsx`. The desktop collapse state is persisted
 * (`mapWorkspaceStore`) so the preference survives reloads.
 *
 * CRITICAL — single-tree render: `{canvas}` is ALWAYS child index 0 inside the
 * SAME wrapper (`styles.workspaceCanvas`), regardless of `isDesktop` or
 * collapse. Crossing 48em at runtime (window resize, tablet rotation) only
 * remounts the sibling at index 1 (sidebar ↔ burger/Drawer); the canvas fiber
 * is preserved, so MapLibre keeps its WebGL context (no permanent grey area —
 * the init effect never re-runs because `containerRef` is stable). Desktop
 * layout uses CSS grid `order` so the sidebar paints to the LEFT even though it
 * comes AFTER the canvas in the DOM.
 *
 * React Compiler is active → no manual `useMemo`/`useCallback`.
 */
export function MapWorkspace({ canvas, controls, activeLayerCount }: MapWorkspaceProps) {
  // `getInitialValueInEffect: false` → on first render Mantine calls
  // `getInitialValue(query)`, which IGNORES the `initialValue` arg entirely:
  // in a browser SPA it reads `window.matchMedia(query).matches` synchronously
  // (correct, no flash), and ONLY when `matchMedia` is unavailable (SSR / no
  // window) does it fall back to `false` → MOBILE-first. The `true` below is
  // therefore never consumed at runtime; it stays only to document intent.
  // El alto es tan load-bearing como el ancho (B2-2.1). Con `min-width` sola, un
  // telefono acostado (844×390) supera los 48em y entraba en modo escritorio: un
  // sidebar fijo de 300-360px sobre un canvas de ~306px de alto, y el reflow
  // apaisado terminaba flotando la top bar ENCIMA de la cabecera del sidebar
  // (con el panel colapsado, el boton de expandir quedaba tapado del todo y el
  // panel era irrecuperable). 30.0625em = 481px deja del lado escritorio a las
  // tablets y a cualquier laptop (768px de alto y para arriba), y manda al
  // telefono acostado al burger + Drawer, que es la forma correcta ahi.
  const isDesktop = useMediaQuery('(min-width: 48em) and (min-height: 30.0625em)', true, {
    getInitialValueInEffect: false,
  });
  const sidebarCollapsed = useMapWorkspaceStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useMapWorkspaceStore((state) => state.toggleSidebar);
  const [drawerOpened, drawer] = useDisclosure(false);

  // FIX 3: when the viewport crosses into desktop, drop any open mobile Drawer
  // so returning to mobile doesn't surface a Drawer that was never re-opened.
  useEffect(() => {
    if (isDesktop) {
      drawer.close();
    }
  }, [isDesktop, drawer]);

  // AUD-005: on mobile, Back is "dismiss". Without this, Back with the layers
  // Drawer open navigated away from the map — the user lost the page to close
  // a panel. Disabled on desktop, where there IS no Drawer to dismiss and the
  // history stack must stay untouched.
  useDrawerHistoryClose({
    opened: drawerOpened,
    onClose: drawer.close,
    enabled: !isDesktop,
  });

  const countBadge =
    activeLayerCount !== undefined ? (
      <Badge size="sm" variant="light" color="blue">
        {activeLayerCount} activas
      </Badge>
    ) : null;

  return (
    <Box
      className={styles.workspaceRoot}
      data-desktop={isDesktop ? 'true' : 'false'}
      data-collapsed={isDesktop && sidebarCollapsed ? 'true' : 'false'}
      data-testid="map-workspace-root"
    >
      {/* Canvas — ALWAYS child index 0, SAME wrapper in every mode. Never
          remounts across the 48em breakpoint → MapLibre keeps its WebGL ctx. */}
      <Box className={styles.workspaceCanvas} data-testid="map-workspace-canvas">
        {canvas}
      </Box>

      {isDesktop ? (
        <Box
          className={styles.workspaceSidebar}
          data-collapsed={sidebarCollapsed ? 'true' : 'false'}
          data-testid="map-workspace-sidebar"
          aria-label="Panel de capas y leyenda"
        >
          <Box
            className={`${styles.workspaceSidebarHeader} ${
              sidebarCollapsed ? styles.workspaceSidebarHeaderCollapsed : ''
            }`}
          >
            {!sidebarCollapsed && (
              <Group gap="xs" wrap="nowrap">
                <IconLayers size={18} />
                <Text fw={600} size="sm">
                  Capas
                </Text>
                {countBadge}
              </Group>
            )}
            <Tooltip
              label={sidebarCollapsed ? 'Expandir panel' : 'Colapsar panel'}
              position="right"
              withArrow
            >
              <ActionIcon
                variant="subtle"
                color="gray"
                onClick={toggleSidebar}
                aria-label={
                  sidebarCollapsed ? 'Expandir panel de capas' : 'Colapsar panel de capas'
                }
                aria-expanded={!sidebarCollapsed}
                data-testid="map-workspace-collapse"
              >
                {sidebarCollapsed ? <IconArrowRight size={18} /> : <IconArrowLeft size={18} />}
              </ActionIcon>
            </Tooltip>
          </Box>
          {/* FIX 2: controls stay MOUNTED across collapse — the body is hidden
              via CSS (data-collapsed), never conditionally rendered, so
              LeyendaPanel/LayerControlsPanel keep their local useState. */}
          <Box className={styles.workspaceSidebarBody}>{controls}</Box>
        </Box>
      ) : (
        <>
          <Tooltip label="Capas y leyenda" position="right" withArrow>
            <Burger
              opened={drawerOpened}
              onClick={drawer.open}
              className={styles.workspaceBurger}
              aria-label={
                drawerOpened ? 'Cerrar panel de capas y leyenda' : 'Abrir panel de capas y leyenda'
              }
              data-testid="map-workspace-burger"
              size="sm"
            />
          </Tooltip>
          <Drawer
            opened={drawerOpened}
            onClose={drawer.close}
            /* Partial, not full-screen (map-fluidity T2, fix 5). At 100% the
               user could not see the effect of a layer toggle without closing
               the Drawer first — open → toggle → close → look → repeat. 75%
               keeps a slice of the map on screen while toggling. */
            size={MOBILE_DRAWER_SIZE}
            padding="md"
            zIndex={1200}
            trapFocus
            returnFocus
            title={
              <Group gap="xs">
                <IconLayers size={18} />
                <Text fw={600}>Capas y leyenda</Text>
                {countBadge}
              </Group>
            }
          >
            {controls}
          </Drawer>
        </>
      )}
    </Box>
  );
}
