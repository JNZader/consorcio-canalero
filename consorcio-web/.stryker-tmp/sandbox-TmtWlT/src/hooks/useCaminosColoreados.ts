/**
 * Hook para cargar caminos con colores por consorcio caminero.
 * Cada camino tiene un color asignado segun su consorcio para visualizacion diferenciada.
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

// Tipo para la informacion de un consorcio
export interface ConsorcioInfo {
  nombre: string;
  codigo: string;
  color: string;
  tramos: number;
  longitud_km: number;
}

// Tipo para la respuesta del endpoint
export interface CaminosColoreados {
  type: 'FeatureCollection';
  features: FeatureCollection['features'];
  metadata: {
    total_tramos: number;
    total_consorcios: number;
    total_km: number;
  };
  consorcios: ConsorcioInfo[];
}
interface UseCaminosColoreados {
  /** GeoJSON de caminos con propiedad 'color' */
  caminos: FeatureCollection | null;
  /** Lista de consorcios con colores y estadisticas */
  consorcios: ConsorcioInfo[];
  /** Metadata con totales */
  metadata: CaminosColoreados['metadata'] | null;
  /** Estado de carga */
  loading: boolean;
  /** Error si hubo alguno */
  error: string | null;
  /** Recargar datos */
  reload: () => Promise<void>;
}

/**
 * Hook para cargar la red vial con colores diferenciados por consorcio caminero.
 *
 * @example
 * ```tsx
 * const { caminos, consorcios, loading } = useCaminosColoreados();
 *
 * // Usar en GeoJSON con style dinamico
 * <GeoJSON
 *   data={caminos}
 *   style={(feature) => ({
 *     color: feature?.properties?.color || '#888',
 *     weight: 2,
 *   })}
 * />
 * ```
 */
export function useCaminosColoreados(): UseCaminosColoreados {
  if (stryMutAct_9fa48("72")) {
    {}
  } else {
    stryCov_9fa48("72");
    const [caminos, setCaminos] = useState<FeatureCollection | null>(null);
    const [consorcios, setConsorcios] = useState<ConsorcioInfo[]>(stryMutAct_9fa48("73") ? ["Stryker was here"] : (stryCov_9fa48("73"), []));
    const [metadata, setMetadata] = useState<CaminosColoreados['metadata'] | null>(null);
    const [loading, setLoading] = useState(stryMutAct_9fa48("74") ? false : (stryCov_9fa48("74"), true));
    const [error, setError] = useState<string | null>(null);
    const reload = useCallback(async () => {
      if (stryMutAct_9fa48("75")) {
        {}
      } else {
        stryCov_9fa48("75");
        setLoading(stryMutAct_9fa48("76") ? false : (stryCov_9fa48("76"), true));
        setError(null);
        try {
          if (stryMutAct_9fa48("77")) {
            {}
          } else {
            stryCov_9fa48("77");
            const response = await fetch(stryMutAct_9fa48("78") ? `` : (stryCov_9fa48("78"), `${API_URL}/api/v1/gee/layers/caminos/coloreados`));
            if (stryMutAct_9fa48("81") ? false : stryMutAct_9fa48("80") ? true : stryMutAct_9fa48("79") ? response.ok : (stryCov_9fa48("79", "80", "81"), !response.ok)) {
              if (stryMutAct_9fa48("82")) {
                {}
              } else {
                stryCov_9fa48("82");
                throw new Error(stryMutAct_9fa48("83") ? `` : (stryCov_9fa48("83"), `HTTP ${response.status}`));
              }
            }
            const data: CaminosColoreados = await response.json();

            // Extraer el FeatureCollection
            const featureCollection: FeatureCollection = stryMutAct_9fa48("84") ? {} : (stryCov_9fa48("84"), {
              type: stryMutAct_9fa48("85") ? "" : (stryCov_9fa48("85"), 'FeatureCollection'),
              features: data.features
            });
            setCaminos(featureCollection);
            setConsorcios(data.consorcios);
            setMetadata(data.metadata);
          }
        } catch (err) {
          if (stryMutAct_9fa48("86")) {
            {}
          } else {
            stryCov_9fa48("86");
            const message = err instanceof Error ? err.message : stryMutAct_9fa48("87") ? "" : (stryCov_9fa48("87"), 'Error desconocido');
            setError(stryMutAct_9fa48("88") ? `` : (stryCov_9fa48("88"), `No se pudieron cargar los caminos: ${message}`));
            logger.error(stryMutAct_9fa48("89") ? "" : (stryCov_9fa48("89"), 'Error loading colored roads'), err);
          }
        } finally {
          if (stryMutAct_9fa48("90")) {
            {}
          } else {
            stryCov_9fa48("90");
            setLoading(stryMutAct_9fa48("91") ? true : (stryCov_9fa48("91"), false));
          }
        }
      }
    }, stryMutAct_9fa48("92") ? ["Stryker was here"] : (stryCov_9fa48("92"), []));
    useEffect(() => {
      if (stryMutAct_9fa48("93")) {
        {}
      } else {
        stryCov_9fa48("93");
        reload();
      }
    }, stryMutAct_9fa48("94") ? [] : (stryCov_9fa48("94"), [reload]));
    return stryMutAct_9fa48("95") ? {} : (stryCov_9fa48("95"), {
      caminos,
      consorcios,
      metadata,
      loading,
      error,
      reload
    });
  }
}
export default useCaminosColoreados;