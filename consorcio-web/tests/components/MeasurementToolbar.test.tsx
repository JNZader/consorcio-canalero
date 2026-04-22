/**
 * MeasurementToolbar — progressive-disclosure floating control for the
 * measurement workflow (SDD map-measurement-tools, Batch-post refactor).
 *
 * The toolbar is a pure presentational component: it takes the current
 * mode + the "has any measurements?" flag, and wires 3 callbacks. State
 * lives in the `useMeasurement` hook that the parent owns.
 *
 * Contract pinned by these tests:
 * - Renders a SINGLE trigger ActionIcon "Medir" that opens a Mantine
 *   `Menu` with two items: "Medir distancia" and "Medir área".
 *   Mirrors the Exportar dropdown pattern from `MapActionsPanel`.
 * - When `mode !== 'idle'` the Medir trigger uses `variant="filled"`
 *   so the user has a clear visual cue that measuring mode is live.
 *   Mirrors the `#fd7e14` orange used by the draw modes in Batch B.
 * - The "Limpiar" ActionIcon is CONDITIONALLY rendered: shown ONLY
 *   when `hasMeasurements === true`. It is NOT disabled when there is
 *   nothing to clear — it is hidden entirely to reduce chrome.
 * - Clicking "Medir distancia" invokes `onStartDistance` exactly once
 *   and closes the dropdown.
 * - Clicking "Medir área" invokes `onStartArea` exactly once and
 *   closes the dropdown.
 * - Clicking "Limpiar" invokes `onClear` exactly once.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { MeasurementToolbar } from '@/components/map2d/measurement/MeasurementToolbar';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('<MeasurementToolbar />', () => {
  it('renders only the Medir trigger when idle and nothing has been measured', () => {
    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
      />,
    );

    // Medir trigger is present.
    expect(screen.getByRole('button', { name: /medir/i })).toBeInTheDocument();

    // Limpiar is NOT rendered when there's nothing to clear.
    expect(screen.queryByRole('button', { name: /limpiar/i })).not.toBeInTheDocument();

    // Exactly ONE toolbar button rendered in this state.
    expect(screen.getAllByRole('button')).toHaveLength(1);
  });

  it('renders the Limpiar button ALONGSIDE Medir when hasMeasurements is true', () => {
    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={true}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
      />,
    );

    expect(screen.getByRole('button', { name: /medir/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /limpiar/i })).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(2);
  });

  it('opens a dropdown with "Medir distancia" and "Medir área" when Medir is clicked', async () => {
    const user = userEvent.setup();

    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
      />,
    );

    await user.click(screen.getByRole('button', { name: /medir/i }));

    expect(screen.getByText('Medir distancia')).toBeInTheDocument();
    expect(screen.getByText('Medir área')).toBeInTheDocument();
  });

  it('calls onStartDistance when "Medir distancia" is selected from the dropdown', async () => {
    const user = userEvent.setup();
    const onStartDistance = vi.fn();

    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={false}
        onStartDistance={onStartDistance}
        onStartArea={() => {}}
        onClear={() => {}}
      />,
    );

    await user.click(screen.getByRole('button', { name: /medir/i }));
    await user.click(screen.getByText('Medir distancia'));

    expect(onStartDistance).toHaveBeenCalledTimes(1);
  });

  it('calls onStartArea when "Medir área" is selected from the dropdown', async () => {
    const user = userEvent.setup();
    const onStartArea = vi.fn();

    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={onStartArea}
        onClear={() => {}}
      />,
    );

    await user.click(screen.getByRole('button', { name: /medir/i }));
    await user.click(screen.getByText('Medir área'));

    expect(onStartArea).toHaveBeenCalledTimes(1);
  });

  it('calls onClear when the Limpiar button is clicked', async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();

    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={true}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={onClear}
      />,
    );

    await user.click(screen.getByRole('button', { name: /limpiar/i }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it('marks the Medir trigger as active (variant="filled") when mode is measuring-distance', () => {
    renderWithMantine(
      <MeasurementToolbar
        mode="measuring-distance"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
      />,
    );

    const medirBtn = screen.getByRole('button', { name: /medir/i });
    // Mantine renders `variant="filled"` with the `mantine-ActionIcon-root`
    // data attribute `data-variant="filled"`.
    expect(medirBtn).toHaveAttribute('data-variant', 'filled');
  });

  it('marks the Medir trigger as active (variant="filled") when mode is measuring-area', () => {
    renderWithMantine(
      <MeasurementToolbar
        mode="measuring-area"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
      />,
    );

    const medirBtn = screen.getByRole('button', { name: /medir/i });
    expect(medirBtn).toHaveAttribute('data-variant', 'filled');
  });

  it('does NOT mark the Medir trigger as filled when mode is idle', () => {
    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
      />,
    );

    const medirBtn = screen.getByRole('button', { name: /medir/i });
    expect(medirBtn).not.toHaveAttribute('data-variant', 'filled');
  });
});
