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
 *    vigencia from the text and never paraphrases anything inside a citation;
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
  Paper,
  Stack,
  Text,
  Textarea,
  Title,
} from '@mantine/core';
import { useState } from 'react';

import { useConocimientoQA } from '../../hooks/useConocimientoQA';
import {
  type ConocimientoCita,
  type ConocimientoEstado,
  type ConocimientoItem,
  type ConocimientoRedireccion,
  CONOCIMIENTO_ESTADOS,
  CONOCIMIENTO_PREGUNTA_MAX_CHARS,
  ConocimientoApiError,
} from '../../lib/api/conocimiento';
import {
  IconAlertTriangle,
  IconClock,
  IconExternalLink,
  IconInfoCircle,
  IconRefresh,
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

/** One citation card. Every field here is server-authored and shown as given. */
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
              color={cita.estado_vigencia.toUpperCase().startsWith('VIGENTE') ? 'teal' : 'red'}
              data-testid="cita-vigencia"
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
          {cita.fuente_url ? (
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
  return (
    <Alert color="blue" variant="light" icon={<IconInfoCircle size={16} />}>
      <Stack gap={4}>
        <Text size="sm" data-testid={`redireccion-${sufijo}motivo`}>
          {redireccion.motivo}
        </Text>
        <Anchor href={redireccion.superficie} data-testid={`redireccion-${sufijo}enlace`}>
          Ir a {redireccion.superficie}
        </Anchor>
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
  const presentacion = PRESENTACION_ESTADO[item.estado];
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
  terminos_no_verificados:
    'los términos del proveedor de generación no están verificados para el modelo configurado',
  credencial_ausente: 'falta la credencial del proveedor de generación',
  embedder_no_listo: 'el servicio de embeddings no está listo',
};

export function EstadoDelServicio({ error }: Readonly<{ error: ConocimientoApiError }>) {
  const causa = error.causa ? (CAUSA_LEGIBLE[error.causa] ?? error.causa) : null;
  return (
    <Alert
      color="orange"
      variant="light"
      icon={<IconAlertTriangle size={16} />}
      title="El buzón de consultas no está operativo"
      data-testid="estado-servicio"
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

function ConocimientoBandeja() {
  const { items, isLoading, isError, error, refetch, enviar, isEnviando, errorEnvio } =
    useConocimientoQA();
  const [pregunta, setPregunta] = useState('');

  const enviarPregunta = () => {
    const limpia = pregunta.trim();
    if (limpia.length === 0) return;
    enviar(limpia);
    setPregunta('');
  };

  const errorDeServicio = [error, errorEnvio].find(esRefusalDeServicio);
  const otroErrorEnvio = errorEnvio && !esRefusalDeServicio(errorEnvio) ? errorEnvio : null;
  const otroErrorListado = error && !esRefusalDeServicio(error) ? error : null;

  return (
    <Stack gap="lg" p="md">
      <Box>
        <Title order={2}>Consultas al corpus normativo</Title>
        <Text size="sm" c="dimmed">
          Las preguntas se encolan y las responde un procesador por lotes. La respuesta aparece acá
          cuando esté lista; nada se contesta al instante.
        </Text>
      </Box>

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
              {otroErrorEnvio.message}
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

/**
 * `require_admin` on the server is the real boundary (retrieval delta:37-41).
 * This gate is the IN-PAGE state: without it an operador who reaches the route
 * sees a form that 403s on submit instead of being told they lack access.
 */
export default function ConocimientoPanel() {
  return (
    <ProtectedRoute allowedRoles={['admin']}>
      <ConocimientoBandeja />
    </ProtectedRoute>
  );
}
