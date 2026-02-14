import { Alert, Box, Button, Container, List, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { SUPPORT_PHONE } from '../constants';
import { FormularioContenido } from './FormularioReporte';

/**
 * ReportesContent - Contenido interno de la pagina de reportes.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 */
export function ReportesContent() {
  return (
    <Box
      style={{ background: 'light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-8))' }}
      mih="100vh"
      py="xl"
    >
      <Container size="md">
        {/* Header */}
        <Stack align="center" mb="xl">
          <Title order={1}>Reportar Incidente</Title>
          <Text c="gray.6" ta="center" maw={500}>
            Ayudanos a mantener los canales y caminos en buen estado. Tu reporte sera revisado por
            el equipo del consorcio.
          </Text>
        </Stack>

        {/* Formulario - usa el contenido directo para evitar provider anidado */}
        <FormularioContenido />

        {/* Info adicional */}
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg" mt="xl">
          <Alert color="blue" title="Informacion importante" icon={<Text>i</Text>}>
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
              <Button component="a" href={`tel:${SUPPORT_PHONE}`} color="red" variant="light" fullWidth>
                Llamar al Consorcio
              </Button>
              <Button component="a" href="tel:103" color="orange" variant="light" fullWidth>
                Defensa Civil (103)
              </Button>
            </Stack>
          </Alert>
        </SimpleGrid>
      </Container>
    </Box>
  );
}

/**
 * ReportesPage - Page component (MantineProvider is provided by main.tsx).
 */
export default function ReportesPage() {
  return <ReportesContent />;
}
