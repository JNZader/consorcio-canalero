import { Button, Container, Stack, Text, Title } from '@mantine/core';
import { IconArrowLeft, IconMapPin } from './ui/icons';

/**
 * 404 Not Found page component.
 */
export default function NotFound() {
  return (
    <Container size="sm" py={80}>
      <Stack align="center" gap="lg">
        <IconMapPin size={80} color="var(--mantine-color-gray-5)" stroke={1.5} />

        <Title order={1} ta="center">
          404
        </Title>

        <Title order={2} ta="center" c="dimmed" fw={400}>
          Pagina no encontrada
        </Title>

        <Text c="dimmed" ta="center" maw={400}>
          La pagina que buscas no existe o fue movida.
          Verifica la URL o vuelve al inicio.
        </Text>

        <Button
          component="a"
          href="/"
          leftSection={<IconArrowLeft size={18} />}
          size="md"
          mt="md"
        >
          Volver al inicio
        </Button>
      </Stack>
    </Container>
  );
}
