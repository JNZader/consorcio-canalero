import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider, useMantineColorScheme } from '@mantine/core';
import ThemeToggle from '../../src/components/ThemeToggle';

const mockSetColorScheme = vi.fn();

vi.mock('@mantine/core', async () => {
  const actual = await vi.importActual<typeof import('@mantine/core')>('@mantine/core');
  return {
    ...actual,
    useMantineColorScheme: vi.fn(() => ({
      colorScheme: 'light',
      setColorScheme: mockSetColorScheme,
    })),
  };
});

vi.mock('../../src/components/ui/icons', () => ({
  IconSun: ({ size }: { size: number }) => <span data-testid="icon-sun" data-size={size} />,
  IconMoon: ({ size }: { size: number }) => <span data-testid="icon-moon" data-size={size} />,
}));

function renderToggle() {
  return render(
    <MantineProvider>
      <ThemeToggle />
    </MantineProvider>
  );
}

describe('ThemeToggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (useMantineColorScheme as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      colorScheme: 'light',
      setColorScheme: mockSetColorScheme,
    });
  });

  it('renders the mounted light-mode button with accessible label and moon icon', async () => {
    renderToggle();

    const button = await screen.findByRole('button', { name: 'Cambiar a modo oscuro' });

    expect(button).toHaveAttribute('type', 'button');
    expect(button).toHaveAttribute('data-variant', 'subtle');
    expect(button).toHaveAttribute('data-size', 'lg');
    expect(screen.getByTestId('icon-moon')).toHaveAttribute('data-size', '18');
    expect(screen.queryByTestId('icon-sun')).not.toBeInTheDocument();
  });

  it('renders dark mode with the sun icon and opposite aria-label', async () => {
    (useMantineColorScheme as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      colorScheme: 'dark',
      setColorScheme: mockSetColorScheme,
    });

    renderToggle();

    const button = await screen.findByRole('button', { name: 'Cambiar a modo claro' });

    expect(button).toHaveAttribute('data-size', 'lg');
    expect(screen.getByTestId('icon-sun')).toHaveAttribute('data-size', '18');
    expect(screen.queryByTestId('icon-moon')).not.toBeInTheDocument();
  });

  it('eventually leaves the loading placeholder after mount', async () => {
    renderToggle();

    await waitFor(() => {
      expect(screen.queryByLabelText('Cargando preferencia de tema')).not.toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /Cambiar a modo/i })).toBeInTheDocument();
  });

  it('toggles from light to dark when clicked', async () => {
    const user = userEvent.setup();
    renderToggle();

    await user.click(await screen.findByRole('button', { name: 'Cambiar a modo oscuro' }));

    expect(mockSetColorScheme).toHaveBeenCalledTimes(1);
    expect(mockSetColorScheme).toHaveBeenCalledWith('dark');
  });

  it('toggles from dark to light when clicked', async () => {
    const user = userEvent.setup();
    (useMantineColorScheme as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      colorScheme: 'dark',
      setColorScheme: mockSetColorScheme,
    });

    renderToggle();

    await user.click(await screen.findByRole('button', { name: 'Cambiar a modo claro' }));

    expect(mockSetColorScheme).toHaveBeenCalledTimes(1);
    expect(mockSetColorScheme).toHaveBeenCalledWith('light');
  });

  it('supports keyboard activation', async () => {
    const user = userEvent.setup();
    renderToggle();

    const button = await screen.findByRole('button', { name: 'Cambiar a modo oscuro' });
    button.focus();
    expect(button).toHaveFocus();

    await user.keyboard('{Enter}');

    expect(mockSetColorScheme).toHaveBeenCalledWith('dark');
  });

  it('handles repeated clicks by issuing a theme change each time', async () => {
    const user = userEvent.setup();
    renderToggle();

    const button = await screen.findByRole('button', { name: 'Cambiar a modo oscuro' });
    await user.click(button);
    await user.click(button);

    expect(mockSetColorScheme).toHaveBeenCalledTimes(2);
    expect(mockSetColorScheme).toHaveBeenNthCalledWith(1, 'dark');
    expect(mockSetColorScheme).toHaveBeenNthCalledWith(2, 'dark');
  });
});
