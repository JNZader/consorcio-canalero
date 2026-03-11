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
  if (stryMutAct_9fa48("416")) {
    {}
  } else {
    stryCov_9fa48("416");
    const [status, setStatus] = useState<JobStatus | 'IDLE'>(stryMutAct_9fa48("417") ? "" : (stryCov_9fa48("417"), 'IDLE'));
    const [result, setResult] = useState<T | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(stryMutAct_9fa48("418") ? true : (stryCov_9fa48("418"), false));
    const checkStatus = useCallback(async () => {
      if (stryMutAct_9fa48("419")) {
        {}
      } else {
        stryCov_9fa48("419");
        if (stryMutAct_9fa48("422") ? false : stryMutAct_9fa48("421") ? true : stryMutAct_9fa48("420") ? jobId : (stryCov_9fa48("420", "421", "422"), !jobId)) return;
        try {
          if (stryMutAct_9fa48("423")) {
            {}
          } else {
            stryCov_9fa48("423");
            const data = await apiFetch<JobResponse<T>>(stryMutAct_9fa48("424") ? `` : (stryCov_9fa48("424"), `/jobs/${jobId}`));
            setStatus(data.status);
            if (stryMutAct_9fa48("427") ? data.status === 'SUCCESS' || data.result : stryMutAct_9fa48("426") ? false : stryMutAct_9fa48("425") ? true : (stryCov_9fa48("425", "426", "427"), (stryMutAct_9fa48("429") ? data.status !== 'SUCCESS' : stryMutAct_9fa48("428") ? true : (stryCov_9fa48("428", "429"), data.status === (stryMutAct_9fa48("430") ? "" : (stryCov_9fa48("430"), 'SUCCESS')))) && data.result)) {
              if (stryMutAct_9fa48("431")) {
                {}
              } else {
                stryCov_9fa48("431");
                setResult(data.result);
                setIsLoading(stryMutAct_9fa48("432") ? true : (stryCov_9fa48("432"), false));
                if (stryMutAct_9fa48("434") ? false : stryMutAct_9fa48("433") ? true : (stryCov_9fa48("433", "434"), onCompleted)) onCompleted(data.result);
              }
            } else if (stryMutAct_9fa48("437") ? data.status !== 'FAILURE' : stryMutAct_9fa48("436") ? false : stryMutAct_9fa48("435") ? true : (stryCov_9fa48("435", "436", "437"), data.status === (stryMutAct_9fa48("438") ? "" : (stryCov_9fa48("438"), 'FAILURE')))) {
              if (stryMutAct_9fa48("439")) {
                {}
              } else {
                stryCov_9fa48("439");
                setError(stryMutAct_9fa48("442") ? data.error && 'Job failed' : stryMutAct_9fa48("441") ? false : stryMutAct_9fa48("440") ? true : (stryCov_9fa48("440", "441", "442"), data.error || (stryMutAct_9fa48("443") ? "" : (stryCov_9fa48("443"), 'Job failed'))));
                setIsLoading(stryMutAct_9fa48("444") ? true : (stryCov_9fa48("444"), false));
              }
            }
          }
        } catch (err) {
          if (stryMutAct_9fa48("445")) {
            {}
          } else {
            stryCov_9fa48("445");
            setError(err instanceof Error ? err.message : stryMutAct_9fa48("446") ? "" : (stryCov_9fa48("446"), 'Error checking job status'));
            setIsLoading(stryMutAct_9fa48("447") ? true : (stryCov_9fa48("447"), false));
          }
        }
      }
    }, stryMutAct_9fa48("448") ? [] : (stryCov_9fa48("448"), [jobId, onCompleted]));
    useEffect(() => {
      if (stryMutAct_9fa48("449")) {
        {}
      } else {
        stryCov_9fa48("449");
        if (stryMutAct_9fa48("452") ? false : stryMutAct_9fa48("451") ? true : stryMutAct_9fa48("450") ? jobId : (stryCov_9fa48("450", "451", "452"), !jobId)) {
          if (stryMutAct_9fa48("453")) {
            {}
          } else {
            stryCov_9fa48("453");
            setStatus(stryMutAct_9fa48("454") ? "" : (stryCov_9fa48("454"), 'IDLE'));
            setResult(null);
            setError(null);
            setIsLoading(stryMutAct_9fa48("455") ? true : (stryCov_9fa48("455"), false));
            return;
          }
        }
        setIsLoading(stryMutAct_9fa48("456") ? false : (stryCov_9fa48("456"), true));
        setStatus(stryMutAct_9fa48("457") ? "" : (stryCov_9fa48("457"), 'PENDING'));

        // Start polling
        const interval = setInterval(() => {
          if (stryMutAct_9fa48("458")) {
            {}
          } else {
            stryCov_9fa48("458");
            if (stryMutAct_9fa48("461") ? status !== 'SUCCESS' || status !== 'FAILURE' : stryMutAct_9fa48("460") ? false : stryMutAct_9fa48("459") ? true : (stryCov_9fa48("459", "460", "461"), (stryMutAct_9fa48("463") ? status === 'SUCCESS' : stryMutAct_9fa48("462") ? true : (stryCov_9fa48("462", "463"), status !== (stryMutAct_9fa48("464") ? "" : (stryCov_9fa48("464"), 'SUCCESS')))) && (stryMutAct_9fa48("466") ? status === 'FAILURE' : stryMutAct_9fa48("465") ? true : (stryCov_9fa48("465", "466"), status !== (stryMutAct_9fa48("467") ? "" : (stryCov_9fa48("467"), 'FAILURE')))))) {
              if (stryMutAct_9fa48("468")) {
                {}
              } else {
                stryCov_9fa48("468");
                checkStatus();
              }
            } else {
              if (stryMutAct_9fa48("469")) {
                {}
              } else {
                stryCov_9fa48("469");
                clearInterval(interval);
              }
            }
          }
        }, 2000); // Check every 2 seconds

        return stryMutAct_9fa48("470") ? () => undefined : (stryCov_9fa48("470"), () => clearInterval(interval));
      }
    }, stryMutAct_9fa48("471") ? [] : (stryCov_9fa48("471"), [jobId, status, checkStatus]));
    return stryMutAct_9fa48("472") ? {} : (stryCov_9fa48("472"), {
      status,
      result,
      error,
      isLoading
    });
  }
}