import {
  Button,
  Modal,
  NumberInput,
  NativeSelect,
  SimpleGrid,
  Stack,
  TextInput,
} from '@mantine/core';
import type { UseFormReturnType } from '@mantine/form';
import type { IngresoFormValues } from './IngresoFormModal';

const EDIT_INGRESO_DESCRIPTION_ERROR_ID = 'edit-ingreso-description-error';
const EDIT_INGRESO_AMOUNT_ERROR_ID = 'edit-ingreso-amount-error';
const EDIT_INGRESO_CATEGORY_ERROR_ID = 'edit-ingreso-category-error';

export function EditIngresoModal({
  opened,
  onClose,
  form,
  categoryData,
  onSubmit,
}: Readonly<{
  opened: boolean;
  onClose: () => void;
  form: UseFormReturnType<IngresoFormValues>;
  categoryData: Array<{ value: string; label: string }>;
  onSubmit: (values: IngresoFormValues) => void | Promise<void>;
}>) {
  return (
    <Modal opened={opened} onClose={onClose} title="Editar ingreso">
      <form onSubmit={form.onSubmit(onSubmit)} noValidate>
        <Stack gap="sm">
          <TextInput
            label="Descripcion"
            required
            {...form.getInputProps('descripcion')}
            errorProps={{
              id: EDIT_INGRESO_DESCRIPTION_ERROR_ID,
              role: 'alert',
              'aria-live': 'assertive',
            }}
          />
          <SimpleGrid cols={2}>
            <NumberInput
              label="Monto ($)"
              required
              hideControls
              {...form.getInputProps('monto')}
              errorProps={{
                id: EDIT_INGRESO_AMOUNT_ERROR_ID,
                role: 'alert',
                'aria-live': 'assertive',
              }}
            />
            <NativeSelect
              label="Categoria"
              data={categoryData}
              required
              {...form.getInputProps('categoria')}
              errorProps={{
                id: EDIT_INGRESO_CATEGORY_ERROR_ID,
                role: 'alert',
                'aria-live': 'assertive',
              }}
            />
          </SimpleGrid>
          <TextInput type="date" label="Fecha" required {...form.getInputProps('fecha')} />
          <Button type="submit" fullWidth mt="md">
            Actualizar ingreso
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
