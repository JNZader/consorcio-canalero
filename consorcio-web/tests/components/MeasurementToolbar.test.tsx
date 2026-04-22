/**
 * MeasurementToolbar — 3-button floating control for the measurement
 * workflow (SDD map-measurement-tools, Batch B).
 *
 * The toolbar is a pure presentational component: it takes the current
 * mode + the "has any measurements?" flag, and wires 3 callbacks. State
 * lives in the `useMeasurement` hook that the parent owns.
 *
 * Contract pinned by these tests:
 * - Renders exactly 3 ActionIcon buttons: Distance, Area, Clear.
 * - Each button has an aria-label matching its Spanish tooltip.
 * - Clicking a button invokes the corresponding callback once.
 * - The "Distance" button is visually active when mode is
 *   'measuring-distance', and only then.
 * - The "Area" button is visually active when mode is 'measuring-area',
 *   and only then.
 * - The "Clear" button is DISABLED when `hasMeasurements` is false
 *   (nothing to clear) and ENABLED when there is at least one.
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
  it('renders 3 buttons with the expected aria-labels', () => {
    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
      />,
    );

    expect(screen.getByRole('button', { name: /medir distancia/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /medir área/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /limpiar mediciones/i })).toBeInTheDocument();
  });

  it('calls onStartDistance when the Distance button is clicked', async () => {
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

    await user.click(screen.getByRole('button', { name: /medir distancia/i }));
    expect(onStartDistance).toHaveBeenCalledTimes(1);
  });

  it('calls onStartArea when the Area button is clicked', async () => {
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

    await user.click(screen.getByRole('button', { name: /medir área/i }));
    expect(onStartArea).toHaveBeenCalledTimes(1);
  });

  it('calls onClear when the Clear button is clicked (and clearable)', async () => {
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

    await user.click(screen.getByRole('button', { name: /limpiar mediciones/i }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it('disables the Clear button when hasMeasurements is false', () => {
    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
      />,
    );

    const clearBtn = screen.getByRole('button', { name: /limpiar mediciones/i });
    expect(clearBtn).toBeDisabled();
  });

  it('enables the Clear button when hasMeasurements is true', () => {
    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={true}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
      />,
    );

    const clearBtn = screen.getByRole('button', { name: /limpiar mediciones/i });
    expect(clearBtn).toBeEnabled();
  });

  it('marks the Distance button as aria-pressed when mode is measuring-distance', () => {
    renderWithMantine(
      <MeasurementToolbar
        mode="measuring-distance"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
      />,
    );

    const distanceBtn = screen.getByRole('button', { name: /medir distancia/i });
    const areaBtn = screen.getByRole('button', { name: /medir área/i });

    expect(distanceBtn).toHaveAttribute('aria-pressed', 'true');
    expect(areaBtn).toHaveAttribute('aria-pressed', 'false');
  });

  it('marks the Area button as aria-pressed when mode is measuring-area', () => {
    renderWithMantine(
      <MeasurementToolbar
        mode="measuring-area"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
      />,
    );

    const distanceBtn = screen.getByRole('button', { name: /medir distancia/i });
    const areaBtn = screen.getByRole('button', { name: /medir área/i });

    expect(distanceBtn).toHaveAttribute('aria-pressed', 'false');
    expect(areaBtn).toHaveAttribute('aria-pressed', 'true');
  });

  it('marks neither Distance nor Area as aria-pressed when mode is idle', () => {
    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
      />,
    );

    expect(screen.getByRole('button', { name: /medir distancia/i })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    expect(screen.getByRole('button', { name: /medir área/i })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });
});
