import { Card, Group, Text, ThemeIcon } from '@mantine/core';
import type { ComponentType } from 'react';

export function StatsCard({
  label,
  value,
  color,
  icon: Icon,
}: Readonly<{
  label: string;
  value: number;
  color: string;
  icon: ComponentType<{ size?: number }>;
}>) {
  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder>
      <Group justify="space-between">
        <div>
          <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
            {label}
          </Text>
          <Text size="xl" fw={700}>
            {value}
          </Text>
        </div>
        <ThemeIcon color={color} size="lg" radius="md" variant="light">
          <Icon size={20} />
        </ThemeIcon>
      </Group>
    </Card>
  );
}
