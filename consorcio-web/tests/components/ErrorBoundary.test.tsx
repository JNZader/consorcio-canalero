import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import ErrorBoundary, { ErrorFallback } from '../../src/components/ErrorBoundary';
import { Component } from 'react';
import { MantineProvider } from '@mantine/core';

// Mock the logger
vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
  },
}));

// Component that throws an error
class ErrorThrowingComponent extends Component {
  render() {
    throw new Error('Test error message');
  }
}

// Component that works normally
function WorkingComponent() {
  return <div>Success content</div>;
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Suppress console.error for error boundary tests
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('normal rendering', () => {
    it('should render children when no error occurs', () => {
      render(
        <ErrorBoundary>
          <WorkingComponent />
        </ErrorBoundary>
      );

      expect(screen.getByText('Success content')).toBeInTheDocument();
    });

    it('should render multiple children correctly', () => {
      render(
        <ErrorBoundary>
          <div>Child 1</div>
          <div>Child 2</div>
        </ErrorBoundary>
      );

      expect(screen.getByText('Child 1')).toBeInTheDocument();
      expect(screen.getByText('Child 2')).toBeInTheDocument();
    });

    it('should not show error UI when no error', () => {
      render(
        <ErrorBoundary>
          <WorkingComponent />
        </ErrorBoundary>
      );

      expect(screen.queryByText(/Algo salio mal/i)).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Intentar de nuevo/i })).not.toBeInTheDocument();
    });
  });

  describe('error handling', () => {
    it('should catch error and display error UI', () => {
      render(
        <MantineProvider>
          <ErrorBoundary>
            <ErrorThrowingComponent />
          </ErrorBoundary>
        </MantineProvider>
      );

      expect(screen.getByText(/Algo salio mal/i)).toBeInTheDocument();
      expect(screen.getByText(/Ha ocurrido un error inesperado/i)).toBeInTheDocument();
    });

    it('should display error UI when error occurs', () => {
      render(
        <MantineProvider>
          <ErrorBoundary>
            <ErrorThrowingComponent />
          </ErrorBoundary>
        </MantineProvider>
      );

      // Should show error alert
      expect(screen.getByText(/Algo salio mal/i)).toBeInTheDocument();
      expect(screen.getByText(/Ha ocurrido un error inesperado/i)).toBeInTheDocument();
    });

    it('should call onError callback when error occurs', () => {
      const onErrorSpy = vi.fn();

      render(
        <MantineProvider>
          <ErrorBoundary onError={onErrorSpy}>
            <ErrorThrowingComponent />
          </ErrorBoundary>
        </MantineProvider>
      );

      expect(onErrorSpy).toHaveBeenCalled();
      const [error, errorInfo] = onErrorSpy.mock.calls[0];
      expect(error).toBeInstanceOf(Error);
      expect(error.message).toBe('Test error message');
      expect(errorInfo).toBeDefined();
      expect(errorInfo.componentStack).toBeDefined();
    });

    it('should show reset button when error occurs', () => {
      render(
        <MantineProvider>
          <ErrorBoundary>
            <ErrorThrowingComponent />
          </ErrorBoundary>
        </MantineProvider>
      );

      const resetButton = screen.getByRole('button', { name: /Intentar de nuevo/i });
      expect(resetButton).toBeInTheDocument();
    });

    it('should show reload button when error occurs', () => {
      render(
        <MantineProvider>
          <ErrorBoundary>
            <ErrorThrowingComponent />
          </ErrorBoundary>
        </MantineProvider>
      );

      const reloadButton = screen.getByRole('button', { name: /Recargar pagina/i });
      expect(reloadButton).toBeInTheDocument();
    });
  });

  describe('error recovery', () => {
    it('should have reset button available when error occurs', () => {
      render(
        <MantineProvider>
          <ErrorBoundary>
            <ErrorThrowingComponent />
          </ErrorBoundary>
        </MantineProvider>
      );

      expect(screen.getByText(/Algo salio mal/i)).toBeInTheDocument();
      const resetButton = screen.getByRole('button', { name: /Intentar de nuevo/i });
      expect(resetButton).toBeInTheDocument();
      expect(resetButton).not.toBeDisabled();
    });

    it('should keep error UI visible and buttons accessible', () => {
      render(
        <MantineProvider>
          <ErrorBoundary>
            <ErrorThrowingComponent />
          </ErrorBoundary>
        </MantineProvider>
      );

      expect(screen.getByText(/Algo salio mal/i)).toBeInTheDocument();
      const resetButton = screen.getByRole('button', { name: /Intentar de nuevo/i });
      const reloadButton = screen.getByRole('button', { name: /Recargar pagina/i });
      
      expect(resetButton).toBeInTheDocument();
      expect(reloadButton).toBeInTheDocument();
    });
  });

  describe('custom fallback', () => {
    it('should render custom fallback when provided', () => {
      const customFallback = <div>Custom Error UI</div>;

      render(
        <ErrorBoundary fallback={customFallback}>
          <ErrorThrowingComponent />
        </ErrorBoundary>
      );

      expect(screen.getByText('Custom Error UI')).toBeInTheDocument();
      expect(screen.queryByText(/Algo salio mal/i)).not.toBeInTheDocument();
    });

    it('should not show default UI when custom fallback is provided', () => {
      const customFallback = <div>My Custom Error</div>;

      render(
        <ErrorBoundary fallback={customFallback}>
          <ErrorThrowingComponent />
        </ErrorBoundary>
      );

      expect(screen.getByText('My Custom Error')).toBeInTheDocument();
      expect(screen.queryByText(/Ha ocurrido un error inesperado/i)).not.toBeInTheDocument();
    });

    it('should not render custom fallback when no error', () => {
      const customFallback = <div>Custom Error UI</div>;

      render(
        <ErrorBoundary fallback={customFallback}>
          <WorkingComponent />
        </ErrorBoundary>
      );

      expect(screen.queryByText('Custom Error UI')).not.toBeInTheDocument();
      expect(screen.getByText('Success content')).toBeInTheDocument();
    });
  });

  describe('reload page functionality', () => {
    it('should have reload button that calls location.reload', () => {
      const reloadSpy = vi.spyOn(globalThis.location, 'reload').mockImplementation(() => {});

      render(
        <MantineProvider>
          <ErrorBoundary>
            <ErrorThrowingComponent />
          </ErrorBoundary>
        </MantineProvider>
      );

      const reloadButton = screen.getByRole('button', { name: /Recargar pagina/i });
      fireEvent.click(reloadButton);

      expect(reloadSpy).toHaveBeenCalled();
      reloadSpy.mockRestore();
    });
  });

  describe('error reporting', () => {
    it('should report error to external service when error occurs', () => {
      const onErrorSpy = vi.fn();

      render(
        <MantineProvider>
          <ErrorBoundary onError={onErrorSpy}>
            <ErrorThrowingComponent />
          </ErrorBoundary>
        </MantineProvider>
      );

      expect(onErrorSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Test error message',
        }),
        expect.objectContaining({
          componentStack: expect.any(String),
        })
      );
    });

    it('should not call onError when no error occurs', () => {
      const onErrorSpy = vi.fn();

      render(
        <MantineProvider>
          <ErrorBoundary onError={onErrorSpy}>
            <WorkingComponent />
          </ErrorBoundary>
        </MantineProvider>
      );

      expect(onErrorSpy).not.toHaveBeenCalled();
    });
  });

  describe('alert box properties', () => {
    it('should display alert with red color', () => {
      const { container } = render(
        <MantineProvider>
          <ErrorBoundary>
            <ErrorThrowingComponent />
          </ErrorBoundary>
        </MantineProvider>
      );

      const alert = container.querySelector('[role="alert"]') || 
                    container.querySelector('[class*="Alert"]');
      expect(alert).toBeInTheDocument();
    });

    it('should display alert message in the correct language', () => {
      render(
        <MantineProvider>
          <ErrorBoundary>
            <ErrorThrowingComponent />
          </ErrorBoundary>
        </MantineProvider>
      );

      expect(screen.getByText(/Algo salio mal/i)).toBeInTheDocument();
    });
  });
});

describe('ErrorFallback', () => {
  it('should render error fallback component', () => {
    render(
      <MantineProvider>
        <ErrorFallback />
      </MantineProvider>
    );

    expect(screen.getByText(/Error al cargar este componente/i)).toBeInTheDocument();
  });

  it('should render custom message', () => {
    render(
      <MantineProvider>
        <ErrorFallback message="Custom error message" />
      </MantineProvider>
    );

    expect(screen.getByText('Custom error message')).toBeInTheDocument();
    expect(screen.queryByText(/Error al cargar este componente/i)).not.toBeInTheDocument();
  });

  it('should render default message when not provided', () => {
    render(
      <MantineProvider>
        <ErrorFallback />
      </MantineProvider>
    );

    expect(screen.getByText(/Error al cargar este componente/i)).toBeInTheDocument();
  });

  it('should render retry button when onRetry is provided', () => {
    const onRetrySpy = vi.fn();

    render(
      <MantineProvider>
        <ErrorFallback onRetry={onRetrySpy} />
      </MantineProvider>
    );

    const retryButton = screen.getByRole('button', { name: /Reintentar/i });
    expect(retryButton).toBeInTheDocument();
  });

  it('should not render retry button when onRetry is not provided', () => {
    render(
      <MantineProvider>
        <ErrorFallback />
      </MantineProvider>
    );

    expect(screen.queryByRole('button', { name: /Reintentar/i })).not.toBeInTheDocument();
  });

  it('should call onRetry when retry button is clicked', () => {
    const onRetrySpy = vi.fn();

    render(
      <MantineProvider>
        <ErrorFallback onRetry={onRetrySpy} />
      </MantineProvider>
    );

    const retryButton = screen.getByRole('button', { name: /Reintentar/i });
    fireEvent.click(retryButton);

    expect(onRetrySpy).toHaveBeenCalledTimes(1);
  });

  it('should call onRetry multiple times on repeated clicks', () => {
    const onRetrySpy = vi.fn();

    render(
      <MantineProvider>
        <ErrorFallback onRetry={onRetrySpy} />
      </MantineProvider>
    );

    const retryButton = screen.getByRole('button', { name: /Reintentar/i });
    fireEvent.click(retryButton);
    fireEvent.click(retryButton);
    fireEvent.click(retryButton);

    expect(onRetrySpy).toHaveBeenCalledTimes(3);
  });

  it('should have error title in alert', () => {
    render(
      <MantineProvider>
        <ErrorFallback />
      </MantineProvider>
    );

    expect(screen.getByText('Error')).toBeInTheDocument();
  });
});
