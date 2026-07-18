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

const GASTO_DESCRIPTION_ERROR_ID = 'gasto-description-error';
const GASTO_AMOUNT_ERROR_ID = 'gasto-amount-error';
const GASTO_CATEGORY_ERROR_ID = 'gasto-category-error';

export interface GastoFormValues {
  descripcion: string;
  monto: number;
  categoria: string;
  fecha: string;
}

export function GastoFormModal({
  opened,
  onClose,
  form,
  categoryData,
  onSubmit,
}: Readonly<{
  opened: boolean;
  onClose: () => void;
  form: UseFormReturnType<GastoFormValues>;
  categoryData: Array<{ value: string; label: string }>;
  onSubmit: (values: GastoFormValues) => void | Promise<void>;
}>) {
  return (
    <Modal opened={opened} onClose={onClose} title="Registrar Gasto de Caja">
      <form onSubmit={form.onSubmit(onSubmit)} noValidate>
        <Stack gap="sm">
          <TextInput
            label="Descripcion del Gasto"
            required
            {...form.getInputProps('descripcion')}
            errorProps={{ id: GASTO_DESCRIPTION_ERROR_ID, role: 'alert', 'aria-live': 'assertive' }}
          />
          <SimpleGrid cols={2}>
            <NumberInput
              label="Monto ($)"
              required
              hideControls
              {...form.getInputProps('monto')}
              errorProps={{ id: GASTO_AMOUNT_ERROR_ID, role: 'alert', 'aria-live': 'assertive' }}
            />
            <NativeSelect
              label="Categoria"
              data={categoryData}
              required
              {...form.getInputProps('categoria')}
              errorProps={{ id: GASTO_CATEGORY_ERROR_ID, role: 'alert', 'aria-live': 'assertive' }}
            />
          </SimpleGrid>
          <TextInput type="date" label="Fecha" required {...form.getInputProps('fecha')} />
          <Button type="submit" fullWidth mt="md" color="red">
            Guardar Gasto
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
