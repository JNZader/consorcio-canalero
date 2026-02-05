import { Alert, Box, Container, List, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { FormularioSugerenciaContent } from './FormularioSugerencia';
import MantineProvider from './MantineProvider';
import { IconInfoCircle, IconLightbulb } from './ui/icons';

/**
 * SugerenciasContent - Contenido interno de la pagina de sugerencias sin MantineProvider.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 */
export function SugerenciasContent() {
  return (
    <Box
      style={{ background: 'light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-8))' }}
      mih="100vh"
      py="xl"
    >
      <Container size="md">
        {/* Header */}
        <Stack align="center" mb="xl">
          <IconLightbulb size={48} color="var(--mantine-color-yellow-6)" />
          <Title order={1}>Buzon de Sugerencias</Title>
          <Text c="gray.6" ta="center" maw={500}>
            Comparte tus ideas y propuestas para mejorar la gestion del consorcio. Todas las
            sugerencias son consideradas en las reuniones de la comision.
          </Text>
        </Stack>

        {/* Formulario - usa el contenido directo para evitar provider anidado */}
        <FormularioSugerenciaContent />

        {/* Info adicional */}
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg" mt="xl">
          <Alert color="blue" title="Como funciona" icon={<IconInfoCircle size={20} />}>
            <List size="sm" spacing="xs">
              <List.Item>Verifica tu contacto (email o WhatsApp) para enviar sugerencias.</List.Item>
              <List.Item>Puedes enviar hasta 3 sugerencias por dia.</List.Item>
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
      </Container>
    </Box>
  );
}

/**
 * SugerenciasPage - Standalone component with MantineProvider.
 */
export default function SugerenciasPage() {
  return (
    <MantineProvider>
      <SugerenciasContent />
    </MantineProvider>
  );
}
