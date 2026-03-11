/**
 * Hook for managing selected satellite image across all map views.
 * Uses localStorage to persist the selection between page navigations.
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
import { logger } from '../lib/logger';
import { isValidSelectedImage } from '../lib/typeGuards';
const STORAGE_KEY = stryMutAct_9fa48("511") ? "" : (stryCov_9fa48("511"), 'consorcio_selected_image');
export interface SelectedImage {
  tile_url: string;
  target_date: string;
  sensor: 'Sentinel-1' | 'Sentinel-2';
  visualization: string;
  visualization_description: string;
  collection: string;
  images_count: number;
  flood_info?: {
    id: string;
    name: string;
    description: string;
    severity: string;
  };
  selected_at: string; // ISO timestamp when selected
}

/**
 * Hook to get and set the currently selected satellite image.
 * The image is stored in localStorage so it persists across page navigations.
 */
export function useSelectedImage() {
  if (stryMutAct_9fa48("512")) {
    {}
  } else {
    stryCov_9fa48("512");
    const [selectedImage, setSelectedImageState] = useState<SelectedImage | null>(null);
    const [isLoading, setIsLoading] = useState(stryMutAct_9fa48("513") ? false : (stryCov_9fa48("513"), true));

    // Load from localStorage on mount
    useEffect(() => {
      if (stryMutAct_9fa48("514")) {
        {}
      } else {
        stryCov_9fa48("514");
        try {
          if (stryMutAct_9fa48("515")) {
            {}
          } else {
            stryCov_9fa48("515");
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stryMutAct_9fa48("517") ? false : stryMutAct_9fa48("516") ? true : (stryCov_9fa48("516", "517"), stored)) {
              if (stryMutAct_9fa48("518")) {
                {}
              } else {
                stryCov_9fa48("518");
                const parsed = JSON.parse(stored);
                // Validate data structure before using
                if (stryMutAct_9fa48("520") ? false : stryMutAct_9fa48("519") ? true : (stryCov_9fa48("519", "520"), isValidSelectedImage(parsed))) {
                  if (stryMutAct_9fa48("521")) {
                    {}
                  } else {
                    stryCov_9fa48("521");
                    setSelectedImageState(parsed as SelectedImage);
                  }
                } else {
                  if (stryMutAct_9fa48("522")) {
                    {}
                  } else {
                    stryCov_9fa48("522");
                    logger.warn(stryMutAct_9fa48("523") ? "" : (stryCov_9fa48("523"), 'Invalid selected image data in localStorage, clearing'));
                    localStorage.removeItem(STORAGE_KEY);
                  }
                }
              }
            }
          }
        } catch (error) {
          if (stryMutAct_9fa48("524")) {
            {}
          } else {
            stryCov_9fa48("524");
            logger.error(stryMutAct_9fa48("525") ? "" : (stryCov_9fa48("525"), 'Error loading selected image from localStorage:'), error);
            localStorage.removeItem(STORAGE_KEY);
          }
        } finally {
          if (stryMutAct_9fa48("526")) {
            {}
          } else {
            stryCov_9fa48("526");
            setIsLoading(stryMutAct_9fa48("527") ? true : (stryCov_9fa48("527"), false));
          }
        }
      }
    }, stryMutAct_9fa48("528") ? ["Stryker was here"] : (stryCov_9fa48("528"), []));

    // Listen for changes from other tabs/windows
    useEffect(() => {
      if (stryMutAct_9fa48("529")) {
        {}
      } else {
        stryCov_9fa48("529");
        const handleStorageChange = (event: StorageEvent) => {
          if (stryMutAct_9fa48("530")) {
            {}
          } else {
            stryCov_9fa48("530");
            if (stryMutAct_9fa48("533") ? event.key !== STORAGE_KEY : stryMutAct_9fa48("532") ? false : stryMutAct_9fa48("531") ? true : (stryCov_9fa48("531", "532", "533"), event.key === STORAGE_KEY)) {
              if (stryMutAct_9fa48("534")) {
                {}
              } else {
                stryCov_9fa48("534");
                if (stryMutAct_9fa48("536") ? false : stryMutAct_9fa48("535") ? true : (stryCov_9fa48("535", "536"), event.newValue)) {
                  if (stryMutAct_9fa48("537")) {
                    {}
                  } else {
                    stryCov_9fa48("537");
                    try {
                      if (stryMutAct_9fa48("538")) {
                        {}
                      } else {
                        stryCov_9fa48("538");
                        const parsed = JSON.parse(event.newValue);
                        // Validate data structure before using
                        if (stryMutAct_9fa48("540") ? false : stryMutAct_9fa48("539") ? true : (stryCov_9fa48("539", "540"), isValidSelectedImage(parsed))) {
                          if (stryMutAct_9fa48("541")) {
                            {}
                          } else {
                            stryCov_9fa48("541");
                            setSelectedImageState(parsed as SelectedImage);
                          }
                        } else {
                          if (stryMutAct_9fa48("542")) {
                            {}
                          } else {
                            stryCov_9fa48("542");
                            setSelectedImageState(null);
                          }
                        }
                      }
                    } catch {
                      if (stryMutAct_9fa48("543")) {
                        {}
                      } else {
                        stryCov_9fa48("543");
                        setSelectedImageState(null);
                      }
                    }
                  }
                } else {
                  if (stryMutAct_9fa48("544")) {
                    {}
                  } else {
                    stryCov_9fa48("544");
                    setSelectedImageState(null);
                  }
                }
              }
            }
          }
        };
        window.addEventListener(stryMutAct_9fa48("545") ? "" : (stryCov_9fa48("545"), 'storage'), handleStorageChange);
        return stryMutAct_9fa48("546") ? () => undefined : (stryCov_9fa48("546"), () => window.removeEventListener(stryMutAct_9fa48("547") ? "" : (stryCov_9fa48("547"), 'storage'), handleStorageChange));
      }
    }, stryMutAct_9fa48("548") ? ["Stryker was here"] : (stryCov_9fa48("548"), []));

    // Set the selected image
    const setSelectedImage = useCallback((image: SelectedImage | null) => {
      if (stryMutAct_9fa48("549")) {
        {}
      } else {
        stryCov_9fa48("549");
        if (stryMutAct_9fa48("551") ? false : stryMutAct_9fa48("550") ? true : (stryCov_9fa48("550", "551"), image)) {
          if (stryMutAct_9fa48("552")) {
            {}
          } else {
            stryCov_9fa48("552");
            const imageWithTimestamp = stryMutAct_9fa48("553") ? {} : (stryCov_9fa48("553"), {
              ...image,
              selected_at: new Date().toISOString()
            });
            localStorage.setItem(STORAGE_KEY, JSON.stringify(imageWithTimestamp));
            setSelectedImageState(imageWithTimestamp);
          }
        } else {
          if (stryMutAct_9fa48("554")) {
            {}
          } else {
            stryCov_9fa48("554");
            localStorage.removeItem(STORAGE_KEY);
            setSelectedImageState(null);
          }
        }

        // Dispatch custom event for same-tab updates
        window.dispatchEvent(new CustomEvent(stryMutAct_9fa48("555") ? "" : (stryCov_9fa48("555"), 'selectedImageChange'), stryMutAct_9fa48("556") ? {} : (stryCov_9fa48("556"), {
          detail: image
        })));
      }
    }, stryMutAct_9fa48("557") ? ["Stryker was here"] : (stryCov_9fa48("557"), []));

    // Clear the selected image
    const clearSelectedImage = useCallback(() => {
      if (stryMutAct_9fa48("558")) {
        {}
      } else {
        stryCov_9fa48("558");
        localStorage.removeItem(STORAGE_KEY);
        setSelectedImageState(null);
        window.dispatchEvent(new CustomEvent(stryMutAct_9fa48("559") ? "" : (stryCov_9fa48("559"), 'selectedImageChange'), stryMutAct_9fa48("560") ? {} : (stryCov_9fa48("560"), {
          detail: null
        })));
      }
    }, stryMutAct_9fa48("561") ? ["Stryker was here"] : (stryCov_9fa48("561"), []));

    // Check if an image is currently selected
    const hasSelectedImage = stryMutAct_9fa48("564") ? selectedImage === null : stryMutAct_9fa48("563") ? false : stryMutAct_9fa48("562") ? true : (stryCov_9fa48("562", "563", "564"), selectedImage !== null);
    return stryMutAct_9fa48("565") ? {} : (stryCov_9fa48("565"), {
      selectedImage,
      setSelectedImage,
      clearSelectedImage,
      hasSelectedImage,
      isLoading
    });
  }
}

/**
 * Hook to listen for selected image changes without ability to modify.
 * Useful for map components that just need to display the layer.
 */
export function useSelectedImageListener() {
  if (stryMutAct_9fa48("566")) {
    {}
  } else {
    stryCov_9fa48("566");
    const [selectedImage, setSelectedImage] = useState<SelectedImage | null>(null);
    useEffect(() => {
      if (stryMutAct_9fa48("567")) {
        {}
      } else {
        stryCov_9fa48("567");
        // Load initial value with validation
        try {
          if (stryMutAct_9fa48("568")) {
            {}
          } else {
            stryCov_9fa48("568");
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stryMutAct_9fa48("570") ? false : stryMutAct_9fa48("569") ? true : (stryCov_9fa48("569", "570"), stored)) {
              if (stryMutAct_9fa48("571")) {
                {}
              } else {
                stryCov_9fa48("571");
                const parsed = JSON.parse(stored);
                if (stryMutAct_9fa48("573") ? false : stryMutAct_9fa48("572") ? true : (stryCov_9fa48("572", "573"), isValidSelectedImage(parsed))) {
                  if (stryMutAct_9fa48("574")) {
                    {}
                  } else {
                    stryCov_9fa48("574");
                    setSelectedImage(parsed as SelectedImage);
                  }
                } else {
                  if (stryMutAct_9fa48("575")) {
                    {}
                  } else {
                    stryCov_9fa48("575");
                    localStorage.removeItem(STORAGE_KEY);
                  }
                }
              }
            }
          }
        } catch {
          if (stryMutAct_9fa48("576")) {
            {}
          } else {
            stryCov_9fa48("576");
            localStorage.removeItem(STORAGE_KEY);
          }
        }

        // Listen for custom events (same tab)
        const handleCustomEvent = (event: CustomEvent<SelectedImage | null>) => {
          if (stryMutAct_9fa48("577")) {
            {}
          } else {
            stryCov_9fa48("577");
            // Custom events come from our own code, but validate anyway
            if (stryMutAct_9fa48("580") ? event.detail === null && isValidSelectedImage(event.detail) : stryMutAct_9fa48("579") ? false : stryMutAct_9fa48("578") ? true : (stryCov_9fa48("578", "579", "580"), (stryMutAct_9fa48("582") ? event.detail !== null : stryMutAct_9fa48("581") ? false : (stryCov_9fa48("581", "582"), event.detail === null)) || isValidSelectedImage(event.detail))) {
              if (stryMutAct_9fa48("583")) {
                {}
              } else {
                stryCov_9fa48("583");
                setSelectedImage(event.detail as SelectedImage | null);
              }
            }
          }
        };

        // Listen for storage events (other tabs)
        const handleStorageChange = (event: StorageEvent) => {
          if (stryMutAct_9fa48("584")) {
            {}
          } else {
            stryCov_9fa48("584");
            if (stryMutAct_9fa48("587") ? event.key !== STORAGE_KEY : stryMutAct_9fa48("586") ? false : stryMutAct_9fa48("585") ? true : (stryCov_9fa48("585", "586", "587"), event.key === STORAGE_KEY)) {
              if (stryMutAct_9fa48("588")) {
                {}
              } else {
                stryCov_9fa48("588");
                if (stryMutAct_9fa48("590") ? false : stryMutAct_9fa48("589") ? true : (stryCov_9fa48("589", "590"), event.newValue)) {
                  if (stryMutAct_9fa48("591")) {
                    {}
                  } else {
                    stryCov_9fa48("591");
                    try {
                      if (stryMutAct_9fa48("592")) {
                        {}
                      } else {
                        stryCov_9fa48("592");
                        const parsed = JSON.parse(event.newValue);
                        if (stryMutAct_9fa48("594") ? false : stryMutAct_9fa48("593") ? true : (stryCov_9fa48("593", "594"), isValidSelectedImage(parsed))) {
                          if (stryMutAct_9fa48("595")) {
                            {}
                          } else {
                            stryCov_9fa48("595");
                            setSelectedImage(parsed as SelectedImage);
                          }
                        } else {
                          if (stryMutAct_9fa48("596")) {
                            {}
                          } else {
                            stryCov_9fa48("596");
                            setSelectedImage(null);
                          }
                        }
                      }
                    } catch {
                      if (stryMutAct_9fa48("597")) {
                        {}
                      } else {
                        stryCov_9fa48("597");
                        setSelectedImage(null);
                      }
                    }
                  }
                } else {
                  if (stryMutAct_9fa48("598")) {
                    {}
                  } else {
                    stryCov_9fa48("598");
                    setSelectedImage(null);
                  }
                }
              }
            }
          }
        };
        window.addEventListener(stryMutAct_9fa48("599") ? "" : (stryCov_9fa48("599"), 'selectedImageChange'), handleCustomEvent as EventListener);
        window.addEventListener(stryMutAct_9fa48("600") ? "" : (stryCov_9fa48("600"), 'storage'), handleStorageChange);
        return () => {
          if (stryMutAct_9fa48("601")) {
            {}
          } else {
            stryCov_9fa48("601");
            window.removeEventListener(stryMutAct_9fa48("602") ? "" : (stryCov_9fa48("602"), 'selectedImageChange'), handleCustomEvent as EventListener);
            window.removeEventListener(stryMutAct_9fa48("603") ? "" : (stryCov_9fa48("603"), 'storage'), handleStorageChange);
          }
        };
      }
    }, stryMutAct_9fa48("604") ? ["Stryker was here"] : (stryCov_9fa48("604"), []));
    return selectedImage;
  }
}

/**
 * Get selected image synchronously (for non-React contexts).
 * Validates the data before returning to prevent XSS attacks.
 */
export function getSelectedImageSync(): SelectedImage | null {
  if (stryMutAct_9fa48("605")) {
    {}
  } else {
    stryCov_9fa48("605");
    try {
      if (stryMutAct_9fa48("606")) {
        {}
      } else {
        stryCov_9fa48("606");
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stryMutAct_9fa48("609") ? false : stryMutAct_9fa48("608") ? true : stryMutAct_9fa48("607") ? stored : (stryCov_9fa48("607", "608", "609"), !stored)) return null;
        const parsed = JSON.parse(stored);
        if (stryMutAct_9fa48("611") ? false : stryMutAct_9fa48("610") ? true : (stryCov_9fa48("610", "611"), isValidSelectedImage(parsed))) {
          if (stryMutAct_9fa48("612")) {
            {}
          } else {
            stryCov_9fa48("612");
            return parsed as SelectedImage;
          }
        }

        // Invalid data, clean up
        localStorage.removeItem(STORAGE_KEY);
        return null;
      }
    } catch {
      if (stryMutAct_9fa48("613")) {
        {}
      } else {
        stryCov_9fa48("613");
        localStorage.removeItem(STORAGE_KEY);
        return null;
      }
    }
  }
}