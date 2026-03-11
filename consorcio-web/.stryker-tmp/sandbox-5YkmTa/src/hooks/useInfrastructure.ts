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
  if (stryMutAct_9fa48("0")) {
    {}
  } else {
    stryCov_9fa48("0");
    const [assets, setAssets] = useState<InfrastructureAsset[]>(stryMutAct_9fa48("1") ? ["Stryker was here"] : (stryCov_9fa48("1"), []));
    const [intersections, setIntersections] = useState<FeatureCollection | null>(null);
    const [loading, setLoading] = useState(stryMutAct_9fa48("2") ? true : (stryCov_9fa48("2"), false));
    const [error, setError] = useState<string | null>(null);
    const fetchInfrastructure = useCallback(async () => {
      if (stryMutAct_9fa48("3")) {
        {}
      } else {
        stryCov_9fa48("3");
        setLoading(stryMutAct_9fa48("4") ? false : (stryCov_9fa48("4"), true));
        try {
          if (stryMutAct_9fa48("5")) {
            {}
          } else {
            stryCov_9fa48("5");
            const [assetsData, intersectionsData] = await Promise.all(stryMutAct_9fa48("6") ? [] : (stryCov_9fa48("6"), [apiFetch<InfrastructureAsset[]>(stryMutAct_9fa48("7") ? "" : (stryCov_9fa48("7"), '/infrastructure/assets')), apiFetch<FeatureCollection>(stryMutAct_9fa48("8") ? "" : (stryCov_9fa48("8"), '/infrastructure/potential-intersections'))]));
            setAssets(assetsData);
            setIntersections(intersectionsData);
          }
        } catch (err) {
          if (stryMutAct_9fa48("9")) {
            {}
          } else {
            stryCov_9fa48("9");
            setError(err instanceof Error ? err.message : stryMutAct_9fa48("10") ? "" : (stryCov_9fa48("10"), 'Error cargando infraestructura'));
          }
        } finally {
          if (stryMutAct_9fa48("11")) {
            {}
          } else {
            stryCov_9fa48("11");
            setLoading(stryMutAct_9fa48("12") ? true : (stryCov_9fa48("12"), false));
          }
        }
      }
    }, stryMutAct_9fa48("13") ? ["Stryker was here"] : (stryCov_9fa48("13"), []));
    useEffect(() => {
      if (stryMutAct_9fa48("14")) {
        {}
      } else {
        stryCov_9fa48("14");
        fetchInfrastructure();
      }
    }, stryMutAct_9fa48("15") ? [] : (stryCov_9fa48("15"), [fetchInfrastructure]));
    const createAsset = async (asset: Omit<InfrastructureAsset, 'id' | 'ultima_inspeccion'>) => {
      if (stryMutAct_9fa48("16")) {
        {}
      } else {
        stryCov_9fa48("16");
        try {
          if (stryMutAct_9fa48("17")) {
            {}
          } else {
            stryCov_9fa48("17");
            const newAsset = await apiFetch<InfrastructureAsset>(stryMutAct_9fa48("18") ? "" : (stryCov_9fa48("18"), '/infrastructure/assets'), stryMutAct_9fa48("19") ? {} : (stryCov_9fa48("19"), {
              method: stryMutAct_9fa48("20") ? "" : (stryCov_9fa48("20"), 'POST'),
              body: JSON.stringify(asset)
            }));
            setAssets(stryMutAct_9fa48("21") ? () => undefined : (stryCov_9fa48("21"), prev => stryMutAct_9fa48("22") ? [] : (stryCov_9fa48("22"), [...prev, newAsset])));
            return newAsset;
          }
        } catch (err) {
          if (stryMutAct_9fa48("23")) {
            {}
          } else {
            stryCov_9fa48("23");
            throw err instanceof Error ? err : new Error(stryMutAct_9fa48("24") ? "" : (stryCov_9fa48("24"), 'Error al crear activo'));
          }
        }
      }
    };
    return stryMutAct_9fa48("25") ? {} : (stryCov_9fa48("25"), {
      assets,
      intersections,
      loading,
      error,
      refresh: fetchInfrastructure,
      createAsset
    });
  }
}