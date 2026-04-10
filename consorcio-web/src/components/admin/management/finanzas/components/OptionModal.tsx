import { Button, Modal, Stack, TextInput } from '@mantine/core';

export function OptionModal({
  opened,
  onClose,
  title,
  value,
  onChange,
  onSave,
  label = 'Nombre',
  placeholder,
  saveLabel,
}: Readonly<{
  opened: boolean;
  onClose: () => void;
  title: string;
  value: string;
  onChange: (value: string) => void;
  onSave: () => void;
  label?: string;
  placeholder: string;
  saveLabel: string;
}>) {
  return (
    <Modal opened={opened} onClose={onClose} title={title}>
      <Stack gap="sm">
        <TextInput
          label={label}
          placeholder={placeholder}
          value={value}
          onChange={(event) => onChange(event.currentTarget.value)}
        />
        <Button type="button" onClick={onSave}>
          {saveLabel}
        </Button>
      </Stack>
    </Modal>
  );
}
