import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { type ComponentProps, afterEach, describe, expect, it, vi } from 'vitest';
import {
  RECORD_VIRTUALIZE_THRESHOLD,
  ResponsiveRecordList,
  nextVirtualRecordIndex,
  type ResponsiveRecord,
} from '../../src/components/ui/ResponsiveRecordList';

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

function records(count: number): ResponsiveRecord[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `row-${index}`,
    cells: [`Persona ${index}`, `20-000000${index}`, <button key="edit" type="button">Editar {index}</button>],
  }));
}

function renderList(
  count: number,
  props?: Partial<ComponentProps<typeof ResponsiveRecordList>>
) {
  return render(
    <MantineProvider env="test">
      <ResponsiveRecordList
        label="Tabla de consorcistas"
        columns={['Consorcista', 'CUIT', 'Acciones']}
        records={records(count)}
        minWidth={680}
        virtualize={props?.virtualize}
      />
    </MantineProvider>
  );
}

describe('ResponsiveRecordList', () => {
  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it('keeps a table on the desktop breakpoint', () => {
    mockViewport(false);
    renderList(2);

    expect(screen.getByRole('table', { name: 'Tabla de consorcistas' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Consorcista' })).toBeInTheDocument();
    expect(screen.getByText('Persona 0')).toBeInTheDocument();
    expect(screen.getByText('Persona 1')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Tabla de consorcistas' })).not.toBeInTheDocument();
  });

  it('stacks records as cards below the sm breakpoint', async () => {
    mockViewport(true);
    const user = userEvent.setup();
    const onEdit = vi.fn();
    render(
      <MantineProvider env="test">
        <ResponsiveRecordList
          label="Tabla de consorcistas"
          columns={['Consorcista', 'Acciones']}
          records={[
            {
              id: 'ana',
              cells: [
                'Perez, Ana',
                <button key="edit" type="button" onClick={onEdit}>
                  Editar Ana
                </button>,
              ],
            },
          ]}
        />
      </MantineProvider>
    );

    expect(screen.getByRole('list', { name: 'Tabla de consorcistas' })).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByText('Consorcista')).toBeInTheDocument();
    expect(screen.getByText('Perez, Ana')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Editar Ana' }));
    expect(onEdit).toHaveBeenCalledOnce();
  });

  it('windows a long padron instead of mounting every row', () => {
    mockViewport(true);
    const count = RECORD_VIRTUALIZE_THRESHOLD + 20;
    renderList(count, { virtualize: true });

    const mounted = document.querySelectorAll('[data-record-id]');
    expect(mounted.length).toBeGreaterThan(0);
    expect(mounted.length).toBeLessThan(count);
    expect(screen.getByText('Persona 0')).toBeInTheDocument();
    expect(screen.queryByText(`Persona ${count - 1}`)).not.toBeInTheDocument();
  });

  it('windows the desktop table when the padron is long', () => {
    mockViewport(false);
    const count = RECORD_VIRTUALIZE_THRESHOLD + 20;
    renderList(count, { virtualize: true });

    expect(screen.getByRole('table', { name: 'Tabla de consorcistas' })).toBeInTheDocument();
    const mounted = document.querySelectorAll('[data-record-id]');
    expect(mounted.length).toBeGreaterThan(0);
    expect(mounted.length).toBeLessThan(count);
    expect(screen.queryByText(`Persona ${count - 1}`)).not.toBeInTheDocument();
  });

  it('keyboard targets stay inside the list, including rows outside the window', () => {
    const count = RECORD_VIRTUALIZE_THRESHOLD + 20;
    expect(nextVirtualRecordIndex(0, 'ArrowDown', count)).toBe(1);
    expect(nextVirtualRecordIndex(2, 'End', count)).toBe(count - 1);
    expect(nextVirtualRecordIndex(count - 1, 'Home', count)).toBe(0);
    expect(nextVirtualRecordIndex(4, 'Tab', count)).toBe(5);
    expect(nextVirtualRecordIndex(count - 1, 'Tab', count)).toBe('leave');
    expect(nextVirtualRecordIndex(0, 'Tab', count, true)).toBe('leave');
    expect(nextVirtualRecordIndex(3, 'Tab', count, true)).toBe(2);
  });

  it('End from the virtualized list reaches the last row', async () => {
    mockViewport(false);
    const user = userEvent.setup();
    const count = RECORD_VIRTUALIZE_THRESHOLD + 20;
    const view = renderList(count, { virtualize: true });
    const scroller = view.container.querySelector<HTMLElement>('[tabindex="0"]');
    expect(scroller).toBeTruthy();
    scroller?.focus();
    await user.keyboard('{End}');
    expect(await screen.findByText(`Persona ${count - 1}`)).toBeInTheDocument();
  });

  it('renders every row when the list is under the threshold', () => {
    mockViewport(false);
    renderList(3, { virtualize: true });
    expect(document.querySelectorAll('[data-record-id]')).toHaveLength(3);
  });
});
