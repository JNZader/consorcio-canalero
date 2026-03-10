/**
 * Hook para verificacion de contacto usando Supabase Auth.
 *
 * Soporta:
 * - Google OAuth (1 click)
 * - Magic Link (cualquier email)
 *
 * Simplificado de la version anterior que usaba WhatsApp.
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
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useState } from 'react';
import { useAuthStore } from '../stores/authStore';
import { getSupabaseClient } from '../lib/supabase';
import { logger } from '../lib/logger';
import { isValidEmail } from '../lib/validators';
export type VerificationMethod = 'google' | 'email';
export interface UseContactVerificationOptions {
  /**
   * Callback cuando la verificacion es exitosa.
   */
  onVerified?: (email: string, name?: string) => void;
}
export interface ContactVerificationState {
  /** Usuario esta verificado (autenticado) */
  contactoVerificado: boolean;
  /** Email del usuario verificado */
  userEmail: string | null;
  /** Nombre del usuario (si disponible) */
  userName: string | null;
  /** Metodo de verificacion seleccionado */
  metodoVerificacion: VerificationMethod;
  /** Cargando autenticacion */
  loading: boolean;
  /** Magic link fue enviado */
  magicLinkSent: boolean;
  /** Email al que se envio el magic link */
  magicLinkEmail: string | null;
}
export interface ContactVerificationActions {
  /** Cambiar metodo de verificacion */
  setMetodoVerificacion: (method: VerificationMethod) => void;
  /** Iniciar login con Google */
  loginWithGoogle: () => Promise<void>;
  /** Enviar magic link */
  sendMagicLink: (email: string) => Promise<void>;
  /** Cerrar sesion */
  logout: () => Promise<void>;
  /** Resetear estado */
  resetVerificacion: () => void;
}
export type UseContactVerificationReturn = ContactVerificationState & ContactVerificationActions;
export function useContactVerification(options: UseContactVerificationOptions = {}): UseContactVerificationReturn {
  if (stryMutAct_9fa48("96")) {
    {}
  } else {
    stryCov_9fa48("96");
    const {
      onVerified
    } = options;

    // Estado del auth store
    const user = useAuthStore(stryMutAct_9fa48("97") ? () => undefined : (stryCov_9fa48("97"), state => state.user));
    const profile = useAuthStore(stryMutAct_9fa48("98") ? () => undefined : (stryCov_9fa48("98"), state => state.profile));
    const initialized = useAuthStore(stryMutAct_9fa48("99") ? () => undefined : (stryCov_9fa48("99"), state => state.initialized));
    const authLoading = useAuthStore(stryMutAct_9fa48("100") ? () => undefined : (stryCov_9fa48("100"), state => state.loading));

    // Estado local
    const [metodoVerificacion, setMetodoVerificacion] = useState<VerificationMethod>(stryMutAct_9fa48("101") ? "" : (stryCov_9fa48("101"), 'google'));
    const [loading, setLoading] = useState(stryMutAct_9fa48("102") ? true : (stryCov_9fa48("102"), false));
    const [magicLinkSent, setMagicLinkSent] = useState(stryMutAct_9fa48("103") ? true : (stryCov_9fa48("103"), false));
    const [magicLinkEmail, setMagicLinkEmail] = useState<string | null>(null);

    // Derivar estado de verificacion del auth store
    const contactoVerificado = stryMutAct_9fa48("106") ? !!user || initialized : stryMutAct_9fa48("105") ? false : stryMutAct_9fa48("104") ? true : (stryCov_9fa48("104", "105", "106"), (stryMutAct_9fa48("107") ? !user : (stryCov_9fa48("107"), !(stryMutAct_9fa48("108") ? user : (stryCov_9fa48("108"), !user)))) && initialized);
    const userEmail = stryMutAct_9fa48("111") ? user?.email && null : stryMutAct_9fa48("110") ? false : stryMutAct_9fa48("109") ? true : (stryCov_9fa48("109", "110", "111"), (stryMutAct_9fa48("112") ? user.email : (stryCov_9fa48("112"), user?.email)) || null);
    const userName = stryMutAct_9fa48("115") ? (profile?.nombre || user?.user_metadata?.full_name || user?.user_metadata?.name) && null : stryMutAct_9fa48("114") ? false : stryMutAct_9fa48("113") ? true : (stryCov_9fa48("113", "114", "115"), (stryMutAct_9fa48("117") ? (profile?.nombre || user?.user_metadata?.full_name) && user?.user_metadata?.name : stryMutAct_9fa48("116") ? false : (stryCov_9fa48("116", "117"), (stryMutAct_9fa48("119") ? profile?.nombre && user?.user_metadata?.full_name : stryMutAct_9fa48("118") ? false : (stryCov_9fa48("118", "119"), (stryMutAct_9fa48("120") ? profile.nombre : (stryCov_9fa48("120"), profile?.nombre)) || (stryMutAct_9fa48("122") ? user.user_metadata?.full_name : stryMutAct_9fa48("121") ? user?.user_metadata.full_name : (stryCov_9fa48("121", "122"), user?.user_metadata?.full_name)))) || (stryMutAct_9fa48("124") ? user.user_metadata?.name : stryMutAct_9fa48("123") ? user?.user_metadata.name : (stryCov_9fa48("123", "124"), user?.user_metadata?.name)))) || null);

    // Notificar cuando se verifica
    useEffect(() => {
      if (stryMutAct_9fa48("125")) {
        {}
      } else {
        stryCov_9fa48("125");
        if (stryMutAct_9fa48("128") ? contactoVerificado && userEmail || onVerified : stryMutAct_9fa48("127") ? false : stryMutAct_9fa48("126") ? true : (stryCov_9fa48("126", "127", "128"), (stryMutAct_9fa48("130") ? contactoVerificado || userEmail : stryMutAct_9fa48("129") ? true : (stryCov_9fa48("129", "130"), contactoVerificado && userEmail)) && onVerified)) {
          if (stryMutAct_9fa48("131")) {
            {}
          } else {
            stryCov_9fa48("131");
            onVerified(userEmail, stryMutAct_9fa48("134") ? userName && undefined : stryMutAct_9fa48("133") ? false : stryMutAct_9fa48("132") ? true : (stryCov_9fa48("132", "133", "134"), userName || undefined));
          }
        }
      }
    }, stryMutAct_9fa48("135") ? [] : (stryCov_9fa48("135"), [contactoVerificado, userEmail, userName, onVerified]));

    // Login con Google OAuth
    const loginWithGoogle = useCallback(async () => {
      if (stryMutAct_9fa48("136")) {
        {}
      } else {
        stryCov_9fa48("136");
        setLoading(stryMutAct_9fa48("137") ? false : (stryCov_9fa48("137"), true));
        try {
          if (stryMutAct_9fa48("138")) {
            {}
          } else {
            stryCov_9fa48("138");
            const supabase = getSupabaseClient();
            const {
              error
            } = await supabase.auth.signInWithOAuth(stryMutAct_9fa48("139") ? {} : (stryCov_9fa48("139"), {
              provider: stryMutAct_9fa48("140") ? "" : (stryCov_9fa48("140"), 'google'),
              options: stryMutAct_9fa48("141") ? {} : (stryCov_9fa48("141"), {
                redirectTo: stryMutAct_9fa48("142") ? `` : (stryCov_9fa48("142"), `${window.location.origin}${window.location.pathname}?auth=success`),
                queryParams: stryMutAct_9fa48("143") ? {} : (stryCov_9fa48("143"), {
                  access_type: stryMutAct_9fa48("144") ? "" : (stryCov_9fa48("144"), 'offline'),
                  prompt: stryMutAct_9fa48("145") ? "" : (stryCov_9fa48("145"), 'consent')
                })
              })
            }));
            if (stryMutAct_9fa48("147") ? false : stryMutAct_9fa48("146") ? true : (stryCov_9fa48("146", "147"), error)) {
              if (stryMutAct_9fa48("148")) {
                {}
              } else {
                stryCov_9fa48("148");
                throw error;
              }
            }
            // El redirect sucede automaticamente
          }
        } catch (error) {
          if (stryMutAct_9fa48("149")) {
            {}
          } else {
            stryCov_9fa48("149");
            logger.error(stryMutAct_9fa48("150") ? "" : (stryCov_9fa48("150"), 'Error en login con Google:'), error);
            notifications.show(stryMutAct_9fa48("151") ? {} : (stryCov_9fa48("151"), {
              title: stryMutAct_9fa48("152") ? "" : (stryCov_9fa48("152"), 'Error'),
              message: stryMutAct_9fa48("153") ? "" : (stryCov_9fa48("153"), 'No se pudo iniciar sesion con Google'),
              color: stryMutAct_9fa48("154") ? "" : (stryCov_9fa48("154"), 'red')
            }));
            setLoading(stryMutAct_9fa48("155") ? true : (stryCov_9fa48("155"), false));
          }
        }
      }
    }, stryMutAct_9fa48("156") ? ["Stryker was here"] : (stryCov_9fa48("156"), []));

    // Enviar magic link
    const sendMagicLink = useCallback(async (email: string) => {
      if (stryMutAct_9fa48("157")) {
        {}
      } else {
        stryCov_9fa48("157");
        // Validacion usando validador centralizado
        if (stryMutAct_9fa48("160") ? false : stryMutAct_9fa48("159") ? true : stryMutAct_9fa48("158") ? isValidEmail(email) : (stryCov_9fa48("158", "159", "160"), !isValidEmail(email))) {
          if (stryMutAct_9fa48("161")) {
            {}
          } else {
            stryCov_9fa48("161");
            notifications.show(stryMutAct_9fa48("162") ? {} : (stryCov_9fa48("162"), {
              title: stryMutAct_9fa48("163") ? "" : (stryCov_9fa48("163"), 'Email invalido'),
              message: stryMutAct_9fa48("164") ? "" : (stryCov_9fa48("164"), 'Ingresa un email valido'),
              color: stryMutAct_9fa48("165") ? "" : (stryCov_9fa48("165"), 'red')
            }));
            return;
          }
        }
        setLoading(stryMutAct_9fa48("166") ? false : (stryCov_9fa48("166"), true));
        try {
          if (stryMutAct_9fa48("167")) {
            {}
          } else {
            stryCov_9fa48("167");
            const supabase = getSupabaseClient();
            const {
              error
            } = await supabase.auth.signInWithOtp(stryMutAct_9fa48("168") ? {} : (stryCov_9fa48("168"), {
              email,
              options: stryMutAct_9fa48("169") ? {} : (stryCov_9fa48("169"), {
                emailRedirectTo: stryMutAct_9fa48("170") ? `` : (stryCov_9fa48("170"), `${window.location.origin}${window.location.pathname}?auth=success`)
              })
            }));
            if (stryMutAct_9fa48("172") ? false : stryMutAct_9fa48("171") ? true : (stryCov_9fa48("171", "172"), error)) {
              if (stryMutAct_9fa48("173")) {
                {}
              } else {
                stryCov_9fa48("173");
                throw error;
              }
            }
            setMagicLinkSent(stryMutAct_9fa48("174") ? false : (stryCov_9fa48("174"), true));
            setMagicLinkEmail(email);
            notifications.show(stryMutAct_9fa48("175") ? {} : (stryCov_9fa48("175"), {
              title: stryMutAct_9fa48("176") ? "" : (stryCov_9fa48("176"), 'Link enviado'),
              message: stryMutAct_9fa48("177") ? `` : (stryCov_9fa48("177"), `Revisa tu email ${email}`),
              color: stryMutAct_9fa48("178") ? "" : (stryCov_9fa48("178"), 'green')
            }));
          }
        } catch (error) {
          if (stryMutAct_9fa48("179")) {
            {}
          } else {
            stryCov_9fa48("179");
            logger.error(stryMutAct_9fa48("180") ? "" : (stryCov_9fa48("180"), 'Error enviando magic link:'), error);
            const message = error instanceof Error ? error.message : stryMutAct_9fa48("181") ? "" : (stryCov_9fa48("181"), 'No se pudo enviar el email');
            notifications.show(stryMutAct_9fa48("182") ? {} : (stryCov_9fa48("182"), {
              title: stryMutAct_9fa48("183") ? "" : (stryCov_9fa48("183"), 'Error'),
              message,
              color: stryMutAct_9fa48("184") ? "" : (stryCov_9fa48("184"), 'red')
            }));
          }
        } finally {
          if (stryMutAct_9fa48("185")) {
            {}
          } else {
            stryCov_9fa48("185");
            setLoading(stryMutAct_9fa48("186") ? true : (stryCov_9fa48("186"), false));
          }
        }
      }
    }, stryMutAct_9fa48("187") ? ["Stryker was here"] : (stryCov_9fa48("187"), []));

    // Logout
    const logout = useCallback(async () => {
      if (stryMutAct_9fa48("188")) {
        {}
      } else {
        stryCov_9fa48("188");
        try {
          if (stryMutAct_9fa48("189")) {
            {}
          } else {
            stryCov_9fa48("189");
            const supabase = getSupabaseClient();
            await supabase.auth.signOut();
            notifications.show(stryMutAct_9fa48("190") ? {} : (stryCov_9fa48("190"), {
              title: stryMutAct_9fa48("191") ? "" : (stryCov_9fa48("191"), 'Sesion cerrada'),
              message: stryMutAct_9fa48("192") ? "" : (stryCov_9fa48("192"), 'Has cerrado sesion correctamente'),
              color: stryMutAct_9fa48("193") ? "" : (stryCov_9fa48("193"), 'blue')
            }));
          }
        } catch (error) {
          if (stryMutAct_9fa48("194")) {
            {}
          } else {
            stryCov_9fa48("194");
            logger.error(stryMutAct_9fa48("195") ? "" : (stryCov_9fa48("195"), 'Error al cerrar sesion:'), error);
          }
        }
      }
    }, stryMutAct_9fa48("196") ? ["Stryker was here"] : (stryCov_9fa48("196"), []));

    // Reset
    const resetVerificacion = useCallback(() => {
      if (stryMutAct_9fa48("197")) {
        {}
      } else {
        stryCov_9fa48("197");
        setMagicLinkSent(stryMutAct_9fa48("198") ? true : (stryCov_9fa48("198"), false));
        setMagicLinkEmail(null);
        setMetodoVerificacion(stryMutAct_9fa48("199") ? "" : (stryCov_9fa48("199"), 'google'));
      }
    }, stryMutAct_9fa48("200") ? ["Stryker was here"] : (stryCov_9fa48("200"), []));
    return stryMutAct_9fa48("201") ? {} : (stryCov_9fa48("201"), {
      // Estado
      contactoVerificado,
      userEmail,
      userName,
      metodoVerificacion,
      loading: stryMutAct_9fa48("204") ? loading && authLoading : stryMutAct_9fa48("203") ? false : stryMutAct_9fa48("202") ? true : (stryCov_9fa48("202", "203", "204"), loading || authLoading),
      magicLinkSent,
      magicLinkEmail,
      // Acciones
      setMetodoVerificacion,
      loginWithGoogle,
      sendMagicLink,
      logout,
      resetVerificacion
    });
  }
}
export default useContactVerification;