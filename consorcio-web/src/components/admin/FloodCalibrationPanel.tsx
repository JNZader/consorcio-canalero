import {
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  Modal,
  Paper,
  Progress,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';

import { CalendarGrid } from './floodCalibration/CalendarGrid';
import { FloodEventsPanel } from './floodCalibration/FloodEventsPanel';
import { FloodSuggestionsPanel } from './floodCalibration/FloodSuggestionsPanel';
import { FloodTrainingPanel } from './floodCalibration/FloodTrainingPanel';
import { useFloodCalibrationController } from './floodCalibration/useFloodCalibrationController';
import {
  IconAlertTriangle,
  IconCalendar,
  IconCheck,
  IconCloudRain,
  IconDroplet,
  IconPlayerPlay,
  IconSatellite,
} from '../ui/icons';

export default function FloodCalibrationPanel() {
  const controller = useFloodCalibrationController();

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Group gap="xs">
          <IconDroplet size={24} />
          <Title order={3}>Calibracion de Modelo de Inundacion</Title>
        </Group>
        <Badge variant="light" color="blue" size="lg">
          {controller.events.length} eventos guardados
        </Badge>
      </Group>

      {controller.error && (
        <Alert color="red" icon={<IconAlertTriangle />} title="Error">
          {controller.error}
        </Alert>
      )}

      {!controller.rainfallLoading && Object.keys(controller.rainfallByDate).length === 0 && (
        <Alert color="blue" icon={<IconCloudRain size={18} />} title="Sin datos de lluvia">
          <Stack gap="xs">
            <Text size="sm">
              No hay datos de precipitacion cargados. Cargalos para ver la lluvia en el calendario y recibir sugerencias de eventos.
            </Text>
            {controller.backfillLoading && controller.backfillStatus ? (
              <Stack gap={4}>
                <Group justify="space-between">
                  <Text size="xs" c="dimmed">
                    {controller.backfillStatus.state === 'PENDING'
                      ? 'Esperando worker...'
                      : `Batch ${controller.backfillStatus.current ?? 0} / ${controller.backfillStatus.total ?? 0} — ${(controller.backfillStatus.records ?? 0).toLocaleString()} registros`}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {controller.backfillStatus.total > 0
                      ? `${Math.round((controller.backfillStatus.current / controller.backfillStatus.total) * 100)}%`
                      : ''}
                  </Text>
                </Group>
                <Progress
                  value={(controller.backfillStatus.total ?? 0) > 0 ? ((controller.backfillStatus.current ?? 0) / (controller.backfillStatus.total ?? 1)) * 100 : 0}
                  animated={controller.backfillStatus.state === 'PROGRESS' || controller.backfillStatus.state === 'PENDING'}
                  color="blue"
                  size="sm"
                />
              </Stack>
            ) : (
              <Group align="center">
                <SegmentedControl
                  size="xs"
                  value={controller.backfillSource}
                  onChange={(v) => controller.setBackfillSource(v as 'CHIRPS' | 'IMERG')}
                  data={[
                    { label: 'CHIRPS (histórico)', value: 'CHIRPS' },
                    { label: 'IMERG (eventos extremos)', value: 'IMERG' },
                  ]}
                />
                <Button size="xs" variant="filled" loading={controller.backfillLoading} onClick={controller.handleBackfill}>
                  Cargar datos
                </Button>
              </Group>
            )}
          </Stack>
        </Alert>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: controller.isMobile ? '1fr' : 'minmax(280px, 340px) 1fr', gap: 16 }}>
        <Stack gap="md">
          <Group justify="flex-end">
            <SegmentedControl
              size="xs"
              value={controller.rainfallSource}
              onChange={(v) => controller.setRainfallSource(v as 'CHIRPS' | 'IMERG' | 'best')}
              data={[
                { label: 'Mejor', value: 'best' },
                { label: 'CHIRPS', value: 'CHIRPS' },
                { label: 'IMERG', value: 'IMERG' },
              ]}
            />
          </Group>

          <CalendarGrid
            year={controller.calendarYear}
            month={controller.calendarMonth}
            availableDates={controller.availableDatesSet}
            selectedDay={controller.selectedDate}
            loadingDates={controller.loadingDates || controller.rainfallLoading}
            onSelectDay={controller.handleSelectDay}
            onPrevMonth={controller.handlePrevMonth}
            onNextMonth={controller.handleNextMonth}
            rainfallByDate={controller.rainfallByDate}
          />

          {controller.selectedDate && (
            <Paper p="md" withBorder radius="md">
              <Stack gap="sm">
                <Group justify="space-between">
                  <Text fw={600} size="sm">
                    <IconCalendar size={16} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                    {controller.selectedDate}
                  </Text>
                  <Badge color={controller.labeledCount > 0 ? 'blue' : 'gray'}>
                    {controller.labeledCount} zona{controller.labeledCount !== 1 ? 's' : ''} etiquetada{controller.labeledCount !== 1 ? 's' : ''}
                  </Badge>
                </Group>

                <TextInput
                  label="Descripcion (opcional)"
                  placeholder="Ej: Inundacion post-tormenta"
                  value={controller.eventDescription}
                  onChange={(e) => controller.setEventDescription(e.currentTarget.value)}
                  size="sm"
                />

                <Group gap="sm">
                  <Button
                    fullWidth
                    onClick={controller.handleSaveEvent}
                    disabled={!controller.canSave}
                    loading={controller.savingEvent}
                    leftSection={<IconCheck size={16} />}
                    color="green"
                  >
                    Guardar Evento
                  </Button>
                  <Button fullWidth variant="light" color="gray" onClick={controller.clearLabels} disabled={controller.labeledCount === 0}>
                    Limpiar Etiquetas
                  </Button>
                </Group>

                <Divider />
                <Text size="xs" c="dimmed" fw={500}>Leyenda (click en zona para alternar):</Text>
                <Group gap="md">
                  <Group gap={4}><div style={{ width: 12, height: 12, borderRadius: 2, background: '#ef4444' }} /><Text size="xs">Inundado</Text></Group>
                  <Group gap={4}><div style={{ width: 12, height: 12, borderRadius: 2, background: '#22c55e' }} /><Text size="xs">No inundado</Text></Group>
                  <Group gap={4}><div style={{ width: 12, height: 12, borderRadius: 2, background: '#9ca3af' }} /><Text size="xs">Sin etiquetar</Text></Group>
                </Group>
              </Stack>
            </Paper>
          )}
        </Stack>

        <Card padding={0} radius="md" withBorder style={{ minHeight: 500, position: 'relative' }}>
          <div ref={controller.mapRef} style={{ width: '100%', height: 500, borderRadius: 'var(--mantine-radius-md)' }} />
          {controller.loadingImage && (
            <div style={{ position: 'absolute', inset: 0, background: 'rgba(255,255,255,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 'var(--mantine-radius-md)' }}>
              <Stack align="center"><Loader size="lg" /><Text>Cargando imagen satelital...</Text></Stack>
            </div>
          )}
          {!controller.selectedDate && !controller.loadingImage && (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
              <Paper p="lg" radius="md" shadow="sm" style={{ pointerEvents: 'auto', textAlign: 'center' }}>
                <IconSatellite size={32} style={{ opacity: 0.4, marginBottom: 8 }} />
                <Text c="dimmed" size="sm">Selecciona un dia del calendario</Text>
                <Text c="dimmed" size="xs">para ver la imagen satelital y etiquetar zonas</Text>
              </Paper>
            </div>
          )}
        </Card>
      </div>

      <FloodSuggestionsPanel
        suggestionsExpanded={controller.suggestionsExpanded}
        onToggleExpanded={() => controller.setSuggestionsExpanded((prev) => !prev)}
        suggestionsCount={controller.suggestionsCount}
        suggestionsLoading={controller.suggestionsLoading}
        onRefresh={controller.fetchSuggestions}
        suggestions={controller.suggestions}
        onSuggestionClick={controller.handleSuggestionClick}
      />

      <div style={{ display: 'grid', gridTemplateColumns: controller.isMobile ? '1fr' : '1fr 1fr', gap: 16 }}>
        <FloodEventsPanel
          eventsLoading={controller.eventsLoading}
          events={controller.events}
          onRefresh={controller.fetchEvents}
          expandedEventId={controller.expandedEventId}
          onToggleEvent={controller.handleToggleEvent}
          expandedEventLoading={controller.expandedEventLoading}
          expandedEventDetail={controller.expandedEventDetail}
          ndwiBaselines={controller.ndwiBaselines}
          onRequestDelete={(id) => {
            controller.setPendingDeleteId(id);
            controller.openDeleteConfirm();
          }}
        />

        <FloodTrainingPanel
          eventsLength={controller.events.length}
          ndwiBaselinesLength={controller.ndwiBaselines.length}
          onRequestTrain={controller.openTrainConfirm}
          trainingLoading={controller.trainingLoading}
          baselineLoading={controller.baselineLoading}
          onComputeBaseline={controller.handleComputeBaseline}
          trainingResult={controller.trainingResult}
        />
      </div>

      <Modal opened={controller.deleteConfirmOpened} onClose={controller.closeDeleteConfirm} title="Confirmar eliminacion" centered size="sm">
        <Stack gap="md">
          <Text size="sm">
            ¿Estas seguro de que queres eliminar este evento? Esta accion no se puede deshacer.
            Las etiquetas y features asociadas tambien seran eliminadas.
          </Text>
          <Group justify="flex-end" gap="sm">
            <Button variant="default" onClick={controller.closeDeleteConfirm}>Cancelar</Button>
            <Button color="red" onClick={controller.handleConfirmDelete}>Eliminar</Button>
          </Group>
        </Stack>
      </Modal>

      <Modal opened={controller.trainConfirmOpened} onClose={controller.closeTrainConfirm} title="Confirmar entrenamiento" centered size="sm">
        <Stack gap="md">
          <Text size="sm">
            Se creara un backup del modelo actual antes de entrenar.
            El proceso puede tardar unos segundos.
          </Text>
          <Group gap="lg">
            <div>
              <Text size="xs" c="dimmed">Eventos disponibles</Text>
              <Text fw={600}>{controller.events.length}</Text>
            </div>
          </Group>
          <Group justify="flex-end" gap="sm">
            <Button variant="default" onClick={controller.closeTrainConfirm}>Cancelar</Button>
            <Button color="blue" onClick={controller.handleConfirmTrain} leftSection={<IconPlayerPlay size={16} />}>Entrenar</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
