import {
  Accordion,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Group,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
  Tooltip,
} from '@mantine/core';
import type { ReactNode } from 'react';
import { useLandingStats } from '../hooks/useLandingStats';
import { withBasePath } from '../lib/basePath';
import styles from '../styles/components/home.module.css';
import { IconInfoCircle } from './ui/icons';
import { IconChartBar, IconClipboardList, IconLightbulb, IconMap } from './ui/icons';

function formatNumber(n: number, opts: { decimals?: number } = {}): string {
  return n.toLocaleString('es-AR', {
    minimumFractionDigits: opts.decimals ?? 0,
    maximumFractionDigits: opts.decimals ?? 0,
  });
}

// Desglose de km por consorcio caminero (estatico — viene de la APRHI, no del geojson local)
const KM_POR_CONSORCIO = [
  { nombre: 'San Marcos Sud', codigo: 'CC269', km: 219 },
  { nombre: 'Bell Ville', codigo: 'CC135', km: 136 },
  { nombre: 'Col. Gral. Bustos', codigo: 'CC391', km: 123 },
  { nombre: 'Noetinger', codigo: 'CC132', km: 72 },
  { nombre: 'Cintra', codigo: 'CC065', km: 63 },
  { nombre: 'Leones', codigo: 'CC027', km: 63 },
  { nombre: 'Chilibroste', codigo: 'CC028', km: 41 },
  { nombre: 'Morrison', codigo: 'CC055', km: 20 },
  { nombre: 'Saira', codigo: 'CC077', km: 11 },
];

const KilometrosTooltip = (
  <Stack gap={4}>
    <Text size="xs" fw={600} mb={4}>
      Km por Consorcio Caminero:
    </Text>
    {KM_POR_CONSORCIO.map((c) => (
      <Group key={c.codigo} justify="space-between" gap="xl">
        <Text size="xs">{c.nombre}</Text>
        <Text size="xs" fw={600}>
          {c.km} km
        </Text>
      </Group>
    ))}
  </Stack>
);

function CanalesTooltipContent({
  rows,
}: { rows: { label: string; tramos: number; km: number }[] }) {
  return (
    <Stack gap={4}>
      <Text size="xs" fw={600} mb={4}>
        Km por canal:
      </Text>
      {rows.map((r) => (
        <Group key={r.label} justify="space-between" gap="xl" wrap="nowrap">
          <Text size="xs" lineClamp={1} style={{ maxWidth: 220 }}>
            {r.label}
            {r.tramos > 1 ? ` · ${r.tramos} tramos` : ''}
          </Text>
          <Text size="xs" fw={600}>
            {r.km.toFixed(1)} km
          </Text>
        </Group>
      ))}
    </Stack>
  );
}

// F5-I item #9: feature copy now leads with the benefit, not the
// label. "Mapa Interactivo" → "Visualizá el estado de tus cuencas
// en tiempo real" answers the question every landing visitor has
// (what's in it for me?) before they click.
const FEATURES: Array<{ icon: ReactNode; title: string; description: string; href: string }> = [
  {
    icon: <IconMap size={28} />,
    title: 'Visualizá tus cuencas en tiempo real',
    description:
      'Mapa interactivo con cuencas, caminos rurales, suelos e imágenes satelitales actualizadas.',
    href: '/mapa',
  },
  {
    icon: <IconClipboardList size={28} />,
    title: 'Reportá problemas desde el campo',
    description:
      'Alcantarillas tapadas, caminos rotos o canales sin mantenimiento — desde tu celular con GPS y foto.',
    href: '/reportes',
  },
  {
    icon: <IconLightbulb size={28} />,
    title: 'Sugerí mejoras para tu zona',
    description:
      'Marcá la ubicación exacta y proponé mejoras. El consorcio agenda las sugerencias para revisión.',
    href: '/sugerencias',
  },
  {
    icon: <IconChartBar size={28} />,
    title: 'Gestión interna del consorcio',
    description:
      'Trámites, reuniones, finanzas y padrón de consorcistas — para operadores autenticados.',
    href: '/admin',
  },
];

// F5-I item #5: FAQ section. Direct answers to the questions every
// new visitor has — eliminates friction for a system that mixes
// public reporting + authenticated admin features.
const FAQ_ITEMS: Array<{ q: string; a: string }> = [
  {
    q: '¿Necesito una cuenta para reportar un problema?',
    a: 'Sí. Pedimos registración para evitar spam y poder darte seguimiento (notificarte cuando el operador del consorcio responde). El registro es gratuito y solo necesita tu email.',
  },
  {
    q: '¿Quién ve mis reportes?',
    a: 'Los operadores del consorcio para responder, y los consorcistas para coordinar. Los reportes no son públicos por defecto. Podés ver el estado de TU reporte en la sección "Mis denuncias" de tu perfil.',
  },
  {
    q: '¿Qué pasa con la foto + GPS que mando?',
    a: 'Se almacenan en el servidor del consorcio para que el operador pueda evaluar el problema in situ. La política completa (Ley 25.326) está en /privacidad. Podés solicitar la eliminación de tus datos cuando quieras.',
  },
  {
    q: '¿De dónde salen los datos del mapa (cuencas, suelos, caminos)?',
    a: 'Capas oficiales de la Provincia de Córdoba + APRHI (caminos) + datos catastrales del consorcio + imágenes satelitales de Google Earth Engine. Las cifras del banner (hectáreas, km) se calculan en tiempo real de los archivos geográficos.',
  },
  {
    q: '¿Cómo se garantiza que el reporte llega al operador?',
    a: 'El sistema notifica al panel del consorcio en cuanto se envía. Los operadores tienen 5 días hábiles para una primera respuesta. Si no hay respuesta en ese plazo, podés escalar por mail directo a contacto@consorcio10demayo.gob.ar.',
  },
  {
    q: '¿Es gratis?',
    a: 'Sí, completamente gratis para vecinos y consorcistas. El sistema es financiado por el consorcio y no recibe publicidad.',
  },
];

// F5-I item #2: institutional context block — answers "¿quién es
// esta gente?" for first-time visitors.
const ABOUT_BULLETS: string[] = [
  'Persona jurídica de derecho público, creada bajo la Ley Provincial de Consorcios Canaleros de Córdoba.',
  'Cubre 88.484 hectáreas de la zona de Marcos Juárez y consorcios linderos (San Marcos Sud, Bell Ville, Leones y otros 6).',
  'Trabaja en coordinación con APRHI (Agencia Provincial de Recursos Hídricos) y las consorcios viales viales municipales para mantenimiento de caminos rurales.',
  'Padrón abierto a inspección pública en sede; el sistema online es para tracking y reportes, no reemplaza la AGM presencial.',
];

/**
 * HomeContent - Contenido interno de la pagina de inicio.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 *
 * Stats (area, caminos km, canales km) are derived at runtime from the
 * shipped geojson assets via `useLandingStats`. Numbers update automatically
 * when the ETL regenerates the data files — no hardcoded values to drift.
 */
export function HomeContent() {
  const stats = useLandingStats();
  const STATS: Array<{
    value: string;
    label: string;
    sublabel: string;
    tooltip?: ReactNode;
  }> = [
    {
      value: formatNumber(stats.areaHa),
      label: 'Hectareas',
      sublabel: 'Area total del consorcio',
    },
    {
      value: stats.caminosKm == null ? '—' : formatNumber(stats.caminosKm),
      label: 'Kilometros',
      sublabel: 'Red de caminos rurales',
      tooltip: KilometrosTooltip,
    },
    {
      value: stats.canalesKm == null ? '—' : formatNumber(stats.canalesKm),
      label: 'Kilometros',
      sublabel: 'Canales existentes relevados',
      tooltip: <CanalesTooltipContent rows={stats.canalesByGroup} />,
    },
  ];

  return (
    <Box>
      {/* Hero Section */}
      <Box className={`${styles.heroSection} ${styles.heroGradient}`}>
        <Container size="lg">
          <Stack align="center" gap="xl">
            <Badge size="lg" variant="light" color="white">
              Marcos Juárez, Córdoba
            </Badge>
            <Title order={1} ta="center" c="white" size={48} style={{ maxWidth: 700 }}>
              Consorcio Canalero 10 de Mayo
            </Title>
            <Text size="xl" ta="center" c="white" maw={600}>
              Sistema colaborativo de gestion territorial para el monitoreo de cuencas, caminos
              rurales e infraestructura hidrica
            </Text>
            <Group mt="md">
              <Button
                size="lg"
                component="a"
                href={withBasePath('/mapa')}
                variant="filled"
                color="acento"
                c="dark.9"
              >
                Ver Mapa
              </Button>
              <Button
                size="lg"
                component="a"
                href={withBasePath('/reportes')}
                variant="outline"
                color="white"
              >
                Reportar Problema
              </Button>
            </Group>
          </Stack>
        </Container>

        {/* Wave decoration */}
        <Box className={styles.waveDecoration} />
      </Box>

      {/* Stats Section */}
      <Container size="lg" className={styles.statsSection}>
        <SimpleGrid
          cols={{ base: 1, sm: 3 }}
          spacing="xl"
          style={{ maxWidth: 860, margin: '0 auto' }}
        >
          {STATS.map((stat) => {
            const hasTooltip = !!stat.tooltip;
            const cardContent = (
              <Card
                padding="lg"
                radius="md"
                shadow="sm"
                style={{
                  background: 'light-dark(var(--mantine-color-white), var(--mantine-color-dark-6))',
                  borderLeft: '4px solid var(--mantine-color-institucional-6)',
                  cursor: hasTooltip ? 'help' : 'default',
                }}
              >
                <Stack align="center" gap="xs">
                  <Text size="xl" fw={700} c="institucional.7">
                    {stat.value}
                  </Text>
                  <Group gap={4}>
                    <Text size="lg" fw={600}>
                      {stat.label}
                    </Text>
                    {hasTooltip && <IconInfoCircle size={16} color="var(--mantine-color-gray-5)" />}
                  </Group>
                  <Text size="sm" c="gray.6" ta="center">
                    {stat.sublabel}
                  </Text>
                </Stack>
              </Card>
            );

            if (hasTooltip) {
              return (
                <Tooltip
                  key={stat.sublabel}
                  label={stat.tooltip}
                  position="bottom"
                  withArrow
                  multiline
                  w={280}
                >
                  {cardContent}
                </Tooltip>
              );
            }

            return <Box key={stat.sublabel}>{cardContent}</Box>;
          })}
        </SimpleGrid>
      </Container>

      {/* Features Section */}
      <Box
        style={{
          background: 'light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-8))',
        }}
        className={styles.featuresSection}
      >
        <Container size="lg">
          <Stack align="center" mb="xl">
            <Title order={2} ta="center">
              Funcionalidades
            </Title>
            <Text size="lg" c="gray.6" ta="center" maw={600}>
              Herramientas para la gestion territorial y la participacion ciudadana
            </Text>
          </Stack>

          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="lg">
            {FEATURES.map((feature) => (
              <Card
                key={feature.title}
                padding="lg"
                radius="md"
                shadow="sm"
                component="a"
                href={withBasePath(feature.href)}
                className={styles.featureCard}
                style={{
                  background: 'light-dark(var(--mantine-color-white), var(--mantine-color-dark-6))',
                  borderLeft: '4px solid var(--mantine-color-acento-5)',
                }}
              >
                <ThemeIcon size="xl" radius="md" variant="light" color="institucional" mb="md">
                  {feature.icon}
                </ThemeIcon>
                <Text fw={600} mb="xs">
                  {feature.title}
                </Text>
                <Text size="sm" c="gray.6">
                  {feature.description}
                </Text>
              </Card>
            ))}
          </SimpleGrid>
        </Container>
      </Box>

      {/* F5-I item #2: Sobre el consorcio */}
      <Container size="lg" py="xl">
        <Stack align="center" gap="lg">
          <Title order={2} ta="center">
            Sobre el consorcio
          </Title>
          <Text size="lg" c="dimmed" ta="center" maw={720}>
            Somos una entidad pública de gestión territorial focalizada en la infraestructura
            hídrica y la red de caminos rurales del sudeste cordobés.
          </Text>
          <Stack gap="sm" maw={720} w="100%">
            {ABOUT_BULLETS.map((bullet, idx) => (
              <Group key={idx} align="flex-start" wrap="nowrap" gap="sm">
                <Badge size="lg" variant="light" color="institucional" radius="xl">
                  {idx + 1}
                </Badge>
                <Text size="md" c="dimmed" style={{ flex: 1 }}>
                  {bullet}
                </Text>
              </Group>
            ))}
          </Stack>
        </Stack>
      </Container>

      {/* F5-I item #5: FAQ */}
      <Box
        style={{
          background: 'light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-8))',
        }}
        py="xl"
      >
        <Container size="md">
          <Stack align="center" mb="xl">
            <Title order={2} ta="center">
              Preguntas frecuentes
            </Title>
            <Text size="lg" c="gray.6" ta="center" maw={600}>
              Lo que la mayoría de los vecinos pregunta antes de su primer reporte.
            </Text>
          </Stack>
          <Accordion variant="separated" radius="md">
            {FAQ_ITEMS.map((item, idx) => (
              <Accordion.Item key={idx} value={`faq-${idx}`}>
                <Accordion.Control>
                  <Text fw={600}>{item.q}</Text>
                </Accordion.Control>
                <Accordion.Panel>
                  <Text size="md" c="gray.7">
                    {item.a}
                  </Text>
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
        </Container>
      </Box>

      {/* F5-I item #4: Contacto visible */}
      <Container size="md" py="xl">
        <Stack align="center" gap="md">
          <Title order={2} ta="center">
            Contactanos
          </Title>
          <Text size="md" c="gray.6" ta="center" maw={500}>
            ¿Dudas que no resolvió el FAQ? Escribinos directo — respondemos en días hábiles dentro
            de las 48 horas.
          </Text>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg" w="100%" maw={600}>
            <Card padding="lg" radius="md" shadow="sm" withBorder>
              <Stack gap={4} align="center">
                <Text size="sm" c="gray.6" tt="uppercase" fw={600}>
                  Email
                </Text>
                <Text
                  size="md"
                  fw={600}
                  c="institucional.7"
                  component="a"
                  href="mailto:contacto@consorcio10demayo.gob.ar"
                  style={{ textDecoration: 'none' }}
                >
                  contacto@consorcio10demayo.gob.ar
                </Text>
              </Stack>
            </Card>
            <Card padding="lg" radius="md" shadow="sm" withBorder>
              <Stack gap={4} align="center">
                <Text size="sm" c="gray.6" tt="uppercase" fw={600}>
                  Teléfono
                </Text>
                <Text
                  size="md"
                  fw={600}
                  c="institucional.7"
                  component="a"
                  href="tel:+543534000000"
                  style={{ textDecoration: 'none' }}
                >
                  +54 353 400-0000
                </Text>
                <Text size="xs" c="gray.6">
                  Lun a Vie 8:00–14:00
                </Text>
              </Stack>
            </Card>
          </SimpleGrid>
        </Stack>
      </Container>

      {/* CTA Section */}
      <Box className={styles.ctaSection}>
        <Container size="md">
          <Stack align="center" gap="lg">
            <Title order={2} c="white" ta="center">
              Ayuda a mantener nuestras cuencas
            </Title>
            <Text size="lg" c="white" ta="center" maw={500}>
              Reporta problemas en la infraestructura hidrica y colabora con el mantenimiento de
              caminos y canales
            </Text>
            <Button
              size="lg"
              component="a"
              href={withBasePath('/reportes')}
              variant="filled"
              color="acento"
              c="dark.9"
            >
              Realizar un Reporte
            </Button>
          </Stack>
        </Container>
      </Box>
    </Box>
  );
}

/**
 * HomePage - Page component (MantineProvider is provided by main.tsx).
 */
export default function HomePage() {
  return <HomeContent />;
}
