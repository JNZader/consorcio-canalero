import { Alert, Button, Code, Group, Paper, Stack, Text, Title } from '@mantine/core';
import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { logger } from '../lib/logger';

interface Props {
  readonly children: ReactNode;
  readonly fallback?: ReactNode;
  readonly onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface ErrorContext {
  message: string;
  stack?: string;
  componentStack?: string;
  componentName?: string;
  url?: string;
  timestamp: string;
  userAgent?: string;
}

/**
 * Send error report to a custom API endpoint.
 * This allows for self-hosted error tracking when third-party services are not used.
 */
async function sendToErrorApi(errorContext: ErrorContext): Promise<void> {
  const errorApiEndpoint = import.meta.env.VITE_ERROR_API_ENDPOINT;

  if (!errorApiEndpoint) {
    return;
  }

  try {
    await fetch(errorApiEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(errorContext),
    });
  } catch (fetchError) {
    // Silently fail - we don't want error reporting to cause additional errors
    logger.warn('[ErrorBoundary] Failed to send error to API:', fetchError);
  }
}

/**
 * Attempt to report error to Sentry if available.
 * Sentry SDK should be initialized in the app entry point.
 */
function sendToSentry(error: Error, errorContext: ErrorContext): boolean {
  // Check if Sentry is available on the global scope
  const Sentry = (globalThis as Record<string, unknown>).Sentry as {
    captureException?: (error: Error, options?: { extra?: ErrorContext }) => void;
  } | undefined;

  if (Sentry?.captureException) {
    Sentry.captureException(error, { extra: errorContext });
    return true;
  }
  return false;
}

/**
 * Attempt to report error to LogRocket if available.
 * LogRocket SDK should be initialized in the app entry point.
 */
function sendToLogRocket(error: Error): boolean {
  const LogRocket = (globalThis as Record<string, unknown>).LogRocket as {
    captureException?: (error: Error) => void;
  } | undefined;

  if (LogRocket?.captureException) {
    LogRocket.captureException(error);
    return true;
  }
  return false;
}

/**
 * Report error to external logging service.
 * Supports multiple error tracking services with automatic detection.
 * Priority: Sentry > LogRocket > Custom API > Console fallback
 */
function reportErrorToService(error: Error, errorInfo: ErrorInfo, componentName?: string): void {
  // Skip reporting in development
  if (import.meta.env.DEV) {
    return;
  }

  // Prepare error context
  const errorContext: ErrorContext = {
    message: error.message,
    stack: error.stack,
    componentStack: errorInfo.componentStack ?? undefined,
    componentName,
    url: globalThis.location?.href,
    timestamp: new Date().toISOString(),
    userAgent: globalThis.navigator?.userAgent,
  };

  // Try Sentry first (most common error tracking service)
  const sentryReported = sendToSentry(error, errorContext);

  // Try LogRocket as secondary option
  const logRocketReported = sendToLogRocket(error);

  // Send to custom API endpoint if configured
  void sendToErrorApi(errorContext);

  // Fallback: Log to console in production if no service captured the error
  // This is useful for debugging via browser devtools
  if (!sentryReported && !logRocketReported) {
    logger.error('[ErrorBoundary] Error reported:', errorContext);
  }
}

interface State {
  readonly hasError: boolean;
  readonly error: Error | null;
  readonly errorInfo: ErrorInfo | null;
}

/**
 * Error Boundary component for catching React errors.
 *
 * Usage:
 * ```tsx
 * <ErrorBoundary>
 *   <YourComponent />
 * </ErrorBoundary>
 *
 * // With custom fallback
 * <ErrorBoundary fallback={<CustomErrorUI />}>
 *   <YourComponent />
 * </ErrorBoundary>
 * ```
 *
 * Environment variables:
 * - VITE_ERROR_API_ENDPOINT: Custom API endpoint for error reporting
 *
 * Supported error tracking services (auto-detected):
 * - Sentry: Initialize with Sentry.init() in your app entry point
 * - LogRocket: Initialize with LogRocket.init() in your app entry point
 */
export class ErrorBoundary extends Component<Props, State> {
  public readonly state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    logger.error('ErrorBoundary caught an error:', error, errorInfo);
    this.setState({ errorInfo });

    // Report to external error logging service
    reportErrorToService(error, errorInfo, 'ErrorBoundary');

    // Call optional error handler
    this.props.onError?.(error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  public render() {
    if (this.state.hasError) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default error UI
      return (
        <Paper shadow="md" p="xl" radius="md" withBorder>
          <Stack gap="md">
            <Alert color="red" title="Algo salio mal" variant="light">
              <Text size="sm">
                Ha ocurrido un error inesperado. Por favor, intenta recargar la pagina.
              </Text>
            </Alert>

            {import.meta.env.DEV && this.state.error && (
              <Stack gap="xs">
                <Title order={5}>Error:</Title>
                <Code block color="red">
                  {this.state.error.message}
                </Code>

                {this.state.errorInfo && (
                  <>
                    <Title order={5}>Stack:</Title>
                    <Code block style={{ maxHeight: 200, overflow: 'auto' }}>
                      {this.state.errorInfo.componentStack}
                    </Code>
                  </>
                )}
              </Stack>
            )}

            <Group>
              <Button onClick={this.handleReset} variant="light">
                Intentar de nuevo
              </Button>
              <Button onClick={() => globalThis.location.reload()} variant="subtle">
                Recargar pagina
              </Button>
            </Group>
          </Stack>
        </Paper>
      );
    }

    return this.props.children;
  }
}

/**
 * Simple error fallback for specific sections.
 */
export function ErrorFallback({
  message = 'Error al cargar este componente',
  onRetry,
}: Readonly<{
  message?: string;
  onRetry?: () => void;
}>) {
  return (
    <Alert color="red" title="Error" variant="light">
      <Text size="sm" mb="sm">
        {message}
      </Text>
      {onRetry && (
        <Button size="xs" variant="light" color="red" onClick={onRetry}>
          Reintentar
        </Button>
      )}
    </Alert>
  );
}

export default ErrorBoundary;
