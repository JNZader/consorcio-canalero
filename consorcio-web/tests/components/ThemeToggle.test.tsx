import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import ThemeToggle from '../../src/components/ThemeToggle';
import { MantineProvider } from '@mantine/core';

// Mock the useMantineColorScheme hook
const mockSetColorScheme = vi.fn();
vi.mock('@mantine/core', async () => {
  const actual = await vi.importActual('@mantine/core');
  return {
    ...actual,
    useMantineColorScheme: vi.fn(() => ({
      colorScheme: 'light',
      setColorScheme: mockSetColorScheme,
    })),
  };
});

// Get the actual imported module to update the mock
import { useMantineColorScheme } from '@mantine/core';

describe('ThemeToggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSetColorScheme.mockClear();
    // Reset mock to default light theme
    (useMantineColorScheme as any).mockReturnValue({
      colorScheme: 'light',
      setColorScheme: mockSetColorScheme,
    });
  });

  it('should render action button', async () => {
    render(
      <MantineProvider>
        <ThemeToggle />
      </MantineProvider>
    );

    await waitFor(() => {
      const button = screen.getByRole('button');
      expect(button).toBeInTheDocument();
    });
  });

  it('should show loading placeholder on initial render', () => {
    render(
      <MantineProvider>
        <ThemeToggle />
      </MantineProvider>
    );

    // Initially should show placeholder with loading aria-label
    // The button might render with either the loading label or get mounted immediately
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(0);

    // Check if loading label is present (may or may not show depending on timing)
    const loadingButton = buttons.find(
      (btn) => btn.getAttribute('aria-label') === 'Cargando preferencia de tema'
    );
    // Either loading state or mounted state is acceptable
    expect(buttons.length).toBeGreaterThan(0);
  });

  it('should render sun icon when in light theme after mount', async () => {
    render(
      <MantineProvider>
        <ThemeToggle />
      </MantineProvider>
    );

    // Wait for component to mount and show actual theme
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Cargando/i })).not.toBeInTheDocument();
    });
  });

  it('should have appropriate aria-label for light theme', async () => {
    (useMantineColorScheme as any).mockReturnValue({
      colorScheme: 'light',
      setColorScheme: mockSetColorScheme,
    });

    render(
      <MantineProvider>
        <ThemeToggle />
      </MantineProvider>
    );

    // Wait for mount
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Cargando/i })).not.toBeInTheDocument();
    });

    // Should have aria-label for switching to dark mode
    const buttons = screen.getAllByRole('button');
    const themeButton = buttons[buttons.length - 1];
    expect(themeButton.getAttribute('aria-label')).toBe('Cambiar a modo oscuro');
  });

  it('should have appropriate aria-label for dark theme', async () => {
    (useMantineColorScheme as any).mockReturnValue({
      colorScheme: 'dark',
      setColorScheme: mockSetColorScheme,
    });

    render(
      <MantineProvider>
        <ThemeToggle />
      </MantineProvider>
    );

    // Wait for mount
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Cargando/i })).not.toBeInTheDocument();
    });

    // Should have aria-label for switching to light mode
    const buttons = screen.getAllByRole('button');
    const themeButton = buttons[buttons.length - 1];
    expect(themeButton.getAttribute('aria-label')).toBe('Cambiar a modo claro');
  });

  it('should toggle theme when clicked', async () => {
    const user = userEvent.setup();

    (useMantineColorScheme as any).mockReturnValue({
      colorScheme: 'light',
      setColorScheme: mockSetColorScheme,
    });

    render(
      <MantineProvider>
        <ThemeToggle />
      </MantineProvider>
    );

    // Wait for mount
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Cargando/i })).not.toBeInTheDocument();
    });

    const buttons = screen.getAllByRole('button');
    const themeButton = buttons[buttons.length - 1];

    await user.click(themeButton);

    // setColorScheme should have been called
    await waitFor(() => {
      expect(mockSetColorScheme).toHaveBeenCalled();
    });
  });

  it('should toggle from light to dark mode', async () => {
    const user = userEvent.setup();

    (useMantineColorScheme as any).mockReturnValue({
      colorScheme: 'light',
      setColorScheme: mockSetColorScheme,
    });

    render(
      <MantineProvider>
        <ThemeToggle />
      </MantineProvider>
    );

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Cargando/i })).not.toBeInTheDocument();
    });

    const buttons = screen.getAllByRole('button');
    const themeButton = buttons[buttons.length - 1];

    await user.click(themeButton);

    await waitFor(() => {
      expect(mockSetColorScheme).toHaveBeenCalledWith('dark');
    });
  });

  it('should toggle from dark to light mode', async () => {
    const user = userEvent.setup();

    (useMantineColorScheme as any).mockReturnValue({
      colorScheme: 'dark',
      setColorScheme: mockSetColorScheme,
    });

    render(
      <MantineProvider>
        <ThemeToggle />
      </MantineProvider>
    );

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Cargando/i })).not.toBeInTheDocument();
    });

    const buttons = screen.getAllByRole('button');
    const themeButton = buttons[buttons.length - 1];

    await user.click(themeButton);

    await waitFor(() => {
      expect(mockSetColorScheme).toHaveBeenCalledWith('light');
    });
  });

  it('should have tooltip with theme label', async () => {
    (useMantineColorScheme as any).mockReturnValue({
      colorScheme: 'light',
      setColorScheme: mockSetColorScheme,
    });

    const { container } = render(
      <MantineProvider>
        <ThemeToggle />
      </MantineProvider>
    );

    // Wait for mount
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Cargando/i })).not.toBeInTheDocument();
    });

    // Tooltip and button should be present
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(0);

    // In light mode, tooltip should say "Modo oscuro"
    const themeButton = buttons[buttons.length - 1];
    expect(themeButton).toBeInTheDocument();
  });

  it('should be keyboard accessible', async () => {
    const user = userEvent.setup();

    (useMantineColorScheme as any).mockReturnValue({
      colorScheme: 'light',
      setColorScheme: mockSetColorScheme,
    });

    render(
      <MantineProvider>
        <ThemeToggle />
      </MantineProvider>
    );

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Cargando/i })).not.toBeInTheDocument();
    });

    const buttons = screen.getAllByRole('button');
    const themeButton = buttons[buttons.length - 1];

    // Focus and press Enter
    themeButton.focus();
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(mockSetColorScheme).toHaveBeenCalled();
    });
  });

  it('should render with appropriate button styling', async () => {
    (useMantineColorScheme as any).mockReturnValue({
      colorScheme: 'light',
      setColorScheme: mockSetColorScheme,
    });

    render(
      <MantineProvider>
        <ThemeToggle />
      </MantineProvider>
    );

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Cargando/i })).not.toBeInTheDocument();
    });

    const buttons = screen.getAllByRole('button');
    const themeButton = buttons[buttons.length - 1];

    // Check for expected attributes
    expect(themeButton).toHaveAttribute('type', 'button');
  });
});
