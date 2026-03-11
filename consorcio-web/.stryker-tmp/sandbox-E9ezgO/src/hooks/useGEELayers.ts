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
export const GEE_LAYER_COLORS: Record<GEELayerName, string> = stryMutAct_9fa48("0") ? {} : (stryCov_9fa48("0"), {
  zona: stryMutAct_9fa48("1") ? "" : (stryCov_9fa48("1"), '#FF0000'),
  candil: stryMutAct_9fa48("2") ? "" : (stryCov_9fa48("2"), '#2196F3'),
  ml: stryMutAct_9fa48("3") ? "" : (stryCov_9fa48("3"), '#4CAF50'),
  noroeste: stryMutAct_9fa48("4") ? "" : (stryCov_9fa48("4"), '#FF9800'),
  norte: stryMutAct_9fa48("5") ? "" : (stryCov_9fa48("5"), '#9C27B0'),
  caminos: stryMutAct_9fa48("6") ? "" : (stryCov_9fa48("6"), '#FFEB3B')
});

// Default styles for GeoJSON layers (Leaflet PathOptions)
export const GEE_LAYER_STYLES: Record<GEELayerName, {
  color: string;
  weight: number;
  fillOpacity: number;
  fillColor?: string;
}> = stryMutAct_9fa48("7") ? {} : (stryCov_9fa48("7"), {
  zona: stryMutAct_9fa48("8") ? {} : (stryCov_9fa48("8"), {
    color: stryMutAct_9fa48("9") ? "" : (stryCov_9fa48("9"), '#FF0000'),
    weight: 3,
    fillOpacity: 0
  }),
  candil: stryMutAct_9fa48("10") ? {} : (stryCov_9fa48("10"), {
    color: stryMutAct_9fa48("11") ? "" : (stryCov_9fa48("11"), '#2196F3'),
    weight: 2,
    fillOpacity: 0.1,
    fillColor: stryMutAct_9fa48("12") ? "" : (stryCov_9fa48("12"), '#2196F3')
  }),
  ml: stryMutAct_9fa48("13") ? {} : (stryCov_9fa48("13"), {
    color: stryMutAct_9fa48("14") ? "" : (stryCov_9fa48("14"), '#4CAF50'),
    weight: 2,
    fillOpacity: 0.1,
    fillColor: stryMutAct_9fa48("15") ? "" : (stryCov_9fa48("15"), '#4CAF50')
  }),
  noroeste: stryMutAct_9fa48("16") ? {} : (stryCov_9fa48("16"), {
    color: stryMutAct_9fa48("17") ? "" : (stryCov_9fa48("17"), '#FF9800'),
    weight: 2,
    fillOpacity: 0.1,
    fillColor: stryMutAct_9fa48("18") ? "" : (stryCov_9fa48("18"), '#FF9800')
  }),
  norte: stryMutAct_9fa48("19") ? {} : (stryCov_9fa48("19"), {
    color: stryMutAct_9fa48("20") ? "" : (stryCov_9fa48("20"), '#9C27B0'),
    weight: 2,
    fillOpacity: 0.1,
    fillColor: stryMutAct_9fa48("21") ? "" : (stryCov_9fa48("21"), '#9C27B0')
  }),
  caminos: stryMutAct_9fa48("22") ? {} : (stryCov_9fa48("22"), {
    color: stryMutAct_9fa48("23") ? "" : (stryCov_9fa48("23"), '#FFEB3B'),
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
  if (stryMutAct_9fa48("24")) {
    {}
  } else {
    stryCov_9fa48("24");
    const {
      layerNames = GEE_LAYER_NAMES,
      enabled = stryMutAct_9fa48("25") ? false : (stryCov_9fa48("25"), true)
    } = options;
    const [layers, setLayers] = useState<GEELayersMap>({});
    const [loading, setLoading] = useState(stryMutAct_9fa48("26") ? false : (stryCov_9fa48("26"), true));
    const [error, setError] = useState<string | null>(null);
    const loadLayer = useCallback(async (name: GEELayerName): Promise<[GEELayerName, FeatureCollection | null]> => {
      if (stryMutAct_9fa48("27")) {
        {}
      } else {
        stryCov_9fa48("27");
        try {
          if (stryMutAct_9fa48("28")) {
            {}
          } else {
            stryCov_9fa48("28");
            const response = await fetch(stryMutAct_9fa48("29") ? `` : (stryCov_9fa48("29"), `${API_URL}/api/v1/gee/layers/${name}`));
            if (stryMutAct_9fa48("31") ? false : stryMutAct_9fa48("30") ? true : (stryCov_9fa48("30", "31"), response.ok)) {
              if (stryMutAct_9fa48("32")) {
                {}
              } else {
                stryCov_9fa48("32");
                const rawData = await response.json();

                // Validate the GeoJSON structure at runtime
                const validatedData = parseFeatureCollection(rawData);
                if (stryMutAct_9fa48("35") ? false : stryMutAct_9fa48("34") ? true : stryMutAct_9fa48("33") ? validatedData : (stryCov_9fa48("33", "34", "35"), !validatedData)) {
                  if (stryMutAct_9fa48("36")) {
                    {}
                  } else {
                    stryCov_9fa48("36");
                    logger.warn(stryMutAct_9fa48("37") ? `` : (stryCov_9fa48("37"), `GEE layer '${name}' returned invalid GeoJSON structure`));
                    return stryMutAct_9fa48("38") ? [] : (stryCov_9fa48("38"), [name, null]);
                  }
                }
                return stryMutAct_9fa48("39") ? [] : (stryCov_9fa48("39"), [name, validatedData]);
              }
            }
            // Log warning but don't throw - layer might not be available
            logger.warn(stryMutAct_9fa48("40") ? `` : (stryCov_9fa48("40"), `GEE layer '${name}' not available: ${response.status}`));
            return stryMutAct_9fa48("41") ? [] : (stryCov_9fa48("41"), [name, null]);
          }
        } catch (err) {
          if (stryMutAct_9fa48("42")) {
            {}
          } else {
            stryCov_9fa48("42");
            logger.warn(stryMutAct_9fa48("43") ? `` : (stryCov_9fa48("43"), `Error loading GEE layer '${name}'`), err);
            return stryMutAct_9fa48("44") ? [] : (stryCov_9fa48("44"), [name, null]);
          }
        }
      }
    }, stryMutAct_9fa48("45") ? ["Stryker was here"] : (stryCov_9fa48("45"), []));
    const reload = useCallback(async () => {
      if (stryMutAct_9fa48("46")) {
        {}
      } else {
        stryCov_9fa48("46");
        setLoading(stryMutAct_9fa48("47") ? false : (stryCov_9fa48("47"), true));
        setError(null);
        try {
          if (stryMutAct_9fa48("48")) {
            {}
          } else {
            stryCov_9fa48("48");
            const results = await Promise.all(layerNames.map(loadLayer));
            const newLayers: GEELayersMap = {};
            let loadedCount = 0;
            for (const [name, data] of results) {
              if (stryMutAct_9fa48("49")) {
                {}
              } else {
                stryCov_9fa48("49");
                if (stryMutAct_9fa48("51") ? false : stryMutAct_9fa48("50") ? true : (stryCov_9fa48("50", "51"), data)) {
                  if (stryMutAct_9fa48("52")) {
                    {}
                  } else {
                    stryCov_9fa48("52");
                    newLayers[name] = data;
                    stryMutAct_9fa48("53") ? loadedCount-- : (stryCov_9fa48("53"), loadedCount++);
                  }
                }
              }
            }
            setLayers(newLayers);

            // Set error if no layers loaded
            if (stryMutAct_9fa48("56") ? loadedCount === 0 || layerNames.length > 0 : stryMutAct_9fa48("55") ? false : stryMutAct_9fa48("54") ? true : (stryCov_9fa48("54", "55", "56"), (stryMutAct_9fa48("58") ? loadedCount !== 0 : stryMutAct_9fa48("57") ? true : (stryCov_9fa48("57", "58"), loadedCount === 0)) && (stryMutAct_9fa48("61") ? layerNames.length <= 0 : stryMutAct_9fa48("60") ? layerNames.length >= 0 : stryMutAct_9fa48("59") ? true : (stryCov_9fa48("59", "60", "61"), layerNames.length > 0)))) {
              if (stryMutAct_9fa48("62")) {
                {}
              } else {
                stryCov_9fa48("62");
                setError(stryMutAct_9fa48("63") ? "" : (stryCov_9fa48("63"), 'No se pudieron cargar las capas del mapa'));
              }
            }
          }
        } catch (err) {
          if (stryMutAct_9fa48("64")) {
            {}
          } else {
            stryCov_9fa48("64");
            setError(stryMutAct_9fa48("65") ? "" : (stryCov_9fa48("65"), 'Error al cargar capas del mapa'));
            logger.error(stryMutAct_9fa48("66") ? "" : (stryCov_9fa48("66"), 'Error loading GEE layers'), err);
          }
        } finally {
          if (stryMutAct_9fa48("67")) {
            {}
          } else {
            stryCov_9fa48("67");
            setLoading(stryMutAct_9fa48("68") ? true : (stryCov_9fa48("68"), false));
          }
        }
      }
    }, stryMutAct_9fa48("69") ? [] : (stryCov_9fa48("69"), [layerNames, loadLayer]));
    useEffect(() => {
      if (stryMutAct_9fa48("70")) {
        {}
      } else {
        stryCov_9fa48("70");
        if (stryMutAct_9fa48("72") ? false : stryMutAct_9fa48("71") ? true : (stryCov_9fa48("71", "72"), enabled)) {
          if (stryMutAct_9fa48("73")) {
            {}
          } else {
            stryCov_9fa48("73");
            reload();
          }
        } else {
          if (stryMutAct_9fa48("74")) {
            {}
          } else {
            stryCov_9fa48("74");
            setLoading(stryMutAct_9fa48("75") ? true : (stryCov_9fa48("75"), false));
          }
        }
      }
    }, stryMutAct_9fa48("76") ? [] : (stryCov_9fa48("76"), [enabled, reload]));

    // Convert layers map to array format
    const layersArray: GEELayerData[] = stryMutAct_9fa48("77") ? Object.entries(layers).map(([name, data]) => ({
      name: name as GEELayerName,
      data: data as FeatureCollection
    })) : (stryCov_9fa48("77"), Object.entries(layers).filter(stryMutAct_9fa48("78") ? () => undefined : (stryCov_9fa48("78"), ([, data]) => stryMutAct_9fa48("81") ? data === undefined : stryMutAct_9fa48("80") ? false : stryMutAct_9fa48("79") ? true : (stryCov_9fa48("79", "80", "81"), data !== undefined))).map(stryMutAct_9fa48("82") ? () => undefined : (stryCov_9fa48("82"), ([name, data]) => stryMutAct_9fa48("83") ? {} : (stryCov_9fa48("83"), {
      name: name as GEELayerName,
      data: data as FeatureCollection
    }))));
    return stryMutAct_9fa48("84") ? {} : (stryCov_9fa48("84"), {
      layers,
      layersArray,
      loading,
      error,
      reload
    });
  }
}
export default useGEELayers;