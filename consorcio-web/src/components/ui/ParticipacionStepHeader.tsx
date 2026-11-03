import { Box, Group, Text } from '@mantine/core';
import type { ReactNode } from 'react';
import { getStepBackgroundColor } from '../suggestion-form/suggestionFormUtils';
import { IconCheck, IconShieldCheck } from './icons';

function getStepText(step: number | ReactNode): string {
  if (typeof step === 'number' || typeof step === 'string') {
    return step.toString();
  }
  return '';
}

export interface ParticipacionStepHeaderProps {
  readonly step: number | ReactNode;
  readonly title: string;
  readonly subtitle?: string;
  readonly status: string;
  readonly isComplete: boolean;
  readonly isDisabled?: boolean;
  readonly isDimmed?: boolean;
  readonly showCheckInsideCircle?: boolean;
  readonly showCheckIcon?: boolean;
  readonly badge?: ReactNode;
}

export function ParticipacionStepHeader({
  step,
  title,
  subtitle,
  status,
  isComplete,
  isDisabled,
  isDimmed,
  showCheckInsideCircle = false,
  showCheckIcon = false,
  badge,
}: ParticipacionStepHeaderProps) {
  const stepText = getStepText(step);
  const accessibleLabel = stepText
    ? `Paso ${stepText}: ${title}, ${status}`
    : `${title}, ${status}`;

  return (
    <Group gap="sm" mb="md" role="group" aria-label={accessibleLabel}>
      <Box
        aria-hidden="true"
        style={{
          width: 28,
          height: 28,
          borderRadius: '50%',
          backgroundColor: getStepBackgroundColor(isComplete, isDisabled),
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          fontSize: 13,
          fontWeight: 600,
          flexShrink: 0,
        }}
      >
        {isComplete && showCheckInsideCircle ? <IconCheck size={14} aria-hidden="true" /> : step}
      </Box>
      <Box>
        <Text fw={600} size="sm" c={isDimmed ? 'dimmed' : undefined}>
          {title}
        </Text>
        {subtitle && (
          <Text size="xs" c="gray.6">
            {subtitle}
          </Text>
        )}
      </Box>
      {badge}
      {showCheckIcon && (
        <IconShieldCheck size={20} color="var(--mantine-color-green-6)" aria-hidden="true" />
      )}
    </Group>
  );
}
