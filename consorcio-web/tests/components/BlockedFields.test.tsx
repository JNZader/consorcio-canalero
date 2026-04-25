import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  DescripcionField,
  FotoField,
  SubmitButton,
  TipoProblemaField,
  UbicacionField,
} from '../../src/components/report-form/ReportFormFields';
import { FormFieldWithSkeleton } from '../../src/components/suggestion-form/suggestionFormUtils';

function renderWithMantine(ui: React.ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const reportFieldProps = {
  contactoVerificado: false,
} as const;

describe('blocked form fields', () => {
  it('announces blocked suggestion fields while contact is not verified', () => {
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

  it('announces blocked report fields while identity is not verified', () => {
    renderWithMantine(
      <>
        <TipoProblemaField
          {...reportFieldProps}
          value=""
          onChange={() => {}}
          tiposDenuncia={[]}
        />
        <DescripcionField {...reportFieldProps} getInputProps={() => ({})} />
        <UbicacionField
          {...reportFieldProps}
          ubicacion={null}
          mostrarInputManual={false}
          obteniendoUbicacion={false}
          onObtenerGPS={() => {}}
          onToggleInputManual={() => {}}
          onLocationSelect={() => {}}
          onCoordinatesChange={() => {}}
          onClearLocation={() => {}}
        />
        <FotoField {...reportFieldProps} fotoPreview={null} onDrop={() => {}} onRemove={() => {}} />
        <SubmitButton {...reportFieldProps} disabled />
      </>
    );

    expect(
      screen.getByRole('status', { name: /tipo de problema bloqueado hasta verificar identidad/i })
    ).toHaveAttribute('aria-busy', 'true');
    expect(
      screen.getByRole('status', { name: /descripcion bloqueado hasta verificar identidad/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('status', { name: /ubicacion del incidente bloqueado hasta verificar identidad/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('status', { name: /foto bloqueado hasta verificar identidad/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('status', { name: /enviar reporte bloqueado hasta verificar identidad/i })
    ).toBeInTheDocument();
  });
});
