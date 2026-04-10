import { Button, Checkbox, Modal, Stack, TextInput } from '@mantine/core';
import { memo } from 'react';
import { IconDownload } from '../ui/icons';

interface ExportPngModalProps {
  readonly opened: boolean;
  readonly title: string;
  readonly includeLegend: boolean;
  readonly includeMetadata: boolean;
  readonly onClose: () => void;
  readonly onTitleChange: (value: string) => void;
  readonly onIncludeLegendChange: (value: boolean) => void;
  readonly onIncludeMetadataChange: (value: boolean) => void;
  readonly onExport: () => void;
}

export const ExportPngModal = memo(function ExportPngModal({
  opened,
  title,
  includeLegend,
  includeMetadata,
  onClose,
  onTitleChange,
  onIncludeLegendChange,
  onIncludeMetadataChange,
  onExport,
}: ExportPngModalProps) {
  return (
    <Modal opened={opened} onClose={onClose} title="Exportar mapa como PNG" size="sm">
      <Stack gap="xs">
        <TextInput
          size="xs"
          label="Título del mapa"
          value={title}
          onChange={(event) => onTitleChange(event.currentTarget.value)}
        />
        <Checkbox
          size="xs"
          label="Incluir leyenda"
          checked={includeLegend}
          onChange={(event) => onIncludeLegendChange(event.currentTarget.checked)}
        />
        <Checkbox
          size="xs"
          label="Incluir metadatos"
          checked={includeMetadata}
          onChange={(event) => onIncludeMetadataChange(event.currentTarget.checked)}
        />
        <Button size="xs" onClick={onExport} leftSection={<IconDownload size={14} />}>
          Descargar PNG
        </Button>
      </Stack>
    </Modal>
  );
});
