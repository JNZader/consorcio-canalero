import {
  ActionIcon,
  Badge,
  Box,
  Burger,
  Group,
  SegmentedControl,
  Text,
  Tooltip,
} from '@mantine/core';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
import type { CSSProperties, ReactNode } from 'react';
import { useEffect, useRef, useState } from 'react';

import { useDrawerHistoryClose } from '../../hooks/useDrawerHistoryClose';
import { mediaMinWidth } from '../../lib/breakpoints';
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
 * El ancho sale de `breakpoints.sm` (`mediaMinWidth('sm')` = 48em).
 * `map.module.css` hardcodea el COMPLEMENTO EXACTO de ese `min-width` en el
 * bloque de portrait: `@media … and (max-width: 47.9375em)`, o sea 48em menos
 * 0.0625em (1px), para que las dos queries nunca sean verdaderas a la vez. El
 * CSS no puede importar esta constante (`@media` no lee custom properties),
 * asi que cambiar el token sin cambiar el 47.9375em de alla reabre el solape
 * en 768px exacto: un viewport
 * que SI pinta la top bar recibiendo el presupuesto de alto que asume que no
 * hay ninguna. `tests/unit/mapSkeletonGeometry.test.ts` deriva el complemento
 * DESDE esta constante y lo compara contra el CSS justamente para que ese
 * cambio rompa el test en vez de quedar verde.
 */
export const MAP_DESKTOP_MEDIA_QUERY = `${mediaMinWidth('sm')} and (min-height: 40em)`;

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
  /**
   * Feature readout. When set, the sidebar offers Capas | Información and
   * shows this node on the Información tab, instead of a card over the map.
   */
  selection?: ReactNode;
  /**
   * Identity of the current selection. A new value opens the sidebar on
   * Información and moves focus there.
   */
  selectionKey?: unknown;
  /** Dismiss the readout and return the sidebar to Capas. */
  onCloseSelection?: () => void;
  /** "N capas activas" indicator. Optional — omitted hides the badge. */
  activeLayerCount?: number;
  /** UX-06: polite status for layer load failures. */
  liveMessage?: string;
  /**
   * Search (and any other control) pinned to the panel header, outside the
   * scrolling body. Hidden while the desktop sidebar is collapsed.
   */
  headerSlot?: ReactNode;
}

type SidebarTab = 'capas' | 'info';

function isFromTextEntry(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
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
export function MapWorkspace({
  canvas,
  controls,
  selection = null,
  selectionKey = null,
  onCloseSelection,
  activeLayerCount,
  liveMessage,
  headerSlot = null,
}: MapWorkspaceProps) {
  const isDesktop = useMapWorkspaceDesktop();
  const sidebarCollapsed = useMapWorkspaceStore((state) => state.sidebarCollapsed);
  const setSidebarCollapsed = useMapWorkspaceStore((state) => state.setSidebarCollapsed);
  const toggleSidebar = useMapWorkspaceStore((state) => state.toggleSidebar);
  const [drawerOpened, drawer] = useDisclosure(false);
  const { open: openDrawer, close: closeDrawer } = drawer;
  const overlayOpen = !isDesktop && drawerOpened;
  const headerCollapsed = isDesktop && sidebarCollapsed;
  const sidebarRef = useRef<HTMLDivElement>(null);
  const hasSelection = selection != null && selectionKey != null;
  const [tab, setTab] = useState<SidebarTab>(hasSelection ? 'info' : 'capas');
  const [seenKey, setSeenKey] = useState<unknown>(selectionKey);
  if (seenKey !== selectionKey) {
    setSeenKey(selectionKey);
    setTab(hasSelection ? 'info' : 'capas');
  }
  const showInfo = hasSelection && tab === 'info';

  useEffect(() => {
    if (isDesktop) {
      closeDrawer();
    }
  }, [isDesktop, closeDrawer]);

  useEffect(() => {
    if (!hasSelection) return;
    if (isDesktop) {
      if (useMapWorkspaceStore.getState().sidebarCollapsed) setSidebarCollapsed(false);
    } else if (!drawerOpened) {
      openDrawer();
    }
  }, [hasSelection, selectionKey, isDesktop, drawerOpened, openDrawer, setSidebarCollapsed]);

  useEffect(() => {
    if (!showInfo) return;
    if (!isDesktop && !overlayOpen) return;
    sidebarRef.current?.focus({ preventScroll: true });
  }, [showInfo, selectionKey, isDesktop, overlayOpen]);

  useEffect(() => {
    if (!overlayOpen && !hasSelection) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (isFromTextEntry(event.target)) return;
      if (hasSelection) {
        onCloseSelection?.();
        return;
      }
      if (overlayOpen) closeDrawer();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [overlayOpen, hasSelection, onCloseSelection, closeDrawer]);

  useDrawerHistoryClose({
    opened: overlayOpen,
    onClose: drawer.close,
    enabled: !isDesktop,
  });

  const countBadge =
    activeLayerCount !== undefined ? (
      <Badge size="sm" variant="light" color="blue" style={{ flexShrink: 0 }}>
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
      <div
        className={styles.visuallyHidden}
        role="status"
        aria-live="polite"
        data-testid="map-live-region"
      >
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
        ref={sidebarRef}
        className={styles.workspaceSidebar}
        data-collapsed={headerCollapsed ? 'true' : 'false'}
        data-tab={showInfo ? 'info' : 'capas'}
        data-testid="map-workspace-sidebar"
        tabIndex={-1}
        aria-label={showInfo ? 'Información del elemento' : 'Panel de capas y leyenda'}
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
          <Group justify="space-between" wrap="nowrap" gap="xs" w="100%">
            {!headerCollapsed && hasSelection && (
              <Group gap="xs" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                <SegmentedControl
                  size="xs"
                  value={tab}
                  onChange={(value) => setTab(value as SidebarTab)}
                  data={[
                    { label: 'Capas', value: 'capas' },
                    { label: 'Información', value: 'info' },
                  ]}
                  aria-label="Sección del panel"
                  data-testid="map-workspace-tabs"
                />
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  onClick={onCloseSelection}
                  aria-label="Cerrar panel de información"
                  data-testid="map-workspace-selection-close"
                >
                  <IconX size={18} />
                </ActionIcon>
              </Group>
            )}
            {!headerCollapsed && !hasSelection && (
              <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
                <IconLayers size={18} style={{ flexShrink: 0 }} />
                <Text fw={600} size="sm" truncate>
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
          </Group>
          {!headerCollapsed && headerSlot ? (
            <Box className={styles.workspaceSidebarSearch} w="100%">
              {headerSlot}
            </Box>
          ) : null}
        </Box>
        <Box className={styles.workspaceSidebarBody}>
          <div hidden={showInfo}>{controls}</div>
          {showInfo ? selection : null}
        </Box>
      </Box>
    </Box>
  );
}
