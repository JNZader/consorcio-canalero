/**
 * CanalBufferControl — the buffer-distance input for `tipo=canal_buffer` (A6).
 *
 * Shows the active canal and lets the user change the buffer half-width, but
 * commits the new value up (`onBufferChange`) ONLY on blur or Enter — never per
 * keystroke. The committed value lives in `useFichaInteraction`; the input keeps
 * a local draft while editing.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { CanalBufferControl } from '@/components/map2d/CanalBufferControl';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('<CanalBufferControl />', () => {
  it('shows the selected canal id and the current buffer value', () => {
    renderWithMantine(
      <CanalBufferControl
        canalId={42}
        bufferM={500}
        maxBufferM={2000}
        onBufferChange={() => {}}
        onClose={() => {}}
      />,
    );

    expect(screen.getByText('Canal #42')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /distancia de influencia/i })).toHaveValue('500');
  });

  it('does NOT report intermediate keystrokes — only commits once on blur', async () => {
    const user = userEvent.setup();
    const onBufferChange = vi.fn();
    renderWithMantine(
      <CanalBufferControl
        canalId={1}
        bufferM={500}
        maxBufferM={2000}
        onBufferChange={onBufferChange}
        onClose={() => {}}
      />,
    );

    const input = screen.getByRole('textbox', { name: /distancia de influencia/i });
    await user.clear(input);
    await user.type(input, '1500');

    // Typing "1500" must NOT fire a request per digit (would self-429/503 the user).
    expect(onBufferChange).not.toHaveBeenCalled();

    await user.tab(); // blur commits the final value exactly once
    expect(onBufferChange).toHaveBeenCalledTimes(1);
    expect(onBufferChange).toHaveBeenCalledWith(1500);
  });

  it('commits on Enter with the fully-typed value', async () => {
    const user = userEvent.setup();
    const onBufferChange = vi.fn();
    renderWithMantine(
      <CanalBufferControl
        canalId={1}
        bufferM={500}
        maxBufferM={2000}
        onBufferChange={onBufferChange}
        onClose={() => {}}
      />,
    );

    const input = screen.getByRole('textbox', { name: /distancia de influencia/i });
    await user.clear(input);
    await user.type(input, '800');
    expect(onBufferChange).not.toHaveBeenCalled();

    await user.keyboard('{Enter}');
    expect(onBufferChange).toHaveBeenCalledTimes(1);
    expect(onBufferChange).toHaveBeenCalledWith(800);
  });

  it('does NOT re-fire when blurring an unchanged value', async () => {
    const user = userEvent.setup();
    const onBufferChange = vi.fn();
    renderWithMantine(
      <CanalBufferControl
        canalId={1}
        bufferM={500}
        maxBufferM={2000}
        onBufferChange={onBufferChange}
        onClose={() => {}}
      />,
    );

    const input = screen.getByRole('textbox', { name: /distancia de influencia/i });
    await user.click(input); // focus without changing
    await user.tab(); // blur, draft still equals the committed 500

    expect(onBufferChange).not.toHaveBeenCalled();
  });

  it('resets an invalid draft back to the committed value on blur', async () => {
    const user = userEvent.setup();
    const onBufferChange = vi.fn();
    renderWithMantine(
      <CanalBufferControl
        canalId={1}
        bufferM={500}
        maxBufferM={2000}
        onBufferChange={onBufferChange}
        onClose={() => {}}
      />,
    );

    const input = screen.getByRole('textbox', { name: /distancia de influencia/i });
    await user.clear(input); // empty → invalid draft
    await user.tab();

    expect(onBufferChange).not.toHaveBeenCalled();
    expect(input).toHaveValue('500'); // snapped back to the source-of-truth prop
  });

  it('commits at most the wire max (never an over-cap value the server would 422)', async () => {
    const user = userEvent.setup();
    const onBufferChange = vi.fn();
    renderWithMantine(
      <CanalBufferControl
        canalId={1}
        bufferM={500}
        maxBufferM={2000}
        onBufferChange={onBufferChange}
        onClose={() => {}}
      />,
    );

    const input = screen.getByRole('textbox', { name: /distancia de influencia/i });
    await user.clear(input);
    await user.type(input, '99999');
    await user.tab();

    // clampBehavior="strict" plus the commit clamp cap the value at the wire max.
    expect(onBufferChange).toHaveBeenCalledTimes(1);
    expect(onBufferChange.mock.calls[0][0]).toBeLessThanOrEqual(2000);
  });

  it('calls onClose when the close button is clicked', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithMantine(
      <CanalBufferControl
        canalId={1}
        bufferM={500}
        maxBufferM={2000}
        onBufferChange={() => {}}
        onClose={onClose}
      />,
    );

    await user.click(screen.getByRole('button', { name: /cerrar selección de canal/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
