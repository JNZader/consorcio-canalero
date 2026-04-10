import { Button, Container, Group, Text, Title } from '@mantine/core';
import { LoadingState } from '../../ui';
import { IconCalendar } from '../../ui/icons';
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
      <Group justify="space-between" mb="xl">
        <div>
          <Title order={2}>Reuniones de Comision</Title>
          <Text c="dimmed">Planificacion de orden del dia y actas</Text>
        </div>
        <Button
          leftSection={<IconCalendar size={18} />}
          onClick={controller.createModal.open}
          color="violet"
        >
          Nueva Reunion
        </Button>
      </Group>

      <ReunionCreateModal
        opened={controller.createOpened}
        onClose={controller.createModal.close}
        form={controller.reunionForm}
        newChecklistPoint={controller.newChecklistPoint}
        setNewChecklistPoint={controller.setNewChecklistPoint}
        onAddChecklistPoint={controller.handleAddChecklistPoint}
        onSubmit={controller.handleCreateReunion}
      />

      <ReunionesGrid reuniones={controller.reuniones} onViewAgenda={controller.handleViewAgenda} />

      <AgendaModal
        opened={controller.agendaOpened}
        onClose={controller.agendaModal.close}
        selectedReunion={controller.selectedReunion}
        agenda={controller.agenda}
        exporting={controller.exporting}
        onExport={controller.handleExportPDF}
        form={controller.itemForm}
        onAddTopic={controller.handleAddTopic}
        availableEntities={controller.availableEntities}
        loadingEntities={controller.loadingEntities}
      />
    </Container>
  );
}
