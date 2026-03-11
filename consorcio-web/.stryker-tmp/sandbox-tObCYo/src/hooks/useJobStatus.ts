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
export type JobStatus = 'PENDING' | 'STARTED' | 'SUCCESS' | 'FAILURE' | 'RETRY' | 'REVOKED';
interface JobResponse<T> {
  job_id: string;
  status: JobStatus;
  result?: T;
  error?: string;
}

/**
 * Hook to track the status of a background job with automatic polling.
 */
export function useJobStatus<T>(jobId: string | null, onCompleted?: (result: T) => void) {
  if (stryMutAct_9fa48("0")) {
    {}
  } else {
    stryCov_9fa48("0");
    const [status, setStatus] = useState<JobStatus | 'IDLE'>(stryMutAct_9fa48("1") ? "" : (stryCov_9fa48("1"), 'IDLE'));
    const [result, setResult] = useState<T | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(stryMutAct_9fa48("2") ? true : (stryCov_9fa48("2"), false));
    const checkStatus = useCallback(async () => {
      if (stryMutAct_9fa48("3")) {
        {}
      } else {
        stryCov_9fa48("3");
        if (stryMutAct_9fa48("6") ? false : stryMutAct_9fa48("5") ? true : stryMutAct_9fa48("4") ? jobId : (stryCov_9fa48("4", "5", "6"), !jobId)) return;
        try {
          if (stryMutAct_9fa48("7")) {
            {}
          } else {
            stryCov_9fa48("7");
            const data = await apiFetch<JobResponse<T>>(stryMutAct_9fa48("8") ? `` : (stryCov_9fa48("8"), `/jobs/${jobId}`));
            setStatus(data.status);
            if (stryMutAct_9fa48("11") ? data.status === 'SUCCESS' || data.result : stryMutAct_9fa48("10") ? false : stryMutAct_9fa48("9") ? true : (stryCov_9fa48("9", "10", "11"), (stryMutAct_9fa48("13") ? data.status !== 'SUCCESS' : stryMutAct_9fa48("12") ? true : (stryCov_9fa48("12", "13"), data.status === (stryMutAct_9fa48("14") ? "" : (stryCov_9fa48("14"), 'SUCCESS')))) && data.result)) {
              if (stryMutAct_9fa48("15")) {
                {}
              } else {
                stryCov_9fa48("15");
                setResult(data.result);
                setIsLoading(stryMutAct_9fa48("16") ? true : (stryCov_9fa48("16"), false));
                if (stryMutAct_9fa48("18") ? false : stryMutAct_9fa48("17") ? true : (stryCov_9fa48("17", "18"), onCompleted)) onCompleted(data.result);
              }
            } else if (stryMutAct_9fa48("21") ? data.status !== 'FAILURE' : stryMutAct_9fa48("20") ? false : stryMutAct_9fa48("19") ? true : (stryCov_9fa48("19", "20", "21"), data.status === (stryMutAct_9fa48("22") ? "" : (stryCov_9fa48("22"), 'FAILURE')))) {
              if (stryMutAct_9fa48("23")) {
                {}
              } else {
                stryCov_9fa48("23");
                setError(stryMutAct_9fa48("26") ? data.error && 'Job failed' : stryMutAct_9fa48("25") ? false : stryMutAct_9fa48("24") ? true : (stryCov_9fa48("24", "25", "26"), data.error || (stryMutAct_9fa48("27") ? "" : (stryCov_9fa48("27"), 'Job failed'))));
                setIsLoading(stryMutAct_9fa48("28") ? true : (stryCov_9fa48("28"), false));
              }
            }
          }
        } catch (err) {
          if (stryMutAct_9fa48("29")) {
            {}
          } else {
            stryCov_9fa48("29");
            setError(err instanceof Error ? err.message : stryMutAct_9fa48("30") ? "" : (stryCov_9fa48("30"), 'Error checking job status'));
            setIsLoading(stryMutAct_9fa48("31") ? true : (stryCov_9fa48("31"), false));
          }
        }
      }
    }, stryMutAct_9fa48("32") ? [] : (stryCov_9fa48("32"), [jobId, onCompleted]));
    useEffect(() => {
      if (stryMutAct_9fa48("33")) {
        {}
      } else {
        stryCov_9fa48("33");
        if (stryMutAct_9fa48("36") ? false : stryMutAct_9fa48("35") ? true : stryMutAct_9fa48("34") ? jobId : (stryCov_9fa48("34", "35", "36"), !jobId)) {
          if (stryMutAct_9fa48("37")) {
            {}
          } else {
            stryCov_9fa48("37");
            setStatus(stryMutAct_9fa48("38") ? "" : (stryCov_9fa48("38"), 'IDLE'));
            setResult(null);
            setError(null);
            setIsLoading(stryMutAct_9fa48("39") ? true : (stryCov_9fa48("39"), false));
            return;
          }
        }
        setIsLoading(stryMutAct_9fa48("40") ? false : (stryCov_9fa48("40"), true));
        setStatus(stryMutAct_9fa48("41") ? "" : (stryCov_9fa48("41"), 'PENDING'));

        // Start polling
        const interval = setInterval(() => {
          if (stryMutAct_9fa48("42")) {
            {}
          } else {
            stryCov_9fa48("42");
            if (stryMutAct_9fa48("45") ? status !== 'SUCCESS' || status !== 'FAILURE' : stryMutAct_9fa48("44") ? false : stryMutAct_9fa48("43") ? true : (stryCov_9fa48("43", "44", "45"), (stryMutAct_9fa48("47") ? status === 'SUCCESS' : stryMutAct_9fa48("46") ? true : (stryCov_9fa48("46", "47"), status !== (stryMutAct_9fa48("48") ? "" : (stryCov_9fa48("48"), 'SUCCESS')))) && (stryMutAct_9fa48("50") ? status === 'FAILURE' : stryMutAct_9fa48("49") ? true : (stryCov_9fa48("49", "50"), status !== (stryMutAct_9fa48("51") ? "" : (stryCov_9fa48("51"), 'FAILURE')))))) {
              if (stryMutAct_9fa48("52")) {
                {}
              } else {
                stryCov_9fa48("52");
                checkStatus();
              }
            } else {
              if (stryMutAct_9fa48("53")) {
                {}
              } else {
                stryCov_9fa48("53");
                clearInterval(interval);
              }
            }
          }
        }, 2000); // Check every 2 seconds

        return stryMutAct_9fa48("54") ? () => undefined : (stryCov_9fa48("54"), () => clearInterval(interval));
      }
    }, stryMutAct_9fa48("55") ? [] : (stryCov_9fa48("55"), [jobId, status, checkStatus]));
    return stryMutAct_9fa48("56") ? {} : (stryCov_9fa48("56"), {
      status,
      result,
      error,
      isLoading
    });
  }
}