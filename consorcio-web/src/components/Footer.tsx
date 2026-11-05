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
    <Box component="footer" id="footer" role="contentinfo" className={styles.footer}>
      <Container size="xl">
        <Stack gap="lg">
          <Group justify="space-between" align="flex-start" wrap="wrap">
            <div>
              <Text size="lg" fw={700} mb="xs" className={styles.title}>
                Consorcio Canalero 10 de Mayo
              </Text>
              <Text size="sm" className={styles.copy}>
                Gestión de cuencas hídricas en Bell Ville, Monte Leña y San Marcos Sud (Córdoba)
              </Text>
            </div>

            <Group gap="xl" align="flex-start">
              <nav aria-label="Enlaces del sitio">
                <Stack gap="xs">
                  <Text size="sm" fw={600} className={styles.heading}>
                    Enlaces
                  </Text>
                  <Text component={Link} to="/" size="sm" className={styles.link}>
                    Inicio
                  </Text>
                  <Text component={Link} to="/mapa" size="sm" className={styles.link}>
                    Mapa
                  </Text>
                  <Text component={Link} to="/participacion" size="sm" className={styles.link}>
                    Participación
                  </Text>
                  {showAdmin ? (
                    <Text
                      component={Link}
                      to="/admin"
                      preload={false}
                      size="sm"
                      className={styles.link}
                    >
                      Admin
                    </Text>
                  ) : null}
                  <Text component={Link} to="/privacidad" size="sm" className={styles.link}>
                    Privacidad
                  </Text>
                </Stack>
              </nav>

              <Stack gap="xs">
                <Text size="sm" fw={600} className={styles.heading}>
                  Contacto
                </Text>
                <Text size="sm" className={styles.copy}>
                  Departamento Unión, Córdoba
                </Text>
                <Text size="sm" className={styles.copy}>
                  Argentina
                </Text>
              </Stack>
            </Group>
          </Group>

          <Divider className={styles.divider} />

          <Group justify="space-between">
            <Text size="xs" className={styles.legal}>
              © {new Date().getFullYear()} Consorcio Canalero 10 de Mayo
            </Text>
            <Text size="xs" className={styles.legal}>
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
