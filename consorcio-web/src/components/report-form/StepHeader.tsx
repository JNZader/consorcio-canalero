import { Badge, Box, Group, Text } from '@mantine/core';
import { IconShieldCheck } from '../ui/icons';
import { getBadgeColor, getBadgeVariant } from './reportFormUtils';

interface StepHeaderProps {
  step: number;
  title: string;
  subtitle: string;
  isComplete: boolean;
  showCheckIcon?: boolean;
  variant?: 'primary' | 'secondary';
}

export function StepHeader({
  step,
  title,
  subtitle,
  isComplete,
  showCheckIcon,
  variant = 'primary',
}: Readonly<StepHeaderProps>) {
  const isPrimary = variant === 'primary';
  const badgeVariant = getBadgeVariant(isPrimary, isComplete);
  const badgeColor = getBadgeColor(isPrimary, isComplete);

  return (
    <Group gap="sm" mb="md">
      <Badge size="lg" radius="xl" variant={badgeVariant} color={badgeColor}>
        {step}
      </Badge>
      <Box>
        <Text fw={600} size="sm" c={!isPrimary && !isComplete ? 'dimmed' : undefined}>
          {title}
        </Text>
        <Text size="xs" c="gray.6">
          {subtitle}
        </Text>
      </Box>
      {showCheckIcon && (
        <IconShieldCheck size={20} color="var(--mantine-color-green-6)" aria-hidden="true" />
      )}
    </Group>
  );
}
