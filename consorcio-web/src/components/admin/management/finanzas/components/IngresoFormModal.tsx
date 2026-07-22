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

const INGRESO_DESCRIPTION_ERROR_ID = 'ingreso-description-error';
const INGRESO_AMOUNT_ERROR_ID = 'ingreso-amount-error';
const INGRESO_CATEGORY_ERROR_ID = 'ingreso-category-error';

export interface IngresoFormValues {
  descripcion: string;
  monto: number;
  categoria: string;
  fecha: string;
}

export function IngresoFormModal({
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
    <Modal opened={opened} onClose={onClose} title="Registrar Ingreso">
      <form onSubmit={form.onSubmit(onSubmit)} noValidate>
        <Stack gap="sm">
          <TextInput
            label="Descripcion"
            required
            {...form.getInputProps('descripcion')}
            errorProps={{
              id: INGRESO_DESCRIPTION_ERROR_ID,
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
              errorProps={{ id: INGRESO_AMOUNT_ERROR_ID, role: 'alert', 'aria-live': 'assertive' }}
            />
            <NativeSelect
              label="Categoria"
              data={categoryData}
              required
              {...form.getInputProps('categoria')}
              errorProps={{
                id: INGRESO_CATEGORY_ERROR_ID,
                role: 'alert',
                'aria-live': 'assertive',
              }}
            />
          </SimpleGrid>
          <TextInput type="date" label="Fecha" required {...form.getInputProps('fecha')} />
          <Button type="submit" fullWidth mt="md" color="green">
            Guardar Ingreso
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
