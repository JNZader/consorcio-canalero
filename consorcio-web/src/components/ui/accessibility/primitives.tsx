import { Alert, Box, Text } from '@mantine/core';
import type { ComponentPropsWithoutRef, ElementType, ReactNode } from 'react';
import { visuallyHiddenStyle } from './shared';

interface VisuallyHiddenProps extends ComponentPropsWithoutRef<'span'> {
  readonly children: ReactNode;
  readonly as?: ElementType;
}

export function VisuallyHidden({
  children,
  as: Component = 'span',
  style,
  ...props
}: VisuallyHiddenProps) {
  return (
    <Component style={{ ...visuallyHiddenStyle, ...style }} {...props}>
      {children}
    </Component>
  );
}

interface AccessibleErrorProps {
  readonly id: string;
  readonly error: string | null | undefined;
  readonly className?: string;
}

export function AccessibleError({ id, error, className }: AccessibleErrorProps) {
  if (!error) return null;

  return (
    <Alert
      id={id}
      color="red"
      variant="light"
      mt="xs"
      role="alert"
      aria-live="assertive"
      className={className}
      styles={{ root: { borderLeft: '4px solid var(--mantine-color-red-6)' } }}
    >
      <Text size="sm">{error}</Text>
    </Alert>
  );
}

interface SkipLink {
  readonly href: string;
  readonly label: string;
}

interface SkipLinksProps {
  readonly links?: SkipLink[];
}

const DEFAULT_SKIP_LINKS: SkipLink[] = [
  { href: '#main-content', label: 'Saltar al contenido principal' },
  { href: '#primary-nav', label: 'Saltar a navegacion' },
  { href: '#footer', label: 'Saltar al pie de pagina' },
];

export function SkipLinks({ links = DEFAULT_SKIP_LINKS }: SkipLinksProps) {
  return (
    <Box
      component="nav"
      aria-label="Enlaces de salto"
      style={{ position: 'absolute', top: 0, left: 0, zIndex: 10000 }}
    >
      {links.map((link, index) => (
        <a
          key={link.href}
          href={link.href}
          style={{
            position: 'absolute',
            top: -100,
            left: index * 180,
            background: 'var(--mantine-color-blue-filled)',
            color: 'white',
            padding: '8px 16px',
            textDecoration: 'none',
            fontWeight: 500,
            borderRadius: '0 0 4px 4px',
            transition: 'top 0.2s',
            zIndex: 10000,
          }}
          onFocus={(event) => {
            event.currentTarget.style.top = '0';
          }}
          onBlur={(event) => {
            event.currentTarget.style.top = '-100px';
          }}
        >
          {link.label}
        </a>
      ))}
    </Box>
  );
}
