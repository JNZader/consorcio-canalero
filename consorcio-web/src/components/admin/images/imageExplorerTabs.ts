export const IMAGE_EXPLORER_TABS = ['escena', 'comparar', 'detectar'] as const;

export type ImageExplorerTab = (typeof IMAGE_EXPLORER_TABS)[number];

export const IMAGE_EXPLORER_TAB_LABELS: Record<ImageExplorerTab, string> = {
  escena: 'Escena',
  comparar: 'Comparar',
  detectar: 'Detectar',
};
