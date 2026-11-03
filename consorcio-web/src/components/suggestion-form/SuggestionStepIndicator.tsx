import type { ReactNode } from 'react';
import { ParticipacionStepHeader } from '../ui/ParticipacionStepHeader';

export function SuggestionStepIndicator({
  step,
  isComplete,
  isDisabled,
  label,
  subtitle,
  badge,
}: Readonly<{
  step: number | ReactNode;
  isComplete: boolean;
  isDisabled?: boolean;
  label: string;
  subtitle?: string;
  badge?: ReactNode;
}>) {
  const status = isComplete ? 'completado' : isDisabled ? 'bloqueado' : 'pendiente';

  return (
    <ParticipacionStepHeader
      step={step}
      title={label}
      subtitle={subtitle}
      status={status}
      isComplete={isComplete}
      isDisabled={isDisabled}
      isDimmed={isDisabled}
      showCheckInsideCircle
      badge={badge}
    />
  );
}
