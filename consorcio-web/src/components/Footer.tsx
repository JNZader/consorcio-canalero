import { Box, Container, Divider, Group, Stack, Text } from '@mantine/core';
import { Link } from '@tanstack/react-router';
import { memo } from 'react';

import { useCanAccess } from '../stores/authStore';
import styles from '../styles/components/footer.module.css';

/**
 * FooterContent - Contenido interno del footer sin MantineProvider.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 * Memoizado porque es completamente estatico.
 */
export const FooterContent = memo(function FooterContent() {
  const showAdmin = useCanAccess(['admin', 'operador']);
  return (
    <Box
      component="footer"
      role="contentinfo"
      py="xl"
      className={styles.footer}
    >
      <Container size="xl">
        <Stack gap="lg">
          <Group justify="space-between" align="flex-start" wrap="wrap">
            <div>
              <Text size="lg" fw={700} mb="xs" c="white">
                Consorcio Canalero 10 de Mayo
              </Text>
              <Text size="sm" c="gray.3">
                Gestión de cuencas hídricas en Bell Ville, Monte Leña y San Marcos Sud (Córdoba)
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
                  <Text component={Link} to="/participacion" c="gray.3" size="sm">
                    Participación
                  </Text>
                  {showAdmin ? (
                    <Text component={Link} to="/admin" c="gray.3" size="sm">
                      Admin
                    </Text>
                  ) : null}
                  <Text component={Link} to="/privacidad" c="gray.3" size="sm">
                    Privacidad
                  </Text>
                </Stack>
              </nav>

              <Stack gap="xs">
                <Text size="sm" fw={600} c="gray.2">
                  Contacto
                </Text>
                <Text size="sm" c="gray.3">
                  Departamento Unión, Córdoba
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
              © {new Date().getFullYear()} Consorcio Canalero 10 de Mayo
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
