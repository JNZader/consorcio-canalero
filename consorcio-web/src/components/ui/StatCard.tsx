import { Badge, Card, Group, Stack, Text, ThemeIcon } from '@mantine/core';
import type { ReactNode } from 'react';

interface StatCardProps {
  readonly title: string;
  readonly value: string | number;
  readonly unit?: string;
  readonly icon?: ReactNode;
  readonly color?: string;
  readonly trend?: { readonly value: number; readonly positive: boolean };
}

export function StatCard({ title, value, unit, icon, color = 'blue', trend }: StatCardProps) {
  return (
    <Card
      padding="lg"
      radius="lg"
      withBorder
      style={{
        background: `light-dark(linear-gradient(145deg, var(--mantine-color-white) 0%, var(--mantine-color-${color}-0) 100%), var(--mantine-color-dark-6))`,
        transition: 'transform 0.2s ease, box-shadow 0.2s ease',
      }}
    >
      <Group justify="space-between" align="flex-start">
        <Stack gap="xs">
          <Text size="xs" c="gray.6" tt="uppercase" fw={700} style={{ letterSpacing: '0.5px' }}>
            {title}
          </Text>

          <Group gap="xs" align="baseline">
            <Text
              size="1.75rem"
              fw={800}
              style={{
                lineHeight: 1,
                fontVariantNumeric: 'tabular-nums',
                letterSpacing: '-0.02em',
                color: 'light-dark(var(--mantine-color-dark-5), var(--mantine-color-white))',
              }}
            >
              {typeof value === 'number' ? value.toLocaleString() : value}
            </Text>

            {trend && (
              <Badge size="sm" variant="light" color={trend.positive ? 'teal' : 'red'} radius="sm">
                {trend.positive ? '↑' : '↓'} {Math.abs(trend.value)}%
              </Badge>
            )}
          </Group>

          {unit && (
            <Text size="xs" c="gray.6" fw={500}>
              {unit}
            </Text>
          )}
        </Stack>

        {icon && (
          <ThemeIcon size={56} radius="xl" variant="light" color={color}>
            {icon}
          </ThemeIcon>
        )}
      </Group>
    </Card>
  );
}
