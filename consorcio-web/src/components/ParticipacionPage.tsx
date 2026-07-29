import {
  Alert,
  Box,
  Button,
  Container,
  List,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  Title,
} from '@mantine/core';
import { useState } from 'react';
import { SUPPORT_PHONE } from '../constants';
import { FormularioContenido } from './FormularioReporte';
import { FormularioSugerenciaContent } from './FormularioSugerencia';
import { IconClipboardList, IconInfoCircle, IconLightbulb } from './ui/icons';

const DEFAULT_TAB = 'reportes';
const TABS_VALIDAS = new Set(['reportes', 'sugerencias']);

/**
 * Tab inicial desde `?tab=` de la URL. Los redirects de las rutas viejas
 * (`/sugerencias` -> `/participacion?tab=sugerencias`) dependen de esto: sin
 * leer el search param, un marcador viejo del buzon aterrizaria en Reportes.
 * Se lee una sola vez al montar (inicializador de useState); cambiar de tab
 * despues no toca la URL, igual que ParticipacionPanel del admin.
 */
function leerTabInicial(): string {
  const tab = new URLSearchParams(window.location.search).get('tab');
  return tab && TABS_VALIDAS.has(tab) ? tab : DEFAULT_TAB;
}

/**
 * ReportarContent - el tab "Reportar un problema": formulario de denuncia
 * mas la ayuda de contexto (plazos, foto, emergencias) que traia la vieja
 * pagina `/reportes`.
 */
function ReportarContent() {
  return (
    <Stack gap="xl">
      {/* Formulario - usa el contenido directo para evitar provider anidado */}
      <FormularioContenido />

      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
        <Alert color="blue" title="Informacion importante" icon={<IconInfoCircle size={20} />}>
          <List size="sm" spacing="xs">
            <List.Item>Los reportes son revisados en un plazo de 24-48 horas habiles.</List.Item>
            <List.Item>
              Incluir una foto ayuda a priorizar y resolver el problema mas rapido.
            </List.Item>
            <List.Item>Recibiras una notificacion cuando tu reporte sea atendido.</List.Item>
          </List>
        </Alert>

        <Alert color="red" title="Emergencias" icon={<Text>!</Text>}>
          <Text size="sm" mb="md">
            Si la situacion es urgente (inundacion activa, peligro inminente), comunicate
            directamente:
          </Text>
          <Stack gap="xs">
            <Button
              component="a"
              href={`tel:${SUPPORT_PHONE}`}
              color="red"
              variant="light"
              fullWidth
            >
              Llamar al Consorcio
            </Button>
            <Button component="a" href="tel:103" color="orange" variant="light" fullWidth>
              Defensa Civil (103)
            </Button>
          </Stack>
        </Alert>
      </SimpleGrid>
    </Stack>
  );
}

/**
 * ProponerContent - el tab "Proponer una mejora": buzon de sugerencias con
 * la ayuda de contexto (como funciona, que temas entran) que traia la vieja
 * pagina `/sugerencias`.
 */
function ProponerContent() {
  return (
    <Stack gap="xl">
      {/* Formulario - usa el contenido directo para evitar provider anidado */}
      <FormularioSugerenciaContent />

      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
        <Alert color="blue" title="Como funciona" icon={<IconInfoCircle size={20} />}>
          <List size="sm" spacing="xs">
            <List.Item>Iniciá sesión con tu email para enviar sugerencias.</List.Item>
            <List.Item>Podés enviar hasta 5 sugerencias cada 24 horas.</List.Item>
            <List.Item>
              Las sugerencias son revisadas por la comision en sus reuniones periodicas.
            </List.Item>
          </List>
        </Alert>

        <Alert color="green" title="Tipos de sugerencias" icon={<IconLightbulb size={20} />}>
          <List size="sm" spacing="xs">
            <List.Item>Mejoras en infraestructura (canales, caminos, alcantarillas)</List.Item>
            <List.Item>Propuestas para servicios del consorcio</List.Item>
            <List.Item>Ideas sobre gestion ambiental</List.Item>
            <List.Item>Temas administrativos y de organizacion</List.Item>
          </List>
        </Alert>
      </SimpleGrid>
    </Stack>
  );
}

/**
 * ParticipacionContent - contenido interno de la pagina publica de
 * Participacion. Exportado para uso dentro de contextos que ya tienen
 * MantineProvider.
 *
 * Unifica las dos acciones que el vecino puede hacer sobre el terreno
 * (reportar un problema, proponer una mejora) bajo un solo header y un par
 * de tabs, en vez de dos paginas separadas con dos links en el navbar.
 *
 * Montaje perezoso por pestana: ambos formularios montan un mapa MapLibre,
 * y ese costo (mas el fetch de capas) no se paga mirando la otra pestana.
 * Un tab se monta la PRIMERA vez que se activa y queda montado, asi
 * alternar no pierde lo que el vecino ya habia escrito o marcado.
 */
export function ParticipacionContent() {
  const [activeTab, setActiveTab] = useState<string>(leerTabInicial);
  const [visitedTabs, setVisitedTabs] = useState<Set<string>>(() => new Set([leerTabInicial()]));

  const handleTabChange = (value: string | null) => {
    if (!value) return;
    setActiveTab(value);
    setVisitedTabs((current) => (current.has(value) ? current : new Set(current).add(value)));
  };

  return (
    <Box
      style={{ background: 'light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-8))' }}
      mih="100vh"
      py="xl"
    >
      <Container size="md">
        {/* Header unico: abarca las dos acciones */}
        <Stack align="center" mb="xl">
          <Title order={1}>Participacion</Title>
          <Text c="gray.6" ta="center" maw={560}>
            Reporta un problema en los canales y caminos, o proponé una mejora para tu zona. Todo lo
            que envies llega al equipo del consorcio y a la comision.
          </Text>
        </Stack>

        <Tabs value={activeTab} onChange={handleTabChange}>
          <Tabs.List mb="xl" grow>
            <Tabs.Tab value="reportes" leftSection={<IconClipboardList size={16} />}>
              Reportar un problema
            </Tabs.Tab>
            <Tabs.Tab value="sugerencias" leftSection={<IconLightbulb size={16} />}>
              Proponer una mejora
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="reportes">
            {visitedTabs.has('reportes') && <ReportarContent />}
          </Tabs.Panel>
          <Tabs.Panel value="sugerencias">
            {visitedTabs.has('sugerencias') && <ProponerContent />}
          </Tabs.Panel>
        </Tabs>
      </Container>
    </Box>
  );
}

/**
 * ParticipacionPage - Page component (MantineProvider is provided by main.tsx).
 */
export default function ParticipacionPage() {
  return <ParticipacionContent />;
}
