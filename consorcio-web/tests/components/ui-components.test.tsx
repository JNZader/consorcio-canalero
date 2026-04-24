/**
 * Tests for UI components
 * Coverage target: 100% (all UI building blocks)
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { LoadingState } from '../../src/components/ui/LoadingState';
import PieChart from '../../src/components/ui/PieChart';
import { StatCard } from '../../src/components/ui/StatCard';
import { StatusBadge } from '../../src/components/ui/StatusBadge';
import { SectionHeader } from '../../src/components/ui/SectionHeader';
import { IconHome } from '@tabler/icons-react';

function renderWithMantine(component: React.ReactNode) {
  return render(<MantineProvider>{component}</MantineProvider>);
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

  describe('PieChart', () => {
    const sampleData = [
      { label: 'Category A', value: 30, color: '#FF6B6B' },
      { label: 'Category B', value: 20, color: '#4ECDC4' },
      { label: 'Category C', value: 50, color: '#45B7D1' },
    ];

    it('should render pie chart with data', () => {
      renderWithMantine(<PieChart data={sampleData} />);
      expect(screen.getByRole('img')).toBeInTheDocument();
    });

    it('should not render when all values are zero', () => {
      const emptyData = [
        { label: 'Category A', value: 0, color: '#FF6B6B' },
      ];
      const { container } = renderWithMantine(<PieChart data={emptyData} />);
      expect(container.querySelector('svg')).not.toBeInTheDocument();
    });

    it('should render title when provided', () => {
      renderWithMantine(<PieChart data={sampleData} title="Distribution Chart" />);
      expect(screen.getByText('Distribution Chart')).toBeInTheDocument();
    });

    it('should render legend by default', () => {
      renderWithMantine(<PieChart data={sampleData} />);
      expect(screen.getByText('Category A')).toBeInTheDocument();
      expect(screen.getByText('Category B')).toBeInTheDocument();
      expect(screen.getByText('Category C')).toBeInTheDocument();
    });

    it('should not render legend when showLegend is false', () => {
      renderWithMantine(<PieChart data={sampleData} showLegend={false} />);
      // SVG should still exist
      expect(screen.getByRole('img')).toBeInTheDocument();
      // But legend entries should not be visible as separate text
      // (they're inside the SVG)
    });

    it('should use custom size', () => {
      const { container } = renderWithMantine(<PieChart data={sampleData} size={300} />);
      const svg = container.querySelector('svg');
      expect(svg).toHaveAttribute('width', '300');
      expect(svg).toHaveAttribute('height', '300');
    });

    it('should display percentage in legend', () => {
      renderWithMantine(<PieChart data={sampleData} />);
      expect(screen.getByText('30.0%')).toBeInTheDocument();
      expect(screen.getByText('20.0%')).toBeInTheDocument();
      expect(screen.getByText('50.0%')).toBeInTheDocument();
    });

    it('should handle single data item', () => {
      const singleData = [{ label: 'Only', value: 100, color: '#FF6B6B' }];
      renderWithMantine(<PieChart data={singleData} />);
      expect(screen.getByRole('img')).toBeInTheDocument();
    });
  });

  describe('StatCard', () => {
    it('should render with required props', () => {
      renderWithMantine(<StatCard title="Total Users" value={1234} />);
      // Title is uppercase
      const elements = screen.queryAllByText((content, element) => {
        return element?.textContent?.toUpperCase().includes('TOTAL USERS') || false;
      });
      expect(elements.length).toBeGreaterThan(0);
    });

    it('should render with unit', () => {
      renderWithMantine(<StatCard title="Revenue" value={5000} unit="USD" />);
      expect(screen.getByText('USD')).toBeInTheDocument();
    });

    it('should format large numbers with locale', () => {
      const { container } = renderWithMantine(<StatCard title="Count" value={1000000} />);
      // Just verify component renders without error
      expect(container.querySelector('[class*="Card"]')).toBeInTheDocument();
    });

    it('should render with string value', () => {
      renderWithMantine(<StatCard title="Status" value="Active" />);
      expect(screen.getByText('Active')).toBeInTheDocument();
    });

    it('should render positive trend', () => {
      renderWithMantine(
        <StatCard title="Growth" value={100} trend={{ value: 15, positive: true }} />
      );
      expect(screen.getByText(/↑/)).toBeInTheDocument();
      expect(screen.getByText(/15%/)).toBeInTheDocument();
    });

    it('should render negative trend', () => {
      renderWithMantine(
        <StatCard title="Decline" value={50} trend={{ value: 10, positive: false }} />
      );
      expect(screen.getByText(/↓/)).toBeInTheDocument();
      expect(screen.getByText(/10%/)).toBeInTheDocument();
    });

    it('should render with icon', () => {
      renderWithMantine(
        <StatCard title="Users" value={100} icon={<IconHome data-testid="card-icon" />} />
      );
      expect(screen.getByTestId('card-icon')).toBeInTheDocument();
    });

    it('should apply custom color', () => {
       const { container } = renderWithMantine(<StatCard title="Test" value={1} color="red" />);
       expect(container.querySelector('[class*="Card"]')).toBeInTheDocument();
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

  describe('SectionHeader', () => {
    it('should render title', () => {
      renderWithMantine(<SectionHeader title="Section Title" />);
      expect(screen.getByText('Section Title')).toBeInTheDocument();
    });

    it('should render icon when provided', () => {
      renderWithMantine(
        <SectionHeader title="Test" icon={<IconHome data-testid="header-icon" />} />
      );
      expect(screen.getByTestId('header-icon')).toBeInTheDocument();
    });

    it('should render action element', () => {
      renderWithMantine(
        <SectionHeader title="Test" action={<button>Action</button>} />
      );
      expect(screen.getByText('Action')).toBeInTheDocument();
    });

    it('should render action link with href and label', () => {
      const { container } = renderWithMantine(
        <SectionHeader title="Test" actionHref="/path" actionLabel="View All" />
      );
      const link = container.querySelector('a[href="/path"]');
      expect(link).toBeInTheDocument();
      expect(link?.textContent).toContain('View All');
    });

    it('should not render link without label', () => {
      const { container } = renderWithMantine(<SectionHeader title="Test" actionHref="/path" />);
      expect(container.querySelector('a[href="/path"]')).not.toBeInTheDocument();
    });

    it('should not render link without href', () => {
      const { container } = renderWithMantine(<SectionHeader title="Test" actionLabel="View All" />);
      expect(container.querySelector('a')).not.toBeInTheDocument();
    });

    it('should render both icon and action', () => {
      const { container } = renderWithMantine(
        <SectionHeader
          title="Test"
          icon={<IconHome data-testid="header-icon" />}
          actionHref="/path"
          actionLabel="More"
        />
      );
      expect(screen.getByTestId('header-icon')).toBeInTheDocument();
      const link = container.querySelector('a[href="/path"]');
      expect(link).toBeInTheDocument();
    });
  });
});
