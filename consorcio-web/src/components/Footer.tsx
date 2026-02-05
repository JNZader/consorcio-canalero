import { Box, Container, Divider, Group, Stack, Text } from '@mantine/core';
import { Link } from '@tanstack/react-router';
import { memo } from 'react';

/**
 * FooterContent - Contenido interno del footer sin MantineProvider.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 * Memoizado porque es completamente estatico.
 */
export const FooterContent = memo(function FooterContent() {
  return (
    <Box
      component="footer"
      py="xl"
      style={{
        background: 'var(--mantine-color-gray-8)',
        borderTop: '1px solid var(--mantine-color-gray-7)',
      }}
    >
      <Container size="xl">
        <Stack gap="lg">
          <Group justify="space-between" align="flex-start" wrap="wrap">
            <div>
              <Text size="lg" fw={700} mb="xs" c="white">
                Consorcio Canalero 10 de Mayo
              </Text>
              <Text size="sm" c="gray.3">
                Gestion de cuencas hidricas en Bell Ville, Cordoba
              </Text>
            </div>

            <Group gap="xl" align="flex-start">
              <nav aria-label="Enlaces del sitio">
                <Stack gap="xs">
                  <Text size="sm" fw={600} c="gray.2">
                    Enlaces
                  </Text>
                  <Text component={Link} to="/" c="gray.3" size="sm">
                    Inicio
                  </Text>
                  <Text component={Link} to="/mapa" c="gray.3" size="sm">
                    Mapa
                  </Text>
                  <Text component={Link} to="/reportes" c="gray.3" size="sm">
                    Reportes
                  </Text>
                  <Text component={Link} to="/admin" c="gray.3" size="sm">
                    Admin
                  </Text>
                </Stack>
              </nav>

              <Stack gap="xs">
                <Text size="sm" fw={600} c="gray.2">
                  Contacto
                </Text>
                <Text size="sm" c="gray.3">
                  Bell Ville, Cordoba
                </Text>
                <Text size="sm" c="gray.3">
                  Argentina
                </Text>
              </Stack>
            </Group>
          </Group>

          <Divider color="gray.7" />

          <Group justify="space-between">
            <Text size="xs" c="gray.4">
              {new Date().getFullYear()} Consorcio Canalero 10 de Mayo
            </Text>
            <Text size="xs" c="gray.4">
              Desarrollado con Google Earth Engine + React
            </Text>
          </Group>
        </Stack>
      </Container>
    </Box>
  );
});

/**
 * Footer - Componente principal del footer.
 *
 * En la arquitectura SPA, el MantineProvider está en main.tsx,
 * por lo que exportamos FooterContent directamente.
 */
export default FooterContent;
