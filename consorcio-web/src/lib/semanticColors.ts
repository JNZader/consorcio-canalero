/**
 * Colores semánticos de Río más limpio para avisos.
 * Los botones de acción usan el `primaryColor` del tema (`institucional`)
 * y sus variantes; estos nombres son solo para alertas y toasts.
 */
export const semanticColor = {
  info: 'institucional',
  success: 'exito',
  warning: 'orange',
  danger: 'alerta',
} as const;

export type SemanticColor = (typeof semanticColor)[keyof typeof semanticColor];

/** Nombres sueltos de Mantine que los avisos todavía reciben. */
const LEGACY_NOTIFICATION_COLOR: Record<string, SemanticColor> = {
  blue: semanticColor.info,
  cyan: semanticColor.info,
  green: semanticColor.success,
  teal: semanticColor.success,
  yellow: semanticColor.warning,
  orange: semanticColor.warning,
  red: semanticColor.danger,
  alerta: semanticColor.danger,
  exito: semanticColor.success,
  institucional: semanticColor.info,
};

/** Lleva el color de un toast a la paleta semántica. El resto se deja igual. */
export function notificationColor(color: string): string {
  return LEGACY_NOTIFICATION_COLOR[color] ?? color;
}
