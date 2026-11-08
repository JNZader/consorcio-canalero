import { Button, Container, Text } from '@mantine/core';
import { erroresUi } from '../../../lib/userFacingError';
import { ConfirmDialog } from '../../ui/ConfirmDialog';
import { IconCalendar } from '../../ui/icons';
import { LoadingState } from '../../ui/LoadingState';
import { PageHeader } from '../../ui/PageHeader';
import { AgendaModal } from './reuniones/components/AgendaModal';
import { ReunionCreateModal } from './reuniones/components/ReunionCreateModal';
import { ReunionesGrid } from './reuniones/components/ReunionesGrid';
import { useReunionesController } from './reuniones/useReunionesController';

export default function ReunionesPanel() {
  const controller = useReunionesController();

  if (controller.loading) {
    return <LoadingState />;
  }

  return (
    <Container size="xl" py="md">
      <PageHeader
        title="Reuniones de Comisión"
        subtitle="Planificación de orden del día y actas"
        actions={
          <Button leftSection={<IconCalendar size={18} />} onClick={controller.createModal.open}>
            Nueva Reunión
          </Button>
        }
      />

      <ReunionCreateModal
        opened={controller.createOpened}
        onClose={controller.createModal.close}
        form={controller.reunionForm}
        newChecklistPoint={controller.newChecklistPoint}
        setNewChecklistPoint={controller.setNewChecklistPoint}
        onAddChecklistPoint={controller.handleAddChecklistPoint}
        onSubmit={controller.handleCreateReunion}
        submitting={controller.submitting}
      />

      {controller.loadError ? (
        <LoadingState
          status="error"
          title={erroresUi.cargarReuniones.titulo}
          message={erroresUi.cargarReuniones.detalle}
          action={
            <Button mt="sm" onClick={() => void controller.fetchReuniones()}>
              Reintentar
            </Button>
          }
        />
      ) : controller.reuniones.length === 0 ? (
        <Text c="dimmed">No hay reuniones cargadas.</Text>
      ) : (
        <ReunionesGrid reuniones={controller.reuniones} onViewAgenda={controller.handleViewAgenda} />
      )}

      <AgendaModal
        opened={controller.agendaOpened}
        onClose={controller.agendaModal.close}
        selectedReunion={controller.selectedReunion}
        agenda={controller.agenda}
        exporting={controller.exporting}
        onExport={controller.handleExportPDF}
        form={controller.itemForm}
        onAddTopic={controller.handleAddTopic}
        onDeleteTopic={controller.handleDeleteTopic}
        onToggleComplete={controller.handleToggleComplete}
        togglingAgendaItemId={controller.togglingAgendaItemId}
        deletingAgendaItemId={controller.deletingAgendaItemId}
        availableEntities={controller.availableEntities}
        loadingEntities={controller.loadingEntities}
      />

      <ConfirmDialog
        opened={controller.topicPendingDelete !== null}
        title="Eliminar tema"
        message={
          controller.topicPendingDelete
            ? `¿Eliminar el tema "${controller.topicPendingDelete.titulo}" de la agenda? Esta acción no se puede deshacer.`
            : ''
        }
        confirmLabel="Eliminar"
        onConfirm={() => void controller.confirmDeleteTopic()}
        onClose={controller.cancelDeleteTopic}
        loading={controller.deletingAgendaItemId !== null}
      />
    </Container>
  );
}
