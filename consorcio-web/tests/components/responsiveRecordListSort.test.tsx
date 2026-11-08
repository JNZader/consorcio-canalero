import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { type ComponentProps, afterEach, describe, expect, it, vi } from 'vitest';
import { ResponsiveRecordList } from '../../src/components/ui/ResponsiveRecordList';

const originalMatchMedia = window.matchMedia;

function mockViewport(compact: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: compact && String(query).includes('max-width'),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

const COLUMNS = [
  { label: 'Fecha', sortKey: 'created_at' },
  'Título',
  { label: 'Estado', sortKey: 'estado' },
];

function renderSortList(
  sorting?: ComponentProps<typeof ResponsiveRecordList>['sorting']
) {
  return render(
    <MantineProvider env="test">
      <ResponsiveRecordList
        label="Tabla de denuncias"
        columns={COLUMNS}
        records={[{ id: 'r-1', cells: ['2026-03-01', 'Título uno', 'pendiente'] }]}
        sorting={sorting}
      />
    </MantineProvider>
  );
}

describe('ResponsiveRecordList sorting', () => {
  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it('fires onChange with the sortKey when a sortable header is clicked', async () => {
    mockViewport(false);
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderSortList({ active: 'created_at', direction: 'desc', onChange });

    // Solo el componente delega: la política de toggle vive en el padre.
    await user.click(screen.getByRole('button', { name: 'Ordenar por Fecha' }));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('created_at');

    await user.click(screen.getByRole('button', { name: 'Ordenar por Estado' }));
    expect(onChange).toHaveBeenCalledTimes(2);
    expect(onChange).toHaveBeenLastCalledWith('estado');
  });

  it('reflects the active column and direction on aria-sort of the th', async () => {
    mockViewport(false);
    const user = userEvent.setup();
    const onChange = vi.fn();
    const view = renderSortList({ active: 'created_at', direction: 'desc', onChange });

    // El nombre accesible del th es el label de la columna; el
    // aria-label "Ordenar por …" vive en el botón interno.
    const fechaTh = screen.getByRole('columnheader', { name: /fecha/i });
    const estadoTh = screen.getByRole('columnheader', { name: /estado/i });
    const tituloTh = screen.getByRole('columnheader', { name: 'Título' });

    expect(fechaTh).toHaveAttribute('aria-sort', 'descending');
    // Ordenable inactiva: 'none' según el spec de ARIA.
    expect(estadoTh).toHaveAttribute('aria-sort', 'none');
    // Columna sin sortKey: sin aria-sort en absoluto.
    expect(tituloTh).not.toHaveAttribute('aria-sort');

    // El indicador visible (flecha) solo existe en la columna activa.
    const fechaButton = within(fechaTh).getByRole('button');
    expect(fechaButton.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    expect(within(estadoTh).getByRole('button').querySelector('svg')).toBeNull();

    // El padre invierte la dirección; el th lo refleja.
    await user.click(fechaButton);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('created_at');
    view.rerender(
      <MantineProvider env="test">
        <ResponsiveRecordList
          label="Tabla de denuncias"
          columns={COLUMNS}
          records={[{ id: 'r-1', cells: ['2026-03-01', 'Título uno', 'pendiente'] }]}
          sorting={{ active: 'created_at', direction: 'asc', onChange }}
        />
      </MantineProvider>
    );
    expect(screen.getByRole('columnheader', { name: /fecha/i })).toHaveAttribute(
      'aria-sort',
      'ascending'
    );
  });

  it('renders plain headers (no button, no aria-sort) when sorting is absent', () => {
    mockViewport(false);
    renderSortList(undefined);

    // Backwards compat: sin `sorting`, las columnas con sortKey se
    // comportan como columnas comunes.
    expect(screen.getByRole('columnheader', { name: 'Fecha' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Estado' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /ordenar por/i })).not.toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Fecha' })).not.toHaveAttribute('aria-sort');
  });

  it('keeps the cards view free of sort controls while still showing labels', () => {
    mockViewport(true);
    renderSortList({ active: 'created_at', direction: 'desc', onChange: vi.fn() });

    expect(screen.getByRole('list', { name: 'Tabla de denuncias' })).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /ordenar por/i })).not.toBeInTheDocument();
    // Las fichas usan col.label ?? col: el descriptor se resuelve a texto.
    expect(screen.getByText('Fecha')).toBeInTheDocument();
    expect(screen.getByText('Estado')).toBeInTheDocument();
  });
});
