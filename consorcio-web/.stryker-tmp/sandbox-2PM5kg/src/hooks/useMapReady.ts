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
  if (stryMutAct_9fa48("473")) {
    {}
  } else {
    stryCov_9fa48("473");
    const map = useMap();
    const hasInitialized = useRef(stryMutAct_9fa48("474") ? true : (stryCov_9fa48("474"), false));
    useEffect(() => {
      if (stryMutAct_9fa48("475")) {
        {}
      } else {
        stryCov_9fa48("475");
        // Force immediate invalidation
        map.invalidateSize();

        // Invalidation schedule for SPA navigation - less aggressive now that we use keys
        const timeouts = stryMutAct_9fa48("476") ? [] : (stryCov_9fa48("476"), [setTimeout(stryMutAct_9fa48("477") ? () => undefined : (stryCov_9fa48("477"), () => map.invalidateSize()), 0), setTimeout(stryMutAct_9fa48("478") ? () => undefined : (stryCov_9fa48("478"), () => map.invalidateSize()), 100), setTimeout(stryMutAct_9fa48("479") ? () => undefined : (stryCov_9fa48("479"), () => map.invalidateSize()), 300)]);

        // Use requestAnimationFrame for smoother updates
        let rafId: number;
        const invalidateOnFrame = () => {
          if (stryMutAct_9fa48("480")) {
            {}
          } else {
            stryCov_9fa48("480");
            map.invalidateSize();
            if (stryMutAct_9fa48("483") ? false : stryMutAct_9fa48("482") ? true : stryMutAct_9fa48("481") ? hasInitialized.current : (stryCov_9fa48("481", "482", "483"), !hasInitialized.current)) {
              if (stryMutAct_9fa48("484")) {
                {}
              } else {
                stryCov_9fa48("484");
                hasInitialized.current = stryMutAct_9fa48("485") ? false : (stryCov_9fa48("485"), true);
                // One more after initialization
                rafId = requestAnimationFrame(stryMutAct_9fa48("486") ? () => undefined : (stryCov_9fa48("486"), () => map.invalidateSize()));
              }
            }
          }
        };
        rafId = requestAnimationFrame(invalidateOnFrame);

        // Handle window resize
        const handleResize = () => {
          if (stryMutAct_9fa48("487")) {
            {}
          } else {
            stryCov_9fa48("487");
            map.invalidateSize();
          }
        };
        window.addEventListener(stryMutAct_9fa48("488") ? "" : (stryCov_9fa48("488"), 'resize'), handleResize);

        // Handle visibility change (tab switching)
        const handleVisibilityChange = () => {
          if (stryMutAct_9fa48("489")) {
            {}
          } else {
            stryCov_9fa48("489");
            if (stryMutAct_9fa48("492") ? document.visibilityState !== 'visible' : stryMutAct_9fa48("491") ? false : stryMutAct_9fa48("490") ? true : (stryCov_9fa48("490", "491", "492"), document.visibilityState === (stryMutAct_9fa48("493") ? "" : (stryCov_9fa48("493"), 'visible')))) {
              if (stryMutAct_9fa48("494")) {
                {}
              } else {
                stryCov_9fa48("494");
                map.invalidateSize();
                setTimeout(stryMutAct_9fa48("495") ? () => undefined : (stryCov_9fa48("495"), () => map.invalidateSize()), 100);
              }
            }
          }
        };
        document.addEventListener(stryMutAct_9fa48("496") ? "" : (stryCov_9fa48("496"), 'visibilitychange'), handleVisibilityChange);

        // Use ResizeObserver for container size changes
        const container = map.getContainer();
        let resizeObserver: ResizeObserver | null = null;
        if (stryMutAct_9fa48("499") ? container || typeof ResizeObserver !== 'undefined' : stryMutAct_9fa48("498") ? false : stryMutAct_9fa48("497") ? true : (stryCov_9fa48("497", "498", "499"), container && (stryMutAct_9fa48("501") ? typeof ResizeObserver === 'undefined' : stryMutAct_9fa48("500") ? true : (stryCov_9fa48("500", "501"), typeof ResizeObserver !== (stryMutAct_9fa48("502") ? "" : (stryCov_9fa48("502"), 'undefined')))))) {
          if (stryMutAct_9fa48("503")) {
            {}
          } else {
            stryCov_9fa48("503");
            resizeObserver = new ResizeObserver(() => {
              if (stryMutAct_9fa48("504")) {
                {}
              } else {
                stryCov_9fa48("504");
                map.invalidateSize();
              }
            });
            resizeObserver.observe(container);
          }
        }
        return () => {
          if (stryMutAct_9fa48("505")) {
            {}
          } else {
            stryCov_9fa48("505");
            timeouts.forEach(clearTimeout);
            cancelAnimationFrame(rafId);
            window.removeEventListener(stryMutAct_9fa48("506") ? "" : (stryCov_9fa48("506"), 'resize'), handleResize);
            document.removeEventListener(stryMutAct_9fa48("507") ? "" : (stryCov_9fa48("507"), 'visibilitychange'), handleVisibilityChange);
            stryMutAct_9fa48("508") ? resizeObserver.disconnect() : (stryCov_9fa48("508"), resizeObserver?.disconnect());
          }
        };
      }
    }, stryMutAct_9fa48("509") ? [] : (stryCov_9fa48("509"), [map]));
    return map;
  }
}

/**
 * Component that fixes map sizing issues.
 * Add this as a child of MapContainer.
 */
export function MapReadyHandler() {
  if (stryMutAct_9fa48("510")) {
    {}
  } else {
    stryCov_9fa48("510");
    useMapReady();
    return null;
  }
}