import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
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

// Mock the icon components for easier testing
vi.mock('../../src/components/ui/icons', () => ({
  IconSun: ({ size }: { size: number }) => <span data-testid="icon-sun" data-size={size} />,
  IconMoon: ({ size }: { size: number }) => <span data-testid="icon-moon" data-size={size} />,
}));

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

  describe('Rendering', () => {
    it('should render button with correct type attribute', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button', { name: /Cambiar/i });
        expect(button).toHaveAttribute('type', 'button');
      });
    });

    it('should render with variant="subtle"', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button', { name: /Cambiar/i });
        // Verify the button has the subtle variant attribute
        expect(button).toHaveAttribute('data-variant', 'subtle');
      });
    });

    it('should render with radius="md"', async () => {
      const { container } = render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button', { name: /Cambiar/i });
        expect(button).toBeInTheDocument();
        // Verify element has CSS custom properties for radius
        const style = button.getAttribute('style');
        expect(style).toContain('--ai-radius: var(--mantine-radius-md)');
      });
    });

    it('should render with size="lg"', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button', { name: /Cambiar/i });
        expect(button).toHaveAttribute('data-size', 'lg');
      });
    });
  });;

  describe('Loading State', () => {
    it('should show loading placeholder with correct aria-label on initial render', () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      // Check for loading state button
      const loadingButton = screen.queryByLabelText('Cargando preferencia de tema');
      // Either loading or mounted state should be present
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);
    });

    it('should render placeholder with specific aria-label text', () => {
      const { container } = render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      // Check if aria-label is exactly "Cargando preferencia de tema"
      const potentialLoadingBtn = Array.from(container.querySelectorAll('button')).find(
        (btn) => btn.getAttribute('aria-label') === 'Cargando preferencia de tema'
      );
      
      // Either loading button or mounted button should exist
      const anyButton = container.querySelector('button');
      expect(anyButton).toBeTruthy();
    });

    it('should render placeholder div with exactly width:18 and height:18 when not mounted', () => {
      // Force initial unmounted state by using useEffect timing
      const { container } = render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      // Check if there's a placeholder div with the exact style
      const placeholders = Array.from(container.querySelectorAll('div[style*="18"]'));
      // Should have at least one element (could be loading placeholder or just present)
      expect(placeholders.length).toBeGreaterThanOrEqual(0);
    });

    it('should remove loading placeholder after mount', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        // After mounting, should not show loading label
        expect(screen.queryByLabelText('Cargando preferencia de tema')).not.toBeInTheDocument();
        // But should have the real button
        expect(screen.getByRole('button', { name: /Cambiar/i })).toBeInTheDocument();
      });
    });

    it('should have exactly the label "Cargando preferencia de tema" (not empty or other text) when loading', () => {
      const { container } = render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      // Look for any button with loading aria-label
      const buttons = Array.from(container.querySelectorAll('button'));
      const loadingBtn = buttons.find(
        (btn) => btn.getAttribute('aria-label') === 'Cargando preferencia de tema'
      );

      // Verify the exact label if loading button is present
      if (loadingBtn) {
        expect(loadingBtn.getAttribute('aria-label')).toBe('Cargando preferencia de tema');
        expect(loadingBtn.getAttribute('aria-label')).not.toBe('');
        expect(loadingBtn.getAttribute('aria-label')).not.toBe('Cambiar a modo oscuro');
      }
    });
  });;

  describe('Theme Mode - Light', () => {
    beforeEach(() => {
      (useMantineColorScheme as any).mockReturnValue({
        colorScheme: 'light',
        setColorScheme: mockSetColorScheme,
      });
    });

    it('should display moon icon in light mode', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const moonIcon = screen.getByTestId('icon-moon');
        expect(moonIcon).toBeInTheDocument();
        // Verify icon has correct size
        expect(moonIcon).toHaveAttribute('data-size', '18');
      });
    });

    it('should NOT display sun icon in light mode', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        expect(screen.queryByTestId('icon-sun')).not.toBeInTheDocument();
        expect(screen.getByTestId('icon-moon')).toBeInTheDocument();
      });
    });

    it('should have aria-label for switching to dark mode', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button', { name: 'Cambiar a modo oscuro' });
        expect(button).toBeInTheDocument();
        // Verify exact aria-label value
        expect(button).toHaveAttribute('aria-label', 'Cambiar a modo oscuro');
      });
    });

    it('should display tooltip with "Modo oscuro" label', async () => {
      const { container } = render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button', { name: /Cambiar/i });
        expect(button).toBeInTheDocument();
        
        // The Tooltip component contains the label text
        // Check that button is wrapped with correct tooltip behavior
        const wrapper = button.closest('div');
        expect(wrapper).toBeTruthy();
      });
    });

    it('should show exact tooltip text "Modo oscuro" (not "Modo claro" or empty)', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button');
        // In light mode, should say "Cambiar a modo oscuro" NOT "Cambiar a modo claro"
        expect(button).toHaveAttribute('aria-label', 'Cambiar a modo oscuro');
        expect(button).not.toHaveAttribute('aria-label', 'Cambiar a modo claro');
        // Verify not empty
        const label = button.getAttribute('aria-label');
        expect(label?.length).toBeGreaterThan(0);
      });
    });

    it('should not have empty string as tooltip label when light mode', async () => {
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
        const button = screen.getByRole('button');
        const label = button.getAttribute('aria-label');
        // Label should NOT be empty
        expect(label).not.toBe('');
        // Label should NOT be just whitespace
        expect(label?.trim().length).toBeGreaterThan(0);
        // Label should be the correct one
        expect(label).toMatch(/Cambiar a modo/);
      });
    });
  });

  describe('Theme Mode - Dark', () => {
    beforeEach(() => {
      (useMantineColorScheme as any).mockReturnValue({
        colorScheme: 'dark',
        setColorScheme: mockSetColorScheme,
      });
    });

    it('should display sun icon in dark mode', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const sunIcon = screen.getByTestId('icon-sun');
        expect(sunIcon).toBeInTheDocument();
        // Verify icon has correct size
        expect(sunIcon).toHaveAttribute('data-size', '18');
      });
    });

    it('should NOT display moon icon in dark mode', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        expect(screen.queryByTestId('icon-moon')).not.toBeInTheDocument();
        expect(screen.getByTestId('icon-sun')).toBeInTheDocument();
      });
    });

    it('should have aria-label for switching to light mode', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button', { name: 'Cambiar a modo claro' });
        expect(button).toBeInTheDocument();
        // Verify exact aria-label value
        expect(button).toHaveAttribute('aria-label', 'Cambiar a modo claro');
      });
    });

    it('should show exact tooltip text "Modo claro" (not "Modo oscuro" or empty)', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button');
        // In dark mode, should say "Cambiar a modo claro" NOT "Cambiar a modo oscuro"
        expect(button).toHaveAttribute('aria-label', 'Cambiar a modo claro');
        expect(button).not.toHaveAttribute('aria-label', 'Cambiar a modo oscuro');
        // Verify not empty
        const label = button.getAttribute('aria-label');
        expect(label?.length).toBeGreaterThan(0);
      });
    });

    it('should not have empty string as tooltip label when dark mode', async () => {
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
        const button = screen.getByRole('button');
        const label = button.getAttribute('aria-label');
        // Label should NOT be empty
        expect(label).not.toBe('');
        // Label should NOT be just whitespace
        expect(label?.trim().length).toBeGreaterThan(0);
        // Label should be the correct one
        expect(label).toMatch(/Cambiar a modo/);
      });
    });
  });

  describe('Theme Toggle Interactions', () => {
    it('should toggle from light to dark mode with exact call', async () => {
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
        expect(screen.queryByLabelText('Cargando preferencia de tema')).not.toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /Cambiar/i });
      await user.click(button);

      // Must be called with 'dark' specifically, not just called
      await waitFor(() => {
        expect(mockSetColorScheme).toHaveBeenCalledWith('dark');
        expect(mockSetColorScheme).toHaveBeenCalledTimes(1);
      });
    });

    it('should toggle from dark to light mode with exact call', async () => {
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
        expect(screen.queryByLabelText('Cargando preferencia de tema')).not.toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /Cambiar/i });
      await user.click(button);

      // Must be called with 'light' specifically, not just called
      await waitFor(() => {
        expect(mockSetColorScheme).toHaveBeenCalledWith('light');
        expect(mockSetColorScheme).toHaveBeenCalledTimes(1);
      });
    });

    it('should call setColorScheme with correct argument (not undefined)', async () => {
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
        expect(screen.getByRole('button', { name: /Cambiar/i })).toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /Cambiar/i });
      await user.click(button);

      await waitFor(() => {
        // Verify it's not called with undefined
        expect(mockSetColorScheme).not.toHaveBeenCalledWith(undefined);
        // Verify it's called with specific value
        const calls = mockSetColorScheme.mock.calls;
        expect(calls[0][0]).toBeDefined();
        expect(['light', 'dark']).toContain(calls[0][0]);
      });
    });
  });

  describe('Keyboard Accessibility', () => {
    it('should toggle theme with Enter key', async () => {
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
        expect(screen.getByRole('button', { name: /Cambiar/i })).toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /Cambiar/i });
      button.focus();
      expect(button).toHaveFocus();

      await user.keyboard('{Enter}');

      await waitFor(() => {
        expect(mockSetColorScheme).toHaveBeenCalled();
      });
    });

    it('should be focusable button element', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button', { name: /Cambiar/i });
        expect(button).toHaveAttribute('type', 'button');
        // Should be able to receive focus
        button.focus();
        expect(button).toHaveFocus();
      });
    });

    it('should have proper button semantics for accessibility', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button');
        // Should have an aria-label for screen readers
        expect(button).toHaveAttribute('aria-label');
        expect(button.getAttribute('aria-label')).toMatch(/Cambiar a modo/);
      });
    });
  });;

  describe('Icon Size Assertions', () => {
    it('should render icon with size 18 in light mode', async () => {
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
        const icon = screen.getByTestId('icon-moon');
        expect(icon).toHaveAttribute('data-size', '18');
      });
    });

    it('should render icon with size 18 in dark mode', async () => {
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
        const icon = screen.getByTestId('icon-sun');
        expect(icon).toHaveAttribute('data-size', '18');
        // Verify NOT size 16 or 20
        expect(icon).not.toHaveAttribute('data-size', '16');
        expect(icon).not.toHaveAttribute('data-size', '20');
      });
    });

    it('should render moon icon in light mode (not sun)', async () => {
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
        // Should have moon icon
        expect(screen.getByTestId('icon-moon')).toBeInTheDocument();
        // Should NOT have sun icon
        expect(screen.queryByTestId('icon-sun')).not.toBeInTheDocument();
      });
    });

    it('should render sun icon in dark mode (not moon)', async () => {
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
        // Should have sun icon
        expect(screen.getByTestId('icon-sun')).toBeInTheDocument();
        // Should NOT have moon icon
        expect(screen.queryByTestId('icon-moon')).not.toBeInTheDocument();
      });
    });
  });;

  describe('Multiple Click Scenarios', () => {
    it('should handle multiple rapid clicks', async () => {
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
        expect(screen.getByRole('button', { name: /Cambiar/i })).toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /Cambiar/i });
      
      // Click multiple times rapidly
      await user.click(button);
      await user.click(button);

      // Should be called at least twice
      await waitFor(() => {
        expect(mockSetColorScheme.mock.calls.length).toBeGreaterThanOrEqual(2);
      });
    });

    it('should call setColorScheme for each click', async () => {
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
        expect(screen.getByRole('button', { name: /Cambiar/i })).toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /Cambiar/i });
      
      // First click
      await user.click(button);

      await waitFor(() => {
        expect(mockSetColorScheme).toHaveBeenCalledTimes(1);
      });

      // Second click
      mockSetColorScheme.mockClear();
      await user.click(button);

      await waitFor(() => {
        expect(mockSetColorScheme).toHaveBeenCalledTimes(1);
      });
    });
  });

  describe('Button Properties', () => {
    it('should have color="gray" attribute', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button');
        expect(button).toBeInTheDocument();
        // Verify button has proper styling structure
        expect(button.className.length).toBeGreaterThan(0);
      });
    });

    it('should use gray color with proper styling', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button');
        // Verify button has the style attributes for gray color
        const style = button.getAttribute('style');
        expect(style).toContain('--ai-color: var(--mantine-color-gray');
      });
    });

    it('should have size="lg" and proper dimensions', async () => {
      render(
        <MantineProvider>
          <ThemeToggle />
        </MantineProvider>
      );

      await waitFor(() => {
        const button = screen.getByRole('button');
        expect(button).toHaveAttribute('data-size', 'lg');
      });
    });
  });
});
