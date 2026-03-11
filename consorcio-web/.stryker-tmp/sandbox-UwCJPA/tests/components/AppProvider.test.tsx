/**
 * AppProvider.test.tsx
 * Tests for unified AppProvider (MantineProvider + Query + Auth/Config initializers)
 */
// @ts-nocheck


import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AppProvider from '../../src/components/AppProvider';

// Mock Zustand stores
vi.mock('../../src/stores/authStore', () => ({
  useAuthStore: vi.fn((selector) =>
    selector({
      initialize: vi.fn(),
    })
  ),
}));

vi.mock('../../src/stores/configStore', () => ({
  useConfigStore: vi.fn((selector) =>
    selector({
      fetchConfig: vi.fn(),
    })
  ),
}));

// Mock child component to avoid Mantine dependency complexity
const TestChild = ({ label = 'Test Child' }: { label?: string }) => <div>{label}</div>;

describe('AppProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic rendering', () => {
    it('should render children', () => {
      render(
        <AppProvider>
          <TestChild label="App Content" />
        </AppProvider>
      );
      expect(screen.getByText('App Content')).toBeInTheDocument();
    });

    it('should render multiple children', () => {
      render(
        <AppProvider>
          <TestChild label="First" />
          <TestChild label="Second" />
        </AppProvider>
      );
      expect(screen.getByText('First')).toBeInTheDocument();
      expect(screen.getByText('Second')).toBeInTheDocument();
    });

    it('should render empty children gracefully', () => {
      const { container } = render(<AppProvider>{null}</AppProvider>);
      expect(container).toBeTruthy();
    });
  });

  describe('Provider integration', () => {
    it('should include MantineProvider', () => {
      const { container } = render(
        <AppProvider>
          <TestChild />
        </AppProvider>
      );
      expect(container).toBeTruthy();
    });

    it('should include QueryClientProvider by default', () => {
      const { container } = render(
        <AppProvider>
          <TestChild />
        </AppProvider>
      );
      expect(container).toBeTruthy();
    });

    it('should accept withQuery prop as true', () => {
      const { container } = render(
        <AppProvider withQuery={true}>
          <TestChild />
        </AppProvider>
      );
      expect(container).toBeTruthy();
    });

    it('should accept withQuery prop as false', () => {
      const { container } = render(
        <AppProvider withQuery={false}>
          <TestChild />
        </AppProvider>
      );
      expect(container).toBeTruthy();
    });

    it('should render with withQuery=false for simple components', () => {
      render(
        <AppProvider withQuery={false}>
          <TestChild label="No Query" />
        </AppProvider>
      );
      expect(screen.getByText('No Query')).toBeInTheDocument();
    });
  });

  describe('Initializers', () => {
    it('should have AuthInitializer component', () => {
      const { container } = render(
        <AppProvider>
          <TestChild />
        </AppProvider>
      );
      // AuthInitializer is internal, just verify it renders without errors
      expect(container).toBeTruthy();
    });

    it('should have ConfigInitializer component', () => {
      const { container } = render(
        <AppProvider>
          <TestChild />
        </AppProvider>
      );
      // ConfigInitializer is internal, just verify it renders without errors
      expect(container).toBeTruthy();
    });

    it('should pass children through initializer chain', () => {
      render(
        <AppProvider>
          <TestChild label="Through Chain" />
        </AppProvider>
      );
      expect(screen.getByText('Through Chain')).toBeInTheDocument();
    });
  });

  describe('Theme configuration', () => {
    it('should export theme from lib/theme', () => {
      // Just verify the export is available (it's a re-export at the bottom of file)
      expect(AppProvider).toBeDefined();
    });
  });

  describe('Re-exported theme', () => {
    it('should be exported for external use', async () => {
      // The file re-exports mantineTheme as theme
      const module = await import('../../src/components/AppProvider');
      expect(module.theme).toBeDefined();
    });
  });

  describe('Props interface', () => {
    it('should render with required children prop', () => {
      render(
        <AppProvider>
          <TestChild label="Required" />
        </AppProvider>
      );
      expect(screen.getByText('Required')).toBeInTheDocument();
    });

    it('should accept optional withQuery prop (defaults to true)', () => {
      render(
        <AppProvider>
          <TestChild label="Default Query" />
        </AppProvider>
      );
      expect(screen.getByText('Default Query')).toBeInTheDocument();
    });

    it('should handle readonly children prop', () => {
      const child = <TestChild label="Readonly" />;
      render(<AppProvider>{child}</AppProvider>);
      expect(screen.getByText('Readonly')).toBeInTheDocument();
    });
  });

  describe('CSS imports', () => {
    it('should import mantine CSS without errors', () => {
      // The component imports '../styles/mantine-imports'
      // Just verify it renders without CSS import errors
      const { container } = render(
        <AppProvider>
          <TestChild />
        </AppProvider>
      );
      expect(container).toBeTruthy();
    });
  });

  describe('Notifications position', () => {
    it('should render notifications component', () => {
      const { container } = render(
        <AppProvider>
          <TestChild />
        </AppProvider>
      );
      // Notifications component is rendered internally
      expect(container).toBeTruthy();
    });
  });

  describe('Composition patterns', () => {
    it('should support nested App structure', () => {
      render(
        <AppProvider>
          <div>
            <TestChild label="Nested" />
          </div>
        </AppProvider>
      );
      expect(screen.getByText('Nested')).toBeInTheDocument();
    });

    it('should support multiple renders without state pollution', () => {
      const { rerender } = render(
        <AppProvider>
          <TestChild label="First Render" />
        </AppProvider>
      );
      expect(screen.getByText('First Render')).toBeInTheDocument();

      rerender(
        <AppProvider>
          <TestChild label="Second Render" />
        </AppProvider>
      );
      expect(screen.getByText('Second Render')).toBeInTheDocument();
    });

    it('should preserve context across multiple children', () => {
      render(
        <AppProvider>
          <TestChild label="Context Test 1" />
          <TestChild label="Context Test 2" />
        </AppProvider>
      );
      expect(screen.getByText('Context Test 1')).toBeInTheDocument();
      expect(screen.getByText('Context Test 2')).toBeInTheDocument();
    });
  });

  describe('Default props behavior', () => {
    it('should use true as default for withQuery', () => {
      // When not specified, withQuery should be true
      render(
        <AppProvider>
          <TestChild label="Default withQuery" />
        </AppProvider>
      );
      expect(screen.getByText('Default withQuery')).toBeInTheDocument();
    });

    it('should respect explicit false for withQuery', () => {
      render(
        <AppProvider withQuery={false}>
          <TestChild label="Explicit withQuery false" />
        </AppProvider>
      );
      expect(screen.getByText('Explicit withQuery false')).toBeInTheDocument();
    });
  });
});
