import { Badge, CloseButton, Divider, Group, Paper, Stack, Text, Title } from '@mantine/core';
import type { Feature } from 'geojson';
import { memo } from 'react';
import styles from '../../styles/components/map.module.css';

interface InfoPanelProps {
  readonly feature: Feature | null;
  readonly onClose: () => void;
}

export const InfoPanel = memo(function InfoPanel({ feature, onClose }: InfoPanelProps) {
  if (!feature) return null;
  const properties = feature.properties ?? {};

  return (
    <Paper shadow="md" p="md" radius="md" className={styles.infoPanel}>
      <Group justify="space-between" mb="xs">
        <Title order={5}>Informacion</Title>
        <CloseButton onClick={onClose} size="sm" aria-label="Cerrar panel de informacion" />
      </Group>
      <Divider mb="xs" />
      <Stack gap={4}>
        {Object.entries(properties)
          .filter(([key]) => !key.startsWith('__'))
          .map(([key, value]) => (
            <Group key={key} gap="xs" wrap="nowrap">
              <Badge size="xs" variant="light" color="gray">
                {key}
              </Badge>
              <Text size="xs" truncate>
                {String(value)}
              </Text>
            </Group>
          ))}
      </Stack>
    </Paper>
  );
});
