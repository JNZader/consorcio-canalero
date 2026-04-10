import { Box, Group, Text } from '@mantine/core';
import type { ReactNode } from 'react';
import { IconCheck } from '../ui/icons';
import { getStepBackgroundColor } from './suggestionFormUtils';

export function SuggestionStepIndicator({
  step,
  isComplete,
  isDisabled,
  label,
  badge,
}: Readonly<{
  step: number | ReactNode;
  isComplete: boolean;
  isDisabled?: boolean;
  label: string;
  badge?: ReactNode;
}>) {
  return (
    <Group gap="xs" mb="md">
      <Box
        style={{
          width: 24,
          height: 24,
          borderRadius: '50%',
          backgroundColor: getStepBackgroundColor(isComplete, isDisabled),
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          fontSize: 12,
          fontWeight: 600,
        }}
      >
        {isComplete ? <IconCheck size={14} /> : step}
      </Box>
      <Text fw={600} size="sm" c={isDisabled ? 'dimmed' : undefined}>
        {label}
      </Text>
      {badge}
    </Group>
  );
}
