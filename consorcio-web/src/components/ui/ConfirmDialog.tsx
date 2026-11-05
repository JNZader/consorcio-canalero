import { Button, Group, Modal, Text } from '@mantine/core';
import type { ReactNode } from 'react';

export interface ConfirmDialogProps {
  readonly opened: boolean;
  readonly title: string;
  readonly message: ReactNode;
  readonly confirmLabel?: string;
  readonly cancelLabel?: string;
  readonly onConfirm: () => void;
  readonly onClose: () => void;
  readonly loading?: boolean;
  /** El botón de confirmación usa el color de peligro. */
  readonly destructive?: boolean;
}

/**
 * Confirmación modal para acciones que no se pueden deshacer.
 * Reemplaza `window.confirm`.
 */
export function ConfirmDialog({
  opened,
  title,
  message,
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancelar',
  onConfirm,
  onClose,
  loading = false,
  destructive = true,
}: ConfirmDialogProps) {
  return (
    <Modal opened={opened} onClose={onClose} title={title} centered closeOnClickOutside={!loading}>
      <Text size="sm">{message}</Text>
      <Group justify="flex-end" mt="lg">
        <Button variant="default" onClick={onClose} disabled={loading}>
          {cancelLabel}
        </Button>
        <Button color={destructive ? 'red' : 'institucional'} onClick={onConfirm} loading={loading}>
          {confirmLabel}
        </Button>
      </Group>
    </Modal>
  );
}
