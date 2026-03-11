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
  if (stryMutAct_9fa48("57")) {
    {}
  } else {
    stryCov_9fa48("57");
    const map = useMap();
    const hasInitialized = useRef(stryMutAct_9fa48("58") ? true : (stryCov_9fa48("58"), false));
    useEffect(() => {
      if (stryMutAct_9fa48("59")) {
        {}
      } else {
        stryCov_9fa48("59");
        // Force immediate invalidation
        map.invalidateSize();

        // Invalidation schedule for SPA navigation - less aggressive now that we use keys
        const timeouts = stryMutAct_9fa48("60") ? [] : (stryCov_9fa48("60"), [setTimeout(stryMutAct_9fa48("61") ? () => undefined : (stryCov_9fa48("61"), () => map.invalidateSize()), 0), setTimeout(stryMutAct_9fa48("62") ? () => undefined : (stryCov_9fa48("62"), () => map.invalidateSize()), 100), setTimeout(stryMutAct_9fa48("63") ? () => undefined : (stryCov_9fa48("63"), () => map.invalidateSize()), 300)]);

        // Use requestAnimationFrame for smoother updates
        let rafId: number;
        const invalidateOnFrame = () => {
          if (stryMutAct_9fa48("64")) {
            {}
          } else {
            stryCov_9fa48("64");
            map.invalidateSize();
            if (stryMutAct_9fa48("67") ? false : stryMutAct_9fa48("66") ? true : stryMutAct_9fa48("65") ? hasInitialized.current : (stryCov_9fa48("65", "66", "67"), !hasInitialized.current)) {
              if (stryMutAct_9fa48("68")) {
                {}
              } else {
                stryCov_9fa48("68");
                hasInitialized.current = stryMutAct_9fa48("69") ? false : (stryCov_9fa48("69"), true);
                // One more after initialization
                rafId = requestAnimationFrame(stryMutAct_9fa48("70") ? () => undefined : (stryCov_9fa48("70"), () => map.invalidateSize()));
              }
            }
          }
        };
        rafId = requestAnimationFrame(invalidateOnFrame);

        // Handle window resize
        const handleResize = () => {
          if (stryMutAct_9fa48("71")) {
            {}
          } else {
            stryCov_9fa48("71");
            map.invalidateSize();
          }
        };
        window.addEventListener(stryMutAct_9fa48("72") ? "" : (stryCov_9fa48("72"), 'resize'), handleResize);

        // Handle visibility change (tab switching)
        const handleVisibilityChange = () => {
          if (stryMutAct_9fa48("73")) {
            {}
          } else {
            stryCov_9fa48("73");
            if (stryMutAct_9fa48("76") ? document.visibilityState !== 'visible' : stryMutAct_9fa48("75") ? false : stryMutAct_9fa48("74") ? true : (stryCov_9fa48("74", "75", "76"), document.visibilityState === (stryMutAct_9fa48("77") ? "" : (stryCov_9fa48("77"), 'visible')))) {
              if (stryMutAct_9fa48("78")) {
                {}
              } else {
                stryCov_9fa48("78");
                map.invalidateSize();
                setTimeout(stryMutAct_9fa48("79") ? () => undefined : (stryCov_9fa48("79"), () => map.invalidateSize()), 100);
              }
            }
          }
        };
        document.addEventListener(stryMutAct_9fa48("80") ? "" : (stryCov_9fa48("80"), 'visibilitychange'), handleVisibilityChange);

        // Use ResizeObserver for container size changes
        const container = map.getContainer();
        let resizeObserver: ResizeObserver | null = null;
        if (stryMutAct_9fa48("83") ? container || typeof ResizeObserver !== 'undefined' : stryMutAct_9fa48("82") ? false : stryMutAct_9fa48("81") ? true : (stryCov_9fa48("81", "82", "83"), container && (stryMutAct_9fa48("85") ? typeof ResizeObserver === 'undefined' : stryMutAct_9fa48("84") ? true : (stryCov_9fa48("84", "85"), typeof ResizeObserver !== (stryMutAct_9fa48("86") ? "" : (stryCov_9fa48("86"), 'undefined')))))) {
          if (stryMutAct_9fa48("87")) {
            {}
          } else {
            stryCov_9fa48("87");
            resizeObserver = new ResizeObserver(() => {
              if (stryMutAct_9fa48("88")) {
                {}
              } else {
                stryCov_9fa48("88");
                map.invalidateSize();
              }
            });
            resizeObserver.observe(container);
          }
        }
        return () => {
          if (stryMutAct_9fa48("89")) {
            {}
          } else {
            stryCov_9fa48("89");
            timeouts.forEach(clearTimeout);
            cancelAnimationFrame(rafId);
            window.removeEventListener(stryMutAct_9fa48("90") ? "" : (stryCov_9fa48("90"), 'resize'), handleResize);
            document.removeEventListener(stryMutAct_9fa48("91") ? "" : (stryCov_9fa48("91"), 'visibilitychange'), handleVisibilityChange);
            stryMutAct_9fa48("92") ? resizeObserver.disconnect() : (stryCov_9fa48("92"), resizeObserver?.disconnect());
          }
        };
      }
    }, stryMutAct_9fa48("93") ? [] : (stryCov_9fa48("93"), [map]));
    return map;
  }
}

/**
 * Component that fixes map sizing issues.
 * Add this as a child of MapContainer.
 */
export function MapReadyHandler() {
  if (stryMutAct_9fa48("94")) {
    {}
  } else {
    stryCov_9fa48("94");
    useMapReady();
    return null;
  }
}