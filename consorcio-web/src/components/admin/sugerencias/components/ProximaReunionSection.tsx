import { Badge, Group, Paper, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import type { Sugerencia } from '../../../../lib/api';
import { formatDate } from '../../../../lib/formatters';
import { IconCalendar } from '../../../ui/icons';
import { PRIORIDAD_OPTIONS } from '../constants';

export function ProximaReunionSection({
  proximaReunion,
  onViewDetail,
}: Readonly<{
  proximaReunion: Sugerencia[];
  onViewDetail: (sugerencia: Sugerencia) => void;
}>) {
  if (proximaReunion.length === 0) return null;

  return (
    <Paper
      shadow="sm"
      p="lg"
      radius="md"
      mb="xl"
      withBorder
      style={{ borderColor: 'var(--mantine-color-institucional-3)' }}
    >
      <Group gap="xs" mb="md">
        <ThemeIcon color="institucional" size="md" variant="light">
          <IconCalendar size={16} />
        </ThemeIcon>
        <Title order={4}>Temas para Próxima Reunión</Title>
        <Badge color="institucional" variant="light">
          {proximaReunion.length} temas
        </Badge>
      </Group>
      <Stack gap="xs">
        {proximaReunion.map((sug) => (
          <Paper
            key={sug.id}
            p="sm"
            radius="sm"
            role="button"
            tabIndex={0}
            aria-label={`Ver detalle de ${sug.titulo}`}
            style={{
              background: 'light-dark(var(--mantine-color-institucional-0), var(--mantine-color-dark-6))',
              cursor: 'pointer',
            }}
            onClick={() => onViewDetail(sug)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onViewDetail(sug);
              }
            }}
          >
            <Group justify="space-between">
              <div style={{ flex: 1 }}>
                <Group gap="xs">
                  <Text size="sm" fw={500}>
                    {sug.titulo}
                  </Text>
                  <Badge
                    size="xs"
                    color={sug.tipo === 'ciudadana' ? 'blue' : 'violet'}
                    variant="light"
                  >
                    {sug.tipo === 'ciudadana' ? 'Ciudadana' : 'Interna'}
                  </Badge>
                  {sug.prioridad !== 'normal' && (
                    <Badge
                      size="xs"
                      color={
                        PRIORIDAD_OPTIONS.find((p) => p.value === sug.prioridad)?.color || 'gray'
                      }
                      variant="dot"
                    >
                      {PRIORIDAD_OPTIONS.find((p) => p.value === sug.prioridad)?.label ||
                        sug.prioridad}
                    </Badge>
                  )}
                </Group>
                <Text size="xs" c="dimmed" lineClamp={1}>
                  {sug.descripcion}
                </Text>
              </div>
              {sug.fecha_reunion && (
                <Badge color="institucional" variant="outline" size="sm">
                  {formatDate(sug.fecha_reunion)}
                </Badge>
              )}
            </Group>
          </Paper>
        ))}
      </Stack>
    </Paper>
  );
}
