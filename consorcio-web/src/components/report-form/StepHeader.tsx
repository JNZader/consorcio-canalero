import { ParticipacionStepHeader } from '../ui/ParticipacionStepHeader';

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
  const status =
    showCheckIcon && isComplete ? 'completado' : isComplete ? 'disponible' : 'pendiente';

  return (
    <ParticipacionStepHeader
      step={step}
      title={title}
      subtitle={subtitle}
      status={status}
      isComplete={isComplete}
      isDisabled={!isPrimary && !isComplete}
      isDimmed={!isPrimary && !isComplete}
      showCheckIcon={showCheckIcon}
    />
  );
}
