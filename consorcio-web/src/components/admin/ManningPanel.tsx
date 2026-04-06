/**
 * ManningPanel — Calculadora de capacidad hidráulica (fórmula de Manning).
 *
 * Calcula caudal máximo para una sección trapezoidal dada la geometría del canal
 * y el coeficiente de rugosidad n (por material o valor directo).
 */

import {
  Alert,
  Box,
  Button,
  Card,
  Divider,
  Grid,
  Group,
  NumberInput,
  Paper,
  Select,
  Stack,
  Text,
  ThemeIcon,
  Title,
  Tooltip,
} from '@mantine/core';
import { useState } from 'react';
import { notifications } from '@mantine/notifications';
import {
  computeManning,
  type ManningRequest,
  type ManningResponse,
} from '../../lib/api/floodFlow';
import {
  IconCalculator,
  IconDroplet,
  IconInfoCircle,
  IconWaveSine,
} from '../ui/icons';

// ─── constants ───────────────────────────────────────────────────────────────

const MATERIAL_OPTIONS = [
  { value: 'hormigon',           label: 'Hormigón (n = 0.014)' },
  { value: 'hormigon_prefabricado', label: 'Hormigón prefabricado (n = 0.013)' },
  { value: 'mamposteria',        label: 'Mampostería (n = 0.020)' },
  { value: 'tierra',             label: 'Tierra (n = 0.025)' },
  { value: 'tierra_limpia',      label: 'Tierra limpia (n = 0.022)' },
  { value: 'tierra_vegetacion',  label: 'Tierra con vegetación (n = 0.030)' },
  { value: 'tierra_maleza',      label: 'Tierra con maleza (n = 0.035)' },
  { value: 'riprap',             label: 'Riprap / enrocado (n = 0.035)' },
];

// ─── helpers ─────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, decimals = 3): string {
  if (n == null) return '—';
  return n.toFixed(decimals);
}

// ─── sub-components ──────────────────────────────────────────────────────────

function ResultMetric({
  label,
  value,
  unit,
  highlighted,
  tooltip,
}: {
  label: string;
  value: string;
  unit: string;
  highlighted?: boolean;
  tooltip?: string;
}) {
  const content = (
    <Card withBorder radius="md" p="md" bg={highlighted ? 'blue.0' : undefined}>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.5} mb={4}>
        {label}
      </Text>
      <Group gap={4} align="baseline">
        <Text fw={700} size={highlighted ? 'xl' : 'lg'} c={highlighted ? 'blue.7' : undefined}>
          {value}
        </Text>
        <Text size="sm" c="dimmed">
          {unit}
        </Text>
      </Group>
    </Card>
  );

  return tooltip ? (
    <Tooltip label={tooltip} position="top" withArrow>
      <Box>{content}</Box>
    </Tooltip>
  ) : (
    content
  );
}

// ─── main component ───────────────────────────────────────────────────────────

export default function ManningPanel() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ManningResponse | null>(null);

  // form state
  const [ancho, setAncho] = useState<number | string>(3.0);
  const [profundidad, setProfundidad] = useState<number | string>(1.5);
  const [slope, setSlope] = useState<number | string>(0.001);
  const [talud, setTalud] = useState<number | string>(1.0);
  const [material, setMaterial] = useState<string | null>('tierra');
  const [coefManning, setCoefManning] = useState<number | string>('');

  async function handleCalcular() {
    const a = Number(ancho);
    const p = Number(profundidad);
    const s = Number(slope);
    const t = Number(talud);

    if (!a || !p || !s) {
      notifications.show({
        title: 'Faltan datos',
        message: 'Ingresá ancho, profundidad y pendiente.',
        color: 'red',
      });
      return;
    }

    const req: ManningRequest = {
      ancho_m: a,
      profundidad_m: p,
      slope: s,
      talud: t,
      material: material ?? undefined,
      coef_manning: coefManning !== '' ? Number(coefManning) : undefined,
    };

    setLoading(true);
    try {
      const res = await computeManning(req);
      setResult(res);
    } catch (err) {
      notifications.show({
        title: 'Error al calcular',
        message: err instanceof Error ? err.message : 'Error desconocido.',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <Stack gap="lg" p="md">
      {/* ── Header ── */}
      <Group gap="sm">
        <ThemeIcon size="xl" radius="md" variant="light" color="teal">
          <IconWaveSine size={22} />
        </ThemeIcon>
        <Box>
          <Title order={2} lh={1.2}>
            Capacidad Hidráulica — Manning
          </Title>
          <Text size="sm" c="dimmed">
            Sección trapezoidal · Q = (1/n) × A × R^(2/3) × S^(1/2)
          </Text>
        </Box>
      </Group>

      <Divider />

      {/* ── Inputs ── */}
      <Paper withBorder p="lg" radius="md">
        <Text fw={600} size="sm" mb="md">
          Geometría del canal
        </Text>
        <Grid gutter="md">
          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <NumberInput
              label="Ancho de base (m)"
              description="Ancho inferior del canal"
              placeholder="3.0"
              value={ancho}
              onChange={setAncho}
              min={0.01}
              step={0.1}
              decimalScale={2}
              disabled={loading}
            />
          </Grid.Col>

          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <NumberInput
              label="Profundidad normal (m)"
              description="Tirante hidráulico"
              placeholder="1.5"
              value={profundidad}
              onChange={setProfundidad}
              min={0.01}
              step={0.1}
              decimalScale={2}
              disabled={loading}
            />
          </Grid.Col>

          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <Tooltip
              label="Pendiente longitudinal como fracción (ej: 0.001 = 1‰)"
              position="top"
              withArrow
            >
              <NumberInput
                label="Pendiente (S)"
                description="Rise/run — ej: 0.001"
                placeholder="0.001"
                value={slope}
                onChange={setSlope}
                min={0.00001}
                step={0.0001}
                decimalScale={6}
                disabled={loading}
              />
            </Tooltip>
          </Grid.Col>

          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <Tooltip
              label="Relación H:V del talud lateral. 0 = rectangular, 1 = 1:1, 2 = 2:1"
              position="top"
              withArrow
            >
              <NumberInput
                label="Talud (H:V)"
                description="0 = rectangular"
                placeholder="1.0"
                value={talud}
                onChange={setTalud}
                min={0}
                step={0.25}
                decimalScale={2}
                disabled={loading}
              />
            </Tooltip>
          </Grid.Col>
        </Grid>

        <Text fw={600} size="sm" mt="lg" mb="md">
          Rugosidad Manning (n)
        </Text>
        <Grid gutter="md" align="flex-end">
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <Select
              label="Material del canal"
              description="Determina el coeficiente n por defecto"
              placeholder="Seleccionar material..."
              data={MATERIAL_OPTIONS}
              value={material}
              onChange={setMaterial}
              clearable
              disabled={loading}
            />
          </Grid.Col>

          <Grid.Col span={{ base: 12, sm: 4 }}>
            <NumberInput
              label="Coef. Manning n (override)"
              description="Deja vacío para usar el del material"
              placeholder="0.025"
              value={coefManning}
              onChange={setCoefManning}
              min={0.001}
              step={0.001}
              decimalScale={4}
              disabled={loading}
            />
          </Grid.Col>

          <Grid.Col span={{ base: 12, sm: 2 }}>
            <Button
              fullWidth
              leftSection={<IconCalculator size={16} />}
              loading={loading}
              onClick={handleCalcular}
            >
              Calcular
            </Button>
          </Grid.Col>
        </Grid>
      </Paper>

      {/* ── Info banner ── */}
      <Alert
        icon={<IconInfoCircle size={16} />}
        color="blue"
        variant="light"
        title="Fórmula aplicada"
      >
        Sección trapezoidal: <strong>A = (b + z·y)·y</strong>, <strong>P = b + 2y·√(1+z²)</strong>,{' '}
        <strong>R = A/P</strong>. Prioridad de n: override &gt; material &gt; defecto (tierra, 0.025).
      </Alert>

      {/* ── Results ── */}
      {result && (
        <>
          <Divider label="Resultados" labelPosition="left" />
          <Grid gutter="md">
            <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
              <ResultMetric
                label="Q capacidad"
                value={fmt(result.q_capacity_m3s)}
                unit="m³/s"
                highlighted
                tooltip="Caudal máximo para la geometría y rugosidad dadas"
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
              <ResultMetric
                label="Velocidad media"
                value={fmt(result.velocidad_ms)}
                unit="m/s"
                tooltip="v = Q / A"
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
              <ResultMetric
                label="Coef. Manning n"
                value={fmt(result.n, 4)}
                unit=""
                tooltip="Valor de n usado en el cálculo"
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <ResultMetric
                label="Área sección"
                value={fmt(result.area_m2)}
                unit="m²"
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <ResultMetric
                label="Perímetro mojado"
                value={fmt(result.perimeter_m)}
                unit="m"
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <ResultMetric
                label="Radio hidráulico"
                value={fmt(result.radio_hidraulico_m)}
                unit="m"
                tooltip="R = A / P"
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <ResultMetric
                label="Pendiente usada"
                value={(result.slope * 1000).toFixed(2)}
                unit="‰"
              />
            </Grid.Col>
          </Grid>

          {/* ── Section sketch ── */}
          <Paper withBorder radius="md" p="md">
            <Group gap="xs" mb="sm">
              <IconDroplet size={16} />
              <Text fw={600} size="sm">
                Parámetros de entrada confirmados
              </Text>
            </Group>
            <Grid gutter="xs">
              {[
                ['Ancho base', `${result.ancho_m} m`],
                ['Profundidad', `${result.profundidad_m} m`],
                ['Talud (H:V)', result.talud === 0 ? 'Rectangular' : `${result.talud}:1`],
                ['Pendiente', `${result.slope}`],
              ].map(([k, v]) => (
                <Grid.Col key={k} span={{ base: 6, sm: 3 }}>
                  <Text size="xs" c="dimmed">
                    {k}
                  </Text>
                  <Text size="sm" fw={500}>
                    {v}
                  </Text>
                </Grid.Col>
              ))}
            </Grid>
          </Paper>
        </>
      )}
    </Stack>
  );
}
