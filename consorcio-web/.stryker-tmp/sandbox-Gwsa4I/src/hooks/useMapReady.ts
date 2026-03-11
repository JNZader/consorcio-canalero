/**
 * Hook to fix Leaflet map sizing issues.
 *
 * Leaflet maps often render incorrectly when:
 * - The container size changes after initialization
 * - The map is initialized while hidden or with zero dimensions
 * - React components re-render
 * - SPA navigation occurs (TanStack Router)
 *
 * This hook calls invalidateSize() to recalculate the map size.
 */
// @ts-nocheck
function stryNS_9fa48() {
  var g = typeof globalThis === 'object' && globalThis && globalThis.Math === Math && globalThis || new Function("return this")();
  var ns = g.__stryker__ || (g.__stryker__ = {});
  if (ns.activeMutant === undefined && g.process && g.process.env && g.process.env.__STRYKER_ACTIVE_MUTANT__) {
    ns.activeMutant = g.process.env.__STRYKER_ACTIVE_MUTANT__;
  }
  function retrieveNS() {
    return ns;
  }
  stryNS_9fa48 = retrieveNS;
  return retrieveNS();
}
stryNS_9fa48();
function stryCov_9fa48() {
  var ns = stryNS_9fa48();
  var cov = ns.mutantCoverage || (ns.mutantCoverage = {
    static: {},
    perTest: {}
  });
  function cover() {
    var c = cov.static;
    if (ns.currentTestId) {
      c = cov.perTest[ns.currentTestId] = cov.perTest[ns.currentTestId] || {};
    }
    var a = arguments;
    for (var i = 0; i < a.length; i++) {
      c[a[i]] = (c[a[i]] || 0) + 1;
    }
  }
  stryCov_9fa48 = cover;
  cover.apply(null, arguments);
}
function stryMutAct_9fa48(id) {
  var ns = stryNS_9fa48();
  function isActive(id) {
    if (ns.activeMutant === id) {
      if (ns.hitCount !== void 0 && ++ns.hitCount > ns.hitLimit) {
        throw new Error('Stryker: Hit count limit reached (' + ns.hitCount + ')');
      }
      return true;
    }
    return false;
  }
  stryMutAct_9fa48 = isActive;
  return isActive(id);
}
import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';

/**
 * Hook that ensures the map renders correctly by calling invalidateSize.
 * Must be used inside a MapContainer component.
 */
export function useMapReady() {
  if (stryMutAct_9fa48("0")) {
    {}
  } else {
    stryCov_9fa48("0");
    const map = useMap();
    const hasInitialized = useRef(stryMutAct_9fa48("1") ? true : (stryCov_9fa48("1"), false));
    useEffect(() => {
      if (stryMutAct_9fa48("2")) {
        {}
      } else {
        stryCov_9fa48("2");
        // Force immediate invalidation
        map.invalidateSize();

        // Invalidation schedule for SPA navigation - less aggressive now that we use keys
        const timeouts = stryMutAct_9fa48("3") ? [] : (stryCov_9fa48("3"), [setTimeout(stryMutAct_9fa48("4") ? () => undefined : (stryCov_9fa48("4"), () => map.invalidateSize()), 0), setTimeout(stryMutAct_9fa48("5") ? () => undefined : (stryCov_9fa48("5"), () => map.invalidateSize()), 100), setTimeout(stryMutAct_9fa48("6") ? () => undefined : (stryCov_9fa48("6"), () => map.invalidateSize()), 300)]);

        // Use requestAnimationFrame for smoother updates
        let rafId: number;
        const invalidateOnFrame = () => {
          if (stryMutAct_9fa48("7")) {
            {}
          } else {
            stryCov_9fa48("7");
            map.invalidateSize();
            if (stryMutAct_9fa48("10") ? false : stryMutAct_9fa48("9") ? true : stryMutAct_9fa48("8") ? hasInitialized.current : (stryCov_9fa48("8", "9", "10"), !hasInitialized.current)) {
              if (stryMutAct_9fa48("11")) {
                {}
              } else {
                stryCov_9fa48("11");
                hasInitialized.current = stryMutAct_9fa48("12") ? false : (stryCov_9fa48("12"), true);
                // One more after initialization
                rafId = requestAnimationFrame(stryMutAct_9fa48("13") ? () => undefined : (stryCov_9fa48("13"), () => map.invalidateSize()));
              }
            }
          }
        };
        rafId = requestAnimationFrame(invalidateOnFrame);

        // Handle window resize
        const handleResize = () => {
          if (stryMutAct_9fa48("14")) {
            {}
          } else {
            stryCov_9fa48("14");
            map.invalidateSize();
          }
        };
        window.addEventListener(stryMutAct_9fa48("15") ? "" : (stryCov_9fa48("15"), 'resize'), handleResize);

        // Handle visibility change (tab switching)
        const handleVisibilityChange = () => {
          if (stryMutAct_9fa48("16")) {
            {}
          } else {
            stryCov_9fa48("16");
            if (stryMutAct_9fa48("19") ? document.visibilityState !== 'visible' : stryMutAct_9fa48("18") ? false : stryMutAct_9fa48("17") ? true : (stryCov_9fa48("17", "18", "19"), document.visibilityState === (stryMutAct_9fa48("20") ? "" : (stryCov_9fa48("20"), 'visible')))) {
              if (stryMutAct_9fa48("21")) {
                {}
              } else {
                stryCov_9fa48("21");
                map.invalidateSize();
                setTimeout(stryMutAct_9fa48("22") ? () => undefined : (stryCov_9fa48("22"), () => map.invalidateSize()), 100);
              }
            }
          }
        };
        document.addEventListener(stryMutAct_9fa48("23") ? "" : (stryCov_9fa48("23"), 'visibilitychange'), handleVisibilityChange);

        // Use ResizeObserver for container size changes
        const container = map.getContainer();
        let resizeObserver: ResizeObserver | null = null;
        if (stryMutAct_9fa48("26") ? container || typeof ResizeObserver !== 'undefined' : stryMutAct_9fa48("25") ? false : stryMutAct_9fa48("24") ? true : (stryCov_9fa48("24", "25", "26"), container && (stryMutAct_9fa48("28") ? typeof ResizeObserver === 'undefined' : stryMutAct_9fa48("27") ? true : (stryCov_9fa48("27", "28"), typeof ResizeObserver !== (stryMutAct_9fa48("29") ? "" : (stryCov_9fa48("29"), 'undefined')))))) {
          if (stryMutAct_9fa48("30")) {
            {}
          } else {
            stryCov_9fa48("30");
            resizeObserver = new ResizeObserver(() => {
              if (stryMutAct_9fa48("31")) {
                {}
              } else {
                stryCov_9fa48("31");
                map.invalidateSize();
              }
            });
            resizeObserver.observe(container);
          }
        }
        return () => {
          if (stryMutAct_9fa48("32")) {
            {}
          } else {
            stryCov_9fa48("32");
            timeouts.forEach(clearTimeout);
            cancelAnimationFrame(rafId);
            window.removeEventListener(stryMutAct_9fa48("33") ? "" : (stryCov_9fa48("33"), 'resize'), handleResize);
            document.removeEventListener(stryMutAct_9fa48("34") ? "" : (stryCov_9fa48("34"), 'visibilitychange'), handleVisibilityChange);
            stryMutAct_9fa48("35") ? resizeObserver.disconnect() : (stryCov_9fa48("35"), resizeObserver?.disconnect());
          }
        };
      }
    }, stryMutAct_9fa48("36") ? [] : (stryCov_9fa48("36"), [map]));
    return map;
  }
}

/**
 * Component that fixes map sizing issues.
 * Add this as a child of MapContainer.
 */
export function MapReadyHandler() {
  if (stryMutAct_9fa48("37")) {
    {}
  } else {
    stryCov_9fa48("37");
    useMapReady();
    return null;
  }
}