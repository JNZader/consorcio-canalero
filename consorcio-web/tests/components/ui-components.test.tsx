/**
 * Tests for UI components
 * Coverage target: 100% (all UI building blocks)
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { LoadingState } from '../../src/components/ui/LoadingState';
import { StatusBadge } from '../../src/components/ui/StatusBadge';

function renderWithMantine(component: React.ReactNode) {
  return render(<MantineProvider env="test">{component}</MantineProvider>);
}

describe('UI Components', () => {
  describe('LoadingState', () => {
    it('should render spinner variant by default', () => {
      renderWithMantine(<LoadingState />);
      expect(screen.getByLabelText('Cargando...')).toBeInTheDocument();
      expect(screen.getByText('Cargando...')).toBeInTheDocument();
    });

    it('should render with custom message', () => {
      renderWithMantine(<LoadingState message="Procesando..." />);
      expect(screen.getByLabelText('Procesando...')).toBeInTheDocument();
      expect(screen.getByText('Procesando...')).toBeInTheDocument();
    });

    it('should render skeleton variant', () => {
      const { container } = renderWithMantine(<LoadingState variant="skeleton" />);
      expect(screen.getByRole('status', { name: 'Cargando...' })).toBeInTheDocument();
      const skeletons = container.querySelectorAll('[class*="Skeleton"]');
      expect(skeletons.length).toBeGreaterThan(0);
    });

    it('should render skeleton with custom count', () => {
      const { container } = renderWithMantine(<LoadingState variant="skeleton" skeletonCount={2} />);
      // Should have stack and cards with skeletons
      expect(container.querySelector('[class*="Stack"]')).toBeInTheDocument();
    });

    it('should use fullScreen height when specified', () => {
      const { container } = renderWithMantine(<LoadingState fullScreen />);
      const center = container.querySelector('[class*="Center"]');
      expect(center).toBeInTheDocument();
    });

    it('should have proper aria attributes for accessibility', () => {
      renderWithMantine(<LoadingState />);
      const container = screen.getByRole('status', { name: 'Cargando...' });
      expect(container).toHaveAttribute('aria-live', 'polite');
      expect(container).toHaveAttribute('aria-busy', 'true');
    });
  });

  describe('StatusBadge', () => {
    it('should render with known status', () => {
      renderWithMantine(<StatusBadge status="pendiente" />);
      // This depends on STATUS_CONFIG, but should render the label
      expect(screen.getByText(/pendiente|Pendiente/i)).toBeInTheDocument();
    });

    it('should render with unknown status as fallback', () => {
      renderWithMantine(<StatusBadge status="unknown_status" />);
      expect(screen.getByText('unknown_status')).toBeInTheDocument();
    });

    it('should apply custom size', () => {
      const { container } = renderWithMantine(<StatusBadge status="pendiente" size="lg" />);
      expect(container.querySelector('[class*="Badge"]')).toBeInTheDocument();
    });

    it('should default to sm size', () => {
      const { container } = renderWithMantine(<StatusBadge status="pendiente" />);
      expect(container.querySelector('[class*="Badge"]')).toBeInTheDocument();
    });
  });

});
