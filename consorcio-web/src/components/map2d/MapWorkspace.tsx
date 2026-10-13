import { ActionIcon, Badge, Box, Burger, Group, Text, Tooltip } from '@mantine/core';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
import { useEffect } from 'react';
import type { CSSProperties, ReactNode } from 'react';

import { useDrawerHistoryClose } from '../../hooks/useDrawerHistoryClose';
import { useMapWorkspaceStore } from '../../stores/mapWorkspaceStore';
import styles from '../../styles/components/map.module.css';
import { IconArrowLeft, IconArrowRight, IconLayers, IconX } from '../ui/icons';

/**
 * Width of the mobile layers overlay. Deliberately NOT 100%: see the overlay
 * comment below (map-fluidity T2, fix 5). Exported so the test asserts the
 * contract instead of a magic string.
 */
export const MOBILE_DRAWER_SIZE = '75%';

/**
 * The ONE desktop breakpoint of the 2D map shell.
 *
 * `MapWorkspace` decides sidebar-vs-overlay with it, and `MapaMapLibre` decides
 * whether to render its floating top bar with it. Those two decisions MUST agree
 * — a mobile viewport that still painted the top bar would show the base-layer
 * control twice (once floating, once inside the overlay). Exported as a single
 * constant so neither side can drift.
 *
 * El alto es tan load-bearing como el ancho (B2-2.1). Con `min-width` sola, un
 * telefono acostado (844×390) supera los 48em y entraba en modo escritorio: un
 * sidebar fijo de 300-360px sobre un canvas de ~306px de alto, y el reflow
 * apaisado terminaba flotando la top bar ENCIMA de la cabecera del sidebar (con
 * el panel colapsado, el boton de expandir quedaba tapado del todo y el panel
 * era irrecuperable). 40em = 640px (UX-15) manda notebooks bajas al overlay
 * para no aplastar el mapa; el telefono acostado sigue en burger + overlay.
 *
 * ── OJO: el contrato es UNIDIRECCIONAL ─────────────────────────────────────
 * `map.module.css` hardcodea el COMPLEMENTO EXACTO de este `min-width` en el
 * bloque de portrait: `@media … and (max-width: 47.9375em)`, o sea 48em menos
 * 0.0625em (1px), para que las dos queries nunca sean verdaderas a la vez. El
 * CSS no puede importar esta constante, asi que cambiar el 48em de aca sin
 * cambiar el 47.9375em de alla reabre el solape en 768px exacto: un viewport
 * que SI pinta la top bar recibiendo el presupuesto de alto que asume que no
 * hay ninguna. `tests/unit/mapSkeletonGeometry.test.ts` deriva el complemento
 * DESDE esta constante y lo compara contra el CSS justamente para que ese
 * cambio rompa el test en vez de quedar verde.
 */
export const MAP_DESKTOP_MEDIA_QUERY = '(min-width: 48em) and (min-height: 40em)';

/**
 * `true` when the 2D map shell is in desktop mode.
 *
 * Wraps the `useMediaQuery` call VERBATIM (same query, same options) so every
 * consumer resolves the breakpoint identically.
 *
 * `getInitialValueInEffect: false` → on first render Mantine calls
 * `getInitialValue(query)`, which IGNORES the `initialValue` arg entirely: in a
 * browser SPA it reads `window.matchMedia(query).matches` synchronously
 * (correct, no flash), and ONLY when `matchMedia` is unavailable (SSR / no
 * window) does it fall back to `false` → MOBILE-first. The `true` below is
 * therefore never consumed at runtime; it stays only to document intent.
 */
export function useMapWorkspaceDesktop(): boolean {
  return useMediaQuery(MAP_DESKTOP_MEDIA_QUERY, true, {
    getInitialValueInEffect: false,
  });
}

interface MapWorkspaceProps {
  /** The map canvas node (MapLibre container + its floating overlays). */
  canvas: ReactNode;
  /** The controls tree (layer toggles + legend). ONE tree feeds both modes. */
  controls: ReactNode;
  /** "N capas activas" indicator. Optional — omitted hides the badge. */
  activeLayerCount?: number;
  /** UX-06: polite status for layer load failures. */
  liveMessage?: string;
}

/**
 * Responsive controls shell for the 2D map (change `rediseno-ux-mapa`).
 *
 * A SINGLE `controls` tree lives in one sidebar host. Desktop shows it as a
 * collapsible left column; mobile CSS-hides that same host until the ☰ burger
 * opens it as a 75% overlay (MAP-11). Crossing 48em never remounts `{controls}`
 * — LayerControlsPanel keeps search/accordion local state. `{canvas}` stays
 * child index 0 so MapLibre keeps its WebGL context.
 *
 * React Compiler is active → no manual `useMemo`/`useCallback`.
 */
export function MapWorkspace({ canvas, controls, activeLayerCount, liveMessage }: MapWorkspaceProps) {
  const isDesktop = useMapWorkspaceDesktop();
  const sidebarCollapsed = useMapWorkspaceStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useMapWorkspaceStore((state) => state.toggleSidebar);
  const [drawerOpened, drawer] = useDisclosure(false);
  const overlayOpen = !isDesktop && drawerOpened;
  const headerCollapsed = isDesktop && sidebarCollapsed;

  useEffect(() => {
    if (isDesktop) {
      drawer.close();
    }
  }, [isDesktop, drawer]);

  useEffect(() => {
    if (!overlayOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') drawer.close();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [overlayOpen, drawer]);

  useDrawerHistoryClose({
    opened: overlayOpen,
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
      data-collapsed={headerCollapsed ? 'true' : 'false'}
      data-drawer-open={overlayOpen ? 'true' : 'false'}
      data-testid="map-workspace-root"
      style={{ '--map-mobile-drawer-size': MOBILE_DRAWER_SIZE } as CSSProperties}
    >
      <Box className={styles.workspaceCanvas} data-testid="map-workspace-canvas">
        {canvas}
      </Box>
      <div className={styles.visuallyHidden} role="status" aria-live="polite" data-testid="map-live-region">
        {liveMessage ?? ''}
      </div>

      {!isDesktop && (
        <>
          <Tooltip label="Capas y leyenda" position="right" withArrow>
            <Burger
              opened={drawerOpened}
              onClick={drawer.toggle}
              className={styles.workspaceBurger}
              aria-label={
                drawerOpened ? 'Cerrar panel de capas y leyenda' : 'Abrir panel de capas y leyenda'
              }
              data-testid="map-workspace-burger"
              size="sm"
            />
          </Tooltip>
          {overlayOpen && (
            <Box
              className={styles.workspaceDrawerOverlay}
              onClick={drawer.close}
              data-testid="map-workspace-drawer-overlay"
            />
          )}
        </>
      )}

      <Box
        className={styles.workspaceSidebar}
        data-collapsed={headerCollapsed ? 'true' : 'false'}
        data-testid="map-workspace-sidebar"
        aria-label="Panel de capas y leyenda"
        aria-hidden={!isDesktop && !overlayOpen ? true : undefined}
        role={overlayOpen ? 'dialog' : undefined}
        aria-modal={overlayOpen ? true : undefined}
        style={!isDesktop ? { width: MOBILE_DRAWER_SIZE } : undefined}
      >
        <Box
          className={`${styles.workspaceSidebarHeader} ${
            headerCollapsed ? styles.workspaceSidebarHeaderCollapsed : ''
          }`}
        >
          {!headerCollapsed && (
            <Group gap="xs" wrap="nowrap">
              <IconLayers size={18} />
              <Text fw={600} size="sm">
                {isDesktop ? 'Capas' : 'Capas y leyenda'}
              </Text>
              {countBadge}
            </Group>
          )}
          {isDesktop ? (
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
          ) : (
            <ActionIcon
              variant="subtle"
              color="gray"
              onClick={drawer.close}
              aria-label="Cerrar panel de capas y leyenda"
              data-testid="map-workspace-drawer-close"
            >
              <IconX size={18} />
            </ActionIcon>
          )}
        </Box>
        <Box className={styles.workspaceSidebarBody}>{controls}</Box>
      </Box>
    </Box>
  );
}
