import { Container, Tabs, Text, Title } from '@mantine/core';
import { useState } from 'react';
import { IconClipboardList, IconLightbulb } from '../../ui/icons';
import ReportsPanel from '../reports/ReportsPanel';
import SugerenciasPanel from '../sugerencias/SugerenciasPanel';

const DEFAULT_TAB = 'reportes';
const TABS_VALIDAS = new Set(['reportes', 'sugerencias']);

/**
 * Tab inicial desde `?tab=` de la URL. Los redirects de las rutas viejas
 * (`/admin/sugerencias` -> `/admin/participacion?tab=sugerencias`) dependen
 * de esto: sin leer el search param, un marcador viejo de Sugerencias
 * aterrizaria en Reportes. Se lee una sola vez al montar (inicializador de
 * useState); cambiar de tab despues no toca la URL, igual que FinanzasPanel.
 */
function leerTabInicial(): string {
  const tab = new URLSearchParams(window.location.search).get('tab');
  return tab && TABS_VALIDAS.has(tab) ? tab : DEFAULT_TAB;
}

/**
 * ParticipacionPanel - contenedor unificado de Participacion Ciudadana.
 *
 * Reune las dos bandejas que el operador usa a diario (denuncias y
 * sugerencias) bajo un solo header y un par de tabs. Cada panel hijo
 * conserva TODA su logica — incluido su propio `LiveRegionProvider` —,
 * solo cede el titulo/descripcion a este contenedor.
 *
 * Montaje perezoso por pestana: `SugerenciasPanel` dispara `useCanales()`
 * (fetch del GeoJSON de relevados) apenas monta, y ese costo no se paga
 * mirando Reportes. Un panel se monta la PRIMERA vez que su tab se activa
 * y a partir de ahi queda montado (Mantine `Tabs` mantiene los paneles en
 * el DOM), asi alternar entre tabs no pierde filtros, pagina ni scroll.
 */
export default function ParticipacionPanel() {
  const [activeTab, setActiveTab] = useState<string>(leerTabInicial);
  const [visitedTabs, setVisitedTabs] = useState<Set<string>>(() => new Set([leerTabInicial()]));

  const handleTabChange = (value: string | null) => {
    if (!value) return;
    setActiveTab(value);
    setVisitedTabs((current) => (current.has(value) ? current : new Set(current).add(value)));
  };

  return (
    <Container size="xl" py="md">
      <div>
        <Title order={2}>Participacion Ciudadana</Title>
        <Text c="gray.6">
          Denuncias y sugerencias de los vecinos y de la comision, en un solo lugar
        </Text>
      </div>

      <Tabs value={activeTab} onChange={handleTabChange} mt="lg">
        <Tabs.List mb="lg">
          <Tabs.Tab value="reportes" leftSection={<IconClipboardList size={16} />}>
            Reportes
          </Tabs.Tab>
          <Tabs.Tab value="sugerencias" leftSection={<IconLightbulb size={16} />}>
            Sugerencias
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="reportes">{visitedTabs.has('reportes') && <ReportsPanel />}</Tabs.Panel>
        <Tabs.Panel value="sugerencias">
          {visitedTabs.has('sugerencias') && <SugerenciasPanel />}
        </Tabs.Panel>
      </Tabs>
    </Container>
  );
}
