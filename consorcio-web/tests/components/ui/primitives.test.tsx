import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ConfirmDialog } from '../../../src/components/ui/ConfirmDialog';
import { ICON_BUTTON_CLASS, IconButton } from '../../../src/components/ui/IconButton';
import { LoadingState } from '../../../src/components/ui/LoadingState';
import { PageHeader } from '../../../src/components/ui/PageHeader';
import { statusColorVar, StatusBadge } from '../../../src/components/ui/StatusBadge';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('PageHeader', () => {
  it('renders a serif page title, subtitle and actions', () => {
    renderWithMantine(
      <PageHeader
        title="Gestión de Trámites"
        subtitle="Seguimiento"
        actions={<button type="button">Nuevo</button>}
      />
    );

    const heading = screen.getByRole('heading', { level: 1, name: 'Gestión de Trámites' });
    expect(heading.getAttribute('style')).toContain('var(--cc-font-family-heading)');
    expect(screen.getByText('Seguimiento')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Nuevo' })).toBeInTheDocument();
  });

  it('centers a public-style heading and can place an icon beside the title', () => {
    renderWithMantine(
      <PageHeader
        title="Participación"
        subtitle={<em>Reportá</em>}
        align="center"
        icon={<span data-testid="page-icon">*</span>}
      />
    );
    expect(screen.getByRole('heading', { name: 'Participación' })).toBeInTheDocument();
    expect(screen.getByTestId('page-icon')).toBeInTheDocument();
    expect(screen.getByText('Reportá')).toBeInTheDocument();
  });

  it('omits an empty subtitle', () => {
    renderWithMantine(<PageHeader title="Solo título" subtitle="" />);
    expect(screen.getByRole('heading', { name: 'Solo título' })).toBeInTheDocument();
  });
});

describe('LoadingState', () => {
  it('renders a compact loader with the message', () => {
    renderWithMantine(<LoadingState compact message="Cargando denuncias..." />);
    expect(screen.getByRole('status', { name: 'Cargando denuncias...' })).toHaveAttribute(
      'aria-busy',
      'true'
    );
    expect(screen.getByText('Cargando denuncias...')).toBeInTheDocument();
  });

  it('renders the empty pattern', () => {
    renderWithMantine(
      <LoadingState status="empty" title="No hay denuncias" description="Sin resultados" />
    );
    expect(screen.getByText('No hay denuncias')).toBeInTheDocument();
    expect(screen.getByText('Sin resultados')).toBeInTheDocument();
  });

  it('renders the error pattern with a retry action', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    renderWithMantine(
      <LoadingState
        status="error"
        title="No se pudo cargar"
        message="Intentá de nuevo"
        action={
          <button type="button" onClick={onRetry}>
            Reintentar
          </button>
        }
      />
    );

    expect(screen.getByRole('alert')).toHaveTextContent('Intentá de nuevo');
    await user.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe('IconButton', () => {
  it('keeps the action icon and marks the coarse-pointer hit area', () => {
    renderWithMantine(
      <IconButton aria-label="Editar" className="extra" onClick={vi.fn()}>
        E
      </IconButton>
    );
    const button = screen.getByRole('button', { name: 'Editar' });
    expect(button).toHaveClass(ICON_BUTTON_CLASS);
    expect(button).toHaveClass('extra');
  });

  it('applies the 44px floor only for coarse pointers', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/styles/global.css'), 'utf8');
    const index = css.indexOf('.cc-icon-button');
    const mediaAt = css.lastIndexOf('@media', index);
    expect(css.slice(mediaAt, index)).toContain('@media (pointer: coarse)');
    expect(css.slice(index, index + 180)).toContain('min-height: var(--cc-touch-min, 44px)');
    expect(css.slice(index, index + 180)).toContain('min-width: var(--cc-touch-min, 44px)');
    expect(css.slice(0, mediaAt)).not.toContain('.cc-icon-button');
  });
});

describe('StatusBadge', () => {
  it.each([
    ['pendiente', 'var(--cc-color-warning)'],
    ['en_revision', 'var(--cc-color-status-review)'],
    ['resuelto', 'var(--cc-color-success)'],
    ['descartado', 'var(--cc-color-danger)'],
    ['descartada', 'var(--cc-color-text-muted)'],
  ])('paints %s with %s', (status, token) => {
    renderWithMantine(<StatusBadge status={status} />);
    expect(statusColorVar(status)).toBe(token);
    expect(screen.getByText(/./).closest('[data-status]')?.getAttribute('style')).toContain(token);
  });

  it('falls back to muted text for an unknown status', () => {
    expect(statusColorVar('otro')).toBe('var(--cc-color-text-muted)');
    renderWithMantine(<StatusBadge status="otro" />);
    expect(screen.getByText('otro')).toBeInTheDocument();
  });
});

describe('ConfirmDialog', () => {
  it('confirms and cancels a destructive action', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    const { rerender } = renderWithMantine(
      <ConfirmDialog
        opened
        title="Eliminar consorcista"
        message="Esta acción no se puede deshacer."
        confirmLabel="Eliminar"
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    expect(screen.getByRole('dialog', { name: 'Eliminar consorcista' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cancelar' }));
    expect(onClose).toHaveBeenCalledOnce();

    rerender(
      <MantineProvider env="test">
        <ConfirmDialog
          opened
          title="Eliminar consorcista"
          message="Esta acción no se puede deshacer."
          confirmLabel="Eliminar"
          onConfirm={onConfirm}
          onClose={onClose}
          destructive={false}
        />
      </MantineProvider>
    );
    await user.click(screen.getByRole('button', { name: 'Eliminar' }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('disables cancel while the confirm action is in flight', () => {
    renderWithMantine(
      <ConfirmDialog
        opened
        loading
        title="Eliminar tema"
        message="Esperá"
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeInTheDocument();
  });
});
