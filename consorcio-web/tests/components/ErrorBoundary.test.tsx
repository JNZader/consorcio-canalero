import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React, { type ReactNode } from 'react';
import { MantineProvider } from '@mantine/core';
import ErrorBoundary, { ErrorFallback } from '../../src/components/ErrorBoundary';

const { loggerMock } = vi.hoisted(() => ({
  loggerMock: {
    error: vi.fn(),
    warn: vi.fn(),
  },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: loggerMock,
}));

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

function WorkingComponent() {
  return <div>Success content</div>;
}

function ThrowingComponent() {
  throw new Error('Test error message');
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders children normally when no error occurs', () => {
    renderWithMantine(
      <ErrorBoundary>
        <WorkingComponent />
      </ErrorBoundary>
    );

    expect(screen.getByText('Success content')).toBeInTheDocument();
    expect(screen.queryByText('Algo salio mal')).not.toBeInTheDocument();
  });

  it('shows the default fallback UI and logs the caught error', () => {
    renderWithMantine(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    );

    expect(screen.getByText('Algo salio mal')).toBeInTheDocument();
    expect(
      screen.getByText(/Ha ocurrido un error inesperado\. Por favor, intenta recargar la pagina\./i)
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Intentar de nuevo/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Recargar pagina/i })).toBeInTheDocument();
    expect(loggerMock.error).toHaveBeenCalledWith(
      'ErrorBoundary caught an error:',
      expect.objectContaining({ message: 'Test error message' }),
      expect.objectContaining({ componentStack: expect.any(String) })
    );
  });

  it('calls onError with the original error and component stack', () => {
    const onError = vi.fn();

    renderWithMantine(
      <ErrorBoundary onError={onError}>
        <ThrowingComponent />
      </ErrorBoundary>
    );

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'Test error message' }),
      expect.objectContaining({ componentStack: expect.any(String) })
    );
  });

  it('renders a custom fallback instead of the default UI', () => {
    renderWithMantine(
      <ErrorBoundary fallback={<div>Custom Error UI</div>}>
        <ThrowingComponent />
      </ErrorBoundary>
    );

    expect(screen.getByText('Custom Error UI')).toBeInTheDocument();
    expect(screen.queryByText('Algo salio mal')).not.toBeInTheDocument();
  });

  it('shows developer error details in DEV mode', () => {
    renderWithMantine(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    );

    if (import.meta.env.DEV) {
      expect(screen.getByText('Error:')).toBeInTheDocument();
      expect(screen.getByText('Test error message')).toBeInTheDocument();
      expect(screen.getByText('Stack:')).toBeInTheDocument();
    }
  });

  it('reload button calls location.reload', () => {
    const reloadSpy = vi.spyOn(globalThis.location, 'reload').mockImplementation(() => {});

    renderWithMantine(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    );

    fireEvent.click(screen.getByRole('button', { name: /Recargar pagina/i }));

    expect(reloadSpy).toHaveBeenCalledTimes(1);
    reloadSpy.mockRestore();
  });

  it('reset button clears the error state and retries rendering children', () => {
    function RecoverableChild({ shouldThrow }: { shouldThrow: boolean }) {
      if (shouldThrow) {
        throw new Error('First render fails');
      }
      return <div>Recovered content</div>;
    }

    function RecoverableHarness() {
      const [shouldThrow, setShouldThrow] = React.useState(true);

      return (
        <>
          <button type="button" onClick={() => setShouldThrow(false)}>
            Fix child
          </button>
          <ErrorBoundary>
            <RecoverableChild shouldThrow={shouldThrow} />
          </ErrorBoundary>
        </>
      );
    }

    renderWithMantine(<RecoverableHarness />);

    expect(screen.getByText('Algo salio mal')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Fix child' }));
    expect(screen.getByText('Algo salio mal')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Intentar de nuevo/i }));

    expect(screen.getByText('Recovered content')).toBeInTheDocument();
    expect(screen.queryByText('Algo salio mal')).not.toBeInTheDocument();
  });
});

describe('ErrorFallback', () => {
  it('renders the default message without a retry button', () => {
    renderWithMantine(<ErrorFallback />);

    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(screen.getByText('Error al cargar este componente')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Reintentar/i })).not.toBeInTheDocument();
  });

  it('renders a custom message and calls onRetry when requested', () => {
    const onRetry = vi.fn();

    renderWithMantine(<ErrorFallback message="Custom error message" onRetry={onRetry} />);

    expect(screen.getByText('Custom error message')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Reintentar/i }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
