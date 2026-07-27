/**
 * Tests de los flujos de recuperacion y verificacion por email de `src/lib/auth.ts`.
 *
 * La mutacion dejo el archivo en 40.89% con 93 mutantes SIN COBERTURA: ningun
 * test ejecutaba `translateAuthError`, `resetPassword`, `updatePassword`,
 * `exchangeEmailCode` ni los dos flujos por token. Son justo los caminos que
 * un usuario recorre cuando ya no puede entrar — o sea, cuando menos se puede
 * dar el lujo de que fallen en silencio.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { mockAdapter, apiFetch } = vi.hoisted(() => ({
  mockAdapter: {
    login: vi.fn(),
    register: vi.fn(),
    loginWithGoogle: vi.fn(),
    logout: vi.fn(),
    getAccessToken: vi.fn(),
    getSession: vi.fn(),
    onAuthStateChange: vi.fn(),
  },
  apiFetch: vi.fn(),
}));

vi.mock('../../src/lib/auth/index', () => ({ authAdapter: mockAdapter }));
vi.mock('../../src/lib/api/core', () => ({ apiFetch }));
vi.mock('../../src/stores/authStore', () => ({
  useAuthStore: Object.assign(
    () => ({ user: null, session: null, profile: null, loading: false, error: null }),
    { getState: () => ({ reset: vi.fn(), profile: { rol: 'admin' } }) }
  ),
}));
vi.mock('../../src/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import {
  completeEmailCodeExchange,
  exchangeEmailCode,
  resetPassword,
  resetPasswordWithToken,
  updatePassword,
  verifyEmailWithToken,
} from '../../src/lib/auth';

/** Respuesta minima con la forma que el codigo consume. */
function respuesta({
  status = 200,
  ok,
  json,
}: {
  status?: number;
  ok?: boolean;
  json?: () => Promise<unknown>;
}) {
  return {
    status,
    ok: ok ?? (status >= 200 && status < 300),
    json: json ?? (async () => ({})),
  } as unknown as Response;
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('fetch', fetchMock);
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('resetPassword', () => {
  it('no revela si el email existe: informa exito incluso con 404 del servidor', async () => {
    // Propiedad de SEGURIDAD, no detalle de implementacion: si el resultado
    // dependiera del status, el formulario se convertiria en un oraculo para
    // enumerar cuentas registradas.
    fetchMock.mockResolvedValue(respuesta({ status: 404 }));

    await expect(resetPassword('nadie@example.com')).resolves.toEqual({ success: true });
  });

  it('pega al endpoint de forgot-password con el email en el cuerpo', async () => {
    fetchMock.mockResolvedValue(respuesta({ status: 202 }));

    await resetPassword('ana@example.com');

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/v2/auth/forgot-password');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ email: 'ana@example.com' });
  });

  it('informa el fallo cuando ni siquiera se pudo llegar al servidor', async () => {
    // Aca si hay que avisar: no es enumeracion, es que el pedido no salio.
    fetchMock.mockRejectedValue(new Error('sin red'));

    await expect(resetPassword('ana@example.com')).resolves.toEqual({
      success: false,
      error: 'Error al enviar el email de recuperacion.',
    });
  });
});

describe('updatePassword', () => {
  it('parchea /users/me con la contrasena nueva', async () => {
    apiFetch.mockResolvedValue({});

    await expect(updatePassword('nueva-clave-larga')).resolves.toEqual({ success: true });

    const [ruta, init] = apiFetch.mock.calls[0];
    expect(ruta).toBe('/users/me');
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body)).toEqual({ password: 'nueva-clave-larga' });
  });

  it('devuelve error cuando el backend rechaza el cambio', async () => {
    apiFetch.mockRejectedValue(new Error('401'));

    await expect(updatePassword('corta')).resolves.toEqual({
      success: false,
      error: 'Error al cambiar la contrasena.',
    });
  });
});

describe('verifyEmailWithToken', () => {
  it('devuelve exito cuando el backend acepta el token', async () => {
    fetchMock.mockResolvedValue(respuesta({ status: 200 }));

    await expect(verifyEmailWithToken('tok-ok')).resolves.toEqual({ success: true });
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/v2/auth/verify');
  });

  it('propaga el detalle del backend traducido', async () => {
    fetchMock.mockResolvedValue(
      respuesta({ status: 400, json: async () => ({ detail: 'User not found' }) })
    );

    await expect(verifyEmailWithToken('tok-malo')).resolves.toEqual({
      success: false,
      error: 'Usuario no encontrado',
    });
  });

  it('sobrevive a un cuerpo de error ilegible y usa el motivo por defecto', async () => {
    fetchMock.mockResolvedValue(
      respuesta({
        status: 400,
        json: async () => {
          throw new Error('no es json');
        },
      })
    );

    const resultado = await verifyEmailWithToken('tok-malo');
    expect(resultado.success).toBe(false);
    expect(resultado.error).toBe('VERIFY_USER_BAD_TOKEN');
  });
});

describe('resetPasswordWithToken', () => {
  it('manda token y contrasena nueva, y devuelve exito', async () => {
    fetchMock.mockResolvedValue(respuesta({ status: 200 }));

    await expect(resetPasswordWithToken('tok', 'clave-nueva')).resolves.toEqual({ success: true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/v2/auth/reset-password');
    expect(JSON.parse(init.body)).toEqual({ token: 'tok', password: 'clave-nueva' });
  });

  it('traduce el token vencido a un mensaje que el usuario entiende', async () => {
    fetchMock.mockResolvedValue(
      respuesta({ status: 400, json: async () => ({ detail: 'RESET_PASSWORD_BAD_TOKEN' }) })
    );

    await expect(resetPasswordWithToken('tok-viejo', 'clave')).resolves.toEqual({
      success: false,
      error: 'El enlace de recuperacion es invalido o ya expiro.',
    });
  });

  it('traduce tambien la contrasena rechazada por politica', async () => {
    fetchMock.mockResolvedValue(
      respuesta({ status: 400, json: async () => ({ detail: 'RESET_PASSWORD_INVALID_PASSWORD' }) })
    );

    const resultado = await resetPasswordWithToken('tok', '123');
    expect(resultado.error).toBe('La contrasena no cumple los requisitos minimos de seguridad.');
  });

  it('cae al motivo por defecto cuando el error viene sin detalle', async () => {
    fetchMock.mockResolvedValue(respuesta({ status: 500, json: async () => ({}) }));

    const resultado = await resetPasswordWithToken('tok', 'clave');
    expect(resultado.error).toBe('El enlace de recuperacion es invalido o ya expiro.');
  });
});

describe('traduccion de errores de auth', () => {
  it('traduce por coincidencia PARCIAL e insensible a mayusculas', async () => {
    // El backend suele envolver el motivo en una frase mas larga; la traduccion
    // igual tiene que salir. Si el `includes` se rompiera, al usuario le
    // llegaria el texto crudo en ingles.
    fetchMock.mockResolvedValue(
      respuesta({
        status: 400,
        json: async () => ({ detail: 'Fallo: INVALID LOGIN CREDENTIALS al autenticar' }),
      })
    );

    const resultado = await verifyEmailWithToken('tok');
    expect(resultado.error).toBe('Email o contrasena incorrectos');
  });

  it('devuelve el mensaje original cuando no hay traduccion disponible', async () => {
    fetchMock.mockResolvedValue(
      respuesta({ status: 400, json: async () => ({ detail: 'algo raro del backend' }) })
    );

    const resultado = await verifyEmailWithToken('tok');
    expect(resultado.error).toBe('algo raro del backend');
  });
});

describe('exchangeEmailCode', () => {
  it('devuelve el token y un handle cuando el canje sale bien', async () => {
    fetchMock.mockResolvedValue(
      respuesta({ status: 200, json: async () => ({ token: 'tok-real' }) })
    );

    const resultado = await exchangeEmailCode('CODE-1', 'verify');

    expect(resultado.status).toBe('success');
    if (resultado.status === 'success') {
      expect(resultado.token).toBe('tok-real');
      expect(resultado.handle).toBeTruthy();
      completeEmailCodeExchange(resultado.handle);
    }
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/v2/auth/exchange-code');
    expect(JSON.parse(init.body).code).toBe('CODE-1');
    expect(JSON.parse(init.body).purpose).toBe('verify');
  });

  it('deduplica llamadas concurrentes del mismo codigo en UN solo request', async () => {
    // Es la razon de ser del mapa de en-vuelo: dos componentes montados a la
    // vez con el mismo codigo del email no deben consumirlo dos veces.
    let resolver: (r: Response) => void = () => undefined;
    fetchMock.mockReturnValue(
      new Promise<Response>((res) => {
        resolver = res;
      })
    );

    const enVuelo = [
      exchangeEmailCode('CODE-DUP', 'verify'),
      exchangeEmailCode('CODE-DUP', 'verify'),
    ];
    resolver(respuesta({ status: 200, json: async () => ({ token: 'tok-unico' }) }));
    const [a, b] = await Promise.all(enVuelo);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(a).toBe(b);
  });

  it('permite reintentar despues de que el request en vuelo termino', async () => {
    // El `finally` borra la entrada del mapa. Si no lo hiciera, un fallo
    // recuperable dejaria el codigo trabado para siempre en esta pestana.
    fetchMock.mockResolvedValue(respuesta({ status: 503, json: async () => ({}) }));

    await exchangeEmailCode('CODE-RETRY', 'reset-password');
    await exchangeEmailCode('CODE-RETRY', 'reset-password');

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('un 4xx es terminal: el codigo es invalido o vencido, no sirve reintentar', async () => {
    fetchMock.mockResolvedValue(respuesta({ status: 400, json: async () => ({}) }));

    await expect(exchangeEmailCode('CODE-4XX', 'verify')).resolves.toEqual({
      status: 'terminal-error',
      reason: 'invalid-or-expired',
    });
  });

  it('un 5xx es recuperable: el codigo puede seguir siendo valido', async () => {
    fetchMock.mockResolvedValue(respuesta({ status: 500, json: async () => ({}) }));

    await expect(exchangeEmailCode('CODE-5XX', 'verify')).resolves.toEqual({
      status: 'retryable-error',
      reason: 'server',
    });
  });

  it('un fallo de red es recuperable', async () => {
    fetchMock.mockRejectedValue(new Error('sin red'));

    await expect(exchangeEmailCode('CODE-NET', 'verify')).resolves.toEqual({
      status: 'retryable-error',
      reason: 'network',
    });
  });

  it('un cuerpo que no es JSON es recuperable, no un exito a medias', async () => {
    fetchMock.mockResolvedValue(
      respuesta({
        status: 200,
        json: async () => {
          throw new Error('no es json');
        },
      })
    );

    await expect(exchangeEmailCode('CODE-BASURA', 'verify')).resolves.toEqual({
      status: 'retryable-error',
      reason: 'malformed-response',
    });
  });

  it('rechaza un token que no es cadena', async () => {
    fetchMock.mockResolvedValue(respuesta({ status: 200, json: async () => ({ token: 12345 }) }));

    await expect(exchangeEmailCode('CODE-NUM', 'verify')).resolves.toEqual({
      status: 'retryable-error',
      reason: 'malformed-response',
    });
  });

  it('rechaza un token en blanco: pasaria el chequeo de tipo pero no sirve', async () => {
    fetchMock.mockResolvedValue(respuesta({ status: 200, json: async () => ({ token: '   ' }) }));

    await expect(exchangeEmailCode('CODE-BLANCO', 'verify')).resolves.toEqual({
      status: 'retryable-error',
      reason: 'malformed-response',
    });
  });

  it('rechaza una respuesta que no es objeto', async () => {
    fetchMock.mockResolvedValue(respuesta({ status: 200, json: async () => null }));

    await expect(exchangeEmailCode('CODE-NULL', 'verify')).resolves.toEqual({
      status: 'retryable-error',
      reason: 'malformed-response',
    });
  });
});
