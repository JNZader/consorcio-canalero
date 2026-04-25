import { MantineProvider } from '@mantine/core';
import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DescripcionField } from '../../src/components/report-form/ReportFormFields';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('report field errors', () => {
  it('connects the description error to the textarea with alert semantics', () => {
    renderWithMantine(
      <DescripcionField
        contactoVerificado
        error="La descripcion debe tener al menos 10 caracteres"
        getInputProps={() => ({ value: '', onChange: () => {} })}
      />
    );

    const description = screen.getByRole('textbox', { name: /descripcion/i });
    const error = screen.getByRole('alert');

    expect(description).toHaveAttribute('aria-invalid', 'true');
    expect(description).toHaveAttribute('aria-describedby', 'descripcion-error');
    expect(error).toHaveAttribute('id', 'descripcion-error');
    expect(error).toHaveTextContent(/al menos 10 caracteres/i);
  });
});
