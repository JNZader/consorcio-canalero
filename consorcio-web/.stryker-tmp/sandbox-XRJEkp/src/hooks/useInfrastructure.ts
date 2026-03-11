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
import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../lib/api';
import type { FeatureCollection } from 'geojson';
export interface InfrastructureAsset {
  id: string;
  nombre: string;
  tipo: 'canal' | 'alcantarilla' | 'puente' | 'otro';
  descripcion: string;
  latitud: number;
  longitud: number;
  cuenca: string;
  estado_actual: 'bueno' | 'regular' | 'malo' | 'critico';
  ultima_inspeccion: string;
}
export function useInfrastructure() {
  if (stryMutAct_9fa48("390")) {
    {}
  } else {
    stryCov_9fa48("390");
    const [assets, setAssets] = useState<InfrastructureAsset[]>(stryMutAct_9fa48("391") ? ["Stryker was here"] : (stryCov_9fa48("391"), []));
    const [intersections, setIntersections] = useState<FeatureCollection | null>(null);
    const [loading, setLoading] = useState(stryMutAct_9fa48("392") ? true : (stryCov_9fa48("392"), false));
    const [error, setError] = useState<string | null>(null);
    const fetchInfrastructure = useCallback(async () => {
      if (stryMutAct_9fa48("393")) {
        {}
      } else {
        stryCov_9fa48("393");
        setLoading(stryMutAct_9fa48("394") ? false : (stryCov_9fa48("394"), true));
        try {
          if (stryMutAct_9fa48("395")) {
            {}
          } else {
            stryCov_9fa48("395");
            const [assetsData, intersectionsData] = await Promise.all(stryMutAct_9fa48("396") ? [] : (stryCov_9fa48("396"), [apiFetch<InfrastructureAsset[]>(stryMutAct_9fa48("397") ? "" : (stryCov_9fa48("397"), '/infrastructure/assets')), apiFetch<FeatureCollection>(stryMutAct_9fa48("398") ? "" : (stryCov_9fa48("398"), '/infrastructure/potential-intersections'))]));
            setAssets(assetsData);
            setIntersections(intersectionsData);
          }
        } catch (err) {
          if (stryMutAct_9fa48("399")) {
            {}
          } else {
            stryCov_9fa48("399");
            setError(err instanceof Error ? err.message : stryMutAct_9fa48("400") ? "" : (stryCov_9fa48("400"), 'Error cargando infraestructura'));
          }
        } finally {
          if (stryMutAct_9fa48("401")) {
            {}
          } else {
            stryCov_9fa48("401");
            setLoading(stryMutAct_9fa48("402") ? true : (stryCov_9fa48("402"), false));
          }
        }
      }
    }, stryMutAct_9fa48("403") ? ["Stryker was here"] : (stryCov_9fa48("403"), []));
    useEffect(() => {
      if (stryMutAct_9fa48("404")) {
        {}
      } else {
        stryCov_9fa48("404");
        fetchInfrastructure();
      }
    }, stryMutAct_9fa48("405") ? [] : (stryCov_9fa48("405"), [fetchInfrastructure]));
    const createAsset = async (asset: Omit<InfrastructureAsset, 'id' | 'ultima_inspeccion'>) => {
      if (stryMutAct_9fa48("406")) {
        {}
      } else {
        stryCov_9fa48("406");
        try {
          if (stryMutAct_9fa48("407")) {
            {}
          } else {
            stryCov_9fa48("407");
            const newAsset = await apiFetch<InfrastructureAsset>(stryMutAct_9fa48("408") ? "" : (stryCov_9fa48("408"), '/infrastructure/assets'), stryMutAct_9fa48("409") ? {} : (stryCov_9fa48("409"), {
              method: stryMutAct_9fa48("410") ? "" : (stryCov_9fa48("410"), 'POST'),
              body: JSON.stringify(asset)
            }));
            setAssets(stryMutAct_9fa48("411") ? () => undefined : (stryCov_9fa48("411"), prev => stryMutAct_9fa48("412") ? [] : (stryCov_9fa48("412"), [...prev, newAsset])));
            return newAsset;
          }
        } catch (err) {
          if (stryMutAct_9fa48("413")) {
            {}
          } else {
            stryCov_9fa48("413");
            throw err instanceof Error ? err : new Error(stryMutAct_9fa48("414") ? "" : (stryCov_9fa48("414"), 'Error al crear activo'));
          }
        }
      }
    };
    return stryMutAct_9fa48("415") ? {} : (stryCov_9fa48("415"), {
      assets,
      intersections,
      loading,
      error,
      refresh: fetchInfrastructure,
      createAsset
    });
  }
}