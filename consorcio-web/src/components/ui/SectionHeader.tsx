import { Anchor, Group, ThemeIcon, Title } from '@mantine/core';
import type { ReactNode } from 'react';

interface SectionHeaderProps {
  readonly icon?: ReactNode;
  readonly title: string;
  readonly action?: ReactNode;
  readonly actionHref?: string;
  readonly actionLabel?: string;
}

export function SectionHeader({
  icon,
  title,
  action,
  actionHref,
  actionLabel,
}: SectionHeaderProps) {
  return (
    <Group justify="space-between" mb="lg">
      <Group gap="sm">
        {icon && (
          <ThemeIcon size="lg" radius="md" variant="light" color="blue">
            {icon}
          </ThemeIcon>
        )}
        <Title order={4}>{title}</Title>
      </Group>
      {action}
      {actionHref && actionLabel && (
        <Anchor href={actionHref} size="sm" c="gray.6">
          {actionLabel} →
        </Anchor>
      )}
    </Group>
  );
}
