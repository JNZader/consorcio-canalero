import { ActionIcon, type ActionIconProps } from '@mantine/core';
import type { ElementType, MouseEventHandler, ReactNode } from 'react';

/** Clase del piso táctil. El CSS solo la agranda con `pointer: coarse`. */
export const ICON_BUTTON_CLASS = 'cc-icon-button';

export interface IconButtonProps extends ActionIconProps {
  readonly 'aria-label': string;
  readonly children?: ReactNode;
  readonly className?: string;
  readonly onClick?: MouseEventHandler<HTMLButtonElement>;
  readonly component?: ElementType;
  readonly href?: string;
  readonly target?: string;
  readonly rel?: string;
  readonly title?: string;
  readonly type?: 'button' | 'submit' | 'reset';
  readonly disabled?: boolean;
  readonly loading?: boolean;
}

/**
 * ActionIcon con área de toque mínima de `--cc-touch-min` (44px) en
 * punteros gruesos. En mouse conserva el tamaño del ActionIcon.
 */
export function IconButton({ className, ...props }: IconButtonProps) {
  const classes = [ICON_BUTTON_CLASS, className].filter(Boolean).join(' ');
  // `component="a"` es más ancho que el factory polimórfico de ActionIcon.
  return <ActionIcon className={classes} {...(props as ActionIconProps)} />;
}
