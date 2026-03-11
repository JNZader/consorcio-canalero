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
const STORAGE_KEY = stryMutAct_9fa48("95") ? "" : (stryCov_9fa48("95"), 'consorcio_selected_image');
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
  if (stryMutAct_9fa48("96")) {
    {}
  } else {
    stryCov_9fa48("96");
    const [selectedImage, setSelectedImageState] = useState<SelectedImage | null>(null);
    const [isLoading, setIsLoading] = useState(stryMutAct_9fa48("97") ? false : (stryCov_9fa48("97"), true));

    // Load from localStorage on mount
    useEffect(() => {
      if (stryMutAct_9fa48("98")) {
        {}
      } else {
        stryCov_9fa48("98");
        try {
          if (stryMutAct_9fa48("99")) {
            {}
          } else {
            stryCov_9fa48("99");
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stryMutAct_9fa48("101") ? false : stryMutAct_9fa48("100") ? true : (stryCov_9fa48("100", "101"), stored)) {
              if (stryMutAct_9fa48("102")) {
                {}
              } else {
                stryCov_9fa48("102");
                const parsed = JSON.parse(stored);
                // Validate data structure before using
                if (stryMutAct_9fa48("104") ? false : stryMutAct_9fa48("103") ? true : (stryCov_9fa48("103", "104"), isValidSelectedImage(parsed))) {
                  if (stryMutAct_9fa48("105")) {
                    {}
                  } else {
                    stryCov_9fa48("105");
                    setSelectedImageState(parsed as SelectedImage);
                  }
                } else {
                  if (stryMutAct_9fa48("106")) {
                    {}
                  } else {
                    stryCov_9fa48("106");
                    logger.warn(stryMutAct_9fa48("107") ? "" : (stryCov_9fa48("107"), 'Invalid selected image data in localStorage, clearing'));
                    localStorage.removeItem(STORAGE_KEY);
                  }
                }
              }
            }
          }
        } catch (error) {
          if (stryMutAct_9fa48("108")) {
            {}
          } else {
            stryCov_9fa48("108");
            logger.error(stryMutAct_9fa48("109") ? "" : (stryCov_9fa48("109"), 'Error loading selected image from localStorage:'), error);
            localStorage.removeItem(STORAGE_KEY);
          }
        } finally {
          if (stryMutAct_9fa48("110")) {
            {}
          } else {
            stryCov_9fa48("110");
            setIsLoading(stryMutAct_9fa48("111") ? true : (stryCov_9fa48("111"), false));
          }
        }
      }
    }, stryMutAct_9fa48("112") ? ["Stryker was here"] : (stryCov_9fa48("112"), []));

    // Listen for changes from other tabs/windows
    useEffect(() => {
      if (stryMutAct_9fa48("113")) {
        {}
      } else {
        stryCov_9fa48("113");
        const handleStorageChange = (event: StorageEvent) => {
          if (stryMutAct_9fa48("114")) {
            {}
          } else {
            stryCov_9fa48("114");
            if (stryMutAct_9fa48("117") ? event.key !== STORAGE_KEY : stryMutAct_9fa48("116") ? false : stryMutAct_9fa48("115") ? true : (stryCov_9fa48("115", "116", "117"), event.key === STORAGE_KEY)) {
              if (stryMutAct_9fa48("118")) {
                {}
              } else {
                stryCov_9fa48("118");
                if (stryMutAct_9fa48("120") ? false : stryMutAct_9fa48("119") ? true : (stryCov_9fa48("119", "120"), event.newValue)) {
                  if (stryMutAct_9fa48("121")) {
                    {}
                  } else {
                    stryCov_9fa48("121");
                    try {
                      if (stryMutAct_9fa48("122")) {
                        {}
                      } else {
                        stryCov_9fa48("122");
                        const parsed = JSON.parse(event.newValue);
                        // Validate data structure before using
                        if (stryMutAct_9fa48("124") ? false : stryMutAct_9fa48("123") ? true : (stryCov_9fa48("123", "124"), isValidSelectedImage(parsed))) {
                          if (stryMutAct_9fa48("125")) {
                            {}
                          } else {
                            stryCov_9fa48("125");
                            setSelectedImageState(parsed as SelectedImage);
                          }
                        } else {
                          if (stryMutAct_9fa48("126")) {
                            {}
                          } else {
                            stryCov_9fa48("126");
                            setSelectedImageState(null);
                          }
                        }
                      }
                    } catch {
                      if (stryMutAct_9fa48("127")) {
                        {}
                      } else {
                        stryCov_9fa48("127");
                        setSelectedImageState(null);
                      }
                    }
                  }
                } else {
                  if (stryMutAct_9fa48("128")) {
                    {}
                  } else {
                    stryCov_9fa48("128");
                    setSelectedImageState(null);
                  }
                }
              }
            }
          }
        };
        window.addEventListener(stryMutAct_9fa48("129") ? "" : (stryCov_9fa48("129"), 'storage'), handleStorageChange);
        return stryMutAct_9fa48("130") ? () => undefined : (stryCov_9fa48("130"), () => window.removeEventListener(stryMutAct_9fa48("131") ? "" : (stryCov_9fa48("131"), 'storage'), handleStorageChange));
      }
    }, stryMutAct_9fa48("132") ? ["Stryker was here"] : (stryCov_9fa48("132"), []));

    // Set the selected image
    const setSelectedImage = useCallback((image: SelectedImage | null) => {
      if (stryMutAct_9fa48("133")) {
        {}
      } else {
        stryCov_9fa48("133");
        if (stryMutAct_9fa48("135") ? false : stryMutAct_9fa48("134") ? true : (stryCov_9fa48("134", "135"), image)) {
          if (stryMutAct_9fa48("136")) {
            {}
          } else {
            stryCov_9fa48("136");
            const imageWithTimestamp = stryMutAct_9fa48("137") ? {} : (stryCov_9fa48("137"), {
              ...image,
              selected_at: new Date().toISOString()
            });
            localStorage.setItem(STORAGE_KEY, JSON.stringify(imageWithTimestamp));
            setSelectedImageState(imageWithTimestamp);
          }
        } else {
          if (stryMutAct_9fa48("138")) {
            {}
          } else {
            stryCov_9fa48("138");
            localStorage.removeItem(STORAGE_KEY);
            setSelectedImageState(null);
          }
        }

        // Dispatch custom event for same-tab updates
        window.dispatchEvent(new CustomEvent(stryMutAct_9fa48("139") ? "" : (stryCov_9fa48("139"), 'selectedImageChange'), stryMutAct_9fa48("140") ? {} : (stryCov_9fa48("140"), {
          detail: image
        })));
      }
    }, stryMutAct_9fa48("141") ? ["Stryker was here"] : (stryCov_9fa48("141"), []));

    // Clear the selected image
    const clearSelectedImage = useCallback(() => {
      if (stryMutAct_9fa48("142")) {
        {}
      } else {
        stryCov_9fa48("142");
        localStorage.removeItem(STORAGE_KEY);
        setSelectedImageState(null);
        window.dispatchEvent(new CustomEvent(stryMutAct_9fa48("143") ? "" : (stryCov_9fa48("143"), 'selectedImageChange'), stryMutAct_9fa48("144") ? {} : (stryCov_9fa48("144"), {
          detail: null
        })));
      }
    }, stryMutAct_9fa48("145") ? ["Stryker was here"] : (stryCov_9fa48("145"), []));

    // Check if an image is currently selected
    const hasSelectedImage = stryMutAct_9fa48("148") ? selectedImage === null : stryMutAct_9fa48("147") ? false : stryMutAct_9fa48("146") ? true : (stryCov_9fa48("146", "147", "148"), selectedImage !== null);
    return stryMutAct_9fa48("149") ? {} : (stryCov_9fa48("149"), {
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
  if (stryMutAct_9fa48("150")) {
    {}
  } else {
    stryCov_9fa48("150");
    const [selectedImage, setSelectedImage] = useState<SelectedImage | null>(null);
    useEffect(() => {
      if (stryMutAct_9fa48("151")) {
        {}
      } else {
        stryCov_9fa48("151");
        // Load initial value with validation
        try {
          if (stryMutAct_9fa48("152")) {
            {}
          } else {
            stryCov_9fa48("152");
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stryMutAct_9fa48("154") ? false : stryMutAct_9fa48("153") ? true : (stryCov_9fa48("153", "154"), stored)) {
              if (stryMutAct_9fa48("155")) {
                {}
              } else {
                stryCov_9fa48("155");
                const parsed = JSON.parse(stored);
                if (stryMutAct_9fa48("157") ? false : stryMutAct_9fa48("156") ? true : (stryCov_9fa48("156", "157"), isValidSelectedImage(parsed))) {
                  if (stryMutAct_9fa48("158")) {
                    {}
                  } else {
                    stryCov_9fa48("158");
                    setSelectedImage(parsed as SelectedImage);
                  }
                } else {
                  if (stryMutAct_9fa48("159")) {
                    {}
                  } else {
                    stryCov_9fa48("159");
                    localStorage.removeItem(STORAGE_KEY);
                  }
                }
              }
            }
          }
        } catch {
          if (stryMutAct_9fa48("160")) {
            {}
          } else {
            stryCov_9fa48("160");
            localStorage.removeItem(STORAGE_KEY);
          }
        }

        // Listen for custom events (same tab)
        const handleCustomEvent = (event: CustomEvent<SelectedImage | null>) => {
          if (stryMutAct_9fa48("161")) {
            {}
          } else {
            stryCov_9fa48("161");
            // Custom events come from our own code, but validate anyway
            if (stryMutAct_9fa48("164") ? event.detail === null && isValidSelectedImage(event.detail) : stryMutAct_9fa48("163") ? false : stryMutAct_9fa48("162") ? true : (stryCov_9fa48("162", "163", "164"), (stryMutAct_9fa48("166") ? event.detail !== null : stryMutAct_9fa48("165") ? false : (stryCov_9fa48("165", "166"), event.detail === null)) || isValidSelectedImage(event.detail))) {
              if (stryMutAct_9fa48("167")) {
                {}
              } else {
                stryCov_9fa48("167");
                setSelectedImage(event.detail as SelectedImage | null);
              }
            }
          }
        };

        // Listen for storage events (other tabs)
        const handleStorageChange = (event: StorageEvent) => {
          if (stryMutAct_9fa48("168")) {
            {}
          } else {
            stryCov_9fa48("168");
            if (stryMutAct_9fa48("171") ? event.key !== STORAGE_KEY : stryMutAct_9fa48("170") ? false : stryMutAct_9fa48("169") ? true : (stryCov_9fa48("169", "170", "171"), event.key === STORAGE_KEY)) {
              if (stryMutAct_9fa48("172")) {
                {}
              } else {
                stryCov_9fa48("172");
                if (stryMutAct_9fa48("174") ? false : stryMutAct_9fa48("173") ? true : (stryCov_9fa48("173", "174"), event.newValue)) {
                  if (stryMutAct_9fa48("175")) {
                    {}
                  } else {
                    stryCov_9fa48("175");
                    try {
                      if (stryMutAct_9fa48("176")) {
                        {}
                      } else {
                        stryCov_9fa48("176");
                        const parsed = JSON.parse(event.newValue);
                        if (stryMutAct_9fa48("178") ? false : stryMutAct_9fa48("177") ? true : (stryCov_9fa48("177", "178"), isValidSelectedImage(parsed))) {
                          if (stryMutAct_9fa48("179")) {
                            {}
                          } else {
                            stryCov_9fa48("179");
                            setSelectedImage(parsed as SelectedImage);
                          }
                        } else {
                          if (stryMutAct_9fa48("180")) {
                            {}
                          } else {
                            stryCov_9fa48("180");
                            setSelectedImage(null);
                          }
                        }
                      }
                    } catch {
                      if (stryMutAct_9fa48("181")) {
                        {}
                      } else {
                        stryCov_9fa48("181");
                        setSelectedImage(null);
                      }
                    }
                  }
                } else {
                  if (stryMutAct_9fa48("182")) {
                    {}
                  } else {
                    stryCov_9fa48("182");
                    setSelectedImage(null);
                  }
                }
              }
            }
          }
        };
        window.addEventListener(stryMutAct_9fa48("183") ? "" : (stryCov_9fa48("183"), 'selectedImageChange'), handleCustomEvent as EventListener);
        window.addEventListener(stryMutAct_9fa48("184") ? "" : (stryCov_9fa48("184"), 'storage'), handleStorageChange);
        return () => {
          if (stryMutAct_9fa48("185")) {
            {}
          } else {
            stryCov_9fa48("185");
            window.removeEventListener(stryMutAct_9fa48("186") ? "" : (stryCov_9fa48("186"), 'selectedImageChange'), handleCustomEvent as EventListener);
            window.removeEventListener(stryMutAct_9fa48("187") ? "" : (stryCov_9fa48("187"), 'storage'), handleStorageChange);
          }
        };
      }
    }, stryMutAct_9fa48("188") ? ["Stryker was here"] : (stryCov_9fa48("188"), []));
    return selectedImage;
  }
}

/**
 * Get selected image synchronously (for non-React contexts).
 * Validates the data before returning to prevent XSS attacks.
 */
export function getSelectedImageSync(): SelectedImage | null {
  if (stryMutAct_9fa48("189")) {
    {}
  } else {
    stryCov_9fa48("189");
    try {
      if (stryMutAct_9fa48("190")) {
        {}
      } else {
        stryCov_9fa48("190");
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stryMutAct_9fa48("193") ? false : stryMutAct_9fa48("192") ? true : stryMutAct_9fa48("191") ? stored : (stryCov_9fa48("191", "192", "193"), !stored)) return null;
        const parsed = JSON.parse(stored);
        if (stryMutAct_9fa48("195") ? false : stryMutAct_9fa48("194") ? true : (stryCov_9fa48("194", "195"), isValidSelectedImage(parsed))) {
          if (stryMutAct_9fa48("196")) {
            {}
          } else {
            stryCov_9fa48("196");
            return parsed as SelectedImage;
          }
        }

        // Invalid data, clean up
        localStorage.removeItem(STORAGE_KEY);
        return null;
      }
    } catch {
      if (stryMutAct_9fa48("197")) {
        {}
      } else {
        stryCov_9fa48("197");
        localStorage.removeItem(STORAGE_KEY);
        return null;
      }
    }
  }
}