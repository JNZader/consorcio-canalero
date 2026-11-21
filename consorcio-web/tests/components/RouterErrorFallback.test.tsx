import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { reportExceptionMock } = vi.hoisted(() => ({
  reportExceptionMock: vi.fn(),
}));

vi.mock('../../src/lib/errorReporting', () => ({
  reportException: reportExceptionMock,
}));

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to, ...props }: { children: ReactNode; to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

import { RouterErrorFallback } from '../../src/components/RouterErrorFallback';

describe('RouterErrorFallback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('reports route errors to the errorReporting bus and invokes reset', () => {
    const reset = vi.fn();
    const error = new Error('Chunk load failure');

    render(
      <MantineProvider env="test">
        <RouterErrorFallback error={error} reset={reset} />
      </MantineProvider>
    );

    expect(reportExceptionMock).toHaveBeenCalledTimes(1);
    expect(reportExceptionMock).toHaveBeenCalledWith(error, {
      boundary: 'RouterErrorFallback',
    });

    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(reset).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('link', { name: 'Volver al inicio' })).toHaveAttribute('href', '/');
  });
});
