import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  DescripcionField,
  SubmitButton,
  TipoProblemaField,
} from '../../src/components/report-form/ReportFormFields';
import { FormFieldWithSkeleton } from '../../src/components/suggestion-form/suggestionFormUtils';

function renderWithMantine(ui: React.ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('form fields before verification', () => {
  it('keeps the suggestion skeleton helper for an explicit unverified slot', () => {
    renderWithMantine(
      <FormFieldWithSkeleton label="Canal en mapa" isVerified={false} skeletonHeight={360}>
        <div>verified content</div>
      </FormFieldWithSkeleton>
    );

    expect(
      screen.getByRole('status', { name: /canal en mapa bloqueado hasta verificar contacto/i })
    ).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByText('verified content')).not.toBeInTheDocument();
  });

  it('shows the report controls even though the public form used to skeleton them', () => {
    renderWithMantine(
      <>
        <TipoProblemaField
          value=""
          onChange={() => {}}
          tiposDenuncia={[{ value: 'desborde', label: 'Desborde' }]}
        />
        <DescripcionField getInputProps={() => ({ value: '', onChange: () => {} })} />
        <SubmitButton disabled={false} />
      </>
    );

    expect(screen.getByRole('radio', { name: /desborde/i })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /descripción/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /enviar reporte/i })).toBeEnabled();
    expect(screen.queryByRole('status', { name: /bloqueado/i })).not.toBeInTheDocument();
  });
});
