import { ActionIcon, Box, Group, Image, Text } from '@mantine/core';
import { Dropzone, IMAGE_MIME_TYPE } from '@mantine/dropzone';

const PHOTO_LABEL_ID = 'foto-label';
const PHOTO_INSTRUCTIONS_ID = 'foto-instrucciones';
const PHOTO_LIMIT_ID = 'foto-limite';

interface PhotoSectionProps {
  fotoPreview: string | null;
  onDrop: (files: File[]) => void;
  onRemove: () => void;
}

export function PhotoSection({ fotoPreview, onDrop, onRemove }: Readonly<PhotoSectionProps>) {
  if (fotoPreview) {
    return (
      <Box pos="relative" role="group" aria-label="Foto adjunta a la denuncia">
        <Image
          src={fotoPreview}
          alt="Vista previa de la foto adjunta a la denuncia"
          radius="md"
          h={200}
          fit="cover"
        />
        <ActionIcon
          pos="absolute"
          top={8}
          right={8}
          color="red"
          variant="filled"
          onClick={onRemove}
          aria-label="Eliminar foto adjunta"
        >
          X
        </ActionIcon>
      </Box>
    );
  }

  return (
    <Dropzone
      onDrop={onDrop}
      accept={IMAGE_MIME_TYPE}
      maxSize={5 * 1024 * 1024}
      maxFiles={1}
      aria-labelledby={PHOTO_LABEL_ID}
      aria-describedby={`${PHOTO_INSTRUCTIONS_ID} ${PHOTO_LIMIT_ID}`}
    >
      <Group justify="center" gap="xl" mih={120} style={{ pointerEvents: 'none' }}>
        <div>
          <Text size="xl" ta="center" aria-hidden="true">
            &#128247;
          </Text>
          <Text id={PHOTO_INSTRUCTIONS_ID} size="sm" c="gray.6" ta="center">
            Arrastra una foto o haz clic para seleccionar
          </Text>
          <Text id={PHOTO_LIMIT_ID} size="xs" c="gray.6" ta="center">
            Max 5MB
          </Text>
        </div>
      </Group>
    </Dropzone>
  );
}
