import { Group, Stack, Text, Title } from '@mantine/core';
import type { ReactNode } from 'react';

export interface PageHeaderProps {
  readonly title: string;
  readonly subtitle?: ReactNode;
  readonly actions?: ReactNode;
  /** Ícono al lado del título. No cambia la tipografía. */
  readonly icon?: ReactNode;
  /**
   * Nivel semántico. El título de una página es h1.
   * El tamaño visual por defecto es h2, el de los paneles de gestión.
   */
  readonly order?: 1 | 2 | 3;
  readonly size?: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6';
  /** `center` reproduce el encabezado de las páginas públicas. */
  readonly align?: 'start' | 'center';
  readonly mb?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 0;
  readonly subtitleSize?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
}

/**
 * Encabezado de página. La familia es la serif de display de las páginas
 * públicas (`--cc-font-family-heading`, DM Serif Display).
 */
export function PageHeader({
  title,
  subtitle,
  actions,
  icon,
  order = 1,
  size = 'h2',
  align = 'start',
  mb = 'xl',
  subtitleSize,
}: PageHeaderProps) {
  const heading = (
    <Title
      order={order}
      size={size}
      ta={align === 'center' ? 'center' : undefined}
      style={{ fontFamily: 'var(--cc-font-family-heading)' }}
    >
      {title}
    </Title>
  );

  const subtitleNode =
    subtitle == null || subtitle === '' ? null : typeof subtitle === 'string' ? (
      <Text
        c="dimmed"
        size={subtitleSize}
        ta={align === 'center' ? 'center' : undefined}
        maw={align === 'center' ? 560 : undefined}
      >
        {subtitle}
      </Text>
    ) : (
      subtitle
    );

  const copy = (
    <Stack gap={4} align={align === 'center' ? 'center' : 'stretch'}>
      {icon ? (
        <Group gap="xs" justify={align === 'center' ? 'center' : 'flex-start'} wrap="nowrap">
          {icon}
          {heading}
        </Group>
      ) : (
        heading
      )}
      {subtitleNode}
    </Stack>
  );

  if (align === 'center' && !actions) {
    return (
      <Stack align="center" mb={mb} gap="md">
        {copy}
      </Stack>
    );
  }

  return (
    <Group justify="space-between" align="flex-start" mb={mb} wrap="wrap">
      {copy}
      {actions ? (
        <Group gap="sm" wrap="wrap">
          {actions}
        </Group>
      ) : null}
    </Group>
  );
}
