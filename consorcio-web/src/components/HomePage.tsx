import {
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
import { memo } from 'react';
import type { ReactNode } from 'react';
import { IconInfoCircle } from './ui/icons';
import styles from '../styles/components/home.module.css';
import { IconChartBar, IconClipboardList, IconMap, IconSatellite } from './ui/icons';

const STATS = [
  { value: '88,277', label: 'Hectareas', sublabel: 'Area total del consorcio' },
  { value: '4', label: 'Cuencas', sublabel: 'Candil, ML, Noroeste, Norte' },
  { value: '749', label: 'Kilometros', sublabel: 'Red de caminos rurales', hasTooltip: true },
];

// Desglose de km por consorcio caminero (actualizado desde API)
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
    <Text size="xs" fw={600} mb={4}>Km por Consorcio Caminero:</Text>
    {KM_POR_CONSORCIO.map((c) => (
      <Group key={c.codigo} justify="space-between" gap="xl">
        <Text size="xs">{c.nombre}</Text>
        <Text size="xs" fw={600}>{c.km} km</Text>
      </Group>
    ))}
  </Stack>
);

const FEATURES: Array<{ icon: ReactNode; title: string; description: string; href: string }> = [
  {
    icon: <IconMap size={28} />,
    title: 'Mapa Interactivo',
    description:
      'Visualiza las cuencas, caminos y zonas inundadas con capas satelitales actualizadas.',
    href: '/mapa',
  },
  {
    icon: <IconChartBar size={28} />,
    title: 'Panel de Control',
    description:
      'Accede a estadisticas en tiempo real sobre el estado de las cuencas e infraestructura.',
    href: '/admin',
  },
  {
    icon: <IconClipboardList size={28} />,
    title: 'Sistema de Reportes',
    description: 'Reporta problemas en caminos, canales o alcantarillas con ubicacion GPS y fotos.',
    href: '/reportes',
  },
  {
    icon: <IconSatellite size={28} />,
    title: 'Analisis Satelital',
    description: 'Deteccion automatica de inundaciones usando imagenes Sentinel-1 y Sentinel-2.',
    href: '/mapa',
  },
];

/**
 * HomeContent - Contenido interno de la pagina de inicio.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 * Memoizado porque es completamente estatico (no tiene props ni state).
 */
export const HomeContent = memo(function HomeContent() {
  return (
    <Box>
      {/* Hero Section */}
      <Box className={`${styles.heroSection} ${styles.heroGradient}`}>
        <Container size="lg">
          <Stack align="center" gap="xl">
            <Badge size="lg" variant="light" color="white">
              Bell Ville, Cordoba
            </Badge>
            <Title order={1} ta="center" c="white" size={48} style={{ maxWidth: 700 }}>
              Consorcio Canalero 10 de Mayo
            </Title>
            <Text size="xl" ta="center" c="white" maw={600}>
              Sistema de gestion y monitoreo de cuencas hidricas con tecnologia satelital para la
              prevencion de inundaciones
            </Text>
            <Group mt="md">
              <Button
                size="lg"
                component="a"
                href="/mapa"
                variant="filled"
                color="acento"
                c="dark.9"
              >
                Ver Mapa
              </Button>
              <Button size="lg" component="a" href="/reportes" variant="outline" color="white">
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
        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="xl">
          {STATS.map((stat) => {
            const cardContent = (
              <Card
                key={stat.label}
                padding="lg"
                radius="md"
                withBorder
                style={{
                  background: 'light-dark(var(--mantine-color-white), var(--mantine-color-dark-6))',
                  cursor: 'hasTooltip' in stat && stat.hasTooltip ? 'help' : 'default',
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
                    {'hasTooltip' in stat && stat.hasTooltip && (
                      <IconInfoCircle size={16} color="var(--mantine-color-gray-5)" />
                    )}
                  </Group>
                  <Text size="sm" c="gray.6" ta="center">
                    {stat.sublabel}
                  </Text>
                </Stack>
              </Card>
            );

            if ('hasTooltip' in stat && stat.hasTooltip) {
              return (
                <Tooltip
                  key={stat.label}
                  label={KilometrosTooltip}
                  position="bottom"
                  withArrow
                  multiline
                  w={220}
                >
                  {cardContent}
                </Tooltip>
              );
            }

            return cardContent;
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
              Herramientas avanzadas para el monitoreo y gestion de cuencas hidricas
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
                href={feature.href}
                className={styles.featureCard}
                style={{
                  background: 'light-dark(var(--mantine-color-white), var(--mantine-color-dark-6))',
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
              href="/reportes"
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
});

/**
 * HomePage - Page component (MantineProvider is provided by main.tsx).
 */
export default function HomePage() {
  return <HomeContent />;
}
