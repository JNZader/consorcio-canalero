/**
 * ConocimientoPanel — the mailbox (bandeja) of legal consultations (U8, tasks
 * 8.1-8.4; design G6 as amended by A3).
 *
 * This is NOT a chat. A question is SUBMITTED, it sits `pendiente` until the
 * worker processes it, and its outcome appears on a later poll. The panel's
 * entire job is to render what the server decided, verbatim:
 *
 *  - the six item states, each visibly distinct. `generacion_fallida` and
 *    `no_disponible` read as OPERATIONAL failures, never as "no applicable
 *    norm" — an abstención is a claim about the law and saying it when the
 *    provider timed out is a lie about the corpus;
 *  - the citation cards, drawn from `respuesta.citas`, which the server already
 *    filtered to the post-exclusion payload. There is no client-side filter here
 *    and there must not be one: one set, one place (design G6);
 *  - the SERVER's markers — `estado_vigencia`, `es_secundaria`,
 *    `relevancia_consorcio` — displayed as given. The panel never re-derives a
 *    vigencia from the text and never paraphrases anything inside a citation.
 *    The one derived thing is PRESENTATION: the badge COLOUR reads the marker's
 *    prefix, while the badge TEXT is always the server's string verbatim. A
 *    colour is a claim too, so it is derived conservatively — see
 *    {@link colorDeVigencia};
 *  - the redirect surface the SERVER named. The classification→surface mapping
 *    is deterministic and server-side (routing spec:31); a lookup table in the
 *    frontend would be a second mapping free to drift from it.
 */

import {
  Alert,
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Code,
  Group,
  Loader,
  NativeSelect,
  Paper,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core';
import { useState } from 'react';

import { useConocimientoNormas } from '../../hooks/useConocimientoNormas';
import { useConocimientoQA } from '../../hooks/useConocimientoQA';
import {
  CONOCIMIENTO_ESTADOS,
  CONOCIMIENTO_PREGUNTA_MAX_CHARS,
  ConocimientoApiError,
  type ConocimientoBorradorExportado,
  type ConocimientoCita,
  type ConocimientoEstado,
  type ConocimientoItem,
  type ConocimientoRedireccion,
  type ConocimientoResultadoNormas,
  PEDIDOS_8803,
} from '../../lib/api/conocimiento';
import {
  IconAlertTriangle,
  IconClock,
  IconDownload,
  IconExternalLink,
  IconInfoCircle,
  IconRefresh,
  IconSearch,
  IconSend,
} from '../ui/icons';
import ProtectedRoute from './ProtectedRoute';

/**
 * How each state is titled and coloured. A const map rather than a switch so the
 * six states are enumerated in ONE place: a state the server can send and this
 * table does not name would otherwise render as a blank card.
 */
const PRESENTACION_ESTADO: Record<ConocimientoEstado, { titulo: string; color: string }> = {
  [CONOCIMIENTO_ESTADOS.PENDIENTE]: { titulo: 'En cola', color: 'gray' },
  [CONOCIMIENTO_ESTADOS.RESPUESTA]: { titulo: 'Respuesta', color: 'teal' },
  [CONOCIMIENTO_ESTADOS.ABSTENCION]: { titulo: 'Sin norma aplicable', color: 'yellow' },
  [CONOCIMIENTO_ESTADOS.REDIRECCION]: { titulo: 'Corresponde a otra sección', color: 'blue' },
  [CONOCIMIENTO_ESTADOS.GENERACION_FALLIDA]: { titulo: 'No se pudo generar', color: 'orange' },
  [CONOCIMIENTO_ESTADOS.NO_DISPONIBLE]: { titulo: 'Servicio no disponible', color: 'red' },
};

/**
 * The presentation for one state, with an explicit fallback for a state this
 * table does not name.
 *
 * The table above is exhaustive over the CURRENT contract, and the type system
 * says so — which is exactly why the runtime needs this. The server can add a
 * seventh state, or a deployment can run a newer backend than this bundle, and
 * indexing the table then yields `undefined`. Reading `.titulo` off that throws
 * inside `ConocimientoItemCard`, and with no error boundary above the list ONE
 * unrecognized item blanks the entire bandeja — every other answer included.
 *
 * The fallback names the value verbatim instead of guessing a meaning for it:
 * this panel does not know what the state means, and inventing "Procesando" or
 * "Error" for an unknown value would be the panel deciding something only the
 * server can decide.
 */
export function presentacionDeEstado(estado: string): { titulo: string; color: string } {
  return (
    PRESENTACION_ESTADO[estado as ConocimientoEstado] ?? {
      titulo: `Estado no reconocido: ${estado}`,
      color: 'gray',
    }
  );
}

/**
 * Explanations of the non-answer states, in the panel's own words.
 *
 * Deliberately NOT the server's `motivo`, which is rendered separately and
 * verbatim next to these. This text explains what the STATE means; the `motivo`
 * says what happened in this particular case, and collapsing the two would put
 * the panel in the business of paraphrasing the server.
 */
const EXPLICACION_ESTADO: Partial<Record<ConocimientoEstado, string>> = {
  [CONOCIMIENTO_ESTADOS.ABSTENCION]:
    'El corpus no tiene una norma aplicable a esta pregunta, o la mejor coincidencia no alcanzó el umbral. No se generó respuesta.',
  [CONOCIMIENTO_ESTADOS.GENERACION_FALLIDA]:
    'Había contexto legal, pero la respuesta no pudo producirse ni certificarse. Esto no dice nada sobre la norma: volvé a preguntar más tarde.',
  [CONOCIMIENTO_ESTADOS.NO_DISPONIBLE]:
    'Una dependencia del servicio no estaba disponible al procesar la consulta.',
};

const FORMATO_FECHA = new Intl.DateTimeFormat('es-AR', {
  dateStyle: 'short',
  timeStyle: 'short',
});

function formatearFecha(iso: string | null | undefined): string {
  if (!iso) return '—';
  const fecha = new Date(iso);
  return Number.isNaN(fecha.getTime()) ? '—' : FORMATO_FECHA.format(fecha);
}

/** In-answer citation markers, same shape the generator emits: `[clave#con#gato]`. */
const MARCADOR_CITA = /(\[[^[\]\s]*#[^[\]\s]*\])/g;

function anclaDeCita(citationKey: string): string {
  return `cita-${citationKey}`;
}

/**
 * The answer prose with its citation markers turned into anchors to the cards.
 *
 * The prose itself is untouched — the markers are LINKED, not removed and not
 * renumbered. Every key in a served answer is a member of the payload (the
 * server rejects any answer where it is not), so every anchor resolves to a card
 * on this same page.
 */
function ProsaConCitas({ prosa }: Readonly<{ prosa: string }>) {
  const partes = prosa.split(MARCADOR_CITA);
  return (
    <Text data-testid="respuesta-prosa" style={{ whiteSpace: 'pre-wrap' }}>
      {/* The position IS the identity here: `split()` output is positional, the
          prose fragments have no id, and the same citation key may legitimately
          appear twice in one answer. The list is also never reordered — it is
          re-derived from the prose on every render. */}
      {partes.map((parte, indice) => {
        if (!parte.startsWith('[') || !parte.endsWith(']') || !parte.includes('#')) {
          return <span key={`t-${indice}`}>{parte}</span>;
        }
        const clave = parte.slice(1, -1);
        return (
          <Anchor key={`c-${indice}`} href={`#${anclaDeCita(clave)}`} data-testid="cita-marcador">
            {parte}
          </Anchor>
        );
      })}
    </Text>
  );
}

/**
 * The badge COLOUR for a `estado_vigencia`. The TEXT is never touched.
 *
 * The spec's marker is prefix-shaped: the only two prefixes with a defined
 * meaning are `VIGENTE…` and `DEROGADA…`. Everything else the corpus can carry —
 * `EN REVISIÓN`, `SIN DATOS`, a value added after this file was written — is
 * UNKNOWN, and painting the unknown red would tell the reader "do not cite this"
 * about a norm nobody said anything against. A red badge is an assertion about
 * the law, so it is spent only on the prefix that actually asserts it; anything
 * else gets a neutral badge and the reader gets the server's own words.
 */
export function colorDeVigencia(estadoVigencia: string): 'teal' | 'red' | 'gray' {
  const normalizado = estadoVigencia.trim().toUpperCase();
  if (normalizado.startsWith('DEROGADA')) return 'red';
  if (normalizado.startsWith('VIGENTE')) return 'teal';
  return 'gray';
}

/** One citation card. Every field here is server-authored and shown as given. */
function isSafeUrl(rawUrl: string): boolean {
  if (!rawUrl) return false;
  const trimmed = rawUrl.trim();
  if (trimmed.startsWith('/') && !trimmed.startsWith('//')) return true;
  try {
    const parsed = new URL(trimmed);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:';
  } catch {
    return false;
  }
}

export function ConocimientoCitaCard({ cita }: Readonly<{ cita: ConocimientoCita }>) {
  return (
    <Card
      withBorder
      radius="md"
      padding="sm"
      id={anclaDeCita(cita.citation_key)}
      data-testid="cita-card"
      data-citation-key={cita.citation_key}
    >
      <Stack gap="xs">
        <Group gap="xs" wrap="wrap">
          <Code>{cita.citation_key}</Code>
          {cita.estado_vigencia ? (
            <Badge
              size="sm"
              variant="light"
              color={colorDeVigencia(cita.estado_vigencia)}
              data-testid="cita-vigencia"
              data-color-vigencia={colorDeVigencia(cita.estado_vigencia)}
            >
              {cita.estado_vigencia}
            </Badge>
          ) : null}
          {cita.es_secundaria ? (
            <Badge size="sm" variant="light" color="gray" data-testid="cita-secundaria">
              fuente secundaria — no es derecho aplicable
            </Badge>
          ) : null}
        </Group>

        {cita.epigrafe ? (
          <Text size="sm" fw={600}>
            {cita.epigrafe}
          </Text>
        ) : null}

        {/* Verbatim, and verbatim is the point: this is the document's own
            statement about how the unit may be used. Summarizing it here would
            be the panel editing a warning about citing the law. */}
        {cita.relevancia_consorcio ? (
          <Alert
            color="orange"
            variant="light"
            icon={<IconAlertTriangle size={16} />}
            data-testid="cita-relevancia"
          >
            {cita.relevancia_consorcio}
          </Alert>
        ) : null}

        <Box
          component="pre"
          data-testid="cita-texto"
          style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'inherit' }}
        >
          {cita.texto}
        </Box>

        <Group gap="xs">
          <Text size="xs" c="dimmed">
            {cita.tipo} · {cita.jurisdiccion}
          </Text>
          {cita.fuente_url && isSafeUrl(cita.fuente_url) ? (
            <Anchor
              href={cita.fuente_url}
              target="_blank"
              rel="noopener noreferrer"
              size="xs"
              data-testid="cita-fuente"
            >
              <Group gap={4} component="span">
                <IconExternalLink size={12} />
                Fuente
              </Group>
            </Anchor>
          ) : null}
        </Group>
      </Stack>
    </Card>
  );
}

function BloqueRedireccion({
  redireccion,
  parcial,
}: Readonly<{ redireccion: ConocimientoRedireccion; parcial: boolean }>) {
  const sufijo = parcial ? 'parcial-' : '';
  const safe = isSafeUrl(redireccion.superficie);
  return (
    <Alert color="blue" variant="light" icon={<IconInfoCircle size={16} />}>
      <Stack gap={4}>
        <Text size="sm" data-testid={`redireccion-${sufijo}motivo`}>
          {redireccion.motivo}
        </Text>
        {safe ? (
          <Anchor href={redireccion.superficie} data-testid={`redireccion-${sufijo}enlace`}>
            Ir a {redireccion.superficie}
          </Anchor>
        ) : (
          <Text size="sm" fw={500} data-testid={`redireccion-${sufijo}enlace`}>
            Ir a {redireccion.superficie}
          </Text>
        )}
      </Stack>
    </Alert>
  );
}

/**
 * One row of the bandeja. Exported for the panel tests: mounting the whole panel
 * to assert on one state would put the fetch and the form in the way of a
 * rendering assertion.
 */
export function ConocimientoItemCard({ item }: Readonly<{ item: ConocimientoItem }>) {
  const presentacion = presentacionDeEstado(item.estado);
  const respuesta = item.respuesta;
  const explicacion = EXPLICACION_ESTADO[item.estado];

  return (
    <Paper withBorder radius="md" p="md" data-testid="item-buzon" data-estado={item.estado}>
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <Text fw={600}>{item.pregunta}</Text>
          <Badge color={presentacion.color} variant="light" data-testid="estado-badge">
            {presentacion.titulo}
          </Badge>
        </Group>

        <Text size="xs" c="dimmed">
          Enviada {formatearFecha(item.creada_en)}
          {item.procesada_en ? ` · procesada ${formatearFecha(item.procesada_en)}` : ''}
        </Text>

        {item.estado === CONOCIMIENTO_ESTADOS.PENDIENTE ? (
          <Group gap="xs">
            <IconClock size={16} />
            {/* "Pendiente" is only honest while it is true (A3). `demorado` is
                computed server-side against the worker's last run — the browser
                cannot know that and must not guess it. */}
            {item.demorado ? (
              <Text size="sm" c="orange" data-testid="pendiente-demorado">
                El procesador no está procesando la cola desde hace un rato. Tu consulta sigue
                encolada; no se perdió.
              </Text>
            ) : (
              <Text size="sm" c="dimmed">
                En cola. La respuesta aparece acá cuando se procese.
              </Text>
            )}
          </Group>
        ) : null}

        {explicacion ? (
          <Text size="sm" c="dimmed">
            {explicacion}
          </Text>
        ) : null}

        {respuesta?.motivo ? (
          <Text size="sm" data-testid="estado-motivo">
            {respuesta.motivo}
          </Text>
        ) : null}

        {respuesta?.respuesta ? <ProsaConCitas prosa={respuesta.respuesta} /> : null}

        {respuesta?.citas.length ? (
          <Stack gap="xs">
            {respuesta.citas.map((cita) => (
              <ConocimientoCitaCard key={cita.citation_key} cita={cita} />
            ))}
          </Stack>
        ) : null}

        {/* Keys ONLY. The server sends no text and no provenance for an excluded
            unit, so no card can exist for one — which is task 8.4's whole point:
            the filter is server-side and this panel has no second source. */}
        {respuesta?.claves_excluidas.length ? (
          <Text size="xs" c="dimmed" data-testid="claves-excluidas">
            Unidades retiradas del contexto por su clasificación:{' '}
            {respuesta.claves_excluidas.join(', ')}
          </Text>
        ) : null}

        {respuesta?.redireccion ? (
          <BloqueRedireccion redireccion={respuesta.redireccion} parcial={false} />
        ) : null}
        {respuesta?.redireccion_parcial ? (
          <BloqueRedireccion redireccion={respuesta.redireccion_parcial} parcial={true} />
        ) : null}
      </Stack>
    </Paper>
  );
}

/**
 * The service's own state, when the surface refuses.
 *
 * The enablement 503 names WHICH of the three ANDed facts is false, and the
 * operator needs that name — "no está disponible" alone sends them looking at
 * the wrong knob. So the cause is shown as a state of the SERVICE rather than
 * folded into a generic error box.
 */
const CAUSA_LEGIBLE: Record<string, string> = {
  // `enforce_conocimiento_qa_enabled`'s three ANDed dependency facts.
  terminos_no_verificados:
    'los términos del proveedor de generación no están verificados para el modelo configurado',
  credencial_ausente: 'falta la credencial del proveedor de generación',
  embedder_no_listo: 'el servicio de embeddings no está listo',
  // The kill switch. This is the MOST likely 503 on a fresh deployment — the
  // default state of a deployment with no flag set is OFF — so leaking the raw
  // setting name here would make the commonest case the least readable one.
  conocimiento_qa_enabled: 'el buzón de consultas no está habilitado en este entorno',
  // The norms surface's own switch and its corpus precondition. Same reasoning:
  // OFF is the default state, so it is the commonest refusal and must read well.
  conocimiento_normas_enabled: 'la búsqueda de normas no está habilitada en este entorno',
  sin_corpus_activo: 'no hay ningún corpus normativo activo para consultar',
  // The quota/ceiling refusals. The server sends `type(exc).__name__`, so the
  // wire value is the Python CLASS name, not the snake_case `causa` attribute.
  CuotaAgotada: 'se agotó tu cuota diaria de consultas',
  CuotaNoConfigurada: 'la cuota diaria de consultas no está configurada',
  TechoDeGasto: 'se alcanzó el techo de gasto configurado para el período',
  TechoNoConfigurado: 'el techo de gasto no está configurado',
  VentanaNoConfigurada: 'la ventana de gasto está mal configurada',
};

/**
 * A cause the operator can read.
 *
 * Unmapped causes are still SHOWN — the identifier is the operator's only lead
 * and dropping it would be worse than an ugly one — but framed as an identifier
 * rather than dropped into the middle of a Spanish sentence as if it were one.
 */
export function causaLegible(causa: string | null): string | null {
  if (!causa) return null;
  const conocida = CAUSA_LEGIBLE[causa];
  if (conocida) return conocida;
  return `una dependencia del servicio reportó «${causa}»`;
}

export function EstadoDelServicio({
  error,
  titulo = 'El buzón de consultas no está operativo',
  testId = 'estado-servicio',
}: Readonly<{ error: ConocimientoApiError; titulo?: string; testId?: string }>) {
  const causa = causaLegible(error.causa);
  return (
    <Alert
      color="orange"
      variant="light"
      icon={<IconAlertTriangle size={16} />}
      title={titulo}
      data-testid={testId}
      data-causa={error.causa ?? ''}
    >
      <Stack gap={4}>
        {causa ? <Text size="sm">Causa: {causa}.</Text> : null}
        <Text size="sm" c="dimmed">
          {error.message}
        </Text>
      </Stack>
    </Alert>
  );
}

function esRefusalDeServicio(error: unknown): error is ConocimientoApiError {
  return error instanceof ConocimientoApiError && error.status === 503;
}

function esSesionExpirada(error: unknown): error is ConocimientoApiError {
  return error instanceof ConocimientoApiError && error.status === 401;
}

/**
 * The 401 surface `lib/api/conocimiento.ts` promises.
 *
 * That module's header justifies bypassing `apiFetch`'s one-shot 401
 * refresh/retry with "the panel says the session expired instead of silently
 * refreshing". That sentence is the whole argument for accepting the known
 * limit, so this component has to exist — without it the trade buys nothing and
 * a 401 lands in the generic red box next to a form that will keep 401ing.
 *
 * A plain anchor rather than the router's `Link`: the token this bundle is
 * holding is the thing the server just refused, and a full document load is the
 * cheapest way to be sure nothing in memory survives into the next session.
 */
export function SesionExpirada() {
  return (
    <Alert
      color="red"
      variant="light"
      icon={<IconAlertTriangle size={16} />}
      title="Tu sesión expiró"
      data-testid="sesion-expirada"
    >
      <Stack gap={4}>
        <Text size="sm">
          El servidor rechazó la sesión de este navegador. Iniciá sesión de nuevo para volver a la
          bandeja; las consultas que ya enviaste siguen encoladas.
        </Text>
        <Anchor href="/login" data-testid="sesion-expirada-login">
          Ir a iniciar sesión
        </Anchor>
      </Stack>
    </Alert>
  );
}

/**
 * What to tell the user about a REJECTED submit.
 *
 * The rate-limit envelope is `{error: "limite_de_tasa", retry_after: <s>}` and
 * carries no `detalle`, so the client's generic "No se pudo contactar el buzón
 * de consultas (error 429)" is both wrong (it was contacted) and useless (it
 * does not say when to retry). The `retry_after` the client already parses into
 * `extra` is the one piece of information the user needs, so it is spoken.
 */
export function mensajeDeErrorEnvio(error: ConocimientoApiError | Error): string {
  if (!(error instanceof ConocimientoApiError) || error.status !== 429) return error.message;

  const segundos = segundosDeReintento(error.extra.retry_after);
  const base = 'Límite de consultas alcanzado.';
  return segundos === null ? base : `${base} Probá de nuevo en ~${segundos} s.`;
}

/** `retry_after` arrives as a number of seconds; a numeric string is accepted too. */
function segundosDeReintento(valor: unknown): number | null {
  const numero = typeof valor === 'string' ? Number(valor) : valor;
  if (typeof numero !== 'number' || !Number.isFinite(numero) || numero <= 0) return null;
  return Math.ceil(numero);
}

export function ConocimientoBandeja() {
  const { items, isLoading, isError, error, refetch, enviar, isEnviando, errorEnvio } =
    useConocimientoQA();
  const [pregunta, setPregunta] = useState('');

  const enviarPregunta = () => {
    const limpia = pregunta.trim();
    if (limpia.length === 0) return;
    // Cleared on ACCEPTANCE only. Clearing here would destroy up to 2000
    // characters the moment the server says 429 or 422 — the two cases where
    // the user's next move is to send that exact same text again.
    enviar(limpia, { onSuccess: () => setPregunta('') });
  };

  const errorDeServicio = [error, errorEnvio].find(esRefusalDeServicio);
  const sesionExpirada = [error, errorEnvio].some(esSesionExpirada);
  const yaMostrado = (candidato: unknown) =>
    esRefusalDeServicio(candidato) || esSesionExpirada(candidato);
  const otroErrorEnvio = errorEnvio && !yaMostrado(errorEnvio) ? errorEnvio : null;
  const otroErrorListado = error && !yaMostrado(error) ? error : null;

  return (
    <Stack gap="lg" p="md">
      <Box>
        <Title order={2}>Consultas al corpus normativo</Title>
        <Text size="sm" c="dimmed">
          Las preguntas se encolan y las responde un procesador por lotes. La respuesta aparece acá
          cuando esté lista; nada se contesta al instante.
        </Text>
      </Box>

      {sesionExpirada ? <SesionExpirada /> : null}
      {errorDeServicio ? <EstadoDelServicio error={errorDeServicio} /> : null}

      <Paper withBorder radius="md" p="md">
        <Stack gap="sm">
          <Textarea
            label="Tu consulta"
            description={`Máximo ${CONOCIMIENTO_PREGUNTA_MAX_CHARS} caracteres. Solo consultas sobre el corpus normativo.`}
            placeholder="¿Quién aprueba el presupuesto anual?"
            autosize
            minRows={3}
            maxLength={CONOCIMIENTO_PREGUNTA_MAX_CHARS}
            value={pregunta}
            onChange={(event) => setPregunta(event.currentTarget.value)}
            data-testid="pregunta-input"
          />
          {otroErrorEnvio ? (
            <Alert color="red" variant="light" data-testid="error-envio">
              {mensajeDeErrorEnvio(otroErrorEnvio)}
            </Alert>
          ) : null}
          <Group justify="space-between">
            <Text size="xs" c="dimmed">
              {pregunta.trim().length}/{CONOCIMIENTO_PREGUNTA_MAX_CHARS}
            </Text>
            <Button
              leftSection={<IconSend size={16} />}
              onClick={enviarPregunta}
              loading={isEnviando}
              disabled={pregunta.trim().length === 0}
              data-testid="pregunta-enviar"
            >
              Enviar a la cola
            </Button>
          </Group>
        </Stack>
      </Paper>

      <Group justify="space-between">
        <Title order={3}>Bandeja</Title>
        <Button
          variant="subtle"
          size="compact-sm"
          leftSection={<IconRefresh size={14} />}
          onClick={refetch}
          data-testid="bandeja-refrescar"
        >
          Actualizar
        </Button>
      </Group>

      {otroErrorListado ? (
        <Alert color="red" variant="light" data-testid="error-bandeja">
          {otroErrorListado.message}
        </Alert>
      ) : null}

      {isLoading ? <Loader size="sm" /> : null}

      {!isLoading && items.length === 0 && !isError ? (
        <Text size="sm" c="dimmed" data-testid="bandeja-vacia">
          Todavía no enviaste ninguna consulta.
        </Text>
      ) : null}

      <Stack gap="md">
        {items.map((item) => (
          <ConocimientoItemCard key={item.id} item={item} />
        ))}
      </Stack>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Norms search + Ley 8803 draft export
// ---------------------------------------------------------------------------

/** `YYYY-MM-DD HH:MM` in the viewer's locale; an unparsable stamp is shown as sent. */
function fechaDeIngesta(iso: string): string {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  return fecha.toLocaleString('es-AR', { dateStyle: 'medium', timeStyle: 'short' });
}

/**
 * What the panel says about the units the server returned.
 *
 * The panel renders the SERVER's decision and re-decides nothing: `rango` is
 * shown only when the server sent it (the response shape itself says whether an
 * order is presented), the `nota_orden` is shown verbatim, and an empty result is
 * "no units recovered" — NOT an abstention. The surface returns units, not
 * answers, so it has no standing to say that no norm applies, and a blank list
 * must not be read as if it did.
 *
 * There is no score anywhere: the server sends none, and a number invented here
 * would be a relevance claim the recorded bar does not back.
 */
export function ResultadoNormasVista({
  resultado,
}: Readonly<{ resultado: ConocimientoResultadoNormas }>) {
  const ordenado = resultado.orden_presentado === true;
  return (
    <Stack gap="sm" data-testid="normas-resultado">
      <Group gap="xs" wrap="wrap">
        <Badge
          size="sm"
          variant="light"
          color="gray"
          title={resultado.corpus_sha}
          data-testid="normas-sha"
          data-corpus-sha={resultado.corpus_sha}
        >
          corpus {resultado.corpus_sha.slice(0, 8)}
        </Badge>
        <Text size="xs" c="dimmed" data-testid="normas-ingesta">
          ingestado el {fechaDeIngesta(resultado.ingested_at)}
        </Text>
        <Badge
          size="sm"
          variant="light"
          color={ordenado ? 'teal' : 'yellow'}
          data-testid="normas-orden-estado"
        >
          {ordenado
            ? `orden por relevancia (${resultado.orden_modo ?? resultado.modo})`
            : 'sin orden de relevancia'}
        </Badge>
      </Group>

      <Text size="sm" c="dimmed" data-testid="normas-nota-orden">
        {resultado.nota_orden}
      </Text>

      {resultado.sin_unidades ? (
        <Alert color="gray" variant="light" data-testid="normas-sin-unidades">
          No se recuperó ninguna unidad para esta consulta. Probá con otras palabras: este resultado
          no dice nada sobre si existe o no una norma aplicable.
        </Alert>
      ) : null}

      <Stack gap="xs">
        {resultado.unidades.map((unidad) => (
          <Box
            key={unidad.citation_key}
            data-testid="norma-unidad"
            data-citation-key={unidad.citation_key}
          >
            <Group gap="xs" align="flex-start" wrap="nowrap">
              {typeof unidad.rango === 'number' ? (
                <Badge size="lg" variant="outline" data-testid="norma-rango">
                  #{unidad.rango}
                </Badge>
              ) : null}
              <Box style={{ flex: 1, minWidth: 0 }}>
                <ConocimientoCitaCard cita={{ ...unidad, fuente_url: null }} />
              </Box>
            </Group>
          </Box>
        ))}
      </Stack>
    </Stack>
  );
}

/** The conditions `normas.chequear` can fail on, plus the classification block. */
const CAUSA_EXPORTACION: Record<string, string> = {
  privado: 'la unidad citada está clasificada como privada o sin clasificar',
  sha: 'el corpus activo ya no es el que el borrador fijó',
  clave: 'la unidad citada no existe en el corpus activo',
  span: 'el texto citado cambió respecto del fijado en el borrador',
  vigencia: 'la vigencia de la norma cambió respecto de la fijada en el borrador',
};

/**
 * Why a draft was NOT exported, naming the slot and the cause.
 *
 * The export is all-or-nothing, so a refusal has no partial text to show: this
 * says which citation slot failed and why, and the operator fixes the template or
 * re-pins the corpus. A 422 (`pedido_no_soportado`) and a 503 are different
 * states and are rendered by the caller, not here.
 */
function RechazoDeExportacion({ error }: Readonly<{ error: ConocimientoApiError }>) {
  const fallas = Array.isArray(error.extra.fallas)
    ? (error.extra.fallas as { slot?: unknown; causa?: unknown }[])
    : [];
  const lista = fallas.length > 0 ? fallas : [{ slot: error.extra.slot, causa: error.causa }];

  return (
    <Alert
      color="red"
      variant="light"
      icon={<IconAlertTriangle size={16} />}
      title="El borrador no se exportó"
      data-testid="pedido-rechazo"
    >
      <Stack gap={4}>
        {lista.map((falla) => (
          <Text size="sm" key={`${String(falla.slot)}-${String(falla.causa)}`}>
            Cita <Code>{String(falla.slot ?? '?')}</Code>: causa{' '}
            <Code>{String(falla.causa ?? '?')}</Code>
            {typeof falla.causa === 'string' && CAUSA_EXPORTACION[falla.causa]
              ? ` — ${CAUSA_EXPORTACION[falla.causa]}`
              : ''}
            .
          </Text>
        ))}
        <Text size="sm" c="dimmed">
          No se generó ningún archivo.
        </Text>
      </Stack>
    </Alert>
  );
}

/** Hand text to the browser as a file. Revoked right away: nothing is kept around. */
function descargarMarkdown({ nombre, contenido }: ConocimientoBorradorExportado) {
  const url = URL.createObjectURL(new Blob([contenido], { type: 'text/markdown;charset=utf-8' }));
  const ancla = document.createElement('a');
  ancla.href = url;
  ancla.download = nombre;
  ancla.click();
  URL.revokeObjectURL(url);
}

export function NormasBusqueda() {
  const {
    resultado,
    isBuscando,
    errorBusqueda,
    buscar,
    exportar,
    isExportando,
    errorExportacion,
    limpiarErrorExportacion,
  } = useConocimientoNormas();
  const [consulta, setConsulta] = useState('');
  const [pedido, setPedido] = useState('');

  const buscarAhora = () => {
    const limpia = consulta.trim();
    if (limpia.length > 0) buscar(limpia);
  };

  const exportarAhora = () => {
    if (pedido === '') return;
    exportar(pedido, { onSuccess: descargarMarkdown });
  };

  const errores = [errorBusqueda, errorExportacion];
  const errorDeServicio = errores.find(esRefusalDeServicio);
  const sesionExpirada = errores.some(esSesionExpirada);
  const rechazo =
    errorExportacion instanceof ConocimientoApiError && errorExportacion.status === 409
      ? errorExportacion
      : null;
  const yaMostrado = (candidato: unknown) =>
    esRefusalDeServicio(candidato) || esSesionExpirada(candidato) || candidato === rechazo;
  const otroErrorBusqueda = errorBusqueda && !yaMostrado(errorBusqueda) ? errorBusqueda : null;
  const otroErrorExportacion =
    errorExportacion && !yaMostrado(errorExportacion) ? errorExportacion : null;

  return (
    <Stack gap="lg" p="md" data-testid="normas-panel">
      <Box>
        <Title order={2}>Búsqueda en el corpus normativo</Title>
        <Text size="sm" c="dimmed">
          Devuelve unidades del corpus tal como están ingestadas, no respuestas. Cada resultado
          indica de qué versión del corpus sale.
        </Text>
      </Box>

      {sesionExpirada ? <SesionExpirada /> : null}
      {errorDeServicio ? (
        <EstadoDelServicio
          error={errorDeServicio}
          titulo="La búsqueda de normas no está operativa"
          testId="normas-estado-servicio"
        />
      ) : null}

      <Paper withBorder radius="md" p="md">
        <Stack gap="sm">
          <Group align="flex-end" wrap="nowrap">
            <TextInput
              style={{ flex: 1 }}
              label="Consulta"
              placeholder="canal de riego, acceso a la información pública…"
              maxLength={CONOCIMIENTO_PREGUNTA_MAX_CHARS}
              value={consulta}
              onChange={(event) => setConsulta(event.currentTarget.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') buscarAhora();
              }}
              data-testid="normas-input"
            />
            <Button
              leftSection={<IconSearch size={16} />}
              onClick={buscarAhora}
              loading={isBuscando}
              disabled={consulta.trim().length === 0}
              data-testid="normas-buscar"
            >
              Buscar
            </Button>
          </Group>
          {otroErrorBusqueda ? (
            <Alert color="red" variant="light" data-testid="normas-error">
              {otroErrorBusqueda.message}
            </Alert>
          ) : null}
        </Stack>
      </Paper>

      {resultado ? <ResultadoNormasVista resultado={resultado} /> : null}

      <Paper withBorder radius="md" p="md">
        <Stack gap="sm">
          <Title order={3}>Borradores de pedidos (Ley 8803)</Title>
          <Text size="xs" c="dimmed">
            Cada cita del borrador se verifica contra el corpus activo antes de exportar. Si una
            falla, no se genera nada.
          </Text>
          <Group align="flex-end" wrap="nowrap">
            <NativeSelect
              style={{ flex: 1 }}
              label="Pedido"
              value={pedido}
              onChange={(event) => {
                setPedido(event.currentTarget.value);
                limpiarErrorExportacion();
              }}
              data={[
                { value: '', label: 'Elegí un pedido…' },
                ...PEDIDOS_8803.map((p) => ({ value: p.id, label: p.titulo })),
              ]}
              data-testid="pedido-select"
            />
            <Button
              leftSection={<IconDownload size={16} />}
              onClick={exportarAhora}
              loading={isExportando}
              disabled={pedido === ''}
              data-testid="pedido-exportar"
            >
              Exportar borrador
            </Button>
          </Group>
          {rechazo ? <RechazoDeExportacion error={rechazo} /> : null}
          {otroErrorExportacion ? (
            <Alert color="red" variant="light" data-testid="pedido-error">
              {otroErrorExportacion.message}
            </Alert>
          ) : null}
        </Stack>
      </Paper>
    </Stack>
  );
}

/**
 * `require_admin` on the server is the real boundary (retrieval delta:37-41).
 * This gate is the IN-PAGE state: without it an operador who reaches the route
 * sees a form that 403s on submit instead of being told they lack access.
 */
export default function ConocimientoPanel() {
  return (
    <ProtectedRoute allowedRoles={['admin']}>
      <ConocimientoBandeja />
      <NormasBusqueda />
    </ProtectedRoute>
  );
}
