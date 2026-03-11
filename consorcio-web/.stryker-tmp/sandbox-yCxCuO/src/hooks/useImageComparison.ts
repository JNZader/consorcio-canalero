/**
 * Hook for managing side-by-side image comparison.
 * Allows selecting two satellite images to compare on the map.
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
import { useCallback, useEffect, useState } from 'react';
import { isValidImageComparison } from '../lib/typeGuards';
import type { SelectedImage } from './useSelectedImage';
const STORAGE_KEY = stryMutAct_9fa48("290") ? "" : (stryCov_9fa48("290"), 'consorcio_image_comparison');
export interface ImageComparison {
  left: SelectedImage;
  right: SelectedImage;
  enabled: boolean;
}

/**
 * Hook to manage image comparison state.
 * Stores left and right images for side-by-side comparison.
 */
export function useImageComparison() {
  if (stryMutAct_9fa48("291")) {
    {}
  } else {
    stryCov_9fa48("291");
    const [comparison, setComparisonState] = useState<ImageComparison | null>(null);
    const [isLoading, setIsLoading] = useState(stryMutAct_9fa48("292") ? false : (stryCov_9fa48("292"), true));

    // Load from localStorage on mount with validation
    useEffect(() => {
      if (stryMutAct_9fa48("293")) {
        {}
      } else {
        stryCov_9fa48("293");
        try {
          if (stryMutAct_9fa48("294")) {
            {}
          } else {
            stryCov_9fa48("294");
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stryMutAct_9fa48("296") ? false : stryMutAct_9fa48("295") ? true : (stryCov_9fa48("295", "296"), stored)) {
              if (stryMutAct_9fa48("297")) {
                {}
              } else {
                stryCov_9fa48("297");
                const parsed = JSON.parse(stored);
                // Validate data structure before using
                if (stryMutAct_9fa48("299") ? false : stryMutAct_9fa48("298") ? true : (stryCov_9fa48("298", "299"), isValidImageComparison(parsed))) {
                  if (stryMutAct_9fa48("300")) {
                    {}
                  } else {
                    stryCov_9fa48("300");
                    setComparisonState(parsed as ImageComparison);
                  }
                } else {
                  if (stryMutAct_9fa48("301")) {
                    {}
                  } else {
                    stryCov_9fa48("301");
                    // Invalid data, clean up
                    localStorage.removeItem(STORAGE_KEY);
                  }
                }
              }
            }
          }
        } catch {
          if (stryMutAct_9fa48("302")) {
            {}
          } else {
            stryCov_9fa48("302");
            localStorage.removeItem(STORAGE_KEY);
          }
        } finally {
          if (stryMutAct_9fa48("303")) {
            {}
          } else {
            stryCov_9fa48("303");
            setIsLoading(stryMutAct_9fa48("304") ? true : (stryCov_9fa48("304"), false));
          }
        }
      }
    }, stryMutAct_9fa48("305") ? ["Stryker was here"] : (stryCov_9fa48("305"), []));

    // Set left image
    const setLeftImage = useCallback((image: SelectedImage) => {
      if (stryMutAct_9fa48("306")) {
        {}
      } else {
        stryCov_9fa48("306");
        setComparisonState(prev => {
          if (stryMutAct_9fa48("307")) {
            {}
          } else {
            stryCov_9fa48("307");
            const newComparison: ImageComparison = stryMutAct_9fa48("308") ? {} : (stryCov_9fa48("308"), {
              left: image,
              right: stryMutAct_9fa48("311") ? prev?.right && image : stryMutAct_9fa48("310") ? false : stryMutAct_9fa48("309") ? true : (stryCov_9fa48("309", "310", "311"), (stryMutAct_9fa48("312") ? prev.right : (stryCov_9fa48("312"), prev?.right)) || image),
              enabled: stryMutAct_9fa48("313") ? prev?.enabled && true : (stryCov_9fa48("313"), (stryMutAct_9fa48("314") ? prev.enabled : (stryCov_9fa48("314"), prev?.enabled)) ?? (stryMutAct_9fa48("315") ? false : (stryCov_9fa48("315"), true)))
            });
            localStorage.setItem(STORAGE_KEY, JSON.stringify(newComparison));
            window.dispatchEvent(new CustomEvent(stryMutAct_9fa48("316") ? "" : (stryCov_9fa48("316"), 'imageComparisonChange'), stryMutAct_9fa48("317") ? {} : (stryCov_9fa48("317"), {
              detail: newComparison
            })));
            return newComparison;
          }
        });
      }
    }, stryMutAct_9fa48("318") ? ["Stryker was here"] : (stryCov_9fa48("318"), []));

    // Set right image
    const setRightImage = useCallback((image: SelectedImage) => {
      if (stryMutAct_9fa48("319")) {
        {}
      } else {
        stryCov_9fa48("319");
        setComparisonState(prev => {
          if (stryMutAct_9fa48("320")) {
            {}
          } else {
            stryCov_9fa48("320");
            const newComparison: ImageComparison = stryMutAct_9fa48("321") ? {} : (stryCov_9fa48("321"), {
              left: stryMutAct_9fa48("324") ? prev?.left && image : stryMutAct_9fa48("323") ? false : stryMutAct_9fa48("322") ? true : (stryCov_9fa48("322", "323", "324"), (stryMutAct_9fa48("325") ? prev.left : (stryCov_9fa48("325"), prev?.left)) || image),
              right: image,
              enabled: stryMutAct_9fa48("326") ? prev?.enabled && true : (stryCov_9fa48("326"), (stryMutAct_9fa48("327") ? prev.enabled : (stryCov_9fa48("327"), prev?.enabled)) ?? (stryMutAct_9fa48("328") ? false : (stryCov_9fa48("328"), true)))
            });
            localStorage.setItem(STORAGE_KEY, JSON.stringify(newComparison));
            window.dispatchEvent(new CustomEvent(stryMutAct_9fa48("329") ? "" : (stryCov_9fa48("329"), 'imageComparisonChange'), stryMutAct_9fa48("330") ? {} : (stryCov_9fa48("330"), {
              detail: newComparison
            })));
            return newComparison;
          }
        });
      }
    }, stryMutAct_9fa48("331") ? ["Stryker was here"] : (stryCov_9fa48("331"), []));

    // Enable/disable comparison
    const setEnabled = useCallback((enabled: boolean) => {
      if (stryMutAct_9fa48("332")) {
        {}
      } else {
        stryCov_9fa48("332");
        setComparisonState(prev => {
          if (stryMutAct_9fa48("333")) {
            {}
          } else {
            stryCov_9fa48("333");
            if (stryMutAct_9fa48("336") ? false : stryMutAct_9fa48("335") ? true : stryMutAct_9fa48("334") ? prev : (stryCov_9fa48("334", "335", "336"), !prev)) return null;
            const newComparison = stryMutAct_9fa48("337") ? {} : (stryCov_9fa48("337"), {
              ...prev,
              enabled
            });
            localStorage.setItem(STORAGE_KEY, JSON.stringify(newComparison));
            window.dispatchEvent(new CustomEvent(stryMutAct_9fa48("338") ? "" : (stryCov_9fa48("338"), 'imageComparisonChange'), stryMutAct_9fa48("339") ? {} : (stryCov_9fa48("339"), {
              detail: newComparison
            })));
            return newComparison;
          }
        });
      }
    }, stryMutAct_9fa48("340") ? ["Stryker was here"] : (stryCov_9fa48("340"), []));

    // Clear comparison
    const clearComparison = useCallback(() => {
      if (stryMutAct_9fa48("341")) {
        {}
      } else {
        stryCov_9fa48("341");
        localStorage.removeItem(STORAGE_KEY);
        setComparisonState(null);
        window.dispatchEvent(new CustomEvent(stryMutAct_9fa48("342") ? "" : (stryCov_9fa48("342"), 'imageComparisonChange'), stryMutAct_9fa48("343") ? {} : (stryCov_9fa48("343"), {
          detail: null
        })));
      }
    }, stryMutAct_9fa48("344") ? ["Stryker was here"] : (stryCov_9fa48("344"), []));

    // Check if both images are set
    const isReady = stryMutAct_9fa48("347") ? comparison?.left || comparison?.right : stryMutAct_9fa48("346") ? false : stryMutAct_9fa48("345") ? true : (stryCov_9fa48("345", "346", "347"), (stryMutAct_9fa48("348") ? comparison.left : (stryCov_9fa48("348"), comparison?.left)) && (stryMutAct_9fa48("349") ? comparison.right : (stryCov_9fa48("349"), comparison?.right)));
    return stryMutAct_9fa48("350") ? {} : (stryCov_9fa48("350"), {
      comparison,
      setLeftImage,
      setRightImage,
      setEnabled,
      clearComparison,
      isReady,
      isLoading
    });
  }
}

/**
 * Hook to listen for comparison changes without ability to modify.
 * Useful for map components that just need to display the comparison.
 */
export function useImageComparisonListener() {
  if (stryMutAct_9fa48("351")) {
    {}
  } else {
    stryCov_9fa48("351");
    const [comparison, setComparison] = useState<ImageComparison | null>(null);
    useEffect(() => {
      if (stryMutAct_9fa48("352")) {
        {}
      } else {
        stryCov_9fa48("352");
        // Load initial value with validation
        try {
          if (stryMutAct_9fa48("353")) {
            {}
          } else {
            stryCov_9fa48("353");
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stryMutAct_9fa48("355") ? false : stryMutAct_9fa48("354") ? true : (stryCov_9fa48("354", "355"), stored)) {
              if (stryMutAct_9fa48("356")) {
                {}
              } else {
                stryCov_9fa48("356");
                const parsed = JSON.parse(stored);
                if (stryMutAct_9fa48("358") ? false : stryMutAct_9fa48("357") ? true : (stryCov_9fa48("357", "358"), isValidImageComparison(parsed))) {
                  if (stryMutAct_9fa48("359")) {
                    {}
                  } else {
                    stryCov_9fa48("359");
                    setComparison(parsed as ImageComparison);
                  }
                } else {
                  if (stryMutAct_9fa48("360")) {
                    {}
                  } else {
                    stryCov_9fa48("360");
                    localStorage.removeItem(STORAGE_KEY);
                  }
                }
              }
            }
          }
        } catch {
          if (stryMutAct_9fa48("361")) {
            {}
          } else {
            stryCov_9fa48("361");
            localStorage.removeItem(STORAGE_KEY);
          }
        }

        // Listen for custom events (same tab)
        const handleCustomEvent = (event: CustomEvent<ImageComparison | null>) => {
          if (stryMutAct_9fa48("362")) {
            {}
          } else {
            stryCov_9fa48("362");
            // Validate even from custom events for extra safety
            if (stryMutAct_9fa48("365") ? event.detail === null && isValidImageComparison(event.detail) : stryMutAct_9fa48("364") ? false : stryMutAct_9fa48("363") ? true : (stryCov_9fa48("363", "364", "365"), (stryMutAct_9fa48("367") ? event.detail !== null : stryMutAct_9fa48("366") ? false : (stryCov_9fa48("366", "367"), event.detail === null)) || isValidImageComparison(event.detail))) {
              if (stryMutAct_9fa48("368")) {
                {}
              } else {
                stryCov_9fa48("368");
                setComparison(event.detail as ImageComparison | null);
              }
            }
          }
        };

        // Listen for storage events (other tabs)
        const handleStorageChange = (event: StorageEvent) => {
          if (stryMutAct_9fa48("369")) {
            {}
          } else {
            stryCov_9fa48("369");
            if (stryMutAct_9fa48("372") ? event.key !== STORAGE_KEY : stryMutAct_9fa48("371") ? false : stryMutAct_9fa48("370") ? true : (stryCov_9fa48("370", "371", "372"), event.key === STORAGE_KEY)) {
              if (stryMutAct_9fa48("373")) {
                {}
              } else {
                stryCov_9fa48("373");
                if (stryMutAct_9fa48("375") ? false : stryMutAct_9fa48("374") ? true : (stryCov_9fa48("374", "375"), event.newValue)) {
                  if (stryMutAct_9fa48("376")) {
                    {}
                  } else {
                    stryCov_9fa48("376");
                    try {
                      if (stryMutAct_9fa48("377")) {
                        {}
                      } else {
                        stryCov_9fa48("377");
                        const parsed = JSON.parse(event.newValue);
                        if (stryMutAct_9fa48("379") ? false : stryMutAct_9fa48("378") ? true : (stryCov_9fa48("378", "379"), isValidImageComparison(parsed))) {
                          if (stryMutAct_9fa48("380")) {
                            {}
                          } else {
                            stryCov_9fa48("380");
                            setComparison(parsed as ImageComparison);
                          }
                        } else {
                          if (stryMutAct_9fa48("381")) {
                            {}
                          } else {
                            stryCov_9fa48("381");
                            setComparison(null);
                          }
                        }
                      }
                    } catch {
                      if (stryMutAct_9fa48("382")) {
                        {}
                      } else {
                        stryCov_9fa48("382");
                        setComparison(null);
                      }
                    }
                  }
                } else {
                  if (stryMutAct_9fa48("383")) {
                    {}
                  } else {
                    stryCov_9fa48("383");
                    setComparison(null);
                  }
                }
              }
            }
          }
        };
        window.addEventListener(stryMutAct_9fa48("384") ? "" : (stryCov_9fa48("384"), 'imageComparisonChange'), handleCustomEvent as EventListener);
        window.addEventListener(stryMutAct_9fa48("385") ? "" : (stryCov_9fa48("385"), 'storage'), handleStorageChange);
        return () => {
          if (stryMutAct_9fa48("386")) {
            {}
          } else {
            stryCov_9fa48("386");
            window.removeEventListener(stryMutAct_9fa48("387") ? "" : (stryCov_9fa48("387"), 'imageComparisonChange'), handleCustomEvent as EventListener);
            window.removeEventListener(stryMutAct_9fa48("388") ? "" : (stryCov_9fa48("388"), 'storage'), handleStorageChange);
          }
        };
      }
    }, stryMutAct_9fa48("389") ? ["Stryker was here"] : (stryCov_9fa48("389"), []));
    return comparison;
  }
}