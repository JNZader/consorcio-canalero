import { Stack, Text, ThemeIcon } from '@mantine/core';
import { type ReactNode, useId } from 'react';
import { IconInbox } from './icons';

interface EmptyStateProps {
  readonly icon?: ReactNode;
  readonly title: string;
  readonly description?: string;
  readonly action?: ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  const titleId = useId();
  const descriptionId = useId();

  return (
    <Stack
      align="center"
      py="xl"
      gap="md"
      role="status"
      aria-live="polite"
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
    >
      <ThemeIcon size={56} radius="xl" variant="light" color="gray" aria-hidden="true">
        {icon || <IconInbox size={28} stroke={1.5} />}
      </ThemeIcon>
      <Text id={titleId} fw={500} ta="center" size="lg">
        {title}
      </Text>
      {description && (
        <Text id={descriptionId} size="sm" c="gray.6" ta="center" maw={300}>
          {description}
        </Text>
      )}
      {action}
    </Stack>
  );
}
