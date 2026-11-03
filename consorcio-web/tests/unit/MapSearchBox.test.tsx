import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MapSearchBox } from '../../src/components/map2d/MapSearchBox';
import type { IndexFile } from '../../src/types/canales';

const sampleCanalIndex: IndexFile = {
  schema_version: '1.0',
  generated_at: '2026-04-20T00:00:00Z',
  counts: { relevados: 2, propuestos: 1, total: 3 },
  relevados: [
    {
      id: 'canal-norte',
      codigo: 'CN-01',
      nombre: 'Canal Norte Principal',
      longitud_m: 2500,
    },
    {
      id: 'canal-sur',
      codigo: 'CS-02',
      nombre: 'Canal Sur Secundario',
      longitud_m: 1800,
    },
  ],
  propuestas: [],
};

describe('<MapSearchBox /> WAI-ARIA combobox & keyboard navigation (A11Y-04)', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('exposes role="combobox", listbox, option semantics and navigates with ArrowDown/ArrowUp/Enter/Escape', () => {
    const onPickCanal = vi.fn();
    const onPickParcel = vi.fn();
    const onQueryChange = vi.fn();

    render(
      <MantineProvider env="test">
        <MapSearchBox
          query="Canal"
          onQueryChange={onQueryChange}
          canalIndex={sampleCanalIndex}
          parcels={null}
          parcelsLoading={false}
          onPickCanal={onPickCanal}
          onPickParcel={onPickParcel}
        />
      </MantineProvider>
    );

    const combobox = screen.getByRole('combobox', { name: /buscar canal o cuenta/i });
    expect(combobox).toHaveAttribute('aria-expanded', 'true');
    expect(combobox).toHaveAttribute('aria-controls', 'map-search-listbox');

    const listbox = screen.getByRole('listbox', { name: /resultados de búsqueda/i });
    expect(listbox).toBeInTheDocument();

    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveAttribute('aria-selected', 'false');
    expect(options[1]).toHaveAttribute('aria-selected', 'false');

    // ArrowDown twice selects the second option
    fireEvent.keyDown(combobox, { key: 'ArrowDown' });
    expect(options[0]).toHaveAttribute('aria-selected', 'true');
    expect(combobox).toHaveAttribute('aria-activedescendant', 'map-search-option-0');

    fireEvent.keyDown(combobox, { key: 'ArrowDown' });
    expect(options[0]).toHaveAttribute('aria-selected', 'false');
    expect(options[1]).toHaveAttribute('aria-selected', 'true');
    expect(combobox).toHaveAttribute('aria-activedescendant', 'map-search-option-1');

    // ArrowUp moves back to first option
    fireEvent.keyDown(combobox, { key: 'ArrowUp' });
    expect(options[0]).toHaveAttribute('aria-selected', 'true');

    // ArrowDown again to second option, then Enter picks it and closes listbox
    fireEvent.keyDown(combobox, { key: 'ArrowDown' });
    fireEvent.keyDown(combobox, { key: 'Enter' });
    expect(onPickCanal).toHaveBeenCalledWith('canal-sur');
    expect(combobox).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    // ArrowDown reopens listbox, Escape closes it
    fireEvent.keyDown(combobox, { key: 'ArrowDown' });
    expect(combobox).toHaveAttribute('aria-expanded', 'true');
    fireEvent.keyDown(combobox, { key: 'Escape' });
    expect(combobox).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
});
