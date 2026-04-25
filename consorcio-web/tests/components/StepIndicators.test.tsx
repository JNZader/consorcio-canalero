import { Badge, MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { StepHeader } from '../../src/components/report-form/StepHeader';
import { SuggestionStepIndicator } from '../../src/components/suggestion-form/SuggestionStepIndicator';

function renderWithMantine(ui: React.ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('form step indicators', () => {
  it('exposes suggestion step state without announcing decorative visual markers', () => {
    renderWithMantine(
      <SuggestionStepIndicator
        step={2}
        isComplete={false}
        isDisabled
        label="Completar sugerencia"
        badge={<Badge>Verifica tu contacto primero</Badge>}
      />
    );

    expect(
      screen.getByRole('group', { name: /paso 2: completar sugerencia, bloqueado/i })
    ).toBeInTheDocument();
    expect(screen.getByText('2')).toHaveAttribute('aria-hidden', 'true');
  });

  it('exposes completed report step state and hides decorative badge/icon', () => {
    renderWithMantine(
      <StepHeader
        step={1}
        title="Verificar identidad"
        subtitle="Verificado"
        isComplete
        showCheckIcon
      />
    );

    expect(
      screen.getByRole('group', { name: /paso 1: verificar identidad, completado/i })
    ).toBeInTheDocument();
    expect(screen.getByText('1').closest('[aria-hidden="true"]')).toBeInTheDocument();
  });

  it('does not announce an available report step as completed without a check icon', () => {
    renderWithMantine(
      <StepHeader
        step={2}
        title="Completar reporte"
        subtitle="Detalles del incidente"
        isComplete
        variant="secondary"
      />
    );

    expect(
      screen.getByRole('group', { name: /paso 2: completar reporte, disponible/i })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('group', { name: /paso 2: completar reporte, completado/i })
    ).not.toBeInTheDocument();
  });
});
