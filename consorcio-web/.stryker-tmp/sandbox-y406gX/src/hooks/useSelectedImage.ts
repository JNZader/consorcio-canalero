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
const STORAGE_KEY = stryMutAct_9fa48("0") ? "" : (stryCov_9fa48("0"), 'consorcio_selected_image');
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
  if (stryMutAct_9fa48("1")) {
    {}
  } else {
    stryCov_9fa48("1");
    const [selectedImage, setSelectedImageState] = useState<SelectedImage | null>(null);
    const [isLoading, setIsLoading] = useState(stryMutAct_9fa48("2") ? false : (stryCov_9fa48("2"), true));

    // Load from localStorage on mount
    useEffect(() => {
      if (stryMutAct_9fa48("3")) {
        {}
      } else {
        stryCov_9fa48("3");
        try {
          if (stryMutAct_9fa48("4")) {
            {}
          } else {
            stryCov_9fa48("4");
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stryMutAct_9fa48("6") ? false : stryMutAct_9fa48("5") ? true : (stryCov_9fa48("5", "6"), stored)) {
              if (stryMutAct_9fa48("7")) {
                {}
              } else {
                stryCov_9fa48("7");
                const parsed = JSON.parse(stored);
                // Validate data structure before using
                if (stryMutAct_9fa48("9") ? false : stryMutAct_9fa48("8") ? true : (stryCov_9fa48("8", "9"), isValidSelectedImage(parsed))) {
                  if (stryMutAct_9fa48("10")) {
                    {}
                  } else {
                    stryCov_9fa48("10");
                    setSelectedImageState(parsed as SelectedImage);
                  }
                } else {
                  if (stryMutAct_9fa48("11")) {
                    {}
                  } else {
                    stryCov_9fa48("11");
                    logger.warn(stryMutAct_9fa48("12") ? "" : (stryCov_9fa48("12"), 'Invalid selected image data in localStorage, clearing'));
                    localStorage.removeItem(STORAGE_KEY);
                  }
                }
              }
            }
          }
        } catch (error) {
          if (stryMutAct_9fa48("13")) {
            {}
          } else {
            stryCov_9fa48("13");
            logger.error(stryMutAct_9fa48("14") ? "" : (stryCov_9fa48("14"), 'Error loading selected image from localStorage:'), error);
            localStorage.removeItem(STORAGE_KEY);
          }
        } finally {
          if (stryMutAct_9fa48("15")) {
            {}
          } else {
            stryCov_9fa48("15");
            setIsLoading(stryMutAct_9fa48("16") ? true : (stryCov_9fa48("16"), false));
          }
        }
      }
    }, stryMutAct_9fa48("17") ? ["Stryker was here"] : (stryCov_9fa48("17"), []));

    // Listen for changes from other tabs/windows
    useEffect(() => {
      if (stryMutAct_9fa48("18")) {
        {}
      } else {
        stryCov_9fa48("18");
        const handleStorageChange = (event: StorageEvent) => {
          if (stryMutAct_9fa48("19")) {
            {}
          } else {
            stryCov_9fa48("19");
            if (stryMutAct_9fa48("22") ? event.key !== STORAGE_KEY : stryMutAct_9fa48("21") ? false : stryMutAct_9fa48("20") ? true : (stryCov_9fa48("20", "21", "22"), event.key === STORAGE_KEY)) {
              if (stryMutAct_9fa48("23")) {
                {}
              } else {
                stryCov_9fa48("23");
                if (stryMutAct_9fa48("25") ? false : stryMutAct_9fa48("24") ? true : (stryCov_9fa48("24", "25"), event.newValue)) {
                  if (stryMutAct_9fa48("26")) {
                    {}
                  } else {
                    stryCov_9fa48("26");
                    try {
                      if (stryMutAct_9fa48("27")) {
                        {}
                      } else {
                        stryCov_9fa48("27");
                        const parsed = JSON.parse(event.newValue);
                        // Validate data structure before using
                        if (stryMutAct_9fa48("29") ? false : stryMutAct_9fa48("28") ? true : (stryCov_9fa48("28", "29"), isValidSelectedImage(parsed))) {
                          if (stryMutAct_9fa48("30")) {
                            {}
                          } else {
                            stryCov_9fa48("30");
                            setSelectedImageState(parsed as SelectedImage);
                          }
                        } else {
                          if (stryMutAct_9fa48("31")) {
                            {}
                          } else {
                            stryCov_9fa48("31");
                            setSelectedImageState(null);
                          }
                        }
                      }
                    } catch {
                      if (stryMutAct_9fa48("32")) {
                        {}
                      } else {
                        stryCov_9fa48("32");
                        setSelectedImageState(null);
                      }
                    }
                  }
                } else {
                  if (stryMutAct_9fa48("33")) {
                    {}
                  } else {
                    stryCov_9fa48("33");
                    setSelectedImageState(null);
                  }
                }
              }
            }
          }
        };
        window.addEventListener(stryMutAct_9fa48("34") ? "" : (stryCov_9fa48("34"), 'storage'), handleStorageChange);
        return stryMutAct_9fa48("35") ? () => undefined : (stryCov_9fa48("35"), () => window.removeEventListener(stryMutAct_9fa48("36") ? "" : (stryCov_9fa48("36"), 'storage'), handleStorageChange));
      }
    }, stryMutAct_9fa48("37") ? ["Stryker was here"] : (stryCov_9fa48("37"), []));

    // Set the selected image
    const setSelectedImage = useCallback((image: SelectedImage | null) => {
      if (stryMutAct_9fa48("38")) {
        {}
      } else {
        stryCov_9fa48("38");
        if (stryMutAct_9fa48("40") ? false : stryMutAct_9fa48("39") ? true : (stryCov_9fa48("39", "40"), image)) {
          if (stryMutAct_9fa48("41")) {
            {}
          } else {
            stryCov_9fa48("41");
            const imageWithTimestamp = stryMutAct_9fa48("42") ? {} : (stryCov_9fa48("42"), {
              ...image,
              selected_at: new Date().toISOString()
            });
            localStorage.setItem(STORAGE_KEY, JSON.stringify(imageWithTimestamp));
            setSelectedImageState(imageWithTimestamp);
          }
        } else {
          if (stryMutAct_9fa48("43")) {
            {}
          } else {
            stryCov_9fa48("43");
            localStorage.removeItem(STORAGE_KEY);
            setSelectedImageState(null);
          }
        }

        // Dispatch custom event for same-tab updates
        window.dispatchEvent(new CustomEvent(stryMutAct_9fa48("44") ? "" : (stryCov_9fa48("44"), 'selectedImageChange'), stryMutAct_9fa48("45") ? {} : (stryCov_9fa48("45"), {
          detail: image
        })));
      }
    }, stryMutAct_9fa48("46") ? ["Stryker was here"] : (stryCov_9fa48("46"), []));

    // Clear the selected image
    const clearSelectedImage = useCallback(() => {
      if (stryMutAct_9fa48("47")) {
        {}
      } else {
        stryCov_9fa48("47");
        localStorage.removeItem(STORAGE_KEY);
        setSelectedImageState(null);
        window.dispatchEvent(new CustomEvent(stryMutAct_9fa48("48") ? "" : (stryCov_9fa48("48"), 'selectedImageChange'), stryMutAct_9fa48("49") ? {} : (stryCov_9fa48("49"), {
          detail: null
        })));
      }
    }, stryMutAct_9fa48("50") ? ["Stryker was here"] : (stryCov_9fa48("50"), []));

    // Check if an image is currently selected
    const hasSelectedImage = stryMutAct_9fa48("53") ? selectedImage === null : stryMutAct_9fa48("52") ? false : stryMutAct_9fa48("51") ? true : (stryCov_9fa48("51", "52", "53"), selectedImage !== null);
    return stryMutAct_9fa48("54") ? {} : (stryCov_9fa48("54"), {
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
  if (stryMutAct_9fa48("55")) {
    {}
  } else {
    stryCov_9fa48("55");
    const [selectedImage, setSelectedImage] = useState<SelectedImage | null>(null);
    useEffect(() => {
      if (stryMutAct_9fa48("56")) {
        {}
      } else {
        stryCov_9fa48("56");
        // Load initial value with validation
        try {
          if (stryMutAct_9fa48("57")) {
            {}
          } else {
            stryCov_9fa48("57");
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stryMutAct_9fa48("59") ? false : stryMutAct_9fa48("58") ? true : (stryCov_9fa48("58", "59"), stored)) {
              if (stryMutAct_9fa48("60")) {
                {}
              } else {
                stryCov_9fa48("60");
                const parsed = JSON.parse(stored);
                if (stryMutAct_9fa48("62") ? false : stryMutAct_9fa48("61") ? true : (stryCov_9fa48("61", "62"), isValidSelectedImage(parsed))) {
                  if (stryMutAct_9fa48("63")) {
                    {}
                  } else {
                    stryCov_9fa48("63");
                    setSelectedImage(parsed as SelectedImage);
                  }
                } else {
                  if (stryMutAct_9fa48("64")) {
                    {}
                  } else {
                    stryCov_9fa48("64");
                    localStorage.removeItem(STORAGE_KEY);
                  }
                }
              }
            }
          }
        } catch {
          if (stryMutAct_9fa48("65")) {
            {}
          } else {
            stryCov_9fa48("65");
            localStorage.removeItem(STORAGE_KEY);
          }
        }

        // Listen for custom events (same tab)
        const handleCustomEvent = (event: CustomEvent<SelectedImage | null>) => {
          if (stryMutAct_9fa48("66")) {
            {}
          } else {
            stryCov_9fa48("66");
            // Custom events come from our own code, but validate anyway
            if (stryMutAct_9fa48("69") ? event.detail === null && isValidSelectedImage(event.detail) : stryMutAct_9fa48("68") ? false : stryMutAct_9fa48("67") ? true : (stryCov_9fa48("67", "68", "69"), (stryMutAct_9fa48("71") ? event.detail !== null : stryMutAct_9fa48("70") ? false : (stryCov_9fa48("70", "71"), event.detail === null)) || isValidSelectedImage(event.detail))) {
              if (stryMutAct_9fa48("72")) {
                {}
              } else {
                stryCov_9fa48("72");
                setSelectedImage(event.detail as SelectedImage | null);
              }
            }
          }
        };

        // Listen for storage events (other tabs)
        const handleStorageChange = (event: StorageEvent) => {
          if (stryMutAct_9fa48("73")) {
            {}
          } else {
            stryCov_9fa48("73");
            if (stryMutAct_9fa48("76") ? event.key !== STORAGE_KEY : stryMutAct_9fa48("75") ? false : stryMutAct_9fa48("74") ? true : (stryCov_9fa48("74", "75", "76"), event.key === STORAGE_KEY)) {
              if (stryMutAct_9fa48("77")) {
                {}
              } else {
                stryCov_9fa48("77");
                if (stryMutAct_9fa48("79") ? false : stryMutAct_9fa48("78") ? true : (stryCov_9fa48("78", "79"), event.newValue)) {
                  if (stryMutAct_9fa48("80")) {
                    {}
                  } else {
                    stryCov_9fa48("80");
                    try {
                      if (stryMutAct_9fa48("81")) {
                        {}
                      } else {
                        stryCov_9fa48("81");
                        const parsed = JSON.parse(event.newValue);
                        if (stryMutAct_9fa48("83") ? false : stryMutAct_9fa48("82") ? true : (stryCov_9fa48("82", "83"), isValidSelectedImage(parsed))) {
                          if (stryMutAct_9fa48("84")) {
                            {}
                          } else {
                            stryCov_9fa48("84");
                            setSelectedImage(parsed as SelectedImage);
                          }
                        } else {
                          if (stryMutAct_9fa48("85")) {
                            {}
                          } else {
                            stryCov_9fa48("85");
                            setSelectedImage(null);
                          }
                        }
                      }
                    } catch {
                      if (stryMutAct_9fa48("86")) {
                        {}
                      } else {
                        stryCov_9fa48("86");
                        setSelectedImage(null);
                      }
                    }
                  }
                } else {
                  if (stryMutAct_9fa48("87")) {
                    {}
                  } else {
                    stryCov_9fa48("87");
                    setSelectedImage(null);
                  }
                }
              }
            }
          }
        };
        window.addEventListener(stryMutAct_9fa48("88") ? "" : (stryCov_9fa48("88"), 'selectedImageChange'), handleCustomEvent as EventListener);
        window.addEventListener(stryMutAct_9fa48("89") ? "" : (stryCov_9fa48("89"), 'storage'), handleStorageChange);
        return () => {
          if (stryMutAct_9fa48("90")) {
            {}
          } else {
            stryCov_9fa48("90");
            window.removeEventListener(stryMutAct_9fa48("91") ? "" : (stryCov_9fa48("91"), 'selectedImageChange'), handleCustomEvent as EventListener);
            window.removeEventListener(stryMutAct_9fa48("92") ? "" : (stryCov_9fa48("92"), 'storage'), handleStorageChange);
          }
        };
      }
    }, stryMutAct_9fa48("93") ? ["Stryker was here"] : (stryCov_9fa48("93"), []));
    return selectedImage;
  }
}

/**
 * Get selected image synchronously (for non-React contexts).
 * Validates the data before returning to prevent XSS attacks.
 */
export function getSelectedImageSync(): SelectedImage | null {
  if (stryMutAct_9fa48("94")) {
    {}
  } else {
    stryCov_9fa48("94");
    try {
      if (stryMutAct_9fa48("95")) {
        {}
      } else {
        stryCov_9fa48("95");
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stryMutAct_9fa48("98") ? false : stryMutAct_9fa48("97") ? true : stryMutAct_9fa48("96") ? stored : (stryCov_9fa48("96", "97", "98"), !stored)) return null;
        const parsed = JSON.parse(stored);
        if (stryMutAct_9fa48("100") ? false : stryMutAct_9fa48("99") ? true : (stryCov_9fa48("99", "100"), isValidSelectedImage(parsed))) {
          if (stryMutAct_9fa48("101")) {
            {}
          } else {
            stryCov_9fa48("101");
            return parsed as SelectedImage;
          }
        }

        // Invalid data, clean up
        localStorage.removeItem(STORAGE_KEY);
        return null;
      }
    } catch {
      if (stryMutAct_9fa48("102")) {
        {}
      } else {
        stryCov_9fa48("102");
        localStorage.removeItem(STORAGE_KEY);
        return null;
      }
    }
  }
}