import { Box, Card, Group, Text, ThemeIcon } from '@mantine/core';
import type { ReactNode } from 'react';

export function FloodFlowStatCard({
  icon,
  label,
  value,
  color,
}: Readonly<{
  icon: ReactNode;
  label: string;
  value: string | number;
  color: string;
}>) {
  return (
    <Card withBorder radius="md" p="md">
      <Group gap="sm">
        <ThemeIcon color={color} variant="light" size="lg" radius="md">
          {icon}
        </ThemeIcon>
        <Box>
          <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.5}>
            {label}
          </Text>
          <Text fw={700} size="xl" lh={1.2}>
            {value}
          </Text>
        </Box>
      </Group>
    </Card>
  );
}
