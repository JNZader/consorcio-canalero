/**
 * Tests de `initialize()` del authStore.
 *
 * La mutacion dejo este archivo al descubierto: el store puntuaba 26.8% y los
 * tests existentes (`authStore.test.ts`) cubren setters, selectores y el
 * logout cross-tab, pero NADA de `initialize()` — que es la parte con logica
 * real: el singleton de modulo que evita inicializaciones paralelas, las dos
 * ramas segun haya sesion o no, el listener de cambios de auth con sus tres
 * eventos, el manejo de error y el `finally` que libera la promesa.
 *
 * Cobertura y mutacion no son lo mismo: estas lineas se EJECUTABAN desde los
 * tests de cross-tab (que llaman a `initialize()` para armar el escenario),
 * pero nadie afirmaba nada sobre ellas, asi que se podian romper en silencio.
 */

import { act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const getSession = vi.fn();
const onAuthStateChange = vi.fn();

vi.mock('../../src/lib/auth/index', () => ({
  authAdapter: {
    getSession: (...args: unknown[]) => getSession(...args),
    onAuthStateChange: (...args: unknown[]) => onAuthStateChange(...args),
  },
}));

const clearAuthTokenCache = vi.fn();
vi.mock('../../src/lib/api', () => ({
  clearAuthTokenCache: () => clearAuthTokenCache(),
}));

const loggerError = vi.fn();
vi.mock('../../src/lib/logger', () => ({
  logger: { error: (...args: unknown[]) => loggerError(...args), warn: vi.fn(), info: vi.fn() },
}));

const { cleanupAuthListener, useAuthStore } = await import('../../src/stores/authStore');

/** Sesion completa tal como la devuelve el adapter JWT. */
function sesionDe(overrides: Record<string, unknown> = {}) {
  return {
    access_token: 'token-abc',
    user: {
      id: 'u-1',
      email: 'ana@example.com',
      nombre: 'Ana',
      apellido: 'Gomez',
      telefono: '3512223344',
      role: 'operador',
      ...overrides,
    },
  };
}

/** Deja el store listo para que `initialize()` haga trabajo de verdad. */
function prepararStoreSinInicializar() {
  useAuthStore.setState({
    user: null,
    session: null,
    profile: null,
    loading: true,
    error: null,
    initialized: false,
  });
}

/** Captura el callback que el store registro en `onAuthStateChange`. */
function callbackDeAuth(): (evento: string, sesion: unknown) => void {
  expect(onAuthStateChange).toHaveBeenCalled();
  return onAuthStateChange.mock.calls[0][0];
}

describe('authStore.initialize', () => {
  beforeEach(() => {
    cleanupAuthListener();
    vi.clearAllMocks();
    onAuthStateChange.mockReturnValue(() => undefined);
    getSession.mockResolvedValue(null);
    prepararStoreSinInicializar();
  });

  afterEach(() => {
    cleanupAuthListener();
  });

  describe('con sesion activa', () => {
    it('publica usuario, sesion y perfil, y deja el store inicializado sin error', async () => {
      getSession.mockResolvedValue(sesionDe());

      await act(async () => {
        await useAuthStore.getState().initialize();
      });

      const estado = useAuthStore.getState();
      expect(estado.user).toEqual({ id: 'u-1', email: 'ana@example.com' });
      expect(estado.session).toEqual({ access_token: 'token-abc' });
      expect(estado.profile).toEqual({
        id: 'u-1',
        email: 'ana@example.com',
        nombre: 'Ana Gomez',
        telefono: '3512223344',
        rol: 'operador',
      });
      expect(estado.loading).toBe(false);
      expect(estado.initialized).toBe(true);
      expect(estado.error).toBeNull();
    });

    it('arma el nombre con lo que haya y deja undefined lo que falta', async () => {
      // El perfil junta nombre y apellido filtrando vacios. Sin ninguno de los
      // dos el join daria '' y el campo tiene que quedar undefined, no cadena
      // vacia: una cadena vacia se renderiza como un nombre en blanco.
      getSession.mockResolvedValue(
        sesionDe({ nombre: '', apellido: '', telefono: '', role: 'ciudadano' })
      );

      await act(async () => {
        await useAuthStore.getState().initialize();
      });

      expect(useAuthStore.getState().profile).toEqual({
        id: 'u-1',
        email: 'ana@example.com',
        nombre: undefined,
        telefono: undefined,
        rol: 'ciudadano',
      });
    });

    it('usa solo el apellido cuando no hay nombre', async () => {
      getSession.mockResolvedValue(sesionDe({ nombre: '' }));

      await act(async () => {
        await useAuthStore.getState().initialize();
      });

      expect(useAuthStore.getState().profile?.nombre).toBe('Gomez');
    });
  });

  describe('sin sesion', () => {
    it('deja todo en null pero marca inicializado, para que la UI deje de esperar', async () => {
      getSession.mockResolvedValue(null);

      await act(async () => {
        await useAuthStore.getState().initialize();
      });

      const estado = useAuthStore.getState();
      expect(estado.user).toBeNull();
      expect(estado.session).toBeNull();
      expect(estado.profile).toBeNull();
      expect(estado.loading).toBe(false);
      expect(estado.initialized).toBe(true);
      expect(estado.error).toBeNull();
    });

    it('trata una sesion sin usuario igual que no tener sesion', async () => {
      getSession.mockResolvedValue({ access_token: 'token-huerfano', user: null });

      await act(async () => {
        await useAuthStore.getState().initialize();
      });

      const estado = useAuthStore.getState();
      expect(estado.user).toBeNull();
      expect(estado.session).toBeNull();
      expect(estado.initialized).toBe(true);
    });
  });

  describe('singleton de inicializacion', () => {
    it('no vuelve a pedir la sesion si el store ya esta inicializado', async () => {
      useAuthStore.setState({ initialized: true });

      await act(async () => {
        await useAuthStore.getState().initialize();
      });

      expect(getSession).not.toHaveBeenCalled();
    });

    it('varias llamadas en paralelo comparten UNA sola consulta de sesion', async () => {
      // Es la razon de existir del singleton de modulo: varias islas de React
      // llaman a initialize() a la vez y no deben disparar N refrescos de token.
      let resolver: (valor: unknown) => void = () => undefined;
      getSession.mockReturnValue(
        new Promise((res) => {
          resolver = res;
        })
      );

      await act(async () => {
        const enVuelo = [
          useAuthStore.getState().initialize(),
          useAuthStore.getState().initialize(),
          useAuthStore.getState().initialize(),
        ];
        resolver(sesionDe());
        await Promise.all(enVuelo);
      });

      expect(getSession).toHaveBeenCalledTimes(1);
      expect(useAuthStore.getState().user?.id).toBe('u-1');
    });

    it('registra el listener de auth una sola vez aunque se reinicialice', async () => {
      getSession.mockResolvedValue(sesionDe());

      await act(async () => {
        await useAuthStore.getState().initialize();
      });
      useAuthStore.setState({ initialized: false });
      await act(async () => {
        await useAuthStore.getState().initialize();
      });

      expect(getSession).toHaveBeenCalledTimes(2);
      expect(onAuthStateChange).toHaveBeenCalledTimes(1);
    });

    it('libera la promesa al terminar, asi un reset permite reinicializar', async () => {
      getSession.mockResolvedValue(null);

      await act(async () => {
        await useAuthStore.getState().initialize();
      });
      useAuthStore.setState({ initialized: false });
      await act(async () => {
        await useAuthStore.getState().initialize();
      });

      // Si el `finally` no limpiara la promesa, la segunda llamada devolveria
      // la vieja ya resuelta y no volveria a consultar la sesion.
      expect(getSession).toHaveBeenCalledTimes(2);
    });
  });

  describe('cuando el adapter falla', () => {
    it('registra el error y deja el store utilizable en vez de colgado', async () => {
      getSession.mockRejectedValue(new Error('red caida'));

      await act(async () => {
        await useAuthStore.getState().initialize();
      });

      const estado = useAuthStore.getState();
      expect(loggerError).toHaveBeenCalled();
      expect(estado.error).toBe('Error al inicializar autenticacion');
      // Lo importante: loading en false e initialized en true. Si quedaran al
      // reves, la UI se queda esperando para siempre en el spinner.
      expect(estado.loading).toBe(false);
      expect(estado.initialized).toBe(true);
    });

    it('libera la promesa tambien cuando falla, asi se puede reintentar', async () => {
      getSession.mockRejectedValueOnce(new Error('red caida'));

      await act(async () => {
        await useAuthStore.getState().initialize();
      });

      getSession.mockResolvedValue(sesionDe());
      useAuthStore.setState({ initialized: false });
      await act(async () => {
        await useAuthStore.getState().initialize();
      });

      expect(useAuthStore.getState().user?.id).toBe('u-1');
      expect(useAuthStore.getState().error).toBeNull();
    });
  });

  describe('listener de cambios de auth', () => {
    beforeEach(async () => {
      getSession.mockResolvedValue(null);
      await act(async () => {
        await useAuthStore.getState().initialize();
      });
      clearAuthTokenCache.mockClear();
    });

    it('SIGNED_IN publica usuario, sesion y perfil', async () => {
      await act(async () => {
        callbackDeAuth()('SIGNED_IN', sesionDe());
      });

      const estado = useAuthStore.getState();
      expect(estado.user).toEqual({ id: 'u-1', email: 'ana@example.com' });
      expect(estado.session).toEqual({ access_token: 'token-abc' });
      expect(estado.profile?.rol).toBe('operador');
      expect(estado.error).toBeNull();
    });

    it('SIGNED_IN sin usuario no toca el estado', async () => {
      useAuthStore.setState({ user: { id: 'previo', email: 'previo@example.com' } });

      await act(async () => {
        callbackDeAuth()('SIGNED_IN', { access_token: 'x', user: null });
      });

      expect(useAuthStore.getState().user?.id).toBe('previo');
    });

    it('SIGNED_OUT limpia el estado y ademas la cache del token', async () => {
      useAuthStore.setState({
        user: { id: 'u-1', email: 'ana@example.com' },
        session: { access_token: 'token-abc' },
        profile: { id: 'u-1', email: 'ana@example.com', rol: 'operador' },
      });

      await act(async () => {
        callbackDeAuth()('SIGNED_OUT', null);
      });

      const estado = useAuthStore.getState();
      expect(estado.user).toBeNull();
      expect(estado.session).toBeNull();
      expect(estado.profile).toBeNull();
      // Sin esto, el proximo request sale con el token del usuario anterior.
      expect(clearAuthTokenCache).toHaveBeenCalled();
    });

    it('TOKEN_REFRESHED cambia el token y invalida la cache, sin tocar al usuario', async () => {
      useAuthStore.setState({
        user: { id: 'u-1', email: 'ana@example.com' },
        session: { access_token: 'token-viejo' },
      });

      await act(async () => {
        callbackDeAuth()('TOKEN_REFRESHED', { access_token: 'token-nuevo', user: null });
      });

      const estado = useAuthStore.getState();
      expect(estado.session).toEqual({ access_token: 'token-nuevo' });
      expect(estado.user?.id).toBe('u-1');
      // Si no se invalida, se sigue mandando el token viejo hasta que expire.
      expect(clearAuthTokenCache).toHaveBeenCalled();
    });

    it('TOKEN_REFRESHED sin sesion no pisa el token vigente', async () => {
      useAuthStore.setState({ session: { access_token: 'token-vigente' } });

      await act(async () => {
        callbackDeAuth()('TOKEN_REFRESHED', null);
      });

      expect(useAuthStore.getState().session?.access_token).toBe('token-vigente');
      expect(clearAuthTokenCache).not.toHaveBeenCalled();
    });

    it('un evento desconocido no altera nada', async () => {
      useAuthStore.setState({
        user: { id: 'u-1', email: 'ana@example.com' },
        session: { access_token: 'token-abc' },
      });

      await act(async () => {
        callbackDeAuth()('PASSWORD_RECOVERY', sesionDe());
      });

      const estado = useAuthStore.getState();
      expect(estado.user?.id).toBe('u-1');
      expect(estado.session?.access_token).toBe('token-abc');
      expect(clearAuthTokenCache).not.toHaveBeenCalled();
    });
  });

  describe('reset', () => {
    it('invalida la cache del token ademas de limpiar el estado', async () => {
      useAuthStore.setState({ user: { id: 'u-1', email: 'ana@example.com' } });
      clearAuthTokenCache.mockClear();

      act(() => {
        useAuthStore.getState().reset();
      });

      const estado = useAuthStore.getState();
      expect(clearAuthTokenCache).toHaveBeenCalled();
      expect(estado.user).toBeNull();
      // reset deja el store USABLE, no en el estado inicial crudo: sin esto la
      // UI volveria al spinner de arranque despues de cerrar sesion.
      expect(estado.loading).toBe(false);
      expect(estado.initialized).toBe(true);
      expect(estado._hasHydrated).toBe(true);
    });
  });
});
