/**
 * Hook for loading GeoJSON layers from GEE backend.
 * Centralizes layer loading logic used across multiple map components.
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
import type { FeatureCollection } from 'geojson';
import { useCallback, useEffect, useState } from 'react';
import { API_URL } from '../lib/api';
import { logger } from '../lib/logger';
import { parseFeatureCollection } from '../lib/typeGuards';

// Default layer names available from GEE
export const GEE_LAYER_NAMES = ['zona', 'candil', 'ml', 'noroeste', 'norte', 'caminos'] as const;
export type GEELayerName = (typeof GEE_LAYER_NAMES)[number];

// Layer colors for styling and legends
export const GEE_LAYER_COLORS: Record<GEELayerName, string> = stryMutAct_9fa48("205") ? {} : (stryCov_9fa48("205"), {
  zona: stryMutAct_9fa48("206") ? "" : (stryCov_9fa48("206"), '#FF0000'),
  candil: stryMutAct_9fa48("207") ? "" : (stryCov_9fa48("207"), '#2196F3'),
  ml: stryMutAct_9fa48("208") ? "" : (stryCov_9fa48("208"), '#4CAF50'),
  noroeste: stryMutAct_9fa48("209") ? "" : (stryCov_9fa48("209"), '#FF9800'),
  norte: stryMutAct_9fa48("210") ? "" : (stryCov_9fa48("210"), '#9C27B0'),
  caminos: stryMutAct_9fa48("211") ? "" : (stryCov_9fa48("211"), '#FFEB3B')
});

// Default styles for GeoJSON layers (Leaflet PathOptions)
export const GEE_LAYER_STYLES: Record<GEELayerName, {
  color: string;
  weight: number;
  fillOpacity: number;
  fillColor?: string;
}> = stryMutAct_9fa48("212") ? {} : (stryCov_9fa48("212"), {
  zona: stryMutAct_9fa48("213") ? {} : (stryCov_9fa48("213"), {
    color: stryMutAct_9fa48("214") ? "" : (stryCov_9fa48("214"), '#FF0000'),
    weight: 3,
    fillOpacity: 0
  }),
  candil: stryMutAct_9fa48("215") ? {} : (stryCov_9fa48("215"), {
    color: stryMutAct_9fa48("216") ? "" : (stryCov_9fa48("216"), '#2196F3'),
    weight: 2,
    fillOpacity: 0.1,
    fillColor: stryMutAct_9fa48("217") ? "" : (stryCov_9fa48("217"), '#2196F3')
  }),
  ml: stryMutAct_9fa48("218") ? {} : (stryCov_9fa48("218"), {
    color: stryMutAct_9fa48("219") ? "" : (stryCov_9fa48("219"), '#4CAF50'),
    weight: 2,
    fillOpacity: 0.1,
    fillColor: stryMutAct_9fa48("220") ? "" : (stryCov_9fa48("220"), '#4CAF50')
  }),
  noroeste: stryMutAct_9fa48("221") ? {} : (stryCov_9fa48("221"), {
    color: stryMutAct_9fa48("222") ? "" : (stryCov_9fa48("222"), '#FF9800'),
    weight: 2,
    fillOpacity: 0.1,
    fillColor: stryMutAct_9fa48("223") ? "" : (stryCov_9fa48("223"), '#FF9800')
  }),
  norte: stryMutAct_9fa48("224") ? {} : (stryCov_9fa48("224"), {
    color: stryMutAct_9fa48("225") ? "" : (stryCov_9fa48("225"), '#9C27B0'),
    weight: 2,
    fillOpacity: 0.1,
    fillColor: stryMutAct_9fa48("226") ? "" : (stryCov_9fa48("226"), '#9C27B0')
  }),
  caminos: stryMutAct_9fa48("227") ? {} : (stryCov_9fa48("227"), {
    color: stryMutAct_9fa48("228") ? "" : (stryCov_9fa48("228"), '#FFEB3B'),
    weight: 2,
    fillOpacity: 0
  })
});

// Layer data structure
export interface GEELayerData {
  name: GEELayerName;
  data: FeatureCollection;
}

// Layers map type
export type GEELayersMap = Partial<Record<GEELayerName, FeatureCollection>>;
interface UseGEELayersResult {
  /** Layers data as a map (name -> FeatureCollection) */
  layers: GEELayersMap;
  /** Layers data as array with name and color info */
  layersArray: GEELayerData[];
  /** Loading state */
  loading: boolean;
  /** Error message if any layer failed to load */
  error: string | null;
  /** Reload layers */
  reload: () => Promise<void>;
}
interface UseGEELayersOptions {
  /** Layer names to load. Defaults to all layers. */
  layerNames?: readonly GEELayerName[];
  /** Whether to load layers immediately. Defaults to true. */
  enabled?: boolean;
}

/**
 * Hook for loading GeoJSON layers from the GEE backend.
 *
 * @example
 * ```tsx
 * const { layers, loading, error } = useGEELayers();
 *
 * // Or load specific layers only
 * const { layers } = useGEELayers({ layerNames: ['zona', 'candil'] });
 * ```
 */
export function useGEELayers(options: UseGEELayersOptions = {}): UseGEELayersResult {
  if (stryMutAct_9fa48("229")) {
    {}
  } else {
    stryCov_9fa48("229");
    const {
      layerNames = GEE_LAYER_NAMES,
      enabled = stryMutAct_9fa48("230") ? false : (stryCov_9fa48("230"), true)
    } = options;
    const [layers, setLayers] = useState<GEELayersMap>({});
    const [loading, setLoading] = useState(stryMutAct_9fa48("231") ? false : (stryCov_9fa48("231"), true));
    const [error, setError] = useState<string | null>(null);
    const loadLayer = useCallback(async (name: GEELayerName): Promise<[GEELayerName, FeatureCollection | null]> => {
      if (stryMutAct_9fa48("232")) {
        {}
      } else {
        stryCov_9fa48("232");
        try {
          if (stryMutAct_9fa48("233")) {
            {}
          } else {
            stryCov_9fa48("233");
            const response = await fetch(stryMutAct_9fa48("234") ? `` : (stryCov_9fa48("234"), `${API_URL}/api/v1/gee/layers/${name}`));
            if (stryMutAct_9fa48("236") ? false : stryMutAct_9fa48("235") ? true : (stryCov_9fa48("235", "236"), response.ok)) {
              if (stryMutAct_9fa48("237")) {
                {}
              } else {
                stryCov_9fa48("237");
                const rawData = await response.json();

                // Validate the GeoJSON structure at runtime
                const validatedData = parseFeatureCollection(rawData);
                if (stryMutAct_9fa48("240") ? false : stryMutAct_9fa48("239") ? true : stryMutAct_9fa48("238") ? validatedData : (stryCov_9fa48("238", "239", "240"), !validatedData)) {
                  if (stryMutAct_9fa48("241")) {
                    {}
                  } else {
                    stryCov_9fa48("241");
                    logger.warn(stryMutAct_9fa48("242") ? `` : (stryCov_9fa48("242"), `GEE layer '${name}' returned invalid GeoJSON structure`));
                    return stryMutAct_9fa48("243") ? [] : (stryCov_9fa48("243"), [name, null]);
                  }
                }
                return stryMutAct_9fa48("244") ? [] : (stryCov_9fa48("244"), [name, validatedData]);
              }
            }
            // Log warning but don't throw - layer might not be available
            logger.warn(stryMutAct_9fa48("245") ? `` : (stryCov_9fa48("245"), `GEE layer '${name}' not available: ${response.status}`));
            return stryMutAct_9fa48("246") ? [] : (stryCov_9fa48("246"), [name, null]);
          }
        } catch (err) {
          if (stryMutAct_9fa48("247")) {
            {}
          } else {
            stryCov_9fa48("247");
            logger.warn(stryMutAct_9fa48("248") ? `` : (stryCov_9fa48("248"), `Error loading GEE layer '${name}'`), err);
            return stryMutAct_9fa48("249") ? [] : (stryCov_9fa48("249"), [name, null]);
          }
        }
      }
    }, stryMutAct_9fa48("250") ? ["Stryker was here"] : (stryCov_9fa48("250"), []));
    const reload = useCallback(async () => {
      if (stryMutAct_9fa48("251")) {
        {}
      } else {
        stryCov_9fa48("251");
        setLoading(stryMutAct_9fa48("252") ? false : (stryCov_9fa48("252"), true));
        setError(null);
        try {
          if (stryMutAct_9fa48("253")) {
            {}
          } else {
            stryCov_9fa48("253");
            const results = await Promise.all(layerNames.map(loadLayer));
            const newLayers: GEELayersMap = {};
            let loadedCount = 0;
            for (const [name, data] of results) {
              if (stryMutAct_9fa48("254")) {
                {}
              } else {
                stryCov_9fa48("254");
                if (stryMutAct_9fa48("256") ? false : stryMutAct_9fa48("255") ? true : (stryCov_9fa48("255", "256"), data)) {
                  if (stryMutAct_9fa48("257")) {
                    {}
                  } else {
                    stryCov_9fa48("257");
                    newLayers[name] = data;
                    stryMutAct_9fa48("258") ? loadedCount-- : (stryCov_9fa48("258"), loadedCount++);
                  }
                }
              }
            }
            setLayers(newLayers);

            // Set error if no layers loaded
            if (stryMutAct_9fa48("261") ? loadedCount === 0 || layerNames.length > 0 : stryMutAct_9fa48("260") ? false : stryMutAct_9fa48("259") ? true : (stryCov_9fa48("259", "260", "261"), (stryMutAct_9fa48("263") ? loadedCount !== 0 : stryMutAct_9fa48("262") ? true : (stryCov_9fa48("262", "263"), loadedCount === 0)) && (stryMutAct_9fa48("266") ? layerNames.length <= 0 : stryMutAct_9fa48("265") ? layerNames.length >= 0 : stryMutAct_9fa48("264") ? true : (stryCov_9fa48("264", "265", "266"), layerNames.length > 0)))) {
              if (stryMutAct_9fa48("267")) {
                {}
              } else {
                stryCov_9fa48("267");
                setError(stryMutAct_9fa48("268") ? "" : (stryCov_9fa48("268"), 'No se pudieron cargar las capas del mapa'));
              }
            }
          }
        } catch (err) {
          if (stryMutAct_9fa48("269")) {
            {}
          } else {
            stryCov_9fa48("269");
            setError(stryMutAct_9fa48("270") ? "" : (stryCov_9fa48("270"), 'Error al cargar capas del mapa'));
            logger.error(stryMutAct_9fa48("271") ? "" : (stryCov_9fa48("271"), 'Error loading GEE layers'), err);
          }
        } finally {
          if (stryMutAct_9fa48("272")) {
            {}
          } else {
            stryCov_9fa48("272");
            setLoading(stryMutAct_9fa48("273") ? true : (stryCov_9fa48("273"), false));
          }
        }
      }
    }, stryMutAct_9fa48("274") ? [] : (stryCov_9fa48("274"), [layerNames, loadLayer]));
    useEffect(() => {
      if (stryMutAct_9fa48("275")) {
        {}
      } else {
        stryCov_9fa48("275");
        if (stryMutAct_9fa48("277") ? false : stryMutAct_9fa48("276") ? true : (stryCov_9fa48("276", "277"), enabled)) {
          if (stryMutAct_9fa48("278")) {
            {}
          } else {
            stryCov_9fa48("278");
            reload();
          }
        } else {
          if (stryMutAct_9fa48("279")) {
            {}
          } else {
            stryCov_9fa48("279");
            setLoading(stryMutAct_9fa48("280") ? true : (stryCov_9fa48("280"), false));
          }
        }
      }
    }, stryMutAct_9fa48("281") ? [] : (stryCov_9fa48("281"), [enabled, reload]));

    // Convert layers map to array format
    const layersArray: GEELayerData[] = stryMutAct_9fa48("282") ? Object.entries(layers).map(([name, data]) => ({
      name: name as GEELayerName,
      data: data as FeatureCollection
    })) : (stryCov_9fa48("282"), Object.entries(layers).filter(stryMutAct_9fa48("283") ? () => undefined : (stryCov_9fa48("283"), ([, data]) => stryMutAct_9fa48("286") ? data === undefined : stryMutAct_9fa48("285") ? false : stryMutAct_9fa48("284") ? true : (stryCov_9fa48("284", "285", "286"), data !== undefined))).map(stryMutAct_9fa48("287") ? () => undefined : (stryCov_9fa48("287"), ([name, data]) => stryMutAct_9fa48("288") ? {} : (stryCov_9fa48("288"), {
      name: name as GEELayerName,
      data: data as FeatureCollection
    }))));
    return stryMutAct_9fa48("289") ? {} : (stryCov_9fa48("289"), {
      layers,
      layersArray,
      loading,
      error,
      reload
    });
  }
}
export default useGEELayers;