import { Button, Container, Group, Tabs, Title, Text } from '@mantine/core';
import { LoadingState } from '../../ui';
import {
  IconArrowUpRight,
  IconCoin,
  IconPlus,
  IconReceipt,
} from '../../ui/icons';
import { EditGastoModal } from './finanzas/components/EditGastoModal';
import { EditIngresoModal } from './finanzas/components/EditIngresoModal';
import { FinanzasSummaryTab } from './finanzas/components/FinanzasSummaryTab';
import { GastoFormModal } from './finanzas/components/GastoFormModal';
import { GastosTable } from './finanzas/components/GastosTable';
import { IngresoFormModal } from './finanzas/components/IngresoFormModal';
import { IngresosTable } from './finanzas/components/IngresosTable';
import { OptionModal } from './finanzas/components/OptionModal';
import { useFinanzasController } from './finanzas/useFinanzasController';

export default function FinanzasPanel() {
  const controller = useFinanzasController();

  if (controller.loading && !controller.balance) {
    return <LoadingState />;
  }

  return (
    <Container size="xl" py="md">
      <Group justify="space-between" mb="xl">
        <div>
          <Title order={2}>Administracion Financiera</Title>
          <Text c="dimmed">Seguimiento de gastos y ejecucion presupuestaria</Text>
        </div>
        <Button leftSection={<IconPlus size={18} />} onClick={controller.gastoModal.open} color="red">
          Registrar Gasto
        </Button>
        <Button
          leftSection={<IconPlus size={18} />}
          onClick={controller.ingresoModal.open}
          color="green"
        >
          Registrar Ingreso
        </Button>
      </Group>

      <Tabs value={controller.activeTab} onChange={controller.setActiveTab}>
        <Tabs.List mb="lg">
          <Tabs.Tab value="balance" leftSection={<IconCoin size={16} />}>
            Balance y Presupuesto
          </Tabs.Tab>
          <Tabs.Tab value="gastos" leftSection={<IconReceipt size={16} />}>
            Libro de Gastos
          </Tabs.Tab>
          <Tabs.Tab value="ingresos" leftSection={<IconArrowUpRight size={16} />}>
            Libro de Ingresos
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="balance">
          <FinanzasSummaryTab balance={controller.balance} currentYear={controller.currentYear} />
        </Tabs.Panel>

        <Tabs.Panel value="gastos">
          <GastosTable gastos={controller.gastos} onEdit={controller.handleOpenEditCategory} />
        </Tabs.Panel>

        <Tabs.Panel value="ingresos">
          <IngresosTable ingresos={controller.ingresos} onEdit={controller.handleOpenEditIngreso} />
        </Tabs.Panel>
      </Tabs>

      <GastoFormModal
        opened={controller.gastoOpened}
        onClose={controller.gastoModal.close}
        form={controller.form}
        categoryData={controller.categoryData}
        comprobanteFile={controller.gastoComprobanteFile}
        setComprobanteFile={controller.setGastoComprobanteFile}
        onOpenCategory={controller.categoryModal.open}
        onSubmit={controller.handleCreateGasto}
        loading={controller.uploadingComprobante}
      />

      <EditGastoModal
        opened={controller.editGastoOpened}
        onClose={controller.editGastoModal.close}
        form={controller.editCategoryForm}
        categoryData={controller.categoryData}
        editingGasto={controller.editingGasto}
        onEditingGastoChange={controller.setEditingGastoComprobanteUrl}
        comprobanteFile={controller.gastoEditComprobanteFile}
        setComprobanteFile={controller.setGastoEditComprobanteFile}
        onOpenCategory={controller.categoryModal.open}
        onSubmit={controller.handleUpdateCategory}
        loading={controller.uploadingComprobante}
      />

      <OptionModal
        opened={controller.categoryOpened}
        onClose={controller.categoryModal.close}
        title="Nueva categoria"
        value={controller.newCategoryName}
        onChange={controller.setNewCategoryName}
        onSave={controller.handleAddCategory}
        placeholder="Ej: viaticos"
        saveLabel="Guardar categoria"
      />

      <IngresoFormModal
        opened={controller.ingresoOpened}
        onClose={controller.ingresoModal.close}
        form={controller.ingresoForm}
        sourceData={controller.sourceData}
        comprobanteFile={controller.ingresoComprobanteFile}
        setComprobanteFile={controller.setIngresoComprobanteFile}
        onOpenSource={controller.sourceModal.open}
        onSubmit={controller.handleCreateIngreso}
        loading={controller.uploadingComprobante}
      />

      <EditIngresoModal
        opened={controller.editIngresoOpened}
        onClose={controller.editIngresoModal.close}
        form={controller.editIngresoForm}
        sourceData={controller.sourceData}
        comprobanteFile={controller.ingresoEditComprobanteFile}
        setComprobanteFile={controller.setIngresoEditComprobanteFile}
        onOpenSource={controller.sourceModal.open}
        onSubmit={controller.handleUpdateIngreso}
        loading={controller.uploadingComprobante}
      />

      <OptionModal
        opened={controller.sourceOpened}
        onClose={controller.sourceModal.close}
        title="Nueva fuente de ingreso"
        value={controller.newSourceName}
        onChange={controller.setNewSourceName}
        onSave={controller.handleAddSource}
        placeholder="Ej: convenio"
        saveLabel="Guardar fuente"
      />
    </Container>
  );
}
