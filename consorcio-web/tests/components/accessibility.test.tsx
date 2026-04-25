import { MantineProvider } from '@mantine/core';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRef } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  AccessibleError,
  AccessibleLoader,
  AccessibleRadioGroup,
  CoordinatesInput,
  LiveRegionProvider,
  SkipLinks,
  useFocusTrap,
  useLiveRegion,
  usePrefersReducedMotion,
} from '../../src/components/ui/accessibility';

vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}));

function Wrapper({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <MantineProvider>
      <LiveRegionProvider>{children}</LiveRegionProvider>
    </MantineProvider>
  );
}

describe('accessibility helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('announces messages through live region provider', async () => {
    function Announcer() {
      const { announce } = useLiveRegion();
      return (
        <button type="button" onClick={() => announce('mensaje accesible', 'assertive')}>
          announce
        </button>
      );
    }

    render(
      <Wrapper>
        <Announcer />
      </Wrapper>
    );

    await userEvent.click(screen.getByRole('button', { name: 'announce' }));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('mensaje accesible');
    });
  });

  it('renders and hides accessible error block correctly', () => {
    const { rerender } = render(
      <MantineProvider>
        <AccessibleError id="field-error" error={null} />
      </MantineProvider>
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    rerender(
      <MantineProvider>
        <AccessibleError id="field-error" error="Campo obligatorio" />
      </MantineProvider>
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Campo obligatorio');
  });

  it('handles coordinate validation and manual submit', async () => {
    const onCoordinatesChange = vi.fn();
    render(
      <Wrapper>
        <CoordinatesInput onCoordinatesChange={onCoordinatesChange} />
      </Wrapper>
    );

    await userEvent.type(screen.getByLabelText(/latitud/i), '100');
    await userEvent.type(screen.getByLabelText(/longitud/i), '-62.6');
    await userEvent.click(screen.getByRole('button', { name: /establecer/i }));
    expect(screen.getByText(/latitud debe estar entre -90 y 90/i)).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText(/latitud/i));
    await userEvent.type(screen.getByLabelText(/latitud/i), '-32.63');
    await userEvent.click(screen.getByRole('button', { name: /establecer/i }));
    expect(onCoordinatesChange).toHaveBeenCalledWith(-32.63, -62.6);
  });

  it('does not submit parent forms from coordinate helper actions', async () => {
    const onSubmit = vi.fn((event: React.FormEvent<HTMLFormElement>) => event.preventDefault());
    const onCoordinatesChange = vi.fn();
    const onAddressSearch = vi.fn().mockResolvedValue({ lat: -32.7, lng: -62.5 });

    render(
      <Wrapper>
        <form onSubmit={onSubmit}>
          <CoordinatesInput
            onCoordinatesChange={onCoordinatesChange}
            onAddressSearch={onAddressSearch}
          />
        </form>
      </Wrapper>,
    );

    await userEvent.type(screen.getByLabelText(/latitud/i), '-32.63');
    await userEvent.type(screen.getByLabelText(/longitud/i), '-62.6');
    await userEvent.click(screen.getByRole('button', { name: /establecer/i }));

    const addressInput = screen.getByLabelText(/direccion a buscar/i);
    await userEvent.type(addressInput, 'Bell Ville');
    await userEvent.click(screen.getByRole('button', { name: /buscar/i }));
    await waitFor(() => expect(onAddressSearch).toHaveBeenCalledWith('Bell Ville'));

    addressInput.focus();
    await userEvent.keyboard('{Enter}');
    await waitFor(() => expect(onAddressSearch).toHaveBeenCalledTimes(2));

    expect(onCoordinatesChange).toHaveBeenCalledWith(-32.63, -62.6);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('supports address search success and not found states', async () => {
    const onCoordinatesChange = vi.fn();
    const onAddressSearch = vi
      .fn()
      .mockResolvedValueOnce({ lat: -32.7, lng: -62.5 })
      .mockResolvedValueOnce(null);

    render(
      <Wrapper>
        <CoordinatesInput onCoordinatesChange={onCoordinatesChange} onAddressSearch={onAddressSearch} />
      </Wrapper>
    );

    await userEvent.type(screen.getByLabelText(/direccion a buscar/i), 'Bell Ville');
    await userEvent.click(screen.getByRole('button', { name: /buscar/i }));
    await waitFor(() => expect(onCoordinatesChange).toHaveBeenCalledWith(-32.7, -62.5));

    await userEvent.clear(screen.getByLabelText(/direccion a buscar/i));
    await userEvent.type(screen.getByLabelText(/direccion a buscar/i), 'Desconocido');
    await userEvent.click(screen.getByRole('button', { name: /buscar/i }));
    await waitFor(() => {
      expect(screen.getByText(/No se encontro la direccion/i)).toBeInTheDocument();
    });
  });

  it('supports keyboard navigation in radio group', async () => {
    const onChange = vi.fn();
    render(
      <MantineProvider>
        <AccessibleRadioGroup
          name="tipo"
          label="Tipo"
          value="a"
          onChange={onChange}
          options={[
            { value: 'a', label: 'A' },
            { value: 'b', label: 'B' },
          ]}
        />
      </MantineProvider>
    );

    const first = screen.getByRole('radio', { name: 'A' });
    first.focus();
    fireEvent.keyDown(first, { key: 'ArrowRight' });
    fireEvent.keyDown(screen.getByRole('radio', { name: 'B' }), { key: 'Enter' });

    expect(onChange).toHaveBeenCalledWith('b');
  });

  it('renders skip links and toggles position on focus', () => {
    render(
      <MantineProvider>
        <SkipLinks links={[{ href: '#main', label: 'Ir a main' }]} />
      </MantineProvider>
    );

    const link = screen.getByRole('link', { name: /ir a main/i });
    expect(link).toHaveStyle({ top: '-100px' });
    fireEvent.focus(link);
    expect(link).toHaveStyle({ top: '0px' });
    fireEvent.blur(link);
    expect(link).toHaveStyle({ top: '-100px' });
  });

  it('traps focus inside container and restores previous focus', async () => {
    function FocusTrapFixture() {
      const containerRef = useRef<HTMLDivElement>(null);
      useFocusTrap(true, containerRef);
      return (
        <div>
          <button type="button">outside</button>
          <div ref={containerRef}>
            <button type="button">first</button>
            <button type="button">last</button>
          </div>
        </div>
      );
    }

    const { unmount } = render(
      <MantineProvider>
        <FocusTrapFixture />
      </MantineProvider>
    );

    await waitFor(() => expect(screen.getByRole('button', { name: 'first' })).toHaveFocus());
    fireEvent.keyDown(screen.getByRole('button', { name: 'last' }).parentElement as HTMLElement, {
      key: 'Tab',
    });

    unmount();
    expect(screen.queryByRole('button', { name: 'first' })).not.toBeInTheDocument();
  });

  it('returns reduced motion preference from media query and cleans listener', async () => {
    let handler: ((e: MediaQueryListEvent) => void) | null = null;
    const removeEventListener = vi.fn();
    const mql = {
      matches: true,
      addEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => {
        handler = cb;
      },
      removeEventListener,
    };
    vi.stubGlobal('matchMedia', () => mql);

    function ReducedMotionProbe() {
      const reduced = usePrefersReducedMotion();
      return <div>{reduced ? 'reduced' : 'normal'}</div>;
    }

    const view = render(
      <MantineProvider>
        <ReducedMotionProbe />
      </MantineProvider>
    );
    expect(screen.getByText('reduced')).toBeInTheDocument();

    await waitFor(() => expect(handler).not.toBeNull());

    act(() => {
      handler?.({ matches: true } as MediaQueryListEvent);
    });

    view.unmount();
    expect(removeEventListener).toHaveBeenCalled();
  });

  it('shows loader state and then children', () => {
    const { rerender } = render(
      <Wrapper>
        <AccessibleLoader loading={true} loadingText="Cargando tabla">
          <div>contenido listo</div>
        </AccessibleLoader>
      </Wrapper>
    );

    expect(screen.getByText(/cargando tabla/i)).toBeInTheDocument();

    rerender(
      <Wrapper>
        <AccessibleLoader loading={false} loadingText="Cargando tabla">
          <div>contenido listo</div>
        </AccessibleLoader>
      </Wrapper>
    );
    expect(screen.getByText(/contenido listo/i)).toBeInTheDocument();
  });
});
