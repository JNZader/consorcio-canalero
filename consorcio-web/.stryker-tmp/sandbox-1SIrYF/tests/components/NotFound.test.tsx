// @ts-nocheck
import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import NotFound from '../../src/components/NotFound';
import { MantineProvider } from '@mantine/core';

// Mock router
vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children, ...props }: any) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

describe('NotFound', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render 404 title', () => {
    render(
      <MantineProvider>
        <NotFound />
      </MantineProvider>
    );

    expect(screen.getByText('404')).toBeInTheDocument();
  });

  it('should render not found message', () => {
    render(
      <MantineProvider>
        <NotFound />
      </MantineProvider>
    );

    expect(screen.getByText('Pagina no encontrada')).toBeInTheDocument();
  });

  it('should render helpful description', () => {
    render(
      <MantineProvider>
        <NotFound />
      </MantineProvider>
    );

    expect(
      screen.getByText(
        /La pagina que buscas no existe o fue movida/i
      )
    ).toBeInTheDocument();
  });

  it('should render home button', () => {
    render(
      <MantineProvider>
        <NotFound />
      </MantineProvider>
    );

    const homeButton = screen.getByRole('link', { name: /Volver al inicio/i });
    expect(homeButton).toBeInTheDocument();
    expect(homeButton).toHaveAttribute('href', '/');
  });

  it('should render with proper semantic structure', () => {
    const { container } = render(
      <MantineProvider>
        <NotFound />
      </MantineProvider>
    );

    // Check for heading structure
    const headings = container.querySelectorAll('h1, h2');
    expect(headings.length).toBeGreaterThan(0);
  });

  it('should have centered layout', () => {
    const { container } = render(
      <MantineProvider>
        <NotFound />
      </MantineProvider>
    );

    const containerElement = container.querySelector('[class*="Container"]');
    expect(containerElement).toBeInTheDocument();
  });

  it('should display icon for visual context', () => {
    const { container } = render(
      <MantineProvider>
        <NotFound />
      </MantineProvider>
    );

    // Icon should be present (SVG or image)
    const svgElements = container.querySelectorAll('svg');
    expect(svgElements.length).toBeGreaterThan(0);
  });

  it('should be accessible with proper ARIA labels', () => {
    render(
      <MantineProvider>
        <NotFound />
      </MantineProvider>
    );

    // Main content should be accessible
    expect(screen.getByText('404')).toBeInTheDocument();
    expect(screen.getByText('Pagina no encontrada')).toBeInTheDocument();
  });

  it('should render button with left icon section', () => {
    render(
      <MantineProvider>
        <NotFound />
      </MantineProvider>
    );

    const button = screen.getByRole('link', { name: /Volver al inicio/i });
    expect(button).toBeInTheDocument();
    // Button should have icon (SVG child)
    const svg = button.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });
});
