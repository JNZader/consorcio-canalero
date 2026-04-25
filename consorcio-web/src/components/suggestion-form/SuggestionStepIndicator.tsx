import { Box, Group, Text } from '@mantine/core';
import type { ReactNode } from 'react';
import { IconCheck } from '../ui/icons';
import { getStepBackgroundColor } from './suggestionFormUtils';

function getStepText(step: number | ReactNode): string {
  if (typeof step === 'number' || typeof step === 'string') {
    return step.toString();
  }
  return '';
}

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
  const status = isComplete ? 'completado' : isDisabled ? 'bloqueado' : 'pendiente';
  const stepText = getStepText(step);
  const accessibleLabel = stepText
    ? `Paso ${stepText}: ${label}, ${status}`
    : `${label}, ${status}`;

  return (
    <Group gap="xs" mb="md" role="group" aria-label={accessibleLabel}>
      <Box
        aria-hidden="true"
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
        {isComplete ? <IconCheck size={14} aria-hidden="true" /> : step}
      </Box>
      <Text fw={600} size="sm" c={isDisabled ? 'dimmed' : undefined}>
        {label}
      </Text>
      {badge}
    </Group>
  );
}
