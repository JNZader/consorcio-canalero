import { Stack, Text, ThemeIcon } from '@mantine/core';
import type { ReactNode } from 'react';
import { IconInbox } from './icons';

interface EmptyStateProps {
  readonly icon?: ReactNode;
  readonly title: string;
  readonly description?: string;
  readonly action?: ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <Stack align="center" py="xl" gap="md">
      <ThemeIcon size={56} radius="xl" variant="light" color="gray" aria-hidden="true">
        {icon || <IconInbox size={28} stroke={1.5} />}
      </ThemeIcon>
      <Text fw={500} ta="center" size="lg">
        {title}
      </Text>
      {description && (
        <Text size="sm" c="gray.6" ta="center" maw={300}>
          {description}
        </Text>
      )}
      {action}
    </Stack>
  );
}
